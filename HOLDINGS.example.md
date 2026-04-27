# Investment Holdings (Example)

This is an **example** holdings file. Copy it to `HOLDINGS.md` and replace every line with your real positions.

`HOLDINGS.md` is git-ignored so your real positions never enter version control.

## Lot format

```
<TICKER>: <quantity> shares @ <cost basis> on <YYYY-MM-DD> [<MARKET>]
```

- One position lot per line.
- `on YYYY-MM-DD` is the **acquisition date** for that lot. Required for new lots; optional only when truly unknown.
- Crypto and FX use `<SYMBOL> <quantity> @ <cost> on <YYYY-MM-DD> [<MARKET>]` (no "shares").
- Cash uses `<CURRENCY>: <amount> [cash]` (no `shares`, no `@ cost`, no date).
- `[<MARKET>]` is the **market-type tag** (required for new lots; back-compat heuristic only when missing). It tells the price agent which primary quote route and fallback hierarchy to use.
- Use `?` when the cost basis or the date is unknown — the agent will render the affected metric as `n/a` and list it under Sources & data gaps. Never invent a number.
- Group lots into the four buckets below; lots within a bucket can be in any order.
- Tickers below (`ALPH`, `BETA`, `GAMA`, ...) are **fictional** and used only for shape.

### Market-type tag values

| Tag | Meaning | Primary quote routing |
|---|---|---|
| `[US]`     | NYSE / NASDAQ / AMEX listed equity or ETF | bare ticker (`NVDA`); `BRK.B` → `BRK-B` |
| `[TW]`     | Taiwan listed equity (TWSE) | `<code>.TW` (`2330.TW`) |
| `[TWO]`    | Taiwan OTC equity (TPEx) | `<code>.TWO` |
| `[JP]`     | Tokyo Stock Exchange | `<code>.T` |
| `[HK]`     | Hong Kong Stock Exchange | `<code>.HK` |
| `[LSE]`    | London Stock Exchange (UCITS ETFs etc.) | `<code>.L` |
| `[crypto]` | Crypto asset | Binance public spot `<SYM>USDT`; CoinGecko by coin id |
| `[FX]`     | Currency pair held as position | `<PAIR>=X` |
| `[cash]`   | Cash / cash-equivalent holding (no price fetch) | — |

If you omit the tag, the price agent falls back to a heuristic (suffix → market, known crypto symbol list, fiat code list). The heuristic is best-effort; **declare the tag explicitly for any non-US listing** so the price retrieval is deterministic.

## Long Term (Not Sell)

- BETA: 215 shares @ $139.52 on 2096-08-04 [US]
- GAMA: 17 shares @ $609.65 on 2097-11-20 [US]
- GAMA: 10 shares @ $487.81 on 2098-02-14 [US]
- GAMA: 23 shares @ $475.39 on ? [US]
- ALPH 1 @ ? on 2095-03-12 [crypto]
- COIN2 8.78 @ ? on ? [crypto]

## Mid Term (1y+)

- DELT: 6 shares @ $390.97 on 2098-06-15 [US]
- DELT: 10 shares @ $433.62 on 2098-09-22 [US]
- DELT: 15 shares @ $222.16 on 2097-02-08 [US]
- ZETA: 53 shares @ $95.22 on 2096-02-09 [US]
- ZETA: 35 shares @ $105.30 on 2096-12-01 [US]
- OMGA: 80 shares @ $12.79 on 2098-04-04 [US]
- OMGA: 80 shares @ $19.53 on 2098-07-18 [US]
- IOTA: 15 shares @ $70.66 on 2097-09-25 [US]
- IOTA: 35 shares @ $85.69 on 2098-03-11 [US]
- 2330.TW: 150 shares @ NT$2300 on 2096-05-20 [TW]

## Short Term (12 Months)

- THTA: 3 shares @ $651.25 on 2098-08-22 [US]
- THTA: 10 shares @ $701.35 on 2098-10-05 [US]
- KAPA: 60 shares @ $43.88 on 2098-10-30 [US]
- KAPA: 50 shares @ $48.07 on 2098-11-15 [US]
- LMBD: 4 shares @ $700.39 on 2098-09-12 [US]
- LMBD: 10 shares @ $659.37 on 2098-11-02 [US]
- SGMA: 10 shares @ $223.72 on 2098-08-04 [US]
- SGMA: 25 shares @ $242.02 on 2098-09-19 [US]
- SGMA: 15 shares @ $200.06 on 2098-12-08 [US]

## Cash Holdings

- USD: 50000 [cash]
- CCY1: 1000000 [cash]
- USDX: 5000 [cash]
