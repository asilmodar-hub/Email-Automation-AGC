#!/usr/bin/env python3
"""Walk through the steps of sending on the real classic Outlook, stopping
before anything is saved or sent. Nothing is left in the mailbox.

    python dev/outlook_dryrun.py

It shows whether Outlook has a window (and opens one, minimised, if not),
whether the signature loads the quiet way and in the email's own window, and
whether an address is accepted. The one step it cannot try is Send itself.
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "agc-deal-flow-outreach", "scripts"))
os.environ.pop("AGC_OUTREACH_FAKE", None)

import outlook  # noqa: E402


def walk(w):
    app, ns = w.connect()
    out = ["Outlook %s, windows before: %d" % (app.Version, app.Explorers.Count)]
    opened = outlook._show_outlook(app, ns)
    out.append("window %s, windows now: %d" % ("opened, minimised" if opened else "was already there", app.Explorers.Count))
    me = ns.Accounts.Item(1).SmtpAddress
    for in_window in (False, True):
        mail = app.CreateItem(outlook.OL_MAIL_ITEM)
        try:
            mail.To = me
            mail.Subject = "dry run, never saved or sent"
            if in_window:
                mail.Display(False)
            else:
                _ = mail.GetInspector
            html = mail.HTMLBody or ""
            combined = outlook.insert_above_signature(html, "Zeile eins\n\nZeile zwei")
            if combined:
                mail.HTMLBody = combined
            resolved = mail.Recipients.ResolveAll()
            out.append("%-22s signature %s, text placed %s, address accepted %s"
                       % ("in its own window:" if in_window else "the quiet way:",
                          "loaded" if len(html) > 500 else "EMPTY", bool(combined), bool(resolved)))
        finally:
            mail.Close(outlook.OL_DISCARD)           # unsaved: disappears without a trace
    return out


if __name__ == "__main__":
    for line in outlook.call(walk, timeout=120):
        print(line)
