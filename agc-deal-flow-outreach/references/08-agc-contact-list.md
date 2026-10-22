# AGC's contact list: the Deal Origination Cockpit

AG Capital keeps its intermediaries in one workbook, the *Deal Origination
Cockpit* (for example `20250801_Deal_Origination_Cockpit_2025.xlsx`). The tool
reads it as it is; nobody needs to reshape it, and it is never written to.
This page says what is in it and how the tool reads it, so you know without
opening the file. The same short forms, countries and regions are in
`assets/agc_directory.json`, which the app reads; change both together.

## Sheets

| Sheet | Visible | What the tool does with it |
|---|---|---|
| `Intermediäre` | yes | **The contact list.** Title row 1, header row 2, one contact per row from row 3 (about 750 rows). Read in full. |
| `Raiffeisen` | hidden | Bank contacts. Header row 2, then a row of short forms (`KLA`, `DJE`, `CGA`, `OBK`, `VKO`); an `X` under one says who looks after the contact. Read. |
| `Datenbanken` | hidden | Databases (Crunchbase and the like), no addresses. Not read. |
| `Berater` | hidden | An older adviser overview without an email column. Not read. |
| `Auswertung`, `Zeitaufwand Team`, `Hilfstabelle`, `Investorenverzueichnisse`, `Dealfloworigination->` | | Figures, plans and lookup tables. Not read as contacts. |

Every sheet with an email column and at least one real address is read; the
one whose header is understood best comes first.

## Columns of `Intermediäre`

| Column | Read as | Notes |
|---|---|---|
| Firma | company | |
| Kategorie | type | M&A Advisor, PE Fonds Inland/Ausland, VC Fonds Inland/Ausland, Rechtsanwälte, Steuerberater, Wirtschaftsprüfer Steuerberater, Banken / Versicherungen, Privatbanken, Family Office / Industrieholding, Berater, Sonstige Berater, Crowdfunding Plattformen, Förderstellen, Business Angels, FoF, Staatliche Stellen and a few more. Shown on the chart under their usual names (M&A adviser, Private equity, …). |
| Ansprechpartner | the person | Free text. "Michael Hengl"; "Mag. Sabine Duchaczek" (title kept); "Hr. Zimmerer" (Herr); a surname alone; "Dr. Barbist, Johannes" (surname first); "Mäkki, Andreas Huber" or "Kleebinder, Pongracz" (two people: the one the address belongs to is written to, the other is kept under `others`). A first name missing in the cell is taken from an address like `roman.pongracz@…`. |
| Position | role | |
| E-Mail | email | Sometimes "Name <address>", two addresses separated by `;` (the first is used, the rest kept), or a city or a name instead of an address (kept as a note). |
| Adresse, PLZ, Ort, Tel | address, postcode, city, phone | `n.a.` and `#N/A` count as empty. |
| Region | region | Often empty. Values like Hessen, Bavaria, Vienna, Germany, DACH, "Austria, Europe". |
| Zuständigkeit | owner | The short form of the AGC person responsible (see below). |
| Relevanz für AT Deal Flow | relevance | Hoch / Mittel / Niedrig. |
| Prio. | priority | A–F and N (see below). |
| Anmerkung (Person & Wann) | notes | |
| Sonstige todos | todos | |
| Datum Erstansprache | date of the first contact | Used like a last-sent date when the tool has not written to the person yet. |
| everything else | `extra` | Co-Investor, Rahmenvereinbarung, UP/Info gesendet, Prio. Erinnerung, Ziel/Erreichte Anzahl, the two-monthly Plan/Ist/Δ columns, Fällig bis, Erstansprache/Follow-up/Investmentkriterien flags, Neue Berater, MM Initiative, Datum. Kept with the contact as background for you; never quoted in an email. |
| cell comments | `comments` | Without Excel's notice and the author's name, e.g. "Hat Bregal 03/2024 verlassen - neue Adresse noch unklar". |

The list has no Herr/Frau, language or Sie/du column. The greeting is written
by you from the first name (`05-personalizing.md`); the language is German,
unless the country is clearly not German-speaking (London, USA, Prague: then
English); the form is Sie.

## Who is responsible: the short forms

Each AGC person has a short form: the first letter of the first name and of
the surname. **Vsevolod Kornilov is VK**; Max Mustermann would be MM. The
`Raiffeisen` sheet uses three letters: the first letter of the first name and
the first two of the surname (Vsevolod Kornilov is VKO, Christoph Ganahl is
CGA). Lower-case variants in the list ("Kl") are the same short form.

| Short form | Long form | Person |
|---|---|---|
| VK | VKO | Vsevolod Kornilov |
| CG | CGA | Christoph Ganahl |
| LA | | Lorenz Ambrosius |
| PM | | Paula Meertz |
| SB | | Sabine Bac |
| KL | KLA | (named in the list only by short form) |
| DJ | DJE | (named in the list only by short form) |
| JO, DN, SK, OP, MN | | (named in the list only by short form) |

How the tool uses it:

- When the app starts, it reads who is sending from Outlook and works out
  their short form: from this table, else from their name ("Max Mustermann"
  is MM), else from an address like `max.mustermann@…`. It is shown, and can
  be changed, on the Setup tab ("Your short form in the list").
- Only contacts with the user's short form in `Zuständigkeit` (or their
  three-letter form under an `X`) are in their rounds. Contacts of other
  short forms show as "belongs to KL" on the Contacts tab and can be ticked in
  by hand.
- A contact with an empty `Zuständigkeit` (about 40 in the list,
  "n. zugewiesen") belongs to nobody, so it is left out unless the user ticks
  "Count contacts nobody is responsible for as mine" on the Setup tab. (In a
  list that names owners by full name, like the tool's own template, an empty
  cell still means "whoever runs the round".)

## Priorities

From the `Hilfstabelle`: how many contacts a year each priority is planned for.

| Prio. | Contacts a year | Days between two emails the tool keeps |
|---|---|---|
| A | 6 | 60 |
| B | 4 | 90 |
| C | 2 | 170 |
| D | 1 | 350 |
| E, F, N | 0 | the user's own rhythm |

E is set at the second contact with a new person, N when the first
introduction email is sent (comments in the Hilfstabelle). Nobody is left out
for their priority alone; the user can filter by it.

## Regions

The `Region` column is filled for fewer than half the rows. Where it is empty,
the tool reads the country and region off the city (`Ort`: Wien, Frankfurt,
München, Linz, Graz, Zürich, London, …), then the postcode (five digits:
Germany), then the ending of the address (`.at`, `.de`, `.ch`). The result is
a country (Austria, Germany, Switzerland, United Kingdom, …) and for Austria,
Germany and Switzerland a region (Wien, Oberösterreich, Hessen, Bayern,
Zürich, …). "DACH" counts for all three countries.

On the Contacts tab, under "Who I write to", the user picks countries, a
region within one country, priorities and relevance. The choice is saved and
decides who is in the round; whoever falls outside shows "outside your region
filter" and can still be ticked in by hand.

## Missing details

About 180 rows have no email address and about 100 no contact person. Those
contacts are left out with the reason "no email address: tick to have Claude
look it up". When the user ticks one, the round gives you a `research` job
(`06-research.md`); what you find is shown on the Review tab for the user to
accept, and is never written into the list.
