# Bond Ladder Planner (Streamlit)

Plan a ladder of **1, 2, 3 and 4-year bonds** (equal amounts). Every year the shortest bond matures and the
money goes into a new 4-year bond, so the ladder keeps rolling. The app is built around one goal:

> **Get ₹20,000 of interest every month in year 1, and have it grow 6% every year.**

All of these are editable in the sidebar: monthly amount, before/after tax, tax rate, yearly growth, ladder length
(2-10 years), projection length and the G-Sec yield.

## Two ways to use it

**① I know my capital → what coupon / YTM do I need?**
Enter the money you can invest. The app tells you the average coupon / YTM you must earn, a rough idea of the
credit quality that implies, how to split it across the rungs, and the coupon every *new* 4-year bond must pay in
later years to keep interest growing. It also shows how much fresh money you would need each year if new bonds
can pay at most a coupon you choose.

**② I know the yields → how much capital do I need?**
Enter the yields you can realistically get. The app tells you the money needed today, the fresh money needed each
year, and what your interest would be if you added no fresh money.

## The key finding

A ladder earns *money invested × yield*. If yields stay flat, interest can only grow 6% a year if the money
invested also grows about 6% a year (or yields keep rising). Without fresh money, each new 4-year bond would need
a coupon that rises every year (roughly 9.6% → 11.4% → 11.9% → ... → 18% by year 10 in the default example),
which no sensible issuer pays.

## Run locally

```bash
pip install -r requirements.txt
streamlit run app.py
python test_ladder.py        # optional: run the maths tests
```

## Deploy

Push to GitHub, then deploy free on [Streamlit Community Cloud](https://share.streamlit.io) → select the repo → `app.py`.

## Files

| File | What it is |
|---|---|
| `app.py` | The Streamlit screens |
| `ladder.py` | The ladder maths (no Streamlit), easy to test |
| `test_ladder.py` | 14 tests, including a check that the interest target is hit exactly every year |

## Assumptions

- Bonds are bought at face value and held to maturity, so coupon = YTM (a premium lowers your income per rupee).
- Interest is paid monthly. Bonds paying yearly or quarterly make monthly income lumpy.
- A new bond is bought on the day the old one matures, once a year. Real maturities rarely line up exactly.
- Interest is spent, not reinvested. No defaults, rating changes or costs. Tax is a flat rate.
- The rating hint is a rough table of typical spreads over G-Secs. Real spreads vary a lot by issuer.

Educational tool only. Not investment advice. Higher coupons come from weaker issuers, so spread each rung over
several issuers and check ratings before buying.
