/* Krish UI motion: the interactive half of krish-ui.css. Krish AI adds it to every page that uses the kit.
   - .nav with .nav-links gets a phone menu button
   - .reveal / .reveal-stagger animate in on scroll (where CSS scroll animations aren't supported)
   - .tilt cards lean towards the pointer in 3D; .spotlight cards light up under it
   - [data-count="1200"] numbers count up when seen (data-suffix="+", data-prefix="₹")
   - .typed[data-words="fast|simple|yours"] types and rotates words */
(function () {
  if (window.__krishUI) return;
  window.__krishUI = true;
  var still = window.matchMedia && matchMedia("(prefers-reduced-motion: reduce)").matches;
  var fine = window.matchMedia && matchMedia("(pointer: fine)").matches;

  function navs() {
    document.querySelectorAll(".nav").forEach(function (nav) {
      var links = nav.querySelector(".nav-links");
      if (!links || nav.querySelector(".nav-toggle")) return;
      var row = links.parentElement;
      var b = document.createElement("button");
      b.type = "button";
      b.className = "nav-toggle";
      b.setAttribute("aria-label", "Menu");
      b.setAttribute("aria-expanded", "false");
      b.innerHTML = "<span></span>";
      row.appendChild(b);
      if (getComputedStyle(row).position === "static") row.style.position = "relative";
      b.addEventListener("click", function () {
        var open = links.classList.toggle("open");
        b.setAttribute("aria-expanded", open ? "true" : "false");
      });
      links.addEventListener("click", function (e) {
        if (e.target.closest("a")) { links.classList.remove("open"); b.setAttribute("aria-expanded", "false"); }
      });
    });
  }

  var revealer = null;
  function reveals() {
    document.querySelectorAll(".reveal-stagger").forEach(function (g) {
      Array.prototype.forEach.call(g.children, function (c, i) { c.style.setProperty("--i", i); });
    });
    var css = window.CSS && CSS.supports && CSS.supports("animation-timeline: view()");
    var items = Array.prototype.filter.call(document.querySelectorAll(css ? ".reveal-stagger" : ".reveal, .reveal-stagger"), function (el) { return !el.classList.contains("kw"); });
    if (!items.length) return;
    if (still || !("IntersectionObserver" in window)) { items.forEach(function (el) { el.classList.add("in"); }); return; }
    document.documentElement.classList.add("krish-io");
    var io = revealer || (revealer = new IntersectionObserver(function (entries) {
      entries.forEach(function (e) { if (e.isIntersecting) { e.target.classList.add("in"); revealer.unobserve(e.target); } });
    }, { threshold: 0.12, rootMargin: "0px 0px -6% 0px" }));
    items.forEach(function (el) { el.classList.add("kw"); io.observe(el); });
  }

  function pointer() {
    if (!fine || still) return;
    document.addEventListener("pointermove", function (e) {
      var t = e.target.closest && e.target.closest(".tilt, .spotlight");
      if (!t) return;
      var r = t.getBoundingClientRect(), x = (e.clientX - r.left) / r.width, y = (e.clientY - r.top) / r.height;
      if (t.classList.contains("tilt")) t.style.transform = "perspective(900px) rotateX(" + ((0.5 - y) * 10).toFixed(2) + "deg) rotateY(" + ((x - 0.5) * 12).toFixed(2) + "deg) translateY(-4px)";
      t.style.setProperty("--mx", (x * 100).toFixed(1) + "%");
      t.style.setProperty("--my", (y * 100).toFixed(1) + "%");
    }, { passive: true });
    document.addEventListener("pointerout", function (e) {
      var t = e.target.closest && e.target.closest(".tilt");
      if (t && !t.contains(e.relatedTarget)) t.style.transform = "";
    });
  }

  function counters() {
    var els = document.querySelectorAll("[data-count]");
    if (!els.length) return;
    function run(el) {
      var end = parseFloat(el.getAttribute("data-count")) || 0, dec = (String(el.getAttribute("data-count")).split(".")[1] || "").length;
      var pre = el.getAttribute("data-prefix") || "", suf = el.getAttribute("data-suffix") || "", t0 = null;
      function show(v) { el.textContent = pre + v.toLocaleString(undefined, { minimumFractionDigits: dec, maximumFractionDigits: dec }) + suf; }
      if (still) return show(end);
      function step(ts) { t0 = t0 || ts; var p = Math.min(1, (ts - t0) / 1400); show(end * (1 - Math.pow(1 - p, 3))); if (p < 1) requestAnimationFrame(step); }
      requestAnimationFrame(step);
    }
    if (!("IntersectionObserver" in window)) return els.forEach(run);
    var io = new IntersectionObserver(function (entries) {
      entries.forEach(function (e) { if (e.isIntersecting) { run(e.target); io.unobserve(e.target); } });
    }, { threshold: 0.4 });
    els.forEach(function (el) { io.observe(el); });
  }

  function typed() {
    document.querySelectorAll(".typed[data-words]").forEach(function (el) {
      var words = el.getAttribute("data-words").split("|").filter(Boolean);
      if (!words.length) return;
      if (still) { el.textContent = words[0]; return; }
      var w = 0, n = 0, back = false;
      (function tick() {
        var word = words[w];
        n += back ? -1 : 1;
        el.textContent = word.slice(0, n);
        var wait = back ? 45 : 85;
        if (!back && n === word.length) { back = true; wait = 1600; }
        else if (back && n === 0) { back = false; w = (w + 1) % words.length; wait = 300; }
        setTimeout(tick, wait);
      })();
    });
  }

  function start() { navs(); reveals(); pointer(); counters(); typed(); }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start);
  else start();
  // Pages that draw their content with JavaScript get the menu button and reveals once it is there.
  if ("MutationObserver" in window) {
    var queued = false;
    new MutationObserver(function () {
      if (queued) return;
      queued = true;
      setTimeout(function () { queued = false; navs(); reveals(); }, 120);
    }).observe(document.documentElement, { childList: true, subtree: true });
  }
})();
