#!/usr/bin/env python3
"""Tests for the deal-flow outreach tool. No real email is sent or read: the
whole run uses the stand-in mailbox and a throwaway settings folder.

    python dev/run_tests.py
"""
import base64
import datetime as dt
import io
import json
import os
import shutil
import sys
import tempfile
import threading
import time
import traceback
import urllib.error
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TMP = tempfile.mkdtemp(prefix="agc-outreach-test-")
os.environ["AGC_OUTREACH_FAKE"] = "1"
os.environ["AGC_OUTREACH_HOME"] = os.path.join(TMP, "home")
os.environ["AGC_OUTREACH_GAP"] = "0.15"
sys.path.insert(0, os.path.join(ROOT, "agc-deal-flow-outreach", "scripts"))

import checks  # noqa: E402
import contacts  # noqa: E402
import outlook  # noqa: E402
import schedule  # noqa: E402
import server  # noqa: E402
import store  # noqa: E402

FIXTURE = os.path.join(ROOT, "dev", "fixtures", "contacts_50.xlsx")
COCKPIT = os.path.join(ROOT, "dev", "fixtures", "agc_cockpit_like.xlsx")
NO_PROXY = urllib.request.build_opener(urllib.request.ProxyHandler({}))
ME = "tester@agcapital.example"
RESULTS = []


def test(fn):
    try:
        fn()
        RESULTS.append((fn.__name__, True, ""))
    except Exception:
        RESULTS.append((fn.__name__, False, traceback.format_exc()))
    return fn


def person(**kw):
    base = {"first": "Anna", "last": "Huber", "title": "", "gender": "f", "company": "Donauhof Rechtsanwälte",
            "language": "de", "form": "sie", "greeting": "", "relationship": "Mandat 2023", "sector": "",
            "notes": "", "role": ""}
    base.update(kw)
    return base


# ---- contacts -----------------------------------------------------------------

@test
def reads_the_fixture():
    book = contacts.read_workbook(FIXTURE)
    assert book["ok"], book["problem"]
    assert len(book["contacts"]) == 53, len(book["contacts"])
    assert book["sheet"] == "Contacts"
    assert not book["unmatched_headers"], book["unmatched_headers"]
    by_last = {c["last"]: c for c in book["contacts"]}
    assert by_last["Ohneadresse"]["problems"] == ["no email address"]
    kim = by_last["Novak"]
    assert kim["language"] == "de" and kim["form"] == "sie" and len(kim["assumed"]) == 2


@test
def a_missing_file_is_a_sentence_not_a_crash():
    book = contacts.read_workbook(os.path.join(TMP, "nope.xlsx"))
    assert not book["ok"] and "not found" in book["problem"]


@test
def greetings_follow_the_rules():
    g = lambda **kw: contacts.greeting(person(**kw))[0]
    assert g() == "Sehr geehrte Frau Huber,"
    assert g(gender="m", title="Dr.") == "Sehr geehrter Herr Dr. Huber,"
    assert g(title="Mag.") == "Sehr geehrte Frau Mag. Huber,"
    assert g(form="du") == "Liebe Anna,"
    assert g(form="du", gender="m", first="Tom") == "Lieber Tom,"
    assert g(form="du", gender="") == "Hallo Anna,"
    assert g(gender="") == "Guten Tag Anna Huber,"
    assert contacts.greeting(person(gender=""))[1] == "Herr/Frau not given"
    assert g(language="en") == "Dear Ms Huber,"
    assert g(language="en", title="Dr.") == "Dear Dr Huber,"
    assert g(language="en", form="du") == "Dear Anna,"
    assert g(greeting="Servus Tom") == "Servus Tom,"


@test
def the_kind_of_contact_is_given_or_read_off_the_firm():
    t = contacts.contact_type
    assert t("", "Donauhof Rechtsanwälte", "Partner") == ("Law firm", True)
    assert t("", "Kahlenberg Steuerberatung", "") == ("Tax / audit", True)       # not "Consultant" via "berat"
    assert t("", "Praterstern Corporate Finance", "") == ("M&A adviser", True)
    assert t("", "Ringstrasse Consulting", "") == ("Consultant", True)
    assert t("", "Wienfluss Bank Firmenkunden", "") == ("Bank", True)
    assert t("", "Muster GmbH", "Rechtsanwalt") == ("Law firm", True)            # the role, when the firm says nothing
    assert t("", "Muster GmbH", "Owner") == ("Other", True)
    assert t("PE", "Hartwell Partners", "") == ("Private equity", False)        # the column wins, under its usual name
    assert t("vc", "Novak", "") == ("Venture capital", False)
    assert t("family friend", "Donauhof Rechtsanwälte", "") == ("Family friend", False)
    book = contacts.read_workbook(FIXTURE)
    kinds = {c["type"] for c in book["contacts"]}
    assert {"Law firm", "Tax / audit", "M&A adviser", "Consultant", "Bank", "Private equity",
            "Venture capital", "Other"} == kinds, kinds


@test
def selection_explains_itself():
    book = contacts.read_workbook(FIXTURE)
    settings = dict(store.DEFAULT_SETTINGS, owner_name="Test Sender")
    rows = contacts.select(book["contacts"], settings, ME, {}, {})
    reasons = {}
    for c in rows:
        reasons.setdefault(c["reason"], []).append(c)
    assert len([c for c in rows if c["included"]]) == 46, len([c for c in rows if c["included"]])
    assert len(reasons["belongs to Somebody Else"]) == 5
    assert len(reasons["marked do not contact in the list"]) == 1
    # written to last week: not due, unless added by hand; an opt-out can never be added by hand
    first = next(c for c in rows if c["included"])
    history = {first["email"]: {"last_sent": (dt.date.today() - dt.timedelta(days=7)).isoformat()}}
    again = {c["id"]: c for c in contacts.select(book["contacts"], settings, ME, history, {})}
    assert not again[first["id"]]["included"] and "7 days ago" in again[first["id"]]["reason"]
    forced = {c["id"]: c for c in contacts.select(book["contacts"], settings, ME, history,
                                                  {first["email"]: {}}, {first["id"]: True})}
    assert not forced[first["id"]]["included"] and forced[first["id"]]["locked"]
    forced = {c["id"]: c for c in contacts.select(book["contacts"], settings, ME, history, {}, {first["id"]: True})}
    assert forced[first["id"]]["included"]


@test
def the_batch_size_is_a_hard_cap():
    book = contacts.read_workbook(FIXTURE)
    settings = dict(store.DEFAULT_SETTINGS, owner_name="Test Sender", batch_size=10)
    rows = contacts.select(book["contacts"], settings, ME, {}, {})
    assert len([c for c in rows if c["included"]]) == 10


# ---- putting an email together, and checking it ------------------------------------

MASTER = "ich melde mich kurz bei Ihnen, weil wir Unternehmen suchen.\n\nBeste Grüße"


def draft_for(contact, body=None, subject="Kurze Frage", **kw):
    standard = checks.assemble(MASTER, contact)
    return dict({"subject": subject, "standard": standard, "body": standard if body is None else body,
                 "changed_by": "", "note": ""}, **kw)


def ids(result):
    return {(c["id"], c["level"]) for c in result}


@test
def the_email_is_the_greeting_and_the_master_text():
    c = person()
    d = draft_for(c)
    assert d["body"] == "Sehr geehrte Frau Huber,\n\n" + MASTER
    assert checks.check(d, c, []) == [], checks.check(d, c, [])
    # stray blank lines in the master text do not travel
    assert "\n\n\n" not in checks.assemble("eins\n\n\n\nzwei\n", c)


