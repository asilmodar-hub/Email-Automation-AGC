"""Read the contact list, and decide who is written to in a round.

The workbook is only ever read. Headers are matched by meaning, in German or
English, so a list AGC already keeps works without being reshaped; anything
that could not be matched is reported, not guessed.
"""
import datetime as dt
import re

import openpyxl

from paths import long_path

# field -> header spellings that mean it (compared lower-case, punctuation removed)
FIELDS = {
    "first": ["first name", "firstname", "vorname", "given name"],
    "last": ["last name", "lastname", "surname", "nachname", "familienname", "name"],
    "title": ["title", "titel", "akad titel", "academic title"],
    "gender": ["salutation", "anrede", "gender", "geschlecht", "mr ms", "herr frau"],
    "company": ["company", "firma", "unternehmen", "organisation", "organization", "kanzlei", "firm"],
    "role": ["role", "position", "funktion", "job title", "rolle"],
    "type": ["type", "contact type", "category", "kategorie", "typ", "kontakttyp", "art", "kontaktart"],
    "email": ["email", "e mail", "mail", "email address", "e mail adresse", "emailadresse"],
    "language": ["language", "sprache", "lang"],
    "form": ["form", "sie du", "du sie", "address form", "anredeform", "formality"],
    "owner": ["owner", "agc owner", "agc contact", "betreuer", "verantwortlich", "agc ansprechpartner",
              "relationship owner"],
    "relationship": ["relationship", "beziehung", "how we know them", "bekannt durch", "kontext",
                     "context"],
    "sector": ["sector focus", "sector", "branche", "branchenfokus", "focus", "fokus", "schwerpunkt"],
    "notes": ["notes", "note", "notizen", "notiz", "bemerkung", "bemerkungen", "anmerkung", "comment",
              "comments", "kommentar"],
    "cadence": ["cadence", "rhythm", "rhythmus", "frequency", "frequenz", "turnus"],
    "dnc": ["do not contact", "dnc", "nicht kontaktieren", "opt out", "optout", "kein kontakt"],
    "greeting": ["greeting", "greeting override", "begruessung", "begrüßung", "grussformel"],
}
REQUIRED = ["email", "last"]
OPTIONAL = ("greeting", "cadence", "type")

# What kind of contact someone is, for the chart on the Contacts tab. Taken from
# the Type column when there is one; otherwise read off the firm's name and the
# role. First match wins, so the narrow words come before the broad ones.
TYPE_RULES = [
    ("Law firm", ["rechtsanw", "anwalt", "anwält", "kanzlei", "legal", "law", "attorney", "notar", "solicitor"]),
    ("Tax / audit", ["steuerberat", "wirtschaftsprüf", "wirtschaftspruef", "tax", "audit", "treuhand",
                     "accounting", "accountant"]),
    ("M&A adviser", ["m&a", "corporate finance", "mergers", "transaction", "investment bank"]),
    ("Venture capital", ["venture", " vc", "vc ", "seed fund"]),
    ("Private equity", ["private equity", "beteiligung", "buyout", "buy-out", " pe ", "family office"]),
    ("Bank", ["bank", "sparkasse", "raiffeisen", "volksbank", "kreditinstitut"]),
    ("Consultant", ["consult", "berat", "advisory", "adviser", "advisor", "interim"]),
]
OTHER_TYPE = "Other"


def _type_of(text):
    low = " %s " % str(text or "").lower()
    for name, words in TYPE_RULES:
        if any(w in low for w in words):
            return name
    return ""


def contact_type(given, company, role):
    """(type, guessed). A value in the Type column always wins: a known kind is
    put under its usual name, anything else is kept as the list has it."""
    given = str(given or "").strip()
    if given:
        return (_type_of(given) or given[:1].upper() + given[1:]), False
    return (_type_of(company) or _type_of(role) or OTHER_TYPE), True

CADENCE_DAYS = {"quarterly": 80, "half_yearly": 170, "yearly": 350}
RECENT_GUARD_DAYS = 30

EMAIL_RE = re.compile(r"^[^@\s,;]+@[^@\s,;]+\.[^@\s,;]{2,}$")


def _norm(text):
    return re.sub(r"[^a-z0-9äöüß]+", " ", str(text or "").lower()).strip()


def _cell(value):
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    return str(value).strip()


def _gender(text):
    t = _norm(text)
    if t in ("herr", "mr", "m", "male", "mann", "männlich", "maennlich", "hr"):
        return "m"
    if t in ("frau", "ms", "mrs", "f", "w", "female", "weiblich", "fr"):
        return "f"
    return ""


