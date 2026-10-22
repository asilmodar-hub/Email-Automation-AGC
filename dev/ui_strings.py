#!/usr/bin/env python3
"""Every sentence the screen can show, and whether it has a German version.

    python dev/ui_strings.py            list what is missing from de.js, and what de.js has that is unused
    python dev/ui_strings.py --all      list every key

Used by the tests too: a sentence added to app.js without German fails them.
"""
import json
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UI = os.path.join(ROOT, "agc-deal-flow-outreach", "assets", "ui")

# Sentences that reach t() through a variable, so the pattern below cannot see them.
BY_VARIABLE = [
    "Setup", "Contacts", "Review", "Tracker",
    "German, Sie", "German, du", "English",
    "Deal lead", "Referral", "Not now", "Decline", "Out of office", "Bounced", "Do not contact", "No reply yet",
    "Law firm", "Tax / audit", "M&A adviser", "Consultant", "Bank", "Private equity", "Venture capital", "Other",
    "In this round", "Left out", "All", "To review", "Changed", "Approved",
    "Type", "Role", "Relationship", "Sector focus", "Notes", "Last written",
    "Responsible", "Region", "Priority", "Relevance", "To do", "Comments", "Also named",
    "Details missing", "Found online",
    "Austria", "Germany", "Switzerland", "Liechtenstein", "Luxembourg", "United Kingdom", "United States",
    "Czech Republic", "Poland", "Italy", "Romania", "Hungary", "Slovakia", "Slovenia", "Croatia", "Netherlands",
    "France", "Spain", "Sweden", "Denmark", "Belgium", "Several countries", "Not known",
    "High", "Medium", "Low", "Not set",
    "Sure: named on the firm’s own website", "Fairly sure", "Not sure: please check",
    "Email", "Name", "Herr/Frau", "Language", "Sie/du",
]
STRING = r'"((?:[^"\\]|\\.)*)"|\'((?:[^\'\\]|\\.)*)\''
CALL = re.compile(r'\bt[fn]?\(\s*(?:[\w.]+\s*,\s*)?(?:%s)(?:\s*,\s*(?:%s))?' % (STRING, STRING))


def used():
    src = open(os.path.join(UI, "app.js"), encoding="utf-8").read()
    keys = set(BY_VARIABLE)
    for m in CALL.finditer(src):
        for raw, quote in ((m.group(1), '"'), (m.group(2), "'"), (m.group(3), '"'), (m.group(4), "'")):
            if raw is not None:
                keys.add(json.loads('"%s"' % raw.replace('\\\'', "'")) if quote == '"'
                         else json.loads('"%s"' % raw.replace('\\\'', "'").replace('"', '\\"')))
    return keys


def german():
    """The dictionary, read the way a browser reads it."""
    code = ("global.window = {}; require(%s); process.stdout.write(JSON.stringify(window.AGC_DE));"
            % json.dumps(os.path.join(UI, "de.js")))
    out = subprocess.run(["node", "-e", code], capture_output=True, check=True)
    return json.loads(out.stdout.decode("utf-8"))


def report():
    keys, de = used(), german()
    return sorted(keys - set(de)), sorted(set(de) - keys), keys, de


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    if "--all" in sys.argv:
        print("\n".join(sorted(used())))
        sys.exit(0)
    missing, unused, keys, de = report()
    print("%d sentences on the screen, %d in the German dictionary" % (len(keys), len(de)))
    for k in missing:
        print("NO GERMAN:", k)
    for k in unused:
        print("not used :", k)
    sys.exit(1 if missing else 0)
