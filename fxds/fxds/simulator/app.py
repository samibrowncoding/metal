"""Streamlit front end for the trading simulator - Practical A.

Replaces the book's Excel sheet:

===========================  ==================================================
Excel original               Here
===========================  ==================================================
Named input cells            Sidebar widgets
Go/Pause and Stop buttons    Streamlit buttons over ``st.session_state``
``Application.OnTime``       ``st.rerun()`` after a sleep of the tick interval
Grouped Option Buttons       Buy / Sell / Do Nothing buttons
Auto-resizing scatter chart  Plotly charts redrawn from the recorded history
===========================  ==================================================

Run with::

    streamlit run fxds/simulator/app.py

Everything the app does is available headlessly on
:class:`~fxds.simulator.engine.Simulator`, so nothing here is load-bearing for the
tests or for notebook 02. This module is the front end and nothing else - all the
trading logic lives in ``market.py``, ``trader.py`` and ``engine.py``.
"""

from __future__ import annotations

import time

import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

from fxds.plotting import ALERT, MUTED, PLOTLY_LAYOUT, PRIMARY, SECONDARY, TERTIARY
from fxds.simulator import (
    LimitBreach,
    Market,
    MarketParticipants,
    ParticipantBias,
    RiskLimits,
    Simulator,
    SpotProcess,
    Trader,
    TraderAction,
)


def build_simulator(config: dict) -> Simulator:
    """Construct a simulator from the sidebar settings."""
    market = Market(
        initial_spot=config["initial_spot"],
        spot_increment=config["spot_increment"],
        bid_offer_spread=config["spread"],
        process=config["process"],
        volatility=config["volatility"],
    )
    trader = Trader(
        limits=RiskLimits(
            max_position=config["max_position"],
            stop_loss=config["stop_loss"],
            profit_target=config["profit_target"],
        ),
        trade_notional=config["trade_notional"],
    )
    participants = None
    if config["price_making"]:
        participants = MarketParticipants(
            buy_probability=config["buy_prob"],
            sell_probability=config["sell_prob"],
            bias=config["bias"],
            bias_strength=config["bias_strength"],
            notional_choices=config["notionals"],
        )
    return Simulator(market=market, trader=trader, participants=participants,
                     seed=config["seed"])


def session_charts(frame) -> go.Figure:
    """Spot with the two-way price, position and P&L, stacked and sharing an x axis."""
    fig = make_subplots(
        rows=3, cols=1, shared_xaxes=True, vertical_spacing=0.06,
        row_heights=[0.46, 0.27, 0.27],
        subplot_titles=("Spot (CCY2 per CCY1)", "Position (CCY1 notional)", "P&L (CCY2)"),
    )

    fig.add_trace(go.Scatter(x=frame["step"], y=frame["offer"], name="offer",
                             line=dict(color=MUTED, width=1, dash="dot")), row=1, col=1)
    fig.add_trace(go.Scatter(x=frame["step"], y=frame["bid"], name="bid",
                             line=dict(color=MUTED, width=1, dash="dot"),
                             fill="tonexty", fillcolor="rgba(107,114,128,0.12)"), row=1, col=1)
    fig.add_trace(go.Scatter(x=frame["step"], y=frame["mid"], name="mid",
                             line=dict(color=PRIMARY, width=2)), row=1, col=1)

    fig.add_trace(go.Scatter(x=frame["step"], y=frame["position"], name="position",
                             line=dict(color=SECONDARY, width=2, shape="hv")), row=2, col=1)
    fig.add_hline(y=0, line=dict(color=MUTED, width=0.8), row=2, col=1)

    pnl_final = frame["pnl"].iloc[-1] if len(frame) else 0.0
    fig.add_trace(go.Scatter(x=frame["step"], y=frame["pnl"], name="P&L",
                             line=dict(color=TERTIARY if pnl_final >= 0 else ALERT, width=2),
                             fill="tozeroy"), row=3, col=1)
    fig.add_hline(y=0, line=dict(color=MUTED, width=0.8), row=3, col=1)

    # Take the house style but drop the keys that would clash with the per-figure
    # settings below - update_layout raises on a duplicated keyword.
    layout = {
        k: v for k, v in PLOTLY_LAYOUT.items()
        if k not in ("xaxis", "yaxis", "title", "margin", "hovermode")
    }
    fig.update_layout(
        **layout,
        height=680,
        showlegend=False,
        hovermode="x unified",
        margin=dict(l=60, r=20, t=40, b=40),
    )
    fig.update_xaxes(title_text="Tick", row=3, col=1)
    return fig


