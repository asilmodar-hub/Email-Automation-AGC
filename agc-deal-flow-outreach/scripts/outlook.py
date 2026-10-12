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
OL_FOLDER_OUTBOX, OL_FOLDER_INBOX = 4, 6
OL_DISCARD = 1

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


def _send(w, to, subject, body):
    app, ns = w.connect()
    mail = app.CreateItem(OL_MAIL_ITEM)
    try:
        mail.To = to
        mail.Subject = subject
        combined = None
        try:
            _ = mail.GetInspector            # makes Outlook put the default signature in
            combined = insert_above_signature(mail.HTMLBody or "", body)
        except Exception:
            combined = None
        if combined:
            mail.HTMLBody = combined
        else:
            mail.Body = body
        if not mail.Recipients.ResolveAll():
            raise ValueError("Outlook does not accept the address %s" % to)
        mail.Save()
        conversation = ""
        try:
            conversation = mail.ConversationID or ""
        except Exception:
            pass
        mail.Send()
    except Exception:
        try:
            mail.Close(OL_DISCARD)
        except Exception:
            pass
        raise
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


# ---- the stand-in -----------------------------------------------------------

def _fake_path():
    return os.path.join(store.home(), "fake_mailbox.json")


def _fake_box():
    return store.read_json(_fake_path(), {"sent": [], "inbox": []})


def _fake_send(to, subject, body):
    if "bounce-now" in to:
        raise ValueError("Outlook does not accept the address %s" % to)
    box = _fake_box()
    conversation = uuid.uuid4().hex.upper()
    box["sent"].append({"to": to, "subject": subject, "body": body, "conversation_id": conversation,
                        "sent_at": store.stamp()})
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


def send(to, subject, body):
    """Send one email. Returns {conversation_id, state, sent_at}; raises on failure."""
    if FAKE:
        return _fake_send(to, subject, body)
    try:
        return call(_send, to, subject, body)
    except Exception as exc:
        raise RuntimeError(_plain(exc))


def scan(since, addresses, conversations):
    """Answers received since `since` from these addresses or in these threads."""
    addresses = {a.lower() for a in addresses}
    if FAKE:
        return _fake_scan(since, addresses, set(conversations))
    return call(_scan, since, addresses, set(conversations), timeout=600)
