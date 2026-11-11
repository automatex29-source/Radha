/* Krish UI motion: the interactive half of krish-ui.css. Krish AI adds it to every page that uses the kit.
   - .nav with .nav-links gets a phone menu button
   - .reveal / .reveal-stagger animate in on scroll (where CSS scroll animations aren't supported)
   - .tilt cards lean towards the pointer in 3D; .spotlight cards light up under it
   - [data-count="1200"] numbers count up when seen (data-suffix="+", data-prefix="₹")
   - .typed[data-words="fast|simple|yours"] types and rotates words
   - .scene[data-scene="glass|blob|galaxy|waves|rings"] draws a live 3D scene (Three.js, loaded only when used)
   - .magnetic buttons lean to the pointer, .split headings rise in word by word, [data-speed] parallax,
     .scroll-progress fills as the page scrolls
   - transitions: links to the app's other pages, [data-show="#screen"] buttons, [data-theme-toggle] and
     krish.transition(update, {type, from}) animate with View Transitions (see the CSS); data-morph="x" pairs
     grow from one screen into the other */
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

  /* ---------- 3D scenes ---------- */
  var THREE_URL = "https://cdn.jsdelivr.net/npm/three@0.160.0/build/three.module.js";
  var threeP = null;
  function webgl() {
    try { var c = document.createElement("canvas"); return !!(c.getContext("webgl2") || c.getContext("webgl")); } catch (e) { return false; }
  }
  function scenes() {
    var els = Array.prototype.filter.call(document.querySelectorAll(".scene[data-scene]"), function (el) { return !el.__krish; });
    if (!els.length) return;
    els.forEach(function (el) { el.__krish = true; });
    var fail = function () { els.forEach(function (el) { el.classList.add("scene-fallback"); }); };
    if (!webgl()) return fail();
    threeP = threeP || import(THREE_URL);
    threeP.then(function (T) {
      els.forEach(function (el) { try { makeScene(T, el); } catch (e) { el.classList.add("scene-fallback"); } });
    }, fail);
  }
  function makeScene(T, el) {
    var cs = getComputedStyle(el);
    function colour(name, fb) { var c = new T.Color(fb); try { var v = cs.getPropertyValue(name).trim(); if (v && v.indexOf("(") < 0) c.setStyle(v); } catch (e) {} return c; }
    var c1 = colour("--accent", "#7c3aed"), c2 = colour("--accent-2", "#06b6d4"), kind = el.getAttribute("data-scene");
    var renderer = new T.WebGLRenderer({ antialias: true, alpha: true, powerPreference: "high-performance" });
    renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
    renderer.toneMapping = T.ACESFilmicToneMapping;
    el.appendChild(renderer.domElement);
    var scene = new T.Scene(), camera = new T.PerspectiveCamera(35, 1, 0.1, 100), group = new T.Group();
    camera.position.set(0, 0, 7);
    scene.add(group);
    // A small studio of coloured lights for reflections: no image files to load.
    var studio = new T.Scene();
    [[c1, -4, 2, -3], [c2, 4, -1, -3], [new T.Color("#ffffff"), 0, 5, 2], [c1.clone().lerp(c2, 0.5), 0, -5, 3]].forEach(function (l) {
      var m = new T.Mesh(new T.BoxGeometry(3, 3, 0.2), new T.MeshBasicMaterial({ color: l[0] }));
      m.position.set(l[1], l[2], l[3]); m.lookAt(0, 0, 0); studio.add(m);
    });
    var pmrem = new T.PMREMGenerator(renderer);
    scene.environment = pmrem.fromScene(studio, 0.04).texture;
    scene.add(new T.AmbientLight(0xffffff, 0.4));
    var sun = new T.DirectionalLight(0xffffff, 1.6); sun.position.set(3, 4, 5); scene.add(sun);
    var glass = function (tint) {
      return new T.MeshPhysicalMaterial({ color: 0xffffff, metalness: 0, roughness: 0.04, transmission: 1, thickness: 1.4, ior: 1.45,
        iridescence: 0.9, iridescenceIOR: 1.3, clearcoat: 1, attenuationColor: tint, attenuationDistance: 2.5, envMapIntensity: 1.4 });
    };
    var tick = function () {}, uTime = { value: 0 };
    if (kind === "blob") {
      var mat = new T.MeshPhysicalMaterial({ color: c1.clone().lerp(new T.Color("#ffffff"), 0.15), metalness: 0.15, roughness: 0.18,
        clearcoat: 1, iridescence: 1, iridescenceIOR: 1.6, sheen: 1, sheenColor: c2, envMapIntensity: 1.3 });
      mat.onBeforeCompile = function (sh) {
        sh.uniforms.uTime = uTime;
        sh.vertexShader = "uniform float uTime;\n" + sh.vertexShader.replace("#include <begin_vertex>",
          "vec3 transformed = position + normal * (0.22 * sin(position.x * 1.8 + uTime) * sin(position.y * 2.1 + uTime * 1.3) * sin(position.z * 1.6 + uTime * 0.7));");
      };
      group.add(new T.Mesh(new T.IcosahedronGeometry(1.55, 64), mat));
    } else if (kind === "galaxy") {
      var n = 9000, pos = new Float32Array(n * 3), col = new Float32Array(n * 3), tmp = new T.Color();
      for (var i = 0; i < n; i++) {
        var r = Math.pow(Math.random(), 0.7) * 3.2, arm = (i % 3) * (Math.PI * 2 / 3), a = arm + r * 1.4;
        var j = function () { return (Math.random() - 0.5) * Math.pow(Math.random(), 2) * 1.2; };
        pos[i * 3] = Math.cos(a) * r + j(); pos[i * 3 + 1] = j() * 0.6; pos[i * 3 + 2] = Math.sin(a) * r + j();
        tmp.copy(c1).lerp(c2, r / 3.2); col[i * 3] = tmp.r; col[i * 3 + 1] = tmp.g; col[i * 3 + 2] = tmp.b;
      }
      var g = new T.BufferGeometry();
      g.setAttribute("position", new T.BufferAttribute(pos, 3)); g.setAttribute("color", new T.BufferAttribute(col, 3));
      group.add(new T.Points(g, new T.PointsMaterial({ size: 0.05, vertexColors: true, transparent: true, depthWrite: false, blending: T.AdditiveBlending })));
      group.rotation.x = 0.55; camera.position.z = 9.5;
      tick = function (t) { group.children[0].rotation.y = t * 0.08; };
    } else if (kind === "waves") {
      var side = 90, wpos = new Float32Array(side * side * 3), wcol = new Float32Array(side * side * 3), k = 0, wc = new T.Color();
      for (var x = 0; x < side; x++) for (var z = 0; z < side; z++) {
        wpos[k * 3] = (x / side - 0.5) * 9; wpos[k * 3 + 2] = (z / side - 0.5) * 9;
        wc.copy(c1).lerp(c2, x / side); wcol[k * 3] = wc.r; wcol[k * 3 + 1] = wc.g; wcol[k * 3 + 2] = wc.b; k++;
      }
      var wg = new T.BufferGeometry();
      wg.setAttribute("position", new T.BufferAttribute(wpos, 3)); wg.setAttribute("color", new T.BufferAttribute(wcol, 3));
      group.add(new T.Points(wg, new T.PointsMaterial({ size: 0.045, vertexColors: true, transparent: true, depthWrite: false, blending: T.AdditiveBlending })));
      group.rotation.x = 0.5; camera.position.set(0, 0.6, 6.5);
      tick = function (t) {
        var p = wg.attributes.position.array;
        for (var q = 0; q < p.length; q += 3) p[q + 1] = Math.sin(p[q] * 0.9 + t * 1.2) * 0.35 + Math.cos(p[q + 2] * 0.8 + t * 0.9) * 0.35;
        wg.attributes.position.needsUpdate = true;
      };
    } else if (kind === "rings") {
      [[1.9, 0.09, c1], [1.45, 0.12, c2], [1.0, 0.1, c1.clone().lerp(c2, 0.5)]].forEach(function (rg, idx) {
        var m = new T.Mesh(new T.TorusGeometry(rg[0], rg[1], 32, 160), glass(rg[2]));
        m.userData.speed = 0.25 + idx * 0.15; m.rotation.x = idx; group.add(m);
      });
      var core = new T.Mesh(new T.SphereGeometry(0.45, 48, 48), new T.MeshStandardMaterial({ color: c2, emissive: c2, emissiveIntensity: 1.4 }));
      group.add(core);
      tick = function (t) { group.children.forEach(function (m, idx) { if (m.userData.speed) { m.rotation.x = idx + t * m.userData.speed; m.rotation.y = t * m.userData.speed * 0.7; } }); };
    } else {
      // glass: a slowly turning knot of clear, rainbow-edged glass with colour glowing through it
      var knot = new T.Mesh(new T.TorusKnotGeometry(1.05, 0.36, 260, 40), glass(c1));
      group.add(knot);
      [[c1, -1.2, 0.6], [c2, 1.3, -0.7]].forEach(function (b) {
        var s = new T.Mesh(new T.SphereGeometry(0.6, 32, 32), new T.MeshBasicMaterial({ color: b[0] }));
        s.position.set(b[1], b[2], -2.2); scene.add(s);
      });
      tick = function (t) { knot.rotation.x = t * 0.18; knot.rotation.y = t * 0.27; };
    }
    function size() {
      var w = el.clientWidth || 400, h = el.clientHeight || 400;
      renderer.setSize(w, h, false); camera.aspect = w / h; camera.updateProjectionMatrix();
      camera.zoom = w < 520 ? 0.8 : 1; camera.updateProjectionMatrix();
    }
    size();
    if ("ResizeObserver" in window) new ResizeObserver(size).observe(el);
    var mx = 0, my = 0, seen = true, t0 = performance.now(), dead = false;
    if (fine) window.addEventListener("pointermove", function (e) { mx = e.clientX / innerWidth - 0.5; my = e.clientY / innerHeight - 0.5; }, { passive: true });
    if ("IntersectionObserver" in window) new IntersectionObserver(function (en) { seen = en[0].isIntersecting; }).observe(el);
    function frame(now) {
      if (dead) return;
      try {
        var t = (now - t0) / 1000;
        uTime.value = t; tick(t);
        group.rotation.y += ((mx * 0.6) - group.rotation.y) * 0.05;
        group.rotation.z += ((-my * 0.25) - group.rotation.z) * 0.05;
        group.position.y = Math.sin(t * 0.8) * 0.08;
        renderer.render(scene, camera);
      } catch (e) { dead = true; el.classList.add("scene-fallback"); return; }
      if (!still) requestAnimationFrame(function (n) { if (seen) frame(n); else setTimeout(function () { requestAnimationFrame(frame); }, 250); });
    }
    requestAnimationFrame(frame);
    el.classList.add("scene-ready");
  }

  /* ---------- Magnetic buttons, word-by-word headings, parallax, scroll progress ---------- */
  function extras() {
    if (fine && !still) document.querySelectorAll(".magnetic:not(.kmag)").forEach(function (b) {
      b.classList.add("kmag");
      b.addEventListener("pointermove", function (e) {
        var r = b.getBoundingClientRect();
        b.style.transform = "translate(" + ((e.clientX - r.left - r.width / 2) * 0.25).toFixed(1) + "px," + ((e.clientY - r.top - r.height / 2) * 0.35).toFixed(1) + "px)";
      });
      b.addEventListener("pointerleave", function () { b.style.transform = ""; });
    });
    document.querySelectorAll(".split:not(.ksplit)").forEach(function (h) {
      h.classList.add("ksplit");
      var i = 0;
      (function walk(node) {
        Array.prototype.slice.call(node.childNodes).forEach(function (c) {
          if (c.nodeType === 3) {
            var frag = document.createDocumentFragment();
            c.textContent.split(/(\s+)/).forEach(function (w) {
              if (!w) return;
              if (/^\s+$/.test(w)) { frag.appendChild(document.createTextNode(w)); return; }
              var s = document.createElement("span"); s.className = "w"; s.style.setProperty("--i", i++); s.textContent = w; frag.appendChild(s);
            });
            c.parentNode.replaceChild(frag, c);
          } else if (c.nodeType === 1 && !c.classList.contains("typed")) walk(c);
        });
      })(h);
    });
  }
  var parallaxOn = false;
  function scrolly() {
    var bar = document.querySelector(".scroll-progress");
    var items = document.querySelectorAll("[data-speed]");
    if ((!bar && !items.length) || parallaxOn) return;
    parallaxOn = true;
    var busy = false;
    function update() {
      busy = false;
      var max = document.documentElement.scrollHeight - innerHeight;
      if (bar) bar.style.transform = "scaleX(" + (max > 0 ? scrollY / max : 0).toFixed(4) + ")";
      if (!still) document.querySelectorAll("[data-speed]").forEach(function (el) {
        var r = el.getBoundingClientRect(), mid = r.top + r.height / 2 - innerHeight / 2;
        el.style.translate = "0 " + (mid * -(parseFloat(el.getAttribute("data-speed")) || 0.2)).toFixed(1) + "px";
      });
    }
    addEventListener("scroll", function () { if (!busy) { busy = true; requestAnimationFrame(update); } }, { passive: true });
    update();
  }

  /* ---------- Fonts for Indian scripts (text drawn by JavaScript after the page loaded) ---------- */
  var SCRIPTS = [[/[\u0900-\u097F]/, "Noto+Sans+Devanagari"], [/[\u0980-\u09FF]/, "Noto+Sans+Bengali"], [/[\u0A00-\u0A7F]/, "Noto+Sans+Gurmukhi"],
    [/[\u0A80-\u0AFF]/, "Noto+Sans+Gujarati"], [/[\u0B00-\u0B7F]/, "Noto+Sans+Oriya"], [/[\u0B80-\u0BFF]/, "Noto+Sans+Tamil"],
    [/[\u0C00-\u0C7F]/, "Noto+Sans+Telugu"], [/[\u0C80-\u0CFF]/, "Noto+Sans+Kannada"], [/[\u0D00-\u0D7F]/, "Noto+Sans+Malayalam"],
    [/[\u0600-\u06FF]/, "Noto+Naskh+Arabic"]];
  var fontsAdded = {};
  function fonts() {
    var text = (document.body && document.body.innerText || "").slice(0, 20000), need = [];
    SCRIPTS.forEach(function (sc) {
      if (fontsAdded[sc[1]] || !sc[0].test(text)) return;
      fontsAdded[sc[1]] = true;
      if (!document.querySelector('link[href*="' + sc[1] + '"]')) need.push("family=" + sc[1] + ":wght@400..700");
    });
    if (Object.keys(fontsAdded).length) document.documentElement.classList.add("krish-indic");
    if (!need.length) return;
    var l = document.createElement("link");
    l.rel = "stylesheet"; l.href = "https://fonts.googleapis.com/css2?" + need.join("&") + "&display=swap";
    document.head.appendChild(l);
  }

  // ---------- Transitions ----------
  var canVT = !!document.startViewTransition && !still;
  function pinNav() {
    var nav = document.querySelector("body > header") || document.querySelector(".nav");
    if (nav && !document.querySelector("[style*=krish-nav]")) nav.style.viewTransitionName = "krish-nav";
  }
  function visible(el) { return !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length); }
  function nameMorphs(on) {
    // Only the visible element of each data-morph pair gets the name, so each name is unique per snapshot.
    var seen = {};
    document.querySelectorAll("[data-morph]").forEach(function (el) {
      var key = "km-" + String(el.getAttribute("data-morph")).replace(/[^\w-]/g, "_");
      if (on && visible(el) && !seen[key]) { el.style.viewTransitionName = key; seen[key] = 1; }
      else if (el.style.viewTransitionName && el.style.viewTransitionName.indexOf("km-") === 0) el.style.viewTransitionName = "";
    });
  }
  // Run `update` (a function that changes the page) as an animated transition. opts.type: slide, zoom, fade,
  // blur, wipe, circle (from opts.from, a click event or {x, y}); opts.back for a slide the other way.
  function transition(update, opts) {
    opts = opts || {};
    if (!canVT) { update(); return Promise.resolve(); }
    var root = document.documentElement, before = root.getAttribute("data-transition"), type = opts.type || before;
    if (type && type !== "circle") root.setAttribute("data-transition", type);
    root.classList.toggle("krish-back", !!opts.back);
    root.classList.toggle("krish-circle", type === "circle");
    nameMorphs(true);
    var vt = document.startViewTransition(function () {
      nameMorphs(false);
      var r = update();
      return Promise.resolve(r).then(function () { nameMorphs(true); });
    });
    if (type === "circle") {
      var p = opts.from || {}, x = p.clientX != null ? p.clientX : (p.x != null ? p.x : innerWidth / 2),
        y = p.clientY != null ? p.clientY : (p.y != null ? p.y : innerHeight / 2);
      var r = Math.hypot(Math.max(x, innerWidth - x), Math.max(y, innerHeight - y));
      vt.ready.then(function () {
        root.animate({ clipPath: ["circle(0px at " + x + "px " + y + "px)", "circle(" + r + "px at " + x + "px " + y + "px)"] },
          { duration: 650, easing: "cubic-bezier(0.65, 0, 0.35, 1)", pseudoElement: "::view-transition-new(root)" });
      }).catch(function () {});
    }
    return vt.finished.catch(function () {}).then(function () {
      nameMorphs(false);
      root.classList.remove("krish-circle", "krish-back");
      if (before === null) root.removeAttribute("data-transition"); else root.setAttribute("data-transition", before);
    });
  }
  window.krish = window.krish || {};
  window.krish.transition = transition;

  var screenOrder = function (el) { return Array.prototype.indexOf.call(el.parentNode.children, el); };
  function showScreen(target, btn, ev) {
    var screen = document.querySelector(target);
    if (!screen) return;
    var group = Array.prototype.filter.call(screen.parentNode.children, function (s) { return s.classList.contains("screen"); });
    var current = group.filter(function (s) { return !s.hidden; })[0];
    if (current === screen) return;
    var back = current && screenOrder(screen) < screenOrder(current);
    transition(function () {
      group.forEach(function (s) { s.hidden = s !== screen; });
      document.querySelectorAll("[data-show]").forEach(function (b) {
        var on = b.getAttribute("data-show") === target;
        b.classList.toggle("active", on);
        if (on) b.setAttribute("aria-current", "page"); else b.removeAttribute("aria-current");
      });
      if (screen.getBoundingClientRect().top < 0) scrollTo({ top: 0 });
      screen.dispatchEvent(new CustomEvent("krish:show", { bubbles: true }));
    }, { type: btn.getAttribute("data-transition") || undefined, from: ev, back: back });
  }
  function toggleTheme(btn, ev) {
    transition(function () {
      var dark = !document.body.classList.contains("dark");
      document.body.classList.toggle("dark", dark);
      try { localStorage.setItem("krish-theme", dark ? "dark" : "light"); } catch (e) {}
      btn.setAttribute("aria-pressed", dark ? "true" : "false");
    }, { type: "circle", from: ev });
  }
  var transitionsReady = false;
  function transitions() {
    pinNav();
    // The first .screen of each group shows until a button picks another.
    var parents = [];
    document.querySelectorAll(".screen").forEach(function (s) { if (parents.indexOf(s.parentNode) < 0) parents.push(s.parentNode); });
    parents.forEach(function (p) {
      if (p.__krishScreens) return;
      p.__krishScreens = true;
      var group = Array.prototype.filter.call(p.children, function (s) { return s.classList.contains("screen"); });
      var shown = group.filter(function (s) { return !s.hidden; });
      var start = location.hash && group.filter(function (s) { return "#" + s.id === location.hash; })[0];
      if (start || shown.length !== 1) group.forEach(function (s, i) { s.hidden = start ? s !== start : i > 0; });
    });
    if (transitionsReady) return;
    transitionsReady = true;
    try { if (localStorage.getItem("krish-theme") === "dark" && document.querySelector("[data-theme-toggle]")) document.body.classList.add("dark"); } catch (e) {}
    document.addEventListener("click", function (ev) {
      var t = ev.target.closest && ev.target.closest("[data-show], [data-theme-toggle]");
      if (!t) return;
      ev.preventDefault();
      if (t.hasAttribute("data-theme-toggle")) toggleTheme(t, ev);
      else showScreen(t.getAttribute("data-show"), t, ev);
    });
    // Going back to an earlier page slides the other way.
    addEventListener("pageswap", function (e) {
      try {
        var to = e.activation && e.activation.entry && e.activation.entry.index, from = navigation.currentEntry.index;
        document.documentElement.classList.toggle("krish-back", to != null && to < from);
      } catch (x) {}
    });
    addEventListener("pagereveal", function (e) {
      try {
        var nav = window.navigation, act = nav && nav.activation;
        var back = act && act.from && act.entry && act.entry.index < act.from.index;
        document.documentElement.classList.toggle("krish-back", !!back);
        if (e.viewTransition) e.viewTransition.finished.then(function () { document.documentElement.classList.remove("krish-back"); });
      } catch (x) {}
    });
  }

  function start() { transitions(); fonts(); navs(); reveals(); pointer(); counters(); typed(); extras(); scrolly(); scenes(); }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start);
  else start();
  // Pages that draw their content with JavaScript get the menu button and reveals once it is there.
  if ("MutationObserver" in window) {
    var queued = false;
    new MutationObserver(function () {
      if (queued) return;
      queued = true;
      setTimeout(function () { queued = false; transitions(); fonts(); navs(); extras(); reveals(); scrolly(); scenes(); }, 120);
    }).observe(document.documentElement, { childList: true, subtree: true });
  }
})();
