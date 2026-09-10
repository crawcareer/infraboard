"""Recurring task reset engine.

When a recurring HireEvent's due date arrives (or passes), it rolls
forward to a new due date (its current due date plus its recurrence
interval) and reverts to "pending" status -- the reset is driven purely
by the calendar, not by whether the task was ever marked done, matching
how a compliance-style task like "renew driver's license every 4 years"
should behave: reminders go out before the deadline regardless, and the
deadline itself is what advances, not completion. assigned_to carries
over untouched.

Shared by the standalone process_recurring_tasks.py script (currently
the only caller).
"""

import calendar
from datetime import date


def add_interval(d, interval, unit):
    """Add `interval` months or years to date `d`, clamping the day of
    month if it overflows the target month's length (e.g. Jan 31 plus 1
    month lands on Feb 28/29, not an invalid Feb 31)."""
    months_to_add = interval * 12 if unit == "years" else interval
    month_index = d.month - 1 + months_to_add
    year = d.year + month_index // 12
    month = month_index % 12 + 1
    day = min(d.day, calendar.monthrange(year, month)[1])
    return d.replace(year=year, month=month, day=day)


def process_due_recurring_tasks(today=None):
    """Reset every recurring HireEvent whose due date is today or
    earlier, advancing it (possibly through more than one cycle, e.g. if
    the reset job didn't run for a while) until its due date is in the
    future. Returns the number of tasks reset."""
    from app.extensions import db
    from app.models import HireEvent

    today = today or date.today()
    due_tasks = HireEvent.query.filter(
        HireEvent.is_recurring.is_(True),
        HireEvent.due_date.isnot(None),
        HireEvent.due_date <= today,
    ).all()

    for task in due_tasks:
        while task.due_date <= today:
            task.due_date = add_interval(task.due_date, task.recurrence_interval, task.recurrence_unit)
        task.status = "pending"

    db.session.commit()
    return len(due_tasks)
