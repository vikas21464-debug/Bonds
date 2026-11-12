"""
Bond Ladder Planner - Streamlit app
-----------------------------------
A ladder of 1, 2, 3 and 4-year bonds. Every year the shortest bond matures and you buy a new
4-year bond. Your monthly interest should rise 6% a year, and you never accept a coupon above
your limit (10.50% by default), so each new bond is bigger than the one it replaces.

Tab 1: first ladder  - type the real coupon and maturity of the 4 bonds -> how much in each.
Tab 2: buy next bond - type the real coupon and maturity of the bond in front of you
                       -> the amount to invest (and how much is fresh money).
Tab 3: plan ahead    - how much money to arrange each year, at your coupon limit.

Educational tool only - NOT investment advice.
"""

from datetime import date

import pandas as pd
import streamlit as st

import ladder as lad

st.set_page_config(page_title="Bond Ladder Planner", page_icon="🪜", layout="wide")

LADDER_YEARS = 4                       # 1, 2, 3 and 4-year bonds. Edit for a different ladder.
DMIN, DMAX = date(2000, 1, 1), date(2100, 12, 31)
L = LADDER_YEARS


# ----------------------------------------------------------------------------
# Helpers
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


COLS = ["Bond / ISIN", "Face value held (₹)", "Coupon (%)", "Maturity date"]


def empty_df():
    return pd.DataFrame({
        COLS[0]: pd.Series(dtype="object"),
        COLS[1]: pd.Series(dtype="float64"),
        COLS[2]: pd.Series(dtype="float64"),
        COLS[3]: pd.Series(dtype="datetime64[ns]"),
    })


def to_df(holdings):
    if not holdings:
        return empty_df()
    return pd.DataFrame({
        COLS[0]: [h.name for h in holdings],
        COLS[1]: [float(h.face) for h in holdings],
        COLS[2]: [h.coupon * 100 for h in holdings],
        COLS[3]: pd.to_datetime([h.maturity for h in holdings]),
    })


def from_df(df):
    """Table -> list of Holding. Rows with a missing value are skipped (and counted)."""
    out, skipped = [], 0
    for _, r in df.iterrows():
        if r.isna().all():
            continue
        face, cpn, mat = r[COLS[1]], r[COLS[2]], r[COLS[3]]
        if pd.isna(face) or pd.isna(cpn) or pd.isna(mat) or face <= 0 or cpn <= 0:
            skipped += 1
            continue
        name = r[COLS[0]]
        out.append(lad.Holding("" if pd.isna(name) else str(name), float(face),
                               float(cpn) / 100, pd.Timestamp(mat).date()))
    return out, skipped


# Your goal and rules are saved inside the CSV too, so next year the app knows which ladder year it is.
SET_COLS = ["Ladder start date", "Monthly interest goal (₹)", "Goal is after tax", "Tax rate (%)",
            "Yearly increase (%)", "Highest coupon (%)", "Face value of one bond (₹)"]


def _clamp(x, lo, hi, default):
    try:
        v = float(x)
    except (TypeError, ValueError):
        return default
    return default if v != v else min(max(v, lo), hi)


def read_settings(raw):
    """Settings stored in the first row of a saved CSV, or {} if the file has none."""
    if raw.empty or not all(c in raw.columns for c in SET_COLS):
        return {}
    r = raw.iloc[0]
    try:
        start_saved = pd.to_datetime(r[SET_COLS[0]])
        if pd.isna(start_saved):
            return {}
        start_saved = start_saved.date()
    except Exception:
        return {}
    if not DMIN <= start_saved <= DMAX:
        return {}
    return {
        "start": start_saved,
        "monthly": _clamp(r[SET_COLS[1]], 1000.0, 1e9, 20000.0),
        "after_tax": str(r[SET_COLS[2]]).strip().lower() in ("true", "1", "yes"),
        "tax": _clamp(r[SET_COLS[3]], 0.0, 45.0, 30.0),
        "growth": _clamp(r[SET_COLS[4]], 0.0, 20.0, 6.0),
        "cap": _clamp(r[SET_COLS[5]], 1.0, 25.0, 10.5),
        "lot": _clamp(r[SET_COLS[6]], 100.0, 1e9, 10000.0),
    }


