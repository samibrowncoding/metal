"""The assembled volatility surface - Practicals D, E and F combined.

The book builds the ATM curve and the volatility smile separately and never joins
them. This module does:

    tenor dates (Practical D)
        -> ATM curve with day weights (Practical E)
            -> Malz smile per tenor (Practical F)
                -> vol(expiry_date, strike)

That chain is the payoff for the whole first half of the book. It also carries real
simplifications, listed in full in the module's ``SIMPLIFICATIONS`` constant and in
``notes/deviations.md``. Read them before trusting a number out of here.
"""