@test
def the_mistakes_a_recipient_notices_are_caught():
    c = person()
    other = person(first="Georg", last="Pichler", gender="m", company="Kahlenberg Steuerberatung")
    std = checks.assemble(MASTER, c)
    changed = lambda extra, **kw: draft_for(c, std.replace("Beste Grüße", extra + "\n\nBeste Grüße"), **kw)

    assert ("register", "fail") in ids(checks.check(changed("Wie geht es dir?"), c, []))
    du = person(form="du")
    du_master = "ich melde mich kurz bei dir.\n\nLiebe Grüße"
    ok = {"subject": "x", "standard": checks.assemble(du_master, du), "body": checks.assemble(du_master, du)}
    assert checks.check(ok, du, []) == []
    assert ("register", "fail") in ids(checks.check(dict(ok, body=ok["body"] + "\nIch hoffe, bei Ihnen ist alles gut."), du, []))

    wrong = changed("Ich habe neulich mit Herrn Pichler gesprochen.")
    assert ("wrong-name", "fail") in ids(checks.check(wrong, c, [other]))
    english = changed("It has been a while since we last spoke about the deal and I wanted to say hello.")
    assert ("language", "fail") in ids(checks.check(english, c, []))
    assert ("placeholder", "fail") in ids(checks.check(changed("Es geht um {company_name}."), c, []))
    assert ("subject", "fail") in ids(checks.check(draft_for(c, subject=""), c, []))
    assert ("empty", "fail") in ids(checks.check(draft_for(c, body="  "), c, []))


@test
def what_claude_adds_is_held_to_the_list_and_the_note():
    c = person()
    std = checks.assemble(MASTER, c)
    by_claude = lambda extra, note="": draft_for(c, std.replace("Beste Grüße", extra + "\n\nBeste Grüße"),
                                                 changed_by="claude", note=note)
    assert ("unsupported", "warn") in ids(checks.check(by_claude("Seit 2019 ist viel passiert."), c, []))
    assert ("unsupported", "warn") not in ids(checks.check(by_claude("Seit 2023 ist viel passiert."), c, []))   # in the row
    assert ("unsupported", "warn") not in ids(checks.check(
        by_claude("Seit 2019 ist viel passiert.", note="erwähne unser Projekt 2019"), c, []))                   # in the note
    assert ("tone", "warn") in ids(checks.check(by_claude("I hope this email finds you well."), c, []))
    # the sender's own master text is never marked for its wording, nor is a hand edit
    canned = "I hope this email finds you well.\n\nBest"
    en = person(language="en")
    own = {"subject": "x", "standard": checks.assemble(canned, en), "body": checks.assemble(canned, en)}
    assert checks.check(own, en, []) == []
    by_hand = draft_for(c, std + "\nSeit 2019 ist viel passiert.", changed_by="hand")
    assert checks.check(by_hand, c, []) == []


@test
def a_changed_greeting_is_noticed():
    c = person()
    d = draft_for(c)
    d["body"] = d["body"].replace("Sehr geehrte Frau Huber,", "Sehr geehrter Herr Pichler,")
    assert ("greeting", "fail") in ids(checks.check(d, c, []))
    d["body"] = d["standard"].replace("Sehr geehrte Frau Huber,", "Liebe Frau Huber,")
    assert ("greeting", "warn") in ids(checks.check(d, c, []))


@test
def the_master_emails_are_checked_too():
    problems = checks.template_problems(server._starter_templates())
    assert set(problems) == set(server.TEMPLATE_KEYS)
    assert all(p == [] for p in problems.values()), problems          # the starter emails have nothing to fill in
    assert not any("[[" in t["body"] or "{" in t["body"] for t in server._starter_templates().values())
    assert checks.template_problems({"de_sie": {"subject": "x", "body": "Wir suchen [[Branche]]."}})["de_sie"] == \
        ["a [[note to fill in]] is still in the text"]
    mixed = {"de_sie": {"subject": "x", "body": "ich melde mich bei dir."},
             "de_du": {"subject": "x", "body": "ich melde mich bei Ihnen."},
             "en": {"subject": "", "body": "Hello {opening}"}}
    p = checks.template_problems(mixed)
    assert p["de_sie"] == ["uses du, but this is the Sie version"]
    assert p["de_du"] == ["uses Sie, but this is the du version"]
    assert p["en"] == ["no subject line", "a placeholder is in the text: {opening}"]


# ---- schedule -----------------------------------------------------------------

@test
def rhythms_become_cron_rules():
    now = dt.datetime(2026, 10, 12, 12, 0)
    s = {"mode": "quarterly", "start_date": "2026-11-03", "time": "09:00"}
    p = schedule.plan(s, now)
    assert (p["action"], p["cron"], p["next_run"]) == ("recurring", "0 9 3 2,5,8,11 *", "2026-11-03T09:00"), p
    assert schedule.plan(dict(s, mode="half_yearly"), now)["cron"] == "0 9 3 5,11 *"
    assert schedule.plan(dict(s, mode="yearly"), now)["cron"] == "0 9 3 11 *"
    assert schedule.plan(dict(s, mode="manual"), now)["action"] == "off"
    late = schedule.plan({"mode": "quarterly", "start_date": "2026-01-31", "time": "08:30"}, now)
    assert late["cron"] == "30 8 28 1,4,7,10 *" and late["next_run"] == "2026-10-28T08:30", late
    once = schedule.plan(dict(s, mode="date"), now)
    assert once["action"] == "once" and once["fire_at"].startswith("2026-11-03T09:00:00")
    assert schedule.plan({"mode": "date", "start_date": "2026-01-01", "time": "09:00"}, now)["problem"]
    assert schedule.plan({"mode": "yearly", "start_date": "", "time": "09:00"}, now)["problem"]


# ---- the whole flow, against the stand-in mailbox ---------------------------------

class Client:
    def __init__(self, httpd, app):
        self.base = "http://127.0.0.1:%d" % httpd.server_address[1]
        self.token = app.token

    def call(self, path, body=None, token=None, raw=False):
        data = None if body is None else json.dumps(body).encode("utf-8")
        req = urllib.request.Request(self.base + path, data=data,
                                     headers={"X-AGC-Token": self.token if token is None else token})
        try:
            with NO_PROXY.open(req, timeout=30) as resp:
                payload = resp.read()
                return resp.status, payload if raw else json.loads(payload.decode("utf-8"))
        except urllib.error.HTTPError as exc:
            return exc.code, json.loads(exc.read().decode("utf-8"))

    def state(self):
        return self.call("/api/state")[1]

    def draft(self, cid):
        return next(d for d in self.state()["round"]["drafts"] if d["contact_id"] == cid)

    def until(self, cond, seconds=30):
        end = time.time() + seconds
        while time.time() < end:
            s = self.state()
            if cond(s):
                return s
            time.sleep(0.1)
        raise AssertionError("timed out waiting")


def finished(templates):
    """The starter master emails with their note to fill in filled in."""
    out = {}
    for key, t in templates.items():
        body = t["body"]
        if "[[" in body:
            body = body[:body.find("[[")] + "Mittelstand in Österreich" + body[body.find("]]") + 2:]
        out[key] = {"subject": t["subject"], "body": body}
    return out


