This is a command line tool to execute swaps on the Shade Protocol AMM. It uses SecretPy to query data, and uses the local install of secretcli for key management and executing transactions. secretcli must be installed and configured to for the same Secret Network blockchain (default secret-4).

To setup, run `shade_swap.py --init` to load the pairs from the factory and query token infos for each token. Querying token infos will take some time. 

The config lives in `~/.shadeswap/config.json`, and the initialization will populate `~/.shadeswap/.data.json` with all the token infos, pairs, and any other data needed to operate. If a new pair is added, this data will need to be reinitialized with `shade_swap.py --init`.

If the secretcli configuration is not configured for the same chainor is misconfigured this tool will fail to execute swaps.

If you are using `secretd` instead of `secretcli` you can set `"secretcli_binary": "secretd"`

Default Config:
```
{
  "swap_gas": 400000,
  "txhash_retries": 30,
  "lcd_endpoint": "https://loadbalancer1.api.securesecrets.org",
  "chain_id": "secret-4",
  "amm_factory": "secret1ja0hcwvy76grqkpgwznxukgd7t8a8anmmx05pp",
  "swap_router": "secret1pjhdug87nxzv0esxasmeyfsucaj98pw4334wyc",
  "oracle": "secret10n2xl5jmez6r9umtdrth78k0vwmce0l5m9f5dm",
  "query_router": "secret17gnlxnwux0szd7qhl90ym8lw22qvedjz4v09dm",
  "secretcli_binary": "secretcli"
}
```

```
usage: shade_swap.py [-h] [-i] [--input INPUT] [--output OUTPUT] [--amount AMOUNT] [-sim] [-k KEY] [--oracle_price ORACLE_PRICE]
                     [--gt GT] [--ge GE] [--lt LT] [--le LE]

options:
  -h, --help            show this help message and exit
  -i, --init            Initialize pairs & tokens data
  --input INPUT         Input token to swap
  --output OUTPUT       Output token from swap
  --amount AMOUNT       Amount to swap
  -sim, --simulate      Only simulate swap
  -k KEY, --key KEY     secretcli key to use to send txs
  --oracle_price ORACLE_PRICE
                        Symbol to check oracle price before executing swap
  --gt GT               Swap requirement for price greater
  --ge GE               Swap requirement for price greater or equal
  --lt LT               Swap requirement for price less
  --le LE               Swap requirement for price less or equal
```

Examples
```
shade_swap.py --input SILK --output SHD --amount .001 --oracle_price SILK --gt 1.0
```

Features in development:
- Multi-hop routing & optimization
- Per-chain data initialization
- Optimized re-initialization to avoid reloading existing good data to get new pairs
- Verification of matching configs between this & the secretcli install
- Better symbol matching to allow using `ATOM` instead of `sATOM` or `BTC` instead of `saWBTC` etc.
