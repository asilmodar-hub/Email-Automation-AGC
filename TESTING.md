# Testing

## What has been tested

**Automatically, against a simulated mailbox** (`python dev/run_tests.py`, 14
tests):

- Reading a contact list: header matching, missing addresses, assumed
  language and Sie/du, the greeting rules in German and English, the kind of
  contact (from a Type column, or read off the firm's name).
- Who is in a round: owner, opt-outs, cadence, the batch cap, hand overrides.
- Putting an email together (greeting plus master text) and every automatic
  check: wrong greeting, Sie/du mix, leftover placeholder, and for changed
  lines another contact's name, the wrong language, unsupported numbers, tone.
- The master emails themselves: unfinished notes, placeholders, Sie/du.
- Rhythm to scheduler rule: quarterly, half-yearly, yearly, a date, month-end.
- The whole flow through the app's own interface: choose list, start round
  (same text for everyone, no job for Claude), ask Claude to change one email,
  a rewrite that fails a check, approve all, back to the master email, edit by
  hand, test email, send with confirmation, stop and resume, nobody written to
  twice, answers by thread and by address, bounce, absence note,
  classification, opt-out list, correcting by hand, Excel export, follow-ups,
  rhythm change, scheduled run.
- Restart with a change request open: nothing lost, the job is handed out
  again.
- Sending without review: only possible with a rhythm set, only on a scheduled
  run, never on a round started by hand, and emails that fail a check are held
  back.
- German: every sentence on the screen has a German version, the app's own
  sentences are translated on the way to the screen, what people wrote is
  never touched, and files on disk stay language-neutral.

**By hand in the browser**, same simulated mailbox: every screen, autosave of
settings, the type chart and its filter, Ask Claude, Approve all, the send
dialog and progress, the tracker.

**The command path Claude uses** (`start`, `wait`, `submit`, `status`, `stop`,
`start --scheduled`), including refused results and a stopped app.

**Real classic Outlook, read-only**, on the development machine: the mailbox
identity is read without a security prompt and the default signature loads
into a new email.

## What has not been tested

- **Sending through real Outlook.** The development machine's mailbox is not
  an AGC one, so no real email was sent. Everything in "Pilot" below is open.
- **Reading real answers** from a real inbox.
- **The first-run setup** (`setup.cmd`) that installs the tool's own Python.
  It is adapted from the deal-model skill's setup, which works, but this copy
  has not been run.
- **A live scheduled run** through the Claude app's scheduler.
- **The Windows notification** on a scheduled run.

## Pilot, on an AGC computer with an AGC mailbox

Do these in order. Stop at the first one that fails.

1. `scripts\outreach.cmd doctor` reports Ready and names the right mailbox.
2. In Claude: "open the deal flow outreach". The screen opens and shows
   "Sending as" with the right address.
3. Setup: choose a list of three or four colleagues, finish the master emails.
4. Contacts: the right people are in, the reasons for the others make sense.
5. Prepare the round. Check a few emails: right greeting, right version
   (Sie, du, English). On one, press **Ask Claude** and ask for a small
   change. Is the marked line something you would have written?
6. **Send a test to myself** on two drafts. In Outlook check: it arrived, the
   font matches your normal emails, your signature is below the text, there
   is no `winmail.dat` attachment, and it sits in Sent Items.
7. Did Outlook show a security prompt ("A program is trying to send an email
   on your behalf")? If yes, stop: IT has to allow programmatic access for
   this to be usable.
8. Send the round to the colleagues. Watch the progress and the pauses.
   Afterwards: each email is in Sent Items, none is left in the Outbox.
9. Ask the colleagues to answer in different ways: one with a lead, one "not
   now", one "please stop writing", one from a phone. Then **Check for
   answers**. Each should land in the right outcome, and the "please stop"
   address should show as left out on the Contacts tab.
10. Set the rhythm to a date a few minutes ahead. Leave Claude open. A round
    should be prepared and the review screen should open by itself.
11. Only then: a first real round, ten contacts.

## Known limits

- Classic Outlook only. The new Outlook app has no automation interface.
- Outlook has to stay open while a round is being sent.
- Answers are found in the Inbox and two levels of folders below it. A rule
  that moves mail elsewhere hides it from the tracker.
- A reply sent from a different address than the one written to, outside the
  original thread, is not recognised. Set the outcome by hand in the tracker.
- The scheduler only runs while the Claude app is open.
- The German on screen was written by Claude and has not been read by a
  native speaker at AGC yet.
- "Send without my review" relies on everything above that is untested with
  real Outlook, with nobody watching. Do not switch it on for real before the
  pilot has passed.