def _language(text):
    t = _norm(text)
    if t.startswith(("en", "eng")):
        return "en"
    if t.startswith(("de", "ger", "deu")):
        return "de"
    return ""


def _form(text):
    t = _norm(text)
    if t in ("du", "informal", "first name", "vorname", "per du", "informell"):
        return "du"
    if t in ("sie", "formal", "per sie", "formell"):
        return "sie"
    return ""


def _cadence(text):
    t = _norm(text)
    if not t:
        return ""
    if t.startswith(("q", "viertel")) or "quart" in t:
        return "quarterly"
    if t.startswith(("half", "halb", "semi")) or "6" in t:
        return "half_yearly"
    if t.startswith(("year", "jähr", "jaehr", "annual")) or "12" in t:
        return "yearly"
    if t.startswith(("never", "nie", "none", "kein")):
        return "never"
    return ""


def _yes(text):
    return _norm(text) in ("x", "yes", "ja", "y", "j", "true", "1", "wahr")


def _find_header(ws):
    """The first row among the top ten that looks like the header row."""
    best = (0, None, {})
    for r, row in enumerate(ws.iter_rows(min_row=1, max_row=10, values_only=True), start=1):
        mapping = {}
        for c, value in enumerate(row):
            # "Salutation (Herr/Frau)" is the Salutation column: hints in brackets are dropped
            key = _norm(re.sub(r"\(.*?\)", " ", str(value or "")))
            if not key:
                continue
            for field, names in FIELDS.items():
                if field not in mapping and key in names:
                    mapping[field] = c
                    break
        if len(mapping) > best[0]:
            best = (len(mapping), r, mapping)
    return best


def read_workbook(path):
    """Return {ok, problem, sheet, contacts, missing_columns, unmatched_headers}."""
    out = {"ok": False, "problem": "", "sheet": "", "contacts": [], "missing_columns": [],
           "unmatched_headers": [], "path": path}
    try:
        wb = openpyxl.load_workbook(long_path(path), read_only=True, data_only=True)
    except FileNotFoundError:
        out["problem"] = "The contact list was not found at this path."
        return out
    except PermissionError:
        out["problem"] = "The contact list could not be opened. Windows refused access to it."
        return out
    except Exception as exc:
        out["problem"] = "This file could not be read as an Excel workbook (%s)." % type(exc).__name__
        return out

    found = (0, None, {}, None)
    for ws in wb.worksheets:
        count, row, mapping = _find_header(ws)
        if count > found[0]:
            found = (count, row, mapping, ws)
    count, header_row, mapping, ws = found
    if ws is None or "email" not in mapping:
        wb.close()
        out["problem"] = ("No sheet has a recognisable header row with an Email column. "
                          "Start from the contact template, or name the columns as it does.")
        return out

    out["sheet"] = ws.title
    out["missing_columns"] = [f for f in FIELDS if f not in mapping and f not in OPTIONAL]
    header = next(ws.iter_rows(min_row=header_row, max_row=header_row, values_only=True))
    matched = set(mapping.values())
    out["unmatched_headers"] = [_cell(v) for c, v in enumerate(header) if _cell(v) and c not in matched]

    seen = {}
    for r, row in enumerate(ws.iter_rows(min_row=header_row + 1, values_only=True), start=header_row + 1):
        get = lambda f: _cell(row[mapping[f]]) if f in mapping and mapping[f] < len(row) else ""
        if not any(_cell(v) for v in row):
            continue
        email = get("email").lower()
        contact = {
            "row": r, "id": email or "row-%d" % r,
            "first": get("first"), "last": get("last"), "title": get("title"),
            "gender": _gender(get("gender")), "company": get("company"), "role": get("role"),
            "email": email, "language": _language(get("language")), "form": _form(get("form")),
            "owner": get("owner"), "relationship": get("relationship"), "sector": get("sector"),
            "notes": get("notes"), "cadence": _cadence(get("cadence")), "dnc": _yes(get("dnc")),
            "greeting": get("greeting"), "problems": [], "assumed": [],
        }
        contact["type"], contact["type_guessed"] = contact_type(get("type"), contact["company"], contact["role"])
        if not contact["first"] and " " in contact["last"]:
            # one "Name" column holding "First Last"
            contact["first"], contact["last"] = contact["last"].rsplit(" ", 1)
        if not email:
            contact["problems"].append("no email address")
        elif not EMAIL_RE.match(email):
            contact["problems"].append("email address looks wrong")
        elif email in seen:
            contact["problems"].append("same email as row %d" % seen[email])
        else:
            seen[email] = r
        if not contact["last"] and not contact["first"]:
            contact["problems"].append("no name")
        if not contact["language"]:
            contact["language"] = "de"
            contact["assumed"].append("language not given, German assumed")
        if not contact["form"]:
            contact["form"] = "sie"
            contact["assumed"].append("Sie/du not given, Sie assumed")
        out["contacts"].append(contact)
    wb.close()
    out["ok"] = True
    return out


