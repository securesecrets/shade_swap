#!/usr/bin/python3

import argparse
import json
from json import JSONDecodeError
from base64 import b64encode
import time

from secret_sdk.client.lcd import LCDClient
from os import getenv, path, mkdir
from subprocess import Popen, PIPE


data_folder = getenv("HOME") + "/.shadeswap"
data_file = f"{data_folder}/.data.json"
config_file = f"{data_folder}/config.json"

default_config = {
    "swap_gas": 300000,
    "txhash_retries": 30,
    "lcd_endpoint": "https://loadbalancer1.api.securesecrets.org",
    "chain_id": "secret-4",
    "amm_factory": "secret1ja0hcwvy76grqkpgwznxukgd7t8a8anmmx05pp",
    "swap_router": "secret1pjhdug87nxzv0esxasmeyfsucaj98pw4334wyc",
    "query_router": "secret17gnlxnwux0szd7qhl90ym8lw22qvedjz4v09dm",
    "oracle": "secret10n2xl5jmez6r9umtdrth78k0vwmce0l5m9f5dm",
    "secretcli_binary": "secretcli",
}

if not path.exists(data_folder):
    print("Creating config folder...")
    mkdir(data_folder)

if not path.isfile(config_file):
    print("Generating config...")
    open(config_file, "w+").write(json.dumps(default_config, indent=2))

config = json.loads(open(config_file).read())


def run_command(command):
    """
    Will run any cli command and return its output after waiting a set amount
    :param command: Array of command to run
    :param wait: Time to wait for command
    :return: Output string
    """
    p = Popen(command, stdout=PIPE, stderr=PIPE, text=True)
    output, err = p.communicate()
    status = p.wait()
    if err and not output:
        return err
    return output


def query_hash(hash):
    return run_command([config["secretcli_binary"], "q", "tx", hash])


def compute_hash(hash):
    return run_command([config["secretcli_binary"], "q", "compute", "tx", hash])


def run_command_compute_hash(command):
    out = run_command(command)

    try:
        txhash = json.loads(out)["txhash"]
        print("TX Hash:", txhash)

    except Exception as e:
        raise e

    for _ in range(config["txhash_retries"]):
        try:
            out = compute_hash(txhash)
            out = json.loads(out)
            tx_data = json.loads(query_hash(txhash))
            return out
        except json.JSONDecodeError as e:
            time.sleep(1)
    print(out)


def get_secretcli_config():
    return json.loads(run_command([config["secretcli_binary"], "config"]))


def verify_secretcli_mainnet(config):
    return config["chain-id"] == "secret-4"


"""
def gen_batch_queries(contract, queries):
    return (
        {
            "id": b64encode(i),
            "contract": contract,
            "query": b64encode(json.dumps(q)),
        }
        for q, i in enumerate(query)
    )


def batch_query(client, batch_queries):
    response = client.wasm.contract_query(
        config['query_router'],
        {"batch": {"queries": list(batch_queries)}},
    )
"""


def fetch_pairs(client, factory):
    start = 0

    while True:
        response = client.wasm.contract_query(
            factory,
            {
                "list_a_m_m_pairs": {
                    "pagination": {
                        "start": start,
                        "limit": 30,
                    }
                }
            },
        )
        pairs = response["list_a_m_m_pairs"]["amm_pairs"]

        yield from pairs

        if len(pairs) < 30:
            break

        start += 30


def fetch_pair_infos(client, pairs):
    return (
        client.wasm.contract_query(pair, {"get_pair_info": {}})["get_pair_info"]
        for pair in pairs
    )


def fetch_token_infos(client, tokens):
    return (
        client.wasm.contract_query(token, {"token_info": {}})["token_info"]
        for token in tokens
    )


def fetch_balances(client, tokens, viewing_key):
    yield from (
        client.wasm.contract_query(
            token, {"balance": {"address": "", "key": viewing_key}}
        )
        for token in tokens
    )


def pull_factory_token_addrs(factory_pairs):

    for pair in factory_pairs:
        yield from (t["custom_token"]["contract_addr"] for t in pair["pair"][:2])


