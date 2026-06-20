import React from "react";

/**
 * flayAI Button — Apple-style control.
 * Variants: primary (Apple blue), secondary (muted fill), ghost (text only),
 * danger (destructive red). Sizes sm | md | lg. Optional leading icon.
 */
export function Button({
  children,
  variant = "primary",
  size = "md",
  disabled = false,
  icon = null,
  type = "button",
  onClick,
  style,
  ...rest
}) {
  // Sizes drive padding/type only. Radius is per-variant: the primary CTA is a
  // full pill (the Apple action signal); utility variants use radius-sm (8px).
  const sizes = {
    sm: { padding: "8px 15px", fontSize: "var(--text-xs)", gap: "5px" },
    md: { padding: "11px 22px", fontSize: "var(--text-sm)", gap: "6px" },
    lg: { padding: "14px 28px", fontSize: "var(--text-base)", gap: "8px" },
  };
  const variants = {
    primary: { background: "var(--primary)", color: "var(--primary-foreground)", border: "1px solid transparent", radius: "var(--radius-pill)" },
    secondary: { background: "var(--muted)", color: "var(--foreground)", border: "1px solid var(--border)", radius: "var(--radius-sm)" },
    ghost: { background: "transparent", color: "var(--foreground)", border: "1px solid transparent", radius: "var(--radius-sm)" },
    danger: { background: "transparent", color: "var(--destructive)", border: "1px solid var(--destructive)", radius: "var(--radius-sm)" },
  };
  const s = sizes[size] || sizes.md;
  const v = variants[variant] || variants.primary;

  const [hover, setHover] = React.useState(false);
  const [active, setActive] = React.useState(false);

  const hoverBg = {
    primary: "color-mix(in srgb, var(--primary) 88%, black)",
    secondary: "var(--accent)",
    ghost: "var(--accent)",
    danger: "color-mix(in srgb, var(--destructive) 12%, transparent)",
  }[variant];

  return (
    <button
      type={type}
      disabled={disabled}
      onClick={onClick}
      onMouseEnter={() => setHover(true)}
      onMouseLeave={() => { setHover(false); setActive(false); }}
      onMouseDown={() => setActive(true)}
      onMouseUp={() => setActive(false)}
      style={{
        display: "inline-flex",
        alignItems: "center",
        justifyContent: "center",
        gap: s.gap,
        fontFamily: "var(--font-sans)",
        fontWeight: "var(--weight-medium)",
        fontSize: s.fontSize,
        padding: s.padding,
        borderRadius: v.radius,
        cursor: disabled ? "not-allowed" : "pointer",
        opacity: disabled ? 0.4 : 1,
        letterSpacing: "var(--tracking-tight)",
        transition: "background 0.15s ease, transform 0.08s ease, color 0.15s ease",
        transform: active && !disabled ? "scale(0.95)" : "scale(1)",
        whiteSpace: "nowrap",
        ...v,
        background: hover && !disabled ? hoverBg : v.background,
        ...style,
      }}
      {...rest}
    >
      {icon && <span style={{ display: "inline-flex", flexShrink: 0 }}>{icon}</span>}
      {children}
    </button>
  );
}