# ---- greeting ---------------------------------------------------------------

def greeting(c):
    """The salutation line. Worked out by rule, never written by the AI: a wrong
    'Herr' or a missing 'Dr.' is the mistake a recipient does not forgive.
    Returns (line, warning or '')."""
    if c.get("greeting"):
        line = c["greeting"].strip()
        return (line if line.endswith(",") else line + ","), ""
    first, last, title, g = c.get("first", ""), c.get("last", ""), c.get("title", ""), c.get("gender", "")
    titled_last = " ".join(p for p in (title, last) if p)
    if c.get("language") == "en":
        if c.get("form") == "du":
            return ("Dear %s," % first, "") if first else ("Dear %s," % titled_last, "no first name")
        if title.lower().rstrip(".") in ("dr", "prof", "prof dr"):
            return "Dear %s %s," % (title.rstrip(".") if title.lower().startswith("dr") else title, last), ""
        if g and last:
            return "Dear %s %s," % ("Mr" if g == "m" else "Ms", last), ""
        return "Dear %s," % " ".join(p for p in (first, last) if p), "Mr/Ms not given"
    if c.get("form") == "du":
        if not first:
            return "Guten Tag %s," % titled_last, "no first name"
        if g:
            return "%s %s," % ("Lieber" if g == "m" else "Liebe", first), ""
        return "Hallo %s," % first, ""
    if g and last:
        return "%s %s," % ("Sehr geehrter Herr" if g == "m" else "Sehr geehrte Frau", titled_last), ""
    return ("Guten Tag %s," % " ".join(p for p in (title, first, last) if p)), "Herr/Frau not given"


# ---- who is in this round ---------------------------------------------------

def _tokens(text):
    return {t for t in _norm(text).split() if len(t) > 1}


def is_mine(contact, owner_name, my_email):
    owner = contact.get("owner", "")
    if not owner:
        return True
    if my_email and my_email.lower() in owner.lower():
        return True
    mine, theirs = _tokens(owner_name), _tokens(owner)
    return bool(mine and theirs and (mine <= theirs or theirs <= mine))


def select(contacts, settings, my_email, history, suppression, overrides=None, today=None):
    """Mark every contact with included (bool) and reason (why, or why not).

    overrides: {contact id: True/False} set by hand on the Contacts screen. A
    hand override can bring in someone who is not due yet, but never someone
    who asked not to be contacted, and never a row without a usable address."""
    overrides = overrides or {}
    today = today or dt.date.today()
    rhythm = settings.get("schedule", {}).get("mode", "manual")
    default_cadence = rhythm if rhythm in CADENCE_DAYS else ""
    cap = int(settings.get("batch_size") or 50)
    taken = 0
    out = []
    for c in contacts:
        c = dict(c)
        past = history.get(c["email"], {}) if c["email"] else {}
        c["last_sent"] = past.get("last_sent", "")
        c["last_outcome"] = past.get("last_outcome", "")
        c["last_summary"] = past.get("last_summary", "")
        included, reason, hard = True, "due", False
        if c["problems"]:
            included, reason, hard = False, c["problems"][0], True
        elif c["dnc"]:
            included, reason, hard = False, "marked do not contact in the list", True
        elif c["email"] in suppression:
            included, reason, hard = False, "asked not to be contacted", True
        elif not is_mine(c, settings.get("owner_name", ""), my_email):
            included, reason = False, "belongs to %s" % c["owner"]
        elif c["cadence"] == "never":
            included, reason = False, "cadence set to never"
        elif c["last_sent"]:
            days = (today - dt.date.fromisoformat(c["last_sent"][:10])).days
            need = CADENCE_DAYS.get(c["cadence"] or default_cadence, RECENT_GUARD_DAYS)
            if days < need:
                included, reason = False, "written to %d days ago" % days
        else:
            reason = "never written to"
        forced = overrides.get(c["id"])
        if not hard and forced is not None and forced != included:
            included, reason = forced, ("added by hand" if forced else "left out by hand")
        if included:
            if taken >= cap:
                included, reason = False, "over the batch size of %d, next round" % cap
            else:
                taken += 1
        c["included"], c["reason"], c["locked"] = included, reason, hard
        out.append(c)
    return out
