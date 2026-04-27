# Investment Holdings (Example)

This is an **example** holdings file. Copy it to `HOLDINGS.md` and replace every line with your real positions.

`HOLDINGS.md` is git-ignored so your real positions never enter version control.

## Lot format

```
<TICKER>: <quantity> shares @ <cost basis> on <YYYY-MM-DD>
```

- One position lot per line.
- `on YYYY-MM-DD` is the **acquisition date** for that lot. Required for new lots; optional only when truly unknown.
- Crypto and FX use `<SYMBOL> <quantity> @ <cost> on <YYYY-MM-DD>` (no "shares").
- Use `?` when the cost basis or the date is unknown — the agent will mark it as a data gap and will not invent a number.
- Group lots into the four buckets below; lots within a bucket can be in any order.
- Tickers below (`ALPH`, `BETA`, `GAMA`, ...) are **fictional** and used only for shape.

## Long Term (Not Sell)

- BETA: 215 shares @ $139.52 on 2096-08-04
- GAMA: 17 shares @ $609.65 on 2097-11-20
- GAMA: 10 shares @ $487.81 on 2098-02-14
- GAMA: 23 shares @ $475.39 on 2098-05-30
- ALPH 1 @ ? on 2095-03-12
- COIN2 8.78 @ ? on 2096-09-01

## Mid Term (1y+)

- DELT: 6 shares @ $390.97 on 2098-06-15
- DELT: 10 shares @ $433.62 on 2098-09-22
- DELT: 15 shares @ $222.16 on 2097-02-08
- ZETA: 53 shares @ $95.22 on 2096-02-09
- ZETA: 35 shares @ $105.30 on 2096-12-01
- OMGA: 80 shares @ $12.79 on 2098-04-04
- OMGA: 80 shares @ $19.53 on 2098-07-18
- IOTA: 15 shares @ $70.66 on 2097-09-25
- IOTA: 35 shares @ $85.69 on 2098-03-11
- 0001.XX: 150 shares @ 2300 on 2096-05-20

## Short Term (12 Months)

- THTA: 3 shares @ $651.25 on 2098-08-22
- THTA: 10 shares @ $701.35 on 2098-10-05
- KAPA: 60 shares @ $43.88 on 2098-10-30
- KAPA: 50 shares @ $48.07 on 2098-11-15
- LMBD: 4 shares @ $700.39 on 2098-09-12
- LMBD: 10 shares @ $659.37 on 2098-11-02
- SGMA: 10 shares @ $223.72 on 2098-08-04
- SGMA: 25 shares @ $242.02 on 2098-09-19
- SGMA: 15 shares @ $200.06 on 2098-12-08

## Cash Holdings

- USD: 50000
- CCY1: 1000000
- USDX: 5000
