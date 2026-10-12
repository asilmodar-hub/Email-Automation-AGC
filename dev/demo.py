#!/usr/bin/env python3
"""Run the tool against the stand-in mailbox, with a stand-in for Claude too,
so the screen can be clicked through from start to finish without a real
email, a real contact or a Claude session.

    python dev/demo.py [--port 8765] [--fresh] [--live]

Then open  http://127.0.0.1:8765/?t=demo

Everything lives in dev/tmp and is thrown away with --fresh.

Without --live, a rule plays Claude's part. It cannot write: asked to change an
email it puts a clearly labelled placeholder where Claude's sentence would go.
It shows the flow, nothing more.

With --live, nobody plays Claude. A real Claude session connects to the demo
the way the skill does and answers "Ask Claude", "Check for answers" and the
rhythm for real, still against the stand-in mailbox:

    set AGC_OUTREACH_FAKE=1
    set AGC_OUTREACH_HOME=<this folder>\\tmp\\home
    python agc-deal-flow-outreach\\scripts\\outreach.py wait
"""
import datetime as dt
import os
import shutil
import sys
import threading
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TMP = os.path.join(ROOT, "dev", "tmp")
if "--fresh" in sys.argv:
    shutil.rmtree(TMP, ignore_errors=True)
port = sys.argv[sys.argv.index("--port") + 1] if "--port" in sys.argv else "8765"
os.environ.update(AGC_OUTREACH_FAKE="1", AGC_OUTREACH_HOME=os.path.join(TMP, "home"),
                  AGC_OUTREACH_PORT=port, AGC_OUTREACH_TOKEN="demo")
os.environ.setdefault("AGC_OUTREACH_GAP", "1.2")
sys.path.insert(0, os.path.join(ROOT, "agc-deal-flow-outreach", "scripts"))

import outlook  # noqa: E402
import server  # noqa: E402
import store  # noqa: E402

# What the stand-in puts in when asked to change an email: a placeholder that
# says what it is. Passing the reviewer's note off as a written sentence would
# look like Claude's work, and it is not.
ADDED = "[Demo stand-in, not Claude. The real Claude would change the email here as asked: “%s”]"
LOOKING_FOR = {
    "de": "mittelständische Unternehmen in Österreich und Süddeutschland, oft mit offener Nachfolge",
    "en": "mid-sized companies in Austria and southern Germany, often where a succession is open",
}
ANSWERS = [
    ("reply", "Danke für die Nachricht. Ich hätte tatsächlich einen Mandanten, der über einen Verkauf nachdenkt. "
              "Rufen Sie mich diese Woche gern an.", "lead", "Has a client who is considering a sale.", "Call this week."),
    ("reply", "Bei mir ist gerade nichts dabei, aber sprechen Sie mit meiner Kollegin Frau Dr. Lindner, sie betreut "
              "zwei Nachfolgefälle.", "referral", "Points to a colleague, Dr. Lindner, who has two succession cases.",
     "Ask for an introduction to Dr. Lindner."),
    ("reply", "Momentan leider nichts Passendes. Melden Sie sich gern im Frühjahr wieder.", "later",
     "Nothing at the moment; asks to be contacted again in spring.", "Write again in spring."),
    ("reply", "Vielen Dank, aber das ist kein Thema für uns.", "decline", "Not a topic for them.", ""),
    ("reply", "Bitte nehmen Sie mich aus Ihrem Verteiler.", "do_not_contact", "Asked to be removed.", ""),
    ("auto", "Ich bin bis Montag nicht im Büro.", None, None, None),
    ("bounce", "Delivery has failed to this recipient.", None, None, None),
]


def play_claude(app):
    """Answer every job the way the skill would, by rule."""
    while True:
        job = app.next_job(5)
        if not job:
            continue
        time.sleep(2.5)
        p = job["payload"]
        if job["type"] == "rewrite":
            greeting, rest = p["email_now"].split("\n\n", 1)
            body = greeting + "\n\n" + ADDED % p["note_from_user"] + "\n\n" + rest
            with app.lock:
                app.take_rewrite(job, {"drafts": [{"contact_id": p["contact_id"], "body": body}]})
        elif job["type"] == "classify":
            out = []
            for a in p["answers"]:
                text = a["messages"][-1]["text"]
                match = next((x for x in ANSWERS if x[1][:30] == text[:30]), ANSWERS[2])
                out.append({"round_id": a["round_id"], "contact_id": a["contact_id"], "outcome": match[2],
                            "summary": match[3], "quote": text[:140], "next_step": match[4]})
            with app.lock:
                app.take_classification(job, {"answers": out})
        elif job["type"] == "schedule":
            with app.lock:
                app.take_schedule(job, {"ok": True})


def answer_mail():
    """Once emails have gone out, let a few of the recipients 'answer'."""
    answered = set()
    while True:
        time.sleep(2)
        box = outlook._fake_box()
        sent = [m for m in box["sent"] if not m["subject"].startswith("[Test")]
        changed = False
        for m, (kind, text, _, _, _) in zip(sent, ANSWERS):
            if m["conversation_id"] in answered or any(i["conversation_id"] == m["conversation_id"] for i in box["inbox"]):
                continue
            answered.add(m["conversation_id"])
            box["inbox"].append({"kind": kind, "from_email": m["to"], "from_name": m["to"],
                                 "received": store.stamp(store.now() + dt.timedelta(seconds=30)),
                                 "subject": "AW: " + m["subject"], "text": text,
                                 "conversation_id": m["conversation_id"]})
            changed = True
        if changed:
            store.write_json(outlook._fake_path(), box)


def main():
    book = os.path.join(TMP, "Contacts", "AGC contacts.xlsx")
    if not os.path.exists(book):
        os.makedirs(os.path.dirname(book), exist_ok=True)
        shutil.copy(os.path.join(ROOT, "dev", "fixtures", "contacts_50.xlsx"), book)
    httpd, app = server.make_server()
    if not app.settings["workbook"]:
        done = {}
        for key, t in app.settings["templates"].items():
            body = t["body"]
            if "[[" in body:
                body = body[:body.find("[[")] + LOOKING_FOR["en" if key.endswith("en") else "de"] + body[body.find("]]") + 2:]
            done[key] = {"subject": t["subject"], "body": body}
        app.save({"workbook": book, "templates": done})
    # so that 'outreach wait' and 'outreach submit' find this demo, as they find the real app
    store.write_json(server.info_path(), {"port": int(port), "token": app.token, "pid": os.getpid(),
                                          "url": "http://127.0.0.1:%s/?t=demo" % port, "started": store.stamp()})
    if "--live" not in sys.argv:
        threading.Thread(target=play_claude, args=(app,), daemon=True).start()
    threading.Thread(target=answer_mail, daemon=True).start()
    print("Open  http://127.0.0.1:%s/?t=demo" % port, flush=True)
    httpd.serve_forever()


if __name__ == "__main__":
    main()