def swap_simulation(client, pair, in_token, code_hash, in_amount):
    return client.wasm.contract_query(
        pair,
        {
            "swap_simulation": {
                "offer": {
                    "token": {
                        "custom_token": {
                            "contract_addr": in_token,
                            "token_code_hash": code_hash,
                        }
                    },
                    "amount": str(in_amount),
                }
            }
        },
    )["swap_simulation"]


def oracle_price(client, oracle, symbol):
    return int(client.wasm.contract_query(
        oracle,
        {
            "get_price": {
                "key": symbol,
            }
        },
    )['data']['rate']) / 10**18


def init_data(client, factory):
    print("Fetching pairs...")
    pairs = list(fetch_pairs(client, factory))
    print("Found", len(pairs), "Pairs")
    # unique tokens to list for predictable ordering
    tokens = list(set(pull_factory_token_addrs(pairs)))
    print("Found", len(tokens), "Tokens")

    # Build routes (forward and back, single pair only for now)
    print("Generating Routes...")
    routes = dict()
    for pair in pairs:
        token_a, token_b = (
            pair["pair"][0]["custom_token"]["contract_addr"],
            pair["pair"][1]["custom_token"]["contract_addr"],
        )

        if token_a not in routes:
            routes[token_a] = dict()
        if token_b not in routes:
            routes[token_b] = dict()

        routes[token_a][token_b] = pair["address"]
        routes[token_b][token_a] = pair["address"]

    # Map the code hashes for when they are needed
    print("Compiling Code Hashes...")
    code_hashes = dict()
    for pair in pairs:
        code_hashes[pair["address"]] = pair["code_hash"]
        for t in pair["pair"][:2]:
            code_hashes[t["custom_token"]["contract_addr"]] = t["custom_token"][
                "token_code_hash"
            ]

    print("Fetching Token Infos (this will take a while)...")
    token_infos = list(fetch_token_infos(client, tokens))

    return {
        "tokens": {info["symbol"]: token for info, token in zip(token_infos, tokens)},
        "token_info": {token: info for token, info in zip(tokens, token_infos)},
        # { in_token: { out_token: pair }}
        "routes": routes,
        "code_hash": code_hashes,
    }


def recommend_symbols(symbols, in_token):
    for symbol in symbols:
        if in_token.lower() in symbol.lower():
            yield symbol


