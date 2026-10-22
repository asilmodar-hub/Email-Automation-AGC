# Looking up a missing address or contact person

A `research` job comes when the reviewer ticked a contact that the list has no
usable email address or no contact person for, because they still want to
write to that firm. You look the missing piece up on the public web and hand
it back. **The app never writes it into the contact list**: it is shown on the
Review tab, marked "found online", and the reviewer decides whether to use it,
enter an address themselves, or leave the contact out.

## What you get

`payload.contacts`, one per contact: `contact_id`, `missing` (`email`,
`person`, or both), the row (`company`, `first`, `last`, `title`, `role`,
`city`, `region`, `country`, `website`, `type`, `email` if there is one, and
`extra` with every other column) and `template` (which language the email is in).

## How to look

- Search with the firm's name and city, and the person's name if the list
  has one. Nothing else from the row goes into a search: not the notes, not
  the owner, not the priority.
- Prefer the firm's own website: team or people pages, the imprint
  (Impressum), the contact page. A professional register or the firm's own
  press release is next best. A personal address from a data broker or a
  guessed pattern (first.last@) is not a finding.
- For a missing **person**, find the one who fits the outreach: a partner or
  managing director in M&A, corporate finance or transactions, or the person
  the list's `role` points to. One person, not a list.
- For a missing **address**, the person's own business address if the site
  shows it, else the firm's general address (office@, info@) and say so in
  `note`.
- If a person in the list has left the firm (a comment may say so), say that
  in `note` and give their successor only if the site names one.
- If nothing reliable turns up, hand back empty fields and a one-line `note`.
  An honest "nothing found" is better than a plausible guess: the reviewer
  will send an email to whatever they accept.

## Handing back

```json
{"found": [
  {"contact_id": "intermediaere:42", "email": "p.lindner@bergkamm.example",
   "first": "Petra", "last": "Lindner", "title": "", "gender": "f", "role": "Partnerin",
   "greeting": "Sehr geehrte Frau Lindner,",
   "source": "https://www.bergkamm.example/team", "confidence": "high",
   "note": "Named on the firm's team page as partner for M&A."},
  {"contact_id": "intermediaere:57", "email": "", "first": "", "last": "",
   "source": "", "confidence": "", "note": "The firm's website lists no people and no address."}
]}
```

- `source` is required whenever you give an address or a person: the web
  address where it is written. The reviewer clicks it.
- `confidence`: `high` (stated on the firm's own site), `medium` (another
  reliable source), `low` (indirect; say why in `note`).
- `greeting` in the language and form of `template`, as in
  `05-personalizing.md`.
- `gender` is `m`, `f` or empty.

The app answers with `still_to_do` and `problems` (an address that is not one,
a finding without a source). The job is done when `still_to_do` is empty.
