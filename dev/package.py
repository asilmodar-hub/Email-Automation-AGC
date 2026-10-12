#!/usr/bin/env python3
"""Pack the skill folder into agc-deal-flow-outreach.skill, the file that is
uploaded to Claude.

    python dev/package.py

Two things never go into the package, even if they are in the skill folder:

  - a "Deal Flow Outreach data" folder. The tool creates one next to whatever
    contact list it is pointed at; pointed at the template inside the skill
    folder, it creates one there.
  - the contact template as it lies on disk. It is easy to try the tool with
    it and leave a real name and address in it, so the package always gets a
    freshly built, empty one.
"""
import os
import sys
import tempfile
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NAME = "agc-deal-flow-outreach"
DATA_FOLDER = "Deal Flow Outreach data"
TEMPLATE = "Contacts_Template.xlsx"

sys.path.insert(0, os.path.join(ROOT, "dev"))
import make_fixtures  # noqa: E402


def main():
    out = os.path.join(ROOT, NAME + ".skill")
    clean_template = make_fixtures.template(os.path.join(tempfile.mkdtemp(prefix="agc-package-"), TEMPLATE))
    count = 0
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for folder, dirs, files in os.walk(os.path.join(ROOT, NAME)):
            dirs[:] = sorted(d for d in dirs if d not in ("__pycache__", DATA_FOLDER))
            for name in sorted(files):
                if name.endswith((".pyc", ".tmp")) or name.startswith("~$"):
                    continue
                full = os.path.join(folder, name)
                z.write(clean_template if name == TEMPLATE else full, os.path.relpath(full, ROOT).replace(os.sep, "/"))
                count += 1
    os.remove(clean_template)
    os.rmdir(os.path.dirname(clean_template))
    print("wrote %s (%d files, %d KB)" % (out, count, os.path.getsize(out) // 1024))


if __name__ == "__main__":
    main()
