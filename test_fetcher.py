"""Tests for fetcher.py parsing. Run with:  python test_fetcher.py   (or pytest)"""

from datetime import date

import fetcher as f


def test_isin_check_digit():
    assert f.valid_isin("INE530L07AV8")
    assert f.valid_isin("INE926R07035")
    assert not f.valid_isin("INE530L07AV9")      # wrong check digit
    assert not f.valid_isin("US0378331005")      # not an Indian ISIN
    assert not f.valid_isin("")


def test_indiabonds_style_text():
    text = """INE530L07AV8 Nido Home Finance
    Coupon Rate (Returns) 10.25 %
    DATE OF MATURITY 31/10/2030
    Face Value ₹ 1,00,000
    Interest Payment Frequency Monthly
    Allotment Date 31/10/2025"""
    b = f.parse_bond_text(text)
    assert b.coupon == 10.25 and b.maturity == date(2030, 10, 31)
    assert b.face_value == 100000 and b.frequency == "monthly" and b.complete


def test_month_name_dates():
    assert f.parse_bond_text("Coupon 9.5%\nMaturity Date: 15 Mar 2029").maturity == date(2029, 3, 15)
    assert f.parse_bond_text("Coupon 9.5%\nMaturity Date: March 15, 2029").maturity == date(2029, 3, 15)
    assert f.parse_bond_text("Coupon 9.5%\nRedemption Date 2029-03-15").maturity == date(2029, 3, 15)
    assert f.parse_bond_text("Coupon 9.5%\nDate of maturity 5th March 2029").maturity == date(2029, 3, 5)


def test_allotment_date_is_not_mistaken_for_maturity():
    b = f.parse_bond_text("Allotment Date 01/01/2024\nMaturity Date 01/01/2028\nCoupon Rate 9%")
    assert b.maturity == date(2028, 1, 1) and b.coupon == 9.0


def test_html_page():
    raw = ("<html><script>var x='Coupon 99%';</script><div>Coupon Rate</div><div><b>9.75%</b></div>"
           "<div>Maturity Date</div><div>12-08-2029</div></html>")
    b = f.parse_bond_text(f.html_to_text(raw))
    assert b.coupon == 9.75 and b.maturity == date(2029, 8, 12)


def test_missing_values_stay_none():
    b = f.parse_bond_text("Nothing useful here")
    assert b.coupon is None and b.maturity is None and not b.complete
    assert not f.parse_bond_text("Coupon Rate 9%").complete


def test_absurd_coupon_rejected():
    assert f.parse_bond_text("Coupon rate 250%").coupon is None


def test_lookup_handles_network_failure_without_crashing(monkeypatch=None):
    orig = f._get
    f._get = lambda *a, **k: (_ for _ in ()).throw(OSError("blocked"))
    try:
        r = f.lookup_isin("INE530L07AV8")
    finally:
        f._get = orig
    assert r.best is None and r.errors


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in tests:
        fn()
        print("ok  ", fn.__name__)
    print(f"{len(tests)} tests passed")
