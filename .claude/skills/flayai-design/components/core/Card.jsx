import React from "react";

/**
 * flayAI Card / SectionCard — bordered rounded container with an optional header.
 * Header shows a title, optional mono badge, optional UP/DOWN availability pill,
 * and can be collapsible. Used across admin dashboard and subtitle tool.
 */
export function Card({
  title,
  badge,
  available,
  collapsible = false,
  defaultCollapsed = false,
  children,
  style,
  ...rest
}) {
  const [collapsed, setCollapsed] = React.useState(collapsible && defaultCollapsed);
  const [hover, setHover] = React.useState(false);

  const header = (
    <>
      {collapsible && (
        <span style={{ color: "var(--muted-foreground)", fontSize: "var(--text-xs)", width: 12, textAlign: "center", flexShrink: 0 }}>
          {collapsed ? "▶" : "▼"}
        </span>
      )}
      <span style={{ fontWeight: "var(--weight-semibold)", fontSize: "var(--text-base)" }}>{title}</span>
      {badge && (
        <span style={{ fontFamily: "var(--font-mono)", fontSize: "var(--text-sm)", color: "var(--muted-foreground)", marginLeft: 4 }}>{badge}</span>
      )}
      {available !== undefined && (
        <span
          style={{
            marginLeft: "auto",
            fontSize: "var(--text-xs)",
            fontFamily: "var(--font-mono)",
            padding: "2px 6px",
            borderRadius: "var(--radius-sm)",
            color: available ? "var(--success)" : "var(--destructive)",
            background: available ? "rgba(52,199,89,0.15)" : "rgba(255,59,48,0.15)",
            border: `1px solid ${available ? "rgba(52,199,89,0.3)" : "rgba(255,59,48,0.3)"}`,
          }}
        >
          {available ? "UP" : "DOWN"}
        </span>
      )}
    </>
  );

  const headerStyle = {
    display: "flex",
    alignItems: "center",
    gap: 8,
    padding: "10px 16px",
    background: "var(--card)",
    flexShrink: 0,
    borderBottom: collapsed ? "none" : "1px solid var(--border)",
    width: "100%",
    textAlign: "left",
    cursor: collapsible ? "pointer" : "default",
    transition: "background 0.15s ease",
    ...(collapsible && hover ? { background: "color-mix(in srgb, var(--accent) 40%, var(--card))" } : {}),
  };

  return (
    <div
      style={{
        border: "1px solid var(--border)",
        borderRadius: "var(--radius-lg)",
        overflow: "hidden",
        display: "flex",
        flexDirection: "column",
        background: "var(--card)",
        ...style,
      }}
      {...rest}
    >
      {title !== undefined &&
        (collapsible ? (
          <button type="button" onClick={() => setCollapsed((c) => !c)} onMouseEnter={() => setHover(true)} onMouseLeave={() => setHover(false)} style={headerStyle}>
            {header}
          </button>
        ) : (
          <div style={headerStyle}>{header}</div>
        ))}
      {!collapsed && <div style={{ padding: 16, flex: 1 }}>{children}</div>}
    </div>
  );
}
