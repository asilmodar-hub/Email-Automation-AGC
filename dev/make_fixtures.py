#!/usr/bin/env python3
"""Build the contact template that ships with the skill, and a list of 50
invented contacts to test with.

    python dev/make_fixtures.py

Writes  agc-deal-flow-outreach/assets/Contacts_Template.xlsx
        dev/fixtures/contacts_50.xlsx

Every person and firm in the fixture is made up, and every address ends in
.example, which cannot receive mail.
"""
import datetime as dt
import os
import random

import openpyxl
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.worksheet.datavalidation import DataValidation

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

HEADERS = [
    ("Salutation (Herr/Frau)", 14, "Herr or Frau. Needed for a formal German or English greeting."),
    ("Title", 9, "Dr., Mag., DI, Prof. Leave empty if none."),
    ("First name", 16, ""),
    ("Last name", 18, ""),
    ("Company", 28, ""),
    ("Role", 22, "What they do there."),
    ("Type", 18, "Optional: Law firm, Tax / audit, M&A adviser, Consultant, Bank, Private equity, Venture "
                 "capital, or your own word. Left empty, it is read off the firm's name."),
    ("Email", 32, "One address per row."),
    ("Language (DE/EN)", 12, "DE or EN. Empty counts as DE."),
    ("Form (Sie/du)", 11, "Sie or du. Empty counts as Sie."),
    ("Owner", 20, "The AGC person who writes to this contact. Empty: whoever runs the round."),
    ("Relationship", 40, "How you know them and when you last spoke. The most useful column for a personal line."),
    ("Sector focus", 28, "What kind of companies they see."),
    ("Notes", 44, "Anything worth referring to. Only what is written here can be mentioned."),
    ("Cadence", 12, "Optional: quarterly, half-yearly, yearly or never. Overrides your own rhythm."),
    ("Do not contact", 12, "x to never write to this person."),
    ("Greeting override", 22, "Optional: the exact greeting line, e.g. 'Lieber Tom,'. Replaces the rule."),
]
NAVY, BLUE = "10336B", "0B63B4"


def sheet(wb, rows):
    ws = wb.active
    ws.title = "Contacts"
    ws.append([h for h, _, _ in HEADERS])
    for i, (_, width, _) in enumerate(HEADERS, start=1):
        cell = ws.cell(row=1, column=i)
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill("solid", fgColor=NAVY)
        cell.alignment = Alignment(vertical="center", wrap_text=True)
        ws.column_dimensions[cell.column_letter].width = width
    ws.row_dimensions[1].height = 32
    ws.freeze_panes = "A2"
    for row in rows:
        ws.append(row)
    for col, options in (("A", "Herr,Frau"), ("I", "DE,EN"), ("J", "Sie,du"),
                         ("O", "quarterly,half-yearly,yearly,never")):
        dv = DataValidation(type="list", formula1='"%s"' % options, allow_blank=True)
        dv.add("%s2:%s2000" % (col, col))
        ws.add_data_validation(dv)
    help_ws = wb.create_sheet("How to fill")
    help_ws.column_dimensions["A"].width = 26
    help_ws.column_dimensions["B"].width = 100
    help_ws.append(["Column", "What goes in it"])
    for cell in help_ws[1]:
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill("solid", fgColor=BLUE)
    for name, _, hint in HEADERS:
        help_ws.append([name, hint])
    help_ws.append([])
    help_ws.append(["", "The tool only reads this workbook. It never changes it."])
    help_ws.append(["", "What it knows about earlier rounds is kept in the folder "
                        "'Deal Flow Outreach data' next to this file."])
    return ws


def template(out=None):
    wb = openpyxl.Workbook()
    sheet(wb, [
        ["Herr", "Dr.", "Max", "Mustermann", "Mustermann & Partner Rechtsanwälte", "Partner, M&A", "Law firm",
         "max.mustermann@kanzlei.example", "DE", "Sie", "", "Gemeinsames Mandat 2023 (Verkauf eines "
         "Maschinenbauers); zuletzt im Frühjahr telefoniert", "Mittelstand, Nachfolge", "", "", "", ""],
        ["Frau", "", "Erika", "Musterfrau", "Musterfrau Consulting", "Managing Director", "",
         "erika@consulting.example", "EN", "du", "", "Met at a conference in Vienna, 2024",
         "Industrial services", "", "yearly", "", ""],
    ])
    out = out or os.path.join(ROOT, "agc-deal-flow-outreach", "assets", "Contacts_Template.xlsx")
    wb.save(out)
    return out


