import React from "react";

/**
 * flayAI Tabs — horizontal tab/nav selector.
 *  - variant "segment": filled active tab (Apple-blue), used for mode switches
 *    like 텍스트→포스터 / 이미지→포스터.
 *  - variant "text": text-only nav (active = foreground, rest = muted), used in
 *    the AppHeader navigation.
 * items: [{ key, label }]. Controlled via `value` + `onChange`.
 */
export function Tabs({ items = [], value, onChange, variant = "segment", style, ...rest }) {
  return (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        gap: variant === "text" ? 14 : 8,
        fontFamily: "var(--font-sans)",
        ...style,
      }}
      {...rest}
    >
      {items.map((it) => {
        const active = it.key === value;
        if (variant === "text") {
          return (
            <TextTab key={it.key} active={active} onClick={() => onChange?.(it.key)}>
              {it.label}
            </TextTab>
          );
        }
        return (
          <button
            key={it.key}
            type="button"
            onClick={() => onChange?.(it.key)}
            style={{
              padding: "5px 12px",
              fontSize: "var(--text-sm)",
              borderRadius: "var(--radius-md)",
              border: "1px solid transparent",
              cursor: "pointer",
              fontWeight: "var(--weight-medium)",
              transition: "background 0.15s ease, color 0.15s ease",
              background: active ? "var(--primary)" : "var(--muted)",
              color: active ? "var(--primary-foreground)" : "var(--foreground)",
              whiteSpace: "nowrap",
            }}
          >
            {it.label}
          </button>
        );
      })}
    </div>
  );
}

function TextTab({ active, onClick, children }) {
  const [hover, setHover] = React.useState(false);
  return (
    <button
      type="button"
      onClick={onClick}
      onMouseEnter={() => setHover(true)}
      onMouseLeave={() => setHover(false)}
      style={{
        background: "none",
        border: "none",
        padding: 0,
        cursor: "pointer",
        fontSize: "var(--text-xs)",
        transition: "color 0.15s ease",
        color: active || hover ? "var(--foreground)" : "var(--muted-foreground)",
      }}
    >
      {children}
    </button>
  );
}
