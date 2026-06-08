/* 全站 MathJax：页面只写数学，渲染行为集中在这里 */
(function () {
  if (window.__zenMathJaxInit) return;
  window.__zenMathJaxInit = true;

  window.MathJax = {
    tex: {
      inlineMath: [["$", "$"], ["\\(", "\\)"]],
      displayMath: [["$$", "$$"], ["\\[", "\\]"]],
      processEscapes: true,
      processEnvironments: true,
      tags: "none",
    },
    options: {
      ignoreHtmlClass: "no-mathjax",
      processHtmlClass: "arithmatex",
    },
    svg: { fontCache: "global" },
    startup: {
      pageReady: function () {
        return window.MathJax.startup.defaultPageReady().then(typesetOnNavigation);
      },
    },
  };

  function typeset() {
    if (window.MathJax && window.MathJax.typesetPromise) {
      window.MathJax.typesetPromise();
    }
  }

  function typesetOnNavigation() {
    if (typeof document$ !== "undefined" && document$.subscribe) {
      document$.subscribe(typeset);
    }
  }

  var script = document.createElement("script");
  script.async = true;
  script.src = "https://cdn.jsdelivr.net/npm/mathjax@3/es5/tex-mml-chtml.js";
  document.head.appendChild(script);
})();

/* 与 instant navigation 配合：每次文档切换后重播主内容入场动画 */
(function () {
  function replayContentEnter() {
    var el = document.querySelector("article.md-content__inner");
    if (!el) return;
    el.classList.remove("zen-content-enter");
    void el.offsetWidth;
    el.classList.add("zen-content-enter");
  }

  function onDocumentUpdate() {
    replayContentEnter();
  }

  if (typeof document$ !== "undefined" && document$.subscribe) {
    document$.subscribe(onDocumentUpdate);
  } else if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", onDocumentUpdate);
  } else {
    onDocumentUpdate();
  }
})();