if __name__ == "__main__":

    parser = argparse.ArgumentParser()

    parser.add_argument(
        "-i", "--init", help="Initialize pairs & tokens data", action="store_true"
    )

    """
    parser.add_argument(
        "-vk",
        "--viewing_key",
        type=str,
        help="Sets the viewing_key to use in the config",
    )
    parser.add_argument(
        "-svk",
        "--set_viewing_key",
        type=str,
        help="Sets the viewing key on input token contract",
    )
    parser.add_argument(
        "-svka",
        "--set_viewing_key_all",
        type=str,
        help="Sets the viewing key on all token contracts",
    )
    """

    parser.add_argument("--input", type=str, help="Input token to swap")
    parser.add_argument("--output", type=str, help="Output token from swap")
    parser.add_argument("--amount", type=float, help="Amount to swap")
    """
    parser.add_argument("--full_balance", action="store_true", help="Swap full balance")
    parser.add_argument(
        "-slip", "--slippage", type=float, help="Acceptable slippage as a percent <= 1.0"
    )
    """
    parser.add_argument(
        "-sim", "--simulate", help="Only simulate swap", action="store_true"
    )
    parser.add_argument(
        "-k",
        "--key",
        help="secretcli key to use to send txs",
        type=str,
    )

    parser.add_argument(
        "--oracle_price",
        help="Symbol to check oracle price before executing swap",
        type=str,
    )

    parser.add_argument(
        "--gt",
        help="Swap requirement for price greater",
        type=float,
    )
    parser.add_argument(
        "--ge",
        help="Swap requirement for price greater or equal",
        type=float,
    )
    parser.add_argument(
        "--lt",
        help="Swap requirement for price less",
        type=float,
    )
    parser.add_argument(
        "--le",
        help="Swap requirement for price less or equal",
        type=float,
    )

    """
    parser.add_argument("min", help="Output token from swap")
    parser.add_argument("max", help="Output token from swap")
    parser.add_argument("rnd", help="Output token from swap")
    """

    args = parser.parse_args()

    client = LCDClient(chain_id=config["chain_id"], url=config["lcd_endpoint"])

    try:
        if args.init:
            data = init_data(client, config["amm_factory"])
            print("Saving initialized data...")
            open(data_file, "w+").write(json.dumps(data))

        else:
            data = json.loads(open(data_file).read())

    except FileNotFoundError as e:
        print("Data has not been initialized, try: \n\tshade-swap --init")
        raise e
    except JSONDecodeError as e:
        print("Data has not been initialized, try: \n\tshade-swap --init")
        raise e

    if any((args.input, args.output, (args.amount or args.full_balance))):
        if args.amount and args.full_balance:
            print("--amount and --full_balance are conflicting, use one or the other")
            exit(1)

        if args.input not in data["tokens"]:
            recs = list(recommend_symbols(data["tokens"].keys(), args.input))
            print("Could not match", args.input)

            if recs:
                print(f"Did you mean ({','.join(recs)})?")
            exit(1)

        if args.output not in data["tokens"]:
            recs = list(recommend_symbols(data["tokens"].keys(), args.output))
            print("Could not match", args.output)

            if recs:
                print(f"Did you mean ({','.join(recs)})?")
            exit(1)

        if not all((args.input, args.output, args.amount)):
            print("Missing required field for swap, exiting...")
            exit(1)

        in_token = data["tokens"][args.input]
        out_token = data["tokens"][args.output]
        input_amount = int(args.amount * 10 ** data["token_info"][in_token]["decimals"])

        print("Swapping", args.amount, args.input, "for", args.output)

        pair = data["routes"][in_token][out_token]

        if not pair:
            print("No pair for this trade, multi-hop routing TBD")
            exit(1)

        if args.oracle_price:
            if not any((args.le, args.lt, args.gt, args.ge)):
                print('Missing comparison for oracle_price (le, lt, gt, ge)')
                exit(1)

            print('Checking oracle price for', args.oracle_price)
            price = oracle_price(client, config['oracle'], args.oracle_price)

            if args.le:
                if price <= args.le:
                    print('Passed comparison', price, '<=', args.le)
                else:
                    print('Failed comparison', price, '<=', args.le)
                    exit(1)
                
            if args.lt:
                if price < args.lt:
                    print('Passed comparison', price, '<', args.lt)
                else:
                    print('Failed comparison', price, '<', args.lt)
                    exit(1)
            if args.gt:
                if price > args.gt:
                    print('Passed comparison', price, '>', args.gt)
                else:
                    print('Failed comparison', price, '>', args.gt)
                    exit(1)
            if args.ge:
                if price >= args.ge:
                    print('Passed comparison', price, '>=', args.ge)
                else:
                    print('Failed comparison', price, '>=', args.ge)
                    exit(1)

        if args.simulate:
            result = swap_simulation(
                client, pair, in_token, data["code_hash"][in_token], input_amount
            )

            received = (
                int(result["result"]["return_amount"])
                / 10 ** data["token_info"][out_token]["decimals"]
            )

            print("Sim Output:", "{:.20f}".format(received).strip("0"), args.output)

        else:

            if not args.key:
                print("Must provide secretcli key for executing txs")
                exit(1)

            msg = {
                "send": {
                    "recipient": pair,
                    "recipient_code_hash": data["code_hash"][pair],
                    "amount": str(input_amount),
                    "msg": b64encode(
                        json.dumps({"swap_tokens": {}}).encode("utf-8")
                    ).decode("utf-8"),
                }
            }
            command = [
                config["secretcli_binary"],
                "tx",
                "compute",
                "execute",
                in_token,
                json.dumps(msg),
                "--from",
                args.key,
                "--gas",
                str(config["swap_gas"]),
                "-y",
            ]

            swap_result = run_command_compute_hash(command)

            # swap_result = json.loads(result)
            for log in swap_result["output_logs"]:
                for attr in log["attributes"]:
                    if attr["key"].strip() == "amount_out":
                        print(
                            "Received",
                            "{:.20f}".format(
                                int(attr["value"])
                                / 10 ** data["token_info"][out_token]["decimals"]
                            ).strip("0"),
                            args.output,
                        )
