"""Put an email together, and check it before a person sees it.

An email is the sender's own master text with the greeting on top. The
greeting is worked out by rule from the contact's row (contacts.greeting);
nothing else differs from one contact to the next unless the reviewer changes
an email by hand or asks Claude to change it.

The checks below are what stands between a mistake and the review screen. Each
one is something a recipient would notice. Checks about wording only look at
the lines that differ from the master text: the master text is the sender's
own, and nobody needs their own sentences marked.
"""
import re

import contacts as contacts_mod

TEMPLATE_KEYS = ("de_sie", "de_du", "en")
FOLLOWUP_PREFIX = "fu_"
LEFTOVER_RE = re.compile(r"\{[a-zA-Z_ ]{2,30}\}|\[\[.*?\]\]|\bXXX\b|\bTODO\b|<[a-zA-Z_ ]{3,30}>")

# Phrasings that make a reader think "this was generated".
MACHINE_PHRASES = [
    "hope this email finds you well", "hope this message finds you well", "i hope you are doing well",
    "i wanted to reach out", "i am reaching out", "touch base", "circle back", "delve", "leverage",
    "synerg", "in today's", "fast-paced", "ever-evolving", "landscape", "thrilled", "excited to",
    "valued", "esteemed", "seamless", "tailored", "game-chang", "unlock", "at the forefront",
    "ich hoffe, diese e-mail erreicht", "ich hoffe, diese nachricht erreicht", "ich hoffe, diese mail erreicht",
    "in der heutigen", "schnelllebig", "maßgeschneidert", "nahtlos", "synergie", "geschätzt",
    "es wäre mir eine freude", "zögern sie nicht", "do not hesitate", "don't hesitate",
]
DE_WORDS = set("der die das und ich wir sie ist nicht mit für auf dass ein eine den dem wie bei uns auch "
               "noch nach zu im haben hat war sind ihre ihren ihnen dir dein euch über wieder seit".split())
EN_WORDS = set("the and you your our are was were with for that this have has not from would about been "
               "since when which will it is of to in on at we us again".split())


def template_key(contact):
    if contact.get("language") == "en":
        return "en"
    return "de_du" if contact.get("form") == "du" else "de_sie"


def _formal_address(text):
    """Is someone addressed as Sie? A capital Sie or Ihr inside a sentence is
    the formal address; at the start of a sentence it may just be 'they'."""
    if re.search(r"\b(Ihnen|Ihre[rnms]|Ihrerseits)\b", text):
        return True
    for m in re.finditer(r"\b(Sie|Ihre?)\b", text):
        before = text[:m.start()].rstrip(" ")
        if before and before[-1] not in ".!?:\n":
            return True
    return False


def _informal_address(text):
    return bool(re.search(r"\b(du|dich|dir|dein\w*|euch|euer\w*)\b", text, re.IGNORECASE))


def template_problems(templates):
    """What is wrong with the master emails, as sentences for the Setup screen."""
    out = {}
    for prefix in ("", FOLLOWUP_PREFIX):
        for key in TEMPLATE_KEYS:
            t = (templates or {}).get(prefix + key) or {}
            body, issues = t.get("body", ""), []
            if not body.strip():
                issues.append("empty: contacts who need this version are held back")
            else:
                if not t.get("subject", "").strip():
                    issues.append("no subject line")
                if re.search(r"\[\[.*?\]\]", body, re.DOTALL):
                    issues.append("a [[note to fill in]] is still in the text")
                elif LEFTOVER_RE.search(body):
                    issues.append("a placeholder is in the text: %s" % LEFTOVER_RE.search(body).group(0))
                if key == "de_sie" and _informal_address(body):
                    issues.append("uses du, but this is the Sie version")
                if key == "de_du" and _formal_address(body):
                    issues.append("uses Sie, but this is the du version")
            out[prefix + key] = issues
    return out


def assemble(template_body, contact):
    """The email for one contact: their greeting, then the master text."""
    text = "\n".join(line.rstrip() for line in (template_body or "").replace("\r\n", "\n").split("\n"))
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    return contacts_mod.greeting(contact)[0] + "\n\n" + text