ss = st.session_state
ss.setdefault("holdings", empty_df())
ss.setdefault("hver", 0)      # bumped to refresh the table after the app changes it
ss.setdefault("uver", 0)      # bumped to clear the file uploader
ss.setdefault("settings", {})  # goal and rules loaded from a saved file
ss.setdefault("sver", 0)      # bumped so the sidebar picks up loaded settings
S, V = ss["settings"], ss["sver"]


# ----------------------------------------------------------------------------
# Sidebar: your rules
# ----------------------------------------------------------------------------

with st.sidebar:
    st.header("Your goal and rules")
    monthly = st.number_input("Monthly interest you want in year 1 (₹)", min_value=1000.0,
                              value=float(S.get("monthly", 20000.0)), step=1000.0, key=f"set_monthly_{V}")
    basis = st.radio("This amount is", ["Before tax (gross interest)", "After tax (in hand)"],
                     index=int(S.get("after_tax", False)), key=f"set_basis_{V}")
    tax_pct = st.number_input("Tax rate on interest (%)", min_value=0.0, max_value=45.0,
                              value=float(S.get("tax", 30.0)), step=1.0, key=f"set_tax_{V}")
    growth_pct = st.number_input("Increase in interest every year (%)", min_value=0.0, max_value=20.0,
                                 value=float(S.get("growth", 6.0)), step=0.5, key=f"set_growth_{V}")
    cap_pct = st.number_input("Highest coupon you will accept (%)", min_value=1.0, max_value=25.0,
                              value=float(S.get("cap", 10.5)), step=0.25, key=f"set_cap_{V}")
    start = st.date_input("Ladder start date (day you bought / will buy the first 4 bonds)",
                          value=S.get("start", date.today()), min_value=DMIN, max_value=DMAX,
                          key=f"set_start_{V}",
                          help="Year 1 runs for 12 months from this date. Your interest target "
                               "goes up by the yearly increase on each anniversary. "
                               "Do not change it after you have started. Loading your saved file restores it.")
    lot = st.number_input("Face value of one bond (₹)", min_value=100.0,
                          value=float(S.get("lot", 10000.0)), step=100.0, key=f"set_lot_{V}",
                          help="Amounts are rounded up to whole bonds. Check the face value on your "
                               "platform (many NCDs are ₹1,000; some are ₹10,000 or ₹1,00,000).")
tax, growth, cap = tax_pct / 100, growth_pct / 100, cap_pct / 100

gross_monthly = monthly if basis.startswith("Before") else lad.gross_from_net(monthly, tax)
year_today = lad.ladder_year(start, date.today())
target_today = gross_monthly * (1 + growth) ** (year_today - 1)

st.title("🪜 Bond Ladder Planner")
st.caption(f"Bonds maturing in 1 to {L} years. Each year the shortest one matures and you buy a new "
           f"{L}-year bond. Educational only, not investment advice.")

if ss.get("notice"):
    st.success(ss.pop("notice"))

k1, k2, k3, k4 = st.columns(4)
k1.metric("Year 1 interest per month (gross)", inr(gross_monthly))
k2.metric(f"Year 1 per month after {tax * 100:.0f}% tax", inr(gross_monthly * (1 - tax)))
k3.metric(f"Interest target today (ladder year {year_today})", inr(target_today),
          f"+{growth * 100:.1f}% every year")
k4.metric("Highest coupon you accept", pct(cap))

st.info(
    f"**How it works.** Because you will not accept a coupon above {cap * 100:.2f}%, your interest can only "
    f"grow {growth * 100:.0f}% a year if each new {L}-year bond is **bigger** than the one that matured. "
    "Enter the real coupon and maturity date of the bond you are about to buy, and the app tells you "
    "how much to invest."
)

