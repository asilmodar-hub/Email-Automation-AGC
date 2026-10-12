#!/usr/bin/env python3
"""Is this computer ready to run the deal-flow outreach tool?

Checks that the packages load and that classic Outlook answers, and says what
it found in plain sentences. It installs nothing and sends nothing.

Exit codes:
    0  ready
    1  usable for preparing drafts, but Outlook could not be reached
    2  not usable, a package is missing
"""
import importlib
import sys

PACKAGES = [
    ("openpyxl", "reads the contact list and writes the tracker export"),
    ("win32com.client", "drives classic Outlook"),
]


def have(mod):
    try:
        importlib.import_module(mod)
        return True
    except Exception:
        return False


def main():
    quiet = "--quiet" in sys.argv
    missing = [(name, why) for name, why in PACKAGES if not have(name)]
    ident = {"ok": False, "problem": "The Outlook connector is not installed."}
    if not any(name.startswith("win32com") for name, _ in missing):
        import outlook
        ident = outlook.identity()
    line = ("Classic Outlook %s answers; mailbox %s" % (ident.get("version", ""), ident.get("email", ""))
            if ident["ok"] else ident["problem"])
    if quiet:
        if missing:
            print("         Missing: %s" % ", ".join(m[0] for m in missing))
        print("         %s" % line)
    else:
        print()
        print("AG CAPITAL  -  Deal flow outreach  -  is this computer ready?")
        print("-" * 60)
        v = sys.version_info
        print("  OK       Python %d.%d.%d  (%s)" % (v.major, v.minor, v.micro, sys.executable))
        for name, why in PACKAGES:
            print("  %-8s %s: %s" % ("MISSING" if (name, why) in missing else "OK", name, why))
        print("  %-8s %s" % ("OK" if ident["ok"] else "CHECK", line))
        print("-" * 60)
        if missing:
            print("Something is missing. Run the setup again: outreach setup")
        elif ident["ok"]:
            print("Ready. Emails will be sent from %s." % ident["email"])
        else:
            print("A round can be prepared, but nothing can be sent or read until classic "
                  "Outlook is installed and set up with your mailbox.")
    if missing:
        return 2
    return 0 if ident["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
