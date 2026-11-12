"""
Bond-ladder maths (pure Python, no Streamlit) so it can be tested on its own.

Model
-----
* Bonds are bought at face value (so coupon = YTM) and held to maturity. No defaults.
* Coupons are paid monthly: a bond with principal P and coupon c pays P * c / 12 every month.
* Years are numbered 1, 2, 3, ...  A bond bought at the start of year `start` with tenor T
  matures at the start of year `start + T`, when its principal comes back.
* At the start of every year after the first, the matured principal (plus any fresh money) is
  put into ONE new bond of the longest tenor (= the ladder length).
* Interest target for year k:  monthly_target * 12 * (1 + growth) ** (k - 1).
"""

from __future__ import annotations

import calendar
import math
from dataclasses import dataclass
from datetime import date
from typing import Dict, List, Optional, Sequence, Tuple

NAN = float("nan")


@dataclass
class Bond:
    start: int          # year (1-based) at whose start the bond is bought
    end: int            # year at whose start it matures (principal returned)
    principal: float
    coupon: float       # annual coupon as a fraction (0.09 = 9%)
    label: str = ""

    def active_in(self, year: int) -> bool:
        return self.start <= year < self.end

    @property
    def tenor(self) -> int:
        return self.end - self.start

    @property
    def annual_income(self) -> float:
        return self.principal * self.coupon


# ----------------------------------------------------------------------------
# Targets and helpers
# ----------------------------------------------------------------------------

def income_targets(monthly_gross: float, growth: float, years: int) -> List[float]:
    """Annual interest wanted in each year 1..years."""
    return [12.0 * monthly_gross * (1.0 + growth) ** k for k in range(years)]


def gross_from_net(net: float, tax: float) -> float:
    """Before-tax interest needed to receive `net` after tax (tax as a fraction, < 1)."""
    if not 0.0 <= tax < 1.0:
        raise ValueError("tax must be in [0, 1)")
    return net / (1.0 - tax)


def rung_coupons(avg: float, slope: float, length: int) -> List[float]:
    """
    Spread an average coupon over the rungs so the shortest rung pays `slope` less than the
    longest. The simple average of the rung coupons stays equal to `avg`.
    """
    if length == 1:
        return [avg]
    return [max(0.0, avg + slope * (j / (length - 1) - 0.5)) for j in range(length)]


# Rough rule of thumb only: typical extra yield over a G-Sec by rating (in basis points).
RATING_SPREADS: List[Tuple[str, int]] = [
    ("AAA", 60), ("AA+", 90), ("AA", 120), ("AA-", 160), ("A+", 220), ("A", 280),
    ("A-", 340), ("BBB+", 420), ("BBB", 500), ("BBB-", 600), ("below BBB-", 800),
]


def typical_rating(yield_frac: float, gsec_frac: float) -> Tuple[str, float, str]:
    """(closest typical rating, spread in bps, 'lower' | 'moderate' | 'high' credit risk)."""
    spread_bps = (yield_frac - gsec_frac) * 10000.0
    label = min(RATING_SPREADS, key=lambda r: abs(r[1] - spread_bps))[0]
    risk = "lower" if spread_bps <= 160 else "moderate" if spread_bps <= 340 else "high"
    return label, spread_bps, risk


# ----------------------------------------------------------------------------
# Simulation
# ----------------------------------------------------------------------------