tab1, tab2, tab3 = st.tabs(["① Build the first ladder", "② Buy the next bond (every year)",
                            "③ Plan ahead"])

# ----------------------------------------------------------------------------
# Tab 1: first ladder
# ----------------------------------------------------------------------------

with tab1:
    st.markdown(f"Enter the **real coupon and maturity date** of the {L} bonds you plan to buy on "
                f"**{start:%d %b %Y}**. You get equal amounts in each, sized to give "
                f"{inr(gross_monthly)} a month.")
    names, cpns, mats = [], [], []
    for j in range(1, L + 1):
        c1, c2, c3 = st.columns([2, 1, 1])
        names.append(c1.text_input(f"{j}-year bond: name / ISIN (optional)", key=f"t1_n{j}"))
        cpns.append(c2.number_input(f"{j}-year bond: coupon (%)", min_value=1.0, max_value=25.0,
                                    value=float(min(8.0 + 0.5 * (j - 1), cap * 100)), step=0.05,
                                    key=f"t1_c{j}") / 100)
        mats.append(c3.date_input(f"{j}-year bond: maturity date", value=lad.add_years(start, j),
                                  min_value=DMIN, max_value=DMAX, key=f"t1_m{j}_{start.isoformat()}"))
    st.caption("The coupons shown are only examples. Replace them with what is actually on offer.")

    over = [f"{j}-year ({cpns[j - 1] * 100:.2f}%)" for j in range(1, L + 1) if cpns[j - 1] > cap + 1e-9]
    early = [str(j) + "-year" for j in range(1, L + 1) if mats[j - 1] <= start]
    odd = [f"{j}-year bond matures in {(mats[j - 1] - start).days / 365.25:.1f} years"
           for j in range(1, L + 1) if mats[j - 1] > start and abs((mats[j - 1] - start).days / 365.25 - j) > 0.5]

    if early:
        st.error(f"Maturity date must be after {start:%d %b %Y} for: {', '.join(early)}.")
    else:
        res = lad.size_initial_ladder(gross_monthly, cpns, lot)
        if over:
            st.error(f"❌ Not confirmed. Coupon above your {cap * 100:.2f}% limit: {', '.join(over)}. "
                     "Pick a different bond for that step. The amounts below are for reference only.")
        else:
            st.success(f"✅ Confirmed. Buy **{res.bonds_each} bonds ({inr(res.face_each)}) in each** of the "
                       f"{L} steps, {inr(res.total_face)} in all, for {inr(res.monthly_total)} of interest "
                       "a month.")
        if odd:
            st.warning("Check the maturities: " + "; ".join(odd) + f". The ladder expects about 1 to {L} years.")

        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Put in each bond", inr(res.face_each))
        m2.metric("Total to invest", inr(res.total_face))
        m3.metric("Monthly interest (gross)", inr(res.monthly_total))
        m4.metric("After tax", inr(res.monthly_total * (1 - tax)))

        table = pd.DataFrame({
            "Step": [f"{j}-year" for j in range(1, L + 1)] + ["Total"],
            "Bond": [n or "—" for n in names] + [""],
            "Coupon": [pct(c) for c in cpns] + [""],
            "Maturity": [m.strftime("%d %b %Y") for m in mats] + [""],
            "Bonds to buy": [str(res.bonds_each)] * L + [str(res.bonds_each * L)],
            "Face value": [inr(res.face_each)] * L + [inr(res.total_face)],
            "Monthly interest": [inr(x) for x in res.monthly_each] + [inr(res.monthly_total)],
        })
        st.dataframe(table, hide_index=True)
        st.caption(f"Exact amount before rounding: {inr(res.face_each_exact)} each. Amounts are face values, "
                   "assuming you buy at par. If you pay above or below face value, use tab ② to see the money to pay.")

        if st.button("Use these bonds as my current ladder", disabled=bool(over), key="t1_use"):
            ss["holdings"] = to_df([lad.Holding(names[j] or f"{j + 1}-year bond", res.face_each, cpns[j],
                                                mats[j]) for j in range(L)])
            ss["hver"] += 1
            st.success("Saved. Now open tab ② to see them.")