@test
def the_whole_flow():
    book = os.path.join(TMP, "list", "contacts.xlsx")
    os.makedirs(os.path.dirname(book))
    shutil.copy(FIXTURE, book)
    httpd, app = server.make_server()
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    api = Client(httpd, app)
    try:
        # nobody without the link gets in
        assert api.call("/api/state", token="wrong")[0] == 403
        api.until(lambda s: s["identity"].get("ok"))

        # setup: list, finished master emails; every change is on disk at once. Claude's pass
        # over each email is switched off here: this test is about everything around it.
        assert api.call("/api/settings", {"workbook": book, "templates": finished(app.settings["templates"]),
                                          "personalize": False})[0] == 200
        assert store.load_settings()["workbook"] == book
        s = api.state()
        assert s["workbook"]["ok"] and len(s["contacts"]) == 53
        assert s["workbook"]["data_folder"].endswith(store.DATA_FOLDER_NAME)
        assert all(not v for v in s["template_problems"].values()), s["template_problems"]
        included = [c for c in s["contacts"] if c["included"]]
        assert len(included) == 46 and all(c["type"] for c in s["contacts"])

        # leave one out by hand
        api.call("/api/override", {"contact_id": included[0]["id"], "included": False})
        assert len([c for c in api.state()["contacts"] if c["included"]]) == 45

        # start the round: the emails are there at once, the same text for everyone, and Claude is not asked
        assert api.call("/api/round/start", {})[0] == 200
        assert api.call("/api/round/start", {})[0] == 400          # one open round at a time
        s = api.state()
        rnd = s["round"]
        rid = rnd["id"]
        assert rnd["status"] == "review" and len(rnd["drafts"]) == 45 and not s["jobs"]
        assert all(d["status"] == "pending" and d["body"] == d["standard"] for d in rnd["drafts"])
        by_template = {}
        for d in rnd["drafts"]:
            greeting, rest = d["body"].split("\n\n", 1)
            assert greeting == contacts.greeting(d["contact"])[0]
            by_template.setdefault(d["template"], set()).add(rest)
        assert set(by_template) == {"de_sie", "de_du", "en"} and all(len(v) == 1 for v in by_template.values())
        tom = next(d for d in rnd["drafts"] if d["contact"]["last"] == "Berger" and d["contact"]["first"] == "Tom")
        assert tom["body"].startswith("Servus Tom,\n\nich melde mich") and "bei dir" in tom["body"]
        # the only thing flagged in a fresh round is a greeting the list could not settle
        flagged = [d for d in rnd["drafts"] if d["level"] != "ok"]
        assert flagged and all({c["id"] for c in d["checks"]} == {"greeting-data"} for d in flagged)

        # the reviewer asks Claude to change one email; only then does Claude get a job
        one = next(d["contact_id"] for d in rnd["drafts"] if d["template"] == "de_sie" and d["level"] == "ok")
        assert api.call("/api/draft/redraft", {"round_id": rid, "contact_id": one, "note": " "})[0] == 400
        api.call("/api/draft/redraft", {"round_id": rid, "contact_id": one, "note": "erwähne unser Treffen im Mai"})
        assert api.draft(one)["status"] == "waiting"
        job = api.call("/api/jobs/next?wait=2")[1]["job"]
        p = job["payload"]
        assert job["type"] == "rewrite" and p["contact_id"] == one and p["note_from_user"] == "erwähne unser Treffen im Mai"
        assert p["email_now"] == p["master_email"] and p["greeting"] == p["email_now"].split("\n")[0]
        empty = api.call("/api/jobs/%s/result" % job["id"], {"drafts": [{"contact_id": one, "body": ""}]})[1]
        assert not empty["ok"] and api.draft(one)["status"] == "waiting"
        # a rewrite that slips into du is handed back with the failed check
        new = p["email_now"].replace("\n\nich melde", "\n\nes war schön, dich im Mai zu sehen. Ich melde", 1)
        back = api.call("/api/jobs/%s/result" % job["id"], {"drafts": [{"contact_id": one, "body": new}]})[1]
        assert back["ok"] and back["failed_checks"] == ["Uses du, but the list says Sie."], back
        d = api.draft(one)
        assert d["status"] == "pending" and d["changed_by"] == "claude" and d["level"] == "fail" and not api.state()["jobs"]

        # approve all: everything except what failed a check
        left = api.call("/api/draft/approve-all", {"round_id": rid})[1]["left"]
        rnd = api.state()["round"]
        assert left == 1 and len([d for d in rnd["drafts"] if d["status"] == "approved"]) == 44
        assert api.draft(one)["status"] == "pending"

        # back to the master text, and it is clean again
        api.call("/api/draft/update", {"round_id": rid, "contact_id": one, "change": {"reset": True}})
        d = api.draft(one)
        assert d["body"] == d["standard"] and d["changed_by"] == "" and d["level"] == "ok"
        api.call("/api/draft/update", {"round_id": rid, "contact_id": one, "change": {"status": "skipped"}})

        # an edit by hand after approval is looked at again
        victim = next(d for d in rnd["drafts"] if d["status"] == "approved")
        api.call("/api/draft/update", {"round_id": rid, "contact_id": victim["contact_id"],
                                       "change": {"body": victim["body"] + "\nPS: bis bald"}})
        d = api.draft(victim["contact_id"])
        assert d["status"] == "pending" and d["changed_by"] == "hand"
        api.call("/api/draft/update", {"round_id": rid, "contact_id": victim["contact_id"], "change": {"status": "approved"}})
        victim = victim["contact_id"]

        # a test goes to the sender's own address and changes nothing
        ok = api.call("/api/send", {"round_id": rid, "ids": [victim], "test": True})
        assert ok[0] == 200, ok
        api.until(lambda s: not s["sending"]["active"])
        box = outlook._fake_box()
        assert len(box["sent"]) == 1 and box["sent"][0]["to"] == ME
        assert box["sent"][0]["subject"].startswith("[Test, would go to ") and box["sent"][0]["body"].endswith("PS: bis bald")
        assert api.draft(victim)["status"] == "approved"

        # sending needs the confirmation, can be stopped, and picks up where it stopped
        all_ids = [d["contact_id"] for d in api.state()["round"]["drafts"]]
        assert api.call("/api/send", {"round_id": rid, "ids": all_ids})[0] == 400
        started = time.time()
        assert api.call("/api/send", {"round_id": rid, "ids": all_ids, "confirm": True})[0] == 200
        assert api.call("/api/send", {"round_id": rid, "ids": all_ids, "confirm": True})[0] == 400
        api.until(lambda s: s["sending"]["done"] >= 3)
        api.call("/api/send/stop", {})
        s = api.until(lambda s: not s["sending"]["active"])
        partly = s["sending"]["done"]
        assert 3 <= partly < 44 and "Stopped" in s["sending"]["message"], s["sending"]
        assert len([d for d in s["round"]["drafts"] if d["status"] == "approved"]) == 44 - partly
        assert api.call("/api/send", {"round_id": rid, "ids": all_ids, "confirm": True})[0] == 200
        s = api.until(lambda s: not s["sending"]["active"], 60)
        assert time.time() - started > 43 * 0.15                     # the gap between emails is kept
        sent = [m for m in outlook._fake_box()["sent"] if not m["subject"].startswith("[Test")]
        assert len(sent) == 44 and len({m["to"] for m in sent}) == 44    # everyone once, nobody twice
        assert s["round"] is None                                    # nothing left to review: round is done
        tracker = next(r for r in s["rounds"] if r["id"] == rid)
        assert tracker["sent"] == 44 and tracker["counts"] == {"no_reply": 44}
        assert os.path.isfile(store.round_path(s["workbook"]["data_folder"], rid, ME))

        # nobody written to today is due again
        assert not [c for c in s["contacts"] if c["included"] and c["last_sent"]]

        # answers: one in the thread, one by address only, a bounce, an absence note, a stranger
        a, b, c, d = sent[0], sent[1], sent[2], sent[3]
        later = store.stamp(store.now() + dt.timedelta(minutes=1))
        box = outlook._fake_box()
        box["inbox"] = [
            {"kind": "reply", "from_email": a["to"], "from_name": "A", "received": later, "subject": "AW: " + a["subject"],
             "text": "Danke, ich hätte da ein Unternehmen im Kopf.\n\nVon: Test Sender\nGesendet: heute",
             "conversation_id": a["conversation_id"]},
            {"kind": "reply", "from_email": b["to"], "from_name": "B", "received": later, "subject": "Bitte keine Mails",
             "text": "Bitte nehmen Sie mich aus dem Verteiler.", "conversation_id": "OTHER"},
            {"kind": "bounce", "from_email": c["to"], "from_name": "", "received": later, "subject": "Undeliverable",
             "text": "Delivery failed", "conversation_id": c["conversation_id"]},
            {"kind": "auto", "from_email": d["to"], "from_name": "D", "received": later, "subject": "Automatische Antwort",
             "text": "Ich bin bis Montag abwesend.", "conversation_id": d["conversation_id"]},
            {"kind": "reply", "from_email": "stranger@elsewhere.example", "from_name": "S", "received": later,
             "subject": "Hello", "text": "Unrelated", "conversation_id": "NOPE"},
        ]
        store.write_json(outlook._fake_path(), box)
        assert api.call("/api/replies/check", {})[0] == 200
        api.until(lambda s: not s["checking"]["active"] and s["checking"]["last"])
        job3 = api.call("/api/jobs/next?wait=2")[1]["job"]
        assert job3["type"] == "classify" and len(job3["payload"]["answers"]) == 2
        by_mail = {x["contact_id"]: x for x in job3["payload"]["answers"]}
        assert "Von:" not in by_mail[a["to"]]["messages"][0]["text"]     # the quoted original is cut off
        assert by_mail[a["to"]]["matched_by"] == "thread" and by_mail[b["to"]]["matched_by"] == "address"
        wrong = api.call("/api/jobs/%s/result" % job3["id"], {"answers": [
            {"round_id": rid, "contact_id": a["to"], "outcome": "maybe"}]})[1]
        assert not wrong["ok"] and len(wrong["still_to_classify"]) == 2
        done = api.call("/api/jobs/%s/result" % job3["id"], {"answers": [
            {"round_id": rid, "contact_id": a["to"], "outcome": "lead", "summary": "Has a company in mind.",
             "quote": "ich hätte da ein Unternehmen im Kopf", "next_step": "Call this week."},
            {"round_id": rid, "contact_id": b["to"], "outcome": "do_not_contact", "summary": "Asked to be removed.",
             "quote": "Bitte nehmen Sie mich aus dem Verteiler.", "next_step": ""}]})[1]
        assert done["ok"] and done["still_to_classify"] == []
        s = api.state()
        tracker = next(r for r in s["rounds"] if r["id"] == rid)
        assert tracker["counts"] == {"lead": 1, "do_not_contact": 1, "bounce": 1, "out_of_office": 1, "no_reply": 40}
        assert b["to"] in s["suppression"]
        assert next(c for c in s["contacts"] if c["email"] == b["to"])["reason"] == "asked not to be contacted"

        # checking again finds nothing new
        api.call("/api/replies/check", {})
        api.until(lambda s: not s["checking"]["active"])
        assert not [j for j in api.state()["jobs"] if j["type"] == "classify"]

        # an outcome can be corrected by hand
        api.call("/api/reply/set", {"round_id": rid, "contact_id": a["to"], "outcome": "referral"})
        assert next(r for r in api.state()["rounds"] if r["id"] == rid)["counts"]["referral"] == 1

        # the export opens as a workbook with a row per email sent
        code, blob = api.call("/api/export", raw=True)
        import openpyxl
        ws = openpyxl.load_workbook(io.BytesIO(blob)).active
        assert code == 200 and ws.max_row == 45

        # follow-ups: only to people who have not answered, never to an opt-out or a bounce
        assert tracker["followups_due"] == 0                         # too early
        api.call("/api/settings", {"followup_after_days": 0})
        assert next(r for r in api.state()["rounds"] if r["id"] == rid)["followups_due"] == 41
        assert api.call("/api/followup/start", {"round_id": rid})[0] == 200
        fu = api.state()["round"]
        assert fu["kind"] == "followup" and len(fu["drafts"]) == 41 and not api.state()["jobs"]
        mails = {x["contact_id"] for x in fu["drafts"]}
        assert not mails & {a["to"], b["to"], c["to"]} and d["to"] in mails
        assert all("anknüpfen" in x["body"] or "follow up" in x["body"] for x in fu["drafts"])
        api.call("/api/round/close", {"round_id": fu["id"]})
        assert api.state()["round"] is None

        # the rhythm: a change is saved at once and handed to Claude as one job
        api.call("/api/settings", {"schedule": {"mode": "quarterly", "start_date": "2027-01-15", "time": "08:00"}})
        api.call("/api/settings", {"schedule": {"mode": "yearly"}})
        assert store.load_settings()["schedule"]["mode"] == "yearly"
        jobs = [j for j in api.state()["jobs"] if j["type"] == "schedule"]
        assert len(jobs) == 1                                         # the earlier change was replaced
        job5 = api.call("/api/jobs/next?wait=2")[1]["job"]
        assert job5["payload"]["cron"] == "0 8 15 1 *" and "scheduled mode" in job5["payload"]["prompt"]
        api.call("/api/jobs/%s/result" % job5["id"], {"ok": True})
        assert store.load_settings()["schedule"]["confirmed"]["cron"] == "0 8 15 1 *"

        # a scheduled run opens a round for whoever is due: here the one left out
        # by hand and the one skipped, the only two never written to. It is
        # ready for review at once, and nothing is sent.
        result = api.call("/api/scheduled", {})[1]
        assert result["started"] and result["count"] == 2, result
        s = api.state()
        assert {x["contact_id"] for x in s["round"]["drafts"]} == {included[0]["id"], one}
        assert s["app"]["scheduled"] and "2 emails are ready" in s["app"]["notice"]
        assert all(x["status"] == "pending" for x in s["round"]["drafts"]) and not s["jobs"]
        assert len([m for m in outlook._fake_box()["sent"] if not m["subject"].startswith("[Test")]) == 44
        # and when a round is already open it starts no second one
        again = api.call("/api/scheduled", {})[1]
        assert not again["started"], again
    finally:
        httpd.shutdown()