def simulate(
    length: int,
    years: int,
    targets: Sequence[float],
    init_principal: float,
    init_coupons: Sequence[float],
    new_coupons: Optional[Sequence[float]] = None,
    topups: Optional[Sequence[float]] = None,
) -> Tuple[List[Dict], List[Bond]]:
    """
    Run the ladder year by year so that interest hits `targets` exactly from year 2 onwards.

    Give EXACTLY ONE of:
      new_coupons  -> coupon of the new bond bought at the start of years 2..years;
                      the function solves the fresh money needed each year.
      topups       -> fresh money added at the start of years 2..years;
                      the function solves the coupon needed on each new bond.

    init_principal is the amount in EACH initial rung (rung j has tenor j years).
    Returns (rows, bonds): one row per year, and every bond ever held.
    """
    if (new_coupons is None) == (topups is None):
        raise ValueError("Give exactly one of new_coupons or topups.")
    if length < 1 or years < 1:
        raise ValueError("length and years must be at least 1.")
    if len(init_coupons) != length:
        raise ValueError("init_coupons needs one coupon per rung.")
    if len(targets) < years:
        raise ValueError("targets must cover every year.")
    chosen = new_coupons if new_coupons is not None else topups
    if len(chosen) < years - 1:
        raise ValueError("new_coupons / topups must cover years 2..years.")

    bonds = [
        Bond(1, 1 + j, init_principal, init_coupons[j - 1], f"Initial {j}-year")
        for j in range(1, length + 1)
    ]
    rows: List[Dict] = []

    for year in range(1, years + 1):
        matured_p, fresh = 0.0, 0.0
        new_p: Optional[float] = None
        new_c: Optional[float] = None

        if year == 1:
            fresh = init_principal * length
        else:
            matured_p = sum(b.principal for b in bonds if b.end == year)
            income_kept = sum(b.annual_income for b in bonds if b.end > year)
            need = targets[year - 1] - income_kept   # interest the NEW bond must supply

            if new_coupons is not None:
                c = new_coupons[year - 2]
                if c <= 0:
                    raise ValueError("new_coupons must be positive.")
                principal = max(need, 0.0) / c
                fresh = principal - matured_p        # negative = money released
            else:
                fresh = topups[year - 2]
                principal = matured_p + fresh
                c = max(need, 0.0) / principal if principal > 0 else NAN

            if principal > 0:
                bonds.append(Bond(year, year + length, principal, c, f"Bought in year {year}"))
            new_p, new_c = principal, c

        active = [b for b in bonds if b.active_in(year)]
        income = sum(b.annual_income for b in active)
        capital = sum(b.principal for b in active)
        rows.append({
            "year": year,
            "target": targets[year - 1],
            "income": income,
            "capital": capital,
            "fresh": fresh,
            "matured": matured_p,
            "new_principal": new_p,
            "new_coupon": new_c,
            "avg_yield": income / capital if capital else NAN,
        })
    return rows, bonds


def plan_for_capital(
    length: int, years: int, targets: Sequence[float], capital: float,
    topups: Sequence[float], slope: float,
):
    """
    You know the capital -> what coupon is needed?
    Returns (avg_coupon_needed, rung_coupons, rows, bonds).
    """
    avg = targets[0] / capital
    coupons = rung_coupons(avg, slope, length)
    rows, bonds = simulate(length, years, targets, capital / length, coupons, topups=topups)
    return avg, coupons, rows, bonds


def plan_for_yields(
    length: int, years: int, targets: Sequence[float],
    init_yields: Sequence[float], new_coupons: Sequence[float],
):
    """
    You know the yields -> how much capital is needed?
    Returns (principal_per_rung, rows, bonds).
    """
    principal = targets[0] / sum(init_yields)
    rows, bonds = simulate(length, years, targets, principal, list(init_yields), new_coupons=new_coupons)
    return principal, rows, bonds


def income_without_fresh_money(
    length: int, years: int, init_principal: float,
    init_coupons: Sequence[float], new_coupons: Sequence[float],
) -> List[float]:
    """Annual interest if matured money is simply rolled into a new bond (no fresh money)."""
    bonds = [
        Bond(1, 1 + j, init_principal, init_coupons[j - 1]) for j in range(1, length + 1)
    ]
    out: List[float] = []
    for year in range(1, years + 1):
        if year > 1:
            matured_p = sum(b.principal for b in bonds if b.end == year)
            bonds.append(Bond(year, year + length, matured_p, new_coupons[year - 2]))
        out.append(sum(b.annual_income for b in bonds if b.active_in(year)))
    return out


# ----------------------------------------------------------------------------
# Real purchases: actual bonds, actual coupons, actual dates
# ----------------------------------------------------------------------------

def add_months(d: date, n: int) -> date:
    y, m = divmod(d.month - 1 + n, 12)
    year, month = d.year + y, m + 1
    return date(year, month, min(d.day, calendar.monthrange(year, month)[1]))