# ----------------------------------------------------------------------------
# Tab 2: buy the next bond
# ----------------------------------------------------------------------------

with tab2:
    st.subheader("1. Your current bonds")
    with st.expander("Load a saved ladder"):
        up = st.file_uploader("Saved ladder (CSV)", type="csv", key=f"upload_{ss['uver']}")
        loaded, file_settings = None, {}
        if up is not None:
            try:
                raw = pd.read_csv(up)
                missing = [c for c in COLS if c not in raw.columns]
                if missing:
                    st.error("This file is missing columns: " + ", ".join(missing))
                else:
                    loaded = raw[COLS].copy()
                    loaded[COLS[1]] = pd.to_numeric(loaded[COLS[1]], errors="coerce")
                    loaded[COLS[2]] = pd.to_numeric(loaded[COLS[2]], errors="coerce")
                    loaded[COLS[3]] = pd.to_datetime(loaded[COLS[3]], errors="coerce")
                    file_settings = read_settings(raw)
            except Exception as ex:   # unreadable file
                st.error(f"Could not read the file: {ex}")
        if loaded is not None:
            ss["holdings"] = loaded
            ss["hver"] += 1
            ss["uver"] += 1
            if file_settings:
                ss["settings"] = file_settings
                ss["sver"] += 1
                ss["notice"] = (f"Loaded {len(loaded)} bonds and your settings: ladder started "
                                f"{file_settings['start']:%d %b %Y}, goal {inr(file_settings['monthly'])} a month, "
                                f"+{file_settings['growth']:.1f}% a year, coupon limit {file_settings['cap']:.2f}%.")
            else:
                ss["notice"] = (f"Loaded {len(loaded)} bonds. This file has no saved settings (it is from an "
                                "older version), so check the ladder start date in the sidebar.")
            st.rerun()

    edited = st.data_editor(
        ss["holdings"], key=f"holdings_editor_{ss['hver']}", num_rows="dynamic", hide_index=True,
        column_config={
            COLS[0]: st.column_config.TextColumn(COLS[0]),
            COLS[1]: st.column_config.NumberColumn(COLS[1], min_value=0, step=10000, format="%d"),
            COLS[2]: st.column_config.NumberColumn(COLS[2], min_value=0.0, max_value=30.0, step=0.05,
                                                   format="%.2f"),
            COLS[3]: st.column_config.DateColumn(COLS[3], min_value=DMIN, max_value=DMAX,
                                                 format="DD MMM YYYY"),
        })
    holdings, skipped = from_df(edited)
    if skipped:
        st.warning(f"{skipped} incomplete row(s) are ignored until every column is filled in.")
    to_save = edited.copy()
    for col, val in zip(SET_COLS, [start.isoformat(), monthly, basis.startswith("After"), tax_pct,
                                   growth_pct, cap_pct, lot]):
        to_save[col] = val
    st.download_button("Save my ladder (CSV)", to_save.to_csv(index=False).encode("utf-8"),
                       file_name="my_bond_ladder.csv", mime="text/csv", key="dl_holdings")
    st.caption("Face value held = the face value of the bonds you own (interest = face value × coupon). "
               "This page forgets everything when you close it or refresh, so save the CSV after every "
               "change and load it next time. The file also remembers your ladder start date, goal and "
               "coupon limit, so next year the app knows which ladder year it is.")

    st.subheader("2. The bond you are about to buy")
    a, b, c, d = st.columns(4)
    on = a.date_input("Purchase date", value=date.today(), min_value=DMIN, max_value=DMAX, key="t2_on")
    new_name = b.text_input("Bond name / ISIN (optional)", key="t2_name")
    new_cpn = c.number_input("Coupon available (%)", min_value=0.5, max_value=25.0, value=10.0,
                             step=0.05, key="t2_cpn") / 100
    new_mat = d.date_input("Maturity date of this bond", value=lad.add_years(date.today(), L),
                           min_value=DMIN, max_value=DMAX, key="t2_mat")
    e, f = st.columns(2)
    price = e.number_input("Price you will pay (% of face value)", min_value=50.0, max_value=150.0,
                           value=100.0, step=0.25, key="t2_price",
                           help="100 = at face value. Bonds bought in the market can cost a little more or "
                                "less. Interest is paid on face value, so a lower price means less money.")
    year_override = f.number_input("Ladder year to size for (0 = automatic)", min_value=0, max_value=60,
                                   value=0, step=1, key="t2_year",
                                   help="Year 1 is the first 12 months after the start date. Your first "
                                        "new 4-year bond is bought in year 2. Leave 0 to work it out "
                                        "from the dates.")

    year_n = int(year_override) or lad.ladder_year(start, on)
    target = gross_monthly * (1 + growth) ** (year_n - 1)
    st.caption(f"Purchase on {on:%d %b %Y} is in **ladder year {year_n}**, so your interest target is "
               f"**{inr(target)} a month** ({inr(target * (1 - tax))} after tax).")

    st.subheader("3. How much to invest")
    if not holdings:
        st.info("Add your current bonds above first (or build the first ladder in tab ①).")
    elif new_mat <= on:
        st.error("The maturity date must be after the purchase date.")
    else:
        sz = lad.size_new_bond(target, holdings, on, new_cpn, price, lot)
        tenor = (new_mat - on).days / 365.25
        if abs(tenor - L) > 0.5:
            st.warning(f"This bond matures in {tenor:.1f} years. Your ladder expects a {L}-year bond, "
                       "so check the maturity date.")
        matured = [h for h in holdings if h.maturity <= on]
        if matured:
            st.caption("Matured by the purchase date (principal back, removed when you add the new bond): "
                       + "; ".join(f"{h.name or 'bond'} {inr(h.face)}" for h in matured))

        over_cap = new_cpn > cap + 1e-9
        if over_cap:
            st.error(f"❌ Not confirmed. The coupon {pct(new_cpn)} is above your {cap * 100:.2f}% limit. "
                     "Look for another bond. The figures below are for reference only.")
        elif not sz.needed:
            st.success(f"✅ No new bond needed. Bonds still running already pay {inr(sz.running_monthly)} "
                       f"a month, at or above the {inr(target)} target."
                       + (f" The matured {inr(sz.matured_principal)} is free to use."
                          if sz.matured_principal > 0 else ""))
        else:
            st.success(f"✅ Confirmed. Invest **{inr(sz.money_to_pay)}** in this bond ({inr(sz.face)} face "
                       f"value" + (f", {sz.bonds} bonds" if sz.bonds else "") + f"). "
                       f"Of that, {inr(sz.matured_principal)} comes from matured bonds and "
                       f"**{inr(sz.fresh_money)}** is fresh money."
                       if sz.fresh_money >= 0 else
                       f"✅ Confirmed. Invest **{inr(sz.money_to_pay)}** in this bond ({inr(sz.face)} face "
                       f"value). That is less than the {inr(sz.matured_principal)} that came back, so "
                       f"{inr(-sz.fresh_money)} is free to take out.")

        if sz.needed:
            n1, n2, n3, n4 = st.columns(4)
            n1.metric("Invest in this bond", inr(sz.money_to_pay))
            n2.metric("Face value to buy", inr(sz.face))
            n3.metric("From matured bonds", inr(sz.matured_principal))
            n4.metric("Fresh money to add" if sz.fresh_money >= 0 else "Money you can take out",
                      inr(abs(sz.fresh_money)))
            steps = pd.DataFrame([
                (f"Interest target (ladder year {year_n})", f"{inr(sz.target_monthly)} a month"),
                ("Interest from bonds still running", f"{inr(sz.running_monthly)} a month"),
                ("Interest still needed from the new bond", f"{inr(sz.shortfall_monthly)} a month"),
                (f"Face value needed at {pct(new_cpn)}", inr(sz.face_exact)),
                (f"Rounded up to whole bonds of {inr(lot)}", f"{sz.bonds} bonds = {inr(sz.face)}"),
                (f"Money to pay at {price:.2f}% of face value", inr(sz.money_to_pay)),
                ("Principal back from matured bonds", inr(sz.matured_principal)),
                ("Fresh money to add (negative = money freed)", inr(sz.fresh_money)),
                ("Monthly interest after buying", f"{inr(sz.monthly_after)} a month"),
            ], columns=["Step", "Amount"])
            st.dataframe(steps, hide_index=True)
            if price != 100.0:
                st.caption(f"At {price:.2f}% of face value, the interest on your money is "
                           f"about {new_cpn / (price / 100) * 100:.2f}% a year.")

            if not over_cap and st.button("✅ I bought it: add it to my ladder", key="t2_add"):
                kept = [h for h in holdings if h.maturity > on]
                kept.append(lad.Holding(new_name or f"{L}-year bond", sz.face, new_cpn, new_mat))
                ss["holdings"] = to_df(kept)
                ss["hver"] += 1
                st.rerun()
            st.caption("The button removes bonds that have matured and adds this one. Edit the table above "
                       "if you bought a different amount, then save the CSV.")

        # Ladder after this purchase
        after = [h for h in holdings if h.maturity > on]
        if sz.needed and not over_cap:
            after = after + [lad.Holding(new_name or "New bond", sz.face, new_cpn, new_mat)]
        if after:
            st.subheader("4. Your ladder after this purchase")
            after = sorted(after, key=lambda h: h.maturity)
            ladder_tbl = pd.DataFrame({
                "Bond": [h.name or "—" for h in after] + ["Total"],
                "Face value": [inr(h.face) for h in after] + [inr(sum(h.face for h in after))],
                "Coupon": [pct(h.coupon) for h in after] + [""],
                "Matures": [h.maturity.strftime("%d %b %Y") for h in after] + [""],
                "Time left": [f"{(h.maturity - on).days / 365.25:.1f} yrs" for h in after] + [""],
                "Monthly interest": [inr(h.monthly_interest) for h in after]
                                    + [inr(sum(h.monthly_interest for h in after))],
            })
            st.dataframe(ladder_tbl, hide_index=True)
            nxt = after[0]
            next_target = gross_monthly * (1 + growth) ** year_n
            st.info(f"Next bond to mature: **{nxt.name or 'bond'}** on {nxt.maturity:%d %b %Y} "
                    f"({inr(nxt.face)} back, {inr(nxt.monthly_interest)} a month of interest lost). "
                    f"Plan your next purchase then. The target will be about {inr(next_target)} a month.")

            last = max(h.maturity for h in after)
            n_months = min(60, (last.year - on.year) * 12 + last.month - on.month + 1)
            series = lad.monthly_interest_series(after, on, n_months)
            st.caption("Monthly interest if you buy nothing else (it steps down as bonds mature):")
            st.bar_chart(pd.DataFrame({"Monthly interest (₹)": [v for _, v in series]},
                                      index=pd.DatetimeIndex([pd.Timestamp(d) for d, _ in series],
                                                             name="Month")))

