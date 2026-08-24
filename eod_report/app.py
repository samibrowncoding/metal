"""Streamlit entry point for the end-of-day precious metals report.

Run with::

    streamlit run app.py

The page is the analyst's working surface: fabricated desk data on the left of
each section, the commentary box for that section on the right, so the numbers
stay visible while the words are written.
"""

from __future__ import annotations

from datetime import date, datetime

import streamlit as st

import config
from data.provider import build_report, get_provider
from formatting import fmt_date, fmt_datetime_london
from models import EodReport, SectionKey
from ui import commentary as commentary_ui
from ui import sections as section_ui

st.set_page_config(
    page_title="EOD — Precious metals",
    layout="wide",
    initial_sidebar_state="expanded",
)

#: Section number, heading, commentary key and render callable, in report order.
SECTION_LAYOUT = (
    (1, "Client flows", SectionKey.CLIENT_FLOWS),
    (2, "Risk", SectionKey.RISK),
    (3, "Technicals", SectionKey.TECHNICALS),
    (4, "ETF holdings and flows", SectionKey.ETF_FLOWS),
    (5, "Open interest and positioning", SectionKey.POSITIONING),
    (6, "Physical inventories", SectionKey.PHYSICAL),
    (7, "Look ahead", SectionKey.LOOK_AHEAD),
)

#: Data column vs commentary column. Wide enough on the left for the tables.
SECTION_COLUMNS = (0.62, 0.38)


@st.cache_data(show_spinner="Building desk data…")
def load_report(report_date: date, author_name: str) -> EodReport:
    """One day's report. Cached per date, so re-renders are free."""
    return build_report(get_provider(), report_date, author_name)


def current_theme() -> str:
    """Chart palette to use, following the viewer's Streamlit theme."""
    try:
        return "dark" if st.context.theme.type == "dark" else "light"
    except (AttributeError, KeyError):
        return "light"


def render_sidebar() -> tuple[date, str]:
    """Report controls. Returns the chosen report date and author."""
    with st.sidebar:
        st.subheader("Report")
        report_date = st.date_input(
            "Report date",
            value=datetime.now(config.LONDON_TZ).date(),
            format="DD/MM/YYYY",
            key="report_date",
            help="London trading date. Mock data is deterministic per date.",
        )
        commentary_ui.ensure_loaded(report_date, default_author="")
        author = commentary_ui.render_author_input(report_date)

        st.divider()
        st.subheader("Commentary")
        commentary_ui.render_toolbar(report_date)
        st.caption(
            f"Drafts autosave to `commentary/{report_date:%Y-%m-%d}.json` "
            "whenever you leave a box."
        )

        st.divider()
        source = "MockDataProvider — fabricated" if config.USE_MOCK else "LiveDataProvider"
        st.caption(f"Data source: {source}")
    return report_date, author


def render_header(report: EodReport, report_date: date) -> None:
    st.title("Precious metals — end of day")
    st.caption(
        f"{report.header.report_label} · {fmt_date(report_date)} · "
        f"generated {fmt_datetime_london(report.header.generated_at_london)}"
    )
    commentary_ui.render_headline_input(report_date)
    section_ui.render_snapshot(report.header)
    commentary_ui.render_box(
        SectionKey.MARKET_OVERVIEW, report_date, "Market overview", height=140
    )


def render_section(
    number: int,
    heading: str,
    key: SectionKey,
    report: EodReport,
    report_date: date,
    theme: str,
) -> None:
    """One bordered section: data on the left, its commentary on the right."""
    with st.container(border=True):
        st.subheader(f"{number} · {heading}")
        data_column, commentary_column = st.columns(SECTION_COLUMNS, gap="large")
        with data_column:
            if key is SectionKey.CLIENT_FLOWS:
                section_ui.render_client_flows(report.client_flows, theme)
            elif key is SectionKey.RISK:
                section_ui.render_risk(report.risk)
            elif key is SectionKey.TECHNICALS:
                section_ui.render_technicals(report.technicals, theme)
            elif key is SectionKey.ETF_FLOWS:
                section_ui.render_etf(report.etf)
            elif key is SectionKey.POSITIONING:
                section_ui.render_positioning(report.positioning)
            elif key is SectionKey.PHYSICAL:
                section_ui.render_physical(report.physical)
            elif key is SectionKey.LOOK_AHEAD:
                section_ui.render_look_ahead(report.look_ahead)
        with commentary_column:
            label = next(
                box_label
                for box_key, box_label, _height in commentary_ui.COMMENTARY_BOXES
                if box_key is key
            )
            commentary_ui.render_box(key, report_date, label)


def main() -> None:
    report_date, author = render_sidebar()
    report = load_report(report_date, author)
    theme = current_theme()

    render_header(report, report_date)
    for number, heading, key in SECTION_LAYOUT:
        render_section(number, heading, key, report, report_date, theme)


main()
