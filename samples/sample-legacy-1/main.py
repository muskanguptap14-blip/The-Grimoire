#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Tally Keeper: a tiny shop-counter ledger written for Python 2.5 in 2008."""
import os
import sys


def ask(prompt):
    """Interactive helper kept from the original shell front end (not used by the demo)."""
    return raw_input(prompt)


def load_sales():
    sales = {}
    for i in xrange(1, 6):
        sales["item%d" % i] = i * 3
    return sales


def total(sales):
    if not sales.has_key("item1"):
        raise ValueError("no item1 in sales")
    amount = 0
    for name, qty in sales.iteritems():
        amount = amount + qty
    return amount


def parse_quantity(text):
    try:
        return int(text)
    except ValueError, e:
        print "bad quantity: %s" % e
        return 0


def report_mode():
    # Unix permission bits, written as an old-style octal literal.
    return 0755


def main():
    sales = load_sales()
    print "TALLY KEEPER"
    print "total units:", total(sales)
    print "bad input gives", parse_quantity("abc")
    print "report mode: %o" % report_mode()
    if total(sales) <> 45:
        sys.exit(1)
    print "TALLY KEEPER ALIVE"


if __name__ == "__main__":
    main()
