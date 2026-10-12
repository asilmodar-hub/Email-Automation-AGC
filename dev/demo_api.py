#!/usr/bin/env python3
"""Talk to the running demo from the command line, for checking things by hand.

    python dev/demo_api.py state                 a short summary of where the demo stands
    python dev/demo_api.py post <path> '<json>'  e.g. post /api/reload '{}'
"""
import json
import os
import sys
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INFO = os.path.join(ROOT, "dev", "tmp", "home", "server.json")
LOCAL = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def call(path, body=None):
    info = json.load(open(INFO, encoding="utf-8"))
    data = None if body is None else json.dumps(body).encode("utf-8")
    req = urllib.request.Request("http://127.0.0.1:%d%s" % (info["port"], path), data=data,
                                 headers={"X-AGC-Token": info["token"]})
    try:
        return json.load(LOCAL.open(req, timeout=30))
    except urllib.error.HTTPError as exc:
        return json.load(exc)


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if sys.argv[1:2] == ["post"]:
        print(json.dumps(call(sys.argv[2], json.loads(sys.argv[3] if len(sys.argv) > 3 else "{}")), ensure_ascii=False))
        return
    s = call("/api/state")
    rnd = s["round"]
    print("claude connected:", s["app"]["claude"], "| jobs:", [(j["type"], j["status"]) for j in s["jobs"]])
    if not rnd:
        print("no round open")
        return
    print("round", rnd["id"], rnd["label"])
    for d in rnd["drafts"]:
        if d["changed_by"] or d["status"] not in ("pending",) or d["level"] != "ok":
            print("  %-48s %-9s changed_by=%-6s level=%-4s note=%r"
                  % (d["contact_id"], d["status"], d["changed_by"] or "-", d["level"], d.get("note", "")))


if __name__ == "__main__":
    main()