def add_years(d: date, n: int) -> date:
    return add_months(d, 12 * n)


def ladder_year(start: date, on: date) -> int:
    """Ladder year on a date: 1 for the first 12 months after `start`, 2 for the next 12, ..."""
    full = on.year - start.year - ((on.month, on.day) < (start.month, start.day))
    return max(1, full + 1)


@dataclass
class Holding:
    """A bond you hold. `face` is the face value held; interest = face * coupon."""
    name: str
    face: float
    coupon: float       # fraction
    maturity: date

    @property
    def monthly_interest(self) -> float:
        return self.face * self.coupon / 12.0


@dataclass
class Sizing:
    target_monthly: float        # interest wanted per month
    running_monthly: float       # interest from bonds still running after the purchase date
    matured_principal: float     # face value of bonds that have matured (money back)
    shortfall_monthly: float     # interest the new bond must supply
    needed: bool                 # False if the running bonds already meet the target
    face_exact: float            # face value that supplies the shortfall exactly
    bonds: int                   # whole bonds to buy (0 if no lot size was given)
    face: float                  # face value to buy, rounded up to whole bonds
    money_to_pay: float          # face * price / 100
    fresh_money: float           # money_to_pay - matured_principal (negative = money released)
    monthly_after: float         # monthly interest after buying


def _round_up_to_lot(face_exact: float, lot: float) -> Tuple[int, float]:
    if lot and lot > 0:
        bonds = max(1, math.ceil(face_exact / lot - 1e-9))
        return bonds, bonds * lot
    return 0, face_exact


def size_new_bond(
    target_monthly: float,
    holdings: Sequence[Holding],
    on: date,
    coupon: float,
    price_pct: float = 100.0,
    lot: float = 0.0,
) -> Sizing:
    """
    How much to put in the new bond so that monthly interest reaches the target.

    Bonds maturing on or before `on` count as matured (principal back, no more interest);
    the rest keep paying. The new bond must supply whatever interest is still missing.
    """
    if coupon <= 0:
        raise ValueError("coupon must be positive")
    if price_pct <= 0:
        raise ValueError("price must be positive")
    running = [h for h in holdings if h.maturity > on]
    matured = [h for h in holdings if h.maturity <= on]
    running_monthly = sum(h.monthly_interest for h in running)
    matured_principal = sum(h.face for h in matured)
    shortfall = target_monthly - running_monthly

    if shortfall <= 0.01:       # already at or above target
        return Sizing(target_monthly, running_monthly, matured_principal, shortfall, False,
                      0.0, 0, 0.0, 0.0, -matured_principal, running_monthly)

    face_exact = shortfall * 12.0 / coupon
    bonds, face = _round_up_to_lot(face_exact, lot)
    money = face * price_pct / 100.0
    return Sizing(target_monthly, running_monthly, matured_principal, shortfall, True,
                  face_exact, bonds, face, money, money - matured_principal,
                  running_monthly + face * coupon / 12.0)


@dataclass
class InitialLadder:
    face_each_exact: float
    bonds_each: int
    face_each: float
    monthly_each: List[float]
    total_face: float
    monthly_total: float


def size_initial_ladder(target_monthly: float, coupons: Sequence[float], lot: float = 0.0) -> InitialLadder:
    """Equal face value in every rung so that year-1 monthly interest reaches the target."""
    total_coupon = sum(coupons)
    if total_coupon <= 0:
        raise ValueError("coupons must be positive")
    exact = target_monthly * 12.0 / total_coupon
    bonds, face = _round_up_to_lot(exact, lot)
    monthly = [face * c / 12.0 for c in coupons]
    return InitialLadder(exact, bonds, face, monthly, face * len(coupons), sum(monthly))


def monthly_interest_series(holdings: Sequence[Holding], on: date, months: int) -> List[Tuple[date, float]]:
    """Monthly interest in each of the next `months` months if you buy nothing else."""
    out = []
    for k in range(months):
        d = add_months(on, k)
        out.append((d, sum(h.monthly_interest for h in holdings if h.maturity > d)))
    return out
