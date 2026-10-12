#!/usr/bin/env python3
"""Pack the skill folder into agc-deal-flow-outreach.skill, the file that is
uploaded to Claude.

    python dev/package.py
"""
import os
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NAME = "agc-deal-flow-outreach"


def main():
    out = os.path.join(ROOT, NAME + ".skill")
    count = 0
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for folder, dirs, files in os.walk(os.path.join(ROOT, NAME)):
            dirs[:] = sorted(d for d in dirs if d != "__pycache__")
            for name in sorted(files):
                if name.endswith((".pyc", ".tmp")) or name.startswith("~$"):
                    continue
                full = os.path.join(folder, name)
                z.write(full, os.path.relpath(full, ROOT).replace(os.sep, "/"))
                count += 1
    print("wrote %s (%d files, %d KB)" % (out, count, os.path.getsize(out) // 1024))


if __name__ == "__main__":
    main()
