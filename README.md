# AGC Deal Flow Outreach

A Claude skill for AG Capital. It sends the firm's periodic deal-flow emails to
advisers, lawyers and other professional contacts from the user's own Outlook,
each under the right personal greeting, and tracks who answered.

## How it works

1. The user calls the skill in Claude. A screen opens in the browser.
2. On the screen they pick their Excel contact list and write their master
   email once (German Sie, German du, English).
3. Everyone gets that master email as it stands, under a greeting worked out
   from the list ("Sehr geehrter Herr Dr. Gruber,"). The Contacts tab shows
   who is in the round and a chart of the kinds of contact.
4. The user reviews. One email can be edited by hand, or changed by Claude
   with **Ask Claude** ("mention that we met in May"); changed lines are
   marked. **Approve all**, then **Send**. Emails leave through classic
   Outlook one at a time with a pause between them.
5. Later, **Check for answers** reads the inbox. Claude sorts each reply into
   lead, referral, not now, decline, out of office, bounce or do not contact.
6. A rhythm (quarterly, half-yearly, yearly, or a date) can be set on the
   screen. On the due date the round is prepared and waits for review.

Nothing is sent without the user pressing Send, with one exception the user
has to switch on themselves: with a rhythm set, "Send without my review" lets
the app send the scheduled round by itself. Emails that fail an automatic
check are still held back.

The screen is in English or German (switch at the top of the Setup tab).

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
Claude. Prepare, ask for a change, approve, send, check for answers: all of it
works, none of it touches Outlook.

## For whoever maintains this

```
python dev/run_tests.py        the test suite (simulated mailbox)
python dev/make_fixtures.py    rebuild the contact template and the fixture
python dev/package.py          rebuild the .skill file
```

Where things are kept at run time:

- Per user: `%LOCALAPPDATA%\AGC-DealFlow` (settings, the tool's Python, jobs).
  Deleting this folder removes the tool from the computer.
- Next to the contact list: `Deal Flow Outreach data` (one file per round and
  sender, and the do-not-contact list). On a shared drive this is what makes
  the tracker firm-wide. The contact list itself is never written to.

## Before the first real round

- A lawyer's view on Austrian rules for unsolicited email (TKG) and on keeping
  contact profiles (GDPR). The tool honours opt-outs; it does not decide
  whether writing to someone is allowed.
- The pilot in `TESTING.md`: real Outlook has only been read from so far, not
  sent from.
