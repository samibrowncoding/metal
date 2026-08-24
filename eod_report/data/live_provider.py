"""Stub live provider — the shape a production implementation must fill.

Nothing here connects to anything. Each method raises ``NotImplementedError``
and documents the source the desk would actually pull from, the publication
timing, and the joins needed to populate the contract in ``models.py``.

Wiring order suggested for the production build: prices first (everything else
values off them), then internal systems (flows, risk), then exchange and
issuer files (ETF, OI, COT, stocks), then the calendar.
"""

from __future__ import annotations

from datetime import date

from models import (
    ClientFlowsSection,
    EtfSection,
    LookAheadSection,
    PhysicalSection,
    PositioningSection,
    ReportHeader,
    RiskSection,
    TechnicalsSection,
)

_NOT_WIRED = "LiveDataProvider is a stub: no market data connection exists yet."


class LiveDataProvider:
    """Real-feed implementation of the :class:`DataProvider` protocol.

    Structurally satisfies the protocol so ``config.USE_MOCK = False`` type
    checks today and fails loudly at runtime until each method is filled in.
    """

    def get_header(self, report_date: date, author_name: str) -> ReportHeader:
        """Spot closes, session ranges and auction prices.

        Likely sources:
          * Spot close / session high / low — Refinitiv (LSEG) Eikon or
            Datascope ``XAU=``/``XAG=``/``XPT=``/``XPD=``, snapped at the
            London close; Bloomberg ``XAU Curncy`` is the usual alternative.
          * LBMA PM auction price — LBMA precious metals prices feed
            (ICE Benchmark Administration for gold and silver, LME for the
            PGMs), published within minutes of each auction.
        """
        raise NotImplementedError(_NOT_WIRED)

    def get_client_flows(self, report_date: date) -> ClientFlowsSection:
        """Client tickets aggregated by metal and client segment.

        Likely sources:
          * Internal trade capture / order management system, end-of-day
            extract filtered to external counterparties.
          * Client segment from the CRM or KYC master, joined on counterparty
            id — the segment taxonomy in ``models.ClientSegment`` has to be
            mapped to whatever the CRM uses.
          * Unallocated account movements from the vault / metal accounts
            ledger, not the trading system.
        """
        raise NotImplementedError(_NOT_WIRED)

    def get_risk(self, report_date: date) -> RiskSection:
        """Position, P&L, VaR, greeks and limit utilisation.

        Likely sources:
          * Position and greeks — the desk's risk engine end-of-day cut
            (Murex, Calypso or an in-house book), after the official close.
          * P&L and attribution — product control's signed-off daily P&L, not
            the trader estimate; attribution buckets must match
            ``models.PnlAttribution`` exactly or the total will not tie.
          * VaR — market risk's overnight batch (historical simulation,
            1-day 99%).
          * Limits — the limit master in the risk system; utilisation should be
            read from there rather than recomputed here.
        """
        raise NotImplementedError(_NOT_WIRED)

    def get_technicals(self, report_date: date) -> TechnicalsSection:
        """Moving averages, RSI, levels, realised and implied vol.

        Likely sources:
          * Daily OHLC history — Refinitiv (LSEG) Datascope or Bloomberg
            ``BDH`` pulls; needs at least 200 clean sessions for the MA200.
          * Implied vol — the desk's own ATM 1-month vol marks, or broker
            runs; realised vol should be computed from the same close series
            used for the moving averages so the spread is consistent.
          * Support and resistance — either the desk's published levels or a
            deterministic swing-point algorithm; whichever is chosen must be
            stated, since the number is analyst-facing.
        """
        raise NotImplementedError(_NOT_WIRED)

    def get_etf(self, report_date: date) -> EtfSection:
        """Physically backed ETF holdings and flows.

        Likely sources:
          * Issuer files — SPDR (GLD), iShares (IAU, SLV) and abrdn (PPLT,
            PALL) publish daily holdings as CSV/XLS on their fund pages.
          * Aggregate "other" line — World Gold Council or Silver Institute
            monthly aggregates, or a vendor ETF holdings dataset.
          * These are **T+1**: the file published this morning is yesterday's
            holdings. Stamp ``as_of_date`` with the effective date, not today.
        """
        raise NotImplementedError(_NOT_WIRED)

    def get_positioning(self, report_date: date) -> PositioningSection:
        """Exchange open interest, COT positioning and EFP levels.

        Likely sources:
          * Open interest and volume — CME/COMEX daily bulletin (preliminary
            volumes intraday, final open interest the following morning).
          * Managed money positioning — CFTC Commitments of Traders,
            disaggregated report: surveyed Tuesday, published Friday 15:30 ET.
            Carry the survey date through to ``cot_report_date``; do not
            silently present it as today's positioning.
          * EFP — broker runs or the desk's own quotes; the trailing range
            should come from the same series to keep the flag meaningful.
        """
        raise NotImplementedError(_NOT_WIRED)

    def get_physical(self, report_date: date) -> PhysicalSection:
        """Inventories, regional premiums and lease rates.

        Likely sources:
          * COMEX registered and eligible stocks — CME daily metal depository
            statistics report.
          * London vaulted holdings — LBMA vault holdings data, published
            **monthly** with roughly a three-month lag on the underlying
            month-end.
          * SGE withdrawals and Shanghai premium — Shanghai Gold Exchange
            weekly delivery data plus SHFE/SGE benchmark prices converted at
            the CNY fix.
          * Loco premiums — desk quotes or a physical broker's run.
          * Lease rates — LBMA forward curves (gold forward offered rates) or
            broker quotes; sign convention matters, so state it once.
        """
        raise NotImplementedError(_NOT_WIRED)

    def get_look_ahead(self, report_date: date) -> LookAheadSection:
        """Forward calendar for the next session and the next week.

        Likely sources:
          * Economic releases and consensus — Refinitiv (LSEG) or Bloomberg
            economic calendar; consensus must be captured as displayed text
            including its unit.
          * Central bank events — the banks' own published calendars.
          * First notice days, expiries and roll windows — CME contract
            specifications; derivable from the contract calendar rather than
            fetched daily.
          * LBMA auction times — fixed schedule, safe to keep in config.
          * Market holidays — exchange holiday calendars for London, New York
            and Shanghai.
        """
        raise NotImplementedError(_NOT_WIRED)