# ----------------------------------------------------------------------------
# Tab 3: plan ahead
# ----------------------------------------------------------------------------

with tab3:
    st.markdown("How much money to arrange each year. Every bond is assumed to pay the same coupon. "
                "**Lower coupons mean you need more money**, so the second case shows a weaker market.")
    a, b, c = st.columns(3)
    c_hi = a.number_input("Coupon on your bonds: best case (%)", min_value=1.0, max_value=25.0,
                          value=float(cap * 100), step=0.25, key=f"t3_hi_{cap:.4f}") / 100
    c_lo = b.number_input("Coupon on your bonds: weaker case (%)", min_value=1.0, max_value=25.0,
                          value=float(max(1.0, cap * 100 - 1.0)), step=0.25, key=f"t3_lo_{cap:.4f}") / 100
    yrs = int(c.number_input("Years to plan", min_value=3, max_value=30, value=10, step=1, key="t3_years"))
    if max(c_hi, c_lo) > cap + 1e-9:
        st.warning(f"A coupon above your {cap * 100:.2f}% limit is not allowed by your rule.")

    tg = lad.income_targets(gross_monthly, growth, yrs)
    p_hi, rows_hi, _ = lad.plan_for_yields(L, yrs, tg, [c_hi] * L, [c_hi] * (yrs - 1))
    p_lo, rows_lo, _ = lad.plan_for_yields(L, yrs, tg, [c_lo] * L, [c_lo] * (yrs - 1))

    st.subheader("Money to arrange")
    q1, q2, q3, q4 = st.columns(4)
    q1.metric(f"Start with ({pct(c_hi)} coupons)", inr(rows_hi[0]["capital"]))
    q2.metric(f"Start with ({pct(c_lo)} coupons)", inr(rows_lo[0]["capital"]))
    q3.metric(f"Fresh money a year ({pct(c_hi)})", inr(sum(r["fresh"] for r in rows_hi[1:]) / (yrs - 1)))
    q4.metric(f"Fresh money a year ({pct(c_lo)})", inr(sum(r["fresh"] for r in rows_lo[1:]) / (yrs - 1)))

    tbl = pd.DataFrame([{
        "Year": h["year"],
        "Monthly interest (gross)": inr(h["income"] / 12),
        "After tax": inr(h["income"] / 12 * (1 - tax)),
        f"Fresh money ({pct(c_hi)})": inr(h["fresh"]) + (" (start)" if h["year"] == 1 else ""),
        f"Total invested ({pct(c_hi)})": inr(h["capital"]),
        f"Fresh money ({pct(c_lo)})": inr(lo["fresh"]) + (" (start)" if lo["year"] == 1 else ""),
        f"Total invested ({pct(c_lo)})": inr(lo["capital"]),
    } for h, lo in zip(rows_hi, rows_lo)])
    st.dataframe(tbl, hide_index=True)
    st.caption("When every bond pays the same coupon, interest equals money invested × coupon, so your money "
               f"invested has to grow {growth * 100:.0f}% a year too. Real bonds will differ, so use tab ② "
               "for each actual purchase.")
    st.bar_chart(pd.DataFrame({
        f"Fresh money at {pct(c_hi)} (₹)": [r["fresh"] for r in rows_hi[1:]],
        f"Fresh money at {pct(c_lo)} (₹)": [r["fresh"] for r in rows_lo[1:]],
    }, index=pd.Index([r["year"] for r in rows_hi[1:]], name="Year")))

# ----------------------------------------------------------------------------
# Notes
# ----------------------------------------------------------------------------

with st.expander("Assumptions and limits"):
    st.markdown("""
- Interest is paid **monthly** on the **face value** you hold. Bonds paying yearly or quarterly make your
  monthly income lumpy.
- A bond counts as matured on its maturity date. Its interest stops and its face value comes back.
- Amounts are rounded **up** to whole bonds, so interest lands at or slightly above the target.
- Prices: the money you pay is face value × price. Accrued interest, brokerage and taxes on purchase are not
  included.
- Tax is a flat rate on interest. TDS rules, slabs and surcharge are not modelled.
- No defaults or rating changes are modelled. **Credit risk is the real risk.** Spread each step over several
  issuers and check the rating before buying. This is not investment advice.
- The page does not remember your bonds after you close it. Use **Save my ladder (CSV)** in tab ②.
""")
