"""Tests for ladder.py. Run with:  python test_ladder.py   (or pytest)"""

import math

import ladder as lad


def close(a, b, tol=1e-9):
    return math.isclose(a, b, rel_tol=tol, abs_tol=1e-6)


def test_targets_grow_6_percent():
    t = lad.income_targets(20000, 0.06, 3)
    assert close(t[0], 240000) and close(t[1], 254400) and close(t[2], 269664)


def test_gross_from_net():
    assert close(lad.gross_from_net(14000, 0.30), 20000)


def test_rung_coupons_keep_average():
    c = lad.rung_coupons(0.096, 0.01, 4)
    assert close(sum(c) / 4, 0.096)
    assert c[0] < c[1] < c[2] < c[3]
    assert close(c[3] - c[0], 0.01)


def test_capital_mode_hits_target_every_year():
    t = lad.income_targets(20000, 0.06, 10)
    avg, coupons, rows, _ = lad.plan_for_capital(4, 10, t, 2_500_000, [50_000] * 9, 0.01)
    assert close(avg, 0.096)
    for r in rows:
        assert close(r["income"], r["target"]), r


def test_yield_mode_hits_target_every_year():
    t = lad.income_targets(20000, 0.06, 10)
    p, rows, _ = lad.plan_for_yields(4, 10, t, [0.08, 0.085, 0.09, 0.095], [0.095] * 9)
    assert close(p * 4 * 0.0875, t[0])        # average of the four yields is 8.75%
    for r in rows:
        assert close(r["income"], r["target"]), r


def test_closed_form_year2_coupon_without_fresh_money():
    # Flat coupons c0, growth g, no fresh money:  c_new(year 2) = c0 * (1 + g * L)
    L, g, c0 = 4, 0.06, 0.096
    t = lad.income_targets(20000, g, 5)
    rows, _ = lad.simulate(L, 5, t, 2_500_000 / L, [c0] * L, topups=[0.0] * 4)
    assert close(rows[1]["new_coupon"], c0 * (1 + g * L))


def test_required_coupon_keeps_rising_without_fresh_money():
    t = lad.income_targets(20000, 0.06, 10)
    _, _, rows, _ = lad.plan_for_capital(4, 10, t, 2_500_000, [0.0] * 9, 0.0)
    coupons = [r["new_coupon"] for r in rows[1:]]
    assert all(b > a for a, b in zip(coupons, coupons[1:]))
    assert coupons[-1] > 0.14                     # becomes unrealistic


def test_no_growth_flat_yields_needs_no_fresh_money():
    t = lad.income_targets(20000, 0.0, 8)
    _, rows, _ = lad.plan_for_yields(4, 8, t, [0.09] * 4, [0.09] * 7)
    for r in rows[1:]:
        assert abs(r["fresh"]) < 1e-6


def test_flat_yields_capital_must_grow_as_fast_as_income():
    g = 0.06
    t = lad.income_targets(20000, g, 8)
    _, rows, _ = lad.plan_for_yields(4, 8, t, [0.09] * 4, [0.09] * 7)
    for a, b in zip(rows, rows[1:]):
        assert close(b["capital"] / a["capital"], 1 + g)


def test_capital_accounting():
    t = lad.income_targets(20000, 0.06, 10)
    _, rows, _ = lad.plan_for_yields(4, 10, t, [0.08, 0.085, 0.09, 0.095], [0.095] * 9)
    for a, b in zip(rows, rows[1:]):
        assert close(b["capital"], a["capital"] + b["fresh"])


def test_first_maturity_is_the_one_year_rung():
    t = lad.income_targets(20000, 0.06, 6)
    _, rows, bonds = lad.plan_for_yields(4, 6, t, [0.08, 0.085, 0.09, 0.095], [0.095] * 5)
    p = rows[0]["capital"] / 4
    assert close(rows[1]["matured"], p)
    assert close(rows[5]["matured"], rows[1]["new_principal"])   # year-2 bond matures in year 6
    assert all(b.tenor in (1, 2, 3, 4) for b in bonds)


def test_income_without_fresh_money_flat_when_yields_flat():
    out = lad.income_without_fresh_money(4, 8, 600_000, [0.09] * 4, [0.09] * 7)
    assert all(close(x, out[0]) for x in out)


def test_typical_rating():
    assert lad.typical_rating(0.0928, 0.0708)[0] == "A+"      # 220 bps
    assert lad.typical_rating(0.0808, 0.0708)[2] == "lower"   # 100 bps
    assert lad.typical_rating(0.1408, 0.0708)[2] == "high"    # 700 bps


def test_bad_arguments():
    t = lad.income_targets(20000, 0.06, 5)
    for kwargs in ({}, {"new_coupons": [0.09] * 4, "topups": [0.0] * 4}):
        try:
            lad.simulate(4, 5, t, 1.0, [0.09] * 4, **kwargs)
        except ValueError:
            continue
        raise AssertionError("expected ValueError")


# ---------------------------------------------------------------------------
# Real purchases with actual dates
# ---------------------------------------------------------------------------

from datetime import date  # noqa: E402

START = date(2026, 11, 12)
COUPONS = [0.08, 0.085, 0.09, 0.095]


def _first_ladder(face_each, lot=0.0):
    return [lad.Holding(f"B{j}", face_each, COUPONS[j - 1], lad.add_years(START, j)) for j in range(1, 5)]


