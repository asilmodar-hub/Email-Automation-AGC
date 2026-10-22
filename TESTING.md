# Testing

## What has been tested

**Automatically, against a simulated mailbox** (`python dev/run_tests.py`, 22
tests; on a computer without Outlook's connector the start-up test stops at
its first check, as it always has):

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
- AGC's Deal Origination Cockpit, on an invented list laid out the same way
  (`dev/fixtures/agc_cockpit_like.xlsx`): title row above the header, the
  contacts sheet and the hidden bank sheet with its row of short forms, sheets
  without addresses left alone, every other column kept, two people in one
  cell, "Hr.", a surname written first, "Name <address>", two addresses in a
  cell, a cell comment, the date of the first contact, country and region
  from the city, English for London.
- Whose contact it is: short forms from the name or the address (VK, MM),
  three-letter forms, "Kl", nobody responsible; the filters by country,
  region, priority and relevance.
- With Claude's parts played by the test: adjusting a round to the list
  (greeting, one changed line, partial hand-backs), looking up a missing
  address (refused without a source, not usable until accepted, the list
  never written to), writing the du version from the Sie one (once per text,
  not overwritten when the text changed meanwhile), files for every email,
  removed from one and added to another, and sent with them; an earlier email
  handed to Claude when the note refers to it, and a note pointing to an email
  that is not there; only the first answer read; a scheduled round that sends
  without review waits for Claude's pass.

**By hand in the browser**, same simulated mailbox: every screen, autosave of
settings, the type chart and its filter, Ask Claude, Approve all, the send
dialog and progress, the tracker. In 1.2, with the AGC-style list, in a
headless Chromium: Setup, Contacts with the filters open, and Review with a
looked-up contact and an attachment, light and dark, without script errors.

**The real Deal Origination Cockpit** (the 2025 workbook, read on the
development machine, not kept in this repository): 759 contacts from
`Intermediäre` and `Raiffeisen`, short forms counted per person (KL 345, DJ
110, VK 108, …), country found for all but 135, about 180 rows without an
address and 100 without a contact person offered for a look online.

**The command path Claude uses** (`start`, `wait`, `submit`, `status`, `stop`,
`start --scheduled`), including refused results and a stopped app.

**Real classic Outlook, without sending**, on the development machine: the
mailbox identity is read without a security prompt, and every step of sending
up to the last one passes, both quietly and in the email's own window
(`python dev/outlook_dryrun.py`; nothing is saved or sent).

**The first-run setup**, once, on the development machine, by installing the
skill in Claude and calling it: the private Python and the packages were
installed. That run showed the app then failed to start, because the private
Python did not find the app's own modules. Fixed in 1.1, and now covered by a
test that starts the app the same way.

## What has not been tested

- **Sending through real Outlook has not worked yet.** One real attempt, on
  the development machine with a mailbox that is not an AGC one, was refused
  by Outlook at the very last step with "The parameter is incorrect". The
  cause is not established: Outlook had no window open at the time, and that
  machine's Outlook security is set by company policy. Since then (1.1) the
  tool opens Outlook's window before sending, tries a second time in the
  email's own window, removes the draft of an email that did not go out, and
  reports which step Outlook refused and with which error number. None of that
  has been confirmed by an email actually leaving. Everything in "Pilot" below
  is open.
- **Reading real answers** from a real inbox.
- **Earlier emails from real Outlook** for "Ask Claude". The search filters
  the Inbox by sender and Sent Items by recipient through Outlook's own
  search; it has only run against the simulated mailbox. If Outlook refuses
  the filter, it falls back to reading the folders, at most 4,000 emails each.
- **Attachments through real Outlook.** Simulated sending checks the files are
  there and records their names; `Attachments.Add` has not run against real
  Outlook.
- **Claude's own parts** (adjusting emails, looking up details, writing the
  du version) with a real Claude session. The tests play Claude's part.
- **The first-run setup on a restricted network.** It needs python.org and
  pypi.org; where those are blocked it stops with a message for IT.
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
- What Claude finds online is a suggestion. It is never sent without the
  reviewer pressing "Use these details" (or typing an address), and never
  written into the list.
- Attached files are copied to `%LOCALAPPDATA%\AGC-DealFlow\attachments`, at
  most 20 MB each.
- "Send without my review" relies on everything above that is untested with
  real Outlook, with nobody watching. Do not switch it on for real before the
  pilot has passed.
