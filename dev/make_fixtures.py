#!/usr/bin/env python3
"""Build the contact template that ships with the skill, and a list of 50
invented contacts to test with.

    python dev/make_fixtures.py

Writes  agc-deal-flow-outreach/assets/Contacts_Template.xlsx
        dev/fixtures/contacts_50.xlsx

Every person and firm in the fixture is made up, and every address ends in
.example, which cannot receive mail.
"""
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


def template():
    wb = openpyxl.Workbook()
    sheet(wb, [
        ["Herr", "Dr.", "Max", "Mustermann", "Mustermann & Partner Rechtsanwälte", "Partner, M&A", "Law firm",
         "max.mustermann@kanzlei.example", "DE", "Sie", "", "Gemeinsames Mandat 2023 (Verkauf eines "
         "Maschinenbauers); zuletzt im Frühjahr telefoniert", "Mittelstand, Nachfolge", "", "", "", ""],
        ["Frau", "", "Erika", "Musterfrau", "Musterfrau Consulting", "Managing Director", "",
         "erika@consulting.example", "EN", "du", "", "Met at a conference in Vienna, 2024",
         "Industrial services", "", "yearly", "", ""],
    ])
    out = os.path.join(ROOT, "agc-deal-flow-outreach", "assets", "Contacts_Template.xlsx")
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


if __name__ == "__main__":
    print("wrote", template())
    print("wrote", fixture())
