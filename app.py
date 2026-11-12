"""
Bond Ladder Planner - Streamlit app
-----------------------------------
Plan a ladder of 1, 2, 3 and 4-year bonds (equal amounts). Every year the shortest bond
matures and the money goes into a new 4-year bond, so the ladder rolls forever.

Tab 1: you know how much money you have  -> the coupon / YTM you need.
Tab 2: you know the yields you can get   -> the money you need.

Educational tool only - NOT investment advice.
"""

import pandas as pd
import streamlit as st

import ladder as lad

st.set_page_config(page_title="Bond Ladder Planner", page_icon="🪜", layout="wide")


# ----------------------------------------------------------------------------
# Formatting helpers
# ----------------------------------------------------------------------------

def inr(x):
    """Rupees with Indian digit grouping, e.g. 2400000 -> ₹24,00,000."""
    if x is None or x != x:
        return "—"
    n = int(round(x))
    sign = "-" if n < 0 else ""
    s = str(abs(n))
    if len(s) > 3:
        head, tail = s[:-3], s[-3:]
        parts = []
        while len(head) > 2:
            parts.insert(0, head[-2:])
            head = head[:-2]
        parts.insert(0, head)
        s = ",".join(parts) + "," + tail
    return f"{sign}₹{s}"


def pct(x):
    return "—" if x is None or x != x else f"{x * 100:.2f}%"


# ----------------------------------------------------------------------------
# Sidebar: the goal
# ----------------------------------------------------------------------------

with st.sidebar:
    st.header("Your goal")
    monthly = st.number_input("Monthly interest you want in year 1 (₹)", min_value=1000.0,
                              value=20000.0, step=1000.0)
    basis = st.radio("This amount is", ["Before tax (gross interest)", "After tax (in hand)"])
    tax = st.number_input("Tax rate on interest (%)", min_value=0.0, max_value=45.0,
                          value=30.0, step=1.0) / 100
    growth = st.number_input("Increase in monthly interest every year (%)", min_value=0.0,
                             max_value=20.0, value=6.0, step=0.5) / 100
    L = int(st.number_input("Ladder length (years)", min_value=2, max_value=10, value=4, step=1))
    years = int(st.number_input("Years to project", min_value=3, max_value=30, value=10, step=1))
    gsec = st.number_input("Government bond (G-Sec) yield (%)", min_value=0.0, max_value=15.0,
                           value=7.08, step=0.05,
                           help="Used only to say what credit quality a yield implies. "
                                "7.08% was the 3-year G-Sec yield on 3 Nov 2026 - update it.") / 100

gross_monthly = monthly if basis.startswith("Before") else lad.gross_from_net(monthly, tax)
targets = lad.income_targets(gross_monthly, growth, years)

st.title("🪜 Bond Ladder Planner")
st.caption(f"{L} equal bonds maturing in 1 to {L} years. Each year the shortest one matures and the "
           f"money goes into a new {L}-year bond. Educational only, not investment advice.")

g1, g2, g3, g4 = st.columns(4)
g1.metric("Year 1 interest per month (gross)", inr(gross_monthly))
g2.metric(f"Year 1 per month after {tax * 100:.0f}% tax", inr(gross_monthly * (1 - tax)))
g3.metric(f"Year {years} interest per month (gross)", inr(targets[-1] / 12),
          f"+{growth * 100:.1f}% every year")
g4.metric(f"Total interest over {years} years (gross)", inr(sum(targets)))

st.info(
    "**Key point.** A ladder earns *money invested × yield*. If yields stay flat, your interest can "
    f"only grow {growth * 100:.0f}% a year if the money invested also grows about "
    f"{growth * 100:.0f}% a year, or if yields keep rising. Tab ① shows the coupon you would need "
    "without adding money. Tab ② shows how much fresh money you would need to add."
)

tab1, tab2 = st.tabs(["① I know my capital → what coupon / YTM do I need?",
                      "② I know the yields → how much capital do I need?"])

# ----------------------------------------------------------------------------
# Tab 1: capital known -> required coupon
# ----------------------------------------------------------------------------

