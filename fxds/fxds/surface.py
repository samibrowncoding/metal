"""The assembled volatility surface - Practicals D, E and F combined.

The book builds the ATM curve and the volatility smile separately and never joins
them. This module does::

    tenor dates (Practical D)
        -> ATM curve with day weights (Practical E)
            -> Malz smile per tenor (Practical F)
                -> vol(expiry_date, strike)

That chain is the payoff for the whole first half of the book. It also carries real
simplifications, listed in full in :data:`SIMPLIFICATIONS` and in
``notes/deviations.md``. Read them before trusting a number out of here.

The surface's job is the one Chapter 7 describes: given *any* expiry date and *any*
strike, return a consistent implied volatility, so a price can be quoted for a
contract nobody has quoted before. That flexibility is the whole point of an OTC
market, and a surface is what makes it possible.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

import numpy as np
import pandas as pd

from .atm_curve import ATMCurve, Interpolation, WeightedATMCurve, variance
from .conventions import MARKET_TENORS
from .dates import expiry_from_tenor
from .smile import MalzSmile, put_delta_from_strike, strike_from_put_delta

SIMPLIFICATIONS: tuple[str, ...] = (
    "Malz smile on OUTRIGHT deltas, not the broker fly the interbank market actually "
    "trades. Chapter 12 spends several pages on why those differ: broker fly strikes "
    "are generated ignoring the risk reversal, so they are not the outright 25 delta "
    "strikes, and a broker fly carries vanna when valued on the smile. This is the "
    "single largest simplification in the surface.",
    "The Malz form implies a 25d/10d risk reversal multiplier of exactly 1.6. Chapter "
    "12 notes the market value is usually nearer 1.8, so the 10 delta skew is "
    "systematically understated.",
    "Smile parameters are interpolated linearly in time between tenors. Real desks "
    "differ on whether to interpolate in delta space, strike space or model-parameter "
    "space - Chapter 12 says so explicitly and does not pick one.",
    "Spot delta throughout. No forward-delta convention (Chapter 12 notes long-dated "
    "G10 and EM risk reversals are usually quoted on forward delta) and no "
    "premium-adjusted delta for CCY1-premium pairs (Chapter 8, detail in Chapter 14).",
    "Weekends-only calendar, no holidays, T+2 settlement assumed for every pair.",
    "Flat continuously compounded interest rates. No curve building, no basis, no "
    "credit - the book sets all three aside in its Preface and so does this.",
    "Non-negative forward variance is CHECKED, not guaranteed by construction. "
    "Chapter 11 notes real desks build curves so the guarantee holds structurally.",
    "One cut only. No New York versus Tokyo differential, and no intraday variance "
    "profile, both of which Chapter 11 covers.",
)
"""Everything this surface simplifies away, in the order it matters.

