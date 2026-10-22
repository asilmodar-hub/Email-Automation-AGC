# AGC Deal Flow Outreach

A Claude skill for AG Capital. It sends the firm's periodic deal-flow emails to
advisers, lawyers and other professional contacts from the user's own Outlook,
each under the right personal greeting, and tracks who answered.

## How it works

1. The user calls the skill in Claude. A screen opens in the browser.
2. On the screen they pick their Excel contact list (AGC's Deal Origination
   Cockpit is read as it is) and write their master email once, without any
   placeholders. Writing the Sie version has Claude write the du version
   (and the other way round). A file can be attached to every email.
3. Only the user's own contacts are in the round: their short form in the
   list's Zuständigkeit column (Vsevolod Kornilov is VK) is worked out from
   their Outlook name. Filters on the Contacts tab narrow the round by
   country, region, priority and relevance. A contact without an address or
   contact person can be ticked in: Claude looks the missing piece up online,
   and the user decides on what it found.
4. Claude adjusts each email to the person from the list: the greeting from
   the name ("Sehr geehrter Herr Dr. Gruber,") and a line only where the list
   gives a reason. Changed lines are marked.
5. The user reviews. One email can be edited by hand, changed by Claude with
   **Ask Claude** ("refer to the email from two weeks ago about the deal":
   Claude reads the earlier emails with that address), or have its
   attachments changed. **Approve all**, then **Send**. Emails leave through
   classic Outlook one at a time with a pause between them.
6. Later, **Check for answers** reads the inbox for each person's first
   answer. Claude sorts it into lead, referral, not now, decline, out of
   office, bounce or do not contact; the rest of the conversation stays in
   Outlook.
7. A rhythm (quarterly, half-yearly, yearly, or a date) can be set on the
   screen. On the due date the round is prepared and waits for review.

Nothing is sent without the user pressing Send, with one exception the user
has to switch on themselves: with a rhythm set, "Send without my review" lets
the app send the scheduled round by itself. Emails that fail an automatic
check are still held back.

The screen is in English or German (switch at the top of the Setup tab), and
light or dark (the moon or sun at the top right; by default it follows
Windows).

## What is in this folder

| Path | What |
|---|---|
| `agc-deal-flow-outreach/` | The skill: `SKILL.md`, `scripts/`, `assets/`, `references/` |
| `agc-deal-flow-outreach.skill` | The same, packed for upload to Claude |
| `dev/` | Test suite, simulated demo, fixture and packaging scripts |
| `TESTING.md` | What has been tested, and the pilot checklist for real mail |

## Installing

Upload `agc-deal-flow-outreach.skill` in Claude under Settings, Capabilities,
Skills. Each user needs Windows, classic Outlook set up with their AGC mailbox,
and the Claude desktop app. The first run sets up its own Python (two to three
minutes, no administrator rights, needs python.org and pypi.org reachable).

## Trying it without sending anything

```
python dev/demo.py --fresh
```

Then open http://127.0.0.1:8765/?t=demo. This runs the real app against a
stand-in mailbox with 50 invented contacts and a rule-based stand-in for
Claude. `dev/fixtures/agc_cockpit_like.xlsx` is a list laid out like AGC's
Deal Origination Cockpit, with invented people, for trying the AGC-specific
parts (short forms, regions, missing details). Prepare, ask for a change, approve, send, check for answers: all of it
works, none of it touches Outlook.

## For whoever maintains this

```
python dev/run_tests.py        the test suite (simulated mailbox)
python dev/make_fixtures.py    rebuild the contact template and the fixtures
python dev/package.py          rebuild the .skill file
```

Where things are kept at run time:

- Per user: `%LOCALAPPDATA%\AGC-DealFlow` (settings, the tool's Python, jobs,
  copies of attached files). Deleting this folder removes the tool from the
  computer.
- Next to the contact list: `Deal Flow Outreach data` (one file per round and
  sender, and the do-not-contact list). On a shared drive this is what makes
  the tracker firm-wide. The contact list itself is never written to.

## Before the first real round

- A lawyer's view on Austrian rules for unsolicited email (TKG) and on keeping
  contact profiles (GDPR). The tool honours opt-outs; it does not decide
  whether writing to someone is allowed.
- The pilot in `TESTING.md`: real Outlook has only been read from so far, not
  sent from.
