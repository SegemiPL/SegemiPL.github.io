/* Global MathJax configuration. Markdown pages only contain math notation. */
(function () {
  if (window.__zenMathJaxInit) return;
  window.__zenMathJaxInit = true;
  var pending = Promise.resolve();

  function typeset() {
    pending = pending.then(function () {
      if (window.MathJax.typesetPromise) {
        return window.MathJax.typesetPromise();
      }
    }).catch(function (error) {
      console.warn("MathJax could not render this page:", error);
    });
  }

  window.MathJax = {
    tex: {
      inlineMath: [["$", "$"], ["\\(", "\\)"]],
      displayMath: [["$$", "$$"], ["\\[", "\\]"]],
      processEscapes: true,
      processEnvironments: true,
      tags: "none",
    },
    options: { ignoreHtmlClass: "no-mathjax", processHtmlClass: "arithmatex" },
    svg: { fontCache: "global" },
    startup: {
      pageReady: function () {
        return window.MathJax.startup.defaultPageReady().then(function () {
          if (typeof document$ !== "undefined") document$.subscribe(typeset);
        });
      },
    },
  };
  var script = document.createElement("script");
  script.async = true;
  // TeX input only: do not re-typeset MathJax's assistive MathML on navigation.
  script.src = "https://cdn.jsdelivr.net/npm/mathjax@3/es5/tex-chtml.js";
  document.head.appendChild(script);
})();

/* Page enhancements run on initial load and Zensical instant navigation. */
(function () {
  if (window.__zenPageEnhancementsInit) return;
  window.__zenPageEnhancementsInit = true;
  var lastArticle = null;
  var enteredPages = new Set();
  var reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)");
  // Articles outside nav use full page loads, so remember visits per tab too.
  try {
    var previousPages = JSON.parse(sessionStorage.getItem("zen-entered-pages") || "[]");
    if (Array.isArray(previousPages)) enteredPages = new Set(previousPages);
  } catch (error) { /* Motion also works when browser storage is unavailable. */ }

  function enterPage(article) {
    // Instant navigation can notify more than once for the same document.
    if (article === lastArticle) return;
    lastArticle = article;
    article.classList.remove("zen-page-enter");
    var path = window.location.pathname;
    var visited = enteredPages.has(path);
    enteredPages.add(path);
    try {
      sessionStorage.setItem("zen-entered-pages", JSON.stringify(Array.from(enteredPages).slice(-100)));
    } catch (error) { /* Fall back to visits within the current document. */ }
    // Preserve the reader's place when following anchors or going back.
    if (visited || window.location.hash || reducedMotion.matches) return;
    article.classList.add("zen-page-enter");
  }

  function syncTheme() {
    var button = document.querySelector("[data-zen-theme]");
    if (!button) return;
    var dark = document.body.dataset.mdColorScheme === "slate";
    button.setAttribute("aria-label", dark ? "切换到浅色模式" : "切换到深色模式");
    button.title = button.getAttribute("aria-label");
  }

  function syncDrawer() {
    var drawer = document.getElementById("__drawer");
    var button = document.querySelector("[data-zen-menu]");
    if (!drawer || !button) return;
    button.setAttribute("aria-expanded", String(drawer.checked));
    button.setAttribute("aria-label", drawer.checked ? "关闭导航" : "打开导航");
  }

  function closeMenus() {
    document.querySelectorAll(".zen-nav-group[open]").forEach(function (menu) {
      menu.open = false;
    });
  }

  function updateNavigation() {
    var current = decodeURI(window.location.pathname);
    document.querySelectorAll(".zen-site-nav a").forEach(function (link) {
      var path = decodeURI(new URL(link.href).pathname);
      var isHome = link === document.querySelector(".zen-site-nav > a");
      var active = isHome ? current === path : current.startsWith(path);
      if (active) link.setAttribute("aria-current", current === path ? "page" : "location");
      else link.removeAttribute("aria-current");
    });
    document.querySelectorAll(".zen-nav-group").forEach(function (menu) {
      menu.toggleAttribute("data-active", Boolean(menu.querySelector("[aria-current]")));
    });
    closeMenus();
  }

  function onPage() {
    updateNavigation();
    syncTheme();
    syncDrawer();
    var article = document.querySelector("article.md-content__inner");
    if (!article) return;
    enterPage(article);
    var readingTime = article.querySelector("[data-zen-reading-time]");
    if (readingTime && !article.querySelector(".zen-post-list, .zen-empty-state")) {
      var text = article.textContent;
      var chinese = (text.match(/[\u3400-\u9fff]/g) || []).length;
      var words = (text.match(/[a-zA-Z0-9]+/g) || []).length;
      readingTime.textContent = "约 " + Math.max(1, Math.ceil(chinese / 400 + words / 200)) + " 分钟阅读";
    }
  }

  document.addEventListener("click", function (event) {
    if (event.target.closest("[data-zen-search]")) {
      var search = document.querySelector(".md-search__button");
      if (search) search.click();
    }
    var theme = event.target.closest("[data-zen-theme]");
    if (theme) {
      var targetScheme = document.body.dataset.mdColorScheme === "slate" ? "default" : "slate";
      var radio = document.querySelector('input[name="__palette"][data-md-color-scheme="' + targetScheme + '"]');
      if (radio) radio.click();
      syncTheme();
    }
    var menu = event.target.closest("[data-zen-menu]");
    if (menu) {
      var drawer = document.getElementById("__drawer");
      if (drawer) {
        drawer.checked = !drawer.checked;
        drawer.dispatchEvent(new Event("change", { bubbles: true }));
        syncDrawer();
      }
    }
    if (!event.target.closest(".zen-nav-group")) closeMenus();
  });
  document.addEventListener("change", function (event) {
    if (event.target.id === "__drawer") syncDrawer();
  });
  document.addEventListener("keydown", function (event) {
    if (event.key !== "Escape") return;
    var openMenu = document.querySelector(".zen-nav-group[open]");
    if (openMenu) openMenu.querySelector("summary").focus();
    closeMenus();
    var drawer = document.getElementById("__drawer");
    if (drawer && drawer.checked) {
      drawer.checked = false;
      drawer.dispatchEvent(new Event("change", { bubbles: true }));
      document.querySelector("[data-zen-menu]").focus();
    }
  });
  new MutationObserver(syncTheme).observe(document.body, { attributes: true, attributeFilter: ["data-md-color-scheme"] });
  if (typeof document$ !== "undefined" && document$.subscribe) document$.subscribe(onPage);
  else if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", onPage);
  else onPage();
})();