@test
def a_restart_picks_up_an_unfinished_round():
    """Runs after the_whole_flow, on the same folders."""
    folder = store.data_dir(store.load_settings()["workbook"])
    store.write_json(os.path.join(folder, "suppression.json"), {})
    for name in os.listdir(os.path.join(folder, "rounds")):
        os.remove(os.path.join(folder, "rounds", name))
    httpd, app = server.make_server()
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    api = Client(httpd, app)
    api.until(lambda s: s["identity"].get("ok"))
    api.call("/api/round/start", {})
    rnd = api.state()["round"]
    one, two = rnd["drafts"][0]["contact_id"], rnd["drafts"][1]["contact_id"]
    api.call("/api/draft/update", {"round_id": rnd["id"], "contact_id": two, "change": {"status": "approved"}})
    api.call("/api/draft/redraft", {"round_id": rnd["id"], "contact_id": one, "note": "kürzer bitte"})
    httpd.shutdown()

    httpd, app = server.make_server()
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    api = Client(httpd, app)
    try:
        s = api.until(lambda s: s["round"] and s["jobs"])
        assert api.draft(two)["status"] == "approved" and api.draft(one)["status"] == "waiting"
        again = api.call("/api/jobs/next?wait=2")[1]["job"]
        assert again["type"] == "rewrite" and again["payload"]["note_from_user"] == "kürzer bitte"
        # a job handed out but never answered is handed out again
        assert api.call("/api/jobs/next?wait=1")[1]["job"]["id"] == again["id"]
    finally:
        httpd.shutdown()


