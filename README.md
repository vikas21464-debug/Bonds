# Bond Ladder Planner (Streamlit)

A ladder of **1, 2, 3 and 4-year bonds** in equal amounts. Every year the shortest bond matures and you buy a
new 4-year bond. The goal: **₹20,000 of interest a month in year 1, growing 6% every year**, without ever
accepting a coupon above **10.50%**.

Because the coupon is capped, interest can only grow 6% a year if each new 4-year bond is **bigger** than the
one that matured. The app works out how much bigger, using the **real coupon and maturity date** of the bond you
are about to buy.

## How to use it

**Once, at the start (tab ①)**
1. Type the real coupon and maturity date of the four bonds you plan to buy (about 1, 2, 3 and 4 years out).
2. The app confirms how much to put in each (equal amounts) to earn ₹20,000 a month.
   A coupon above your limit is **not confirmed**.
3. Press **Use these bonds as my current ladder**, then go to tab ② and press **Save my ladder (CSV)**.

**Every year, when a bond matures (tab ②)**
1. Open the app, and under *Load a saved ladder* upload your CSV. It restores your bonds **and** your start date,
   goal and coupon limit, so the app knows which ladder year it is.
2. Type the **purchase date**, the **coupon available** and the **maturity date** of the bond in front of you
   (and the price if it is not 100% of face value).
3. The app confirms the **amount to invest**, how much of it comes from the matured bond, and how much is
   **fresh money**. Coupon above the limit, wrong maturity or a past date are flagged.
4. After you buy, press **I bought it: add it to my ladder**, then **Save my ladder (CSV)** again.

**Plan ahead (tab ③)** shows roughly how much fresh money you need each year at your best-case and a weaker coupon.

The page forgets everything when you close it, so **always save the CSV** after a change.

## Run locally

```bash
pip install -r requirements.txt
streamlit run app.py
python test_ladder.py        # optional: 23 maths tests
```

Deploy free on [Streamlit Community Cloud](https://share.streamlit.io): push these files to GitHub, then
select the repo and `app.py`. Keep all files in the same folder.

## Files

| File | What it is |
|---|---|
| `app.py` | The Streamlit screens |
| `ladder.py` | The ladder maths (no Streamlit), easy to test |
| `test_ladder.py` | 23 tests, including a check that real-date sizing matches the yearly engine |

## Assumptions

- Interest is paid **monthly** on the **face value** you hold. Yearly or quarterly payers make monthly income lumpy.
- Set *Face value of one bond* in the sidebar to match your bonds. Amounts are rounded **up** to whole bonds, so
  interest lands at or slightly above target. The default is ₹10,000.
- Money to pay = face value × price. Accrued interest, brokerage and purchase taxes are **not** included.
- A bond counts as matured on its maturity date: interest stops and face value comes back.
- Tax is a flat rate. No defaults or rating changes are modelled.

Educational tool only. Not investment advice. Higher coupons come from weaker issuers, so spread each step over
several issuers and check ratings before buying.
