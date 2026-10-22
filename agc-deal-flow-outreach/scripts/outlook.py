"""Everything that touches the mailbox: who we are, sending, reading answers.

Classic Outlook is driven through its own automation interface, so an email
leaves exactly as if the user had written it: from their account, with their
signature, into their Sent Items. The new Outlook app has no such interface;
classic Outlook has to be installed and set up with the mailbox.

Outlook is only ever spoken to from one thread (Outlook insists on that), so
every call goes through `call`.

With AGC_OUTREACH_FAKE=1 nothing here touches Outlook. A stand-in keeps "sent"
mail and canned answers in a file, so the whole tool can be exercised without a
single real email.
"""
import datetime as dt
import html as html_mod
import os
import queue
import re
import threading
import time
import uuid

import store

FAKE = os.environ.get("AGC_OUTREACH_FAKE") == "1"

OL_MAIL_ITEM = 0
OL_FOLDER_OUTBOX, OL_FOLDER_SENT, OL_FOLDER_INBOX = 4, 5, 6
PR_SMTP_ADDRESS = "http://schemas.microsoft.com/mapi/proptag/0x39FE001E"
OL_DISCARD = 1
OL_MINIMIZED = 1

QUOTE_MARKERS = [
    r"^-{3,}\s*(original message|ursprüngliche nachricht|ursprüngliche nachricht)",
    r"^(von|from):\s.+", r"^am .+ schrieb .+:\s*$", r"^on .+ wrote:\s*$",
    r"^_{10,}\s*$", r"^>+ ?",
]
AUTO_SUBJECTS = ("automatic reply", "automatische antwort", "abwesenheit", "out of office",
                 "autoreply", "auto-reply", "abwesenheitsnotiz")
BOUNCE_SUBJECTS = ("undeliverable", "unzustellbar", "delivery status notification", "mail delivery failed",
                   "delivery has failed", "nicht zustellbar", "returned mail")


def strip_quoted(text, limit=3000):
    """The part of an answer the person wrote, without the email it quotes."""
    kept = []
    for line in (text or "").replace("\r\n", "\n").split("\n"):
        if any(re.match(p, line.strip(), re.IGNORECASE) for p in QUOTE_MARKERS):
            break
        kept.append(line.rstrip())
    return re.sub(r"\n{3,}", "\n\n", "\n".join(kept)).strip()[:limit]


def text_to_html(text):
    """Plain paragraphs in the markup Outlook itself writes, so they pick up the
    user's default font and sit naturally above the signature."""
    parts = []
    for line in text.replace("\r\n", "\n").split("\n"):
        inner = html_mod.escape(line) if line.strip() else "&nbsp;"
        parts.append("<p class=MsoNormal>%s<o:p></o:p></p>" % inner)
    return "".join(parts)


def insert_above_signature(signature_html, text):
    block = text_to_html(text) + "<p class=MsoNormal><o:p>&nbsp;</o:p></p>"
    m = re.search(r"<div class=\"?WordSection1\"?[^>]*>", signature_html, re.IGNORECASE) or \
        re.search(r"<body[^>]*>", signature_html, re.IGNORECASE)
    if not m:
        return None
    return signature_html[:m.end()] + block + signature_html[m.end():]


# ---- the one thread that talks to Outlook -----------------------------------

class _Worker(threading.Thread):
    def __init__(self):
        super().__init__(daemon=True, name="outlook")
        self.jobs = queue.Queue()
        self.app = None
        self.ns = None

    def run(self):
        import pythoncom
        pythoncom.CoInitialize()
        while True:
            fn, args, box = self.jobs.get()
            try:
                box["value"] = fn(self, *args)
            except Exception as exc:  # reported to the caller, never fatal to the thread
                box["error"] = exc
                self.app = self.ns = None   # reconnect next time; Outlook may have been closed
            box["done"].set()

    def connect(self):
        if self.app is None:
            import win32com.client
            self.app = win32com.client.Dispatch("Outlook.Application")
            self.ns = self.app.GetNamespace("MAPI")
        return self.app, self.ns


_worker = None
_lock = threading.Lock()


def call(fn, *args, timeout=180):
    global _worker
    with _lock:
        if _worker is None:
            _worker = _Worker()
            _worker.start()
    box = {"done": threading.Event()}
    _worker.jobs.put((fn, args, box))
    if not box["done"].wait(timeout):
        raise TimeoutError("Outlook did not answer. A dialog may be open in an Outlook window.")
    if "error" in box:
        raise box["error"]
    return box["value"]


def _plain(exc):
    text = str(exc)
    m = re.search(r"'([^']{12,})'", text)
    return (m.group(1) if m else text).strip()[:200]