@test
def the_app_starts_under_the_tools_own_python():
    """The private Python the setup installs does not put a script's own folder
    on the path, so a script that imports its neighbours without saying where
    they are does not start. -I gives any Python the same blind spot; where the
    private Python is installed on this computer, it is tried as well."""
    import subprocess
    scripts = os.path.join(ROOT, "agc-deal-flow-outreach", "scripts")
    pythons = [[sys.executable, "-I"]]
    private = os.path.join(os.environ.get("LOCALAPPDATA", ""), "AGC-DealFlow", "runtime", "python.exe")
    if os.path.exists(private):
        pythons.append([private])
    for python in pythons:
        home = tempfile.mkdtemp(prefix="start-", dir=TMP)
        env = dict(os.environ, AGC_OUTREACH_FAKE="1", AGC_OUTREACH_HOME=home)
        for name in ("AGC_OUTREACH_PORT", "AGC_OUTREACH_TOKEN"):
            env.pop(name, None)
        run = lambda *args: subprocess.run(python + list(args), env=env, capture_output=True, text=True, timeout=90)

        ready = run(os.path.join(scripts, "preflight.py"), "--quiet")
        assert ready.returncode == 0 and "Traceback" not in ready.stderr, (python, ready.stdout, ready.stderr)

        app = subprocess.Popen(python + [os.path.join(scripts, "server.py")], env=env, stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE, text=True)
        try:
            info = os.path.join(home, "server.json")
            for _ in range(80):
                if os.path.exists(info) or app.poll() is not None:
                    break
                time.sleep(0.25)
            assert app.poll() is None and os.path.exists(info), (python, app.stderr.read() if app.poll() is not None else "no server.json")
            status = run(os.path.join(scripts, "outreach.py"), "status")
            assert "Running at" in status.stdout and "tester@agcapital.example" in status.stdout, (python, status.stdout, status.stderr)
        finally:
            run(os.path.join(scripts, "outreach.py"), "stop")
            try:
                app.wait(timeout=15)
            except subprocess.TimeoutExpired:
                app.kill()
            # the pipes must be closed before the folder can be removed on Windows
            app.stdout.close()
            app.stderr.close()


def clean_slate():
    """Empty the folder next to the list, so the next test starts with everyone due."""
    folder = store.data_dir(store.load_settings()["workbook"])
    store.write_json(os.path.join(folder, "suppression.json"), {})
    for name in os.listdir(os.path.join(folder, "rounds")):
        os.remove(os.path.join(folder, "rounds", name))
    store.write_json(outlook._fake_path(), {"sent": [], "inbox": []})
    return folder


@test
def a_scheduled_round_can_send_without_review_if_the_user_said_so():
    """Runs after the tests above, on the same folders."""
    folder = clean_slate()
    httpd, app = server.make_server()
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    api = Client(httpd, app)
    try:
        api.until(lambda s: s["identity"].get("ok"))
        # the switch belongs to an automatic rhythm: without one it cannot be on
        api.call("/api/settings", {"schedule": {"mode": "manual"}})
        assert api.call("/api/settings", {"schedule": {"auto_send": True}})[0] == 400
        assert store.load_settings()["schedule"]["auto_send"] is False
        api.call("/api/settings", {"schedule": {"mode": "quarterly", "start_date": "2027-01-15", "time": "08:00"}})
        assert api.call("/api/settings", {"schedule": {"auto_send": True}})[0] == 200
        assert store.load_settings()["schedule"]["auto_send"] is True

        # a master email that would embarrass: the du version says Sie. Those emails fail a check.
        templates = store.load_settings()["templates"]
        api.call("/api/settings", {"templates": {"de_du": {"body": templates["de_du"]["body"].replace("bei dir", "bei Ihnen")}}})
        people = [c for c in api.state()["contacts"] if c["included"]]
        du = [c for c in people if c["language"] == "de" and c["form"] == "du"]
        assert du and len(people) > len(du)

        # starting a round by hand never sends, switch or no switch
        api.call("/api/round/start", {})
        s = api.state()
        assert not s["sending"]["active"] and all(d["status"] == "pending" for d in s["round"]["drafts"])
        assert outlook._fake_box()["sent"] == []
        api.call("/api/round/close", {"round_id": s["round"]["id"]})

        # the scheduled run does: everything that passed the checks goes, the rest is held back
        result = api.call("/api/scheduled", {})[1]
        assert result["started"] and result["sending"] == len(people) - len(du) and result["held"] == len(du), result
        s = api.until(lambda s: not s["sending"]["active"], 60)
        sent = outlook._fake_box()["sent"]
        assert len(sent) == len(people) - len(du) and not {m["to"] for m in sent} & {c["email"] for c in du}
        assert "without review" in s["app"]["notice"] and "%d were held back" % len(du) in s["app"]["notice"]
        held = [d for d in s["round"]["drafts"] if d["status"] == "pending"]
        assert {d["to"] for d in held} == {c["email"] for c in du} and all(d["level"] == "fail" for d in held)
        api.call("/api/round/close", {"round_id": s["round"]["id"]})

        # back to "only when I start it": the switch goes off with it
        api.call("/api/settings", {"schedule": {"mode": "manual"}})
        assert store.load_settings()["schedule"]["auto_send"] is False
    finally:
        api.call("/api/settings", {"templates": {"de_du": templates["de_du"]}, "schedule": {"mode": "manual"}})
        httpd.shutdown()


@test
def the_screen_speaks_german_when_asked():
    """Runs after the tests above, on the same folders."""
    import lang
    sys.path.insert(0, os.path.join(ROOT, "dev"))
    import ui_strings
    missing, _, keys, _ = ui_strings.report()
    assert not missing, "no German for: %s" % missing          # every sentence in app.js is in de.js
    assert lang.localize("written to 7 days ago", "de") == "vor 7 Tagen angeschrieben"
    assert lang.localize("written to 7 days ago", "en") == "written to 7 days ago"
    assert lang.localize("a sentence nobody translated", "de") == "a sentence nobody translated"

    clean_slate()
    httpd, app = server.make_server()
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    api = Client(httpd, app)
    try:
        api.until(lambda s: s["identity"].get("ok"))
        api.call("/api/round/start", {})
        assert api.call("/api/settings", {"language": "fr"})[0] == 200 and api.state()["settings"]["language"] == "en"
        english = api.state()
        api.call("/api/settings", {"language": "de"})
        assert store.load_settings()["language"] == "de"
        german = api.state()
        reasons = {c["reason"] for c in german["contacts"]}
        assert "vor 0 Tagen angeschrieben" not in reasons          # nobody has been written to yet
        assert {"gehört zu Somebody Else", "keine E-Mail-Adresse: anhaken, damit Claude es heraussucht",
                "in der Liste als „nicht kontaktieren“ markiert"} <= reasons, reasons
        assert german["schedule"]["labels"]["quarterly"] == "Jedes Quartal"
        flagged = [c["text"] for d in german["round"]["drafts"] for c in d["checks"]]
        assert flagged and all(t == "Herr/Frau fehlt in der Liste, daher ist die Anrede neutral." for t in flagged), flagged
        # what a person wrote is never touched: names, emails, the email text
        strip = lambda s: [(d["contact_id"], d["body"], d["subject"]) for d in s["round"]["drafts"]]
        assert strip(german) == strip(english)
        # an error comes back in German too
        code, answer = api.call("/api/round/start", {})
        assert code == 400 and answer["error"].startswith("Es ist bereits eine Runde offen"), answer
        # and on disk everything stays in English, so the next person reads it in their own language
        saved = store.load_rounds(store.data_dir(store.load_settings()["workbook"]))[0]
        assert all(c["text"].endswith("so the greeting is a neutral one.") for d in saved["drafts"] for c in d["checks"])
        api.call("/api/round/close", {"round_id": german["round"]["id"]})
    finally:
        api.call("/api/settings", {"language": "en"})
        httpd.shutdown()


# ---- AGC's own list ------------------------------------------------------------