FIRST_M = ["Thomas", "Michael", "Stefan", "Andreas", "Markus", "Christian", "Florian", "Lukas", "Georg", "Peter"]
FIRST_F = ["Anna", "Katharina", "Julia", "Barbara", "Elisabeth", "Sabine", "Martina", "Claudia", "Eva", "Nina"]
LAST = ["Gruber", "Huber", "Bauer", "Wagner", "Pichler", "Steiner", "Moser", "Mayer", "Hofer", "Leitner",
        "Berger", "Fuchs", "Eder", "Fischer", "Schmid", "Winkler", "Weber", "Schwarz", "Maier", "Reiter",
        "Brunner", "Lang", "Baumgartner", "Auer", "Binder", "Lechner", "Wolf", "Wallner", "Aigner", "Ebner"]
FIRMS = [
    ("Donauhof Rechtsanwälte", "lawyer", "Partner", "Gesellschaftsrecht, Nachfolge im Mittelstand"),
    ("Kahlenberg Steuerberatung", "tax", "Partnerin", "Familienunternehmen, Übergaben"),
    ("Praterstern Corporate Finance", "m&a", "Director", "Sell-side Mandate, Industrie und Technik"),
    ("Ringstrasse Consulting", "consultant", "Senior Manager", "Restrukturierung, Carve-outs"),
    ("Alpenrand Wirtschaftsprüfung", "audit", "Partner", "Prüfung mittelständischer Gruppen"),
    ("Stephansplatz Legal", "lawyer", "Counsel", "M&A, Private Equity"),
    ("Northgate Advisory", "m&a", "Managing Director", "Cross-border mid-market deals"),
    ("Belvedere Interim Management", "interim", "Geschäftsführer", "Interim CFO Mandate"),
    ("Wienfluss Bank Firmenkunden", "bank", "Firmenkundenbetreuer", "Finanzierung KMU"),
    ("Hartwell Partners", "consultant", "Partner", "Commercial due diligence"),
]
# Some rows say what kind of contact it is; the rest leave it to be read off the firm's name.
GIVEN_TYPE = {"Hartwell Partners": "Private equity", "Northgate Advisory": "M&A adviser",
              "Belvedere Interim Management": "Consultant"}
RELATION = {
    "de": ["Gemeinsames Mandat %d, zuletzt im Frühjahr telefoniert", "Kennengelernt beim Unternehmertag %d",
           "Hat uns %d ein Unternehmen aus der Verpackungsbranche vorgestellt", "Studienkollege, sehen uns ein-, zweimal im Jahr",
           "Gegenseite bei einer Transaktion %d, seither gelegentlich Kontakt", ""],
    "en": ["Worked on the same deal in %d, spoke last in spring", "Met at a conference in Vienna in %d",
           "Introduced a packaging company to us in %d", "Former colleague, in touch once or twice a year", ""],
}
NOTES = {
    "de": ["Ist im Sommer zur Partnerin ernannt worden", "Kanzlei hat ein Büro in Graz eröffnet",
           "Interessiert sich für Nachfolgethemen im Maschinenbau", "", "", ""],
    "en": ["Moved to the Munich office this year", "Published a piece on succession in family firms", "", ""],
}


