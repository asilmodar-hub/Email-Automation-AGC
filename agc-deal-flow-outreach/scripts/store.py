"""Where the tool keeps what it knows, and how it is written safely.

Two places:

  the user's own folder   %LOCALAPPDATA%\\AGC-DealFlow
      settings.json       everything set in the UI, saved on every change
      server.json         where the running app listens (port, token)
      jobs\\               work handed to Claude and what came back
      attachments\\        files to go out with the emails, one folder each

  next to the contact list   <workbook folder>\\Deal Flow Outreach data
      rounds\\<round>__<sender>.json    one file per round and sender
      suppression.json                 people who asked not to be contacted

Each round file is written by one person only, so a list on a shared drive
gives a firm-wide tracker without two people writing to the same file. The
contact workbook itself is never written to.
"""
import datetime as dt
import hashlib
import json
import os
import re
import tempfile

VERSION = "1.2"
DATA_FOLDER_NAME = "Deal Flow Outreach data"

DEFAULT_SETTINGS = {
    "language": "en",            # the screen's language: en | de
    "theme": "system",           # light | dark | system (follows Windows)
    "workbook": "",
    "owner_name": "",            # how this user appears in the Owner column
    "owner_code": "",            # their short form in AGC's Zuständigkeit column, e.g. VK
    "unassigned_mine": None,     # a contact nobody is responsible for counts as this user's (None: decided by the list)
    "filters": {                 # who this user writes to, on top of what is due
        "countries": [], "states": [], "priorities": [], "relevance": [], "types": [],
    },
    "personalize": True,         # Claude adjusts each email to what the list says about the person
    "sync_forms": True,          # writing the Sie version has Claude write the du version, and back
    "batch_size": 50,
    "gap_min_seconds": 20,
    "gap_max_seconds": 40,
    "followup_after_days": 14,
    "schedule": {
        "mode": "manual",        # manual | quarterly | half_yearly | yearly | date
        "start_date": "",        # YYYY-MM-DD: first run, and the anchor of the rhythm
        "time": "09:00",
        "auto_send": False,      # on a scheduled run, send without waiting for a review
        "confirmed": None,       # what Claude last registered with the scheduler
    },
    # master emails, keyed de_sie | de_du | en and fu_de_sie | fu_de_du | fu_en
    # (follow-ups); filled from assets\templates the first time the app starts
    "templates": {},
    # which German version Claude wrote from which: {key: {from, hash, at}}
    "template_sync": {},
    # files that go out with every email of a round: {round: [...], followup: [...]},
    # each {id, name, size}; the file itself is in attachments\<id>\<name>
    "attachments": {"round": [], "followup": []},
}


def home():
    base = os.environ.get("AGC_OUTREACH_HOME")
    if not base:
        base = os.path.join(os.environ.get("LOCALAPPDATA") or os.path.expanduser("~"), "AGC-DealFlow")
    os.makedirs(base, exist_ok=True)
    return base


def now():
    return dt.datetime.now().replace(microsecond=0)


def stamp(when=None):
    return (when or now()).isoformat(timespec="seconds")


def parse_stamp(text):
    try:
        return dt.datetime.fromisoformat(text)
    except (TypeError, ValueError):
        return None


def read_json(path, default=None):
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return default


def write_json(path, data):
    """Write the whole file or none of it: a half-written round file would lose
    the record of who has already been written to."""
    folder = os.path.dirname(path)
    os.makedirs(folder, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".tmp-", suffix=".json", dir=folder)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False, indent=1)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)


def slug(text):
    return re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-") or "unknown"


# ---- settings ---------------------------------------------------------------

def _merge(base, extra):
    out = dict(base)
    for key, value in (extra or {}).items():
        if isinstance(value, dict) and isinstance(out.get(key), dict) and key != "attachments":
            out[key] = _merge(out[key], value)
        else:
            out[key] = value
    return out


def settings_path():
    return os.path.join(home(), "settings.json")


def load_settings():
    return _merge(DEFAULT_SETTINGS, read_json(settings_path(), {}))