with tab1:
    a, b, c, d = st.columns(4)
    capital = a.number_input("Money you can invest today (₹)", min_value=100000.0,
                             value=2500000.0, step=100000.0, key="t1_capital")
    topup_y = b.number_input("Fresh money you can add each year (₹)", min_value=0.0,
                             value=0.0, step=10000.0, key="t1_topup")
    slope = c.number_input(f"Yield gap: 1-year vs {L}-year bond (percentage points)", min_value=0.0,
                           max_value=4.0, value=1.0, step=0.25, key="t1_slope",
                           help="Shorter bonds usually pay less. 0 = same coupon on every bond.") / 100
    cap = d.number_input(f"Highest coupon you would accept on a new {L}-year bond (%)",
                         min_value=1.0, max_value=25.0, value=10.5, step=0.25, key="t1_cap") / 100

    avg, coupons, rows, _ = lad.plan_for_capital(L, years, targets, capital,
                                                 [topup_y] * (years - 1), slope)
    label, spread_bps, risk = lad.typical_rating(avg, gsec)

    st.subheader("Today's purchase")
    m1, m2, m3 = st.columns(3)
    m1.metric("Average coupon / YTM you need", pct(avg))
    m2.metric("Spread over G-Sec", f"{spread_bps:.0f} bps")
    m3.metric("Typical rating at that yield", f"{label} ({risk} risk)")

    if avg > 0.14:
        st.error("This yield is only available from very risky issuers. A ladder built on it can lose "
                 "far more to defaults than it earns. Invest more money or lower the monthly target.")
    elif risk == "high":
        st.warning("This return needs bonds with real default risk (BBB+ or lower). Spread each rung "
                   "over several issuers, or consider investing more money or lowering the target.")
    elif risk == "moderate":
        st.info("This return is typical of A-category bonds. They carry some credit risk, so use "
                "several issuers per rung rather than one.")
    else:
        st.success("This return is available from higher-rated bonds (AA- or better).")
    st.caption("Rating hint is a rough rule of thumb. Real spreads vary a lot by issuer and market mood.")

    per = capital / L
    buy = pd.DataFrame({
        "Bond": [f"{j}-year" for j in range(1, L + 1)] + ["Total"],
        "Amount": [inr(per)] * L + [inr(capital)],
        "Coupon / YTM needed": [pct(x) for x in coupons] + [pct(avg) + " (average)"],
        "Monthly interest": [inr(per * x / 12) for x in coupons] + [inr(sum(per * x / 12 for x in coupons))],
    })
    st.dataframe(buy, hide_index=True)
    st.caption("Only the average matters. Aim for lower coupons on the 1-year bond and higher on the "
               "longest, as long as the average comes out at or above the figure above.")

    st.subheader("Year by year: coupon needed on each new bond")
    first_bad, tbl = None, []
    for r in rows:
        y = r["year"]
        flag = ""
        if y > 1:
            bad = r["new_coupon"] > cap + 1e-12
            if bad and first_bad is None:
                first_bad = y
            flag = "❌ above your limit" if bad else "✅ within your limit"
        tbl.append({
            "Year": y,
            "Monthly interest (gross)": inr(r["income"] / 12),
            "After tax": inr(r["income"] / 12 * (1 - tax)),
            "Money put in": inr(r["fresh"]),
            "New bond size": inr(r["new_principal"]) if y > 1 else "—",
            "Coupon needed on new bond": pct(r["new_coupon"]) if y > 1 else "—",
            "Within your limit?": flag,
        })
    st.dataframe(pd.DataFrame(tbl), hide_index=True)

    if first_bad is None:
        st.success(f"Every new {L}-year bond needs at most {cap * 100:.2f}%, within your limit.")
    else:
        worst = max(r["new_coupon"] for r in rows[1:])
        if topup_y > 0:
            reason = (f"Even with {inr(topup_y)} of fresh money a year, interest cannot keep growing "
                      f"{growth * 100:.0f}% a year. Add more fresh money (see below and tab ②), "
                      "lower the growth, or lower the target.")
        else:
            reason = (f"Interest cannot keep growing {growth * 100:.0f}% a year from coupons alone. "
                      "Add fresh money (see below and tab ②), lower the growth, or lower the target.")
        st.warning(f"From year {first_bad} the new {L}-year bond would need more than your "
                   f"{cap * 100:.2f}% limit, reaching **{worst * 100:.1f}%** by year {years}. {reason}")

    chart = pd.DataFrame({
        "Coupon needed on each new bond (%)": [r["new_coupon"] * 100 for r in rows[1:]],
        "Your limit (%)": [cap * 100] * (years - 1),
    }, index=pd.Index([r["year"] for r in rows[1:]], name="Year"))
    st.line_chart(chart)

    st.subheader(f"What if new bonds can pay at most {cap * 100:.2f}%?")
    rows_cap, _ = lad.simulate(L, years, targets, capital / L, coupons, new_coupons=[cap] * (years - 1))
    cap_tbl = pd.DataFrame([{
        "Year": r["year"],
        "Fresh money needed": inr(r["fresh"]),
        "New bond size": inr(r["new_principal"]),
        "Total money invested": inr(r["capital"]),
    } for r in rows_cap[1:]])
    st.dataframe(cap_tbl, hide_index=True)
    total_fresh = sum(r["fresh"] for r in rows_cap[1:])
    st.caption(f"Total fresh money over {years - 1} years: **{inr(total_fresh)}** "
               f"(about {inr(total_fresh / (years - 1))} a year). A negative number means money you "
               "could take out.")

    raw1 = pd.DataFrame(rows).rename(columns={
        "year": "Year", "target": "Target annual interest", "income": "Annual interest",
        "capital": "Money invested", "fresh": "Money put in", "matured": "Matured principal",
        "new_principal": "New bond size", "new_coupon": "Coupon needed", "avg_yield": "Portfolio yield"})
    st.download_button("Download this plan (CSV)", raw1.to_csv(index=False).encode("utf-8"),
                       file_name="bond_ladder_required_coupon.csv", mime="text/csv", key="dl_t1")

