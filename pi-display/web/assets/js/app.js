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

  // ---------------------------------------------------------------- Layout & Ruhemodus
  // Hochformat: per Config erzwungen oder (auto) wenn der Bildschirm höher als breit ist.
  // Die Breitengrenze verhindert, dass Handys im Hochformat das Kiosk-Layout bekommen.
  function applyLayout() {
    var mode = (state && state.ui && state.ui.layout) || "auto";
    var portrait = mode === "portrait" ||
      (mode === "auto" && window.innerHeight > window.innerWidth && window.innerWidth >= 900);
    document.body.classList.toggle("is-portrait", portrait);
  }

  // Ruhemodus: ohne Verbindung zum PC nur Uhr und Datum zentriert (Hochformat, siehe style.css)
  function renderIdle() {
    var connected = serverReachable && state && state.link && state.link.connected;
    document.body.classList.toggle("is-idle", !connected);
  }

  // ---------------------------------------------------------------- Musik
  var STATUS = {
    playing: { icon: "play-fill", text: "Wiedergabe" },
    paused: { icon: "pause-fill", text: "Pausiert" },
    stopped: { icon: "stop-fill", text: "Gestoppt" }
  };

  function renderMedia() {
    var media = state.media || {};
    var connected = serverReachable && state.link && state.link.connected;
    var show = connected && media.active;

    $("media-body").hidden = !show;
    $("media-empty").hidden = show;
    if (!show) {
      setText("media-empty", !serverReachable ? "Anzeige-Dienst nicht erreichbar"
        : connected ? "Keine Wiedergabe aktiv" : "Keine Verbindung zum PC");
      return;
    }

    // Statuszeile: "▶ Spotify" bzw. "⏸ Pausiert · Spotify"
    var st = STATUS[media.status] || STATUS.stopped;
    var label = media.status === "playing" && media.source_app ? media.source_app
      : st.text + (media.source_app ? " · " + media.source_app : "");
    var status = $("media-status");
    status.querySelector(".bi").className = "bi bi-" + st.icon;
    setText("media-status-text", label);

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

    list.textContent = "";

    // Keine (weiteren) Termine oder kein Kalender: Bereich ganz ausblenden, keine Meldung
    document.body.classList.toggle("no-events", !upcoming.length);
    if (!upcoming.length) { return; }

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

  // ---------------------------------------------------------------- Wetter (vom PC, Open-Meteo)
  // WMO-Wettercodes -> [Icon Tag, Icon Nacht, Text]
  var WEATHER = [
    [[0], "sun", "moon-stars", "Klar"],
    [[1], "sun", "moon", "Überwiegend klar"],
    [[2], "cloud-sun", "cloud-moon", "Teilweise bewölkt"],
    [[3], "clouds", "clouds", "Bedeckt"],
    [[45, 48], "cloud-fog", "cloud-fog", "Nebel"],
    [[51, 53, 55, 56, 57], "cloud-drizzle", "cloud-drizzle", "Nieselregen"],
    [[61, 80], "cloud-rain", "cloud-rain", "Leichter Regen"],
    [[63, 66, 81], "cloud-rain", "cloud-rain", "Regen"],
    [[65, 67, 82], "cloud-rain-heavy", "cloud-rain-heavy", "Starker Regen"],
    [[71, 73, 75, 77, 85, 86], "cloud-snow", "cloud-snow", "Schnee"],
    [[95, 96, 99], "cloud-lightning-rain", "cloud-lightning-rain", "Gewitter"]
  ];
  var MAX_AGE_MS = 3 * 3600 * 1000;   // ältere Daten (PC lange offline) nicht mehr zeigen

  function fresh(part) {
    return part && state.link && state.link.connected && serverNow() - part.received_ms < MAX_AGE_MS;
  }

  function deg(value) { return Math.round(value) + "°"; }

  function renderWeather() {
    var w = state.weather;
    $("weather").hidden = !fresh(w);
    if (!fresh(w)) { return; }
    var entry = WEATHER.filter(function (e) { return e[0].indexOf(w.code) !== -1; })[0] || [[], "cloud", "cloud", ""];
    $("weather-icon").className = "bi bi-" + (w.is_day ? entry[1] : entry[2]);
    setText("weather-temp", deg(w.temp));
    var parts = [entry[3]];
    if (w.t_max !== null && w.t_min !== null) { parts.push(deg(w.t_min) + " / " + deg(w.t_max)); }
    if (w.place) { parts.push(w.place); }
    setText("weather-text", parts.filter(Boolean).join(" · "));
  }

  // ---------------------------------------------------------------- Schlagzeilen (vom PC, RSS)
  var newsIndex = 0;
  var newsShownAt = 0;
  var newsStamp = null;      // received_ms der angezeigten Schlagzeilen

  function tickNews(force) {
    var news = state && state.news;
    var items = fresh(news) ? news.items : [];
    $("news").hidden = !items.length;
    document.body.classList.toggle("has-news", items.length > 0);
    if (!items.length) { return; }
    if (news.received_ms !== newsStamp) {   // neue Schlagzeilen -> von vorne beginnen
      newsStamp = news.received_ms;
      newsIndex = 0;
      force = true;
    }
    var seconds = (state.ui && state.ui.news_seconds) || 12;
    if (!force && Date.now() - newsShownAt < seconds * 1000) { return; }
    if (!force) { newsIndex += 1; }
    newsIndex = newsIndex % items.length;
    newsShownAt = Date.now();
    var line = $("news").querySelector(".news-line");
    line.classList.remove("is-visible");
    // kurz ausblenden, dann neue Schlagzeile einblenden
    setTimeout(function () {
      var item = items[newsIndex % items.length];
      if (!item) { return; }
      setText("news-source", item.source || "");
      setText("news-title", item.title);
      line.classList.add("is-visible");
    }, force ? 0 : 400);
  }

  // ---------------------------------------------------------------- Datenempfang
  function applyState(snapshot) {
    state = snapshot;
    serverReachable = true;
    if (typeof snapshot.server_now_ms === "number") { clockOffset = snapshot.server_now_ms - Date.now(); }
    applyLayout();
    renderIdle();
    renderMedia();
    renderCalendar();
    renderWeather();
    tickNews(false);
  }

  function markUnreachable() {
    serverReachable = false;
    renderIdle();
    if (state) { renderMedia(); }
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
    if (/[?&]kiosk=1\b/.test(window.location.search)) { document.body.classList.add("kiosk"); }
    applyLayout();
    renderIdle();
    window.addEventListener("resize", applyLayout);
    tickClock();
    setInterval(tickClock, 1000);
    setInterval(tickProgress, 250);
    setInterval(function () { if (state) { renderCalendar(); tickNews(false); } }, 1000);
    connect();
  });
})();
