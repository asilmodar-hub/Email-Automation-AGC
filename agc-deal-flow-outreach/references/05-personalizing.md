# Adjusting a round to the list

A `personalize` job comes the moment a round is prepared. Every email in it is
the sender's master email under a greeting the app worked out by rule. Your
part is to make each one fit its person, from what the contact list says, so
the sender does not have to fill in anything by hand. There are no variables
in the master email: you read the row and decide.

## What you get

`payload.emails`, one per contact:

| Field | Meaning |
|---|---|
| `contact_id` | Copy it back exactly |
| `template` | `de_sie`, `de_du` or `en`: the version this person gets |
| `email_now` | The email as it stands: rule greeting, blank line, master text |
| `rule_greeting` | The greeting the app worked out by rule |
| `subject` | The subject line |
| `contact` | The whole row: name, title, company, role, type, city, region, priority, relevance, owner, notes, to-dos, cell comments (`comments`), people also named in the cell (`others`), and every other column of the list under `extra` |

## What to do, per email

1. **The greeting.** Write the right salutation line from the name. The AGC
   list has no Herr/Frau column, so the rule falls back to a neutral
   "Guten Tag Michael Hengl,". You can do better: a first name almost always
   says Herr or Frau ("Sehr geehrter Herr Hengl,"); keep any academic title
   ("Sehr geehrte Frau Mag. Dorn,", "Sehr geehrter Herr Dr. Barbist,"); in the
   du version "Lieber Michael," / "Liebe Sabine,"; in English "Dear Mr Hengl,"
   / "Dear Dr Barbist,". When the first name does not tell you (Kim, Andrea in
   an international firm, initials only), keep the neutral `rule_greeting`.
   When only a surname is known and the gender is not clear from anything in
   the row, also keep it. Never guess.
2. **The text.** Leave it exactly as it is, unless the row gives a concrete,
   honest reason for one sentence: a note in `notes`, `todos`, `comments` or
   `extra` that the sender would plainly want acknowledged (for example
   "Kennt den Markt für Nachfolgen", or a comment that the person changed
   firm). Then add or adapt one sentence, in the sender's voice, following
   `01-rewriting.md`. Most emails get no change to the text at all, and that
   is right: the master email is the sender's own.
3. **Never** mention priorities, relevance ratings, planning figures, owner
   short forms or anything else that is the firm's internal bookkeeping about
   the person. Those columns are background, not content.

The rules of `01-rewriting.md` hold here too: the language and Sie/du are the
contact's, nothing goes in that the row does not say, and the generated-sounding
phrases listed there stay out.

## Handing back

```json
{"drafts": [
  {"contact_id": "mh@1492.example", "greeting": "Sehr geehrter Herr Hengl,"},
  {"contact_id": "a.huber@kanzlei.example", "greeting": "Sehr geehrte Frau Dr. Huber,",
   "body": "Sehr geehrte Frau Dr. Huber,\n\nich melde mich …\n\nVielen Dank und beste Grüße"}
]}
```

`greeting` is required for every email. Add `body` (the whole email, greeting
included) only for an email whose text you changed. Large rounds can be handed
back in several submits; the app answers with `still_to_do` until every email
is done, and with `failed_checks` for any email whose change broke a check.
The reviewer sees every changed line marked, and can go back to the master
email with one click.
