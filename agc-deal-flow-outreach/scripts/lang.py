"""German for the sentences the app itself produces.

The screen has its own dictionary for its labels (assets/ui/de.js). This one is
for what comes from the app: why a contact is left out, what a check found,
why something could not be done.

Everything is produced and stored in English and put into German only on the
way to the screen, so switching the language changes every sentence at once,
old rounds included, and the files next to the contact list read the same
whoever wrote them. A sentence missing here simply stays English.
"""
import re

LANGUAGES = ("en", "de")

EXACT = {
    # Outlook
    "Checking Outlook…": "Outlook wird geprüft…",
    "Classic Outlook is installed but no mailbox is set up in it.":
        "Das klassische Outlook ist installiert, aber es ist kein Postfach eingerichtet.",
    # the contact list
    "The contact list was not found at this path.": "Unter diesem Pfad wurde keine Kontaktliste gefunden.",
    "The contact list could not be opened. Windows refused access to it.":
        "Die Kontaktliste konnte nicht geöffnet werden. Windows hat den Zugriff verweigert.",
    "No sheet has a recognisable header row with an Email column. Start from the contact template, or name "
    "the columns as it does.":
        "Kein Tabellenblatt hat eine erkennbare Kopfzeile mit einer E-Mail-Spalte. Am besten mit der "
        "Kontaktvorlage beginnen oder die Spalten so benennen wie dort.",
    "no email address": "keine E-Mail-Adresse",
    "email address looks wrong": "E-Mail-Adresse sieht falsch aus",
    "no name": "kein Name",
    "language not given, German assumed": "Sprache nicht angegeben, Deutsch angenommen",
    "language not given, English assumed from the country": "Sprache nicht angegeben, nach dem Land Englisch angenommen",
    "first name taken from the email address": "Vorname aus der E-Mail-Adresse übernommen",
    "Sie/du not given, Sie assumed": "Sie/du nicht angegeben, Sie angenommen",
    # who is in the round
    "due": "fällig",
    "never written to": "noch nie angeschrieben",
    "marked do not contact in the list": "in der Liste als „nicht kontaktieren“ markiert",
    "asked not to be contacted": "möchte nicht mehr angeschrieben werden",
    "cadence set to never": "Rhythmus steht auf „nie“",
    "nobody is responsible for this contact in the list": "laut Liste ist niemand für diesen Kontakt zuständig",
    "outside your region filter": "außerhalb Ihres Regionen-Filters",
    "outside your priority filter": "außerhalb Ihres Prioritäten-Filters",
    "outside your relevance filter": "außerhalb Ihres Relevanz-Filters",
    "outside your type filter": "außerhalb Ihres Filters nach Art",
    "Claude will look up the missing details": "Claude sucht die fehlenden Angaben heraus",
    "added by hand": "von Hand hinzugefügt",
    "left out by hand": "von Hand ausgenommen",
    "no German (Sie) master email yet": "noch keine Standard-E-Mail auf Deutsch (Sie)",
    "no German (du) master email yet": "noch keine Standard-E-Mail auf Deutsch (du)",
    "no English master email yet": "noch keine Standard-E-Mail auf Englisch",
    # the master emails
    "empty: contacts who need this version are held back":
        "leer: Kontakte, die diese Fassung brauchen, werden zurückgehalten",
    "no subject line": "kein Betreff",
    "a [[note to fill in]] is still in the text": "im Text steht noch ein [[Hinweis zum Ausfüllen]]",
    "uses du, but this is the Sie version": "verwendet du, obwohl dies die Sie-Fassung ist",
    "uses Sie, but this is the du version": "verwendet Sie, obwohl dies die du-Fassung ist",
    # checks on an email
    "No subject line.": "Kein Betreff.",
    "The email is empty.": "Die E-Mail ist leer.",
    "Uses du, but the list says Sie.": "Verwendet du, laut Liste gilt aber Sie.",
    "Uses Sie, but the list says du.": "Verwendet Sie, laut Liste gilt aber du.",
    "A long dash in the changed lines; people rarely type one.":
        "Ein langer Gedankenstrich in den geänderten Zeilen; den tippt kaum jemand.",
    "No contact person in the list, so the greeting is a neutral one.":
        "Die Liste nennt keine Ansprechperson, daher ist die Anrede neutral.",
    "Claude found these details online. Check them and press “Use these details” before this email can be approved.":
        "Claude hat diese Angaben online gefunden. Bitte prüfen und „Diese Angaben verwenden“ klicken, bevor die "
        "E-Mail freigegeben werden kann.",
    "Claude found no reliable address online. Add one by hand or skip this person.":
        "Claude hat online keine verlässliche Adresse gefunden. Bitte eine von Hand eintragen oder diese Person auslassen.",
    "There is no email address for this person yet.": "Für diese Person gibt es noch keine E-Mail-Adresse.",
    "The email address looks wrong.": "Die E-Mail-Adresse sieht falsch aus.",
    "The text mentions an attachment, but nothing is attached.":
        "Der Text erwähnt einen Anhang, es ist aber nichts angehängt.",
    "Herr/frau not given in the list, so the greeting is a neutral one.":
        "Herr/Frau fehlt in der Liste, daher ist die Anrede neutral.",
    "Mr/ms not given in the list, so the greeting is a neutral one.":
        "Herr/Frau fehlt in der Liste, daher ist die Anrede neutral.",
    "No first name in the list, so the greeting is a neutral one.":
        "Der Vorname fehlt in der Liste, daher ist die Anrede neutral.",
    "The app stopped while this email was being sent. Look in Sent Items before sending it again.":
        "Das Programm wurde beendet, während diese E-Mail gesendet wurde. Vor einem erneuten Senden bitte in "
        "„Gesendete Elemente“ nachsehen.",
    # the rhythm
    "Only when I start it": "Nur wenn ich es starte",
    "Every quarter": "Jedes Quartal",
    "Every half-year": "Jedes Halbjahr",
    "Every year": "Jedes Jahr",
    "Once, on a date I pick": "Einmalig, an einem Datum meiner Wahl",
    "Pick a date and time for the first run.": "Bitte Datum und Uhrzeit für den ersten Lauf wählen.",
    "The date picked is in the past.": "Das gewählte Datum liegt in der Vergangenheit.",
    "A round was already open, so no new one was started.":
        "Es war bereits eine Runde offen, daher wurde keine neue gestartet.",
    "Scheduled round: nothing was sent without review, because every email failed a check. They are on the "
    "Review tab.":
        "Geplante Runde: Ohne Prüfung wurde nichts gesendet, weil jede E-Mail bei einer Kontrolle "
        "durchgefallen ist. Die E-Mails liegen im Reiter „Prüfen“.",
    # answers
    "Reading the inbox…": "Posteingang wird gelesen…",
    "The email could not be delivered.": "Die E-Mail konnte nicht zugestellt werden.",
    "Check the address in the contact list.": "Adresse in der Kontaktliste prüfen.",
    "Automatic reply.": "Automatische Antwort.",
    # things that could not be done
    "That round no longer exists.": "Diese Runde gibt es nicht mehr.",
    "A round is already open. Finish or close it first.":
        "Es ist bereits eine Runde offen. Bitte diese zuerst abschließen oder schließen.",
    "Nobody is due for this round.": "Für diese Runde ist niemand fällig.",
    "That draft no longer exists.": "Diese E-Mail gibt es nicht mehr.",
    "This email has already been sent.": "Diese E-Mail wurde bereits gesendet.",
    "Claude is changing this email. It is back in a moment.":
        "Claude ändert diese E-Mail gerade. Sie ist gleich wieder da.",
    "This email cannot be changed right now.": "Diese E-Mail kann im Moment nicht geändert werden.",
    "Say what should be different, so Claude knows what to change.":
        "Bitte angeben, was anders sein soll, damit Claude weiß, was zu ändern ist.",
    "Emails are being sent. Stop the sending first.": "Es werden gerade E-Mails gesendet. Bitte zuerst das Senden stoppen.",
    "Emails are already being sent.": "Es werden bereits E-Mails gesendet.",
    "Nothing to send: no approved email is among the ones chosen.":
        "Nichts zu senden: Unter den gewählten E-Mails ist keine freigegebene.",
    "Sending was not confirmed.": "Das Senden wurde nicht bestätigt.",
    "Stopped after three failures in a row. Outlook may be closed or offline.":
        "Nach drei Fehlern in Folge gestoppt. Outlook ist möglicherweise geschlossen oder offline.",
    "Nothing has been sent yet, so there are no answers to look for.":
        "Es wurde noch nichts gesendet, daher gibt es keine Antworten zu suchen.",
    "That contact is not in this round.": "Dieser Kontakt ist nicht in dieser Runde.",
    "No file dialog in simulated mode. Paste the path instead.":
        "Im Simulationsmodus gibt es keinen Dateidialog. Bitte den Pfad einfügen.",
    "The file dialog could not be opened. Paste the path instead.":
        "Der Dateidialog konnte nicht geöffnet werden. Bitte den Pfad einfügen.",
    "This link has expired. Start the tool again from Claude.":
        "Dieser Link ist abgelaufen. Bitte das Werkzeug in Claude erneut starten.",
    "Claude is still preparing this email. It is ready in a moment.":
        "Claude bereitet diese E-Mail noch vor. Sie ist gleich fertig.",
    "This is not an email address.": "Das ist keine E-Mail-Adresse.",
    "Settle the address first: use what Claude found, enter one, or skip this person.":
        "Bitte zuerst die Adresse klären: das Gefundene verwenden, eine eintragen oder diese Person auslassen.",
    "This address asked not to be contacted.": "Diese Adresse möchte nicht mehr angeschrieben werden.",
    "There is nothing found online to use for this email.": "Für diese E-Mail wurde online nichts gefunden, das sich verwenden ließe.",
    "Another email of this round already goes to this address.":
        "Eine andere E-Mail dieser Runde geht bereits an diese Adresse.",
    "Everyone written to has answered; there is nothing more to look for.":
        "Alle Angeschriebenen haben geantwortet; es gibt nichts mehr zu suchen.",
    "Only the German versions are kept in step.": "Nur die deutschen Fassungen werden abgeglichen.",
    "The file could not be read.": "Die Datei konnte nicht gelesen werden.",
    "Sending without review needs an automatic rhythm.":
        "Senden ohne Prüfung setzt einen automatischen Rhythmus voraus.",
}