@test
def the_agc_list_is_read_with_all_its_rows_and_columns():
    book = contacts.read_workbook(COCKPIT)
    assert book["ok"], book["problem"]
    # the contacts sheet and the hidden bank sheet; the sheets without addresses are left alone
    assert book["sheets"] == ["Intermediäre", "Raiffeisen"], book["sheets"]
    assert len(book["contacts"]) == 17, len(book["contacts"])
    assert book["missing_columns"] == [] and set(book["worked_out"]) == {"gender", "language", "form"}
    by = {(c["company"], c["last"]): c for c in book["contacts"]}
    hagen = by[("Lindengrund Partners", "Hagen")]
    assert (hagen["first"], hagen["email"], hagen["owner"], hagen["city"], hagen["country"], hagen["state"]) == \
        ("Michael", "mh@lindengrund.example", "VK", "Wien", "AT", "Wien")
    assert (hagen["priority"], hagen["relevance"], hagen["type"], hagen["notes"]) == \
        ("B", "high", "M&A adviser", "Kennt den Markt für Nachfolgen")
    # every column without a field of its own travels with the contact
    assert hagen["extra"]["UP/Info gesendet"] == "ja" and hagen["extra"]["Prio. Erinnerung"] == "B"
    assert "01-02 2026 Plan" in hagen["extra"] and "01-02 2026 Plan (T)" in hagen["extra"]
    # two people in one cell: the one the address belongs to is written to, the other is kept as a note
    two = by[("Seeblick Capital", "Paulsen")]
    assert two["first"] == "" and two["others"] == ["Andreas Roth"], two
    rosner = by[("Weidenhof Advisory", "Rosner")]
    assert rosner["first"] == "Roman" and "first name taken from the email address" in rosner["assumed"]
    assert rosner["country"] == "DE" and rosner["state"] == "Bayern"
    # "Hr." says Herr; "Dr. Barbist, Johannes" is one person written surname first
    assert by[("Nordlicht Corporate Finance", "Zeller")]["gender"] == "m"
    barbist = by[("Krähenfeld Steuerberatung", "Barbist")]
    assert (barbist["title"], barbist["first"]) == ("Dr.", "Johannes")
    assert contacts.greeting(barbist)[0] == "Guten Tag Dr. Johannes Barbist,"
    # "Name <address>" and two addresses in one cell
    assert by[("Uferweg Rechtsanwälte", "Dorn")]["email"] == "dorn@uferweg.example"
    hahn = by[("Abendrot Finanz", "Hahn")]
    assert hahn["email"] == "felix.hahn@abendrot.example" and hahn["extra"]["Further addresses"] == "office@abendrot.example"
    # a cell comment, without Excel's notice and the author's name
    assert by[("Kobaltblau Consulting", "Kranz")]["comments"] == ["Hat das Unternehmen gewechselt, neue Adresse folgt"]
    # the date of the first contact, from the list
    assert barbist["first_contact_date"] == "2026-09-30"
    # English for a contact in London; "Kl" is KL
    assert by[("Thames Bridge Advisors", "Shore")]["language"] == "en"
    assert by[("Eichenhain Beratung", "Bezner")]["owner"] == "KL"
    # an X under a row of short forms says who looks after a contact
    assert by[("Landesbank Beispiel", "Rainer")]["owner"] == "VKO"
    # what is missing is a problem a look online can solve, not a dead end
    assert by[("Talblick Holding", "")]["problems"] == ["no name"]
    assert by[("Bergkamm Ventures", "Lindner")]["problems"] == ["no email address"]
    assert book["owners"]["VK"] == 11


@test
def whose_contact_it_is_comes_from_the_short_form():
    assert contacts.initials("Vsevolod Kornilov") == "VK" and contacts.initials("Kornilov, Vsevolod") == "VK"
    assert contacts.code_for("Vsevolod Kornilov", "vk@agcapital.example") == "VK"
    assert contacts.code_for("", "max.mustermann@agcapital.example") == "MM"
    assert contacts.code_for("Max Mustermann", "mm@agcapital.example") == "MM"
    mine = lambda owner, code="VK": contacts.is_mine({"owner": owner}, "", "", code, False)
    assert mine("VK") and mine("VKO") and mine("KL, VK") and not mine("KL") and not mine("KLA")
    assert not mine("") and contacts.is_mine({"owner": ""}, "", "", "VK", True)
    book = contacts.read_workbook(COCKPIT)
    assert contacts.uses_codes(book["contacts"]) and not contacts.uses_codes(contacts.read_workbook(FIXTURE)["contacts"])
    settings = dict(store.DEFAULT_SETTINGS, owner_code="VK")
    rows = {(c["company"], c["last"]): c for c in contacts.select(book["contacts"], settings, ME, {}, {})}
    assert rows[("Lindengrund Partners", "Hagen")]["included"]
    assert rows[("Silberau Partners", "Pöschl")]["reason"] == "belongs to KL"
    assert rows[("Grünspan Capital", "Kern")]["reason"] == "nobody is responsible for this contact in the list"
    assert rows[("Landesbank Beispiel", "Rainer")]["included"]
    assert rows[("Krähenfeld Steuerberatung", "Barbist")]["reason"] == "first contacted %d days ago according to the list" \
        % (dt.date.today() - dt.date(2026, 9, 30)).days
    # missing details: left out, but a tick brings them in for Claude to look up
    lindner = rows[("Bergkamm Ventures", "Lindner")]
    assert not lindner["included"] and not lindner["locked"] and lindner["research"] == ["email"]
    assert lindner["reason"] == "no email address: tick to have Claude look it up"
    ticked = {c["id"]: c for c in contacts.select(book["contacts"], settings, ME, {}, {}, {lindner["id"]: True})}
    assert ticked[lindner["id"]]["included"] and ticked[lindner["id"]]["reason"] == "Claude will look up the missing details"
    assert rows[("Morgenrot M&A", "")]["research"] == ["email", "person"]
    # a list of names (the template): an empty Owner cell is whoever runs the round
    assert contacts.unassigned_is_mine(contacts.read_workbook(FIXTURE)["contacts"], store.DEFAULT_SETTINGS)


@test
def filters_decide_who_is_in_the_round():
    book = contacts.read_workbook(COCKPIT)
    base = dict(store.DEFAULT_SETTINGS, owner_code="VK")
    inside = lambda **f: {c["company"] for c in contacts.select(
        book["contacts"], dict(base, filters=dict(store.DEFAULT_SETTINGS["filters"], **f)), ME, {}, {}) if c["included"]}
    everyone = inside()
    assert {"Lindengrund Partners", "Nordlicht Corporate Finance", "Thames Bridge Advisors"} <= everyone
    austria = inside(countries=["AT"])
    assert "Lindengrund Partners" in austria and "Nordlicht Corporate Finance" not in austria and "Thames Bridge Advisors" not in austria
    assert inside(countries=["AT"], states=["Wien"]) == {"Lindengrund Partners", "Seeblick Capital"}
    assert inside(priorities=["A", "B"]) == {"Lindengrund Partners", "Uferweg Rechtsanwälte"}
    assert inside(relevance=["high"]) == {"Lindengrund Partners", "Uferweg Rechtsanwälte"}
    left = {c["company"]: c["reason"] for c in contacts.select(
        book["contacts"], dict(base, filters=dict(store.DEFAULT_SETTINGS["filters"], countries=["DE"])), ME, {}, {})}
    assert left["Lindengrund Partners"] == "outside your region filter"


def _as_claude(api, kind, seconds=5):
    job = api.call("/api/jobs/next?wait=%d" % seconds)[1]["job"]
    assert job and job["type"] == kind, job
    return job