/* 桌面端：彩色光标拖尾 + 点击星星（同一按钮开关，localStorage 记忆） */
(function () {
  if (window.__zenCursorFxInit) return;
  if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
  if (!window.matchMedia("(pointer: fine)").matches) return;

  var LS_KEY = "zen-cursor-fx";
  var TRAIL_MAX = 10;
  var TRAIL_WIDTH = 1.55;
  var TRAIL_SHADOW_BLUR = 8;
  var STARS_PER_CLICK = 11;
  var MAX_STARS = 160;
  var STAR_GRAVITY = 0.42;
  var STAR_FRICTION = 0.985;

  var canvas = null;
  var ctx = null;
  var toggleBtn = null;
  var trail = [];
  var stars = [];
  var rafId = 0;
  var pendingMove = null;
  var moveRaf = 0;
  var lastTrailMs = 0;
  var enabled = true;

  function readEnabled() {
    try {
      return localStorage.getItem(LS_KEY) !== "0";
    } catch (e) {
      return true;
    }
  }

  function writeEnabled(on) {
    try {
      if (on) localStorage.removeItem(LS_KEY);
      else localStorage.setItem(LS_KEY, "0");
    } catch (e) {
      /* ignore */
    }
  }

  function syncToggleUi() {
    if (!toggleBtn || !canvas) return;
    toggleBtn.setAttribute("aria-pressed", enabled ? "true" : "false");
    toggleBtn.textContent = enabled ? "光标动效：开" : "光标动效：关";
    canvas.classList.toggle("zen-cursor-fx--off", !enabled);
  }

  function stopLoop() {
    if (rafId) {
      window.cancelAnimationFrame(rafId);
      rafId = 0;
    }
    trail.length = 0;
    stars.length = 0;
    if (ctx && canvas) {
      var dpr = window.devicePixelRatio || 1;
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx.clearRect(0, 0, window.innerWidth, window.innerHeight);
    }
  }

  function setEnabled(on) {
    enabled = !!on;
    writeEnabled(enabled);
    syncToggleUi();
    if (!enabled) stopLoop();
  }

  function resize() {
    if (!canvas || !ctx) return;
    var dpr = window.devicePixelRatio || 1;
    var w = window.innerWidth;
    var h = window.innerHeight;
    canvas.width = Math.max(1, Math.floor(w * dpr));
    canvas.height = Math.max(1, Math.floor(h * dpr));
    canvas.style.width = w + "px";
    canvas.style.height = h + "px";
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  }

  function drawTrail() {
    if (trail.length < 2) return;
    var n = trail.length;
    var hueBase = performance.now() * 0.022;
    ctx.save();
    ctx.lineCap = "round";
    ctx.lineJoin = "round";
    ctx.lineWidth = TRAIL_WIDTH;
    for (var i = 1; i < n; i++) {
      var hue = (hueBase + i * 36) % 360;
      var segA = 0.055 + (i / (n - 1)) * 0.11;
      var stroke = "hsla(" + hue + ", 52%, 62%, " + segA + ")";
      ctx.strokeStyle = stroke;
      ctx.shadowBlur = TRAIL_SHADOW_BLUR;
      ctx.shadowColor = "hsla(" + hue + ", 52%, 62%, " + (segA * 0.75) + ")";
      ctx.beginPath();
      ctx.moveTo(trail[i - 1].x, trail[i - 1].y);
      ctx.lineTo(trail[i].x, trail[i].y);
      ctx.stroke();
    }
    ctx.restore();
  }

  function drawStarPath(x, y, outerR, innerR, rotation) {
    var spikes = 5;
    var step = Math.PI / spikes;
    var rot = -Math.PI / 2 + rotation;
    ctx.beginPath();
    for (var i = 0; i < spikes * 2; i++) {
      var rad = i % 2 === 0 ? outerR : innerR;
      var px = x + Math.cos(rot) * rad;
      var py = y + Math.sin(rot) * rad;
      if (i === 0) ctx.moveTo(px, py);
      else ctx.lineTo(px, py);
      rot += step;
    }
    ctx.closePath();
  }

  function spawnStars(clientX, clientY) {
    var room = MAX_STARS - stars.length;
    if (room <= 0) return;
    var n = Math.min(STARS_PER_CLICK, room);
    for (var i = 0; i < n; i++) {
      stars.push({
        x: clientX,
        y: clientY,
        vx: (Math.random() - 0.5) * 6.5,
        vy: -Math.random() * 7.2 - 2.2,
        hue: Math.floor(Math.random() * 360),
        life: 1,
        lifeDecay: 0.012 + Math.random() * 0.018,
        outer: 3.2 + Math.random() * 3.8,
        rotation: Math.random() * Math.PI * 2,
        spin: (Math.random() - 0.5) * 0.35,
      });
    }
  }

  function tick() {
    rafId = 0;
    if (!ctx || !canvas || !enabled) return;

    var dpr = window.devicePixelRatio || 1;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, window.innerWidth, window.innerHeight);

    var i;
    for (i = stars.length - 1; i >= 0; i--) {
      var s = stars[i];
      s.vy += STAR_GRAVITY;
      s.vx *= STAR_FRICTION;
      s.vy *= STAR_FRICTION;
      s.x += s.vx;
      s.y += s.vy;
      s.rotation += s.spin;
      s.life -= s.lifeDecay;
      if (s.life <= 0 || s.y > window.innerHeight + s.outer * 2) {
        stars.splice(i, 1);
        continue;
      }
      var inner = s.outer * 0.42;
      var alpha = Math.max(0, Math.min(1, s.life));
      ctx.save();
      ctx.fillStyle = "hsla(" + s.hue + ", 78%, 62%, " + (alpha * 0.92) + ")";
      ctx.strokeStyle = "hsla(" + s.hue + ", 85%, 72%, " + (alpha * 0.55) + ")";
      ctx.lineWidth = 0.6;
      drawStarPath(s.x, s.y, s.outer, inner, s.rotation);
      ctx.fill();
      ctx.stroke();
      ctx.restore();
    }

    drawTrail();

    if (trail.length > 0) {
      if (performance.now() - lastTrailMs > 34) trail.shift();
    }

    if (trail.length > 0 || stars.length > 0) {
      rafId = window.requestAnimationFrame(tick);
    }
  }

  function ensureLoop() {
    if (!rafId) rafId = window.requestAnimationFrame(tick);
  }

  function onMouseMove(ev) {
    if (!enabled) return;
    pendingMove = { x: ev.clientX, y: ev.clientY };
    if (moveRaf) return;
    moveRaf = window.requestAnimationFrame(function () {
      moveRaf = 0;
      if (!enabled || !pendingMove) return;
      trail.push(pendingMove);
      lastTrailMs = performance.now();
      if (trail.length > TRAIL_MAX) trail.splice(0, trail.length - TRAIL_MAX);
      pendingMove = null;
      ensureLoop();
    });
  }

  function onDocClick(ev) {
    if (!enabled) return;
    if (ev.button !== 0 && ev.button !== undefined) return;
    var t = ev.target;
    if (toggleBtn && (t === toggleBtn || toggleBtn.contains(t))) return;
    spawnStars(ev.clientX, ev.clientY);
    ensureLoop();
  }

  function boot() {
    if (window.__zenCursorFxInit) return;
    if (!document.body) return;
    window.__zenCursorFxInit = true;

    enabled = readEnabled();

    canvas = document.createElement("canvas");
    canvas.id = "zen-cursor-fx";
    canvas.setAttribute("aria-hidden", "true");
    ctx = canvas.getContext("2d", { alpha: true });
    document.body.appendChild(canvas);

    toggleBtn = document.createElement("button");
    toggleBtn.type = "button";
    toggleBtn.id = "zen-cursor-fx-toggle";
    toggleBtn.setAttribute("aria-label", "切换光标轨迹与点击星星动效");
    toggleBtn.addEventListener("click", function () {
      setEnabled(!enabled);
    });
    document.body.appendChild(toggleBtn);
    syncToggleUi();
    if (!enabled) stopLoop();

    resize();

    var passive = { passive: true };
    window.addEventListener("resize", resize, passive);
    document.addEventListener("mousemove", onMouseMove, passive);
    document.addEventListener("click", onDocClick, passive);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }
})();

/* 固定「返回上一页」：与 instant 导航兼容，无历史时回站点首页 */
(function () {
  function goBack() {
    var ref = document.referrer;
    var sameOrigin = false;
    try {
      sameOrigin = ref && new URL(ref).origin === window.location.origin;
    } catch (e) {
      /* ignore */
    }
    if (window.history.length > 1 || sameOrigin) {
      window.history.back();
    } else {
      window.location.assign("/");
    }
  }

  function initBackButton() {
    if (document.getElementById("zen-back-btn")) return;
    var btn = document.createElement("button");
    btn.type = "button";
    btn.id = "zen-back-btn";
    btn.className = "zen-back-btn";
    btn.setAttribute("aria-label", "返回上一页");
    btn.setAttribute("title", "返回上一页");
    btn.textContent = "返回";
    btn.addEventListener("click", function (e) {
      e.preventDefault();
      goBack();
    });
    document.body.appendChild(btn);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initBackButton);
  } else {
    initBackButton();
  }
})();