def main() -> None:
    """Render the app."""
    st.set_page_config(page_title="FX Trading Simulator — Practical A", layout="wide")
    st.title("Trading simulator")
    st.caption(
        "Practical A from *FX Derivatives Trader School* (Ch. 3). "
        "Task A ticks a mid; Task B adds a two-way price you can trade on; "
        "Task C adds market participants who trade on **you**."
    )

    # ---- sidebar: the book's named input cells ----
    sb = st.sidebar
    sb.header("Market")
    initial_spot = sb.number_input("Initial spot", value=1.3000, step=0.0001, format="%.4f")
    process = SpotProcess.VOLATILITY if sb.toggle(
        "Volatility-based spot", value=False,
        help="Extension: geometric Brownian motion instead of a fixed increment.",
    ) else SpotProcess.FIXED_INCREMENT

    spot_increment = sb.number_input("Spot increment", value=0.0005, step=0.0001,
                                     format="%.4f", disabled=process is SpotProcess.VOLATILITY)
    volatility = sb.slider("Volatility (annualised)", 0.01, 0.60, 0.10, 0.01,
                           disabled=process is SpotProcess.FIXED_INCREMENT)
    spread = sb.number_input("Bid–offer spread", value=0.0010, step=0.0001, format="%.4f")
    tick_seconds = sb.slider(
        "Seconds between ticks", 0.1, 5.0, 1.0, 0.1,
        help="The book suggests starting at five seconds while the interactions "
             "between market, position and P&L become familiar.",
    )
    seed = sb.number_input("Random seed", value=0, step=1,
                           help="Same seed replays the same session exactly.")

    sb.header("Trader")
    trade_notional = sb.number_input("Trade size", value=1.0, step=1.0, min_value=0.01)
    use_limits = sb.toggle("Risk limits and P&L targets", value=False,
                           help="Extension 1. Start them in line, then push them out of line.")
    max_position = sb.number_input("Max position", value=10.0, step=1.0) if use_limits else None
    stop_loss = sb.number_input("Stop loss (negative)", value=-0.05, step=0.01,
                                format="%.4f") if use_limits else None
    profit_target = sb.number_input("Profit target", value=0.05, step=0.01,
                                    format="%.4f") if use_limits else None

    sb.header("Market participants (Task C)")
    price_making = sb.toggle("Enable price making", value=True)
    buy_prob = sb.slider("P(market buys)", 0.0, 0.5, 0.15, 0.01, disabled=not price_making)
    sell_prob = sb.slider("P(market sells)", 0.0, 0.5, 0.15, 0.01, disabled=not price_making)
    bias = ParticipantBias(sb.selectbox(
        "Flow bias", [b.value for b in ParticipantBias], index=0, disabled=not price_making,
        help="Extension 3: participants whose direction depends on where spot has moved.",
    ))
    bias_strength = sb.slider("Bias strength", 0.0, 1.0, 0.5, 0.05,
                              disabled=not price_making or bias is ParticipantBias.INDEPENDENT)
    varied = sb.toggle("Variable trade sizes", value=False, disabled=not price_making,
                       help="Extension 4: in practice larger size trades further from mid.")

    config = dict(
        initial_spot=initial_spot, spot_increment=spot_increment, spread=spread,
        process=process, volatility=volatility, seed=int(seed),
        trade_notional=trade_notional, max_position=max_position,
        stop_loss=stop_loss, profit_target=profit_target,
        price_making=price_making, buy_prob=buy_prob, sell_prob=sell_prob,
        bias=bias, bias_strength=bias_strength,
        notionals=(1.0, 3.0, 5.0) if varied else (1.0,),
    )

    # Rebuild whenever the settings change - the equivalent of the book's Stop
    # button clearing the sheet before a new run.
    if "config" not in st.session_state or st.session_state.config != config:
        st.session_state.config = config
        st.session_state.sim = build_simulator(config)
        st.session_state.running = False

    sim: Simulator = st.session_state.sim

    # ---- controls: the book's Go/Pause and Stop buttons ----
    go_col, stop_col, buy_col, sell_col, step_col = st.columns([1, 1, 1, 1, 1])
    if go_col.button("Go / Pause", use_container_width=True):
        st.session_state.running = not st.session_state.running
    if stop_col.button("Stop", use_container_width=True):
        sim.reset()
        st.session_state.running = False
    buy_clicked = buy_col.button("Buy at offer", use_container_width=True,
                                 disabled=sim.stopped is not LimitBreach.NONE)
    sell_clicked = sell_col.button("Sell at bid", use_container_width=True,
                                   disabled=sim.stopped is not LimitBreach.NONE)
    step_clicked = step_col.button("Step once", use_container_width=True,
                                   disabled=sim.stopped is not LimitBreach.NONE)

    if buy_clicked:
        sim.set_action(TraderAction.BUY)
    if sell_clicked:
        sim.set_action(TraderAction.SELL)

    # A manual click ticks immediately, so the trade happens on the next tick and
    # the effect is visible straight away rather than waiting for the timer.
    if (buy_clicked or sell_clicked or step_clicked) and sim.stopped is LimitBreach.NONE:
        sim.step()

    # ---- live numbers ----
    price = sim.market.price
    m1, m2, m3, m4, m5, m6 = st.columns(6)
    # Bid and offer get their own columns: a combined "1.2995 / 1.3005" is wide
    # enough that Streamlit truncates it at this column count.
    m1.metric("Bid", f"{price.bid:.4f}", help="Sell here — you give the bid.")
    m2.metric("Offer", f"{price.offer:.4f}", help="Buy here — you pay the offer.")
    m3.metric("Mid", f"{sim.market.mid:.4f}",
              delta=f"{sim.market.mid - sim.market.initial_spot:+.4f}")
    m4.metric("Position", f"{sim.trader.position:+,.0f}")
    m5.metric("P&L", f"{sim.trader.pnl:+.4f}")
    m6.metric("Tick", f"{sim.market.step_count}")

    if sim.stopped is not LimitBreach.NONE:
        st.warning(f"Session stopped: **{sim.stopped.value}**. Press Stop to start again.")
        st.session_state.running = False

    frame = sim.to_frame()
    if len(frame):
        st.plotly_chart(session_charts(frame), use_container_width=True)

        paid, earned = sim.trader.spread_paid, sim.trader.spread_earned
        s1, s2, s3 = st.columns(3)
        s1.metric("Spread paid (taking)", f"{paid:.4f}", delta=f"{sim.trader.trades_taken} trades",
                  delta_color="off")
        s2.metric("Spread earned (making)", f"{earned:.4f}", delta=f"{sim.trader.trades_made} trades",
                  delta_color="off")
        s3.metric("Net spread", f"{earned - paid:+.4f}")

        st.caption(
            "**The lesson.** Every trade you initiate costs half the spread, whichever "
            "way you go — so a price taker is structurally negative carry and "
            "over-trading is a slow bleed. Every trade the market does with you *earns* "
            "half the spread, but you do not choose the position that comes with it. "
            "Notebook 02 runs a thousand sessions of each and plots the two P&L "
            "distributions."
        )
    else:
        st.info("Press **Go / Pause** to start the market ticking, or **Step once** to advance a single tick.")

    # ---- the clock ----
    # The Excel original schedules the next tick with Application.OnTime. Streamlit
    # has no timer, so we sleep and rerun: the script re-executes top to bottom and
    # the simulator state survives in st.session_state.
    if st.session_state.running and sim.stopped is LimitBreach.NONE:
        sim.step()
        time.sleep(tick_seconds)
        st.rerun()


if __name__ == "__main__":
    main()
