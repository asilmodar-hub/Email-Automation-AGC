"""The local app behind the browser screen.

It listens on this computer only (127.0.0.1) and does four things: serves the
screen, keeps the state of the current round, hands work to Claude as jobs and
takes the results back, and talks to Outlook.

The division of labour is deliberate:

  the screen    every decision: which list, which contacts, what is approved,
                when to send
  Claude        adjusting each email to what the list says about the person,
                changing one email when the reviewer asks, writing the du
                version of a Sie master email (and back), looking up a missing
                address online, and reading the answers
  this app      everything mechanical, and the only place an email is sent from

Sending starts in exactly one way: POST /api/send from the screen's Send
button. There is no job type, command or other route that sends.
"""
import base64
import datetime as dt
import hashlib
import io
import json
import os
import random
import re
import secrets
import subprocess
import sys
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

# The tool's private Python does not put a script's own folder on the path, so
# the modules beside this file are not found unless we say where they are.
HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import checks  # noqa: E402
import contacts as contacts_mod  # noqa: E402
import lang  # noqa: E402
import outlook  # noqa: E402
import schedule  # noqa: E402
import store  # noqa: E402

VERSION = store.VERSION
ASSETS = os.path.join(os.path.dirname(HERE), "assets")
UI_DIR = os.path.join(ASSETS, "ui")

IDLE_SHUTDOWN_SECONDS = 45 * 60
CLAUDE_SEEN_WITHIN = 45
OUTCOMES = ["lead", "referral", "later", "decline", "out_of_office", "bounce", "do_not_contact",
            "unrelated"]
TEMPLATE_KEYS = list(checks.TEMPLATE_KEYS) + ["fu_" + k for k in checks.TEMPLATE_KEYS]
# The two German versions of a master email are kept in step: whichever was
# written last, Claude writes the other from it.
COUNTERPART = {"de_sie": "de_du", "de_du": "de_sie", "fu_de_sie": "fu_de_du", "fu_de_du": "fu_de_sie"}
# The note to fill in that the first starter emails carried. A saved master
# email that still has it gets the sentence that replaced it.
OLD_NOTES = {
    "[[ein Satz dazu, wonach AGC sucht: Größe, Branchen, Region, Situation]]":
        "mittelständische Unternehmen im deutschsprachigen Raum, oft in einer Nachfolgesituation oder wenn ein "
        "Eigentümer einen Partner für den nächsten Schritt sucht",
    "[[one sentence on what AGC looks for: size, sectors, region, situation]]":
        "mid-sized companies in the German-speaking countries, often where a succession is open or an owner is "
        "looking for a partner for the next step",
}
# what Claude is given about a contact: the row, as the list has it
CONTACT_FIELDS = ("first", "last", "title", "gender", "company", "role", "department", "type", "language", "form",
                  "relationship", "sector", "notes", "todos", "city", "region", "country", "state", "postcode",
                  "address", "phone", "website", "priority", "relevance", "first_contact_date", "owner", "others",
                  "comments", "extra", "sheet", "row", "email", "last_sent", "last_outcome", "last_summary")
# what the screen needs of each contact on the Contacts tab
SCREEN_FIELDS = ("id", "row", "sheet", "first", "last", "title", "company", "role", "type", "type_guessed", "email",
                 "language", "form", "owner", "country", "state", "city", "region", "priority", "relevance",
                 "research", "included", "reason", "locked", "assumed", "last_sent", "problems")
MIME = {".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8",
        ".css": "text/css; charset=utf-8", ".svg": "image/svg+xml", ".ico": "image/x-icon"}

SCHEDULED_PROMPT = (
    "Use the agc-deal-flow-outreach skill in scheduled mode. A deal-flow outreach round is due "
    "today. Follow the skill's \"Scheduled run\" section: start the app with the --scheduled "
    "option, which prepares the round and opens the review screen, and tell the user what it "
    "reports. Do not send anything yourself, and do not press Approve or Send on the screen: the "
    "user sends with the Send button, unless they have switched on sending without review, in "
    "which case the app does it on its own.")


def _tally(values):
    out = {}
    for v in values:
        v = "multi" if v == "MULTI" else v
        out[v] = out.get(v, 0) + 1
    return out


def answered(d):
    """Has this person given their first answer? An absence note is not one."""
    reply = d.get("reply") or {}
    return bool(d.get("pending_reply")) or bool(reply.get("outcome") and reply["outcome"] != "out_of_office")


class Problem(Exception):
    """Something the person at the screen should be told in a sentence."""


def EMAIL_OK(address):
    return bool(address) and bool(contacts_mod.EMAIL_RE.match(address))


def text_hash(*parts):
    return hashlib.sha1("\n\x00".join(str(p or "") for p in parts).encode("utf-8")).hexdigest()[:16]


def contact_for_claude(c):
    return {k: c.get(k, "") for k in CONTACT_FIELDS}


def _starter_templates():
    out = {}
    for key in TEMPLATE_KEYS:
        try:
            with open(os.path.join(ASSETS, "templates", key + ".txt"), encoding="utf-8") as fh:
                text = fh.read().replace("\r\n", "\n")
        except OSError:
            continue
        subject, _, body = text.partition("\n")
        out[key] = {"subject": subject.replace("Subject:", "", 1).strip(), "body": body.strip()}
    return out


