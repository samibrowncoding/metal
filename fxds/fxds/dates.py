"""Business days, spot dates and tenor expiry dates - Practical D (Ch. 10).

Implements Practical D: business day increment and decrement, spot date from horizon
(T+2) and back, and ``expiry_from_tenor`` handling ON, nW, nM and nY per the rules
set out in Chapter 10.

Weekends only - there is no holiday calendar here, matching the practical. The
functions take an injectable calendar so one can be added later without reworking
the call sites. The end-end and month-overflow special cases that Chapter 10
describes but Practical D skips are marked as TODOs and documented in
``notes/deviations.md``.
"""