Printed by :meth:`VolatilitySurface.explain_simplifications`. Not decoration - a
surface that does not tell you what it is ignoring is worse than no surface.
"""


@dataclass
class TenorSmile:
    """The three market instruments at one tenor (Ch. 12).

    Attributes:
        tenor: Tenor label, e.g. ``"1M"``.
        atm: ATM implied volatility, as a decimal.
        rr25: 25 delta risk reversal, as a decimal.
        fly25: 25 delta butterfly, as a decimal.
    """

    tenor: str
    atm: float
    rr25: float
    fly25: float

    def as_malz(self) -> MalzSmile:
        """The Malz smile for this tenor."""
        return MalzSmile(atm=self.atm, rr25=self.rr25, fly25=self.fly25)


@dataclass
class VolatilitySurface:
    """A volatility surface assembled from Practicals D, E and F.

    Args:
        horizon: The trade date.
        spot: Current spot, CCY2 per CCY1.
        r_ccy1: Continuously compounded CCY1 rate.
        r_ccy2: Continuously compounded CCY2 rate.
        tenor_smiles: The market instruments at each tenor, ascending in maturity.
        interpolation: How the ATM curve interpolates between tenors.
        weights: Optional day-weight model. When supplied, the ATM curve carries the
            weekend saw-tooth and any event weights from Practical E, Task C; the
            tenor ATM levels are then treated as the shape the weights modulate.

    Raises:
        ValueError: If no tenors are supplied or spot is not positive.
    """

    horizon: date
    spot: float
    r_ccy1: float
    r_ccy2: float
    tenor_smiles: list[TenorSmile]
    interpolation: Interpolation = Interpolation.LINEAR_VARIANCE
    weights: WeightedATMCurve | None = None

    _atm_curve: ATMCurve = field(init=False, repr=False)
    _expiries: list[date] = field(init=False, repr=False)

    def __post_init__(self) -> None:
        if not self.tenor_smiles:
            raise ValueError("A surface needs at least one tenor")
        if self.spot <= 0:
            raise ValueError(f"Spot must be positive, got {self.spot}")

        self._expiries = [
            expiry_from_tenor(self.horizon, ts.tenor) for ts in self.tenor_smiles
        ]
        if any(b <= a for a, b in zip(self._expiries, self._expiries[1:])):
            raise ValueError("Tenors must be supplied in ascending maturity order")

        self._atm_curve = ATMCurve(
            horizon=self.horizon,
            expiries=list(self._expiries),
            volatilities=[ts.atm for ts in self.tenor_smiles],
            method=self.interpolation,
        )

    # -- the ATM backbone -------------------------------------------------------

    @property
    def expiries(self) -> list[date]:
        """Expiry dates for the quoted tenors."""
        return list(self._expiries)

    @property
    def atm_curve(self) -> ATMCurve:
        """The underlying ATM curve."""
        return self._atm_curve

    def years_to(self, expiry: date) -> float:
        """Time from horizon to an expiry, in years."""
        return self._atm_curve.years_to(expiry)

    def atm(self, expiry: date) -> float:
        """ATM volatility for any expiry date (Practical E).

        With a day-weight model attached, the interpolated ATM is scaled by the ratio
        of weighted to unweighted volatility at that date - so the weekend saw-tooth
        and any event weights ride on top of the market-tenor shape.

        This composition is a choice, not a market convention: Chapter 11 says real
        desks combine a core curve with weights on top, but does not specify how. The
        multiplicative form keeps the tenor levels roughly intact while letting the
        weights shape the days in between. Flagged in ``notes/deviations.md``.

        Args:
            expiry: The expiry date.

        Returns:
            ATM volatility as a decimal.
        """
        base = self._atm_curve.volatility(expiry)
        if self.weights is None:
            return base

        days = (expiry - self.horizon).days
        weighted = self.weights.build(days)
        weighted_vol = float(weighted["atm_vol"].iloc[-1])
        return base * (weighted_vol / self.weights.flat_volatility)

    # -- the smile dimension ----------------------------------------------------

    def smile_at(self, expiry: date) -> MalzSmile:
        """The smile for any expiry date, interpolating the market instruments.

        The ATM comes from :meth:`atm`. The risk reversal and butterfly are
        interpolated linearly in time between the bracketing tenors, and held flat
        beyond the ends.

        Args:
            expiry: The expiry date.

        Returns:
            A :class:`~fxds.smile.MalzSmile`.
        """
        T = self.years_to(expiry)
        times = [self.years_to(e) for e in self._expiries]
        rr = float(np.interp(T, times, [ts.rr25 for ts in self.tenor_smiles]))
        fly = float(np.interp(T, times, [ts.fly25 for ts in self.tenor_smiles]))
        return MalzSmile(atm=self.atm(expiry), rr25=rr, fly25=fly)

    def volatility(self, expiry: date, strike: float) -> float:
        """**The point of the whole thing**: implied volatility for any expiry and strike.

        Unlike :func:`~fxds.smile.strike_placement`, this direction *is* circular. The
        smile is quoted in delta space, so to find the volatility for a given strike
        you need the delta - which needs a volatility. It is solved by fixed-point
        iteration from the ATM, which converges in a handful of steps because the
        smile is shallow in delta.

        Args:
            expiry: The expiry date.
            strike: The strike, CCY2 per CCY1.

        Returns:
            Implied volatility as a decimal.

        Raises:
            ValueError: If the strike is not positive.
            RuntimeError: If the iteration fails to converge.
        """
        if strike <= 0:
            raise ValueError(f"Strike must be positive, got {strike}")

        T = self.years_to(expiry)
        smile = self.smile_at(expiry)
        sigma = smile.atm

        for _ in range(50):
            delta = put_delta_from_strike(
                self.spot, strike, T, self.r_ccy1, self.r_ccy2, sigma
            )
            # put_delta_from_strike returns the signed value; Malz wants it positive.
            updated = float(smile.volatility(np.clip(-delta, 1e-6, 1 - 1e-6)))
            if abs(updated - sigma) < 1e-12:
                return updated
            sigma = updated

        raise RuntimeError(
            f"Smile iteration did not converge for expiry {expiry}, strike {strike}. "
            f"This usually means the smile is steep enough in delta that the "
            f"fixed point is unstable - check the risk reversal and butterfly."
        )

    def strike_for_delta(self, expiry: date, put_delta: float) -> float:
        """The strike at a given positive quoted put delta, on the smile.

        Args:
            expiry: The expiry date.
            put_delta: Positive quoted put delta, between 0 and 1.

        Returns:
            The strike.
        """
        T = self.years_to(expiry)
        vol = float(self.smile_at(expiry).volatility(put_delta))
        return strike_from_put_delta(
            self.spot, -put_delta, T, self.r_ccy1, self.r_ccy2, vol
        )

    # -- views ------------------------------------------------------------------

    def grid(
        self, put_deltas: tuple[float, ...] = (0.10, 0.25, 0.50, 0.75, 0.90)
    ) -> pd.DataFrame:
        """The surface as a table: one row per tenor, one column per delta.

        This is the shape a desk actually looks at - the run of market instruments
        across tenors that Chapter 12 shows.
        """
        rows = []
        for ts, expiry in zip(self.tenor_smiles, self._expiries):
            smile = self.smile_at(expiry)
            row = {"tenor": ts.tenor, "expiry": expiry,
                   "years": round(self.years_to(expiry), 4)}
            for x in put_deltas:
                label = f"{x:.0%}P" if x <= 0.5 else f"{1 - x:.0%}C"
                row[label] = float(smile.volatility(x))
            rows.append(row)
        return pd.DataFrame(rows)

    def surface_mesh(self, points: int = 40) -> pd.DataFrame:
        """A dense grid of (expiry, strike, volatility) for a 3D plot."""
        deltas = np.linspace(0.05, 0.95, points)
        rows = []
        for expiry in self._expiries:
            T = self.years_to(expiry)
            smile = self.smile_at(expiry)
            for x in deltas:
                vol = float(smile.volatility(x))
                rows.append({
                    "expiry": expiry,
                    "years": T,
                    "put_delta": x,
                    "strike": strike_from_put_delta(
                        self.spot, -x, T, self.r_ccy1, self.r_ccy2, vol
                    ),
                    "volatility": vol,
                })
        return pd.DataFrame(rows)

    def check_no_calendar_arbitrage(self) -> pd.DataFrame:
        """Check ATM total variance is non-decreasing across tenors (Ch. 11).

        Returns:
            A DataFrame with per-tenor total variance, the forward variance to the
            next tenor, and whether it is negative. Any ``True`` in the last column is
            a calendar arbitrage and should be treated as a construction failure, not
            a rounding artefact.
        """
        rows = []
        for ts, expiry in zip(self.tenor_smiles, self._expiries):
            T = self.years_to(expiry)
            rows.append({"tenor": ts.tenor, "years": T, "atm": self.atm(expiry),
                         "total_variance": variance(self.atm(expiry), T)})
        frame = pd.DataFrame(rows)
        frame["forward_variance"] = frame["total_variance"].diff()
        frame["negative"] = frame["forward_variance"] < 0
        return frame

    def explain_simplifications(self) -> str:
        """The simplifications this surface carries, as readable text."""
        lines = ["This surface simplifies in the following ways:", ""]
        lines += [f"{i}. {s}" for i, s in enumerate(SIMPLIFICATIONS, start=1)]
        return "\n".join(lines)


def example_surface(horizon: date, spot: float = 1.3000) -> VolatilitySurface:
    """A plausible EUR/USD-shaped surface, for demonstrations and tests.

    Upward-sloping ATM curve, negative (downside-rich) risk reversals that steepen
    with maturity, and positive butterflies - the shape Chapter 7 describes for
    EUR/USD in July 2014.

    Args:
        horizon: The trade date.
        spot: Current spot.

    Returns:
        A :class:`VolatilitySurface`.
    """
    quotes = [
        # tenor, atm,   rr25,    fly25
        ("1W",  0.0685, -0.0015, 0.0018),
        ("2W",  0.0700, -0.0020, 0.0020),
        ("1M",  0.0720, -0.0028, 0.0022),
        ("2M",  0.0745, -0.0035, 0.0025),
        ("3M",  0.0765, -0.0042, 0.0028),
        ("6M",  0.0800, -0.0055, 0.0032),
        ("9M",  0.0820, -0.0064, 0.0035),
        ("1Y",  0.0835, -0.0070, 0.0038),
        ("2Y",  0.0870, -0.0085, 0.0044),
    ]
    return VolatilitySurface(
        horizon=horizon,
        spot=spot,
        r_ccy1=0.005,
        r_ccy2=0.025,
        tenor_smiles=[TenorSmile(t, a, rr, fly) for t, a, rr, fly in quotes],
    )
