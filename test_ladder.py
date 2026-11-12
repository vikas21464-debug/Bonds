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


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in tests:
        fn()
        print("ok  ", fn.__name__)
    print(f"{len(tests)} tests passed")