@test
def claude_prepares_looks_up_and_keeps_sie_and_du_in_step():
    """AGC's own list, start to finish: Claude adjusts each email to the list,
    looks up a missing address, files go out with the emails, the reviewer
    refers to an earlier email, the du version is written from the Sie one,
    and only the first answer is read."""
    home_before = os.environ["AGC_OUTREACH_HOME"]
    os.environ["AGC_OUTREACH_HOME"] = os.path.join(TMP, "home-agc")
    book = os.path.join(TMP, "agc", "Deal_Origination_Cockpit.xlsx")
    os.makedirs(os.path.dirname(book))
    shutil.copy(COCKPIT, book)
    httpd, app = server.make_server()
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    api = Client(httpd, app)
    try:
        api.until(lambda s: s["identity"].get("ok"))
        api.call("/api/settings", {"workbook": book, "owner_code": "vk", "theme": "dark"})
        s = api.state()
        assert s["settings"]["owner_code"] == "VK" and s["settings"]["theme"] == "dark"
        assert s["settings"]["personalize"] and s["settings"]["sync_forms"]
        assert s["workbook"]["sheets"] == ["Intermediäre", "Raiffeisen"] and s["workbook"]["uses_codes"]
        assert not s["workbook"]["unassigned_mine"]
        assert "extra" not in s["contacts"][0]                       # the screen gets what it shows, not the whole row
        assert {"value": "AT", "n": 9} in s["filter_options"]["countries"]

        # Sie and du: writing one has Claude write the other
        api.call("/api/settings", {"templates": {"de_sie": {"subject": "Kurze Frage", "body":
                 "ich melde mich bei Ihnen, weil wir Unternehmen suchen.\n\nFalls Ihnen etwas begegnet, freue ich mich.\n\nBeste Grüße"}}})
        api.call("/api/template/sync", {"key": "de_sie"})
        api.call("/api/template/sync", {"key": "de_sie"})            # twice: still one job
        assert api.state()["template_sync"]["de_du"]["state"] == "working"
        conv = _as_claude(api, "convert")
        assert conv["payload"]["source_form"] == "Sie" and conv["payload"]["target_form"] == "du"
        assert len([j for j in api.state()["jobs"] if j["type"] == "convert"]) == 1
        du_text = "ich melde mich bei dir, weil wir Unternehmen suchen.\n\nFalls dir etwas begegnet, freue ich mich.\n\nLiebe Grüße"
        back = api.call("/api/jobs/%s/result" % conv["id"], {"subject": "Kurze Frage", "body": du_text})[1]
        assert back["ok"] and back["template_problems"] == []
        s = api.state()
        assert s["settings"]["templates"]["de_du"]["body"] == du_text
        assert s["template_sync"]["de_du"]["state"] == "fresh"
        api.call("/api/template/sync", {"key": "de_sie"})            # nothing changed: no new job
        assert not [j for j in api.state()["jobs"] if j["type"] == "convert"]
        # a version changed while Claude was writing is not overwritten
        api.call("/api/settings", {"templates": {"de_du": {"body": du_text + " "}}})
        api.call("/api/template/sync", {"key": "de_du"})
        late = _as_claude(api, "convert")
        api.call("/api/settings", {"templates": {"de_du": {"body": du_text}}})
        stale = api.call("/api/jobs/%s/result" % late["id"], {"subject": "x", "body": "something else"})[1]
        assert stale["ok"] and "not used" in stale["note"]
        assert "Ihnen" in store.load_settings()["templates"]["de_sie"]["body"]

        # a file for every email of the round
        pdf = base64.b64encode(b"%PDF-1.4 invented teaser").decode("ascii")
        code, added = api.call("/api/attachments/add", {"target": "master", "kind": "round",
                                                        "files": [{"name": "..\\\\AGC Teaser.pdf", "data": pdf}]})
        assert code == 200 and added["added"][0]["name"] == "AGC Teaser.pdf", added
        assert [a["name"] for a in api.state()["settings"]["attachments"]["round"]] == ["AGC Teaser.pdf"]

        # tick a contact without an address, so Claude looks it up
        lindner = next(c for c in api.state()["contacts"] if c["last"] == "Lindner")
        assert not lindner["included"] and lindner["research"] == ["email"]
        api.call("/api/override", {"contact_id": lindner["id"], "included": True})
        assert api.call("/api/round/start", {})[0] == 200
        s = api.state()
        rnd = s["round"]
        rid = rnd["id"]
        by_last = {d["contact"]["last"]: d for d in rnd["drafts"]}
        assert by_last["Lindner"]["status"] == "research" and by_last["Lindner"]["to"] == ""
        assert all(d["status"] == "preparing" for d in rnd["drafts"] if d["contact"]["last"] != "Lindner")
        assert all(d["attachments"][0]["name"] == "AGC Teaser.pdf" for d in rnd["drafts"])
        assert api.call("/api/draft/update", {"round_id": rid, "contact_id": by_last["Hagen"]["contact_id"],
                                              "change": {"status": "approved"}})[0] == 400      # not ready yet

        # Claude adjusts the emails to the list: the greeting from the name, one line where the row says so
        prep = _as_claude(api, "personalize")
        emails = {e["contact"]["last"]: e for e in prep["payload"]["emails"]}
        assert "Lindner" not in emails and emails["Hagen"]["rule_greeting"] == "Guten Tag Michael Hagen,"
        assert emails["Hagen"]["contact"]["extra"]["UP/Info gesendet"] == "ja"
        hagen = emails["Hagen"]
        line = hagen["email_now"].replace("Guten Tag Michael Hagen,", "Sehr geehrter Herr Hagen,")
        line = line.replace("Beste Grüße", "Sie kennen den Markt für Nachfolgen wie kaum jemand.\n\nBeste Grüße")
        part = api.call("/api/jobs/%s/result" % prep["id"], {"drafts": [
            {"contact_id": hagen["contact_id"], "greeting": "Sehr geehrter Herr Hagen", "body": line},
            {"contact_id": "nobody@nowhere.example", "greeting": "Hallo,"}]})[1]
        assert not part["ok"] and len(part["still_to_do"]) == len(emails) - 1
        rest = [{"contact_id": e["contact_id"], "greeting": e["rule_greeting"]} for k, e in emails.items() if k != "Hagen"]
        assert api.call("/api/jobs/%s/result" % prep["id"], {"drafts": rest})[1]["still_to_do"] == []
        d = api.draft(hagen["contact_id"])
        assert d["status"] == "pending" and d["greeting"] == "Sehr geehrter Herr Hagen," and d["changed_by"] == "list"
        assert d["standard"].startswith("Sehr geehrter Herr Hagen,\n\n") and not [c for c in d["checks"] if c["level"] == "fail"]
        shore = next(x for x in api.state()["round"]["drafts"] if x["contact"]["last"] == "Shore")
        assert shore["template"] == "en" and shore["body"].startswith("Dear David Shore,")

        # Claude looks the missing address up; it is shown, not used, until the reviewer says so
        look = _as_claude(api, "research")
        assert look["payload"]["contacts"][0]["missing"] == ["email"]
        cid = look["payload"]["contacts"][0]["contact_id"]
        bad = api.call("/api/jobs/%s/result" % look["id"], {"found": [{"contact_id": cid, "email": "p.lindner@bergkamm.example"}]})[1]
        assert not bad["ok"] and "source" in bad["problems"][0]           # where it was found must be said
        found = {"contact_id": cid, "email": "p.lindner@bergkamm.example", "first": "Petra", "last": "Lindner",
                 "gender": "f", "role": "Partnerin", "greeting": "Sehr geehrte Frau Lindner,",
                 "source": "https://bergkamm.example/team", "confidence": "high", "note": "Team page"}
        assert api.call("/api/jobs/%s/result" % look["id"], {"found": [found]})[1]["ok"]
        d = api.draft(cid)
        assert d["status"] == "pending" and d["to"] == "" and d["research"]["status"] == "found"
        assert ("research", "fail") in ids(d["checks"])
        assert api.call("/api/draft/update", {"round_id": rid, "contact_id": cid, "change": {"status": "approved"}})[0] == 400
        assert api.call("/api/draft/accept-research", {"round_id": rid, "contact_id": cid})[0] == 200
        d = api.draft(cid)
        assert d["to"] == "p.lindner@bergkamm.example" and d["body"].startswith("Sehr geehrte Frau Lindner,\n\n")
        assert d["research"]["accepted"] and d["level"] != "fail", d["checks"]
        assert "p.lindner" not in open(book, "rb").read().decode("latin-1")      # the list is never written to

        # one email without the file, another with one more
        api.call("/api/attachments/remove", {"target": "draft", "round_id": rid, "contact_id": shore["contact_id"],
                                             "id": added["added"][0]["id"]})
        api.call("/api/attachments/add", {"target": "draft", "round_id": rid, "contact_id": hagen["contact_id"],
                                          "files": [{"name": "Investmentkriterien.pdf", "data": base64.b64encode(b"criteria").decode()}]})
        assert api.draft(shore["contact_id"])["attachments"] == []
        assert [a["name"] for a in api.draft(hagen["contact_id"])["attachments"]] == ["AGC Teaser.pdf", "Investmentkriterien.pdf"]

        api.call("/api/draft/approve-all", {"round_id": rid})
        going = [x["contact_id"] for x in api.state()["round"]["drafts"] if x["status"] == "approved"]
        assert cid in going and hagen["contact_id"] in going
        api.call("/api/send", {"round_id": rid, "ids": going, "confirm": True})
        api.until(lambda s: not s["sending"]["active"], 60)
        sent = {m["to"]: m for m in outlook._fake_box()["sent"]}
        assert sent["mh@lindengrund.example"]["attachments"] == ["AGC Teaser.pdf", "Investmentkriterien.pdf"]
        assert sent["david@thamesbridge.example"]["attachments"] == []
        assert sent["p.lindner@bergkamm.example"]["body"].startswith("Sehr geehrte Frau Lindner,")

        # only the first answer: a second message in the same thread is left alone
        hm = sent["mh@lindengrund.example"]
        box = outlook._fake_box()
        first_at = store.stamp(store.now() + dt.timedelta(minutes=1))
        box["inbox"] = [{"kind": "reply", "from_email": hm["to"], "from_name": "H", "received": first_at,
                         "subject": "AW: " + hm["subject"], "text": "Wir hätten ein Unternehmen im Kopf.",
                         "conversation_id": hm["conversation_id"]}]
        store.write_json(outlook._fake_path(), box)
        api.call("/api/replies/check", {})
        api.until(lambda s: not s["checking"]["active"] and s["checking"]["last"])
        job = _as_claude(api, "classify")
        assert len(job["payload"]["answers"]) == 1 and len(job["payload"]["answers"][0]["messages"]) == 1
        api.call("/api/jobs/%s/result" % job["id"], {"answers": [{"round_id": rid, "contact_id": hagen["contact_id"],
                                                                 "outcome": "lead", "summary": "Has a company in mind.",
                                                                 "quote": "", "next_step": "Call."}]})
        box = outlook._fake_box()
        box["inbox"].append({"kind": "reply", "from_email": hm["to"], "from_name": "H",
                             "received": store.stamp(store.now() + dt.timedelta(minutes=2)), "subject": "AW: AW: x",
                             "text": "Und noch etwas: rufen Sie mich an.", "conversation_id": hm["conversation_id"]})
        store.write_json(outlook._fake_path(), box)
        api.call("/api/replies/check", {})
        api.until(lambda s: not s["checking"]["active"])
        assert not [j for j in api.state()["jobs"] if j["type"] == "classify"]
        row = next(r for r in next(x for x in api.state()["rounds"] if x["id"] == rid)["rows"] if r["contact_id"] == hagen["contact_id"])
        assert row["outcome"] == "lead" and row["summary"] == "Has a company in mind."

        # "refer to the email from last week": Claude gets what was written with this address
        api.call("/api/settings", {"filters": {"countries": ["GB"]}})
        assert [c["last"] for c in api.state()["contacts"] if c["included"]] == []      # Shore was written to today
        api.call("/api/settings", {"filters": {"countries": []}})
        for c in api.state()["contacts"]:
            if c["last"] == "Pöschl":
                api.call("/api/override", {"contact_id": c["id"], "included": True})
        api.call("/api/settings", {"personalize": False})
        api.call("/api/round/start", {})
        rnd2 = api.state()["round"]
        target = next(x for x in rnd2["drafts"] if x["contact"]["last"] == "Pöschl")
        box = outlook._fake_box()
        box["inbox"].append({"kind": "reply", "from_email": "j.poeschl@silberau.example", "from_name": "P",
                             "received": store.stamp(store.now() - dt.timedelta(days=14)), "subject": "Deal Waldviertel",
                             "text": "Anbei die Unterlagen zum Deal Waldviertel, Umsatz 2025 rund 40 Mio.", "conversation_id": "OLD"})
        store.write_json(outlook._fake_path(), box)
        api.call("/api/draft/redraft", {"round_id": rnd2["id"], "contact_id": target["contact_id"],
                                        "note": "nimm Bezug auf die E-Mail von vor zwei Wochen zum Deal"})
        job = _as_claude(api, "rewrite")
        history = job["payload"]["mail_history"]
        assert len(history) == 1 and history[0]["subject"] == "Deal Waldviertel" and history[0]["direction"] == "in"
        body = job["payload"]["email_now"].replace("Beste Grüße", "Danke noch für die Unterlagen zum Deal Waldviertel mit rund 40 Mio. Umsatz.\n\nBeste Grüße")
        api.call("/api/jobs/%s/result" % job["id"], {"drafts": [{"contact_id": target["contact_id"], "body": body}]})
        d = api.draft(target["contact_id"])
        assert ("unsupported", "warn") not in ids(d["checks"]), d["checks"]       # 40 is in the earlier email
        # an email the note points to that is not there: Claude says so, and the email comes back unchanged
        api.call("/api/draft/redraft", {"round_id": rnd2["id"], "contact_id": target["contact_id"],
                                        "note": "erwähne seine Mail vom Jänner"})
        job = _as_claude(api, "rewrite")
        api.call("/api/jobs/%s/fail" % job["id"], {"reason": "No email from January was found."})
        s = api.state()
        assert api.draft(target["contact_id"])["status"] == "pending"
        assert s["app"]["notice"].endswith("No email from January was found."), s["app"]["notice"]
        api.call("/api/round/close", {"round_id": rnd2["id"]})
    finally:
        httpd.shutdown()
        os.environ["AGC_OUTREACH_HOME"] = home_before


