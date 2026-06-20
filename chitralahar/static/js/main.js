/* Chitralahar — public scripts: sticky-header shadow + gallery lightbox */
(function () {
  "use strict";

  // Subtle border on the header once the page is scrolled.
  var header = document.getElementById("siteHeader");
  if (header) {
    var onScroll = function () {
      header.classList.toggle("scrolled", window.scrollY > 8);
    };
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
  }

  // Mobile menu (hamburger) — runs on every page, so it lives before the
  // gallery-only early return below.
  var navToggle = document.getElementById("navToggle");
  var siteNav = document.getElementById("siteNav");
  if (navToggle && siteNav) {
    var setNav = function (open) {
      siteNav.classList.toggle("is-open", open);
      navToggle.classList.toggle("is-open", open);
      navToggle.setAttribute("aria-expanded", open ? "true" : "false");
    };
    navToggle.addEventListener("click", function () {
      setNav(!siteNav.classList.contains("is-open"));
    });
    siteNav.addEventListener("click", function (e) {
      if (e.target.tagName === "A") setNav(false);
    });
    document.addEventListener("keydown", function (e) {
      if (e.key === "Escape") setNav(false);
    });
    window.addEventListener("resize", function () {
      if (window.innerWidth > 640) setNav(false);
    });
  }

  // Lightbox over the gallery.
  var lb = document.getElementById("lightbox");
  var links = Array.prototype.slice.call(
    document.querySelectorAll(".g-link[data-full]")
  );
  if (!lb || !links.length) return;

  var img = document.getElementById("lbImg");
  var cap = document.getElementById("lbCap");
  var idx = 0;

  function show(i) {
    idx = (i + links.length) % links.length;
    var a = links[idx];
    var full = a.getAttribute("data-full");
    var caption = a.getAttribute("data-cap") || "";
    img.classList.add("is-loading");
    var pre = new Image();
    pre.onload = function () {
      img.src = full;
      img.classList.remove("is-loading");
    };
    pre.src = full;
    img.alt = caption;
    cap.textContent = caption;
  }

  function open(i) {
    show(i);
    lb.classList.add("is-open");
    lb.setAttribute("aria-hidden", "false");
    document.body.classList.add("lb-locked");
  }

  function close() {
    lb.classList.remove("is-open");
    lb.setAttribute("aria-hidden", "true");
    document.body.classList.remove("lb-locked");
  }

  links.forEach(function (a, i) {
    a.addEventListener("click", function (e) {
      e.preventDefault();
      open(i);
    });
  });

  lb.addEventListener("click", function (e) {
    var action = e.target.getAttribute("data-lb");
    if (action === "close") return close();
    if (action === "prev") return show(idx - 1);
    if (action === "next") return show(idx + 1);
    if (e.target === lb || e.target.classList.contains("lb-stage")) close();
  });

  document.addEventListener("keydown", function (e) {
    if (!lb.classList.contains("is-open")) return;
    if (e.key === "Escape") close();
    else if (e.key === "ArrowLeft") show(idx - 1);
    else if (e.key === "ArrowRight") show(idx + 1);
  });

  // Touch swipe between photos.
  var startX = 0;
  lb.addEventListener("touchstart", function (e) {
    startX = e.changedTouches[0].clientX;
  }, { passive: true });
  lb.addEventListener("touchend", function (e) {
    var dx = e.changedTouches[0].clientX - startX;
    if (Math.abs(dx) > 50) show(idx + (dx < 0 ? 1 : -1));
  }, { passive: true });
})();

/* Home slideshow (the "Slider" template) — its own scope so it runs even on
   pages where the gallery lightbox above early-returns. */
(function () {
  "use strict";
  var slider = document.getElementById("homeSlider");
  if (!slider) return;
  var slides = Array.prototype.slice.call(slider.querySelectorAll(".slide"));
  if (slides.length < 2) return;  // a single featured photo is just a static hero

  var dots = Array.prototype.slice.call(slider.querySelectorAll(".slider-dot"));
  var i = 0, timer = null, DELAY = 5500;

  function show(n) {
    i = (n + slides.length) % slides.length;
    slides.forEach(function (s, k) { s.classList.toggle("is-active", k === i); });
    dots.forEach(function (d, k) { d.classList.toggle("is-active", k === i); });
  }
  function go(n) { show(n); start(); }
  function start() { stop(); timer = setInterval(function () { show(i + 1); }, DELAY); }
  function stop() { if (timer) { clearInterval(timer); timer = null; } }

  var next = slider.querySelector(".slider-next");
  var prev = slider.querySelector(".slider-prev");
  if (next) next.addEventListener("click", function () { go(i + 1); });
  if (prev) prev.addEventListener("click", function () { go(i - 1); });
  dots.forEach(function (d, k) { d.addEventListener("click", function () { go(k); }); });

  slider.addEventListener("mouseenter", stop);
  slider.addEventListener("mouseleave", start);

  // Swipe on touch; a small drag shouldn't block tapping a slide's link.
  var x0 = null;
  slider.addEventListener("touchstart", function (e) { x0 = e.touches[0].clientX; }, { passive: true });
  slider.addEventListener("touchend", function (e) {
    if (x0 === null) return;
    var dx = e.changedTouches[0].clientX - x0;
    if (Math.abs(dx) > 45) { go(i + (dx < 0 ? 1 : -1)); }
    x0 = null;
  }, { passive: true });

  if (!window.matchMedia || !window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
    start();
  }
})();
