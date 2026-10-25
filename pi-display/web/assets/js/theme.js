/* InfoDisplay – Hell/Dunkel-Umschaltung
   Reihenfolge: gespeicherte Wahl im Browser > Vorgabe aus config.ini > Systemeinstellung */
(function () {
  "use strict";

  var KEY = "infodisplay-theme";
  var root = document.documentElement;
  var media = window.matchMedia ? window.matchMedia("(prefers-color-scheme: dark)") : null;

  function stored() {
    try { return localStorage.getItem(KEY); } catch (e) { return null; }
  }

  function save(value) {
    try { localStorage.setItem(KEY, value); } catch (e) { /* privater Modus o. Ä. */ }
  }

  var Theme = {
    defaultTheme: "auto",

    resolve: function () {
      var s = stored();
      if (s === "light" || s === "dark") { return s; }
      if (this.defaultTheme === "light" || this.defaultTheme === "dark") { return this.defaultTheme; }
      return media && media.matches ? "dark" : "light";
    },

    current: function () {
      return root.getAttribute("data-theme") === "dark" ? "dark" : "light";
    },

    apply: function (theme) {
      root.setAttribute("data-theme", theme);
      var btn = document.getElementById("theme-toggle");
      if (btn) {
        var icon = btn.querySelector(".bi");
        if (icon) { icon.className = "bi " + (theme === "dark" ? "bi-sun" : "bi-moon-stars"); }
        btn.setAttribute("aria-label", theme === "dark" ? "Helle Darstellung" : "Dunkle Darstellung");
        btn.title = btn.getAttribute("aria-label");
      }
    },

    toggle: function () {
      var next = this.current() === "dark" ? "light" : "dark";
      save(next);
      this.apply(next);
    },

    setDefault: function (value) {
      if (value === this.defaultTheme) { return; }
      this.defaultTheme = value;
      this.apply(this.resolve());
    }
  };

  window.InfoTheme = Theme;
  Theme.apply(Theme.resolve());

  if (media && media.addEventListener) {
    media.addEventListener("change", function () { Theme.apply(Theme.resolve()); });
  }

  document.addEventListener("DOMContentLoaded", function () {
    Theme.apply(Theme.current());
    var btn = document.getElementById("theme-toggle");
    if (btn) { btn.addEventListener("click", function () { Theme.toggle(); }); }
    if (/[?&]kiosk=1\b/.test(window.location.search)) { document.body.classList.add("kiosk"); }
  });
})();