def changed_lines(body, standard):
    """The lines of an email that are not in the master version of it. Capitals
    are ignored: a sentence that only went from "ich melde" to "Ich melde"
    because a line was put before it has not changed."""
    usual = {line.strip().lower() for line in (standard or "").split("\n")}
    return [line.strip() for line in (body or "").split("\n")
            if line.strip() and line.strip().lower() not in usual]


def _words(text):
    return re.findall(r"[a-zäöüß']+", (text or "").lower())


def _language_of(text):
    words = _words(text)
    de = sum(w in DE_WORDS for w in words)
    en = sum(w in EN_WORDS for w in words)
    if max(de, en) < 3 or abs(de - en) < 2:
        return ""
    return "de" if de > en else "en"


def _profile_text(contact):
    return " ".join(str(contact.get(k, "")) for k in
                    ("first", "last", "title", "company", "role", "relationship", "sector", "notes",
                     "last_sent", "last_summary"))


def check(draft, contact, others):
    """Return a list of {id, level, text}; level is 'fail' or 'warn'.

    others: the other contacts of the same round, for the one check that only
    makes sense across a batch (somebody else's name in this email)."""
    out = []
    add = lambda cid, level, text: out.append({"id": cid, "level": level, "text": text})
    body, standard = draft.get("body", ""), draft.get("standard", "")
    lang, form = contact.get("language"), contact.get("form")

    if not draft.get("subject", "").strip():
        add("subject", "fail", "No subject line.")
    if not body.strip():
        add("empty", "fail", "The email is empty.")
        return out
    left = LEFTOVER_RE.search(body) or LEFTOVER_RE.search(draft.get("subject", ""))
    if left:
        add("placeholder", "fail", "A placeholder was left in the text: %s" % left.group(0))

    # the greeting is the rule's, and names the right person
    want, warning = contacts_mod.greeting(contact)
    first_line = body.strip().split("\n", 1)[0].strip()
    if first_line != want:
        name = contact.get("first") if (form == "du" and contact.get("first")) else contact.get("last")
        if name and name.lower() not in first_line.lower():
            add("greeting", "fail", "The greeting does not name %s. Expected: %s" % (name, want))
        else:
            add("greeting", "warn", "The greeting was changed. The list gives: %s" % want)
    if warning:
        add("greeting-data", "warn", "%s in the list, so the greeting is a neutral one." % warning.capitalize())

    # Sie and du do not mix
    if lang == "de":
        if form == "sie" and _informal_address(body):
            add("register", "fail", "Uses du, but the list says Sie.")
        if form == "du" and _formal_address(body):
            add("register", "fail", "Uses Sie, but the list says du.")

    # the rest only concerns what was changed for this contact
    changed = " ".join(line for line in changed_lines(body, standard) if line != first_line)
    if not changed:
        return out

    own, usual = _profile_text(contact).lower(), standard.lower()
    for other in others:
        for value in (other.get("last", ""), other.get("company", "")):
            v = value.strip()
            if len(v) < 4 or v.lower() in own or v.lower() in usual:
                continue
            if re.search(r"(?<![\wäöüß])%s(?![\wäöüß])" % re.escape(v), changed, re.IGNORECASE):
                add("wrong-name", "fail", "Mentions \"%s\", which belongs to another contact (%s %s)."
                    % (v, other.get("first", ""), other.get("last", "")))

    written_in = _language_of(changed)
    if written_in and written_in != lang:
        add("language", "fail", "The changed lines read as %s, but the list says %s."
            % ("German" if written_in == "de" else "English", "German" if lang == "de" else "English"))

    # nothing claimed that neither the list nor the reviewer's own note says
    known = _profile_text(contact) + " " + str(draft.get("note", ""))
    if draft.get("changed_by") == "claude":
        for number in sorted(set(re.findall(r"\d{2,}", changed))):
            if number not in known:
                add("unsupported", "warn", "Mentions \"%s\", which is neither in this contact's row nor in "
                                           "your note." % number)
        hits = [p for p in MACHINE_PHRASES if p in changed.lower()]
        if hits:
            add("tone", "warn", "Reads as generated: \"%s\"." % "\", \"".join(hits[:3]))
        if "—" in changed or " – " in changed:
            add("tone", "warn", "A long dash in the changed lines; people rarely type one.")
    return out


def worst(checks):
    levels = {c["level"] for c in checks}
    return "fail" if "fail" in levels else ("warn" if "warn" in levels else "ok")
