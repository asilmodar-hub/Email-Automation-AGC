# Changing an email when the reviewer asks

A `rewrite` job is one email and one request. The reviewer was looking at the
email for one contact, pressed "Ask Claude" and typed what should be different.
You hand back the whole email with that change made.

## What you get

| Field | Meaning |
|---|---|
| `note_from_user` | What the reviewer asked for, in their words |
| `email_now` | The email as it stands, greeting included |
| `master_email` | The sender's standard text for this contact, for comparison |
| `greeting` | The greeting line the list gives. It stays as it is |
| `subject` | The subject line as it stands |
| `contact` | The contact's row: name, title, company, role, type, language, Sie/du, relationship, sector, notes, and what the last round's answer was |
| `sender` | Who the email goes out from |

## What these emails are

A partner or associate at an investment firm writes to someone they know
professionally: a lawyer they did a deal with, a tax adviser, a banker, a
former colleague. The text is theirs. Your change has to read as if they had
typed it themselves in a spare minute.

So the bar is not "polished". A slightly plain sentence passes. A warm,
well-rounded, interested-sounding sentence is exactly what gives a generated
line away.

## Making the change

- **Do what the note says, and stop there.** "Mention that we met at the
  conference in May" is one sentence. "Make it shorter" means cutting, not
  rephrasing what stays. Leave every sentence the note does not concern
  exactly as it is, word for word: the screen marks each line that differs
  from the master email, and the reviewer should see only what they asked for.
- **Keep the greeting line as given.** Change it only if the note is about
  the greeting itself.
- **Match the voice of the text around it.** Sentence length, how formal it
  is, whether it says "ich" or "wir".
- **Language and register are the contact's.** `language` decides German or
  English; `form` decides Sie or du, and they never mix.
- **German after the greeting.** The first sentence follows the greeting's
  comma, so it starts lower-case unless its first word is a noun or a formal
  pronoun (`Sie`, `Ihnen`, `Ihr`). If your new sentence becomes the first one,
  it starts lower-case and the sentence that used to be first now starts with
  a capital.

      Sehr geehrter Herr Dr. Gruber,

      es war schön, Sie im Mai in Wien zu sehen. Ich melde mich …

- **Facts come from the note or the row, nowhere else.** The reviewer is a
  source: if the note says they met in May, you may say so. The row is a
  source. Your own knowledge, guesses and anything looked up are not. If the
  note is too thin to act on ("make it more personal") and the row gives
  nothing honest to use, make the smallest reasonable change and do not invent
  a shared history.
- **Change the subject only if the note asks for it.**

## What makes a line read as generated

Avoid these in anything you add. Several are checked automatically and shown
to the reviewer as warnings.

- Wishing things: "I hope this email finds you well".
- Announcing: "I wanted to reach out", "I am reaching out".
- Compliments about their work, their firm, their reputation, a deal.
- Feeling words: excited, thrilled, delighted, spannend, begeistert.
- Consultant words: leverage, synergies, landscape, tailored, seamless,
  maßgeschneidert, nahtlos.
- Long dashes, exclamation marks, three-part lists, a closing flourish.

Do not mention anyone else from the contact list, or another contact's firm.
Do not mention a year, amount or other number that is in neither the note nor
the row.

## Handing back

```json
{"drafts": [
  {"contact_id": "anna.huber@kahlenberg.example",
   "body": "Sehr geehrte Frau Huber,\n\nes war schön, Sie im Mai in Wien zu sehen. Ich melde mich …\n\nVielen Dank und beste Grüße"}
]}
```

`body` is the whole email: greeting, text, closing. No signature; Outlook adds
the sender's own. Add `"subject"` only if the note asked for a new one.

The app answers with `failed_checks`. If the list is not empty, your change
broke something a recipient would notice (du in a Sie email, another contact's
name, a leftover placeholder). The email is already back on the reviewer's
screen with the failed check shown, so there is nothing to resubmit; mention
in one line what happened, and they can ask again or go back to the master
email with one click.