def fixture():
    rng = random.Random(7)
    rows, used = [], set()
    for i in range(50):
        female = i % 2 == 1
        first = rng.choice(FIRST_F if female else FIRST_M)
        last = LAST[i % len(LAST)]
        firm, _, role, sector = FIRMS[i % len(FIRMS)]
        lang = "en" if firm in ("Northgate Advisory", "Hartwell Partners") else "de"
        form = "du" if i % 7 == 3 else "Sie"
        title = "Dr." if i % 6 == 0 else ("Mag." if i % 6 == 2 and lang == "de" else "")
        domain = firm.lower().replace("&", "").replace(" ", "-").replace("ä", "ae").replace("ü", "ue")
        email = "%s.%s@%s.example" % (first.lower(), last.lower(), domain)
        while email in used:
            email = "x" + email
        used.add(email)
        relation = rng.choice(RELATION[lang])
        if "%d" in relation:
            relation = relation % rng.choice([2021, 2022, 2023, 2024])
        rows.append(["Frau" if female else "Herr", title, first, last, firm, role, GIVEN_TYPE.get(firm, ""), email,
                     lang.upper(), form,
                     "" if i % 10 else "Somebody Else", relation, sector, rng.choice(NOTES[lang]),
                     "yearly" if i % 13 == 5 else "", "x" if i == 41 else "", ""])
    # the awkward rows a real list always has
    rows.append(["", "", "Kim", "Novak", "Novak Ventures", "Owner", "Venture capital",
                 "kim.novak@novak-ventures.example", "", "",
                 "", "", "", "", "", "", ""])                                       # nothing given: all assumed
    rows.append(["Herr", "", "Paul", "Ohneadresse", "Unbekannt GmbH", "", "", "", "DE", "Sie", "", "", "", "", "",
                 "", ""])                                                         # no email
    rows.append(["Herr", "", "Tom", "Berger", "Donauhof Rechtsanwälte", "Partner", "", "tom@donauhof.example", "DE",
                 "du", "", "Alter Freund", "", "", "", "", "Servus Tom,"])        # greeting override
    wb = openpyxl.Workbook()
    sheet(wb, rows)
    folder = os.path.join(ROOT, "dev", "fixtures")
    os.makedirs(folder, exist_ok=True)
    out = os.path.join(folder, "contacts_50.xlsx")
    wb.save(out)
    return out


# A list laid out like AGC's own Deal Origination Cockpit: a title row above the
# header, the contacts on "Intermediäre" with one "Ansprechpartner" cell for the
# person, short forms in "Zuständigkeit", planning columns, a cell comment, a
# hidden sheet whose responsible person is an X under a row of short forms, and
# sheets with figures but no addresses. Every name and firm is invented.
COCKPIT_HEADER = ["Firma", "Kategorie", "Ansprechpartner", "Position", "E-Mail", "Adresse", "PLZ", "Ort", "Tel",
                  "Co-Investor", "Region", "Zuständigkeit", "Relevanz für AT Deal Flow", "Rahmen-vereinbarung",
                  "UP/Info gesendet", "Prio.", "Prio. Erinnerung", "01-02 2026 Plan", "01-02 2026 Ist", "01-02 2026 Plan",
                  "Sonstige todos", "Fällig bis\n(Datum)", "Anmerkung (Person & Wann)", "Erstansprache Mail erfolgt? (0/1)",
                  "Datum Erstansprache"]
COCKPIT_ROWS = [
    # Firma, Kategorie, Ansprechpartner, Position, E-Mail, PLZ, Ort, Region, Zuständigkeit, Relevanz, Prio, Anmerkung, Erstansprache
    ("Lindengrund Partners", "M&A Advisor", "Michael Hagen", "Partner", "mh@lindengrund.example", 1010, "Wien", None, "VK", "Hoch", "B", "Kennt den Markt für Nachfolgen", None),
    ("Kobaltblau Consulting", "Berater", "Georg Kranz", None, "kranz@kobaltblau.example", 8042, "Graz", None, "VK", "Mittel", "C", None, None),
    ("Seeblick Capital", "PE Fonds Ausland", "Paulsen, Andreas Roth", None, "apaulsen@seeblick.example", "n.a.", "Wien", None, "VK", None, "D", None, None),
    ("Weidenhof Advisory", "M&A Advisor", "Kleebach, Rosner", None, "roman.rosner@weidenhof.example", None, "München", "Bavaria", "VK", "Mittel", "C", None, None),
    ("Nordlicht Corporate Finance", "M&A Advisor", "Hr. Zeller", "MD", "zeller@nordlicht.example", 60325, "Frankfurt", "Hessen", "VK", "Niedrig", "D", None, None),
    ("Uferweg Rechtsanwälte", "Rechtsanwälte", "Mag. Sabine Dorn", None, "Sabine Dorn <dorn@uferweg.example>", None, "Linz", None, "VK", "Hoch", "A", None, None),
    ("Talblick Holding", "Family Office / Industrieholding", None, None, "office@talblick.example", None, "Salzburg", None, "VK", "Mittel", "C", None, None),
    ("Bergkamm Ventures", "VC Fonds Inland", "Petra Lindner", "Partnerin", None, None, "Wien", "Vienna", "VK", "Mittel", "C", None, None),
    ("Morgenrot M&A", "M&A Advisor", None, None, None, None, "Zürich", "Switzerland", "VK", None, "E", None, None),
    ("Thames Bridge Advisors", "M&A Advisor", "David Shore", "Co-Founder", "david@thamesbridge.example", None, "London", "United Kingdom", "VK", "Niedrig", "D", None, None),
    ("Krähenfeld Steuerberatung", "Steuerberater", "Dr. Barbist, Johannes", None, "j.barbist@kraehenfeld.example", None, "Innsbruck", None, "VK", None, "D", None, "2026-09-30"),
    ("Silberau Partners", "M&A Advisor", "Jan Pöschl", None, "j.poeschl@silberau.example", None, "Berlin", None, "KL", "Mittel", "C", None, None),
    ("Eichenhain Beratung", "Sonstige Berater", "Daniel Bezner", None, "daniel.bezner@eichenhain.example", None, "Wien", None, "Kl", "Mittel", "C", None, None),
    ("Grünspan Capital", "PE Fonds Inland", "Lisa Kern", None, "lisa.kern@gruenspan.example", None, "Wien", None, None, "Hoch", "B", None, None),
    ("Abendrot Finanz", "M&A Advisor", "Felix Hahn", None, "felix.hahn@abendrot.example; office@abendrot.example", None, "Stuttgart", None, "DJ", None, "D", None, None),
]