def test_add_months_years_and_ladder_year():
    assert lad.add_years(date(2028, 2, 29), 1) == date(2029, 2, 28)
    assert lad.add_months(date(2026, 1, 31), 1) == date(2026, 2, 28)
    assert lad.add_months(date(2026, 11, 12), 3) == date(2027, 2, 12)
    assert lad.ladder_year(START, date(2026, 11, 12)) == 1
    assert lad.ladder_year(START, date(2027, 11, 11)) == 1
    assert lad.ladder_year(START, date(2027, 11, 12)) == 2
    assert lad.ladder_year(START, date(2030, 11, 12)) == 5
    assert lad.ladder_year(START, date(2026, 1, 1)) == 1


def test_initial_ladder_exact_and_rounded():
    ini = lad.size_initial_ladder(20000, COUPONS, lot=0)
    assert close(ini.monthly_total, 20000)
    assert close(ini.face_each, 20000 * 12 / sum(COUPONS))
    r = lad.size_initial_ladder(20000, COUPONS, lot=10000)
    assert r.face_each % 10000 == 0 and r.monthly_total >= 20000
    assert r.face_each - ini.face_each < 10000
    assert r.bonds_each * 10000 == r.face_each


def test_new_bond_sizing_matches_the_yearly_engine_for_years_2_and_3():
    t = lad.income_targets(20000, 0.06, 3)
    ini = lad.size_initial_ladder(20000, COUPONS, lot=0)
    rows, _ = lad.simulate(4, 3, t, ini.face_each, COUPONS, new_coupons=[0.095, 0.095])

    holdings = _first_ladder(ini.face_each)
    on2 = date(2027, 11, 12)                       # the 1-year bond matures today
    s2 = lad.size_new_bond(20000 * 1.06, holdings, on2, 0.095, 100, 0)
    assert close(s2.matured_principal, rows[1]["matured"])
    assert close(s2.face_exact, rows[1]["new_principal"])
    assert close(s2.fresh_money, rows[1]["fresh"])
    assert close(s2.monthly_after, 20000 * 1.06)

    # chain into year 3: drop the matured bond, add the new one (matures 4 years later)
    holdings = [h for h in holdings if h.maturity > on2]
    holdings.append(lad.Holding("new", s2.face_exact, 0.095, lad.add_years(on2, 4)))
    on3 = date(2028, 11, 12)
    s3 = lad.size_new_bond(20000 * 1.06 ** 2, holdings, on3, 0.095, 100, 0)
    assert close(s3.face_exact, rows[2]["new_principal"])
    assert close(s3.fresh_money, rows[2]["fresh"])


def test_rounding_up_to_whole_bonds_always_meets_target():
    ini = lad.size_initial_ladder(20000, COUPONS, lot=0)
    s = lad.size_new_bond(21200, _first_ladder(ini.face_each), date(2027, 11, 12), 0.10, 100, 10000)
    assert s.needed and s.face % 10000 == 0 and s.face >= s.face_exact
    assert s.face - s.face_exact < 10000 and s.bonds * 10000 == s.face
    assert s.monthly_after >= 21200 - 1e-6


def test_price_below_par_lowers_the_money_to_pay_not_the_face_value():
    ini = lad.size_initial_ladder(20000, COUPONS, lot=0)
    h = _first_ladder(ini.face_each)
    par = lad.size_new_bond(21200, h, date(2027, 11, 12), 0.10, 100, 0)
    disc = lad.size_new_bond(21200, h, date(2027, 11, 12), 0.10, 98, 0)
    assert close(par.face, disc.face)
    assert close(disc.money_to_pay, par.face * 0.98)
    assert close(disc.fresh_money, disc.money_to_pay - disc.matured_principal)


def test_no_purchase_needed_when_running_bonds_already_meet_target():
    h = [lad.Holding("big", 10_000_000, 0.10, date(2030, 1, 1)),
         lad.Holding("old", 500_000, 0.09, date(2027, 1, 1))]
    s = lad.size_new_bond(21200, h, date(2027, 6, 1), 0.10, 100, 10000)
    assert not s.needed and s.face == 0 and s.money_to_pay == 0
    assert close(s.fresh_money, -500_000)


def test_bond_maturing_on_the_purchase_date_counts_as_matured():
    h = [lad.Holding("a", 100000, 0.10, date(2027, 11, 12))]
    s = lad.size_new_bond(5000, h, date(2027, 11, 12), 0.10, 100, 0)
    assert close(s.matured_principal, 100000) and close(s.running_monthly, 0)


def test_sizing_rejects_bad_inputs():
    for kw in ({"coupon": 0.0}, {"coupon": 0.1, "price_pct": 0}):
        try:
            lad.size_new_bond(20000, [], date(2027, 1, 1), **{"coupon": 0.1, **kw})
        except ValueError:
            continue
        raise AssertionError("expected ValueError")


def test_monthly_interest_series_steps_down_at_maturities():
    ini = lad.size_initial_ladder(20000, COUPONS, lot=0)
    h = _first_ladder(ini.face_each)
    s = lad.monthly_interest_series(h, START, 48)
    assert close(s[0][1], 20000)
    assert all(b[1] <= a[1] + 1e-9 for a, b in zip(s, s[1:]))
    assert s[11][1] > s[12][1] > s[24][1] > s[36][1] > 0      # drops at each anniversary
    assert close(s[12][1], sum(x.monthly_interest for x in h[1:]))


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in tests:
        fn()
        print("ok  ", fn.__name__)
    print(f"{len(tests)} tests passed")
