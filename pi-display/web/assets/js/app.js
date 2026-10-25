/* InfoDisplay – Anzeige-Logik
   Empfängt den Zustand per Server-Sent Events (/api/events) und rendert
   Musik, Uhr und Termine. Texte werden ausschließlich über textContent gesetzt. */
(function () {
  "use strict";

  var LOCALE = "de-AT";
  var state = null;          // letzter Zustand vom Server
  var clockOffset = 0;       // Server-Uhr minus Browser-Uhr (ms)
  var serverReachable = false;

  var $ = function (id) { return document.getElementById(id); };

  // ---------------------------------------------------------------- Hilfen
  function serverNow() { return Date.now() + clockOffset; }

  function pad(n) { return n < 10 ? "0" + n : String(n); }

  function formatDuration(ms) {
    var total = Math.max(0, Math.floor(ms / 1000));
    var h = Math.floor(total / 3600);
    var m = Math.floor((total % 3600) / 60);
    var s = total % 60;
    return h > 0 ? h + ":" + pad(m) + ":" + pad(s) : m + ":" + pad(s);
  }

  // "2026-10-25T14:30" als lokale Zeit interpretieren
  function parseLocal(iso) {
    var p = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})/.exec(iso || "");
    return p ? new Date(+p[1], +p[2] - 1, +p[3], +p[4], +p[5]) : null;
  }

  function dayKey(d) { return d.getFullYear() + "-" + d.getMonth() + "-" + d.getDate(); }

  function timeText(d) { return pad(d.getHours()) + ":" + pad(d.getMinutes()); }

  function el(tag, className, text) {
    var node = document.createElement(tag);
    if (className) { node.className = className; }
    if (text !== undefined) { node.textContent = text; }
    return node;
  }

  function icon(name) {
    var i = el("i", "bi bi-" + name);
    i.setAttribute("aria-hidden", "true");
    return i;
  }

  function setText(id, text) {
    var node = $(id);
    if (node && node.textContent !== text) { node.textContent = text; }
  }

  // ---------------------------------------------------------------- Kopf & Fuß
  function renderChrome() {
    var ui = state.ui || {};
    setText("app-title", ui.title || "Info-Display");
    document.title = ui.title || "Info-Display";
    setText("app-version", "v" + ((state.app && state.app.version) || "?"));
    if (ui.logo && /^[\w\-./]+\.(svg|png|jpe?g)$/i.test(ui.logo) && ui.logo.indexOf("..") === -1) {
      var logo = $("brand-logo");
      if (logo.getAttribute("src") !== ui.logo) { logo.setAttribute("src", ui.logo); }
    }
    if (window.InfoTheme) { window.InfoTheme.setDefault(ui.default_theme || "auto"); }
  }

  function renderLink() {
    var chip = $("link-status");
    var text = chip.querySelector(".status-text");
    var link = state ? state.link : null;
    var cls, label;
    if (!serverReachable) {
      cls = "is-warn"; label = "Anzeige-Dienst nicht erreichbar";
    } else if (link && link.connected) {
      cls = "is-on"; label = "Verbunden" + (link.client ? " – " + link.client : "");
    } else {
      cls = "is-off"; label = "Keine Verbindung";
    }
    chip.className = "status-chip " + cls;
    text.textContent = label;
    setText("footer-client", link && link.client ? "Sender: " + link.client : "");
  }

  function renderFooterAge() {
    var link = state && state.link;
    if (!link || !link.last_message_ms) { setText("footer-last", "Noch keine Daten empfangen"); return; }
    var age = Math.max(0, Math.round((serverNow() - link.last_message_ms) / 1000));
    var label = age < 5 ? "gerade eben" : age < 120 ? "vor " + age + " s" : "vor " + Math.round(age / 60) + " min";
    setText("footer-last", "Letzte Daten: " + label);
  }

  // ---------------------------------------------------------------- Musik
  var STATUS = {
    playing: { icon: "play-fill", text: "Wiedergabe", cls: "badge is-playing" },
    paused: { icon: "pause-fill", text: "Pausiert", cls: "badge" },
    stopped: { icon: "stop-fill", text: "Gestoppt", cls: "badge" }
  };

  function renderMedia() {
    var media = state.media || {};
    var connected = state.link && state.link.connected;
    var show = connected && media.active;

    $("media-body").hidden = !show;
    $("media-empty").hidden = show;
    $("media-source").hidden = !show || !media.source_app;
    if (!show) {
      $("media-empty-icon").className = "bi " + (connected ? "bi-pause-circle" : "bi-bluetooth");
      setText("media-empty-text", connected ? "Keine Wiedergabe aktiv" : "Keine Verbindung zum PC");
      return;
    }

    $("media-source").querySelector("span").textContent = media.source_app || "";
    var st = STATUS[media.status] || STATUS.stopped;
    var badge = $("media-status");
    badge.className = st.cls;
    badge.querySelector(".bi").className = "bi bi-" + st.icon;
    badge.querySelector("span").textContent = st.text;

    setText("media-title", media.title || "Unbekannter Titel");
    setText("media-artist", media.artist || "");
    setText("media-album", media.album || "");
    $("media-artist").hidden = !media.artist;
    $("media-album").hidden = !media.album;

    var img = $("cover-img");
    if (media.cover_url) {
      if (img.getAttribute("src") !== media.cover_url) {
        img.onload = function () { img.hidden = false; $("cover-placeholder").hidden = true; };
        img.onerror = function () { img.hidden = true; $("cover-placeholder").hidden = false; };
        img.setAttribute("src", media.cover_url);
      }
    } else {
      img.hidden = true;
      img.removeAttribute("src");
      $("cover-placeholder").hidden = false;
    }

    $("media-progress").hidden = !(media.duration_ms > 0);
    tickProgress();
  }

  function tickProgress() {
    if (!state || !state.media || !state.media.active || !(state.media.duration_ms > 0)) { return; }
    var m = state.media;
    var pos = m.position_ms || 0;
    if (m.status === "playing" && m.anchor_ms) { pos += serverNow() - m.anchor_ms; }
    pos = Math.min(Math.max(0, pos), m.duration_ms);
    var pct = (pos / m.duration_ms) * 100;
    $("progress-fill").style.width = pct.toFixed(2) + "%";
    $("media-progress").querySelector(".progress").setAttribute("aria-valuenow", Math.round(pct));
    setText("time-pos", formatDuration(pos));
    setText("time-dur", formatDuration(m.duration_ms));
  }

  // ---------------------------------------------------------------- Uhr
  var dateFormat = new Intl.DateTimeFormat(LOCALE, { weekday: "long", day: "numeric", month: "long", year: "numeric" });

  function tickClock() {
    var now = new Date();
    var node = $("clock-time");
    var showSec = !state || !state.ui || state.ui.show_seconds !== false;
    var main = timeText(now);
    if (node.dataset.value !== main + (showSec ? now.getSeconds() : "")) {
      node.dataset.value = main + (showSec ? now.getSeconds() : "");
      node.textContent = main;
      if (showSec) { node.appendChild(el("span", "sec", pad(now.getSeconds()))); }
    }
    setText("clock-date", dateFormat.format(now));
  }

  // ---------------------------------------------------------------- Termine
  var dayFormat = new Intl.DateTimeFormat(LOCALE, { weekday: "long", day: "numeric", month: "long" });
  var lastCalendarRender = "";

  function dayLabel(date, now) {
    var today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
    var diff = Math.round((new Date(date.getFullYear(), date.getMonth(), date.getDate()) - today) / 86400000);
    if (diff === 0) { return "Heute"; }
    if (diff === 1) { return "Morgen"; }
    return dayFormat.format(date);
  }

  function renderCalendar() {
    var cal = state && state.calendar;
    var list = $("calendar-list");
    var now = new Date();
    var events = (cal && cal.events) || [];

    var upcoming = events
      .map(function (e) { return { e: e, start: parseLocal(e.start), end: parseLocal(e.end) }; })
      .filter(function (x) { return x.start && x.end && x.end > now; });

    // Nur neu zeichnen, wenn sich etwas geändert hat (Daten oder Minute)
    var signature = JSON.stringify(events) + "|" + timeText(now) + "|" + (cal && cal.received_ms);
    if (signature === lastCalendarRender) { return; }
    lastCalendarRender = signature;

    setText("calendar-stand", cal && cal.received_ms ? "Stand " + timeText(new Date(cal.received_ms)) : "");
    list.textContent = "";

    if (!upcoming.length) {
      list.hidden = true;
      $("calendar-empty").hidden = false;
      setText("calendar-empty-text", cal && cal.events ? "Keine weiteren Termine" : "Noch keine Kalenderdaten");
      return;
    }
    list.hidden = false;
    $("calendar-empty").hidden = true;

    var lastDay = null;
    upcoming.forEach(function (x) {
      var key = dayKey(x.start < now ? now : x.start);
      if (key !== lastDay) {
        lastDay = key;
        list.appendChild(el("li", "event-day", dayLabel(x.start < now ? now : x.start, now)));
      }
      var running = x.start <= now && x.end > now;
      var li = el("li", "event" + (running ? " is-now" : ""));

      var time = el("div", "event-time");
      if (x.e.all_day) {
        time.textContent = "Ganztägig";
      } else {
        time.textContent = timeText(x.start);
        time.appendChild(el("small", null, "bis " + timeText(x.end)));
      }

      var body = el("div", "event-body");
      var subject = el("div", "event-subject", x.e.subject);
      if (running) { subject.appendChild(el("span", "event-now", "Jetzt")); }
      body.appendChild(subject);
      if (x.e.location) {
        var meta = el("div", "event-meta");
        meta.appendChild(icon("geo-alt"));
        meta.appendChild(el("span", null, x.e.location));
        body.appendChild(meta);
      }
      li.appendChild(time);
      li.appendChild(body);
      list.appendChild(li);
    });
  }

  // ---------------------------------------------------------------- Datenempfang
  function applyState(snapshot) {
    state = snapshot;
    serverReachable = true;
    if (typeof snapshot.server_now_ms === "number") { clockOffset = snapshot.server_now_ms - Date.now(); }
    renderChrome();
    renderLink();
    renderMedia();
    renderCalendar();
    renderFooterAge();
  }

  function markUnreachable() {
    serverReachable = false;
    if (state) { renderLink(); }
    else { renderLinkWithoutState(); }
  }

  function renderLinkWithoutState() {
    var chip = $("link-status");
    chip.className = "status-chip is-warn";
    chip.querySelector(".status-text").textContent = "Anzeige-Dienst nicht erreichbar";
  }

  function poll() {
    fetch("/api/state", { cache: "no-store" })
      .then(function (r) { if (!r.ok) { throw new Error(r.status); } return r.json(); })
      .then(applyState)
      .catch(markUnreachable);
  }

  function connect() {
    if (!window.EventSource) {
      poll();
      setInterval(poll, 2000);
      return;
    }
    var source = new EventSource("/api/events");
    source.addEventListener("state", function (ev) {
      try { applyState(JSON.parse(ev.data)); } catch (e) { /* defekte Nachricht ignorieren */ }
    });
    source.onerror = function () {
      markUnreachable();
      // EventSource verbindet sich selbst neu; bei endgültigem Abbruch neu aufbauen
      if (source.readyState === EventSource.CLOSED) { setTimeout(connect, 5000); }
    };
  }

  document.addEventListener("DOMContentLoaded", function () {
    tickClock();
    setInterval(tickClock, 1000);
    setInterval(tickProgress, 250);
    setInterval(function () { if (state) { renderCalendar(); renderFooterAge(); } }, 1000);
    connect();
  });
})();