class App:
    def __init__(self):
        self.lock = threading.RLock()
        self.token = secrets.token_urlsafe(18)
        self.settings = store.load_settings()
        missing = {k: v for k, v in _starter_templates().items() if k not in self.settings["templates"]}
        if missing:
            self.settings = store.save_settings({"templates": missing})
        noted = {}
        for key, tpl in self.settings["templates"].items():
            body = tpl.get("body", "")
            for note, sentence in OLD_NOTES.items():
                body = body.replace(note, sentence)
            if body != tpl.get("body", ""):
                noted[key] = dict(tpl, body=body)
        if noted:
            self.settings = store.save_settings({"templates": noted})
        self.identity = {"ok": False, "email": "", "name": "", "problem": "Checking Outlook…",
                         "checking": True}
        self.book = None            # result of contacts.read_workbook
        self.book_key = None        # (path, mtime) the book was read at
        self.folder = None          # data folder next to the workbook
        self.rounds = []
        self.rounds_read = 0.0
        self.overrides = {}
        self.jobs = []
        self.sending = {"active": False, "total": 0, "done": 0, "current": "", "test": False,
                        "failed": 0, "message": "", "round_id": ""}
        self.checking = {"active": False, "message": "", "last": ""}
        self.stop_sending = threading.Event()
        self.job_ready = threading.Condition(self.lock)
        self.claude_seen = 0.0
        self.ui_seen = time.time()
        self.scheduled = False
        self.notice = ""
        threading.Thread(target=self._load_identity, daemon=True).start()
        self.reload()

    # ---- loading ------------------------------------------------------------

    def _load_identity(self):
        ident = outlook.identity()
        with self.lock:
            self.identity = ident
            if ident.get("ok") and not self.settings.get("owner_name"):
                guess = ident["email"].split("@")[0].replace(".", " ").replace("_", " ").title()
                self.settings = store.save_settings({"owner_name": guess})
            if ident.get("ok") and not self.settings.get("owner_code"):
                # "Vsevolod Kornilov" is VK in the Zuständigkeit column
                known = set((self.book or {}).get("owners") or {})
                code = contacts_mod.code_for(ident.get("name") or self.settings.get("owner_name", ""),
                                             ident["email"], known)
                if code:
                    self.settings = store.save_settings({"owner_code": code})
        if ident.get("ok"):
            self.recover()

    def reload(self, force=False):
        """Read the workbook again if it changed, and the rounds beside it."""
        with self.lock:
            path = self.settings.get("workbook", "")
            if not path:
                self.book, self.book_key, self.folder, self.rounds = None, None, None, []
                return
            try:
                key = (path, os.path.getmtime(path))
            except OSError:
                key = (path, None)
            if force or key != self.book_key:
                self.book = contacts_mod.read_workbook(path)
                self.book_key = key
                folder = store.data_dir(path) if self.book["ok"] else None
                if folder != self.folder:
                    self.folder, self.rounds = folder, []
                force = True
            if not self.folder:
                self.rounds = []
            elif force or time.time() - self.rounds_read > 8:
                # This sender's rounds live in memory once loaded: the sending
                # loop and the screen must work on the same objects. Other
                # people's rounds are only ever read, so they come from disk.
                self.rounds_read = time.time()
                me = self.me()
                mine = {r["id"]: r for r in self.rounds if me and r.get("sender") == me}
                self.rounds = [mine.get(r["id"], r) if r.get("sender") == me else r
                               for r in store.load_rounds(self.folder)]

    def recover(self):
        """Pick up where an earlier run of the app stopped."""
        with self.lock:
            self.reload(force=True)
            for rnd in self.my_rounds():
                if rnd.get("status") != "review":
                    continue
                for d in rnd["drafts"]:
                    if d["status"] == "sending":
                        d.update(status="failed", error="The app stopped while this email was being sent. "
                                                        "Look in Sent Items before sending it again.")
                for d in rnd["drafts"]:
                    if d["status"] == "waiting":
                        self._fetch_and_rewrite(rnd, d)
                preparing = [d for d in rnd["drafts"] if d["status"] == "preparing"]
                if preparing:
                    self._queue_personalize(rnd, preparing)
                looking = [d for d in rnd["drafts"] if d["status"] == "research"]
                if looking:
                    self._queue_research(rnd, looking)
                store.save_round(self.folder, rnd)

    def me(self):
        return self.identity.get("email", "")

    def my_rounds(self):
        return [r for r in self.rounds if r.get("sender") == self.me()]

    def current_round(self):
        """The round on the review screen: this sender's newest that is not closed."""
        for rnd in self.my_rounds():
            if rnd.get("status") == "review":
                return rnd
        return None

    def find_round(self, round_id, mine=True):
        for rnd in (self.my_rounds() if mine else self.rounds):
            if rnd["id"] == round_id:
                return rnd
        raise Problem("That round no longer exists.")

    def selected(self):
        if not self.book or not self.book["ok"]:
            return []
        rows = contacts_mod.select(self.book["contacts"], self.settings, self.me(),
                                   store.history(self.rounds), store.load_suppression(self.folder),
                                   self.overrides)
        templates = self.settings["templates"]
        names = {"de_sie": "German (Sie)", "de_du": "German (du)", "en": "English"}
        for c in rows:
            key = checks.template_key(c)
            if c["included"] and not (templates.get(key) or {}).get("body", "").strip():
                c["included"], c["reason"] = False, "no %s master email yet" % names[key]
        return rows

    # ---- jobs for Claude ------------------------------------------------------

    def add_job(self, kind, payload, replace=False, key=""):
        """replace: a queued job of the same type (and the same key, if one is
        given) is dropped, because this one supersedes it."""
        with self.lock:
            if replace:
                self.jobs = [j for j in self.jobs if not (j["type"] == kind and j["status"] == "queued"
                                                          and j.get("key", "") == key)]
            job = {"id": uuid.uuid4().hex[:8], "type": kind, "status": "queued", "created": store.stamp(),
                   "payload": payload, "done": 0, "total": payload.get("count", 1), "error": "", "key": key}
            self.jobs.append(job)
            self.job_ready.notify_all()
            return job

    def next_job(self, wait):
        """Hand Claude the next job, waiting up to `wait` seconds for one. A job
        taken but never answered is handed out again, so a restart loses nothing."""
        deadline = time.time() + wait
        with self.lock:
            while True:
                self.claude_seen = time.time()
                for status in ("queued", "taken"):
                    for job in self.jobs:
                        if job["status"] == status:
                            job["status"] = "taken"
                            return job
                left = deadline - time.time()
                if left <= 0:
                    return None
                self.job_ready.wait(min(left, 5))

    def job(self, job_id):
        for job in self.jobs:
            if job["id"] == job_id:
                return job
        raise Problem("There is no job %s. It may belong to an earlier start of the app." % job_id)

    def finish_job(self, job, error=""):
        job["status"] = "failed" if error else "done"
        job["error"] = error

    def give_up(self, job, reason):
        """Claude could not do a job: whatever waits on it goes back to the reviewer."""
        self.finish_job(job, reason)
        p = job["payload"]
        try:
            rnd = self.find_round(p["round_id"]) if p.get("round_id") else None
        except Problem:
            rnd = None
        if rnd is None:
            return
        if job["type"] == "rewrite":
            draft = next((d for d in rnd["drafts"] if d["contact_id"] == p["contact_id"]), None)
            if draft is not None and draft["status"] == "waiting":
                draft["status"] = "pending"
                name = " ".join(filter(None, [draft["contact"].get("first"), draft["contact"].get("last")]))
                self.notice = "Claude could not change the email for %s: %s" % (name or draft["to"], reason)
        elif job["type"] == "personalize":
            for d in rnd["drafts"]:
                if d["status"] == "preparing":
                    d["status"] = "pending"
            self._after_preparing(rnd)
        elif job["type"] == "research":
            for d in rnd["drafts"]:
                if d["status"] == "research":
                    d["status"] = "pending"
                    d["research"] = dict(d.get("research") or {}, status="nothing",
                                         found={"note": reason}, accepted=False)
        self.recheck(rnd)
        store.save_round(self.folder, rnd)

    # ---- a round --------------------------------------------------------------

    def start_round(self, kind="round", parent=None):
        with self.lock:
            if not self.identity.get("ok"):
                raise Problem("Outlook is not ready: %s" % self.identity.get("problem", ""))
            if self.current_round():
                raise Problem("A round is already open. Finish or close it first.")
            if kind == "followup":
                people = self._followup_people(parent)
                label = "Follow-up to %s" % parent.get("label", parent["id"])
                prefix = "fu_"
            else:
                people = [c for c in self.selected() if c["included"]]
                label = schedule.round_label()
                prefix = ""
            if not people:
                raise Problem("Nobody is due for this round.")
            rnd = {
                # the time for reading, a few random characters so two rounds never share a file
                "id": store.now().strftime("%Y-%m-%d_%H%M%S") + "-" + uuid.uuid4().hex[:4], "label": label, "kind": kind,
                "parent": parent["id"] if parent else "", "sender": self.me(),
                "sender_name": self.settings.get("owner_name") or self.identity.get("name", ""),
                "created": store.stamp(), "status": "review", "workbook": self.settings["workbook"],
                "templates": {k[len(prefix):]: v for k, v in self.settings["templates"].items()
                              if k.startswith(prefix) and k[len(prefix):] in checks.TEMPLATE_KEYS},
                "drafts": [],
            }
            attachments = (self.settings.get("attachments") or {}).get("followup" if kind == "followup" else "round") or []
            personalize = bool(self.settings.get("personalize", True))
            for c in people:
                key = checks.template_key(c)
                standard = checks.assemble(rnd["templates"].get(key, {}).get("body", ""), c)
                needs = list(c.get("research") or []) if kind != "followup" else []
                status = "research" if needs else ("preparing" if personalize else "pending")
                c = {k: v for k, v in c.items() if k not in ("included", "reason", "locked")}
                rnd["drafts"].append({
                    "contact_id": c["id"], "contact": c, "to": c["email"] if EMAIL_OK(c["email"]) else "",
                    "template": key, "subject": rnd["templates"].get(key, {}).get("subject", ""),
                    "body": standard, "standard": standard, "greeting": "", "changed_by": "", "note": "",
                    "status": status, "checks": [], "level": "ok", "sent_at": "",
                    "conversation_id": "", "error": "", "reply": None, "seen": [],
                    "attachments": [dict(a) for a in attachments],
                    "research": {"needed": needs, "status": "waiting"} if needs else None,
                })
            self.recheck(rnd)
            self.rounds.insert(0, rnd)
            store.save_round(self.folder, rnd)
            self.overrides = {}
            preparing = [d for d in rnd["drafts"] if d["status"] == "preparing"]
            if preparing:
                self._queue_personalize(rnd, preparing)
            looking = [d for d in rnd["drafts"] if d["status"] == "research"]
            if looking:
                self._queue_research(rnd, looking)
            return rnd

    def followup_days(self):
        value = self.settings.get("followup_after_days")
        return 14 if value in (None, "") else max(0, int(value))

    def _followup_people(self, parent):
        after = self.followup_days()
        suppression = store.load_suppression(self.folder)
        already = {d["to"] for r in self.my_rounds() if r.get("parent") == parent["id"]
                   for d in r["drafts"] if d["status"] == "sent"}
        out = []
        for d in parent["drafts"]:
            if d["status"] != "sent" or d["to"] in suppression or d["to"] in already:
                continue
            outcome = (d.get("reply") or {}).get("outcome", "")
            if outcome and outcome != "out_of_office":
                continue
            sent = store.parse_stamp(d["sent_at"])
            if sent and (store.now() - sent).days >= after:
                out.append(dict(d["contact"], last_sent=d["sent_at"]))
        return out

    def _fetch_and_rewrite(self, rnd, draft):
        """Look up what was written with this address before (the reviewer may
        refer to it: "mention the email from two weeks ago"), then hand the
        change to Claude. Outlook is read outside the lock: it can take a while."""
        address = draft.get("to") or draft["contact"].get("email", "")

        def work():
            history = outlook.history(address) if address else []
            with self.lock:
                if draft.get("status") == "waiting":
                    self._queue_rewrite(rnd, draft, history)

        threading.Thread(target=work, daemon=True).start()

    def _queue_rewrite(self, rnd, draft, history=()):
        """Ask Claude to change one email the way the reviewer's note says."""
        c = draft["contact"]
        self.add_job("rewrite", {
            "round_id": rnd["id"], "kind": rnd["kind"], "count": 1,
            "sender": {"name": rnd["sender_name"], "email": rnd["sender"]},
            "contact_id": draft["contact_id"], "note_from_user": draft.get("note", ""),
            "greeting": draft.get("greeting") or contacts_mod.greeting(c)[0], "subject": draft["subject"],
            "email_now": draft["body"], "master_email": draft["standard"],
            "contact": contact_for_claude(c),
            "mail_history": list(history),
            "mail_history_note": "Emails between the sender and %s in the last 12 months, newest first, read from "
                                 "Outlook. Use them only when the reviewer's note refers to an earlier email or "
                                 "conversation." % (draft.get("to") or c.get("email", "")),
            "write": "The whole email as it should read after the change: {contact_id, body} and, only if "
                     "the note asks for it, subject. Read references/01-rewriting.md first.",
        })

    # ---- Claude adjusts the round to the list ------------------------------------

    def _queue_personalize(self, rnd, drafts):
        """Hand Claude the new emails, so each one fits its person: the greeting
        from the name (Herr or Frau, the title), and anything the row asks for."""
        self.add_job("personalize", {
            "round_id": rnd["id"], "kind": rnd["kind"], "count": len(drafts),
            "sender": {"name": rnd["sender_name"], "email": rnd["sender"]},
            "emails": [{"contact_id": d["contact_id"], "template": d["template"], "subject": d["subject"],
                        "email_now": d["body"], "rule_greeting": contacts_mod.greeting(d["contact"])[0],
                        "contact": contact_for_claude(d["contact"])} for d in drafts],
            "write": "One object per email: {contact_id, greeting} and, only if the row gives a reason to change "
                     "the text, body (the whole email). Read references/05-personalizing.md first.",
        }, replace=True, key=rnd["id"])

    def take_personalize(self, job, result):
        rnd = self.find_round(job["payload"]["round_id"])
        wanted = {e["contact_id"] for e in job["payload"]["emails"]}
        by_id = {d["contact_id"]: d for d in rnd["drafts"]}
        problems = []
        for item in result.get("drafts") or []:
            cid = item.get("contact_id")
            draft = by_id.get(cid)
            if cid not in wanted or draft is None:
                problems.append("%r is not an email of this job" % (cid,))
                continue
            greeting = " ".join(str(item.get("greeting") or "").split())
            if not greeting:
                problems.append("%s: greeting is missing" % cid)
                continue
            if not greeting.endswith(","):
                greeting += ","
            wanted.discard(cid)
            if draft["status"] != "preparing":
                continue
            master = rnd["templates"].get(draft["template"], {}).get("body", "")
            draft["greeting"] = greeting
            draft["standard"] = checks.assemble(master, draft["contact"], greeting)
            body = str(item.get("body") or "").replace("\r\n", "\n").strip()
            draft["body"] = body or draft["standard"]
            draft["changed_by"] = "list" if draft["body"] != draft["standard"] else ""
            draft["status"] = "pending"
        job["payload"]["emails"] = [e for e in job["payload"]["emails"] if e["contact_id"] in wanted]
        job["done"] = job["total"] - len(wanted)
        if not wanted:
            self.finish_job(job)
        self.recheck(rnd)
        store.save_round(self.folder, rnd)
        if not wanted:
            self._after_preparing(rnd)
        failed = [{"contact_id": d["contact_id"], "failed_checks": [c["text"] for c in d["checks"] if c["level"] == "fail"]}
                  for d in rnd["drafts"] if d["changed_by"] == "list" and d["level"] == "fail"]
        return {"ok": not problems, "problems": problems, "still_to_do": sorted(wanted), "failed_checks": failed}

    def skip_preparing(self, round_id):
        """The reviewer does not want to wait for Claude: the emails stand with
        the greeting the list gives."""
        rnd = self.find_round(round_id)
        for job in self.jobs:
            if job["type"] == "personalize" and job["payload"].get("round_id") == round_id and \
                    job["status"] in ("queued", "taken"):
                self.finish_job(job, "the reviewer went ahead without it")
        for d in rnd["drafts"]:
            if d["status"] == "preparing":
                d["status"] = "pending"
        self.recheck(rnd)
        store.save_round(self.folder, rnd)
        self._after_preparing(rnd)

    def _after_preparing(self, rnd):
        """A scheduled round that sends without review goes once Claude is done."""
        if rnd.get("auto_send") and not any(d["status"] == "preparing" for d in rnd["drafts"]):
            rnd["auto_send"] = False
            store.save_round(self.folder, rnd)
            self._send_unreviewed(rnd)

    # ---- Claude looks up what the list does not have --------------------------------

    def _queue_research(self, rnd, drafts):
        self.add_job("research", {
            "round_id": rnd["id"], "count": len(drafts),
            "contacts": [dict(contact_for_claude(d["contact"]), contact_id=d["contact_id"],
                              missing=(d.get("research") or {}).get("needed", []), template=d["template"])
                         for d in drafts],
            "write": "One object per contact: {contact_id, email, first, last, title, gender, role, greeting, "
                     "source, confidence, note}; empty strings for what you could not find. Read "
                     "references/06-research.md first.",
        }, replace=True, key=rnd["id"])

    def take_research(self, job, result):
        rnd = self.find_round(job["payload"]["round_id"])
        wanted = {c["contact_id"] for c in job["payload"]["contacts"]}
        by_id = {d["contact_id"]: d for d in rnd["drafts"]}
        problems = []
        for item in result.get("found") or []:
            cid = item.get("contact_id")
            draft = by_id.get(cid)
            if cid not in wanted or draft is None:
                problems.append("%r is not a contact of this job" % (cid,))
                continue
            email = str(item.get("email") or "").strip().lower()
            if email and not EMAIL_OK(email):
                problems.append("%s: %r is not an email address" % (cid, email))
                continue
            source = str(item.get("source") or "").strip()
            if (email or item.get("last")) and not re.match(r"^https?://", source):
                problems.append("%s: say where it was found (source, a web address)" % cid)
                continue
            wanted.discard(cid)
            if draft["status"] not in ("research", "skipped") or (draft.get("research") or {}).get("status") != "waiting":
                continue
            # a contact skipped meanwhile keeps what was found, for when it is put back
            found = {k: " ".join(str(item.get(k) or "").split())[:200]
                     for k in ("first", "last", "title", "role", "greeting", "note", "confidence")}
            found.update(email=email, source=source[:500], gender=item.get("gender") if item.get("gender") in ("m", "f") else "")
            useful = email or (found["last"] and "person" in draft["research"].get("needed", []))
            draft["research"] = dict(draft["research"], status="found" if useful else "nothing",
                                     found=found, accepted=False)
            if draft["status"] == "research":
                draft["status"] = "pending"
        job["payload"]["contacts"] = [c for c in job["payload"]["contacts"] if c["contact_id"] in wanted]
        job["done"] = job["total"] - len(wanted)
        if not wanted:
            self.finish_job(job)
        self.recheck(rnd)
        store.save_round(self.folder, rnd)
        return {"ok": not problems, "problems": problems, "still_to_do": sorted(wanted)}

    def accept_research(self, round_id, contact_id):
        """The reviewer takes what Claude found: the address and the person go
        into this email (never into the list itself)."""
        rnd = self.find_round(round_id)
        draft = next((d for d in rnd["drafts"] if d["contact_id"] == contact_id), None)
        research = (draft or {}).get("research") or {}
        if not draft or research.get("status") != "found":
            raise Problem("There is nothing found online to use for this email.")
        found = research.get("found") or {}
        to = found.get("email") or draft.get("to")
        if to in store.load_suppression(self.folder):
            raise Problem("This address asked not to be contacted.")
        if any(d is not draft and d.get("to") == to for d in rnd["drafts"]):
            raise Problem("Another email of this round already goes to this address.")
        c = draft["contact"]
        for field in ("first", "last", "title", "gender", "role"):
            if found.get(field):
                c[field] = found[field]
        c["email"] = to
        draft["to"] = to
        unchanged = draft["body"] == draft["standard"]
        master = rnd["templates"].get(draft["template"], {}).get("body", "")
        draft["greeting"] = found.get("greeting") or contacts_mod.greeting(c)[0]
        if not draft["greeting"].endswith(","):
            draft["greeting"] += ","
        draft["standard"] = checks.assemble(master, c, draft["greeting"])
        if unchanged:
            draft["body"] = draft["standard"]
        else:
            draft["body"] = draft["greeting"] + "\n" + draft["body"].split("\n", 1)[1] if "\n" in draft["body"] else draft["standard"]
        draft["research"] = dict(research, accepted=True)
        if draft["status"] == "approved":
            draft["status"] = "pending"
        self.recheck(rnd)
        store.save_round(self.folder, rnd)

    def recheck(self, rnd):
        people = [d["contact"] for d in rnd["drafts"]]
        for d in rnd["drafts"]:
            if d["status"] in ("waiting", "sent", "outbox", "preparing", "research"):
                continue
            for att in d.get("attachments") or []:
                att["missing"] = not os.path.isfile(store.attachment_path(att))
            d["checks"] = checks.check(d, d["contact"], [c for c in people if c is not d["contact"]])
            d["level"] = checks.worst(d["checks"])

    def take_rewrite(self, job, result):
        rnd = self.find_round(job["payload"]["round_id"])
        cid = job["payload"]["contact_id"]
        draft = next((d for d in rnd["drafts"] if d["contact_id"] == cid), None)
        if draft is None or draft["status"] != "waiting":
            self.finish_job(job)
            return {"ok": True, "note": "This email is no longer waiting for a rewrite."}
        item = next((i for i in result.get("drafts") or [] if i.get("contact_id") == cid), None)
        body = str((item or {}).get("body") or "").replace("\r\n", "\n").strip()
        if not body:
            return {"ok": False, "problems": ['Hand back {"drafts": [{"contact_id": "%s", "body": '
                                              '"the whole email"}]}' % cid]}
        draft.update(body=body, status="pending", error="",
                     changed_by="claude" if body != draft["standard"] else "")
        # numbers from the earlier emails are not made up when the note referred to them
        history = " ".join("%s %s" % (m.get("subject", ""), m.get("text", "")) for m in job["payload"].get("mail_history") or [])
        draft["known_numbers"] = sorted(set(re.findall(r"\d{2,}", history)))[:200]
        if str(item.get("subject") or "").strip():
            draft["subject"] = str(item["subject"]).strip()
        self.finish_job(job)
        self.recheck(rnd)
        store.save_round(self.folder, rnd)
        failed = [c["text"] for c in draft["checks"] if c["level"] == "fail"]
        return {"ok": True, "problems": [], "failed_checks": failed,
                "hint": "The email is back on the review screen with these shown as failed checks. This job "
                        "is closed; the reviewer can ask again or go back to the master email." if failed else ""}

    def update_draft(self, round_id, contact_id, change):
        rnd = self.find_round(round_id)
        draft = next((d for d in rnd["drafts"] if d["contact_id"] == contact_id), None)
        if draft is None:
            raise Problem("That draft no longer exists.")
        if draft["status"] in ("sent", "outbox", "sending"):
            raise Problem("This email has already been sent.")
        if draft["status"] == "waiting":
            raise Problem("Claude is changing this email. It is back in a moment.")
        if draft["status"] in ("preparing", "research") and change != {"status": "skipped"}:
            raise Problem("Claude is still preparing this email. It is ready in a moment.")
        if "status" in change:
            if change["status"] not in ("pending", "approved", "skipped"):
                raise Problem("Unknown status.")
            if change["status"] == "pending" and draft["status"] == "skipped" and draft.get("research") and \
                    draft["research"].get("status") == "waiting":
                change = dict(change, status="research")
            if change["status"] == "approved" and any(c["level"] == "fail" and c["id"] in ("research", "address")
                                                      for c in draft.get("checks") or []):
                raise Problem("Settle the address first: use what Claude found, enter one, or skip this person.")
            draft["status"] = change["status"]
        if "to" in change and change["to"] != draft.get("to"):
            to = str(change["to"] or "").strip().lower()
            if not EMAIL_OK(to):
                raise Problem("This is not an email address.")
            if to in store.load_suppression(self.folder):
                raise Problem("This address asked not to be contacted.")
            draft["to"] = to
            draft["contact"]["email"] = to
            if draft.get("research"):
                draft["research"] = dict(draft["research"], accepted=True, by_hand=True)
            if draft["status"] == "approved":
                draft["status"] = "pending"
        before = (draft["subject"], draft["body"])
        if change.get("reset"):
            draft.update(body=draft["standard"], changed_by="", note="",
                         subject=rnd["templates"].get(draft["template"], {}).get("subject", ""))
        for field in ("subject", "body"):
            if field in change and change[field] != draft[field]:
                draft[field] = str(change[field])
                if field == "body":
                    draft["changed_by"] = "hand" if draft["body"].strip() != draft["standard"].strip() else ""
        if (draft["subject"], draft["body"]) != before and draft["status"] == "approved":
            draft["status"] = "pending"         # a change after approval is looked at again
        self.recheck(rnd)
        store.save_round(self.folder, rnd)

    def approve_all(self, round_id):
        """Approve everything still to review, except what failed a check: a
        wrong name or a leftover placeholder has to be looked at, not waved
        through. Returns how many were left behind for that reason."""
        rnd = self.find_round(round_id)
        left = 0
        for d in rnd["drafts"]:
            if d["status"] == "pending":
                if d["level"] == "fail":
                    left += 1
                else:
                    d["status"] = "approved"
        store.save_round(self.folder, rnd)
        return left

    def redraft(self, round_id, contact_id, note):
        rnd = self.find_round(round_id)
        draft = next((d for d in rnd["drafts"] if d["contact_id"] == contact_id), None)
        if draft is None or draft["status"] in ("sent", "outbox", "sending", "waiting"):
            raise Problem("This email cannot be changed right now.")
        if not note.strip():
            raise Problem("Say what should be different, so Claude knows what to change.")
        draft.update(status="waiting", note=note.strip())
        store.save_round(self.folder, rnd)
        self._fetch_and_rewrite(rnd, draft)

    def close_round(self, round_id):
        rnd = self.find_round(round_id)
        if self.sending["active"]:
            raise Problem("Emails are being sent. Stop the sending first.")
        rnd["status"] = "closed"
        for job in self.jobs:
            if job["type"] in ("rewrite", "personalize", "research") and \
                    job["payload"].get("round_id") == round_id and job["status"] in ("queued", "taken"):
                self.finish_job(job, "the round was closed")
        store.save_round(self.folder, rnd)

    # ---- sending --------------------------------------------------------------

    def send(self, round_id, ids, test, confirm):
        with self.lock:
            if self.sending["active"]:
                raise Problem("Emails are already being sent.")
            if not self.identity.get("ok"):
                raise Problem("Outlook is not ready: %s" % self.identity.get("problem", ""))
            rnd = self.find_round(round_id)
            suppression = store.load_suppression(self.folder)
            queue = []
            for d in rnd["drafts"]:
                if d["contact_id"] not in ids:
                    continue
                if test:
                    if d["status"] not in ("waiting", "sending", "preparing", "research") and d["body"].strip():
                        queue.append(d)
                elif d["status"] == "approved" and EMAIL_OK(d["to"]) and d["to"] not in suppression:
                    queue.append(d)
            if not queue:
                raise Problem("Nothing to send: no approved email is among the ones chosen.")
            if not test and not confirm:
                raise Problem("Sending was not confirmed.")
            if test:
                queue = queue[:5]
            self.stop_sending.clear()
            self.sending = {"active": True, "total": len(queue), "done": 0, "current": "", "test": test,
                            "failed": 0, "message": "", "round_id": round_id}
            if not test:
                for d in queue:
                    d["status"] = "sending"
                store.save_round(self.folder, rnd)
            threading.Thread(target=self._send_loop, args=(rnd, queue, test), daemon=True).start()

    def _gap(self):
        if os.environ.get("AGC_OUTREACH_GAP"):
            return float(os.environ["AGC_OUTREACH_GAP"])
        low = max(1, int(self.settings.get("gap_min_seconds") or 20))
        high = max(low, int(self.settings.get("gap_max_seconds") or 40))
        return random.uniform(low, high)

    def _send_loop(self, rnd, queue, test):
        in_a_row = 0
        message = ""
        for index, draft in enumerate(queue):
            if self.stop_sending.is_set():
                message = "Stopped. %d of %d were sent." % (self.sending["done"], len(queue))
                break
            name = "%s %s" % (draft["contact"].get("first", ""), draft["contact"].get("last", ""))
            with self.lock:
                self.sending["current"] = name.strip()
            to = self.me() if test else draft["to"]
            subject = ("[Test, would go to %s] " % (draft["to"] or "?") if test else "") + draft["subject"]
            paths = [store.attachment_path(a) for a in draft.get("attachments") or []]
            try:
                gone = [os.path.basename(p) for p in paths if not os.path.isfile(p)]
                if gone:
                    raise RuntimeError("The attachment %s is no longer on this computer." % gone[0])
                result = outlook.send(to, subject, draft["body"], paths)
                in_a_row = 0
                with self.lock:
                    if test:
                        draft["tested"] = result["sent_at"]
                    else:
                        draft.update(status=result["state"], sent_at=result["sent_at"],
                                     conversation_id=result["conversation_id"], error="")
                    self.sending["done"] += 1
            except Exception as exc:
                in_a_row += 1
                with self.lock:
                    self.sending["failed"] += 1
                    if not test:
                        draft.update(status="failed", error=str(exc)[:300])
            with self.lock:
                store.save_round(self.folder, rnd)
            if in_a_row >= 3:
                message = "Stopped after three failures in a row. Outlook may be closed or offline."
                break
            if index < len(queue) - 1 and self.stop_sending.wait(0.2 if test else self._gap()):
                message = "Stopped. %d of %d were sent." % (self.sending["done"], len(queue))
                break
        with self.lock:
            for d in queue:
                if d["status"] == "sending":
                    d["status"] = "approved"    # not reached: still approved, still unsent
            if not test and not any(d["status"] in ("waiting", "pending", "approved", "failed")
                                    for d in rnd["drafts"]):
                rnd["status"] = "sent"
            store.save_round(self.folder, rnd)
            done, failed = self.sending["done"], self.sending["failed"]
            if not message:
                where = "to your own address" if test else "from %s" % self.me()
                message = "%d email%s sent %s." % (done, "" if done == 1 else "s", where)
                if failed:
                    message += " %d could not be sent." % failed
            self.sending.update(active=False, current="", message=message)

    # ---- answers --------------------------------------------------------------

    def check_replies(self):
        with self.lock:
            if self.checking["active"]:
                return
            if not self.identity.get("ok"):
                raise Problem("Outlook is not ready: %s" % self.identity.get("problem", ""))
            sent = [(r, d) for r in self.my_rounds() for d in r["drafts"] if d["status"] in ("sent", "outbox")]
            if not sent:
                raise Problem("Nothing has been sent yet, so there are no answers to look for.")
            # Only the first answer counts. Whoever has answered is not looked for again,
            # and the rest of the conversation is left alone.
            self._requeue_unread(sent)
            sent = [(r, d) for r, d in sent if not answered(d)]
            if not sent:
                self.checking = {"active": False, "last": store.stamp(),
                                 "message": "Everyone written to has answered; there is nothing more to look for."}
                return
            self.checking = {"active": True, "message": "Reading the inbox…", "last": self.checking["last"]}
        threading.Thread(target=self._check_loop, args=(sent,), daemon=True).start()

    def _check_loop(self, sent):
        try:
            since = min(store.parse_stamp(d["sent_at"]) or store.now() for _, d in sent)
            found = outlook.scan(since - dt.timedelta(minutes=5), {d["to"] for _, d in sent},
                                 {d["conversation_id"] for _, d in sent if d["conversation_id"]})
            with self.lock:
                to_classify = self._file_answers(sent, found)
                for rnd in {id(r): r for r, _ in sent}.values():
                    store.save_round(self.folder, rnd)
                if to_classify:
                    self._queue_classify(to_classify)
                message = "%d new answer%s found." % (len(to_classify), "" if len(to_classify) == 1 else "s")
                self.checking = {"active": False, "message": message, "last": store.stamp()}
        except Exception as exc:
            with self.lock:
                self.checking = {"active": False, "message": "The inbox could not be read: %s" % str(exc)[:200],
                                 "last": self.checking["last"]}

    def _requeue_unread(self, sent):
        """A first answer that was found but never read by Claude (the app was
        closed in between) is handed to Claude again."""
        open_keys = {(a["round_id"], a["contact_id"]) for j in self.jobs if j["type"] == "classify"
                     and j["status"] in ("queued", "taken") for a in j["payload"]["answers"]}
        again = []
        for rnd, d in sent:
            pending = d.get("pending_reply")
            if pending and not d.get("reply") and (rnd["id"], d["contact_id"]) not in open_keys:
                again.append(self._answer_entry(rnd, d, pending.get("matched_by", "thread"),
                                                [{"received": pending["received"], "subject": pending.get("subject", ""),
                                                  "text": pending["text"]}]))
        if again:
            self._queue_classify(again)

    def _answer_entry(self, rnd, d, matched_by, messages):
        return {"round_id": rnd["id"], "contact_id": d["contact_id"],
                "name": ("%s %s" % (d["contact"].get("first", ""), d["contact"].get("last", ""))).strip(),
                "company": d["contact"].get("company", ""), "our_subject": d["subject"],
                "our_email": d["body"], "matched_by": matched_by, "messages": messages}

    def _queue_classify(self, answers):
        self.add_job("classify", {
            "count": len(answers), "answers": answers, "outcomes": OUTCOMES,
            "language": self.settings.get("language", "en"),
            "write": "One object per answer: {round_id, contact_id, outcome, summary, quote, "
                     "next_step}. Read references/02-replies.md first."})

    def _file_answers(self, sent, found):
        """Attach each message to the email it answers; return what Claude should
        read. Only a person's first answer is taken: an absence note does not
        count as one, a bounce does."""
        fresh = {}
        for m in sorted(found, key=lambda x: x["received"]):
            target = None
            for rnd, d in sent:
                if m.get("conversation_id") and m["conversation_id"] == d["conversation_id"]:
                    target = (rnd, d)
            if target is None:
                same = [(r, d) for r, d in sent if d["to"] == m.get("from_email") and d["sent_at"] <= m["received"]]
                target = max(same, key=lambda p: p[1]["sent_at"]) if same else None
            if target is None:
                continue
            rnd, d = target
            key = "%s|%s|%s" % (m["received"], m.get("from_email", ""), m["subject"])
            if key in d.setdefault("seen", []):
                continue
            d["seen"].append(key)
            if answered(d):
                continue
            reply = d.get("reply") or {}
            if m["kind"] == "bounce":
                d["reply"] = {"outcome": "bounce", "summary": "The email could not be delivered.",
                              "quote": "", "next_step": "Check the address in the contact list.",
                              "received": m["received"], "text": m["text"]}
            elif m["kind"] == "auto":
                if not reply:
                    d["reply"] = {"outcome": "out_of_office", "summary": "Automatic reply.", "quote": "",
                                  "next_step": "", "received": m["received"], "text": m["text"]}
            else:
                fresh[(rnd["id"], d["contact_id"])] = self._answer_entry(
                    rnd, d, m["matched_by"], [{"received": m["received"], "subject": m["subject"], "text": m["text"]}])
                d["pending_reply"] = {"received": m["received"], "text": m["text"], "subject": m["subject"],
                                      "matched_by": m["matched_by"]}
        return list(fresh.values())

    def take_classification(self, job, result):
        problems = []
        wanted = {(a["round_id"], a["contact_id"]) for a in job["payload"]["answers"]}
        for item in result.get("answers") or []:
            key = (item.get("round_id"), item.get("contact_id"))
            if key not in wanted:
                problems.append("%r is not an answer of this job" % (key,))
                continue
            if item.get("outcome") not in OUTCOMES:
                problems.append("%s: outcome must be one of %s" % (key[1], ", ".join(OUTCOMES)))
                continue
            rnd = self.find_round(key[0])
            draft = next(d for d in rnd["drafts"] if d["contact_id"] == key[1])
            pending = draft.pop("pending_reply", None) or {}
            if item["outcome"] == "unrelated":
                wanted.discard(key)
                store.save_round(self.folder, rnd)
                continue
            draft["reply"] = {"outcome": item["outcome"], "summary": str(item.get("summary") or "")[:400],
                              "quote": str(item.get("quote") or "")[:400],
                              "next_step": str(item.get("next_step") or "")[:300],
                              "received": pending.get("received", ""), "text": pending.get("text", "")}
            if item["outcome"] == "do_not_contact":
                store.suppress(self.folder, draft["to"], "asked in an answer: " + draft["reply"]["quote"][:120],
                               self.me())
            wanted.discard(key)
            store.save_round(self.folder, rnd)
        job["payload"]["answers"] = [a for a in job["payload"]["answers"]
                                     if (a["round_id"], a["contact_id"]) in wanted]
        job["done"] = job["total"] - len(wanted)
        if not wanted:
            self.finish_job(job)
        return {"ok": not problems, "problems": problems, "still_to_classify": [k[1] for k in wanted]}

    def set_outcome(self, round_id, contact_id, outcome):
        rnd = self.find_round(round_id)
        draft = next((d for d in rnd["drafts"] if d["contact_id"] == contact_id), None)
        if draft is None:
            raise Problem("That contact is not in this round.")
        if outcome == "":
            draft["reply"] = None
        elif outcome in OUTCOMES:
            draft["reply"] = dict(draft.get("reply") or {"summary": "", "quote": "", "next_step": "",
                                                         "received": "", "text": ""},
                                  outcome=outcome, by_hand=True)
            if outcome == "do_not_contact":
                store.suppress(self.folder, draft["to"], "set by hand in the tracker", self.me())
        else:
            raise Problem("Unknown outcome.")
        store.save_round(self.folder, rnd)

    # ---- the two German versions of a master email -------------------------------------

    def sync_template(self, key):
        """The reviewer finished writing one German version: Claude writes the
        other from it, Sie into du or du into Sie."""
        target = COUNTERPART.get(key)
        if not target:
            raise Problem("Only the German versions are kept in step.")
        if not self.settings.get("sync_forms", True):
            return None
        source = self.settings["templates"].get(key) or {}
        if not source.get("body", "").strip():
            return None
        current = self.settings["templates"].get(target) or {}
        h = text_hash(source.get("subject"), source.get("body"))
        done = (self.settings.get("template_sync") or {}).get(target) or {}
        if done.get("from") == key and done.get("hash") == h:
            return None                      # already written from exactly this text
        return self.add_job("convert", {
            "count": 1, "source_key": key, "target_key": target,
            "source_form": "du" if key.endswith("de_du") else "Sie",
            "target_form": "du" if target.endswith("de_du") else "Sie",
            "kind": "followup" if key.startswith("fu_") else "first",
            "subject": source.get("subject", ""), "body": source.get("body", ""),
            "target_now": {"subject": current.get("subject", ""), "body": current.get("body", "")},
            "source_hash": h,
            "write": "The other German version: {subject, body}. Read references/07-sie-du.md first.",
        }, replace=True, key=target)

    def take_convert(self, job, result):
        p = job["payload"]
        body = str(result.get("body") or "").replace("\r\n", "\n").strip()
        subject = " ".join(str(result.get("subject") or "").split()) or p["subject"]
        if not body:
            return {"ok": False, "problems": ['Hand back {"subject": "...", "body": "the whole master email"}']}
        source = self.settings["templates"].get(p["source_key"]) or {}
        self.finish_job(job)
        if text_hash(source.get("subject"), source.get("body")) != p["source_hash"]:
            return {"ok": True, "note": "The text was changed again meanwhile, so this version was not used. A newer "
                                        "job follows."}
        sync = dict(self.settings.get("template_sync") or {})
        sync[p["target_key"]] = {"from": p["source_key"], "hash": p["source_hash"],
                                 "target_hash": text_hash(subject, body), "at": store.stamp()}
        self.settings = store.save_settings({"templates": {p["target_key"]: {"subject": subject, "body": body}},
                                             "template_sync": sync})
        issues = checks.template_problems(self.settings["templates"]).get(p["target_key"], [])
        return {"ok": True, "problems": [], "template_problems": issues}

    def template_sync_state(self):
        """For each German version: was it written by Claude from the other,
        and does it still match?"""
        out = {}
        sync = self.settings.get("template_sync") or {}
        templates = self.settings["templates"]
        for target, source in COUNTERPART.items():
            working = next((j for j in self.jobs if j["type"] == "convert" and j.get("key") == target
                            and j["status"] in ("queued", "taken")), None)
            failed = next((j for j in reversed(self.jobs) if j["type"] == "convert" and j.get("key") == target
                           and j["status"] == "failed"), None)
            done = sync.get(target) or {}
            src, tgt = templates.get(source) or {}, templates.get(target) or {}
            state = ""
            if working:
                state = "working"
            elif done.get("from") == source:
                if text_hash(tgt.get("subject"), tgt.get("body")) != done.get("target_hash"):
                    state = "edited"
                elif text_hash(src.get("subject"), src.get("body")) != done.get("hash"):
                    state = "stale"
                else:
                    state = "fresh"
            if failed and state in ("", "stale") and failed["created"] >= done.get("at", ""):
                state = "failed"
            out[target] = {"state": state, "from": source, "at": done.get("at", ""),
                           "error": failed["error"] if failed and state == "failed" else ""}
        return out

    # ---- attachments --------------------------------------------------------------

    def _decode_files(self, files):
        out = []
        for f in files or []:
            try:
                data = base64.b64decode(str(f.get("data") or ""), validate=False)
            except (ValueError, TypeError):
                raise Problem("The file could not be read.")
            if not data:
                raise Problem("The file %s is empty." % store.safe_name(f.get("name")))
            if len(data) > store.ATTACHMENT_MAX_BYTES:
                raise Problem("The file %s is larger than 20 MB, too large to send by email." % store.safe_name(f.get("name")))
            out.append(store.add_attachment(f.get("name"), data))
        return out

    def add_attachments(self, body):
        added = self._decode_files(body.get("files"))
        if body.get("target") == "draft":
            rnd = self.find_round(body["round_id"])
            draft = self._open_draft(rnd, body["contact_id"])
            have = {a["id"] for a in draft.setdefault("attachments", [])}
            draft["attachments"] += [a for a in added if a["id"] not in have]
            if draft["status"] == "approved":
                draft["status"] = "pending"            # a change after approval is looked at again
            self.recheck(rnd)
            store.save_round(self.folder, rnd)
        else:
            kind = "followup" if body.get("kind") == "followup" else "round"
            all_ = dict(self.settings.get("attachments") or {"round": [], "followup": []})
            have = {a["id"] for a in all_.get(kind, [])}
            all_[kind] = list(all_.get(kind, [])) + [a for a in added if a["id"] not in have]
            self.settings = store.save_settings({"attachments": all_})
        return added

    def remove_attachment(self, body):
        att_id = body.get("id")
        if body.get("target") == "draft":
            rnd = self.find_round(body["round_id"])
            draft = self._open_draft(rnd, body["contact_id"])
            draft["attachments"] = [a for a in draft.get("attachments") or [] if a["id"] != att_id]
            if draft["status"] == "approved":
                draft["status"] = "pending"
            self.recheck(rnd)
            store.save_round(self.folder, rnd)
        else:
            kind = "followup" if body.get("kind") == "followup" else "round"
            all_ = dict(self.settings.get("attachments") or {"round": [], "followup": []})
            all_[kind] = [a for a in all_.get(kind, []) if a["id"] != att_id]
            self.settings = store.save_settings({"attachments": all_})

    def _open_draft(self, rnd, contact_id):
        draft = next((d for d in rnd["drafts"] if d["contact_id"] == contact_id), None)
        if draft is None:
            raise Problem("That draft no longer exists.")
        if draft["status"] in ("sent", "outbox", "sending"):
            raise Problem("This email has already been sent.")
        return draft

    # ---- settings and schedule ------------------------------------------------

    def save(self, patch):
        with self.lock:
            before = dict(self.settings.get("schedule", {}))
            allowed = {k: v for k, v in patch.items() if k in store.DEFAULT_SETTINGS
                       and k not in ("attachments", "template_sync")}
            if "theme" in allowed and allowed["theme"] not in ("light", "dark", "system"):
                del allowed["theme"]
            if "owner_code" in allowed:
                allowed["owner_code"] = re.sub(r"[^A-ZÄÖÜ]", "", str(allowed["owner_code"] or "").upper())[:3]
            for flag in ("personalize", "sync_forms") + (("unassigned_mine",) if allowed.get("unassigned_mine")
                                                          is not None else ()):
                if flag in allowed:
                    allowed[flag] = allowed[flag] is True
            if "filters" in allowed:
                given = allowed["filters"] if isinstance(allowed["filters"], dict) else {}
                allowed["filters"] = {k: [str(x)[:60] for x in given[k]][:60] for k in store.DEFAULT_SETTINGS["filters"]
                                      if isinstance(given.get(k), list)}
            if "templates" in allowed:
                allowed["templates"] = {k: v for k, v in allowed["templates"].items() if k in TEMPLATE_KEYS}
            if "schedule" in allowed:
                allowed["schedule"] = {k: v for k, v in allowed["schedule"].items()
                                       if k in ("mode", "start_date", "time", "auto_send")}
                if "auto_send" in allowed["schedule"]:
                    allowed["schedule"]["auto_send"] = allowed["schedule"]["auto_send"] is True
                mode = allowed["schedule"].get("mode", before.get("mode", "manual"))
                if mode == "manual":
                    # Sending without review belongs to an automatic rhythm. Without one
                    # the switch is not even shown, so it must not stay on unseen.
                    if allowed["schedule"].get("auto_send"):
                        raise Problem("Sending without review needs an automatic rhythm.")
                    allowed["schedule"]["auto_send"] = False
            if "language" in allowed and allowed["language"] not in lang.LANGUAGES:
                del allowed["language"]
            self.settings = store.save_settings(allowed)
            if "workbook" in allowed:
                self.overrides = {}
                self.reload(force=True)
            after = self.settings["schedule"]
            if any(before.get(k) != after.get(k) for k in ("mode", "start_date", "time")):
                self.queue_schedule()

    def queue_schedule(self):
        plan = schedule.plan(self.settings["schedule"])
        if plan["problem"]:
            return
        self.add_job("schedule", dict(plan, prompt=SCHEDULED_PROMPT,
                                      title="AGC deal flow outreach",
                                      description="Prepare the next AGC deal-flow outreach round for review"),
                     replace=True)

    def take_schedule(self, job, result):
        if result.get("ok"):
            confirmed = {k: job["payload"][k] for k in ("mode", "action", "cron", "fire_at", "next_run")}
            confirmed["at"] = store.stamp()
            current = store.load_settings()["schedule"]
            current["confirmed"] = confirmed
            self.settings = store.save_settings({"schedule": current})
            self.finish_job(job)
        else:
            self.finish_job(job, str(result.get("error") or "The scheduler did not accept the task.")[:300])
        return {"ok": True}

    def run_scheduled(self):
        """A due date has arrived: open a round if anyone is due."""
        with self.lock:
            self.scheduled = True
            self.reload(force=True)
            deadline = time.time() + 60
        while self.identity.get("checking") and time.time() < deadline:
            time.sleep(0.5)
        with self.lock:
            if self.current_round():
                self.notice = "A round was already open, so no new one was started."
                return {"started": False, "reason": self.notice}
            try:
                rnd = self.start_round()
            except Problem as exc:
                self.notice = "Scheduled run: %s" % exc
                return {"started": False, "reason": str(exc)}
            total = len(rnd["drafts"])
            if not self.settings["schedule"].get("auto_send"):
                self.notice = "Scheduled round: %d emails are ready for your review." % total
                return {"started": True, "count": total, "round_id": rnd["id"], "sending": 0, "held": 0}
            if any(d["status"] == "preparing" for d in rnd["drafts"]):
                # sent once Claude has adjusted them to the list: see _after_preparing
                rnd["auto_send"] = True
                store.save_round(self.folder, rnd)
                self.notice = ("Scheduled round: %d emails are being adjusted to the list by Claude. They are sent "
                               "without review as soon as that is done, as set on the Setup tab." % total)
                return {"started": True, "count": total, "round_id": rnd["id"], "sending": 0, "held": 0,
                        "preparing": True}
            going, held = self._send_unreviewed(rnd)
            return {"started": True, "count": total, "round_id": rnd["id"], "sending": going, "held": held}

    def _send_unreviewed(self, rnd):
        """The user switched reviews off for scheduled rounds. What failed a check
        is still held back: that is a mistake a recipient would see. So is an
        address found online, which nobody has confirmed."""
        held = self.approve_all(rnd["id"])
        going = [d["contact_id"] for d in rnd["drafts"] if d["status"] == "approved"]
        held += len([d for d in rnd["drafts"] if d["status"] == "research"])
        if not going:
            self.notice = ("Scheduled round: nothing was sent without review, because every email failed "
                           "a check. They are on the Review tab.")
            return 0, held
        self.send(rnd["id"], set(going), False, True)
        self.notice = ("Scheduled round: %d emails are being sent without review, as set on the Setup tab."
                       % len(going)) + (" %d were held back because a check failed." % held if held else "")
        return len(going), held

    # ---- what the screen shows --------------------------------------------------

    def state(self):
        """Everything the screen shows, in the screen's language."""
        raw = self._state()
        code = raw["settings"].get("language", "en")
        if code == "en":
            return raw
        s = json.loads(json.dumps(raw))            # a copy: the sentences are stored in English
        say = lambda text: lang.localize(text, code)
        s["identity"]["problem"] = say(s["identity"].get("problem", ""))
        s["template_problems"] = {k: [say(p) for p in v] for k, v in s["template_problems"].items()}
        s["schedule"]["labels"] = {k: say(v) for k, v in s["schedule"]["labels"].items()}
        s["schedule"]["problem"] = say(s["schedule"]["problem"])
        s["workbook"]["problem"] = say(s["workbook"]["problem"])
        for c in s["contacts"]:
            c["reason"] = say(c["reason"])
            c["assumed"] = [say(a) for a in c.get("assumed", [])]
        for v in s["template_sync"].values():
            v["error"] = say(v["error"])
        if s["round"]:
            s["round"]["label"] = say(s["round"]["label"])
            for d in s["round"]["drafts"]:
                d["error"] = say(d.get("error", ""))
                d["contact"]["assumed"] = [say(a) for a in d["contact"].get("assumed", [])]
                for check in d["checks"]:
                    check["text"] = say(check["text"])
        s["sending"]["message"] = say(s["sending"]["message"])
        s["checking"]["message"] = say(s["checking"]["message"])
        s["app"]["notice"] = say(s["app"]["notice"])
        for r in s["rounds"]:
            r["label"] = say(r["label"])
            for row in r["rows"]:
                row["summary"], row["next_step"] = say(row["summary"]), say(row["next_step"])
        return s

    def _state(self):
        with self.lock:
            self.ui_seen = time.time()
            self.reload()
            rows = self.selected()
            current = self.current_round()
            book = self.book or {}
            plan = schedule.plan(self.settings["schedule"])
            return {
                "app": {"version": VERSION, "simulated": outlook.FAKE, "scheduled": self.scheduled,
                        "claude": time.time() - self.claude_seen < CLAUDE_SEEN_WITHIN,
                        "notice": self.notice},
                "identity": self.identity,
                "settings": self.settings,
                "template_problems": checks.template_problems(self.settings["templates"]),
                "template_sync": self.template_sync_state(),
                "schedule": dict(plan, labels=schedule.LABELS),
                "workbook": {"path": self.settings.get("workbook", ""), "ok": bool(book.get("ok")),
                             "problem": book.get("problem", ""), "sheet": book.get("sheet", ""),
                             "sheets": book.get("sheets", []),
                             "missing_columns": book.get("missing_columns", []),
                             "worked_out": book.get("worked_out", []),
                             "unmatched_headers": book.get("unmatched_headers", []),
                             "owners": book.get("owners", {}),
                             "uses_codes": contacts_mod.uses_codes(book.get("contacts") or []),
                             "unassigned_mine": contacts_mod.unassigned_is_mine(book.get("contacts") or [],
                                                                                 self.settings),
                             "data_folder": self.folder or ""},
                "team": contacts_mod.directory().get("team", []),
                "filter_options": self._filter_options(book.get("contacts") or []),
                "contacts": [{k: c.get(k) for k in SCREEN_FIELDS} for c in rows],
                "round": current,
                "sending": self.sending,
                "checking": self.checking,
                "jobs": [{k: j[k] for k in ("id", "type", "status", "done", "total", "error", "created")}
                         for j in self.jobs if j["status"] in ("queued", "taken")
                         or (j["status"] == "failed" and j["type"] == "schedule")],
                "rounds": [self._round_summary(r) for r in self.rounds if r.get("status") != "closed"
                           or any(d["status"] == "sent" for d in r["drafts"])],
                "outcomes": OUTCOMES,
                "suppression": store.load_suppression(self.folder),
            }

    def _filter_options(self, people):
        """What the list holds, for the filters on the Contacts tab, with counts."""
        count = lambda key: sorted(
            ({"value": v, "n": n} for v, n in _tally(c.get(key) or "none" for c in people).items()),
            key=lambda x: (-x["n"], x["value"]))
        states = {}
        for c in people:
            if c.get("state"):
                states.setdefault(c["country"], {}).setdefault(c["state"], 0)
                states[c["country"]][c["state"]] += 1
        in_order = lambda items, order: sorted(items, key=lambda x: order.index(x["value"]) if x["value"] in order else 99)
        return {"countries": count("country"),
                "priorities": in_order(count("priority"), ["A", "B", "C", "D", "E", "F", "N", "none"]),
                "relevance": in_order(count("relevance"), ["high", "medium", "low", "none"]),
                "types": count("type"),
                "states": {k: sorted(({"value": s, "n": n} for s, n in v.items()), key=lambda x: (-x["n"], x["value"]))
                           for k, v in states.items()}}

    def _round_summary(self, rnd):
        after = self.followup_days()
        rows, counts = [], {}
        for d in rnd["drafts"]:
            if d["status"] not in ("sent", "outbox"):
                continue
            reply = d.get("reply") or {}
            outcome = reply.get("outcome") or "no_reply"
            counts[outcome] = counts.get(outcome, 0) + 1
            c = d["contact"]
            rows.append({"contact_id": d["contact_id"], "name": ("%s %s" % (c.get("first", ""), c.get("last", ""))).strip(),
                         "company": c.get("company", ""), "email": d["to"], "sent_at": d["sent_at"],
                         "state": d["status"], "outcome": outcome, "summary": reply.get("summary", ""),
                         "quote": reply.get("quote", ""), "next_step": reply.get("next_step", ""),
                         "received": reply.get("received", ""), "by_hand": bool(reply.get("by_hand"))})
        mine = rnd.get("sender") == self.me()
        due = len(self._followup_people(rnd)) if mine and rnd.get("kind") != "followup" else 0
        return {"id": rnd["id"], "label": rnd.get("label", rnd["id"]), "kind": rnd.get("kind", "round"),
                "sender": rnd.get("sender", ""), "sender_name": rnd.get("sender_name", ""),
                "created": rnd.get("created", ""), "status": rnd.get("status", ""), "mine": mine,
                "sent": len(rows), "counts": counts, "rows": rows, "followups_due": due,
                "followup_after_days": after}

    def export(self):
        import openpyxl
        from openpyxl.styles import Font
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Tracker"
        head = ["Round", "Sent by", "Name", "Company", "Email", "Sent", "Outcome", "Summary", "Key sentence",
                "Next step", "Answer received"]
        ws.append(head)
        for cell in ws[1]:
            cell.font = Font(bold=True)
        with self.lock:
            for rnd in self.rounds:
                s = self._round_summary(rnd)
                for r in s["rows"]:
                    ws.append([s["label"], s["sender"], r["name"], r["company"], r["email"],
                               r["sent_at"].replace("T", " "), r["outcome"].replace("_", " "), r["summary"],
                               r["quote"], r["next_step"], r["received"].replace("T", " ")])
        for col, width in zip("ABCDEFGHIJK", (16, 26, 24, 26, 30, 18, 16, 50, 50, 36, 18)):
            ws.column_dimensions[col].width = width
        ws.freeze_panes = "A2"
        buf = io.BytesIO()
        wb.save(buf)
        return buf.getvalue()


