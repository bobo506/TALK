// 外观模式：自动（08:00–18:00 白天，其余夜间）/ 白天 / 夜间。
// 只负责主题状态与顶部控件；具体颜色由 CSS 变量按 data-theme 切换。
(function () {
  "use strict";
  const STORAGE_KEY = "talk-theme-mode";
  const MODES = ["auto", "light", "dark"];
  const DAY_START = 8;
  const NIGHT_START = 18;

  function storedMode() {
    try {
      const raw = window.localStorage.getItem(STORAGE_KEY);
      return MODES.includes(raw) ? raw : "auto";
    } catch (_) {
      return "auto";
    }
  }

  function autoTheme(now) {
    const hour = (now || new Date()).getHours();
    return hour >= DAY_START && hour < NIGHT_START ? "light" : "dark";
  }

  function resolve(mode, now) {
    const normalized = MODES.includes(mode) ? mode : "auto";
    return normalized === "auto" ? autoTheme(now) : normalized;
  }

  function apply(mode) {
    const root = document.documentElement;
    root.dataset.theme = resolve(mode);
    root.dataset.themeMode = mode;
    for (const button of document.querySelectorAll("[data-theme-mode]")) {
      const active = button.dataset.themeMode === mode;
      button.classList.toggle("is-active", active);
      button.setAttribute("aria-pressed", String(active));
    }
  }

  function save(mode) {
    try {
      window.localStorage.setItem(STORAGE_KEY, mode);
    } catch (_) {
      /* 存储不可用时只在本次会话生效。 */
    }
  }

  function scheduleNextBoundary() {
    window.clearTimeout(scheduleNextBoundary.timer);
    const now = new Date();
    const next = new Date(now);
    next.setHours(now.getHours() < DAY_START ? DAY_START : now.getHours() < NIGHT_START ? NIGHT_START : DAY_START, 0, 0, 0);
    if (next <= now) next.setDate(next.getDate() + 1);
    scheduleNextBoundary.timer = window.setTimeout(() => {
      apply(storedMode());
      scheduleNextBoundary();
    }, Math.max(1000, next.getTime() - now.getTime()));
  }

  function bind() {
    const group = document.getElementById("theme-switch");
    if (group) {
      group.addEventListener("click", event => {
        const button = event.target.closest("[data-theme-mode]");
        if (!button || !group.contains(button)) return;
        const mode = button.dataset.themeMode;
        if (!MODES.includes(mode)) return;
        save(mode);
        apply(mode);
        scheduleNextBoundary();
      });
    }
    document.addEventListener("visibilitychange", () => {
      if (!document.hidden) apply(storedMode());
    });
    apply(storedMode());
    scheduleNextBoundary();
  }

  window.talkTheme = { autoTheme, resolve, apply: mode => { apply(mode); }, mode: storedMode };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", bind, { once: true });
  } else {
    bind();
  }
})();