def _code(exc):
    """Outlook's own error number, as IT would look it up, or ''."""
    for value in (getattr(exc, "excepinfo", None) or (None,) * 6)[5:6] + (getattr(exc, "hresult", None),):
        if isinstance(value, int) and value:
            return "0x%08X" % (value & 0xFFFFFFFF)
    return ""


class SendRefused(Exception):
    """Outlook would not do one of the steps of sending. Says which, and why."""

    def __init__(self, step, exc):
        self.step, self.code, self.reason = step, _code(exc), _plain(exc)
        hint = {
            # what Outlook answers when a program is not allowed to send on the user's behalf
            "0x80004004": " Outlook did not allow a program to send for you. That is a security setting of "
                          "your organisation; IT can allow it.",
            "0x80070005": " Outlook did not allow a program to send for you. That is a security setting of "
                          "your organisation; IT can allow it.",
        }.get(self.code, "")
        super().__init__("Outlook refused to %s: %s%s%s" % (step, self.reason, " (%s)" % self.code if self.code else "",
                                                            hint))


def _when(value):
    """Outlook hands back local time labelled as UTC; take the clock reading."""
    return dt.datetime(value.year, value.month, value.day, value.hour, value.minute, value.second)


# ---- real Outlook -----------------------------------------------------------

def _identity(w):
    app, ns = w.connect()
    email = name = ""
    if ns.Accounts.Count:
        acct = ns.Accounts.Item(1)
        email, name = acct.SmtpAddress or "", acct.UserName or acct.DisplayName or ""
    return {"ok": bool(email), "email": email.lower(), "name": name, "version": app.Version,
            "accounts": ns.Accounts.Count,
            "problem": "" if email else "Classic Outlook is installed but no mailbox is set up in it."}


def _in_outbox(ns, to, subject):
    box = ns.GetDefaultFolder(OL_FOLDER_OUTBOX).Items
    for i in range(1, box.Count + 1):
        try:
            item = box.Item(i)
            if item.Subject == subject and to.lower() in (item.To or "").lower():
                return True
        except Exception:
            continue
    return False


def _show_outlook(app, ns):
    """Make sure Outlook has a window. Started in the background by a program,
    Outlook has none, and in that state it often refuses to send or leaves mail
    lying in the Outbox. Opened minimised, so it does not jump in front."""
    if app.Explorers.Count:
        return False
    ns.GetDefaultFolder(OL_FOLDER_INBOX).Display()
    for _ in range(20):                       # the window takes a moment to exist
        if app.Explorers.Count:
            break
        time.sleep(0.25)
    try:
        app.ActiveExplorer().WindowState = OL_MINIMIZED
    except Exception:
        pass
    return True


def _throw_away(mail, saved):
    """Leave nothing behind from an email that did not go out. A draft that
    was saved goes to Deleted Items, where it can still be found; an unsaved
    one simply disappears."""
    try:
        if saved:
            mail.Delete()
        else:
            mail.Close(OL_DISCARD)
    except Exception:
        pass


def _attempt(app, to, subject, body, in_window, attachments=()):
    """Build one email and send it. in_window opens the email's own window
    first, the way a person composes; the quiet way does not show anything."""
    step, saved = "create the email", False
    mail = app.CreateItem(OL_MAIL_ITEM)
    try:
        step = "address the email"
        mail.To = to
        mail.Subject = subject
        for path in attachments:
            step = "attach %s" % os.path.basename(path)
            mail.Attachments.Add(path)
        step = "put the text above your signature"
        combined = None
        try:
            if in_window:
                mail.Display(False)
            else:
                _ = mail.GetInspector        # makes Outlook put the default signature in
            combined = insert_above_signature(mail.HTMLBody or "", body)
        except Exception:
            combined = None
        if combined:
            mail.HTMLBody = combined
        else:
            mail.Body = body
        step = "accept the address %s" % to
        if not mail.Recipients.ResolveAll():
            raise ValueError("Outlook does not know this address")
        step = "save the email"
        mail.Save()
        saved = True
        conversation = ""
        try:
            conversation = mail.ConversationID or ""
        except Exception:
            pass
        step = "send the email"
        mail.Send()
        return conversation
    except Exception as exc:
        _throw_away(mail, saved)
        raise SendRefused(step, exc)