# ----------------------------------------------------------------------------
# Tab 2: yields known -> capital needed
# ----------------------------------------------------------------------------

with tab2:
    st.markdown("Enter the yields you can realistically get (bought at face value, so coupon = YTM). "
                "These defaults are only illustrative. Replace them with real quotes from your bond platform.")
    cols = st.columns(L)
    init_y = []
    for j in range(1, L + 1):
        default = min(8.0 + 0.5 * (j - 1), 14.0)
        init_y.append(cols[j - 1].number_input(f"{j}-year bond (%)", min_value=1.0, max_value=25.0,
                                               value=default, step=0.1, key=f"t2_y{j}") / 100)
    e, f = st.columns(2)
    new_y = e.number_input(f"Coupon on future {L}-year bonds (%)", min_value=1.0, max_value=25.0,
                           value=9.5, step=0.1, key="t2_new") / 100
    drift = f.number_input("Change in that coupon every year (percentage points)", min_value=-2.0,
                           max_value=2.0, value=0.0, step=0.1, key="t2_drift") / 100
    new_list = [max(0.005, new_y + drift * i) for i in range(years - 1)]

    per2, rows2, _ = lad.plan_for_yields(L, years, targets, init_y, new_list)
    cap0 = rows2[0]["capital"]
    avg_y = sum(init_y) / L
    label2, spread2, risk2 = lad.typical_rating(avg_y, gsec)
    fresh_list = [r["fresh"] for r in rows2[1:]]
    cap_end = rows2[-1]["capital"]

    st.subheader("Money you need")
    n1, n2, n3, n4 = st.columns(4)
    n1.metric("Money needed today", inr(cap0))
    n2.metric("Average yield today", pct(avg_y))
    n3.metric("Fresh money needed per year (average)", inr(sum(fresh_list) / len(fresh_list)))
    n4.metric(f"Money invested in year {years}", inr(cap_end),
              f"{(cap_end / cap0 - 1) * 100:+.0f}% vs today", delta_color="inverse")
    st.caption(f"That average yield is about {spread2:.0f} bps over the G-Sec, typical of {label2}-rated "
               f"bonds ({risk2} credit risk). Rough rule of thumb only.")

    buy2 = pd.DataFrame({
        "Bond": [f"{j}-year" for j in range(1, L + 1)] + ["Total"],
        "Amount": [inr(per2)] * L + [inr(cap0)],
        "Coupon / YTM": [pct(x) for x in init_y] + [pct(avg_y) + " (average)"],
        "Monthly interest": [inr(per2 * x / 12) for x in init_y] + [inr(sum(per2 * x / 12 for x in init_y))],
    })
    st.dataframe(buy2, hide_index=True)

    st.subheader("Year by year: fresh money needed")
    tbl2 = [{
        "Year": r["year"],
        "Monthly interest (gross)": inr(r["income"] / 12),
        "After tax": inr(r["income"] / 12 * (1 - tax)),
        "Fresh money needed": inr(r["fresh"]) if r["year"] > 1 else inr(r["fresh"]) + " (start)",
        "New bond size": inr(r["new_principal"]) if r["year"] > 1 else "—",
        "Coupon on new bond": pct(r["new_coupon"]) if r["year"] > 1 else "—",
        "Total money invested": inr(r["capital"]),
    } for r in rows2]
    st.dataframe(pd.DataFrame(tbl2), hide_index=True)
    st.caption("Fresh money = new bond size minus the principal that just matured. "
               "A negative number means money you could take out.")

    st.bar_chart(pd.DataFrame({"Fresh money needed (₹)": fresh_list},
                              index=pd.Index([r["year"] for r in rows2[1:]], name="Year")))

    no_fresh = lad.income_without_fresh_money(L, years, per2, init_y, new_list)
    st.subheader("Reality check: what if you add no fresh money?")
    cmp_df = pd.DataFrame({
        "Target (₹ / month)": [t / 12 for t in targets],
        "Without fresh money (₹ / month)": [x / 12 for x in no_fresh],
    }, index=pd.Index(range(1, years + 1), name="Year"))
    st.line_chart(cmp_df)
    shortfall = targets[-1] / 12 - no_fresh[-1] / 12
    st.caption(f"With no fresh money, year {years} interest would be {inr(no_fresh[-1] / 12)} a month, "
               f"{inr(shortfall)} short of the {inr(targets[-1] / 12)} target.")

    raw2 = pd.DataFrame(rows2).rename(columns={
        "year": "Year", "target": "Target annual interest", "income": "Annual interest",
        "capital": "Money invested", "fresh": "Fresh money", "matured": "Matured principal",
        "new_principal": "New bond size", "new_coupon": "Coupon on new bond", "avg_yield": "Portfolio yield"})
    st.download_button("Download this plan (CSV)", raw2.to_csv(index=False).encode("utf-8"),
                       file_name="bond_ladder_capital_needed.csv", mime="text/csv", key="dl_t2")

# ----------------------------------------------------------------------------
# Notes
# ----------------------------------------------------------------------------

with st.expander("Assumptions and limits"):
    st.markdown("""
- Every bond is bought at **face value** and held to maturity, so coupon = YTM. If you pay a premium, your
  income per rupee is lower than the coupon.
- Bonds pay interest **monthly**. Bonds paying yearly or quarterly will make your monthly income lumpy.
- The new bond is bought on the day the old one matures, once a year. Real maturities rarely line up exactly.
- Coupons are **not reinvested**: you spend the interest. No defaults, no rating changes, no costs.
- Tax is a flat rate on interest. TDS rules, slabs and surcharge are not modelled.
- Rupee amounts are shown in nominal terms. A 6% yearly rise roughly keeps pace with inflation.
- The rating hint uses a rough table of typical spreads over G-Secs. Real spreads vary a lot.
- **Credit risk is the real risk.** High coupons come from weaker issuers. Spread each rung over several
  issuers and check ratings before buying. This is not investment advice.
""")