def browse_for_workbook():
    """A normal Windows 'open file' dialog, in front of the browser. The screen
    cannot ask for a path itself: a browser only ever hands a page the file's
    contents, not where it lives."""
    if outlook.FAKE:
        raise Problem("No file dialog in simulated mode. Paste the path instead.")
    script = (
        "[Console]::OutputEncoding=[Text.Encoding]::UTF8;"
        "Add-Type -AssemblyName System.Windows.Forms;"
        "$f=New-Object System.Windows.Forms.Form -Property @{TopMost=$true;ShowInTaskbar=$false;"
        "WindowState='Minimized'};"
        "$d=New-Object System.Windows.Forms.OpenFileDialog;"
        "$d.Title='Choose the contact list';$d.Filter='Excel workbook (*.xlsx;*.xlsm)|*.xlsx;*.xlsm';"
        "if($d.ShowDialog($f) -eq 'OK'){$d.FileName}")
    try:
        done = subprocess.run(["powershell", "-NoProfile", "-STA", "-Command", script], capture_output=True,
                              timeout=600, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except (OSError, subprocess.TimeoutExpired):
        raise Problem("The file dialog could not be opened. Paste the path instead.")
    return done.stdout.decode("utf-8", "replace").strip()


# ---- HTTP -------------------------------------------------------------------

class Handler(BaseHTTPRequestHandler):
    app = None
    server_version = "AGCOutreach/" + VERSION

    def log_message(self, *args):
        pass

    def _send(self, code, body, ctype="application/json; charset=utf-8", extra=None):
        if isinstance(body, dict) and body.get("error"):
            body = dict(body, error=lang.localize(body["error"], self.app.settings.get("language", "en")))
        data = body if isinstance(body, bytes) else json.dumps(body, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(data)

    def _allowed(self, query):
        host = (self.headers.get("Host") or "").split(":")[0]
        if host not in ("127.0.0.1", "localhost"):
            return False
        token = self.headers.get("X-AGC-Token") or (query.get("t") or [""])[0]
        return secrets.compare_digest(token, self.app.token)

    def _body(self):
        length = int(self.headers.get("Content-Length") or 0)
        if not length:
            return {}
        try:
            return json.loads(self.rfile.read(length).decode("utf-8"))
        except ValueError:
            raise Problem("The request was not valid JSON.")

    def do_GET(self):
        url = urlparse(self.path)
        query = parse_qs(url.query)
        if not url.path.startswith("/api/"):
            return self._static(url.path)
        if not self._allowed(query):
            return self._send(403, {"error": "This link has expired. Start the tool again from Claude."})
        app = self.app
        try:
            if url.path == "/api/state":
                return self._send(200, app.state())
            if url.path == "/api/ping":
                return self._send(200, {"ok": True, "version": VERSION})
            if url.path == "/api/jobs/next":
                job = app.next_job(min(float((query.get("wait") or ["25"])[0]), 55))
                return self._send(200, {"job": job})
            if url.path == "/api/template":
                with open(os.path.join(ASSETS, "Contacts_Template.xlsx"), "rb") as fh:
                    return self._send(200, fh.read(),
                                      "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                                      {"Content-Disposition": 'attachment; filename="Contacts_Template.xlsx"'})
            if url.path == "/api/export":
                name = "Deal flow tracker %s.xlsx" % dt.date.today().isoformat()
                return self._send(200, app.export(),
                                  "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                                  {"Content-Disposition": 'attachment; filename="%s"' % name})
            return self._send(404, {"error": "Not found."})
        except Problem as exc:
            return self._send(400, {"error": str(exc)})
        except Exception as exc:
            return self._send(500, {"error": "%s: %s" % (type(exc).__name__, str(exc)[:200])})

    def do_POST(self):
        url = urlparse(self.path)
        if not self._allowed(parse_qs(url.query)):
            return self._send(403, {"error": "This link has expired. Start the tool again from Claude."})
        app, path = self.app, url.path
        try:
            body = self._body()
            if path == "/api/settings":
                app.save(body)
            elif path == "/api/browse":
                picked = browse_for_workbook()
                if picked:
                    app.save({"workbook": picked})
                return self._send(200, {"path": picked})
            elif path == "/api/reload":
                app.reload(force=True)
            elif path == "/api/override":
                with app.lock:
                    app.overrides[body["contact_id"]] = bool(body["included"])
            elif path == "/api/round/start":
                with app.lock:
                    app.start_round()
            elif path == "/api/round/close":
                with app.lock:
                    app.close_round(body["round_id"])
            elif path == "/api/followup/start":
                with app.lock:
                    app.start_round("followup", app.find_round(body["round_id"]))
            elif path == "/api/draft/update":
                with app.lock:
                    app.update_draft(body["round_id"], body["contact_id"], body.get("change") or {})
            elif path == "/api/draft/approve-all":
                with app.lock:
                    return self._send(200, {"ok": True, "left": app.approve_all(body["round_id"])})
            elif path == "/api/draft/redraft":
                with app.lock:
                    app.redraft(body["round_id"], body["contact_id"], str(body.get("note") or "")[:500])
            elif path == "/api/draft/accept-research":
                with app.lock:
                    app.accept_research(body["round_id"], body["contact_id"])
            elif path == "/api/round/skip-prepare":
                with app.lock:
                    app.skip_preparing(body["round_id"])
            elif path == "/api/template/sync":
                with app.lock:
                    app.sync_template(str(body.get("key") or ""))
            elif path == "/api/attachments/add":
                with app.lock:
                    return self._send(200, {"ok": True, "added": app.add_attachments(body)})
            elif path == "/api/attachments/remove":
                with app.lock:
                    app.remove_attachment(body)
            elif path == "/api/send":
                app.send(body["round_id"], set(body.get("ids") or []), bool(body.get("test")),
                         body.get("confirm") is True)
            elif path == "/api/send/stop":
                app.stop_sending.set()
            elif path == "/api/replies/check":
                app.check_replies()
            elif path == "/api/reply/set":
                with app.lock:
                    app.set_outcome(body["round_id"], body["contact_id"], body.get("outcome", ""))
            elif path == "/api/schedule/retry":
                with app.lock:
                    app.queue_schedule()
            elif path == "/api/notice/clear":
                with app.lock:
                    app.notice = ""
            elif path == "/api/scheduled":
                return self._send(200, app.run_scheduled())
            elif path == "/api/quit":
                self._send(200, {"ok": True})
                threading.Thread(target=self.server.shutdown, daemon=True).start()
                return
            elif path.startswith("/api/jobs/"):
                _, _, _, job_id, action = path.split("/")
                with app.lock:
                    job = app.job(job_id)
                    if action == "fail":
                        app.give_up(job, str(body.get("reason") or "Claude could not do this.")[:300])
                        return self._send(200, {"ok": True})
                    if job["status"] in ("done", "failed"):
                        return self._send(200, {"ok": True, "note": "This job is already closed."})
                    taker = {"rewrite": app.take_rewrite, "classify": app.take_classification,
                             "schedule": app.take_schedule, "personalize": app.take_personalize,
                             "research": app.take_research, "convert": app.take_convert}[job["type"]]
                    return self._send(200, taker(job, body))
            else:
                return self._send(404, {"error": "Not found."})
            return self._send(200, {"ok": True})
        except Problem as exc:
            return self._send(400, {"error": str(exc)})
        except KeyError as exc:
            return self._send(400, {"error": "The request is missing %s." % exc})
        except Exception as exc:
            return self._send(500, {"error": "%s: %s" % (type(exc).__name__, str(exc)[:200])})

    def _static(self, path):
        name = "index.html" if path in ("/", "") else path.lstrip("/")
        full = os.path.normpath(os.path.join(UI_DIR, name))
        if not full.startswith(UI_DIR) or not os.path.isfile(full):
            return self._send(404, b"Not found", "text/plain")
        with open(full, "rb") as fh:
            self._send(200, fh.read(), MIME.get(os.path.splitext(full)[1], "application/octet-stream"))


def info_path():
    return os.path.join(store.home(), "server.json")


def make_server():
    app = App()
    if outlook.FAKE and os.environ.get("AGC_OUTREACH_TOKEN"):
        app.token = os.environ["AGC_OUTREACH_TOKEN"]        # a fixed link for the demo, never for real mail
    Handler.app = app
    httpd = ThreadingHTTPServer(("127.0.0.1", int(os.environ.get("AGC_OUTREACH_PORT") or 0)), Handler)
    httpd.daemon_threads = True
    return httpd, app


def run():
    """Start the app and stay until it has been idle for a long while."""
    httpd, app = make_server()
    port = httpd.server_address[1]
    url = "http://127.0.0.1:%d/?t=%s" % (port, app.token)
    store.write_json(info_path(), {"port": port, "token": app.token, "pid": os.getpid(), "url": url,
                                   "started": store.stamp()})

    def watchdog():
        while True:
            time.sleep(30)
            with app.lock:
                busy = app.sending["active"] or app.checking["active"]
                idle = time.time() - app.ui_seen      # the screen, not Claude, keeps the app alive
            if not busy and idle > IDLE_SHUTDOWN_SECONDS:
                httpd.shutdown()
                return

    threading.Thread(target=watchdog, daemon=True).start()
    try:
        httpd.serve_forever()
    finally:
        current = store.read_json(info_path(), {})
        if current.get("pid") == os.getpid():
            try:
                os.remove(info_path())
            except OSError:
                pass


if __name__ == "__main__":
    run()
