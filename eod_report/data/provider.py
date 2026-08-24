"""The single seam between the report and its data.

Every number that reaches the UI or the email comes through the
:class:`DataProvider` protocol below. Swapping fabricated data for real feeds
is a one-line change: set ``USE_MOCK = False`` in ``config.py``.

The protocol is deliberately section-shaped rather than instrument-shaped: one
call per report section, each returning a fully validated pydantic model. That
keeps the Rust port's trait surface small and makes it obvious which upstream
system owns which block of the report.
"""

from __future__ import annotations

from datetime import date
from typing import Protocol, runtime_checkable

import config
from models import (
    ClientFlowsSection,
    EodReport,
    EtfSection,
    LookAheadSection,
    PhysicalSection,
    PositioningSection,
    ReportHeader,
    RiskSection,
    TechnicalsSection,
)


@runtime_checkable
class DataProvider(Protocol):
    """Source of one trading day's report data.

    Implementations must be pure with respect to ``report_date``: calling any
    method twice with the same date returns equal data. The mock provider
    guarantees this with a date-derived seed; a live provider gets it from the
    fact that an end-of-day snapshot is immutable once the session has closed.
    """

    def get_header(self, report_date: date, author_name: str) -> ReportHeader:
        """Section 0 — report identity and the per-metal snapshot strip."""
        ...

    def get_client_flows(self, report_date: date) -> ClientFlowsSection:
        """Section 1 — net client flow by metal and client segment."""
        ...

    def get_risk(self, report_date: date) -> RiskSection:
        """Section 2 — desk position, P&L, VaR, greeks and limit utilisation."""
        ...

    def get_technicals(self, report_date: date) -> TechnicalsSection:
        """Section 3 — moving averages, RSI, levels, vols and price history."""
        ...

    def get_etf(self, report_date: date) -> EtfSection:
        """Section 4 — physically backed ETF holdings and flows (T+1)."""
        ...

    def get_positioning(self, report_date: date) -> PositioningSection:
        """Section 5 — COMEX open interest, COT positioning and EFP levels."""
        ...

    def get_physical(self, report_date: date) -> PhysicalSection:
        """Section 6 — inventories, regional premiums and lease rates."""
        ...

    def get_look_ahead(self, report_date: date) -> LookAheadSection:
        """Section 7 — next session and next week calendar."""
        ...


def build_report(
    provider: DataProvider, report_date: date, author_name: str
) -> EodReport:
    """Assemble a whole day's report from a provider.

    Kept as a free function rather than a protocol method so implementations
    only have to supply the eight section calls.
    """
    return EodReport(
        header=provider.get_header(report_date, author_name),
        client_flows=provider.get_client_flows(report_date),
        risk=provider.get_risk(report_date),
        technicals=provider.get_technicals(report_date),
        etf=provider.get_etf(report_date),
        positioning=provider.get_positioning(report_date),
        physical=provider.get_physical(report_date),
        look_ahead=provider.get_look_ahead(report_date),
    )


def get_provider() -> DataProvider:
    """Return the configured provider.

    Imports are local so that flipping ``USE_MOCK`` never drags the unused
    implementation (and, in production, its client libraries) into the process.
    """
    if config.USE_MOCK:
        from data.mock_provider import MockDataProvider

        return MockDataProvider()

    from data.live_provider import LiveDataProvider

    return LiveDataProvider()