def save_settings(patch):
    """Merge a change into the saved settings and return the result."""
    merged = _merge(load_settings(), patch)
    write_json(settings_path(), merged)
    return merged


# ---- the data folder next to the workbook -----------------------------------

def data_dir(workbook):
    """The shared folder beside the contact list, or a private one if that
    place cannot be written to (a read-only share, for instance)."""
    if not workbook:
        return None
    wanted = os.path.join(os.path.dirname(os.path.abspath(workbook)), DATA_FOLDER_NAME)
    try:
        os.makedirs(os.path.join(wanted, "rounds"), exist_ok=True)
        probe = os.path.join(wanted, ".write-test")
        with open(probe, "w") as fh:
            fh.write("ok")
        os.remove(probe)
        return wanted
    except OSError:
        key = hashlib.sha1(os.path.abspath(workbook).lower().encode("utf-8")).hexdigest()[:10]
        fallback = os.path.join(home(), "data", key)
        os.makedirs(os.path.join(fallback, "rounds"), exist_ok=True)
        return fallback


# ---- attachments ---------------------------------------------------------------

ATTACHMENT_MAX_BYTES = 20 * 1024 * 1024


def attachments_dir():
    path = os.path.join(home(), "attachments")
    os.makedirs(path, exist_ok=True)
    return path


def safe_name(name):
    """A file name Windows accepts, without any folder in it."""
    name = os.path.basename(str(name or "").replace("\\", "/")).strip().strip(".")
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name)
    return name[:120] or "attachment"


def add_attachment(name, data):
    """Keep a copy of the file in the user's own folder. Returns {id, name, size}."""
    if len(data) > ATTACHMENT_MAX_BYTES:
        raise ValueError("too large")
    att_id = hashlib.sha1(data).hexdigest()[:12]
    name = safe_name(name)
    folder = os.path.join(attachments_dir(), att_id)
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, name)
    if not os.path.exists(path):
        with open(path, "wb") as fh:
            fh.write(data)
    return {"id": att_id, "name": name, "size": len(data)}


def attachment_path(att):
    return os.path.join(attachments_dir(), safe_name(att.get("id", "")), safe_name(att.get("name", "")))


def round_path(folder, round_id, sender):
    return os.path.join(folder, "rounds", "%s__%s.json" % (round_id, slug(sender)))


def save_round(folder, rnd):
    rnd["updated"] = stamp()
    write_json(round_path(folder, rnd["id"], rnd["sender"]), rnd)


def load_rounds(folder):
    """Every round in the folder, from every sender, newest first."""
    out = []
    rounds_dir = os.path.join(folder or "", "rounds")
    if not folder or not os.path.isdir(rounds_dir):
        return out
    for name in os.listdir(rounds_dir):
        if name.endswith(".json") and not name.startswith("."):
            rnd = read_json(os.path.join(rounds_dir, name))
            if isinstance(rnd, dict) and rnd.get("id"):
                out.append(rnd)
    out.sort(key=lambda r: r.get("created", ""), reverse=True)
    return out


def load_suppression(folder):
    return read_json(os.path.join(folder or "", "suppression.json"), {}) if folder else {}


def suppress(folder, email, reason, by):
    data = load_suppression(folder)
    data[email.strip().lower()] = {"reason": reason, "by": by, "when": stamp()}
    write_json(os.path.join(folder, "suppression.json"), data)


def history(rounds):
    """What earlier rounds say about each address: when it was last written to,
    by whom, and how the last answer was classified."""
    out = {}
    for rnd in sorted(rounds, key=lambda r: r.get("created", "")):
        for d in rnd.get("drafts", []):
            if d.get("status") != "sent" or not d.get("sent_at"):
                continue
            entry = out.setdefault(d["to"].lower(), {})
            entry.update(last_sent=d["sent_at"], last_sender=rnd.get("sender", ""),
                         last_round=rnd.get("label", rnd["id"]))
            reply = d.get("reply")
            if reply:
                entry.update(last_outcome=reply.get("outcome", ""),
                             last_summary=reply.get("summary", ""))
            else:
                entry.pop("last_outcome", None)
                entry.pop("last_summary", None)
    return out
