"""Commentary editing, word-count guidance and JSON persistence.

Drafts are written to ``commentary/{YYYY-MM-DD}.json`` as a serialised
``Commentary`` model. Every box autosaves when the analyst moves off it, so a
browser refresh cannot lose work; the Save draft button is there for
reassurance rather than necessity.

Widget state lives in ``st.session_state`` under ``cmt_<section>`` keys. Buttons
mutate that state from ``on_click`` callbacks — Streamlit refuses writes to a
widget's key after the widget has been created in the same run, and callbacks
fire before the next run builds them.
"""

from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path

import streamlit as st

import config
from formatting import character_count, word_count
from models import Commentary, SectionKey

#: Commentary boxes in report order: key, heading, and the height of the box.
COMMENTARY_BOXES: tuple[tuple[SectionKey, str, int], ...] = (
    (SectionKey.MARKET_OVERVIEW, "Market overview", 150),
    (SectionKey.CLIENT_FLOWS, "Client flow commentary", 190),
    (SectionKey.RISK, "Risk commentary", 190),
    (SectionKey.TECHNICALS, "Technical commentary", 190),
    (SectionKey.ETF_FLOWS, "ETF commentary", 190),
    (SectionKey.POSITIONING, "Positioning commentary", 190),
    (SectionKey.PHYSICAL, "Physical commentary", 190),
    (SectionKey.LOOK_AHEAD, "What we are watching", 190),
)

_HEADLINE_KEY = "cmt_headline"
_AUTHOR_KEY = "cmt_author"
_LOADED_DATE_KEY = "cmt_loaded_date"
_STATUS_KEY = "cmt_status"


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------


def commentary_path(report_date: date) -> Path:
    return config.COMMENTARY_DIR / f"{report_date:%Y-%m-%d}.json"


def load_commentary(report_date: date) -> Commentary | None:
    """Read a saved draft, or return None when the analyst has not started."""
    path = commentary_path(report_date)
    if not path.exists():
        return None
    try:
        return Commentary.model_validate(json.loads(path.read_text(encoding="utf-8")))
    except (json.JSONDecodeError, ValueError):
        # A corrupt draft must not take the app down; the analyst starts fresh.
        return None


def save_commentary(commentary: Commentary) -> Path:
    """Write a draft, stamping the save time in London."""
    config.COMMENTARY_DIR.mkdir(parents=True, exist_ok=True)
    stamped = commentary.model_copy(
        update={"saved_at_london": datetime.now(config.LONDON_TZ)}
    )
    path = commentary_path(stamped.report_date)
    path.write_text(
        json.dumps(stamped.model_dump(mode="json"), indent=2), encoding="utf-8"
    )
    return path


def previous_commentary(report_date: date) -> tuple[date, Commentary] | None:
    """Most recent saved draft strictly before ``report_date``.

    "Yesterday's commentary" in practice means the last session the analyst
    wrote up, which after a weekend or a holiday is not the previous day.
    """
    if not config.COMMENTARY_DIR.exists():
        return None
    candidates: list[date] = []
    for path in config.COMMENTARY_DIR.glob("*.json"):
        try:
            candidates.append(date.fromisoformat(path.stem))
        except ValueError:
            continue
    earlier = sorted(day for day in candidates if day < report_date)
    if not earlier:
        return None
    previous_day = earlier[-1]
    document = load_commentary(previous_day)
    return (previous_day, document) if document else None


# ---------------------------------------------------------------------------
# Session state
# ---------------------------------------------------------------------------


def _box_key(section: SectionKey) -> str:
    return f"cmt_{section.value}"


def ensure_loaded(report_date: date, default_author: str) -> None:
    """Load the day's draft into session state, once per report date."""
    if st.session_state.get(_LOADED_DATE_KEY) == report_date.isoformat():
        return
    document = load_commentary(report_date) or Commentary(
        report_date=report_date, author_name=default_author
    )
    for section, _label, _height in COMMENTARY_BOXES:
        st.session_state[_box_key(section)] = getattr(document, section.value)
    st.session_state[_HEADLINE_KEY] = document.headline
    st.session_state[_AUTHOR_KEY] = document.author_name or default_author
    st.session_state[_LOADED_DATE_KEY] = report_date.isoformat()
    st.session_state[_STATUS_KEY] = (
        f"Loaded draft saved {document.saved_at_london:%H:%M} London"
        if document.saved_at_london
        else "New draft"
    )


