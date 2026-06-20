import React from "react";

const ORDER = ["system", "light", "dark"];
const LABEL = { system: "시스템", light: "라이트", dark: "다크" };

function applyTheme(t) {
  if (typeof window === "undefined") return;
  const dark = t === "dark" || (t === "system" && window.matchMedia("(prefers-color-scheme: dark)").matches);
  const el = document.documentElement;
  el.classList.toggle("dark", dark);
  el.style.colorScheme = dark ? "dark" : "light";
}

/**
 * flayAI ThemeToggle — header button that cycles 시스템 → 라이트 → 다크, toggling
 * `.dark` on <html>. Icon: monitor (system) / sun (light) / moon (dark).
 * Persists to localStorage("flayai-theme") and follows the OS in system mode.
 */
export function ThemeToggle({ storageKey = "flayai-theme", style, ...rest }) {
  const [theme, setTheme] = React.useState("system");

  React.useEffect(() => {
    let t = "system";
    try { t = localStorage.getItem(storageKey) || "system"; } catch {}
    if (!ORDER.includes(t)) t = "system";
    setTheme(t);
    applyTheme(t);
  }, [storageKey]);

  React.useEffect(() => {
    if (theme !== "system") return;
    const mq = window.matchMedia("(prefers-color-scheme: dark)");
    const onChange = () => applyTheme("system");
    mq.addEventListener("change", onChange);
    return () => mq.removeEventListener("change", onChange);
  }, [theme]);

  const cycle = () => {
    const next = ORDER[(ORDER.indexOf(theme) + 1) % ORDER.length];
    setTheme(next);
    applyTheme(next);
    try { localStorage.setItem(storageKey, next); } catch {}
  };

  const [hover, setHover] = React.useState(false);
  const common = { width: 16, height: 16, viewBox: "0 0 24 24", fill: "none", stroke: "currentColor", strokeWidth: 2, strokeLinecap: "round", strokeLinejoin: "round" };

  return (
    <button
      type="button"
      onClick={cycle}
      onMouseEnter={() => setHover(true)}
      onMouseLeave={() => setHover(false)}
      title={`테마: ${LABEL[theme]} (클릭하여 전환)`}
      aria-label={`테마: ${LABEL[theme]}`}
      style={{ display: "inline-flex", background: "none", border: "none", cursor: "pointer", color: hover ? "var(--foreground)" : "var(--muted-foreground)", transition: "color 0.15s ease", ...style }}
      {...rest}
    >
      {theme === "light" ? (
        <svg {...common}><circle cx="12" cy="12" r="4" /><path d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M6.34 17.66l-1.41 1.41M19.07 4.93l-1.41 1.41" /></svg>
      ) : theme === "dark" ? (
        <svg {...common}><path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z" /></svg>
      ) : (
        <svg {...common}><rect x="2" y="3" width="20" height="14" rx="2" /><path d="M8 21h8M12 17v4" /></svg>
      )}
    </button>
  );
}
