#!/usr/bin/env python3
"""Email the volunteer inbox the attendee list for today's lunch.

Intended to be run once a day by a PythonAnywhere scheduled task, a few hours
before the lunch starts (lunch is at 12:00, so ~09:00 local time).

It exits quietly on days with no lunch, so it is safe to run daily. It also
records each send, so running it more than once on the same day will not send
a duplicate.

Usage:
    python send_lunch_summary.py                # today's lunch
    python send_lunch_summary.py 2026-08-08     # a specific date (testing)
    python send_lunch_summary.py 2026-08-08 --force   # ignore the duplicate guard
"""
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import app, send_lunch_summary


def main():
    args = [a for a in sys.argv[1:] if a != '--force']
    force = '--force' in sys.argv

    target_date = None
    if args:
        try:
            target_date = datetime.strptime(args[0], '%Y-%m-%d').date()
        except ValueError:
            print(f"Invalid date '{args[0]}' - expected YYYY-MM-DD")
            return 1

    with app.app_context():
        result = send_lunch_summary(target_date=target_date, force=force)

    print(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] {result}")
    return 0


if __name__ == '__main__':
    sys.exit(main())
