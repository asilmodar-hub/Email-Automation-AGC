/* The screen of the AGC deal-flow outreach tool.

   It asks the local app for its state every second and a half and draws it.
   Every decision is made here and posted back; nothing is decided by the page
   on its own. Text from the contact list and from answers is always escaped:
   a reply is written by someone outside the firm.

   Every sentence the screen shows goes through t(), tf() or tn(), which look
   it up in the German dictionary (de.js) when the screen is set to German.
   The English sentence is the key, and what is not in the dictionary stays
   English. */
(function () {
  "use strict";

  var params = new URLSearchParams(location.search);
  var TOKEN = params.get("t") || sessionStorage.getItem("agc-token") || "";
  sessionStorage.setItem("agc-token", TOKEN);
  if (params.get("t")) history.replaceState(null, "", location.pathname + location.hash);

  var S = null;                       // the app's state
  var LANG = "en";
  var ui = {
    tab: location.hash.replace("#", "") || "",
    sel: null, filter: "all", editing: null, buf: null, asking: null, note: "",
    tpl: "de_sie", followup: false, contactFilter: "in", type: "", round: null, outcome: "",
    confirm: null, lastHtml: {}, wasSending: false, gone: false,
    q: "", showAll: false, filtersOpen: false, attachTo: null, editTo: null
  };
  var TABS = [["setup", "Setup"], ["contacts", "Contacts"], ["review", "Review"], ["tracker", "Tracker"]];
  var TPL_NAMES = { de_sie: "German, Sie", de_du: "German, du", en: "English" };
  var TPL_GREETING = { de_sie: "Sehr geehrter Herr Dr. Mustermann,", de_du: "Lieber Max,", en: "Dear Mr Smith," };
  var COUNTERPART = { de_sie: "de_du", de_du: "de_sie" };
  var COUNTRY_NAMES = {
    AT: "Austria", DE: "Germany", CH: "Switzerland", LI: "Liechtenstein", LU: "Luxembourg", GB: "United Kingdom",
    US: "United States", CZ: "Czech Republic", PL: "Poland", IT: "Italy", RO: "Romania", HU: "Hungary", SK: "Slovakia",
    SI: "Slovenia", HR: "Croatia", NL: "Netherlands", FR: "France", ES: "Spain", SE: "Sweden", DK: "Denmark",
    BE: "Belgium", multi: "Several countries", none: "Not known"
  };
  var RELEVANCE_NAMES = { high: "High", medium: "Medium", low: "Low", none: "Not set" };
  var ROWS_SHOWN = 200;
  var OUTCOME_NAMES = {
    lead: "Deal lead", referral: "Referral", later: "Not now", decline: "Decline",
    out_of_office: "Out of office", bounce: "Bounced", do_not_contact: "Do not contact", no_reply: "No reply yet"
  };
  var OUTCOME_ORDER = ["lead", "referral", "later", "decline", "out_of_office", "bounce", "do_not_contact", "no_reply"];

  // A colour belongs to a kind of contact, not to its rank in the chart, so a
  // filter never repaints the others. The order is the one in which
  // neighbouring colours stay apart for colour-blind readers.
  var TYPE_ORDER = ["Law firm", "Tax / audit", "M&A adviser", "Consultant", "Bank", "Private equity", "Venture capital"];
  var TYPE_COLORS = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#4a3aa7"];
  var EXTRA_COLOR = "#e34948", OTHER_COLOR = "#9aa5b5", OTHER = "Other";

  // ---- language --------------------------------------------------------------

  function t(s) {
    var d = LANG === "de" ? window.AGC_DE : null;
    return d && Object.prototype.hasOwnProperty.call(d, s) ? d[s] : s;
  }
  // tf("{0} of {1}", a, b): a sentence with values in it
  function tf(s) {
    var out = t(s), args = arguments;
    return out.replace(/\{(\d)\}/g, function (m, i) { return args[Number(i) + 1] === undefined ? m : args[Number(i) + 1]; });
  }
  // tn(n, "{0} email", "{0} emails"): the right form for the number, {0} is the number
  function tn(n, one, many) { return tf(n === 1 ? one : many, n); }

  // ---- small helpers ---------------------------------------------------------

  function esc(v) {
    return String(v == null ? "" : v).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }
  function $(id) { return document.getElementById(id); }
  function locale() { return LANG === "de" ? "de-AT" : "en-GB"; }
  function day(stamp) {
    if (!stamp) return "";
    var d = new Date(stamp);
    return isNaN(d) ? stamp : d.toLocaleDateString(locale(), { day: "numeric", month: "short", year: "numeric" });
  }
  function moment(stamp) {
    if (!stamp) return "";
    var d = new Date(stamp);
    return isNaN(d) ? stamp : d.toLocaleDateString(locale(), { weekday: "short", day: "numeric", month: "short", year: "numeric" }) +
      ", " + d.toLocaleTimeString(locale(), { hour: "2-digit", minute: "2-digit" });
  }
  function toast(text) {
    var el = $("toast");
    el.textContent = text;
    el.classList.add("show");
    clearTimeout(toast.timer);
    toast.timer = setTimeout(function () { el.classList.remove("show"); }, 4200);
  }

  var ICONS = {
    check: '<path d="M4 12.5l5 5L20 6.5"/>',
    send: '<path d="M21 3L10 14M21 3l-7 18-4-7-7-4z"/>',
    refresh: '<path d="M20 11a8 8 0 10-2.3 5.7M20 4v7h-7"/>',
    download: '<path d="M12 4v11m0 0l-4-4m4 4l4-4M5 20h14"/>',
    edit: '<path d="M4 20h4L19 9l-4-4L4 16zM13.5 6.5l4 4"/>',
    undo: '<path d="M9 7L4 12l5 5M4 12h10a6 6 0 010 12"/>',
    x: '<path d="M6 6l12 12M18 6L6 18"/>',
    alert: '<path d="M12 8v5m0 3.5v.01M10.3 3.9L2.6 17.5A2 2 0 004.3 20.5h15.4a2 2 0 001.7-3L13.7 3.9a2 2 0 00-3.4 0z"/>',
    folder: '<path d="M3 7a2 2 0 012-2h4l2 2h8a2 2 0 012 2v8a2 2 0 01-2 2H5a2 2 0 01-2-2z"/>',
    inbox: '<path d="M3 13l3-8h12l3 8v5a2 2 0 01-2 2H5a2 2 0 01-2-2zm0 0h5l1 3h6l1-3h5"/>',
    clip: '<path d="M21 11.5l-8.6 8.6a5 5 0 01-7.1-7.1l8.6-8.6a3.4 3.4 0 014.8 4.8l-8.6 8.6a1.7 1.7 0 01-2.4-2.4l7.9-7.9"/>',
    moon: '<path d="M20 14.5A8 8 0 019.5 4 8 8 0 1020 14.5z"/>',
    sun: '<path d="M12 4V2m0 20v-2m8-8h2M2 12h2m13.7-5.7l1.4-1.4M4.9 19.1l1.4-1.4m11.4 0l1.4 1.4M4.9 4.9l1.4 1.4M16 12a4 4 0 11-8 0 4 4 0 018 0z"/>',
    search: '<path d="M11 18a7 7 0 100-14 7 7 0 000 14zm5-2l5 5"/>',
    globe: '<path d="M12 21a9 9 0 100-18 9 9 0 000 18zm0 0c2.5-2.4 3.8-5.4 3.8-9S14.5 5.4 12 3m0 18c-2.5-2.4-3.8-5.4-3.8-9S9.5 5.4 12 3M3.5 9h17M3.5 15h17"/>',
    filter: '<path d="M3 5h18l-7 8v6l-4 2v-8z"/>'
  };
  function icon(name, size) {
    size = size || 16;
    return '<svg viewBox="0 0 24 24" width="' + size + '" height="' + size + '" fill="none" stroke="currentColor" ' +
      'stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">' + ICONS[name] + "</svg>";
  }
  // The mark beside "Claude is connected": a small spark in Claude's colour.
  function spark(size) {
    size = size || 14;
    return '<svg viewBox="0 0 24 24" width="' + size + '" height="' + size + '" fill="none" stroke="currentColor" ' +
      'stroke-width="2.6" stroke-linecap="round" aria-hidden="true"><path d="M12 2.5v19M2.5 12h19M5.3 5.3l13.4 13.4M18.7 5.3L5.3 18.7"/></svg>';
  }

  function api(path, body) {
    var opts = { headers: { "X-AGC-Token": TOKEN } };
    if (body !== undefined) {
      opts.method = "POST";
      opts.headers["Content-Type"] = "application/json";
      opts.body = JSON.stringify(body);
    }
    return fetch(path, opts).then(function (r) {
      return r.json().then(function (data) {
        if (!r.ok) throw new Error(data.error || t("The app could not do this."));
        return data;
      });
    });
  }
  function act(path, body, done) {
    return api(path, body || {}).then(function (data) {
      if (done) done(data);
      return refresh(true);
    }).catch(function (err) { toast(err.message); });
  }

  function refresh(force) {
    return api("/api/state").then(function (state) {
      S = state;
      ui.gone = false;
      draw(force);
    }).catch(function (err) {
      if (!ui.gone) {
        ui.gone = true;
        $("banners").innerHTML = '<div class="banner bad">' + icon("alert") + "<span>" +
          tf("The tool is no longer running ({0}). In Claude, ask for the deal flow outreach again and this screen comes back.", esc(err.message)) +
          "</span></div>";
      }
    });
  }

  // ---- drawing ---------------------------------------------------------------

  function put(id, html, force) {
    var el = $(id);
    if (ui.lastHtml[id] === html) return;
    var active = document.activeElement;
    var typing = active && el.contains(active) && /^(INPUT|TEXTAREA|SELECT)$/.test(active.tagName);
    if (typing && !force) return;           // never pull the text out from under someone typing
    var scrolls = {};
    el.querySelectorAll("[data-scroll]").forEach(function (n) { scrolls[n.dataset.scroll] = n.scrollTop; });
    el.innerHTML = html;
    ui.lastHtml[id] = html;
    el.querySelectorAll("[data-scroll]").forEach(function (n) {
      if (scrolls[n.dataset.scroll]) n.scrollTop = scrolls[n.dataset.scroll];
    });
  }

  // ---- light and dark ----------------------------------------------------------

  function darkWanted() {
    var pick = S ? S.settings.theme : "system";
    return pick === "dark" || (pick !== "light" && window.matchMedia && matchMedia("(prefers-color-scheme: dark)").matches);
  }
  function applyTheme() {
    var theme = darkWanted() ? "dark" : "light";
    if (document.documentElement.dataset.theme !== theme) document.documentElement.dataset.theme = theme;
    try { localStorage.setItem("agc-theme", S.settings.theme || "system"); } catch (e) {}
    var meta = document.querySelector('meta[name="theme-color"]');
    if (meta) meta.content = theme === "dark" ? "#0d1117" : "#ffffff";
  }
  if (window.matchMedia) matchMedia("(prefers-color-scheme: dark)").addEventListener("change", function () { if (S) { applyTheme(); draw(true); } });

  function draw(force) {
    if (!S) return;
    applyTheme();
    LANG = S.settings.language === "de" ? "de" : "en";
    if (document.documentElement.lang !== LANG) {
      document.documentElement.lang = LANG;
      document.querySelector(".skip").textContent = t("Skip to content");
    }
    if (!ui.tab) ui.tab = S.round ? "review" : (S.workbook.ok ? "contacts" : "setup");
    if (S.sending.active) ui.wasSending = true;
    else if (ui.wasSending) { ui.wasSending = false; if (S.sending.message) toast(S.sending.message); }

    var included = S.contacts.filter(function (c) { return c.included; }).length;
    var toReview = S.round ? S.round.drafts.filter(function (d) { return d.status === "pending"; }).length : 0;
    put("tabs", TABS.map(function (tab) {
      var n = tab[0] === "contacts" && included ? included : (tab[0] === "review" && toReview ? toReview : 0);
      return '<button data-action="tab" data-tab="' + tab[0] + '"' + (ui.tab === tab[0] ? ' aria-current="page"' : "") + ">" +
        t(tab[1]) + (n ? '<span class="count">' + n + "</span>" : "") + "</button>";
    }).join(""));

    var id = S.identity;
    put("who", '<span class="pill" title="' + t("The mailbox emails are sent from") + '">' +
      (id.ok ? tf("Sending as <b>{0}</b>", esc(id.email)) : (id.checking ? t("Checking Outlook…") : t("Outlook not ready"))) + "</span>" +
      '<span class="pill claude ' + (S.app.claude ? "on" : "off") + '" title="' + t("Claude changes an email when you ask, and reads the answers") + '">' +
      spark() + (S.app.claude ? t("Claude is connected") : t("Claude is not connected")) + "</span>" +
      '<button class="iconbtn" data-action="theme" aria-label="' + (darkWanted() ? t("Switch to the light screen") : t("Switch to the dark screen")) +
      '" title="' + (darkWanted() ? t("Switch to the light screen") : t("Switch to the dark screen")) + '">' + icon(darkWanted() ? "sun" : "moon") + "</button>");

    put("banners", banners());
    put("main", { setup: setup, contacts: contacts, review: review, tracker: tracker }[ui.tab](), force);
    put("modal", modal(), true);
  }

  function banners() {
    var out = "";
    if (S.app.simulated) out += '<div class="banner warn"><span>' + t("<b>Simulated mode.</b> No real email is sent or read.") + "</span></div>";
    if (S.app.notice) out += '<div class="banner note"><span>' + esc(S.app.notice) +
      '</span><button class="btn small" data-action="clear-notice">' + t("Dismiss") + "</button></div>";
    if (!S.identity.ok && !S.identity.checking) out += '<div class="banner bad">' + icon("alert") + "<span><b>" + t("Outlook is not ready.") + "</b> " +
      esc(S.identity.problem) + "</span></div>";
    var waiting = S.jobs.filter(function (j) { return j.status !== "failed"; }).length;
    if (!S.app.claude && waiting) out += '<div class="banner warn">' + icon("alert") + "<span>" +
      tn(waiting, "<b>Claude is not connected,</b> and {0} task is waiting for it. In Claude, say “continue the deal flow outreach”.",
        "<b>Claude is not connected,</b> and {0} tasks are waiting for it. In Claude, say “continue the deal flow outreach”.") + "</span></div>";
    return out;
  }

  // ---- setup -----------------------------------------------------------------

  function field(path, value, attrs) {
    return '<input type="text" autocomplete="off" data-setting="' + path + '" value="' + esc(value) + '" ' + (attrs || "") + ">";
  }
  function savedTick(path) { return '<span class="saved" data-saved="' + path + '">' + t("Saved") + "</span>"; }

  function setup() {
    var st = S.settings, wb = S.workbook, sch = st.schedule, plan = S.schedule;
    var h = '<div class="wide"><div class="head"><div><h1>' + t("Setup") + '</h1><p class="lede">' +
      t("Everything here is saved as you change it and remembered the next time you open the tool.") + "</p></div>" +
      '<div class="seg" role="group" aria-label="Language / Sprache">' +
      [["en", "English"], ["de", "Deutsch"]].map(function (l) {
        return '<button data-action="language" data-lang="' + l[0] + '" lang="' + l[0] + '" aria-pressed="' + (LANG === l[0]) + '">' + l[1] + "</button>";
      }).join("") + "</div></div><div class=\"setup\"><div>";

    // contact list
    h += '<section class="card"><h2>' + t("Contact list") + '</h2><p class="hint">' +
      t("The Excel workbook with the people you write to. It is only read, never changed.") +
      ' <a href="/api/template?t=' + encodeURIComponent(TOKEN) + '">' + t("Download an empty template") + "</a></p>" +
      '<div class="path">' + field("workbook", st.workbook, 'data-save="change" spellcheck="false" placeholder="C:\\…\\Contacts.xlsx" aria-label="' + t("Path to the contact list") + '"') +
      '<button class="btn" data-action="browse">' + icon("folder") + t("Browse…") + '</button></div><p style="margin:10px 0 0">';
    if (!st.workbook) h += '<span class="soft">' + t("No list chosen yet.") + "</span>";
    else if (!wb.ok) h += '<span class="bad">' + esc(wb.problem) + "</span>";
    else {
      var sheets = (wb.sheets && wb.sheets.length ? wb.sheets : [wb.sheet]).map(function (s) { return "“" + esc(s) + "”"; }).join(", ");
      h += '<span class="ok">' + (wb.sheets && wb.sheets.length > 1
        ? tn(S.contacts.length, "{0} contact read from the sheets {1}.", "{0} contacts read from the sheets {1}.")
        : tn(S.contacts.length, "{0} contact read from the sheet {1}.", "{0} contacts read from the sheet {1}.")).replace("{1}", sheets) + "</span>";
      if (wb.missing_columns.length) h += ' <span class="warn">' + tf("No column found for: {0}.", esc(wb.missing_columns.map(function (f) { return t(FIELD_NAMES[f] || f); }).join(", "))) + "</span>";
      if (wb.worked_out && wb.worked_out.length) h += ' <span class="soft">' + tf("Not in the list, so worked out for each person: {0}.",
        esc(wb.worked_out.map(function (f) { return t(FIELD_NAMES[f] || f); }).join(", "))) + "</span>";
      if (wb.unmatched_headers.length) h += ' <span class="soft" title="' + esc(wb.unmatched_headers.join(", ")) + '">' +
        tn(wb.unmatched_headers.length, "{0} more column is read as background for Claude.", "{0} more columns are read as background for Claude.") + "</span>";
    }
    h += "</p></section>";

    // who
    var codes = Object.keys(wb.owners || {}).sort(function (a, b) { return (wb.owners[b] - wb.owners[a]) || a.localeCompare(b); });
    var team = {};
    (S.team || []).forEach(function (p) { if (p.name) team[p.code] = p.name; });
    h += '<section class="card"><h2>' + t("You") + '</h2><p class="hint">' + (S.identity.ok
      ? tf("Emails go out from <b>{0}</b>, the mailbox set up in classic Outlook, with your Outlook signature.", esc(S.identity.email))
      : esc(S.identity.problem || "")) + '</p><div class="pair"><label class="field"><span>' + t("Your short form in the list") +
      savedTick("owner_code") + "</span>" + field("owner_code", st.owner_code, 'list="codes" maxlength="3" style="max-width:120px;text-transform:uppercase" spellcheck="false"') +
      '<datalist id="codes">' + codes.map(function (c) { return '<option value="' + esc(c) + '">' + esc((team[c] ? team[c] + ", " : "") + tn(wb.owners[c], "{0} contact", "{0} contacts")) + "</option>"; }).join("") + "</datalist></label>" +
      '<label class="field"><span>' + t("Your name as it appears in the Owner column") + savedTick("owner_name") + "</span>" +
      field("owner_name", st.owner_name, 'style="max-width:320px"') + "</label></div>" +
      '<p class="soft" style="margin:0 0 10px">' + (st.owner_code
        ? tf("Contacts with {0} in the Zuständigkeit column are yours ({1} in this list). Those with another short form are left to that person.",
          bold(st.owner_code), (wb.owners || {})[st.owner_code] || 0)
        : t("Contacts with another name in the Owner column are left to that person.")) + "</p>" +
      '<label class="check"><input type="checkbox" data-action="unassigned"' + (wb.unassigned_mine ? " checked" : "") + "> " +
      t("Count contacts nobody is responsible for as mine") + "</label></section>";

    // rhythm
    h += '<section class="card"><h2>' + t("Rhythm") + savedTick("schedule") + '</h2><p class="hint">' +
      (sch.auto_send && sch.mode !== "manual"
        ? t("On the due date the round is prepared and sent, without a review.")
        : t("On the due date the round is prepared and the review screen opens. Nothing is ever sent until you press Send.")) +
      '</p><div class="choices">' +
      Object.keys(plan.labels).map(function (m) {
        return '<label><input type="radio" name="mode" data-setting="schedule.mode" value="' + m + '"' +
          (sch.mode === m ? " checked" : "") + "> " + esc(plan.labels[m]) + "</label>";
      }).join("") + "</div>";
    if (sch.mode !== "manual") {
      h += '<div class="when"><label class="field"><span>' + (sch.mode === "date" ? t("Date") : t("First round on")) +
        '</span><input type="date" data-setting="schedule.start_date" value="' + esc(sch.start_date) + '"></label>' +
        '<label class="field"><span>' + t("Time") + '</span><input type="time" data-setting="schedule.time" value="' + esc(sch.time) + '"></label></div>';
      var c = sch.confirmed, failed = S.jobs.filter(function (j) { return j.type === "schedule" && j.status === "failed"; })[0];
      var pending = S.jobs.filter(function (j) { return j.type === "schedule" && j.status !== "failed"; })[0];
      h += '<div class="next">';
      if (plan.problem) h += '<span class="warn">' + esc(plan.problem) + "</span>";
      else {
        h += tf("Next round: <b>{0}</b>", esc(moment(plan.next_run))) + "<br>";
        if (pending) h += '<span class="soft">' + (S.app.claude ? t("Claude is registering this…") : t("Waiting for Claude to register this. It is saved and will be registered the next time Claude is connected.")) + "</span>";
        else if (failed) h += '<span class="bad">' + tf("Could not be registered: {0}", esc(failed.error)) + '</span> <button class="btn small" data-action="schedule-retry">' + t("Try again") + "</button>";
        else if (c && c.mode === sch.mode && c.next_run === plan.next_run) h += '<span class="ok">' + t("Registered with Claude’s scheduler.") + "</span>";
        else h += '<span class="warn">' + t("Not registered yet.") + '</span> <button class="btn small" data-action="schedule-retry">' + t("Register now") + "</button>";
        h += '<br><span class="soft">' + t("The scheduler runs while the Claude app is open. If it is closed on the day, the round is prepared the next time you open it.") + "</span>";
      }
      h += "</div>";

      // sending without review: only offered with an automatic rhythm
      h += '<label class="switch"><input type="checkbox" data-action="auto-send"' + (sch.auto_send ? " checked" : "") + "><span><b>" +
        t("Send without my review") + '</b><span class="sub">' + t("On the due date the emails go out by themselves. Nobody presses Send.") + "</span></span></label>";
      if (sch.auto_send) h += '<div class="caution">' + icon("alert") + "<div><b>" + t("Nobody reads these emails before they leave.") + "</b> " +
        t("Before the date, read your master email on this page once more, and look at the Contacts tab to see who will be written to. You can also prepare a round by hand at any time and look through it on the Review tab. An email that fails an automatic check is held back for you instead of being sent.") +
        "</div></div>";
    } else if (sch.confirmed && sch.confirmed.action !== "off") {
      var off = S.jobs.filter(function (j) { return j.type === "schedule" && j.status !== "failed"; })[0];
      h += '<div class="next soft">' + (off ? t("Switching the automatic run off…") : t("The automatic run is still registered.")) + "</div>";
    }
    h += "</section>";

    // details
    h += '<section class="card"><h2>' + t("Sending") + savedTick("numbers") + '</h2><p class="hint">' +
      t("Emails leave one at a time with a pause between them, the way a person sends.") + '</p><div class="numbers">' +
      num("batch_size", t("Emails per round, at most"), st.batch_size, 1, 200) +
      num("gap_min_seconds", t("Shortest pause between two emails, in seconds"), st.gap_min_seconds, 1, 600) +
      num("gap_max_seconds", t("Longest pause, in seconds"), st.gap_max_seconds, 1, 900) +
      num("followup_after_days", t("Follow up after this many days without an answer"), st.followup_after_days, 0, 365) +
      "</div></section></div><div>";

    // master emails
    var key = (ui.followup ? "fu_" : "") + ui.tpl;
    var tpl = st.templates[key] || { subject: "", body: "" };
    var probs = S.template_problems[key] || [];
    var kind = ui.followup ? "followup" : "round";
    var files = (st.attachments || {})[kind] || [];
    h += '<section class="card"><h2>' + t("Master emails") + '</h2><p class="hint">' +
      t("Write these yourself, the way you would write to someone you know. Everyone on the list gets this text as it stands, in the version that fits them.") + "</p>" +
      '<div class="row" style="margin-bottom:16px"><div class="seg">' +
      Object.keys(TPL_NAMES).map(function (k) {
        var flagged = (S.template_problems[(ui.followup ? "fu_" : "") + k] || []).length;
        return '<button data-action="tpl" data-key="' + k + '" aria-pressed="' + (ui.tpl === k) + '">' + t(TPL_NAMES[k]) +
          (flagged ? '<span class="flag" title="' + t("Needs attention") + '"></span>' : "") + "</button>";
      }).join("") + '</div><div class="seg"><button data-action="fu" data-on="0" aria-pressed="' + !ui.followup +
      '">' + t("First email") + '</button><button data-action="fu" data-on="1" aria-pressed="' + ui.followup + '">' + t("Follow-up") + "</button></div></div>" +
      '<label class="field"><span>' + t("Subject") + savedTick("templates." + key + ".subject") + "</span>" +
      field("templates." + key + ".subject", tpl.subject, 'data-sync="' + key + '"') + "</label>" +
      '<label class="field" style="margin-bottom:0"><span>' + t("Text") + savedTick("templates." + key + ".body") + "</span>" +
      '<div class="composer"><div class="ghost" title="' + t("Added for each person from the contact list") + '">' +
      (st.personalize ? t("Greeting: written for each person from the list") : TPL_GREETING[ui.tpl]) + "</div>" +
      '<textarea data-setting="templates.' + key + '.body" data-sync="' + key + '" rows="12" spellcheck="true" aria-label="' + t("Text of the master email") + '">' + esc(tpl.body) +
      '</textarea><div class="ghost">' + t("Your Outlook signature") + "</div></div></label>" + syncLine(key);
    if (probs.length) h += '<ul class="problems">' + probs.map(function (p) { return "<li>" + esc(p) + "</li>"; }).join("") + "</ul>";
    h += '<div class="files"><div class="row"><b>' + (ui.followup ? t("Attached to every follow-up") : t("Attached to every email of a round")) + "</b>" +
      '<span class="spacer"></span><button class="btn small" data-action="attach" data-target="master" data-kind="' + kind + '">' + icon("clip", 15) + t("Add a file") + "</button></div>" +
      (files.length ? attachmentList(files, 'data-target="master" data-kind="' + kind + '"', false)
        : '<p class="soft" style="margin:6px 0 0">' + t("No attachment. A file added here goes out with every email; on the Review tab it can be taken off a single one.") + "</p>") + "</div>";
    h += '<div class="opts"><label class="check"><input type="checkbox" data-action="flag" data-flag="personalize"' + (st.personalize ? " checked" : "") + "> " +
      "<span><b>" + t("Claude adjusts each email to the person") + '</b><span class="sub">' +
      t("The greeting from the name and title in the list (Herr or Frau, Dr.), and a line only where the list gives a reason. Changed lines are marked for you.") + "</span></span></label>" +
      '<label class="check"><input type="checkbox" data-action="flag" data-flag="sync_forms"' + (st.sync_forms ? " checked" : "") + "> " +
      "<span><b>" + t("Keep Sie and du in step") + '</b><span class="sub">' +
      t("When you finish writing one German version, Claude writes the other from it: more formal for Sie, more personal for du.") + "</span></span></label></div>";
    h += "</section></div></div></div>";
    return h;
  }

  var FIELD_NAMES = { email: "Email", name: "Name", gender: "Herr/Frau", language: "Language", form: "Sie/du" };

  // Under a German master email: was the other version written from this one?
  function syncLine(key) {
    var base = key.replace("fu_", ""), other = COUNTERPART[base];
    if (!other || !S.settings.sync_forms) return '<p class="soft" style="margin:10px 0 0">' +
      t("The greeting is added above your text for each person. Begin with the sentence that follows it.") + "</p>";
    var prefix = key.indexOf("fu_") === 0 ? "fu_" : "";
    var mine = S.template_sync[key] || {}, theirs = S.template_sync[prefix + other] || {};
    var otherName = other === "de_du" ? "du" : "Sie";
    var line;
    if (theirs.state === "working") line = '<span class="claude-ink">' + spark(13) + " " + (S.app.claude
      ? tf("Claude is writing the {0} version from this text…", otherName) : tf("The {0} version is written as soon as Claude is connected.", otherName)) + "</span>";
    else if (mine.state === "working") line = '<span class="claude-ink">' + spark(13) + " " + tf("Claude is rewriting this version from the {0} one…", otherName) + "</span>";
    else if (mine.state === "fresh") line = '<span class="ok">' + tf("Claude wrote this version from your {0} text. Read it once; change anything and Claude rewrites the other.", otherName) + "</span>";
    else if (theirs.state === "fresh") line = '<span class="ok">' + tf("The {0} version was written by Claude from this text.", otherName) + "</span>";
    else if (theirs.state === "failed") line = '<span class="bad">' + tf("The {0} version could not be written: {1}", otherName, esc(theirs.error)) + "</span>";
    else line = '<span class="soft">' + tf("When you leave this text, Claude writes the {0} version from it.", otherName) + "</span>";
    return '<p class="syncline">' + line + ' <button class="btn quiet small" data-action="sync-now" data-key="' + key + '">' +
      tf("Write the {0} version now", otherName) + "</button></p>";
  }

  function bold(text) { return "<b>" + esc(text) + "</b>"; }
  function size(n) { return n > 1048576 ? (n / 1048576).toFixed(1).replace(".", LANG === "de" ? "," : ".") + " MB" : Math.max(1, Math.round(n / 1024)) + " KB"; }

  function attachmentList(files, attrs, locked) {
    return '<ul class="attachments">' + files.map(function (a) {
      return '<li class="' + (a.missing ? "gone" : "") + '">' + icon("clip", 14) + '<span class="fname">' + esc(a.name) + '</span><span class="soft num">' + size(a.size) + "</span>" +
        (locked ? "" : '<button data-action="detach" data-id="' + esc(a.id) + '" ' + attrs + ' aria-label="' + esc(tf("Remove {0}", a.name)) + '" title="' + esc(tf("Remove {0}", a.name)) + '">' + icon("x", 13) + "</button>") + "</li>";
    }).join("") + "</ul>";
  }
  function num(path, label, value, min, max) {
    return '<label class="field"><span>' + label + '</span><input type="number" inputmode="numeric" data-setting="' + path + '" data-tick="numbers" min="' +
      min + '" max="' + max + '" value="' + esc(value) + '"></label>';
  }

  // ---- contacts --------------------------------------------------------------

  function typeColor(name, extra) {
    var i = TYPE_ORDER.indexOf(name);
    return i >= 0 ? TYPE_COLORS[i] : (name === extra ? EXTRA_COLOR : OTHER_COLOR);
  }

  // How the people in view divide by kind. At most eight slices: the seven
  // usual kinds, one more of the list's own if it has one, and the rest as Other.
  function typeShares(rows) {
    var counts = {};
    rows.forEach(function (c) { counts[c.type || OTHER] = (counts[c.type || OTHER] || 0) + 1; });
    var own = Object.keys(counts).filter(function (k) { return TYPE_ORDER.indexOf(k) < 0 && k !== OTHER; })
      .sort(function (a, b) { return counts[b] - counts[a] || a.localeCompare(b); });
    var extra = own[0] || "";
    var parts = TYPE_ORDER.concat(extra ? [extra] : []).filter(function (k) { return counts[k]; })
      .map(function (k) { return { name: k, n: counts[k], color: typeColor(k, extra), members: [k] }; });
    var rest = own.slice(1).concat(counts[OTHER] ? [OTHER] : []);
    if (rest.length) parts.push({ name: OTHER, color: OTHER_COLOR, members: rest,
      n: rest.reduce(function (sum, k) { return sum + counts[k]; }, 0) });
    return { parts: parts, extra: extra };
  }

  function donut(parts, total) {
    var R = 66, W = 22, C = 2 * Math.PI * R, at = 0, gap = parts.length > 1 ? 2 : 0;
    var h = '<svg class="donut" viewBox="0 0 180 180" width="180" height="180" role="img" aria-label="' + t("Contacts by type") + ": " +
      esc(parts.map(function (p) { return t(p.name) + " " + p.n; }).join(", ")) + '">';
    parts.forEach(function (p) {
      var len = p.n / total * C, dash = Math.max(len - gap, 1);
      var dim = ui.type && ui.type !== p.name ? ' opacity=".28"' : "";
      h += '<circle cx="90" cy="90" r="' + R + '" fill="none" stroke="' + p.color + '" stroke-width="' + W + '" stroke-dasharray="' +
        dash.toFixed(2) + " " + (C - dash).toFixed(2) + '" stroke-dashoffset="' + (-at).toFixed(2) + '" transform="rotate(-90 90 90)"' + dim +
        "><title>" + esc(t(p.name)) + ": " + p.n + " (" + Math.round(100 * p.n / total) + "%)</title></circle>";
      at += len;
    });
    return h + '<text class="total" x="90" y="92" text-anchor="middle">' + total + '</text><text class="unit" x="90" y="110" text-anchor="middle">' +
      (total === 1 ? t("contact") : t("contacts")) + "</text></svg>";
  }

  function contacts() {
    var wb = S.workbook;
    if (!wb.ok) return empty(t("No contact list yet"), wb.path ? wb.problem : t("Choose the Excel workbook with your contacts to begin."),
      '<button class="btn primary" data-action="tab" data-tab="setup">' + t("Go to Setup") + "</button>");
    var all = S.contacts, inn = all.filter(function (c) { return c.included; });
    var view = ui.contactFilter === "in" ? inn : (ui.contactFilter === "out" ? all.filter(function (c) { return !c.included; }) :
      ui.contactFilter === "research" ? all.filter(function (c) { return c.research && c.research.length; }) : all);
    var shares = typeShares(view);
    var picked = shares.parts.filter(function (p) { return p.name === ui.type; })[0];
    if (ui.type && !picked) ui.type = "";
    var rows = picked ? view.filter(function (c) { return picked.members.indexOf(c.type || OTHER) >= 0; }) : view;
    if (ui.q.trim()) {
      var words = ui.q.toLowerCase().split(/\s+/).filter(Boolean);
      rows = rows.filter(function (c) {
        var hay = [c.title, c.first, c.last, c.company, c.email, c.city, c.region, c.state, c.owner, c.role, c.type].join(" ").toLowerCase();
        return words.every(function (w) { return hay.indexOf(w) >= 0; });
      });
    }
    var open = !!S.round;
    var researchN = inn.filter(function (c) { return c.research && c.research.length; }).length;
    var needInfo = all.filter(function (c) { return c.research && c.research.length; }).length;

    var h = '<div class="wide"><div class="head"><div><h1>' +
      tn(inn.length, '<span class="num">{0}</span> person in this round', '<span class="num">{0}</span> people in this round') +
      '</h1><p class="lede">' + tf("{0} of {1} are left out, each with the reason shown. Tick or untick to decide by hand.", all.length - inn.length, all.length) +
      (researchN ? " " + tn(researchN, "For {0} of them Claude looks up the missing address or contact person online; you decide on what it finds.",
        "For {0} of them Claude looks up the missing address or contact person online; you decide on what it finds.") : "") + "</p></div>" +
      '<button class="btn" data-action="reload">' + icon("refresh") + t("Read the list again") + "</button>" +
      '<button class="btn primary" data-action="start-round"' + (open || !inn.length || !S.identity.ok ? " disabled" : "") + ">" +
      tn(inn.length, "Prepare {0} email", "Prepare {0} emails") + "</button></div>";
    if (open) h += '<div class="status">' + tn(S.round.drafts.length, "A round is already open with {0} email.", "A round is already open with {0} emails.") +
      ' <button class="btn quiet small" data-action="tab" data-tab="review">' + t("Go to Review") + "</button></div>";

    h += filterCard();
    h += '<div class="split"><div><div class="row" style="margin-bottom:12px"><div class="seg">' +
      [["in", "In this round", inn.length], ["out", "Left out", all.length - inn.length], ["all", "All", all.length]]
        .concat(needInfo ? [["research", "Details missing", needInfo]] : [])
        .map(function (f) { return '<button data-action="cfilter" data-f="' + f[0] + '" aria-pressed="' + (ui.contactFilter === f[0]) + '">' + t(f[1]) + ' <span class="num soft">' + f[2] + "</span></button>"; }).join("") +
      "</div>" + (picked ? '<span class="chip"><i class="dot" style="background:' + picked.color + ';margin:0"></i>' + esc(t(picked.name)) +
        '<button data-action="type" data-type="" aria-label="' + t("Show every type again") + '">' + icon("x", 12) + "</button></span>" : "") +
      '<label class="search">' + icon("search", 15) + '<input type="search" data-q value="' + esc(ui.q) + '" placeholder="' + t("Search name, firm, city…") + '" aria-label="' + t("Search the list") + '"></label></div>';
    var shown = ui.showAll ? rows : rows.slice(0, ROWS_SHOWN);
    h += '<div class="tablewrap"><table><thead><tr><th><span class="soft" aria-hidden="true">' + t("In") + "</span></th><th>" + t("Name") + "</th><th>" +
      t("Company") + "</th><th>" + t("Type") + "</th><th>" + t("Region") + "</th><th>" + t("Writes in") + "</th><th>" + t("Status") + "</th></tr></thead><tbody>";
    h += shown.map(function (c) {
      var assumed = c.assumed && c.assumed.length ? '<span class="sub warn">' + esc(c.assumed.join("; ")) + "</span>" : "";
      var name = [c.title, c.first, c.last].filter(Boolean).join(" ");
      var lookup = c.research && c.research.length ? '<span class="sub claude-ink">' + spark(11) + " " +
        (c.research.indexOf("email") >= 0 ? t("address to be found online") : t("contact person to be found online")) + "</span>" : "";
      var where = [c.state || (c.country && c.country !== "MULTI" ? t(COUNTRY_NAMES[c.country] || c.country) : ""), c.city && c.city !== c.state ? c.city : ""]
        .filter(Boolean).join(", ");
      var marks = [c.priority ? tf("Prio {0}", c.priority) : "", c.relevance ? tf("relevance {0}", t(RELEVANCE_NAMES[c.relevance]).toLowerCase()) : ""].filter(Boolean).join(" · ");
      return '<tr class="' + (c.included ? "" : "out") + '"><td><input type="checkbox" data-action="override" data-id="' + esc(c.id) + '"' +
        (c.included ? " checked" : "") + (c.locked || open ? " disabled" : "") + ' aria-label="' + esc(tf("Include {0}", name || c.company)) + '"></td><td><b>' +
        (name ? esc(name) : '<span class="soft">' + t("no contact person") + "</span>") + '</b><span class="sub">' + (c.email ? esc(c.email) : t("no email address")) + "</span>" + lookup + "</td><td>" + esc(c.company) +
        '<span class="sub">' + esc(c.role) + '</span></td><td class="fit"' + (c.type_guessed ? ' title="' + t("Read off the firm’s name. Add a Type column to the list to set it yourself.") + '"' : "") +
        '><i class="dot" style="background:' + typeColor(c.type, shares.extra) + '"></i>' + esc(t(c.type)) + (marks ? '<span class="sub">' + esc(marks) + "</span>" : "") +
        '</td><td class="fit">' + (esc(where) || '<span class="soft">' + t("not known") + "</span>") + '</td><td class="fit">' +
        (c.language === "en" ? t("English") : t("German")) + ", " + (c.form === "du" ? "du" : (c.language === "en" ? t("formal") : "Sie")) + assumed +
        "</td><td>" + esc(c.reason) + (c.last_sent ? '<span class="sub">' + tf("last written {0}", esc(day(c.last_sent))) + "</span>" : "") + "</td></tr>";
    }).join("") || '<tr><td colspan="7" class="soft">' + t("Nobody here.") + "</td></tr>";
    h += "</tbody></table></div>";
    if (shown.length < rows.length) h += '<div class="more"><button class="btn" data-action="show-all">' + tf("Show all {0}", rows.length) + "</button></div>";
    h += "</div>";

    var names = { "in": tf("By type, for the {0} in this round.", view.length), out: tf("By type, for the {0} left out.", view.length),
      all: tf("By type, for all {0} on the list.", view.length), research: tf("By type, for the {0} with details missing.", view.length) };
    h += '<aside class="card side"><h2>' + t("Who they are") + '</h2><p class="soft" style="margin:0">' + names[ui.contactFilter] + "</p>";
    if (view.length) {
      h += donut(shares.parts, view.length) + '<ul class="legend">' + shares.parts.map(function (p) {
        return '<li><button data-action="type" data-type="' + esc(p.name) + '" aria-pressed="' + (ui.type === p.name) + '" title="' + esc(tf("Show only {0}", t(p.name))) + '">' +
          '<i class="dot" style="background:' + p.color + '"></i><span>' + esc(t(p.name)) + '</span><span class="n">' + p.n + '</span><span class="pct">' +
          Math.round(100 * p.n / view.length) + "%</span></button></li>";
      }).join("") + "</ul>";
      if (view.some(function (c) { return c.type_guessed; })) h += '<p class="sidenote">' + t("Where the list has no Type, it is read off the firm’s name. A Type column in the list overrides that.") + "</p>";
    } else h += '<p class="soft" style="margin:16px 0 0">' + t("Nobody in this view.") + "</p>";
    h += "</aside></div></div>";
    return h;
  }

  // The user's own filters: which regions, priorities and relevance they write to.
  // They decide who is in the round, and are saved like every other setting.
  function filterCard() {
    var f = S.settings.filters || {}, o = S.filter_options || {};
    var active = ["countries", "states", "priorities", "relevance"].reduce(function (n, k) { return n + ((f[k] || []).length ? 1 : 0); }, 0);
    var h = '<section class="card filters-card"><div class="row"><button class="disclose" data-action="filters" aria-expanded="' + (ui.filtersOpen || false) + '">' +
      icon("filter", 15) + "<b>" + t("Who I write to") + "</b>" + (active ? '<span class="count">' + active + "</span>" : "") + "</button>" +
      '<span class="soft">' + (active ? summary(f) : t("Every region, priority and relevance.")) + "</span><span class=\"spacer\"></span>" +
      (active ? '<button class="btn quiet small" data-action="filters-clear">' + t("Clear the filters") + "</button>" : "") + "</div>";
    if (ui.filtersOpen) {
      h += '<div class="facets">' +
        facet("countries", t("Country"), o.countries || [], function (v) { return t(COUNTRY_NAMES[v] || v); });
      var chosen = (f.countries || []).filter(function (c) { return (o.states || {})[c]; });
      if (chosen.length === 1) h += facet("states", tf("Region in {0}", t(COUNTRY_NAMES[chosen[0]] || chosen[0])), o.states[chosen[0]], function (v) { return v; });
      h += facet("priorities", t("Priority"), o.priorities || [], function (v) { return v === "none" ? t("Not set") : v; }) +
        facet("relevance", t("Relevance for AT deal flow"), o.relevance || [], function (v) { return t(RELEVANCE_NAMES[v] || v); }) + "</div>" +
        '<p class="soft" style="margin:8px 0 0">' + t("Region, priority and relevance come from the list (Region, Ort, Prio., Relevanz). Where the list has no region, it is read off the city, the postcode or the address.") + "</p>";
    }
    return h + "</section>";
  }
  function summary(f) {
    var parts = [];
    if ((f.countries || []).length) parts.push(f.countries.map(function (v) { return t(COUNTRY_NAMES[v] || v); }).join(", "));
    if ((f.states || []).length) parts.push(f.states.join(", "));
    if ((f.priorities || []).length) parts.push(tf("Prio {0}", f.priorities.map(function (v) { return v === "none" ? "–" : v; }).join("/")));
    if ((f.relevance || []).length) parts.push(tf("relevance {0}", f.relevance.map(function (v) { return t(RELEVANCE_NAMES[v] || v).toLowerCase(); }).join("/")));
    return esc(parts.join(" · "));
  }
  function facet(group, label, options, name) {
    var on = (S.settings.filters || {})[group] || [];
    return '<div class="facet"><span class="label">' + esc(label) + '</span><div class="chips">' + options.map(function (x) {
      return '<button class="fchip" data-action="facet" data-group="' + group + '" data-value="' + esc(x.value) + '" aria-pressed="' + (on.indexOf(x.value) >= 0) + '">' +
        esc(name(x.value)) + ' <span class="num">' + x.n + "</span></button>";
    }).join("") + "</div></div>";
  }

  function empty(title, text, button) {
    return '<div class="empty"><h1>' + esc(title) + "</h1><p>" + esc(text) + "</p>" + (button || "") + "</div>";
  }

  // ---- review ----------------------------------------------------------------

  function glyph(d) {
    var cls = d.status === "waiting" || d.status === "preparing" || d.status === "research" ? "waiting" : d.status === "approved" ? "approved" :
      (d.status === "sent" || d.status === "outbox") ? "sent" : d.status === "skipped" ? "skipped" :
      (d.status === "failed" || d.level === "fail") ? "fail" : d.level === "warn" ? "warn" : "";
    var words = { waiting: d.status === "research" ? t("Claude is looking it up online") : d.status === "preparing" ? t("Claude is adjusting it to the list") : t("Claude is changing it"),
      approved: t("Approved"), sent: t("Sent"), skipped: t("Skipped"),
      fail: d.status === "failed" ? t("Could not be sent") : t("A check failed"), warn: t("Worth a look"), "": t("To review") };
    var inner = cls === "approved" || cls === "sent" ? icon("check") : (cls === "fail" || cls === "warn" ? '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3.4" stroke-linecap="round" aria-hidden="true"><path d="M12 6v8m0 4v.01"/></svg>' : "");
    return '<i class="glyph ' + cls + '" title="' + words[cls] + '">' + inner + "</i>";
  }
  function person(d) { return [d.contact.first, d.contact.last].filter(Boolean).join(" ") || d.to || d.contact.company; }

  function review() {
    var r = S.round;
    if (!r) {
      var inn = S.contacts.filter(function (c) { return c.included; }).length;
      var msg = S.sending.message && !S.sending.test ? S.sending.message + " " : "";
      return empty(msg ? t("Round finished") : t("No round is open"),
        msg + (inn ? tn(inn, "{0} person is due. Start a round from the Contacts tab.", "{0} people are due. Start a round from the Contacts tab.") : t("Nobody is due right now.")),
        '<button class="btn primary" data-action="tab" data-tab="' + (msg ? "tracker" : "contacts") + '">' + (msg ? t("Open the tracker") : t("Go to Contacts")) + "</button>");
    }
    var ds = r.drafts, n = function (s) { return ds.filter(function (d) { return d.status === s; }).length; };
    var pending = n("pending"), approved = n("approved"), sentN = n("sent") + n("outbox"), failedN = n("failed");
    var ready = ds.filter(function (d) { return d.status === "pending" && d.level !== "fail"; }).length;
    var busy = S.sending.active;
    var preparing = n("preparing"), looking = n("research");
    var found = ds.filter(function (d) { return d.research && d.research.status === "found" && !d.research.accepted && d.status !== "skipped"; }).length;
    var h = '<div class="wide"><div class="head"><div><h1>' + esc(r.label) + '</h1><p class="lede num">' +
      [tf("{0} approved", approved), tf("{0} to review", pending), tf("{0} skipped", n("skipped"))]
        .concat(sentN ? [tf("{0} sent", sentN)] : [], failedN ? [tf("{0} failed", failedN)] : []).join(", ") +
      "</p></div>" +
      '<button class="btn danger" data-action="close-round"' + (busy ? " disabled" : "") + ">" + (sentN ? t("Close this round") : t("Discard this round")) + "</button>" +
      '<button class="btn" data-action="approve-all"' + (ready && !busy ? "" : " disabled") + ">" + icon("check") + t("Approve all") + (ready ? ' <span class="num soft">' + ready + "</span>" : "") + "</button>" +
      '<button class="btn primary" data-action="ask-send"' + (approved && !busy && S.identity.ok ? "" : " disabled") + ">" + icon("send") +
      tn(approved, "Send {0} approved email", "Send {0} approved emails") + "</button></div>";

    if (preparing) {
      h += '<div class="status row claude-box">' + spark(15) + "<span>" + (S.app.claude
        ? tn(preparing, "Claude is adjusting {0} email to what the list says about the person…", "Claude is adjusting {0} emails to what the list says about each person…")
        : tn(preparing, "{0} email waits for Claude to adjust it to the list. In Claude, say “continue the deal flow outreach”.", "{0} emails wait for Claude to adjust them to the list. In Claude, say “continue the deal flow outreach”.")) +
        '</span><span class="spacer"></span><button class="btn small" data-action="skip-prepare">' + t("Go ahead without it") + "</button></div>";
    }
    if (looking) h += '<div class="status row claude-box">' + spark(15) + "<span>" + (S.app.claude
      ? tn(looking, "Claude is looking up the missing details of {0} contact online…", "Claude is looking up the missing details of {0} contacts online…")
      : tn(looking, "{0} contact waits for Claude to look up its missing details.", "{0} contacts wait for Claude to look up their missing details.")) + "</span></div>";
    if (found) h += '<div class="status row found-box">' + icon("globe", 16) + "<span>" +
      tn(found, "<b>Found online:</b> Claude found the missing details for {0} contact. They are not in your list. Check each one and decide before it can be approved.",
        "<b>Found online:</b> Claude found the missing details for {0} contacts. They are not in your list. Check each one and decide before they can be approved.") +
      '</span><span class="spacer"></span><button class="btn small" data-action="filter" data-f="online">' + t("Show them") + "</button></div>";

    if (busy) {
      var s = S.sending;
      h += '<div class="status"><div class="row"><b class="num">' + (s.test ? tf("Sending a test to yourself: {0} of {1}", s.done, s.total) : tf("Sending: {0} of {1}", s.done, s.total)) +
        "</b>" + (s.current ? '<span class="soft">' + tf("now: {0}", esc(s.current)) + "</span>" : "") + '<span class="spacer"></span>' +
        '<button class="btn danger small" data-action="stop">' + t("Stop") + '</button></div><div class="progress"><i style="width:' +
        Math.round(100 * s.done / Math.max(1, s.total)) + '%"></i></div><span class="soft">' + t("Keep Outlook and this window open. Emails go out one at a time with a pause between them.") + "</span></div>";
    } else if (S.sending.message && S.sending.round_id === r.id) {
      h += '<div class="status">' + esc(S.sending.message) + "</div>";
    }

    var filters = { all: function () { return true; }, review: function (d) { return d.status === "pending"; },
      flagged: function (d) { return (d.level !== "ok" || d.changed_by || d.status === "waiting") && d.status !== "sent"; },
      approved: function (d) { return d.status === "approved"; },
      online: function (d) { return !!d.research; } };
    if (ui.filter === "online" && !ds.some(filters.online)) ui.filter = "all";
    var list = ds.filter(filters[ui.filter]);
    if (!ui.sel || !ds.some(function (d) { return d.contact_id === ui.sel; })) {
      var first = ds.filter(function (d) { return d.status === "pending"; })[0] || ds[0];
      ui.sel = first ? first.contact_id : null;
    }
    var cur = ds.filter(function (d) { return d.contact_id === ui.sel; })[0];

    h += '<div class="desk"><div class="pile"><div class="filters"><div class="seg">' +
      [["all", "All"], ["review", "To review"], ["flagged", "Changed"], ["approved", "Approved"]]
        .concat(ds.some(filters.online) ? [["online", "Found online"]] : []).map(function (f) {
        return '<button data-action="filter" data-f="' + f[0] + '" aria-pressed="' + (ui.filter === f[0]) + '">' + t(f[1]) + "</button>";
      }).join("") + '</div></div><ul data-scroll="pile">' + (list.map(function (d) {
        return '<li><button data-action="select" data-id="' + esc(d.contact_id) + '" aria-current="' + (d.contact_id === ui.sel) + '">' + glyph(d) +
          '<span><span class="name">' + esc(person(d)) + '</span><span class="firm">' + esc(d.contact.company) + "</span></span></button></li>";
      }).join("") || '<li style="padding:14px" class="soft">' + t("Nothing in this view.") + "</li>") + "</ul></div><div>" + (cur ? letter(r, cur, busy) : "") + "</div></div></div>";
    return h;
  }

  // The email with every line that differs from the master text marked.
  function marked(d) {
    // Compared without regard to capitals: a sentence that only moved from
    // "ich melde" to "Ich melde" because a line was put before it is not a change.
    var usual = {};
    (d.standard || "").split("\n").forEach(function (line) { usual[line.trim().toLowerCase()] = true; });
    return d.body.split("\n").map(function (line) {
      return line.trim() && !usual[line.trim().toLowerCase()] ? "<mark>" + esc(line) + "</mark>" : esc(line);
    }).join("\n");
  }

  function letter(r, d, busy) {
    var c = d.contact, locked = busy || d.status === "sent" || d.status === "outbox" || d.status === "sending";
    var h = '<article class="letter"><dl class="meta"><dt>' + t("From") + "</dt><dd>" + esc(S.identity.email || t("your Outlook mailbox")) +
      "</dd><dt>" + t("To") + "</dt><dd>";
    if (ui.editTo === d.contact_id) {
      h += '<div class="row"><input type="text" autocomplete="off" data-to value="' + esc(ui.buf && ui.buf.to || d.to || "") + '" aria-label="' + t("Email address") + '" spellcheck="false" style="max-width:340px">' +
        '<button class="btn small primary" data-action="save-to">' + t("Use this address") + '</button><button class="btn small" data-action="cancel-to">' + t("Cancel") + "</button></div>";
    } else {
      h += esc(person(d)) + " " + (d.to ? '<span class="soft">&lt;' + esc(d.to) + "&gt;</span>" : '<span class="bad">' + t("no address yet") + "</span>") +
        (d.research && !locked && d.status !== "research" ? ' <button class="btn quiet small" data-action="edit-to">' + t("Change the address") + "</button>" : "");
    }
    h += "</dd><dt>" + t("Subject") + "</dt><dd>";
    if (d.status === "waiting" || d.status === "preparing" || d.status === "research") {
      var what = d.status === "research" ? (S.app.claude ? t("Claude is looking up the missing details online…") : t("Waiting for Claude to look up the missing details…"))
        : d.status === "preparing" ? (S.app.claude ? t("Claude is adjusting this email to the list…") : t("Waiting for Claude to adjust this email to the list…"))
        : (S.app.claude ? t("Claude is changing this email…") : t("Waiting for Claude to change this email…"));
      var why = d.status === "waiting" ? tf("You asked: “{0}”", esc(d.note))
        : d.status === "research" ? t("The list has no email address or no contact person here. What Claude finds is shown to you to decide on; it is not written into the list.")
        : t("The greeting from the name in the list, and a line only where the list gives a reason.");
      return h + "<b>" + esc(d.subject) + '</b></dd></dl><div class="busy">' + spark(18) + "<div><b>" + what + '</b><br><span class="soft">' + why + "</span></div></div></article>" +
        (d.status !== "waiting" ? '<div class="under row"><button class="btn" data-action="set" data-s="skipped">' + t("Skip this person") + "</button></div>" : "");
    }
    if (ui.editing === d.contact_id) {
      h += '<input type="text" autocomplete="off" data-buf="subject" value="' + esc(ui.buf.subject) + '" aria-label="' + t("Subject") + '"></dd></dl>' +
        '<textarea class="body" data-buf="body" aria-label="' + t("Email text") + '" spellcheck="true">' + esc(ui.buf.body) + "</textarea></article>" +
        '<div class="under row"><button class="btn primary" data-action="save-edit">' + t("Save changes") + '</button><button class="btn" data-action="cancel-edit">' + t("Cancel") + "</button></div>";
      return h;
    }
    var files = d.attachments || [];
    h += "<b>" + esc(d.subject) + "</b></dd>" + (files.length || !locked ? "<dt>" + t("Files") + "</dt><dd>" +
      (files.length ? attachmentList(files, 'data-target="draft"', locked) : '<span class="soft">' + t("none") + "</span>") +
      (locked ? "" : '<button class="btn quiet small" data-action="attach" data-target="draft">' + icon("clip", 14) + t("Add a file") + "</button>") + "</dd>" : "") +
      '</dl><div class="body">' + marked(d) + '</div><div class="sig">' + t("Your Outlook signature follows here.") + "</div></article>";
    h += '<div class="under">' + researchPanel(d, locked) + '<div class="row">';
    var off = locked ? " disabled" : "";
    if (d.status === "sent" || d.status === "outbox") {
      h += '<span class="ok">' + tf("<b>Sent</b> {0}", esc(moment(d.sent_at))) + "</span>" +
        (d.status === "outbox" ? ' <span class="warn">' + t("Still in the Outlook outbox. Open Outlook so it can leave.") + "</span>" : "");
    } else {
      h += (d.status === "approved"
        ? '<button class="btn" data-action="set" data-s="pending"' + off + ">" + icon("undo") + t("Take back approval") + "</button>"
        : '<button class="btn primary" data-action="set" data-s="approved"' + off + (unsettled(d) ? ' disabled title="' + t("Settle the address first.") + '"' : "") + ">" + icon("check") + t("Approve") + "</button>") +
        (d.status === "skipped"
          ? '<button class="btn" data-action="set" data-s="pending"' + off + ">" + t("Put back") + "</button>"
          : '<button class="btn" data-action="set" data-s="skipped"' + off + ">" + t("Skip this person") + "</button>") +
        '<button class="btn" data-action="edit"' + off + ">" + icon("edit") + t("Edit text") + "</button>" +
        '<button class="btn" data-action="ask"' + off + ">" + spark(15) + t("Ask Claude") + "</button>" +
        '<span class="spacer"></span><button class="btn quiet" data-action="test"' + (busy || !S.identity.ok ? " disabled" : "") + ">" + t("Send a test to myself") + "</button>";
    }
    h += "</div>";
    if (d.status === "failed") h += '<ul class="checks"><li class="fail">' + icon("alert") + "<span><b>" + t("Could not be sent.") + "</b> " + esc(d.error) + " " + t("Approve it again to retry.") + "</span></li></ul>";
    if (ui.asking === d.contact_id) {
      h += '<div class="ask"><label class="field"><span>' + spark(15) + t("What should Claude change in this email?") + "</span>" +
        '<input type="text" autocomplete="off" data-note value="' + esc(ui.note) + '" placeholder="' + t("e.g. add a line that we met at the conference in May…") + '"></label>' +
        '<p class="soft" style="margin:-4px 0 10px">' + t("Claude can read your earlier emails with this address, so you can say “refer to the email from two weeks ago about the deal”.") + "</p>" +
        '<div class="row"><button class="btn primary" data-action="send-ask">' + t("Ask Claude") + '</button><button class="btn" data-action="cancel-ask">' + t("Cancel") + "</button>" +
        (S.app.claude ? "" : '<span class="warn">' + t("Claude is not connected right now. The request waits until it is.") + "</span>") + "</div></div>";
    }
    if (d.changed_by) {
      h += '<p class="origin"><i></i><span>' + (d.changed_by === "claude"
        ? tf("Claude changed the marked lines at your request: “{0}”.", esc(d.note))
        : d.changed_by === "list" ? t("Claude adjusted the marked lines to what the list says about this person.")
        : t("You edited the marked lines by hand.")) + " " + t("Everything else is your master email.") + ' <button class="btn quiet small" data-action="reset"' + off + ">" +
        icon("undo", 14) + t("Back to the master email") + "</button></span></p>";
    } else if (d.status !== "sent" && d.status !== "outbox") {
      h += '<p class="origin"><span>' + (d.greeting
        ? tf("Your master email, with the greeting Claude wrote from the list. The same text goes to everyone who gets the {0} version.", t(TPL_NAMES[d.template]))
        : tf("Your master email, with the greeting from the list. The same text goes to everyone who gets the {0} version.", t(TPL_NAMES[d.template]))) + "</span></p>";
    }
    if (d.checks.length) h += '<ul class="checks">' + d.checks.map(function (k) { return '<li class="' + k.level + '">' + icon("alert") + "<span>" + esc(k.text) + "</span></li>"; }).join("") + "</ul>";
    else if (d.status !== "sent" && d.status !== "outbox") h += '<ul class="checks"><li class="pass">' + icon("check") + "<span>" + t("Passed every automatic check.") + "</span></li></ul>";
    var place = [c.city, c.state || (c.country && c.country !== "MULTI" ? t(COUNTRY_NAMES[c.country] || c.country) : "")].filter(Boolean).filter(function (v, i, a) { return a.indexOf(v) === i; }).join(", ");
    var facts = [["Type", t(c.type)], ["Role", c.role], ["Responsible", c.owner], ["Region", place], ["Priority", c.priority],
      ["Relevance", c.relevance ? t(RELEVANCE_NAMES[c.relevance]) : ""], ["Relationship", c.relationship], ["Sector focus", c.sector], ["Notes", c.notes],
      ["To do", c.todos], ["Comments", (c.comments || []).join(" · ")], ["Also named", (c.others || []).join(", ")],
      ["Last written", c.last_sent ? day(c.last_sent) + (c.last_summary ? ": " + c.last_summary : "") : ""]].filter(function (f) { return f[1]; });
    var extra = Object.keys(c.extra || {});
    h += '<div class="profile"><b>' + esc(person(d)) + (c.company && person(d) !== c.company ? ", " + esc(c.company) : "") + "</b>" + (facts.length
      ? "<dl>" + facts.map(function (f) { return "<dt>" + t(f[0]) + "</dt><dd>" + esc(f[1]) + "</dd>"; }).join("") + "</dl>"
      : '<p class="soft" style="margin:6px 0 0">' + t("The list has nothing more on this person.") + "</p>") +
      (extra.length ? '<details><summary>' + tn(extra.length, "{0} more column from the list", "{0} more columns from the list") + "</summary><dl>" +
        extra.map(function (k) { return "<dt>" + esc(k) + "</dt><dd>" + esc(c.extra[k]) + "</dd>"; }).join("") + "</dl></details>" : "") +
      '<p class="soft" style="margin:8px 0 0">' + (c.sheet ? tf("Sheet “{0}”, row {1}.", esc(c.sheet), c.row) : tf("Row {0} of the list.", c.row)) + "</p></div></div>";
    return h;
  }

  function unsettled(d) { return d.checks.some(function (k) { return k.level === "fail" && (k.id === "research" || k.id === "address"); }); }

  // What Claude found online for a contact the list had no address or person for.
  function researchPanel(d, locked) {
    var r = d.research;
    if (!r || d.status === "sent" || d.status === "outbox") return "";
    var f = r.found || {};
    var h = '<div class="found ' + (r.accepted ? "taken" : r.status) + '"><div class="row">' + icon("globe", 16) + "<b>";
    if (r.status === "found" && !r.accepted) h += t("Found online, not in your list. Please check before using it.");
    else if (r.status === "found") h += r.by_hand ? t("You entered the address by hand.") : t("You chose to use what Claude found online.");
    else if (r.by_hand) h += t("You entered the address by hand.");
    else h += t("Claude found nothing reliable online.");
    h += "</b></div>";
    if (r.status === "found") {
      var who = [f.title, f.first, f.last].filter(Boolean).join(" ");
      h += "<dl>" + (who ? "<dt>" + t("Person") + "</dt><dd>" + esc(who) + (f.role ? ", " + esc(f.role) : "") + "</dd>" : "") +
        (f.email ? "<dt>" + t("Address") + "</dt><dd>" + esc(f.email) + "</dd>" : "") +
        (f.greeting ? "<dt>" + t("Greeting") + "</dt><dd>" + esc(f.greeting) + "</dd>" : "") +
        (f.source ? "<dt>" + t("Source") + '</dt><dd><a href="' + esc(/^https?:\/\//i.test(f.source) ? f.source : "#") + '" target="_blank" rel="noopener noreferrer">' + esc(f.source) + "</a></dd>" : "") +
        (f.confidence ? "<dt>" + t("How sure") + "</dt><dd>" + esc(t(CONFIDENCE[f.confidence] || f.confidence)) + "</dd>" : "") +
        (f.note ? "<dt>" + t("Note") + "</dt><dd>" + esc(f.note) + "</dd>" : "") + "</dl>";
    } else if (f.note) h += '<p class="soft" style="margin:6px 0 0">' + esc(f.note) + "</p>";
    if (!locked && !r.accepted && d.status !== "skipped") {
      h += '<div class="row" style="margin-top:10px">' + (r.status === "found" ? '<button class="btn primary small" data-action="accept-research">' + icon("check", 14) + t("Use these details") + "</button>" : "") +
        '<button class="btn small" data-action="edit-to">' + t("Enter an address myself") + '</button><button class="btn small" data-action="set" data-s="skipped">' + t("Do not write to them") + "</button></div>";
    }
    return h + "</div>";
  }
  var CONFIDENCE = { high: "Sure: named on the firm’s own website", medium: "Fairly sure", low: "Not sure: please check" };

  function modal() {
    if (!ui.confirm) return "";
    var c = ui.confirm, st = S.settings;
    var open = '<div class="dialog" role="dialog" aria-modal="true" aria-labelledby="dlg"><h2 id="dlg">';
    var cancel = '<div class="row"><button class="btn" data-action="cancel-confirm">' + t("Cancel") + "</button>";
    if (c.kind === "send") {
      var mins = Math.max(1, Math.round(c.count * (Number(st.gap_min_seconds) + Number(st.gap_max_seconds)) / 2 / 60));
      return open + tn(c.count, "Send {0} email?", "Send {0} emails?") + "</h2><p>" +
        tf("They go out from <b>{0}</b>, one at a time, over about {1}. Keep Outlook and this window open until it is done. You can stop at any point; what has left cannot be recalled.",
          esc(S.identity.email), tn(mins, "{0} minute", "{0} minutes")) + "</p>" + cancel +
        '<button class="btn primary" data-action="confirm-send">' + icon("send") + tn(c.count, "Send {0} email", "Send {0} emails") + "</button></div></div>";
    }
    if (c.kind === "auto") {
      return open + t("Send without your review?") + "</h2><p>" +
        t("On the due date the emails will go out from your mailbox by themselves. Nobody reads them first, and what has left cannot be recalled.") + "</p><p>" +
        t("Please read your master email on this page once more before you switch this on, and look at the Contacts tab to see who will be written to. An email that fails an automatic check is held back instead of being sent.") +
        "</p>" + cancel + '<button class="btn primary" data-action="confirm-auto">' + t("Send without review") + "</button></div></div>";
    }
    return open + esc(c.title) + "</h2><p>" + esc(c.text) + "</p>" + cancel + '<button class="btn primary" data-action="confirm-close">' + esc(c.button) + "</button></div></div>";
  }

  // ---- tracker ---------------------------------------------------------------

  function tracker() {
    var rounds = S.rounds.filter(function (r) { return r.sent; });
    if (!rounds.length) return empty(t("Nothing sent yet"), t("Once a round has gone out, the answers are collected here."), "");
    if (!ui.round || !rounds.some(function (r) { return r.id === ui.round; })) ui.round = rounds[0].id;
    var r = rounds.filter(function (x) { return x.id === ui.round; })[0];
    var answered = r.sent - (r.counts.no_reply || 0);
    var h = '<div class="wide"><div class="head"><div><h1>' + tf('<span class="num">{0} of {1}</span> answered', answered, r.sent) + '</h1><p class="lede">' +
      tf("{0}, sent by {1}", esc(r.label), esc(r.sender_name || r.sender)) + (S.checking.last ? ". " + tf("Inbox last read {0}", esc(moment(S.checking.last))) : "") + ".</p></div>" +
      '<a class="btn" href="/api/export?t=' + encodeURIComponent(TOKEN) + '">' + icon("download") + t("Export to Excel") + "</a>" +
      '<button class="btn primary" data-action="check"' + (S.checking.active || !S.identity.ok ? " disabled" : "") + ">" + icon("inbox") +
      (S.checking.active ? t("Reading the inbox…") : t("Check for answers")) + "</button></div>";
    var classify = S.jobs.filter(function (j) { return j.type === "classify" && j.status !== "failed"; })[0];
    if (classify) {
      var left = classify.total - classify.done;
      h += '<div class="status row">' + spark(15) + "<span>" + (S.app.claude
        ? tn(left, "Claude is reading {0} new answer…", "Claude is reading {0} new answers…")
        : tn(left, "Waiting for Claude to read {0} new answer…", "Waiting for Claude to read {0} new answers…")) + "</span></div>";
    } else if (S.checking.message && !S.checking.active) h += '<div class="status">' + esc(S.checking.message) + "</div>";

    if (rounds.length > 1) h += '<div class="rounds">' + rounds.map(function (x) {
      return '<button data-action="round" data-id="' + esc(x.id) + '" aria-pressed="' + (x.id === r.id) + '"><b>' + esc(x.label) + "</b><small>" +
        esc(x.sender_name || x.sender) + ", " + esc(day(x.created)) + ", " + tf("{0} sent", x.sent) + "</small></button>";
    }).join("") + "</div>";

    h += '<div class="bar" role="img" aria-label="' + t("Answers by outcome") + ": " + esc(OUTCOME_ORDER.filter(function (o) { return r.counts[o]; }).map(function (o) { return t(OUTCOME_NAMES[o]) + " " + r.counts[o]; }).join(", ")) + '">' +
      OUTCOME_ORDER.map(function (o) {
        return r.counts[o] ? '<i class="o-' + o + '" style="flex:' + r.counts[o] + '" title="' + t(OUTCOME_NAMES[o]) + ": " + r.counts[o] + '"></i>' : "";
      }).join("") + '</div><div class="key">' + OUTCOME_ORDER.map(function (o) {
        return '<button data-action="outcome" data-o="' + o + '" aria-pressed="' + (ui.outcome === o) + '"><i class="dot o-' + o + '"></i><b>' +
          (r.counts[o] || 0) + "</b> " + t(OUTCOME_NAMES[o]) + "</button>";
      }).join("") + "</div>";

    if (r.mine && r.kind !== "followup" && r.followups_due) {
      h += '<div class="status row"><span>' + tn(r.followups_due, "{0} person has not answered after {1}.", "{0} people have not answered after {1}.")
        .replace("{1}", tn(r.followup_after_days, "{0} day", "{0} days")) +
        '</span><span class="spacer"></span><button class="btn small" data-action="followup" data-id="' + esc(r.id) + '"' + (S.round ? ' disabled title="' + t("Finish the open round first") + '"' : "") +
        ">" + tn(r.followups_due, "Prepare {0} follow-up", "Prepare {0} follow-ups") + "</button></div>";
    }

    var rows = r.rows.filter(function (x) { return !ui.outcome || x.outcome === ui.outcome; });
    rows.sort(function (a, b) { return OUTCOME_ORDER.indexOf(a.outcome) - OUTCOME_ORDER.indexOf(b.outcome) || a.name.localeCompare(b.name); });
    h += '<div class="tablewrap"><table><thead><tr><th>' + t("Name") + "</th><th>" + t("Sent") + "</th><th>" + t("Outcome") + "</th><th>" + t("What they said") + "</th><th>" + t("Next step") + "</th></tr></thead><tbody>" +
      (rows.map(function (x) {
        var pick = r.mine ? '<select data-action="set-outcome" data-id="' + esc(x.contact_id) + '" aria-label="' + esc(tf("Outcome for {0}", x.name)) + '">' +
          OUTCOME_ORDER.map(function (o) { return '<option value="' + (o === "no_reply" ? "" : o) + '"' + (o === x.outcome ? " selected" : "") + ">" + t(OUTCOME_NAMES[o]) + "</option>"; }).join("") + "</select>"
          : '<i class="dot o-' + x.outcome + '"></i>' + t(OUTCOME_NAMES[x.outcome]);
        return "<tr><td><b>" + esc(x.name) + '</b><span class="sub">' + esc(x.company) + '</span></td><td class="fit num">' + esc(day(x.sent_at)) +
          (x.state === "outbox" ? '<span class="sub warn">' + t("in outbox") + "</span>" : "") + '</td><td class="fit">' + pick +
          (x.received ? '<span class="sub num">' + esc(day(x.received)) + (x.by_hand ? ", " + t("set by hand") : "") + "</span>" : (x.by_hand ? '<span class="sub">' + t("set by hand") + "</span>" : "")) +
          "</td><td>" + esc(x.summary) + (x.quote ? '<div class="quote">' + esc(x.quote) + "</div>" : "") + "</td><td>" + esc(x.next_step) + "</td></tr>";
      }).join("") || '<tr><td colspan="5" class="soft">' + t("Nobody with this outcome.") + "</td></tr>") + "</tbody></table></div>";
    h += '<p class="soft" style="margin-top:12px">' + t("Only each person’s first answer is read and sorted. Whoever has answered is not looked for again, and the rest of the conversation is left to you in Outlook.") + "</p>";
    var supp = Object.keys(S.suppression || {}).length;
    if (supp) h += '<p class="soft" style="margin-top:12px">' + tn(supp, "{0} person has asked not to be contacted and will not be written to again, by anyone using this list.",
      "{0} people have asked not to be contacted and will not be written to again, by anyone using this list.") + "</p>";
    return h + "</div>";
  }

  // ---- settings: saved as they change -------------------------------------------

  var timers = {};
  function patchFor(path, value) {
    var patch = {}, at = patch, parts = path.split(".");
    parts.forEach(function (p, i) { at = at[p] = (i === parts.length - 1 ? value : {}); });
    return patch;
  }
  // sync: the German version that was just finished, whose other version Claude then writes
  function saveSetting(el, sync) {
    var path = el.dataset.setting, value = el.value;
    if (el.type === "number") {
      if (value === "" || isNaN(Number(value))) return;
      value = Math.max(Number(el.min), Math.min(Number(el.max), Math.round(Number(value))));
    }
    api("/api/settings", patchFor(path, value)).then(function () {
      if (sync) return api("/api/template/sync", { key: sync });
    }).then(function () {
      var tick = document.querySelector('[data-saved="' + (el.dataset.tick || (path.indexOf("schedule") === 0 ? "schedule" : path)) + '"]');
      if (tick) { tick.classList.add("show"); setTimeout(function () { tick.classList.remove("show"); }, 1600); }
      refresh(el.type === "radio" || el.dataset.save === "change");
    }).catch(function (err) { toast(err.message); });
  }

  document.addEventListener("input", function (e) {
    var el = e.target;
    if (el.dataset.buf && ui.buf) { ui.buf[el.dataset.buf] = el.value; return; }
    if (el.dataset.note !== undefined) { ui.note = el.value; return; }
    if (el.dataset.to !== undefined) { ui.buf = { to: el.value }; return; }
    if (el.dataset.q !== undefined) {
      // the table follows the search as it is typed, and the cursor stays where it was
      ui.q = el.value; ui.showAll = false;
      var at = el.selectionStart;
      draw(true);
      var box = document.querySelector("[data-q]");
      if (box) { box.focus(); try { box.setSelectionRange(at, at); } catch (err) {} }
      return;
    }
    if (!el.dataset.setting || el.dataset.save === "change" || el.type === "radio" || el.type === "date" || el.type === "time") return;
    clearTimeout(timers[el.dataset.setting]);
    timers[el.dataset.setting] = setTimeout(function () { saveSetting(el); }, 500);
  });
  document.addEventListener("change", function (e) {
    var el = e.target;
    if (el.id === "filepick") { upload(el.files); el.value = ""; return; }
    if (el.dataset.setting) {
      clearTimeout(timers[el.dataset.setting]);
      saveSetting(el, el.dataset.sync && S.settings.sync_forms ? el.dataset.sync : "");
      return;
    }
    if (el.dataset.action === "unassigned") act("/api/settings", { unassigned_mine: el.checked });
    if (el.dataset.action === "flag") { var flag = {}; flag[el.dataset.flag] = el.checked; act("/api/settings", flag); }
    if (el.dataset.action === "override") act("/api/override", { contact_id: el.dataset.id, included: el.checked });
    if (el.dataset.action === "set-outcome") act("/api/reply/set", { round_id: ui.round, contact_id: el.dataset.id, outcome: el.value });
    if (el.dataset.action === "auto-send") {
      if (el.checked) { el.checked = false; ui.confirm = { kind: "auto" }; draw(true); }     // on only after the warning
      else act("/api/settings", { schedule: { auto_send: false } }, function () { toast(t("Reviews are back on: nothing is sent until you press Send.")); });
    }
  });
  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape" && ui.confirm) { ui.confirm = null; draw(true); }
    if (e.key === "Enter" && e.target.dataset && e.target.dataset.note !== undefined) click("send-ask", e.target);
    if (e.key === "Enter" && e.target.dataset && e.target.dataset.to !== undefined) click("save-to", e.target);
  });

  // ---- clicks ----------------------------------------------------------------

  function current() { return S.round && S.round.drafts.filter(function (d) { return d.contact_id === ui.sel; })[0]; }

  // Files picked in the browser are handed to the app, which keeps a copy in the
  // user's own folder and attaches it in Outlook when the email is sent.
  function upload(list) {
    var target = ui.attachTo;
    if (!target || !list || !list.length) return;
    var files = Array.prototype.slice.call(list);
    var big = files.filter(function (f) { return f.size > 20 * 1024 * 1024; })[0];
    if (big) { toast(tf("{0} is larger than 20 MB, too large to send by email.", big.name)); return; }
    Promise.all(files.map(function (f) {
      return new Promise(function (resolve, reject) {
        var reader = new FileReader();
        reader.onload = function () { resolve({ name: f.name, data: String(reader.result).split(",")[1] || "" }); };
        reader.onerror = function () { reject(new Error(tf("{0} could not be read.", f.name))); };
        reader.readAsDataURL(f);
      });
    })).then(function (read) {
      return act("/api/attachments/add", Object.assign({}, target, { files: read }), function () {
        toast(tn(read.length, "{0} file attached.", "{0} files attached."));
      });
    }).catch(function (err) { toast(err.message); });
  }

  function click(action, el) {
    var r = S && S.round, d = current();
    switch (action) {
      case "tab": ui.tab = el.dataset.tab; location.hash = ui.tab; draw(true); $("main").scrollTop = 0; break;
      case "language": act("/api/settings", { language: el.dataset.lang }); break;
      case "browse": act("/api/browse", {}, function (res) { if (res.path) toast(t("Contact list chosen.")); }); break;
      case "reload": act("/api/reload", {}, function () { toast(t("The list was read again.")); }); break;
      case "tpl": ui.tpl = el.dataset.key; draw(true); break;
      case "fu": ui.followup = el.dataset.on === "1"; draw(true); break;
      case "schedule-retry": act("/api/schedule/retry"); break;
      case "clear-notice": act("/api/notice/clear"); break;
      case "theme": act("/api/settings", { theme: darkWanted() ? "light" : "dark" }); break;
      case "sync-now": act("/api/template/sync", { key: el.dataset.key }); break;
      case "attach":
        ui.attachTo = el.dataset.target === "draft" ? { target: "draft", round_id: r.id, contact_id: d.contact_id } : { target: "master", kind: el.dataset.kind };
        $("filepick").click(); break;
      case "detach":
        act("/api/attachments/remove", el.dataset.target === "draft" ? { target: "draft", round_id: r.id, contact_id: d.contact_id, id: el.dataset.id }
          : { target: "master", kind: el.dataset.kind, id: el.dataset.id }); break;
      case "filters": ui.filtersOpen = !ui.filtersOpen; draw(true); break;
      case "filters-clear": act("/api/settings", { filters: { countries: [], states: [], priorities: [], relevance: [], types: [] } }); break;
      case "facet":
        var f = S.settings.filters || {}, group = el.dataset.group, list = (f[group] || []).slice(), at = list.indexOf(el.dataset.value);
        if (at >= 0) list.splice(at, 1); else list.push(el.dataset.value);
        var change = {}; change[group] = list;
        if (group === "countries") change.states = [];          // a region belongs to one country
        act("/api/settings", { filters: change }); break;
      case "show-all": ui.showAll = true; draw(true); break;
      case "skip-prepare": act("/api/round/skip-prepare", { round_id: r.id }); break;
      case "accept-research": act("/api/draft/accept-research", { round_id: r.id, contact_id: d.contact_id }, function () { toast(t("The details are used for this email. Your list is unchanged.")); }); break;
      case "edit-to": ui.editTo = d.contact_id; ui.buf = { to: d.to || ((d.research || {}).found || {}).email || "" }; draw(true);
        var to = document.querySelector("[data-to]"); if (to) to.focus(); break;
      case "cancel-to": ui.editTo = null; draw(true); break;
      case "save-to": act("/api/draft/update", { round_id: r.id, contact_id: d.contact_id, change: { to: (ui.buf || {}).to || "" } }, function () { ui.editTo = null; }); break;
      case "confirm-auto": ui.confirm = null; act("/api/settings", { schedule: { auto_send: true } }); break;
      case "cfilter": ui.contactFilter = el.dataset.f; draw(true); break;
      case "type": ui.type = ui.type === el.dataset.type ? "" : el.dataset.type; draw(true); break;
      case "start-round": act("/api/round/start", {}, function () { ui.tab = "review"; location.hash = "review"; ui.sel = null; }); break;
      case "filter": ui.filter = el.dataset.f; draw(true); break;
      case "select": ui.sel = el.dataset.id; ui.editing = ui.asking = ui.editTo = null; draw(true); break;
      case "set": act("/api/draft/update", { round_id: r.id, contact_id: d.contact_id, change: { status: el.dataset.s } }, function () {
        if (el.dataset.s !== "pending") {            // move on to the next one that needs a decision
          var rest = r.drafts.filter(function (x) { return x.status === "pending" && x.contact_id !== d.contact_id; });
          if (rest.length) ui.sel = rest[0].contact_id;
        }
      }); break;
      case "approve-all": act("/api/draft/approve-all", { round_id: r.id }, function (res) {
        if (res.left) toast(tn(res.left, "{0} email with a failed check was left for you to look at.", "{0} emails with a failed check were left for you to look at."));
      }); break;
      case "edit": ui.editing = d.contact_id; ui.buf = { subject: d.subject, body: d.body }; ui.asking = null; draw(true); break;
      case "cancel-edit": ui.editing = null; draw(true); break;
      case "save-edit": act("/api/draft/update", { round_id: r.id, contact_id: ui.editing, change: ui.buf }, function () { ui.editing = null; }); break;
      case "reset": act("/api/draft/update", { round_id: r.id, contact_id: d.contact_id, change: { reset: true } }); break;
      case "ask": ui.asking = d.contact_id; ui.note = ""; draw(true);
        var box = document.querySelector("[data-note]"); if (box) box.focus(); break;
      case "cancel-ask": ui.asking = null; draw(true); break;
      case "send-ask": act("/api/draft/redraft", { round_id: r.id, contact_id: ui.asking, note: ui.note }, function () { ui.asking = null; }); break;
      case "test": act("/api/send", { round_id: r.id, ids: [d.contact_id], test: true }, function () { toast(tf("A test is on its way to {0}.", S.identity.email)); }); break;
      case "ask-send": ui.confirm = { kind: "send", count: r.drafts.filter(function (x) { return x.status === "approved"; }).length }; draw(true); break;
      case "confirm-send":
        ui.confirm = null;
        act("/api/send", { round_id: r.id, confirm: true, ids: r.drafts.filter(function (x) { return x.status === "approved"; }).map(function (x) { return x.contact_id; }) });
        break;
      case "stop": act("/api/send/stop"); break;
      case "close-round":
        var sent = r.drafts.some(function (x) { return x.status === "sent"; });
        ui.confirm = sent
          ? { kind: "close", title: t("Close this round?"), button: t("Close this round"), text: t("Emails already sent stay in the tracker. The ones not sent are dropped.") }
          : { kind: "close", title: t("Discard this round?"), button: t("Discard this round"), text: t("All emails of this round are dropped. Nothing has been sent.") };
        draw(true); break;
      case "confirm-close": ui.confirm = null; act("/api/round/close", { round_id: r.id }, function () { ui.sel = null; }); break;
      case "cancel-confirm": ui.confirm = null; draw(true); break;
      case "check": act("/api/replies/check"); break;
      case "round": ui.round = el.dataset.id; ui.outcome = ""; draw(true); break;
      case "outcome": ui.outcome = ui.outcome === el.dataset.o ? "" : el.dataset.o; draw(true); break;
      case "followup": act("/api/followup/start", { round_id: el.dataset.id }, function () { ui.tab = "review"; location.hash = "review"; ui.sel = null; }); break;
    }
  }
  document.addEventListener("click", function (e) {
    var el = e.target.closest("[data-action]");
    if (!el || el.disabled || el.tagName === "SELECT" || el.type === "checkbox") return;
    click(el.dataset.action, el);
  });
  window.addEventListener("hashchange", function () {
    var tab = location.hash.replace("#", "");
    if (tab && tab !== ui.tab && TABS.some(function (x) { return x[0] === tab; })) { ui.tab = tab; draw(true); }
  });

  refresh(true);
  setInterval(refresh, 1500);
})();
