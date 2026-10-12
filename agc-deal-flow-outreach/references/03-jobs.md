# How jobs travel between the screen and you

## The loop

```
scripts\outreach.cmd wait            blocks until there is a job, prints it, exits
   read the details file
   write the result file
scripts\outreach.cmd submit <job>    hands it back, prints the app's answer
scripts\outreach.cmd wait            and again
```

`wait` prints something like:

```
JOB 3f9a12c0  type=rewrite
Details: C:\Users\<user>\AppData\Local\AGC-DealFlow\jobs\3f9a12c0.json
The reviewer asked for a change to the email for Anna Huber:
  "erwähne, dass wir uns im Mai in Wien getroffen haben"
Read references/01-rewriting.md, then the details file.
Result file: C:\Users\<user>\AppData\Local\AGC-DealFlow\jobs\3f9a12c0.result.json   shape: {"drafts": [{"contact_id", "body"}]}
Then: outreach submit 3f9a12c0
Afterwards run 'outreach wait' again.
```

or a single line starting with `CLOSED` when the app is no longer running.

## Files

- **Details file**: the whole job as JSON. Everything you need is under
  `payload`. Read it with your file tool.
- **Result file**: you create it at the path `wait` printed, as UTF-8 JSON.
  `submit <job>` reads that path; `submit <job> <other file>` reads another.

## What is in a job

**`rewrite`** `payload`: `contact_id`, `note_from_user`, `email_now`,
`master_email`, `greeting`, `subject`, `contact` (the row), `sender`, `kind`
(`round` or `followup`). See `01-rewriting.md`.

Result: `{"drafts": [{"contact_id", "body"}]}`, with `"subject"` added only if
the note asked for one. `body` is the whole email.

The app answers:

```json
{"ok": true, "problems": [], "failed_checks": ["Uses du, but the list says Sie."], "hint": "..."}
```

`failed_checks` is what the reviewer now sees flagged on that email. The job
is closed either way. `"ok": false` with `problems` means the result could not
be used at all (no body, wrong contact): correct it and submit again.

**`classify`** `payload`: `outcomes` (the allowed values) and `answers`, each
with `round_id`, `contact_id`, `name`, `company`, `our_subject`, `our_email`,
`matched_by` and `messages` (`received`, `subject`, `text`). See
`02-replies.md`.

Result: `{"answers": [{"round_id", "contact_id", "outcome", "summary",
"quote", "next_step"}]}`. Answer: `{"ok", "problems", "still_to_classify"}`.
Answers can be handed back in several submits; the job is done when
`still_to_classify` is empty.

**`schedule`** `payload`: `task_id`, `mode`, `label`, `action` (`recurring`,
`once` or `off`), `cron`, `fire_at`, `next_run`, `prompt`, `title`,
`description`. Result: `{"ok": true}` or `{"ok": false, "error": "..."}`.
See `04-schedule.md`.

## Good to know

- **A job you were given but did not finish is given to you again** the next
  time you `wait`, even after the app or the session restarted. Handing back
  the same result twice is harmless.
- **Several jobs can queue.** The reviewer may ask for changes to three emails
  in a row. You get them one at a time, oldest first.
- **`submit` exits with 1** when the answer has `"ok": false`. That is the
  app telling you to fix something, not a crash.
- **A job that cannot be done** is closed with
  `scripts\outreach.cmd fail <job> "<why, one sentence>"`, so the screen stops
  waiting and shows the reason.
- **There is no job that sends, and no command that does.** If you find
  yourself looking for one, stop: sending is the user's button.