def _send(w, to, subject, body, attachments=()):
    app, ns = w.connect()
    _show_outlook(app, ns)
    try:
        conversation = _attempt(app, to, subject, body, False, attachments)
    except SendRefused as first:
        if first.step != "send the email" or first.code in ("0x80004004", "0x80070005"):
            raise                 # a wrong address or a security refusal does not get better by asking twice
        # Some setups only send an email that was open in its own window.
        try:
            conversation = _attempt(app, to, subject, body, True, attachments)
        except SendRefused:
            raise first
    # Sent only counts once the email has left the Outbox. Outlook started in the
    # background sometimes holds mail there until it is told to send.
    left = False
    for attempt in range(20):
        time.sleep(1)
        if not _in_outbox(ns, to, subject):
            left = True
            break
        if attempt == 4:
            try:
                ns.SendAndReceive(False)
            except Exception:
                pass
    return {"conversation_id": conversation, "state": "sent" if left else "outbox",
            "sent_at": store.stamp()}


def _sender_address(item):
    try:
        if item.SenderEmailType == "EX":
            user = item.Sender.GetExchangeUser()
            if user is not None:
                return (user.PrimarySmtpAddress or "").lower()
        return (item.SenderEmailAddress or "").lower()
    except Exception:
        return ""


def _folders(folder, depth=2):
    yield folder
    if depth:
        try:
            for i in range(1, folder.Folders.Count + 1):
                for sub in _folders(folder.Folders.Item(i), depth - 1):
                    yield sub
        except Exception:
            return


def _scan(w, since, addresses, conversations):
    _, ns = w.connect()
    found = []
    for folder in _folders(ns.GetDefaultFolder(OL_FOLDER_INBOX)):
        items = folder.Items
        items.Sort("[ReceivedTime]", True)
        item = items.GetFirst()
        while item is not None:
            try:
                received = _when(item.ReceivedTime)
            except Exception:
                item = items.GetNext()
                continue
            if received < since:
                break
            try:
                found.extend(_match(item, received, addresses, conversations))
            except Exception:
                pass
            item = items.GetNext()
    return found


def _match(item, received, addresses, conversations):
    cls = (item.MessageClass or "")
    subject = item.Subject or ""
    try:
        conversation = item.ConversationID or ""
    except Exception:
        conversation = ""
    in_thread = bool(conversation) and conversation in conversations
    low_subject = subject.lower()
    if cls.upper().startswith("REPORT") or low_subject.startswith(BOUNCE_SUBJECTS):
        body = (item.Body or "")[:4000]
        hit = [a for a in addresses if a in body.lower()]
        if not in_thread and not hit:
            return []
        return [{"kind": "bounce", "from_email": hit[0] if hit else "", "from_name": "",
                 "received": store.stamp(received), "subject": subject, "text": body[:600].strip(),
                 "conversation_id": conversation, "matched_by": "thread" if in_thread else "address"}]
    sender = _sender_address(item)
    if not in_thread and sender not in addresses:
        return []
    auto = "ooftemplate" in cls.lower() or low_subject.startswith(AUTO_SUBJECTS)
    return [{"kind": "auto" if auto else "reply", "from_email": sender,
             "from_name": getattr(item, "SenderName", "") or "", "received": store.stamp(received),
             "subject": subject, "text": strip_quoted(item.Body or ""),
             "conversation_id": conversation, "matched_by": "thread" if in_thread else "address"}]


def _recipient_addresses(item):
    out = []
    try:
        recipients = item.Recipients
        for i in range(1, recipients.Count + 1):
            r = recipients.Item(i)
            address = ""
            try:
                address = r.PropertyAccessor.GetProperty(PR_SMTP_ADDRESS) or ""
            except Exception:
                address = r.Address or ""
            out.append(address.lower())
    except Exception:
        pass
    return out


def _restricted(items, dasl):
    """The items a DASL filter lets through, or all of them if Outlook will
    not filter (an old version, a store that is not indexed)."""
    try:
        return items.Restrict(dasl)
    except Exception:
        return items


def _history(w, address, since, limit):
    """Emails from and to one address since a date, newest first."""
    _, ns = w.connect()
    address = address.lower()
    found = []

    def read(folder, direction, date_field, dasl):
        items = _restricted(folder.Items, dasl)
        try:
            items.Sort("[%s]" % date_field, True)
        except Exception:
            pass
        item, looked = items.GetFirst(), 0
        while item is not None and looked < 4000 and len(found) < limit * 3:
            looked += 1
            try:
                when = _when(getattr(item, date_field))
            except Exception:
                item = items.GetNext()
                continue
            if when < since:
                break
            try:
                if direction == "in":
                    hit = _sender_address(item) == address
                else:
                    hit = address in (item.To or "").lower() or address in _recipient_addresses(item)
                if hit:
                    found.append({"direction": direction, "when": store.stamp(when), "subject": item.Subject or "",
                                  "text": strip_quoted(item.Body or "", 1500)})
            except Exception:
                pass
            item = items.GetNext()

    quoted = address.replace("'", "''")
    for folder in _folders(ns.GetDefaultFolder(OL_FOLDER_INBOX)):
        read(folder, "in", "ReceivedTime",
             "@SQL=\"urn:schemas:httpmail:fromemail\" LIKE '%%%s%%'" % quoted)
    read(ns.GetDefaultFolder(OL_FOLDER_SENT), "out", "SentOn",
         "@SQL=\"urn:schemas:httpmail:displayto\" LIKE '%%%s%%' OR "
         "\"http://schemas.microsoft.com/mapi/proptag/0x0E04001F\" LIKE '%%%s%%'" % (quoted, quoted))
    found.sort(key=lambda m: m["when"], reverse=True)
    return found[:limit]


