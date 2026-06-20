import React from "react";

/**
 * flayAI Chip — fully-rounded pill. Two roles:
 *  - "suggestion": first-screen example queries (border + card bg, hover tints)
 *  - "option": small search-option pills (개수 / 종류), muted fill
 * `selected` gives the Apple-blue active treatment (used in popovers/segments).
 */
export function Chip({ children, role = "suggestion", selected = false, onClick, style, ...rest }) {
  const [hover, setHover] = React.useState(false);
  const base = {
    display: "inline-flex",
    alignItems: "center",
    gap: "6px",
    borderRadius: "var(--radius-full)",
    fontFamily: "var(--font-sans)",
    cursor: onClick ? "pointer" : "default",
    whiteSpace: "nowrap",
    transition: "background 0.15s ease, color 0.15s ease, border-color 0.15s ease",
    letterSpacing: "var(--tracking-tight)",
  };
  const roles = {
    suggestion: {
      padding: "6px 14px",
      fontSize: "var(--text-sm)",
      border: "1px solid var(--border)",
      background: hover ? "var(--accent)" : "var(--card)",
      color: hover ? "var(--foreground)" : "var(--muted-foreground)",
    },
    option: {
      padding: "4px 10px",
      fontSize: "var(--text-xs)",
      border: "1px solid var(--border)",
      background: hover ? "var(--accent)" : "var(--muted)",
      color: "var(--foreground)",
    },
  };
  const sel = selected
    ? {
        border: "1px solid var(--primary)",
        background: "color-mix(in srgb, var(--primary) 18%, transparent)",
        color: "var(--primary)",
      }
    : {};
  return (
    <button
      type="button"
      onClick={onClick}
      onMouseEnter={() => setHover(true)}
      onMouseLeave={() => setHover(false)}
      style={{ ...base, ...(roles[role] || roles.suggestion), ...sel, ...style }}
      {...rest}
    >
      {children}
    </button>
  );
}
