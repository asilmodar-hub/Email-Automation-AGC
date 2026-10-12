"""The automatic rhythm: when the next round is due, and what to tell the
scheduler.

The UI saves a mode, a start date and a time. From those this module works out
the next run for display, and the one instruction Claude passes to the Claude
app's scheduler: a cron rule for a repeating rhythm, a single moment for a
picked date, or "off".

Automatic never means sending. On the due date the round is drafted and the
review screen opens; a person presses Send.
"""
import datetime as dt

TASK_ID = "agc-deal-flow-outreach"
STEP_MONTHS = {"quarterly": 3, "half_yearly": 6, "yearly": 12}
LABELS = {"manual": "Only when I start it", "quarterly": "Every quarter",
          "half_yearly": "Every half-year", "yearly": "Every year", "date": "Once, on a date I pick"}


def _parse(schedule):
    try:
        day = dt.date.fromisoformat(schedule.get("start_date") or "")
        hour, minute = (int(p) for p in (schedule.get("time") or "09:00").split(":")[:2])
        return dt.datetime(day.year, day.month, day.day, hour, minute)
    except (ValueError, TypeError):
        return None


def _add_months(when, months):
    index = when.month - 1 + months
    return when.replace(year=when.year + index // 12, month=index % 12 + 1)


def next_run(schedule, now=None):
    """The next moment a round is prepared, or None."""
    now = now or dt.datetime.now()
    mode = schedule.get("mode", "manual")
    start = _parse(schedule)
    if mode == "manual" or start is None:
        return None
    if mode == "date":
        return start if start > now else None
    # A day after the 28th does not exist in every month; the rhythm runs on the 28th.
    when = start.replace(day=min(start.day, 28))
    step = STEP_MONTHS[mode]
    while when <= now:
        when = _add_months(when, step)
    return when


def plan(schedule, now=None):
    """What the scheduler should hold: {action, cron | fire_at, next_run, label, problem}.

    action is 'recurring', 'once' or 'off'."""
    mode = schedule.get("mode", "manual")
    out = {"task_id": TASK_ID, "mode": mode, "label": LABELS.get(mode, mode), "action": "off",
           "cron": "", "fire_at": "", "next_run": "", "problem": ""}
    if mode == "manual":
        return out
    start = _parse(schedule)
    if start is None:
        out["problem"] = "Pick a date and time for the first run."
        return out
    upcoming = next_run(schedule, now)
    if upcoming is None:
        out["problem"] = "The date picked is in the past."
        return out
    out["next_run"] = upcoming.isoformat(timespec="minutes")
    if mode == "date":
        out["action"] = "once"
        out["fire_at"] = upcoming.astimezone().isoformat(timespec="seconds")
        return out
    step = STEP_MONTHS[mode]
    months = sorted({(start.month - 1 + k * step) % 12 + 1 for k in range(12 // step)})
    out["action"] = "recurring"
    out["cron"] = "%d %d %d %s *" % (start.minute, start.hour, min(start.day, 28),
                                     ",".join(str(m) for m in months))
    return out


def round_label(when=None):
    when = when or dt.datetime.now()
    return "Q%d %d" % ((when.month - 1) // 3 + 1, when.year)
