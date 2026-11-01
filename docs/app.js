// Castcorder — page interactions

(function () {
  "use strict";

  /* ---------- LED demo ---------- */

  var demoDeck = document.querySelector(".deck--demo");
  var segments = demoDeck
    ? Array.prototype.slice.call(demoDeck.querySelectorAll(".seg"))
    : [];
  var reels = demoDeck
    ? Array.prototype.slice.call(demoDeck.querySelectorAll(".reel"))
    : [];
  var liveBtn = document.getElementById("live-btn");
  var note = document.getElementById("demo-note");
  var chips = Array.prototype.slice.call(document.querySelectorAll("[data-state]"));

  var notes = {
    idle: "Alles aus — die LIVE-Taste glimmt nur schwach.",
    connecting: "Die VU-Leiter läuft 1 → 7 durch, die Spulen drehen.",
    live: "Eingangspegel als Leiter 0–7. Bei 0 dBFS leuchtet die ganze Leiter (Clipping).",
    retrying: "Alle Segmente blinken langsam: der Encoder versucht es erneut.",
    error: "Alle Segmente blinken schnell: max_retries erreicht.",
  };

  var state = "idle";
  var timer = null;
  var level = 3;

  function stop() {
    if (timer !== null) {
      clearInterval(timer);
      timer = null;
    }
    segments.forEach(function (s) {
      s.className = "seg";
    });
    reels.forEach(function (r) {
      r.classList.remove("is-spinning");
    });
  }

  function paintLevel(n) {
    segments.forEach(function (s, i) {
      var on = i < n;
      s.classList.toggle("on", on);
      s.classList.toggle("clip", on && n >= 7);
    });
  }

  function setState(next) {
    state = next;
    stop();

    chips.forEach(function (c) {
      c.classList.toggle("is-active", c.dataset.state === next);
    });

    if (liveBtn) {
      var on = next === "live";
      liveBtn.classList.toggle("is-on", on);
      liveBtn.setAttribute("aria-pressed", String(on));
    }

    if (note) {
      note.textContent = notes[next] || "";
    }

    if (next === "connecting") {
      var i = 0;
      reels.forEach(function (r) {
        r.classList.add("is-spinning");
      });
      timer = setInterval(function () {
        paintLevel((i % segments.length) + 1);
        i += 1;
      }, 140);
    } else if (next === "live") {
      level = 3;
      reels.forEach(function (r) {
        r.classList.add("is-spinning");
      });
      timer = setInterval(function () {
        level += Math.random() * 2.6 - 1.15;
        if (level < 0) level = 0;
        if (level > 7) level = 7;
        paintLevel(Math.round(level));
      }, 130);
    } else if (next === "retrying") {
      segments.forEach(function (s) {
        s.classList.add("blink-slow");
      });
    } else if (next === "error") {
      segments.forEach(function (s) {
        s.classList.add("blink-fast");
      });
    }
  }

  chips.forEach(function (chip) {
    chip.addEventListener("click", function () {
      setState(chip.dataset.state);
    });
  });

  if (liveBtn) {
    liveBtn.addEventListener("click", function () {
      if (state === "live") {
        setState("idle");
        return;
      }
      setState("connecting");
      setTimeout(function () {
        if (state === "connecting") setState("live");
      }, 1100);
    });
  }

  setState("idle");

  /* ---------- copy buttons ---------- */

  Array.prototype.forEach.call(document.querySelectorAll(".copy-btn"), function (btn) {
    btn.addEventListener("click", function () {
      var block = btn.closest(".code");
      var code = block && block.querySelector("code");
      if (!code) return;

      var text = code.textContent;
      var done = function (label) {
        var original = btn.textContent;
        btn.textContent = label;
        setTimeout(function () {
          btn.textContent = original;
        }, 1600);
      };

      if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(text).then(
          function () {
            done("Kopiert ✓");
          },
          function () {
            done("Nicht erlaubt");
          },
        );
      } else {
        done("Nicht erlaubt");
      }
    });
  });

  /* ---------- lightbox ---------- */

  var lightbox = document.getElementById("lightbox");
  var lightboxImg = document.getElementById("lightbox-img");
  var lightboxCaption = document.getElementById("lightbox-caption");

  if (lightbox && lightboxImg) {
    Array.prototype.forEach.call(
      document.querySelectorAll("[data-lightbox]"),
      function (btn) {
        btn.addEventListener("click", function () {
          var img = btn.querySelector("img");
          if (!img) return;
          lightboxImg.src = img.src;
          lightboxImg.alt = img.alt;
          if (lightboxCaption) {
            lightboxCaption.textContent = btn.dataset.lightbox || "";
          }
          if (typeof lightbox.showModal === "function") {
            lightbox.showModal();
          }
        });
      },
    );

    lightbox.addEventListener("click", function (event) {
      if (event.target === lightbox) {
        lightbox.close();
      }
    });
  }

  /* ---------- reveal on scroll ---------- */

  var reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  var revealables = Array.prototype.slice.call(document.querySelectorAll(".reveal"));

  if (reduceMotion || !("IntersectionObserver" in window)) {
    revealables.forEach(function (el) {
      el.classList.add("in");
    });
  } else {
    var observer = new IntersectionObserver(
      function (entries) {
        entries.forEach(function (entry) {
          if (entry.isIntersecting) {
            entry.target.classList.add("in");
            observer.unobserve(entry.target);
          }
        });
      },
      { rootMargin: "0px 0px -8% 0px", threshold: 0.08 },
    );

    revealables.forEach(function (el) {
      observer.observe(el);
    });
  }
})();