def cockpit(out=None):
    wb = openpyxl.Workbook()
    wb.active.title = "Dealfloworigination->"
    rating = wb.create_sheet("Auswertung")
    rating.append(["Auswertung Deal-Origination"])
    rating.append(["Zuständigkeit", "Kontaktaufnahmen Plan", "Kontaktaufnahmen IST"])
    rating.append(["VK", 12, 3])
    ws = wb.create_sheet("Intermediäre")
    ws.append(["Übersicht Intermediäre"] + [None] * 16 + ["Auswertung 2026"])
    ws.append(COCKPIT_HEADER)
    for firm, cat, person, role, email, plz, city, region, owner, rel, prio, note, first in COCKPIT_ROWS:
        ws.append([firm, cat, person, role, email, None, plz, city, None, None, region, owner, rel, None,
                   "ja" if prio == "B" else None, prio, prio, 1, 0, 0, None, None, note, 1 if first else None,
                   dt.datetime.strptime(first, "%Y-%m-%d") if first else None])
    from openpyxl.comments import Comment
    ws["C4"].comment = Comment("Erika Beispiel:\nHat das Unternehmen gewechselt, neue Adresse folgt", "Erika Beispiel")
    bank = wb.create_sheet("Raiffeisen")
    bank.sheet_state = "hidden"
    bank.append(["Übersicht Netzwerk/Ansprechpartner Raiffeisen"])
    bank.append(["Person", "Bank", "Position", "Bereich", "Mailadresse", "Adresse", "PLZ", "Ort", "Tel", "Region",
                 "Zuständig", None, None, None, None, "Ranking"])
    bank.append([None] * 10 + ["KLA", "DJE", "CGA", "OBK", "VKO", None])
    bank.append(["Sigrid Rainer", "Landesbank Beispiel", "Senior Manager", "Corporate Clients", "sigrid.rainer@lb-beispiel.example",
                 None, None, None, None, "AT", None, None, None, None, "X", "High"])
    bank.append(["Klaus Imberg", "Landesbank Beispiel", "MD", "Head of M&A", "klaus.imberg@lb-beispiel.example",
                 None, None, None, None, "AT, Osteuropa", "X", None, None, None, None, "High"])
    db = wb.create_sheet("Datenbanken")
    db.sheet_state = "hidden"
    db.append(["Datenbanken"])
    db.append(["Firma", "Fokus", "Ansprechpartner", "Position", "Mailadresse"])
    db.append(["Beispieldatenbank", "VC", None, None, None])
    db.append(["[tbd]"])
    helper = wb.create_sheet("Hilfstabelle")
    helper.append(["Kategorie", "Zuständigkeit", None, "Relevanz AT Deal Flow"])
    helper.append(["M&A Advisor", "KL", None, "Hoch"])
    out = out or os.path.join(ROOT, "dev", "fixtures", "agc_cockpit_like.xlsx")
    wb.save(out)
    return out


if __name__ == "__main__":
    print("wrote", template())
    print("wrote", fixture())
    print("wrote", cockpit())
