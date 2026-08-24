"""Export the data contract for the Rust implementation.

Writes, into ``schema/``:

* ``<ModelName>.schema.json`` — JSON Schema for every model in
  ``models.CONTRACT_MODELS``, straight from ``model_json_schema()``.
* ``index.json`` — the model list plus the report date used, so the handoff
  bundle is self-describing.
* ``sample_payload.json`` — one full day of fabricated data serialised from
  ``EodReport``, to deserialise against.
* ``sample_commentary.json`` — a filled ``Commentary`` document, matching what
  the app writes to ``commentary/{YYYY-MM-DD}.json``.

Usage::

    python export_schema.py                     # today, London
    python export_schema.py --date 2026-08-24   # a specific session
    python export_schema.py --out /tmp/schema   # somewhere else
"""

from __future__ import annotations

import argparse
import json
from datetime import date, datetime
from pathlib import Path

import config
from data.provider import build_report, get_provider
from models import CONTRACT_MODELS, Commentary, EodReport

SAMPLE_AUTHOR = "A. Analyst"

SAMPLE_COMMENTARY_TEXT: dict[str, str] = {
    "headline": "Gold holds the range into the London close as central bank bids absorb producer selling.",
    "market_overview": (
        "Gold spent the session in a tight range, twice failing at the 20-session high before "
        "settling mid-range on the auction. Silver led on the way up and gave most of it back, "
        "leaving the ratio broadly unchanged. The PGMs were quiet, with platinum better bid on "
        "thin volume."
    ),
    "client_flows": (
        "Two-way in gold with a modest net client buy, driven by a central bank on the dips and "
        "an asset manager switch out of ETF into allocated. Producers were the main sellers into "
        "strength. Silver flow was industrial and one-directional."
    ),
    "risk": (
        "The book finished modestly long delta in gold and short in palladium. P&L was carried by "
        "client spread rather than direction. Gold delta notional utilisation is the line to watch "
        "into the roll."
    ),
    "technicals": (
        "Gold remains above the 50-day and the trend label is unchanged. The 20-session high is "
        "the level that matters; a close through it opens the round number above. Implied is "
        "still trading over realised, which caps the appetite for gamma here."
    ),
    "etf_flows": (
        "A small creation day across the gold funds, the fourth in five sessions, which sits "
        "awkwardly with the flat price action. Silver holdings were unchanged. PGM funds continue "
        "to bleed slowly."
    ),
    "positioning": (
        "Open interest rose on the day with volume close to the 20-day average, consistent with "
        "new length rather than short covering. The COT is a week stale but shows managed money "
        "already long. EFP is inside its range."
    ),
    "physical": (
        "COMEX registered stocks were little changed. The Shanghai premium remains positive but "
        "off the highs, and lease rates in the PGMs are still elevated, which is the clearest "
        "sign of physical tightness in the complex."
    ),
    "look_ahead": (
        "US CPI is the event that matters; the first notice day for the front gold contract falls "
        "inside the same window, so expect the roll to dominate the screen either side of it. "
        "Watch for reduced Shanghai liquidity later in the month."
    ),
}


def export(report_date: date, out_dir: Path) -> list[Path]:
    """Write schema files and sample payloads; return what was written."""
    out_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []

    for model in CONTRACT_MODELS:
        path = out_dir / f"{model.__name__}.schema.json"
        path.write_text(
            json.dumps(model.model_json_schema(), indent=2, sort_keys=False) + "\n",
            encoding="utf-8",
        )
        written.append(path)

    provider = get_provider()
    report: EodReport = build_report(provider, report_date, SAMPLE_AUTHOR)
    payload_path = out_dir / "sample_payload.json"
    payload_path.write_text(
        json.dumps(report.model_dump(mode="json"), indent=2) + "\n", encoding="utf-8"
    )
    written.append(payload_path)

    commentary = Commentary(
        report_date=report_date,
        author_name=SAMPLE_AUTHOR,
        saved_at_london=report.header.generated_at_london,
        **SAMPLE_COMMENTARY_TEXT,
    )
    commentary_path = out_dir / "sample_commentary.json"
    commentary_path.write_text(
        json.dumps(commentary.model_dump(mode="json"), indent=2) + "\n", encoding="utf-8"
    )
    written.append(commentary_path)

    index_path = out_dir / "index.json"
    index_path.write_text(
        json.dumps(
            {
                "generated_from": "eod_report/models.py",
                "report_date": report_date.isoformat(),
                "provider": type(provider).__name__,
                "root_model": EodReport.__name__,
                "models": [model.__name__ for model in CONTRACT_MODELS],
                "sample_payload": payload_path.name,
                "sample_commentary": commentary_path.name,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    written.append(index_path)
    return written


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--date",
        type=lambda value: datetime.strptime(value, "%Y-%m-%d").date(),
        default=datetime.now(config.LONDON_TZ).date(),
        help="Report date to fabricate, YYYY-MM-DD (default: today, London).",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=config.SCHEMA_DIR,
        help="Output directory (default: eod_report/schema).",
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    written = export(args.date, args.out)
    print(f"Wrote {len(written)} files to {args.out} for {args.date:%Y-%m-%d}:")
    for path in written:
        print(f"  {path.name} ({path.stat().st_size:,} bytes)")


if __name__ == "__main__":
    main()
