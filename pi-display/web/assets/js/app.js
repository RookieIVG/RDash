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

  // Ruhemodus: ohne Verbindung zum PC nur Uhr und Datum als Bildschirmschoner (siehe style.css)
  function renderIdle() {
    var connected = serverReachable && state && state.link && state.link.connected;
    document.body.classList.toggle("is-idle", !connected);
    if (!connected) { startSaver(); }
  }

  // ---------------------------------------------------------------- Bildschirmschoner
  // Uhr und Datum wandern langsam schräg über den Bildschirm und prallt an den Rändern ab
  // (wie das bekannte DVD-Logo). Schont den Monitor vor eingebrannten Bildern.
  var saver = { x: 0, y: 0, vx: 1, vy: 1, last: 0, running: false };

  function startSaver() {
    if (saver.running) { return; }
    var node = $("saver-box");
    saver.running = true;
    saver.last = 0;
    saver.x = Math.random() * Math.max(0, window.innerWidth - node.offsetWidth);
    saver.y = Math.random() * Math.max(0, window.innerHeight - node.offsetHeight);
    saver.vx = Math.random() < 0.5 ? -1 : 1;
    saver.vy = Math.random() < 0.5 ? -1 : 1;
    window.requestAnimationFrame(saverFrame);
  }

  function saverFrame(ts) {
    if (!document.body.classList.contains("is-idle")) { saver.running = false; return; }
    var speed = (state && state.ui && state.ui.saver_speed) || 40;    // Pixel pro Sekunde
    var dt = saver.last ? Math.min(0.1, (ts - saver.last) / 1000) : 0;
    saver.last = ts;
    var node = $("saver-box");
    var maxX = Math.max(0, window.innerWidth - node.offsetWidth);
    var maxY = Math.max(0, window.innerHeight - node.offsetHeight);
    saver.x += saver.vx * speed * dt;
    saver.y += saver.vy * speed * dt;
    if (saver.x <= 0) { saver.x = 0; saver.vx = 1; } else if (saver.x >= maxX) { saver.x = maxX; saver.vx = -1; }
    if (saver.y <= 0) { saver.y = 0; saver.vy = 1; } else if (saver.y >= maxY) { saver.y = maxY; saver.vy = -1; }
    node.style.transform = "translate3d(" + saver.x.toFixed(1) + "px," + saver.y.toFixed(1) + "px,0)";
    window.requestAnimationFrame(saverFrame);
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
    if (!show) { setBackground("", null); }
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
        img.onload = function () { img.hidden = false; $("cover-placeholder").hidden = true; coverBackground(); };
        img.onerror = function () { img.hidden = true; $("cover-placeholder").hidden = false; setBackground("", null); };
        img.setAttribute("src", media.cover_url);
      } else {
        coverBackground();
      }
    } else {
      img.hidden = true;
      img.removeAttribute("src");
      $("cover-placeholder").hidden = false;
      setBackground("", null);
    }

    $("media-progress").hidden = !(media.duration_ms > 0);
    tickProgress();
  }

  // ---------------------------------------------------------------- Hintergrund passend zum Cover
  // Aus dem Cover werden ein Grundton und die kräftigste Farbe gewonnen, stark abgedunkelt
  // (weiße Schrift bleibt gut lesbar) und als Verlauf hinterlegt. Sonst: schwarz.
  var bgKey = "";              // aktuell gezeigter Hintergrund ("" = schwarz)
  var bgTop = 0;               // Index der oberen Ebene
  var coverCache = { src: null, colors: null };

  function setBackground(key, css) {
    if (key === bgKey) { return; }
    bgKey = key;
    var layers = $("bg").children;
    var next = layers[1 - bgTop];
    var prev = layers[bgTop];
    bgTop = 1 - bgTop;
    // neue Ebene unsichtbar nach oben legen und einblenden; die alte bleibt darunter stehen
    next.style.transition = "none";
    next.style.opacity = "0";
    next.style.background = css || "#000";
    next.style.zIndex = "2";
    prev.style.zIndex = "1";
    void next.offsetWidth;     // Neuberechnung erzwingen, damit die Überblendung startet
    next.style.transition = "";
    next.style.opacity = "1";
  }

  function rgbToHsl(r, g, b) {
    r /= 255; g /= 255; b /= 255;
    var max = Math.max(r, g, b), min = Math.min(r, g, b), l = (max + min) / 2, h = 0, s = 0;
    if (max !== min) {
      var d = max - min;
      s = l > 0.5 ? d / (2 - max - min) : d / (max + min);
      h = max === r ? (g - b) / d + (g < b ? 6 : 0) : max === g ? (b - r) / d + 2 : (r - g) / d + 4;
      h *= 60;
    }
    return [h, s, l];
  }

  function hsl(c) { return "hsl(" + Math.round(c[0]) + "," + Math.round(c[1] * 100) + "%," + Math.round(c[2] * 100) + "%)"; }

  // Liefert [kräftigste Farbe, Grundton] als HSL oder null
  function coverColors(img) {
    var size = 24;
    var canvas = document.createElement("canvas");
    canvas.width = canvas.height = size;
    var ctx = canvas.getContext("2d");
    ctx.drawImage(img, 0, 0, size, size);
    var data = ctx.getImageData(0, 0, size, size).data;
    var total = [0, 0, 0], buckets = [];
    for (var i = 0; i < data.length; i += 4) {
      var r = data[i], g = data[i + 1], b = data[i + 2];
      total[0] += r; total[1] += g; total[2] += b;
      var c = rgbToHsl(r, g, b);
      if (c[1] < 0.2 || c[2] < 0.1 || c[2] > 0.9) { continue; }   // Grau, Schwarz, Weiß zählen nicht
      var k = Math.floor(c[0] / 30) % 12;                          // 12 Farbbereiche
      var bucket = buckets[k] || (buckets[k] = { w: 0, r: 0, g: 0, b: 0 });
      var w = c[1] * (1 - Math.abs(c[2] - 0.5));                   // kräftige, mittlere Farben wiegen mehr
      bucket.w += w; bucket.r += r * w; bucket.g += g * w; bucket.b += b * w;
    }
    var n = data.length / 4;
    var base = rgbToHsl(total[0] / n, total[1] / n, total[2] / n);
    var best = buckets.reduce(function (a, x) { return x && (!a || x.w > a.w) ? x : a; }, null);
    var accent = best ? rgbToHsl(best.r / best.w, best.g / best.w, best.b / best.w) : base;
    // abdunkeln: Farbe max. 30 % Helligkeit, Grundton max. 12 %
    return [[accent[0], Math.min(accent[1], 0.75), Math.min(Math.max(accent[2], 0.18), 0.3)],
            [base[0], Math.min(base[1], 0.6), Math.min(base[2], 0.12)]];
  }

  function coverBackground() {
    var img = $("cover-img");
    var enabled = !state.ui || state.ui.cover_background !== false;
    if (!enabled || img.hidden || !img.complete || !img.naturalWidth) { setBackground("", null); return; }
    var src = img.getAttribute("src");
    if (coverCache.src !== src) {
      try { coverCache = { src: src, colors: coverColors(img) }; }
      catch (e) { coverCache = { src: src, colors: null }; }
    }
    if (!coverCache.colors) { setBackground("", null); return; }
    // Farbschwerpunkt dort, wo das Cover steht (links im Querformat, unten im Hochformat)
    var rect = img.getBoundingClientRect();
    var x = Math.round((rect.left + rect.width / 2) / window.innerWidth * 100);
    var y = Math.round((rect.top + rect.height / 2) / window.innerHeight * 100);
    var accent = hsl(coverCache.colors[0]), base = hsl(coverCache.colors[1]);
    setBackground(src + "|" + x + "|" + y,
      "radial-gradient(120% 110% at " + x + "% " + y + "%, " + accent + " 0%, " + base + " 60%, #000 100%)");
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

  function renderTime(node, now, showSec) {
    var main = timeText(now);
    var value = main + (showSec ? now.getSeconds() : "");
    if (node.dataset.value === value) { return; }
    node.dataset.value = value;
    node.textContent = main;
    if (showSec) { node.appendChild(el("span", "sec", pad(now.getSeconds()))); }
  }

  function tickClock() {
    var now = new Date();
    var showSec = !state || !state.ui || state.ui.show_seconds !== false;
    renderTime($("clock-time"), now, showSec);
    renderTime($("saver-time"), now, showSec);
    setText("clock-date", dateFormat.format(now));
    setText("saver-date", dateFormat.format(now));
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

    eventCount = upcoming.length;
    list.textContent = "";
    renderNextEvent(upcoming, now);
    arrange();
    // Keine (weiteren) Termine oder kein Kalender: Bereich bleibt ausgeblendet, keine Meldung
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

  // Kleine Leiste unten (wenn die Schlagzeilen groß sind): laufender bzw. nächster Termin
  function renderNextEvent(upcoming, now) {
    var x = upcoming[0];
    if (!x) { return; }
    var running = x.start <= now;
    var when = running ? "Jetzt" : dayLabel(x.start, now) + (x.e.all_day ? "" : " " + timeText(x.start));
    if (running && !x.e.all_day) { when += " bis " + timeText(x.end); }
    setText("next-when", when);
    setText("next-subject", x.e.subject);
    setText("next-location", x.e.location || "");
    $("next-location").hidden = !x.e.location;
    setText("next-more", upcoming.length > 1 ? "+" + (upcoming.length - 1) + " weitere" : "");
  }

  // ---------------------------------------------------------------- Anordnung: was ist groß, was klein?
  // [ui] focus = calendar | news. Fehlt der Inhalt für den großen Bereich, übernimmt der andere.
  var eventCount = 0;

  function newsItems() {
    var news = state && state.news;
    return fresh(news) ? news.items : [];
  }

  function arrange() {
    if (!state) { return; }
    var hasNews = newsItems().length > 0;
    var hasEvents = eventCount > 0;
    // Hochformat: Mitte immer Schlagzeilen (Termine nur, wenn es keine gibt)
    var portrait = document.body.classList.contains("is-portrait");
    var focus = portrait || (state.ui && state.ui.focus) === "news" ? "news" : "calendar";
    if (focus === "news" && !hasNews) { focus = "calendar"; }
    if (focus === "calendar" && !hasEvents && hasNews) { focus = "news"; }

    var bigCalendar = focus === "calendar" && hasEvents;
    var bigNews = focus === "news" && hasNews;
    var smallNews = focus === "calendar" && hasNews;
    var smallCalendar = focus === "news" && hasEvents;

    var wasBigNews = !$("headlines").hidden;
    $("calendar").hidden = !bigCalendar;
    $("headlines").hidden = !bigNews;
    $("news").hidden = !smallNews;
    $("next-event").hidden = !smallCalendar;
    document.body.classList.toggle("no-events", !bigCalendar && !bigNews);   // kein großer Bereich
    document.body.classList.toggle("has-news", smallNews || smallCalendar);  // Leiste unten
    if (bigNews && !wasBigNews) { renderHeadlines(false); }
  }

  // ---------------------------------------------------------------- Wetter (vom PC, Open-Meteo)
  // WMO-Wettercodes -> [Codes, Icon Tag, Icon Nacht, Text]; Icons: Meteocons (animiert, lokal)
  var WEATHER = [
    [[0], "clear-day", "clear-night", "Klar"],
    [[1], "partly-cloudy-day", "partly-cloudy-night", "Überwiegend klar"],
    [[2], "partly-cloudy-day", "partly-cloudy-night", "Teilweise bewölkt"],
    [[3], "overcast", "overcast", "Bedeckt"],
    [[45, 48], "fog-day", "fog-night", "Nebel"],
    [[51, 53, 55], "drizzle", "drizzle", "Nieselregen"],
    [[56, 57, 66, 67], "sleet", "sleet", "Gefrierender Regen"],
    [[61, 80], "rain", "rain", "Leichter Regen"],
    [[63, 81], "rain", "rain", "Regen"],
    [[65, 82], "extreme-rain", "extreme-rain", "Starker Regen"],
    [[71, 73, 77, 85], "snow", "snow", "Schnee"],
    [[75, 86], "extreme-snow", "extreme-snow", "Starker Schneefall"],
    [[95], "thunderstorms-rain", "thunderstorms-rain", "Gewitter"],
    [[96, 99], "thunderstorms-extreme-rain", "thunderstorms-extreme-rain", "Gewitter mit Hagel"]
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
    var entry = WEATHER.filter(function (e) { return e[0].indexOf(w.code) !== -1; })[0] ||
      [[], "not-available", "not-available", ""];
    var src = "assets/vendor/meteocons/" + (w.is_day ? entry[1] : entry[2]) + ".svg";
    var img = $("weather-icon");
    if (img.getAttribute("src") !== src) { img.setAttribute("src", src); }   // sonst startet die Animation neu
    setText("weather-temp", deg(w.temp));
    var parts = [entry[3]];
    if (w.t_max !== null && w.t_min !== null) { parts.push(deg(w.t_min) + " / " + deg(w.t_max)); }
    if (w.place) { parts.push(w.place); }
    setText("weather-text", parts.filter(Boolean).join(" · "));
  }

  // ---------------------------------------------------------------- Schlagzeilen (vom PC, RSS/Atom)
  var newsIndex = 0;
  var newsShownAt = 0;
  var newsStamp = null;      // received_ms der angezeigten Schlagzeilen
  var pageStart = 0;         // Großansicht: erste Schlagzeile der aktuellen Seite
  var pageCount = 0;         // Großansicht: Anzahl Schlagzeilen, die auf die Seite passen
  var pageShownAt = 0;

  function tickNews() {
    if (!state) { return; }
    var items = newsItems();
    var news = state.news;
    var changed = items.length && news.received_ms !== newsStamp;
    if (changed) {                            // neue Schlagzeilen -> von vorne beginnen
      newsStamp = news.received_ms;
      newsIndex = 0;
      pageStart = 0;
    }
    arrange();
    if (!items.length) { return; }
    var ui = state.ui || {};
    if (!$("news").hidden) { tickTicker(items, changed, (ui.news_seconds || 12) * 1000); }
    if (!$("headlines").hidden && (changed || Date.now() - pageShownAt >= (ui.news_page_seconds || 30) * 1000)) {
      renderHeadlines(!changed);
    }
  }

  // Klein: eine Schlagzeile nach der anderen in der Leiste unten
  function tickTicker(items, force, interval) {
    if (!force && Date.now() - newsShownAt < interval) { return; }
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

  // Groß: so viele Schlagzeilen (mit Text) wie Platz haben, seitenweise weiterblättern
  function renderHeadlines(advance) {
    var items = newsItems();
    var list = $("headlines-list");
    if (!items.length) { return; }
    if (advance && pageCount < items.length) { pageStart = (pageStart + pageCount) % items.length; }
    if (pageCount >= items.length) { pageStart = 0; }
    pageShownAt = Date.now();
    list.textContent = "";
    pageCount = 0;
    for (var n = 0; n < items.length; n++) {
      var item = items[(pageStart + n) % items.length];
      var li = el("li", "headline");
      if (item.source) { li.appendChild(el("div", "headline-source", item.source)); }
      li.appendChild(el("div", "headline-title", item.title));
      if (item.text) { li.appendChild(el("div", "headline-text", item.text)); }
      list.appendChild(li);
      if (list.scrollHeight > list.clientHeight + 1) {   // passt nicht mehr -> wieder weg
        if (pageCount > 0) { list.removeChild(li); }
        else { pageCount = 1; }
        break;
      }
      pageCount += 1;
    }
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
    tickNews();
  }

  function markUnreachable() {
    serverReachable = false;
    renderIdle();
    if (state) { renderMedia(); } else { setBackground("", null); }
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
    window.addEventListener("resize", function () {
      applyLayout();
      if (!$("headlines").hidden) { renderHeadlines(false); }
    });
    tickClock();
    setInterval(tickClock, 1000);
    setInterval(tickProgress, 250);
    setInterval(function () { if (state) { renderCalendar(); tickNews(); } }, 1000);
    connect();
  });
})();