@test
def a_scheduled_round_waits_for_claude_before_sending_unreviewed():
    home_before = os.environ["AGC_OUTREACH_HOME"]
    os.environ["AGC_OUTREACH_HOME"] = os.path.join(TMP, "home-agc-scheduled")
    book = os.path.join(TMP, "agc2", "Cockpit.xlsx")
    os.makedirs(os.path.dirname(book))
    shutil.copy(COCKPIT, book)
    httpd, app = server.make_server()
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    api = Client(httpd, app)
    try:
        api.until(lambda s: s["identity"].get("ok"))
        store.write_json(outlook._fake_path(), {"sent": [], "inbox": []})
        api.call("/api/settings", {"workbook": book, "owner_code": "VK",
                                   "schedule": {"mode": "quarterly", "start_date": "2027-01-15", "time": "08:00"}})
        api.call("/api/settings", {"schedule": {"auto_send": True}})
        result = api.call("/api/scheduled", {})[1]
        assert result["started"] and result.get("preparing") and result["sending"] == 0, result
        assert outlook._fake_box()["sent"] == []                      # nothing goes before Claude is done
        job = next(j for j in iter(lambda: api.call("/api/jobs/next?wait=3")[1]["job"], None) if j["type"] == "personalize")
        api.call("/api/jobs/%s/result" % job["id"], {"drafts": [{"contact_id": e["contact_id"], "greeting": e["rule_greeting"]}
                                                                for e in job["payload"]["emails"]]})
        api.until(lambda s: not s["sending"]["active"] and outlook._fake_box()["sent"], 60)
        assert len(outlook._fake_box()["sent"]) == len(job["payload"]["emails"])
        assert "without review" in api.state()["app"]["notice"]
    finally:
        api.call("/api/settings", {"schedule": {"mode": "manual"}})
        httpd.shutdown()
        os.environ["AGC_OUTREACH_HOME"] = home_before


if __name__ == "__main__":
    failed = [r for r in RESULTS if not r[1]]
    for name, ok, detail in RESULTS:
        print("%s  %s" % ("ok  " if ok else "FAIL", name.replace("_", " ")))
        if not ok:
            print(detail)
    print("\n%d of %d passed" % (len(RESULTS) - len(failed), len(RESULTS)))
    shutil.rmtree(TMP, ignore_errors=True)
    sys.exit(1 if failed else 0)