_NAMES = {"German": "Deutsch", "English": "Englisch"}


def _n(count, one, many):
    return (one if int(count) == 1 else many) % int(count)


_STEPS = {
    "create the email": "die E-Mail anzulegen",
    "address the email": "die E-Mail zu adressieren",
    "put the text above your signature": "den Text über Ihre Signatur zu setzen",
    "save the email": "die E-Mail zu speichern",
    "send the email": "die E-Mail zu senden",
}


def _step(text):
    if text.startswith("attach "):
        return "%s anzuhängen" % text[len("attach "):]
    if text.startswith("accept the address "):
        return "die Adresse %s anzunehmen" % text[len("accept the address "):]
    return _STEPS.get(text, text)


def _sent(m, where):
    text = _n(m.group(1), "%d E-Mail", "%d E-Mails") + " " + where + " gesendet."
    if m.group("failed"):
        text += " " + _n(m.group("failed"), "%d konnte", "%d konnten") + " nicht gesendet werden."
    return text


# (pattern, what to say); the second is a function of the match
PATTERNS = [(re.compile(p, re.DOTALL), f) for p, f in [
    (r"^Outlook is not ready: (.*)$", lambda m: "Outlook ist nicht bereit: " + localize(m.group(1), "de")),
    (r"^Classic Outlook could not be reached \((.*)\)\. It has to be installed and set up with your mailbox; "
     r"the new Outlook app cannot be automated\.$",
     lambda m: "Das klassische Outlook ist nicht erreichbar (%s). Es muss installiert und mit Ihrem Postfach "
               "eingerichtet sein; das neue Outlook lässt sich nicht automatisieren." % m.group(1)),
    (r"^This file could not be read as an Excel workbook \((.*)\)\.$",
     lambda m: "Diese Datei konnte nicht als Excel-Arbeitsmappe gelesen werden (%s)." % m.group(1)),
    (r"^same email as row (\d+)$", lambda m: "gleiche E-Mail-Adresse wie in Zeile %s" % m.group(1)),
    (r"^same email as row (\d+) of (.*)$",
     lambda m: "gleiche E-Mail-Adresse wie in Zeile %s von %s" % (m.group(1), m.group(2))),
    (r"^(no email address|email address looks wrong|no name): tick to have Claude look it up$",
     lambda m: "%s: anhaken, damit Claude es heraussucht" % localize(m.group(1), "de")),
    (r"^first contacted (\d+) days ago according to the list$",
     lambda m: _n(m.group(1), "laut Liste vor %d Tag erstmals angeschrieben", "laut Liste vor %d Tagen erstmals angeschrieben")),
    (r"^The greeting does not name (.*)\.$", lambda m: "Die Anrede nennt %s nicht." % m.group(1)),
    (r"^The attachment (.*) is no longer on this computer\.$",
     lambda m: "Der Anhang %s ist nicht mehr auf diesem Computer." % m.group(1)),
    (r"^The file (.*) is empty\.$", lambda m: "Die Datei %s ist leer." % m.group(1)),
    (r"^The file (.*) is larger than 20 MB, too large to send by email\.$",
     lambda m: "Die Datei %s ist größer als 20 MB und damit zu groß für eine E-Mail." % m.group(1)),
    (r"^Scheduled round: (\d+) emails are being adjusted to the list by Claude\. They are sent without review as "
     r"soon as that is done, as set on the Setup tab\.$",
     lambda m: "Geplante Runde: " + _n(m.group(1), "%d E-Mail wird", "%d E-Mails werden") +
               " von Claude an die Liste angepasst. Danach gehen sie ohne Prüfung hinaus, wie in der Einrichtung "
               "festgelegt."),
    (r"^belongs to (.*)$", lambda m: "gehört zu %s" % m.group(1)),
    (r"^written to (\d+) days ago$", lambda m: _n(m.group(1), "vor %d Tag angeschrieben", "vor %d Tagen angeschrieben")),
    (r"^over the batch size of (\d+), next round$",
     lambda m: "über der Höchstzahl von %s, nächste Runde" % m.group(1)),
    (r"^a placeholder is in the text: (.*)$", lambda m: "im Text steht ein Platzhalter: %s" % m.group(1)),
    (r"^A placeholder was left in the text: (.*)$", lambda m: "Im Text ist ein Platzhalter stehen geblieben: %s" % m.group(1)),
    (r"^The greeting does not name (.*)\. Expected: (.*)$",
     lambda m: "Die Anrede nennt %s nicht. Erwartet: %s" % (m.group(1), m.group(2))),
    (r"^The greeting was changed\. The list gives: (.*)$",
     lambda m: "Die Anrede wurde geändert. Laut Liste: %s" % m.group(1)),
    (r"^Mentions \"(.*)\", which belongs to another contact \((.*)\)\.$",
     lambda m: "Erwähnt „%s“, das zu einem anderen Kontakt gehört (%s)." % (m.group(1), m.group(2))),
    (r"^The changed lines read as (German|English), but the list says (German|English)\.$",
     lambda m: "Die geänderten Zeilen lesen sich wie %s, laut Liste gilt aber %s."
               % (_NAMES[m.group(1)], _NAMES[m.group(2)])),
    (r"^Mentions \"(.*)\", which is neither in this contact's row nor in your note\.$",
     lambda m: "Erwähnt „%s“, das weder in der Zeile dieses Kontakts noch in Ihrem Hinweis steht." % m.group(1)),
    (r"^Reads as generated: (.*)\.$", lambda m: "Liest sich wie generiert: %s." % m.group(1)),
    (r"^Follow-up to (.*)$", lambda m: "Nachfass-Runde zu %s" % m.group(1)),
    (r"^Claude could not change the email for (.*?): (.*)$",
     lambda m: "Claude konnte die E-Mail an %s nicht ändern: %s" % (m.group(1), m.group(2))),
    (r"^Scheduled run: (.*)$", lambda m: "Geplanter Lauf: " + localize(m.group(1), "de")),
    (r"^Scheduled round: (\d+) emails are ready for your review\.$",
     lambda m: "Geplante Runde: " + _n(m.group(1), "%d E-Mail liegt", "%d E-Mails liegen") + " zur Prüfung bereit."),
    (r"^Scheduled round: (\d+) emails are being sent without review, as set on the Setup tab\."
     r"(?: (?P<held>\d+) were held back because a check failed\.)?$",
     lambda m: "Geplante Runde: " + _n(m.group(1), "%d E-Mail wird", "%d E-Mails werden") +
               " ohne Prüfung gesendet, wie in der Einrichtung festgelegt." +
               (" " + _n(m.group("held"), "%d wurde", "%d wurden") + " zurückgehalten, weil eine Kontrolle "
                "fehlgeschlagen ist." if m.group("held") else "")),
    (r"^Stopped\. (\d+) of (\d+) were sent\.$",
     lambda m: "Gestoppt. %s von %s wurden gesendet." % (m.group(1), m.group(2))),
    (r"^(\d+) emails? sent to your own address\.(?: (?P<failed>\d+) could not be sent\.)?$",
     lambda m: _sent(m, "an Ihre eigene Adresse")),
    (r"^(\d+) emails? sent from (\S+)\.(?: (?P<failed>\d+) could not be sent\.)?$",
     lambda m: _sent(m, "von %s" % m.group(2))),
    (r"^(\d+) new answers? found\.$",
     lambda m: _n(m.group(1), "%d neue Antwort gefunden.", "%d neue Antworten gefunden.")),
    (r"^The inbox could not be read: (.*)$", lambda m: "Der Posteingang konnte nicht gelesen werden: %s" % m.group(1)),
    (r"^The request is missing (.*)\.$", lambda m: "In der Anfrage fehlt %s." % m.group(1)),
    (r"^Outlook refused to (?P<step>.*?): (?P<why>.*?)(?P<it> Outlook did not allow a program to send for you\. "
     r"That is a security setting of your organisation; IT can allow it\.)?$",
     lambda m: "Outlook hat sich geweigert, %s: %s%s" % (
         _step(m.group("step")), m.group("why"),
         " Outlook hat einem Programm nicht erlaubt, in Ihrem Namen zu senden. Das ist eine "
         "Sicherheitseinstellung Ihrer Organisation; die IT kann es freigeben." if m.group("it") else "")),
]]


def localize(text, lang):
    """The sentence in the screen's language, or as it is if we have no German for it."""
    if lang != "de" or not text or not isinstance(text, str):
        return text
    hit = EXACT.get(text)
    if hit is not None:
        return hit
    for pattern, say in PATTERNS:
        m = pattern.match(text)
        if m:
            return say(m)
    return text
