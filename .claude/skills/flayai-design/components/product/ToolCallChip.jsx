import React from "react";

/**
 * flayAI ToolCallChip — the small centered "⚙ tool_name(args)" line shown while
 * the assistant invokes a tool, with a ▼ to expand truncated args. Mono, muted,
 * cyan tool name. Also renders the "↳ N items" / "↳ name → 0 items" result line
 * when `result` is provided instead of args.
 */
export function ToolCallChip({ name, args, result, style, ...rest }) {
  const [expanded, setExpanded] = React.useState(false);

  // Result line variant
  if (result !== undefined) {
    return (
      <div
        style={{
          fontFamily: "var(--font-mono)",
          fontSize: "var(--text-xs)",
          color: "var(--muted-foreground)",
          textAlign: "center",
          ...style,
        }}
        {...rest}
      >
        ↳ {result}
      </div>
    );
  }

  const argsStr = args ? JSON.stringify(args) : "";
  const truncatable = argsStr.length > 80;
  const displayed = truncatable && !expanded ? argsStr.slice(0, 80) + "…" : argsStr;

  return (
    <div
      style={{
        fontFamily: "var(--font-mono)",
        fontSize: "var(--text-xs)",
        color: "var(--muted-foreground)",
        display: "flex",
        alignItems: "flex-start",
        gap: 4,
        flexWrap: "wrap",
        justifyContent: "center",
        ...style,
      }}
      {...rest}
    >
      <span style={{ color: "var(--primary)", flexShrink: 0 }}>⚙ {name}</span>
      <span style={{ wordBreak: "break-all" }}>{argsStr.length > 0 ? `(${displayed})` : "()"}</span>
      {truncatable && (
        <button
          type="button"
          onClick={() => setExpanded((v) => !v)}
          title={expanded ? "접기" : "펼치기"}
          style={{ flexShrink: 0, background: "none", border: "none", cursor: "pointer", color: "var(--muted-foreground)", lineHeight: 1 }}
        >
          {expanded ? "▲" : "▼"}
        </button>
      )}
    </div>
  );
}
