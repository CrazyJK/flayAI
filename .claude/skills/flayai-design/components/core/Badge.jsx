import React from "react";

/**
 * flayAI Badge — small status/label pill.
 * tone: instance | archive | success | running | failed | warning | neutral | info
 * Renders a translucent tinted fill + matching border + mono text, matching the
 * KindBadge / status chips used across chat, subtitle queue and admin.
 */
export function Badge({ children, tone = "neutral", mono = true, style, ...rest }) {
  const tones = {
    instance: { fg: "var(--kind-instance)", base: "16,185,129" },
    archive: { fg: "var(--kind-archive)", base: "113,113,122" },
    success: { fg: "var(--success)", base: "52,199,89" },
    running: { fg: "var(--primary)", base: "10,132,255" },
    info: { fg: "var(--primary)", base: "10,132,255" },
    failed: { fg: "var(--destructive)", base: "255,59,48" },
    warning: { fg: "#d97706", base: "245,158,11" },
    neutral: { fg: "var(--muted-foreground)", base: "150,150,150" },
  };
  const t = tones[tone] || tones.neutral;
  return (
    <span
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: "4px",
        padding: "2px 7px",
        fontSize: "var(--text-xs)",
        lineHeight: 1.4,
        fontFamily: mono ? "var(--font-mono)" : "var(--font-sans)",
        borderRadius: "var(--radius-sm)",
        color: t.fg,
        background: `rgba(${t.base}, 0.15)`,
        border: `1px solid rgba(${t.base}, 0.35)`,
        whiteSpace: "nowrap",
        ...style,
      }}
      {...rest}
    >
      {children}
    </span>
  );
}
