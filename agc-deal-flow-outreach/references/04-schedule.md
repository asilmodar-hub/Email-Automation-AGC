# The automatic rhythm

On the Setup tab the user picks how often a round is prepared: only when they
start it, every quarter, every half-year, every year, or once on a date. The
setting is saved by the app the moment it changes. What is left for you is to
make the Claude app's scheduler match it. That is what a `schedule` job asks.

By default automatic means *prepared*, not *sent*: on the due date a round is
put together and the review screen opens, and the user presses Send. The user
can switch on "Send without my review" on the same tab; then the app sends the
prepared round by itself. Either way the sending is not yours to do, and the
scheduler task is the same.

## Doing a `schedule` job

The job's `payload` tells you everything:

| `action` | Do this |
|---|---|
| `recurring` | The task runs on `cron` (five fields, local time) |
| `once` | The task runs once at `fire_at` (ISO time with offset) |
| `off` | The task must not run automatically |

There is one task for this tool, with the id in `task_id`
(`agc-deal-flow-outreach`). Never create a second one.

1. List the scheduled tasks and look for that id.
2. **If it exists**, update it: set `cronExpression` to `cron`, or `fireAt` to
   `fire_at`, and make sure it is enabled. For `off`, disable it; do not
   delete it.
3. **If it does not exist** and the action is not `off`, create it with
   `taskId` = `task_id`, the `cron` or `fire_at`, `title` and `description`
   from the payload, and `prompt` from the payload **word for word**. The
   prompt is written so that a fresh session with no memory of this one knows
   what to do and knows not to send.
4. Hand back `{"ok": true}`. The Setup tab then shows "Registered".

If the scheduler refuses, or this Claude app has no scheduler tools, hand back
`{"ok": false, "error": "<one plain sentence>"}`. The Setup tab shows that
sentence with a button to try again. Do not fall back to another scheduling
mechanism (Windows Task Scheduler, a loop, a reminder): the user chose a
setting on a screen and should see honestly whether it took.

The first time you register a rhythm in a conversation, tell the user one
thing the screen also says: the scheduler runs while the Claude app is open,
and if it is closed on the day, the round is prepared the next time they open
it.

## When the task fires

A fresh session receives the prompt and uses this skill in scheduled mode. See
"Scheduled run" in `SKILL.md`: `scripts\outreach.cmd start --scheduled`, a
one-line note that the round is ready for review, then `wait`. Nothing is
sent.

A recurring task keeps its rhythm by itself. A one-time task disables itself
after it has run; the Setup tab then shows that no run is upcoming until the
user picks a new date.