def current_commentary(report_date: date) -> Commentary:
    """Build a ``Commentary`` from whatever is in the boxes right now."""
    return Commentary(
        report_date=report_date,
        author_name=st.session_state.get(_AUTHOR_KEY, ""),
        headline=st.session_state.get(_HEADLINE_KEY, ""),
        saved_at_london=None,
        **{
            section.value: st.session_state.get(_box_key(section), "")
            for section, _label, _height in COMMENTARY_BOXES
        },
    )


def _autosave(report_date: date) -> None:
    save_commentary(current_commentary(report_date))
    st.session_state[_STATUS_KEY] = (
        f"Autosaved {datetime.now(config.LONDON_TZ):%H:%M:%S} London"
    )


# ---------------------------------------------------------------------------
# Widgets
# ---------------------------------------------------------------------------


def render_box(section: SectionKey, report_date: date, label: str, height: int = 190) -> str:
    """One commentary box with its placeholder prompt and length guide."""
    st.text_area(
        label,
        key=_box_key(section),
        height=height,
        placeholder=config.COMMENTARY_PLACEHOLDERS[section.value],
        on_change=_autosave,
        args=(report_date,),
        label_visibility="visible",
    )
    text = st.session_state.get(_box_key(section), "")
    st.caption(_length_guide(text))
    return text


def _length_guide(text: str) -> str:
    """Word and character count with a soft nudge towards the house length."""
    words = word_count(text)
    characters = character_count(text)
    low, high = config.COMMENTARY_WORD_TARGET
    if words == 0:
        return f"Empty — omitted from the email. Aim {low}–{high} words."
    if words < low:
        note = f"a little short of the {low}–{high} word guide"
    elif words > high:
        note = f"over the {low}–{high} word guide"
    else:
        note = "within the guide"
    return f"{words} words · {characters} characters · {note}"


def render_headline_input(report_date: date) -> str:
    st.text_input(
        "Headline",
        key=_HEADLINE_KEY,
        placeholder=(
            "One line, the way you would say it to the head of desk: what "
            "happened and why it matters."
        ),
        on_change=_autosave,
        args=(report_date,),
    )
    return st.session_state.get(_HEADLINE_KEY, "")


def render_author_input(report_date: date) -> str:
    st.text_input(
        "Author",
        key=_AUTHOR_KEY,
        placeholder="Name on the report",
        on_change=_autosave,
        args=(report_date,),
    )
    return st.session_state.get(_AUTHOR_KEY, "")


# ---------------------------------------------------------------------------
# Toolbar
# ---------------------------------------------------------------------------


def _save_draft_cb(report_date: date) -> None:
    path = save_commentary(current_commentary(report_date))
    st.session_state[_STATUS_KEY] = f"Saved to {path.name}"


def _load_previous_cb(report_date: date) -> None:
    found = previous_commentary(report_date)
    if not found:
        st.session_state[_STATUS_KEY] = "No earlier commentary found"
        return
    previous_day, document = found
    for section, _label, _height in COMMENTARY_BOXES:
        st.session_state[_box_key(section)] = getattr(document, section.value)
    st.session_state[_HEADLINE_KEY] = document.headline
    # Persist straight away, so a refresh keeps the loaded starting point.
    save_commentary(current_commentary(report_date))
    st.session_state[_STATUS_KEY] = f"Loaded {previous_day:%d %b %Y} as a starting point"



def _clear_all_cb(report_date: date) -> None:
    for section, _label, _height in COMMENTARY_BOXES:
        st.session_state[_box_key(section)] = ""
    st.session_state[_HEADLINE_KEY] = ""
    save_commentary(current_commentary(report_date))
    st.session_state[_STATUS_KEY] = "Cleared"


def render_toolbar(report_date: date) -> None:
    """Save / load / clear buttons plus the last-action status line."""
    st.button(
        "Save draft",
        on_click=_save_draft_cb,
        args=(report_date,),
        width="stretch",
        help="Commentary also autosaves whenever you leave a box.",
    )
    st.button(
        "Load yesterday's commentary",
        on_click=_load_previous_cb,
        args=(report_date,),
        width="stretch",
        help="Copies the most recent earlier draft into today's boxes.",
    )
    st.button(
        "Clear all",
        on_click=_clear_all_cb,
        args=(report_date,),
        width="stretch",
        help="Empties every box for this date.",
    )
    status = st.session_state.get(_STATUS_KEY)
    if status:
        st.caption(status)
