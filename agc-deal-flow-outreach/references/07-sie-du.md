# Writing the other German version of a master email

The user writes a master email in German once, either the Sie version or the
du version. When they leave the text, a `convert` job asks you for the other
one, so they do not have to copy, paste and rewrite it themselves. It works in
both directions: whichever version the user wrote last is the source.

## What you get

`payload`: `source_form` and `target_form` (`Sie` or `du`), `kind` (`first`
email or `followup`), the `subject` and `body` the user wrote, and
`target_now` (what the other version says at the moment, for comparison).

## How to write it

- **Same email, other register.** Keep the content, the order, the length and
  the paragraphs. Do not improve, shorten or add.
- **Sie to du** is more than swapping pronouns: it is the voice one uses with a
  colleague one is on first-name terms with. "Vielen Dank und beste Grüße"
  becomes "Danke dir und liebe Grüße"; "Falls Ihnen … begegnet" becomes
  "Falls dir … begegnet"; a stiff phrase may become the plain one a person
  would say. Verbs follow the pronoun ("können Sie" / "kannst du").
- **du to Sie** is more formal in the same measure: "liebe Grüße" becomes
  "beste Grüße", "Danke dir" becomes "Vielen Dank", "Hallo" style openings
  become the plain formal ones.
- `Sie`, `Ihnen`, `Ihr` are capitalised; `du`, `dir`, `dein` are lower-case
  inside a sentence. The two never mix: the app checks this and flags the
  version on the Setup tab if they do.
- No greeting line and no signature: the greeting is added per person, and
  Outlook adds the signature.
- The subject usually stays the same; change it only if it addresses the
  reader.
- The rules of `01-rewriting.md` on generated-sounding phrases hold here too.

## Handing back

```json
{"subject": "Kurze Frage aus der AG Capital",
 "body": "ich melde mich wieder einmal kurz bei dir, …\n\nDanke dir und liebe Grüße"}
```

If the user changed the source text again while you were writing, the app
answers that your version was not used and a newer job follows. That is
normal; just take the next job.
