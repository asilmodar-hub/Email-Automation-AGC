#!/usr/bin/env python3
"""One entry point for the AGC deal-flow outreach tool.

Reached through outreach.cmd, which makes sure the tool's own Python and
packages are in place before anything runs.

    outreach start [--scheduled] [--no-browser]   start the app, open the screen
    outreach wait                                 block until the screen asks Claude for something
    outreach submit <job> [file]                  hand a job's result back
    outreach fail <job> "<reason>"                say a job could not be done
    outreach status                               one-line state of the app
    outreach stop                                 close the app
    outreach doctor                               is this computer set up correctly

There is no command that sends email. Sending is the Send button on the screen.
"""
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import store  # noqa: E402

CLOSED = "CLOSED"
# The app is on this computer. A company proxy must never be asked for it.
_LOCAL = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def _info():
    return store.read_json(os.path.join(store.home(), "server.json"))


def _request(info, path, body=None, timeout=70):
    url = "http://127.0.0.1:%d%s" % (info["port"], path)
    data = None if body is None else json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={"X-AGC-Token": info["token"],
                                                          "Content-Type": "application/json"})
    try:
        with _LOCAL.open(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        try:
            return json.loads(exc.read().decode("utf-8"))
        except ValueError:
            return {"error": "The app answered with an error (%d)." % exc.code}


def _alive(info):
    if not info:
        return False
    try:
        return bool(_request(info, "/api/ping", timeout=3).get("ok"))
    except (OSError, ValueError):
        return False


def _running():
    info = _info()
    return info if _alive(info) else None


def _jobs_dir():
    path = os.path.join(store.home(), "jobs")
    os.makedirs(path, exist_ok=True)
    return path


def _notify(text):
    """A Windows notification, if the system lets us show one. Never an error."""
    if sys.platform != "win32" or os.environ.get("AGC_OUTREACH_FAKE") == "1":
        return
    text = text.replace("'", " ")
    script = (
        "[Windows.UI.Notifications.ToastNotificationManager,Windows.UI.Notifications,ContentType=WindowsRuntime]|Out-Null;"
        "$x=[Windows.UI.Notifications.ToastNotificationManager]::GetTemplateContent("
        "[Windows.UI.Notifications.ToastTemplateType]::ToastText02);$t=$x.GetElementsByTagName('text');"
        "$t.Item(0).AppendChild($x.CreateTextNode('AG Capital deal flow outreach'))|Out-Null;"
        "$t.Item(1).AppendChild($x.CreateTextNode('%s'))|Out-Null;"
        "[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier("
        r"'{1AC14E77-02E7-4E5D-B744-2EB1AE5198B7}\WindowsPowerShell\v1.0\powershell.exe')"
        ".Show([Windows.UI.Notifications.ToastNotification]::new($x))" % text)
    try:
        subprocess.Popen(["powershell", "-NoProfile", "-Command", script], stdin=subprocess.DEVNULL,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except OSError:
        pass


def cmd_start(args):
    info = _running()
    if info and _request(info, "/api/ping", timeout=3).get("version") != store.VERSION:
        cmd_stop([])            # an app left running from an older copy of the skill
        time.sleep(1)
        info = None
    fresh = info is None
    if fresh:
        log = open(os.path.join(store.home(), "app-log.txt"), "a", encoding="utf-8")
        flags = 0
        if sys.platform == "win32":
            flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW
        subprocess.Popen([sys.executable, os.path.join(HERE, "server.py")], cwd=HERE, stdin=subprocess.DEVNULL,
                         stdout=log, stderr=log, creationflags=flags, close_fds=True)
        for _ in range(60):
            time.sleep(0.25)
            info = _running()
            if info:
                break
        if not info:
            print("The app did not start. Details are in %s" % os.path.join(store.home(), "app-log.txt"))
            return 2
    url = info["url"]
    if "--scheduled" in args:
        result = _request(info, "/api/scheduled", {}, timeout=120)
        if result.get("started"):
            if result.get("sending"):
                held = " %d were held back because a check failed and wait on the Review tab." % result["held"]
                print("Scheduled round opened: %d emails are being SENT WITHOUT REVIEW by the app, because the "
                      "user switched that on.%s" % (result["sending"], held if result.get("held") else ""))
                _notify("%d emails are being sent without review." % result["sending"])
            else:
                print("Scheduled round opened: %d emails are ready for review." % result["count"])
                _notify("%d emails are ready for your review." % result["count"])
        else:
            print("No round was opened: %s" % result.get("reason", result.get("error", "")))
        url += "#review"
    if "--no-browser" not in args:
        try:
            os.startfile(url)  # the user's default browser
        except (OSError, AttributeError):
            import webbrowser
            webbrowser.open(url)
    state = _request(info, "/api/state")
    ident = state.get("identity", {})
    print("The screen is %s: %s" % ("open" if fresh else "already running, reopened", info["url"]))
    if ident.get("ok"):
        print("Sending as: %s" % ident["email"])
    elif not ident.get("checking"):
        print("Outlook is not ready: %s" % ident.get("problem", ""))
    if state.get("app", {}).get("simulated"):
        print("SIMULATED MODE: no real email is sent or read.")
    print("Next: run 'outreach wait' in the background and act on each job it returns.")
    return 0


def _describe(job, path):
    p = job["payload"]
    print("JOB %s  type=%s" % (job["id"], job["type"]))
    print("Details: %s" % path)
    result = os.path.join(_jobs_dir(), "%s.result.json" % job["id"])
    if job["type"] == "rewrite":
        print("The reviewer asked for a change to the email for %s %s:"
              % (p["contact"].get("first", ""), p["contact"].get("last", "")))
        print("  \"%s\"" % p["note_from_user"])
        print("Read references/01-rewriting.md, then the details file.")
        print('Result file: %s   shape: {"drafts": [{"contact_id", "body"}]}' % result)
        print("Then: outreach submit %s" % job["id"])
    elif job["type"] == "classify":
        print("Read %d answer%s and classify each." % (len(p["answers"]), "" if len(p["answers"]) == 1 else "s"))
        print("Read references/02-replies.md, then the details file.")
        print('Result file: %s   shape: {"answers": [{"round_id", "contact_id", "outcome", "summary", '
              '"quote", "next_step"}]}' % result)
        print("Then: outreach submit %s" % job["id"])
    elif job["type"] == "schedule":
        print("The user changed the automatic rhythm to: %s." % p["label"])
        print("Read references/04-schedule.md and set the Claude scheduler task '%s' accordingly "
              "(action=%s cron=%r fire_at=%r)." % (p["task_id"], p["action"], p["cron"], p["fire_at"]))
        print('Result file: %s   shape: {"ok": true} or {"ok": false, "error": "..."}' % result)
        print("Then: outreach submit %s" % job["id"])
    print("Afterwards run 'outreach wait' again.")


def cmd_wait(args):
    info = _running()
    if not info:
        print("%s  The app is not running. Start it with: outreach start" % CLOSED)
        return 0
    misses = 0
    while True:
        try:
            answer = _request(info, "/api/jobs/next?wait=25")
            misses = 0
        except (OSError, ValueError):
            misses += 1
            if misses >= 3 or not _alive(_info()):
                print("%s  The app has closed. Nothing more to do until the skill is called again." % CLOSED)
                return 0
            time.sleep(2)
            continue
        if answer.get("error"):
            print("%s  %s" % (CLOSED, answer["error"]))
            return 0
        job = answer.get("job")
        if job:
            path = os.path.join(_jobs_dir(), "%s.json" % job["id"])
            store.write_json(path, job)
            _describe(job, path)
            return 0


def cmd_submit(args):
    if not args:
        print("Which job? outreach submit <job> [file]")
        return 1
    info = _running()
    if not info:
        print("The app is not running, so the result cannot be handed back. Start it with: outreach start")
        return 2
    path = args[1] if len(args) > 1 else os.path.join(_jobs_dir(), "%s.result.json" % args[0])
    try:
        with open(path, "r", encoding="utf-8-sig") as fh:
            result = json.load(fh)
    except OSError:
        print("There is no result file at %s" % path)
        return 1
    except ValueError as exc:
        print("The result file is not valid JSON: %s" % exc)
        return 1
    answer = _request(info, "/api/jobs/%s/result" % args[0], result)
    print(json.dumps(answer, ensure_ascii=False, indent=1))
    return 0 if answer.get("ok") else 1


def cmd_fail(args):
    info = _running()
    if not info or not args:
        print("Nothing to report to.")
        return 1
    print(json.dumps(_request(info, "/api/jobs/%s/fail" % args[0], {"reason": " ".join(args[1:])})))
    return 0


def cmd_status(args):
    info = _running()
    if not info:
        print("The app is not running.")
        return 0
    s = _request(info, "/api/state")
    rnd = s.get("round")
    print("Running at %s" % info["url"])
    print("Sending as: %s" % (s["identity"].get("email") or s["identity"].get("problem")))
    print("Contact list: %s" % (s["workbook"]["path"] or "not chosen yet"))
    if rnd:
        counts = {}
        for d in rnd["drafts"]:
            counts[d["status"]] = counts.get(d["status"], 0) + 1
        print("Open round %s: %s" % (rnd["label"], ", ".join("%d %s" % (n, k) for k, n in sorted(counts.items()))))
    else:
        print("No round is open.")
    print("Jobs waiting for Claude: %d" % len([j for j in s["jobs"] if j["status"] != "failed"]))
    return 0


def cmd_stop(args):
    info = _running()
    if info:
        try:
            _request(info, "/api/quit", {})
        except (OSError, ValueError):
            pass
    print("The app is closed.")
    return 0


def cmd_doctor(args):
    import preflight
    return preflight.main()


COMMANDS = {"start": cmd_start, "wait": cmd_wait, "submit": cmd_submit, "fail": cmd_fail,
            "status": cmd_status, "stop": cmd_stop, "doctor": cmd_doctor}


def main():
    # Names and answers contain characters a Windows console cannot always show.
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    args = sys.argv[1:]
    if not args or args[0] in ("help", "-h", "--help"):
        print(__doc__)
        return 0
    if args[0] not in COMMANDS:
        print("There is no command called %r. Run 'outreach help' for the list." % args[0])
        return 1
    try:
        return COMMANDS[args[0]](args[1:])
    except Exception as exc:
        print("The '%s' command could not finish (%s: %s)."
              % (args[0], type(exc).__name__, str(exc).splitlines()[0][:160] if str(exc) else ""))
        return 3


if __name__ == "__main__":
    sys.exit(main())