# ---- the stand-in -----------------------------------------------------------

def _fake_path():
    return os.path.join(store.home(), "fake_mailbox.json")


def _fake_box():
    return store.read_json(_fake_path(), {"sent": [], "inbox": []})


def _fake_send(to, subject, body, attachments=()):
    if "bounce-now" in to:
        raise ValueError("Outlook does not accept the address %s" % to)
    for path in attachments:
        if not os.path.isfile(path):
            raise ValueError("Outlook refused to attach %s: the file is not there" % os.path.basename(path))
    box = _fake_box()
    conversation = uuid.uuid4().hex.upper()
    box["sent"].append({"to": to, "subject": subject, "body": body, "conversation_id": conversation,
                        "sent_at": store.stamp(), "attachments": [os.path.basename(p) for p in attachments]})
    store.write_json(_fake_path(), box)
    return {"conversation_id": conversation, "state": "sent", "sent_at": store.stamp()}


def _fake_scan(since, addresses, conversations):
    out = []
    for m in _fake_box()["inbox"]:
        when = store.parse_stamp(m.get("received", "")) or store.now()
        if when < since:
            continue
        in_thread = m.get("conversation_id") in conversations
        if in_thread or m.get("from_email", "").lower() in addresses:
            out.append(dict(m, text=strip_quoted(m.get("text", "")),
                            matched_by="thread" if in_thread else "address"))
    return out


def _fake_history(address, since, limit):
    box = _fake_box()
    out = []
    for m in box["sent"]:
        if m["to"].lower() == address and (store.parse_stamp(m["sent_at"]) or store.now()) >= since:
            out.append({"direction": "out", "when": m["sent_at"], "subject": m["subject"],
                        "text": strip_quoted(m["body"], 1500)})
    for m in box["inbox"] + box.get("archive", []):
        if m.get("from_email", "").lower() == address and (store.parse_stamp(m.get("received", "")) or store.now()) >= since:
            out.append({"direction": "in", "when": m["received"], "subject": m["subject"],
                        "text": strip_quoted(m.get("text", ""), 1500)})
    out.sort(key=lambda m: m["when"], reverse=True)
    return out[:limit]


# ---- what the rest of the tool calls ----------------------------------------

def identity():
    if FAKE:
        return {"ok": True, "email": "tester@agcapital.example", "name": "Test Sender", "version": "simulated",
                "accounts": 1, "problem": "", "simulated": True}
    try:
        return call(_identity, timeout=60)
    except Exception as exc:
        return {"ok": False, "email": "", "name": "", "version": "", "accounts": 0,
                "problem": "Classic Outlook could not be reached (%s). It has to be installed and "
                           "set up with your mailbox; the new Outlook app cannot be automated."
                           % _plain(exc)}


def send(to, subject, body, attachments=()):
    """Send one email, with the files at these paths attached. Returns
    {conversation_id, state, sent_at}; raises on failure."""
    attachments = list(attachments)
    if FAKE:
        return _fake_send(to, subject, body, attachments)
    try:
        return call(_send, to, subject, body, attachments)
    except SendRefused as exc:
        raise RuntimeError(str(exc))
    except Exception as exc:
        raise RuntimeError(_plain(exc))


def scan(since, addresses, conversations):
    """Answers received since `since` from these addresses or in these threads."""
    addresses = {a.lower() for a in addresses}
    if FAKE:
        return _fake_scan(since, addresses, set(conversations))
    return call(_scan, since, addresses, set(conversations), timeout=600)


def history(address, days=365, limit=15):
    """The emails exchanged with one address in the last `days`, newest first:
    [{direction: in|out, when, subject, text}]. Empty when Outlook cannot be
    read; looking back is a help for Claude, never a reason to fail."""
    address = (address or "").strip().lower()
    if not address:
        return []
    since = store.now() - dt.timedelta(days=days)
    try:
        if FAKE:
            return _fake_history(address, since, limit)
        return call(_history, address, since, limit, timeout=240)
    except Exception:
        return []
