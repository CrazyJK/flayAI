/* @ds-bundle: {"format":3,"namespace":"FlayAIDesignSystem_105b78","components":[{"name":"Badge","sourcePath":"components/core/Badge.jsx"},{"name":"Button","sourcePath":"components/core/Button.jsx"},{"name":"Card","sourcePath":"components/core/Card.jsx"},{"name":"Chip","sourcePath":"components/core/Chip.jsx"},{"name":"Tabs","sourcePath":"components/core/Tabs.jsx"},{"name":"Composer","sourcePath":"components/product/Composer.jsx"},{"name":"ThemeToggle","sourcePath":"components/product/ThemeToggle.jsx"},{"name":"ToolCallChip","sourcePath":"components/product/ToolCallChip.jsx"},{"name":"VideoCard","sourcePath":"components/product/VideoCard.jsx"}],"sourceHashes":{"components/core/Badge.jsx":"6f1c4d32629d","components/core/Button.jsx":"55093136df59","components/core/Card.jsx":"821857411f65","components/core/Chip.jsx":"c120a75ba5e4","components/core/Tabs.jsx":"9571edd6aba1","components/product/Composer.jsx":"5b0a1b6f7546","components/product/ThemeToggle.jsx":"4837f90fc9e7","components/product/ToolCallChip.jsx":"f7d36757099e","components/product/VideoCard.jsx":"c4365d083770","ui_kits/admin/screens.jsx":"1610da0b45d0","ui_kits/diary/screens.jsx":"0a6ab4dc815e","ui_kits/search-chat/screens.jsx":"2aa38c8c82dc"},"inlinedExternals":[],"unexposedExports":[]} */

(() => {

const __ds_ns = (window.FlayAIDesignSystem_105b78 = window.FlayAIDesignSystem_105b78 || {});

const __ds_scope = {};

(__ds_ns.__errors = __ds_ns.__errors || []);

// components/core/Badge.jsx
try { (() => {
function _extends() { return _extends = Object.assign ? Object.assign.bind() : function (n) { for (var e = 1; e < arguments.length; e++) { var t = arguments[e]; for (var r in t) ({}).hasOwnProperty.call(t, r) && (n[r] = t[r]); } return n; }, _extends.apply(null, arguments); }
/**
 * flayAI Badge — small status/label pill.
 * tone: instance | archive | success | running | failed | warning | neutral | info
 * Renders a translucent tinted fill + matching border + mono text, matching the
 * KindBadge / status chips used across chat, subtitle queue and admin.
 */
function Badge({
  children,
  tone = "neutral",
  mono = true,
  style,
  ...rest
}) {
  const tones = {
    instance: {
      fg: "var(--kind-instance)",
      base: "16,185,129"
    },
    archive: {
      fg: "var(--kind-archive)",
      base: "113,113,122"
    },
    success: {
      fg: "var(--success)",
      base: "52,199,89"
    },
    running: {
      fg: "var(--primary)",
      base: "10,132,255"
    },
    info: {
      fg: "var(--primary)",
      base: "10,132,255"
    },
    failed: {
      fg: "var(--destructive)",
      base: "255,59,48"
    },
    warning: {
      fg: "#d97706",
      base: "245,158,11"
    },
    neutral: {
      fg: "var(--muted-foreground)",
      base: "150,150,150"
    }
  };
  const t = tones[tone] || tones.neutral;
  return /*#__PURE__*/React.createElement("span", _extends({
    style: {
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
      ...style
    }
  }, rest), children);
}
Object.assign(__ds_scope, { Badge });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/core/Badge.jsx", error: String((e && e.message) || e) }); }

// components/core/Button.jsx
try { (() => {
function _extends() { return _extends = Object.assign ? Object.assign.bind() : function (n) { for (var e = 1; e < arguments.length; e++) { var t = arguments[e]; for (var r in t) ({}).hasOwnProperty.call(t, r) && (n[r] = t[r]); } return n; }, _extends.apply(null, arguments); }
/**
 * flayAI Button — Apple-style control.
 * Variants: primary (Apple blue), secondary (muted fill), ghost (text only),
 * danger (destructive red). Sizes sm | md | lg. Optional leading icon.
 */
function Button({
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
    sm: {
      padding: "8px 15px",
      fontSize: "var(--text-xs)",
      gap: "5px"
    },
    md: {
      padding: "11px 22px",
      fontSize: "var(--text-sm)",
      gap: "6px"
    },
    lg: {
      padding: "14px 28px",
      fontSize: "var(--text-base)",
      gap: "8px"
    }
  };
  const variants = {
    primary: {
      background: "var(--primary)",
      color: "var(--primary-foreground)",
      border: "1px solid transparent",
      radius: "var(--radius-pill)"
    },
    secondary: {
      background: "var(--muted)",
      color: "var(--foreground)",
      border: "1px solid var(--border)",
      radius: "var(--radius-sm)"
    },
    ghost: {
      background: "transparent",
      color: "var(--foreground)",
      border: "1px solid transparent",
      radius: "var(--radius-sm)"
    },
    danger: {
      background: "transparent",
      color: "var(--destructive)",
      border: "1px solid var(--destructive)",
      radius: "var(--radius-sm)"
    }
  };
  const s = sizes[size] || sizes.md;
  const v = variants[variant] || variants.primary;
  const [hover, setHover] = React.useState(false);
  const [active, setActive] = React.useState(false);
  const hoverBg = {
    primary: "color-mix(in srgb, var(--primary) 88%, black)",
    secondary: "var(--accent)",
    ghost: "var(--accent)",
    danger: "color-mix(in srgb, var(--destructive) 12%, transparent)"
  }[variant];
  return /*#__PURE__*/React.createElement("button", _extends({
    type: type,
    disabled: disabled,
    onClick: onClick,
    onMouseEnter: () => setHover(true),
    onMouseLeave: () => {
      setHover(false);
      setActive(false);
    },
    onMouseDown: () => setActive(true),
    onMouseUp: () => setActive(false),
    style: {
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
      ...style
    }
  }, rest), icon && /*#__PURE__*/React.createElement("span", {
    style: {
      display: "inline-flex",
      flexShrink: 0
    }
  }, icon), children);
}
Object.assign(__ds_scope, { Button });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/core/Button.jsx", error: String((e && e.message) || e) }); }

// components/core/Card.jsx
try { (() => {
function _extends() { return _extends = Object.assign ? Object.assign.bind() : function (n) { for (var e = 1; e < arguments.length; e++) { var t = arguments[e]; for (var r in t) ({}).hasOwnProperty.call(t, r) && (n[r] = t[r]); } return n; }, _extends.apply(null, arguments); }
/**
 * flayAI Card / SectionCard — bordered rounded container with an optional header.
 * Header shows a title, optional mono badge, optional UP/DOWN availability pill,
 * and can be collapsible. Used across admin dashboard and subtitle tool.
 */
function Card({
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
  const header = /*#__PURE__*/React.createElement(React.Fragment, null, collapsible && /*#__PURE__*/React.createElement("span", {
    style: {
      color: "var(--muted-foreground)",
      fontSize: "var(--text-xs)",
      width: 12,
      textAlign: "center",
      flexShrink: 0
    }
  }, collapsed ? "▶" : "▼"), /*#__PURE__*/React.createElement("span", {
    style: {
      fontWeight: "var(--weight-semibold)",
      fontSize: "var(--text-base)"
    }
  }, title), badge && /*#__PURE__*/React.createElement("span", {
    style: {
      fontFamily: "var(--font-mono)",
      fontSize: "var(--text-sm)",
      color: "var(--muted-foreground)",
      marginLeft: 4
    }
  }, badge), available !== undefined && /*#__PURE__*/React.createElement("span", {
    style: {
      marginLeft: "auto",
      fontSize: "var(--text-xs)",
      fontFamily: "var(--font-mono)",
      padding: "2px 6px",
      borderRadius: "var(--radius-sm)",
      color: available ? "var(--success)" : "var(--destructive)",
      background: available ? "rgba(52,199,89,0.15)" : "rgba(255,59,48,0.15)",
      border: `1px solid ${available ? "rgba(52,199,89,0.3)" : "rgba(255,59,48,0.3)"}`
    }
  }, available ? "UP" : "DOWN"));
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
    ...(collapsible && hover ? {
      background: "color-mix(in srgb, var(--accent) 40%, var(--card))"
    } : {})
  };
  return /*#__PURE__*/React.createElement("div", _extends({
    style: {
      border: "1px solid var(--border)",
      borderRadius: "var(--radius-lg)",
      overflow: "hidden",
      display: "flex",
      flexDirection: "column",
      background: "var(--card)",
      ...style
    }
  }, rest), title !== undefined && (collapsible ? /*#__PURE__*/React.createElement("button", {
    type: "button",
    onClick: () => setCollapsed(c => !c),
    onMouseEnter: () => setHover(true),
    onMouseLeave: () => setHover(false),
    style: headerStyle
  }, header) : /*#__PURE__*/React.createElement("div", {
    style: headerStyle
  }, header)), !collapsed && /*#__PURE__*/React.createElement("div", {
    style: {
      padding: 16,
      flex: 1
    }
  }, children));
}
Object.assign(__ds_scope, { Card });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/core/Card.jsx", error: String((e && e.message) || e) }); }

// components/core/Chip.jsx
try { (() => {
function _extends() { return _extends = Object.assign ? Object.assign.bind() : function (n) { for (var e = 1; e < arguments.length; e++) { var t = arguments[e]; for (var r in t) ({}).hasOwnProperty.call(t, r) && (n[r] = t[r]); } return n; }, _extends.apply(null, arguments); }
/**
 * flayAI Chip — fully-rounded pill. Two roles:
 *  - "suggestion": first-screen example queries (border + card bg, hover tints)
 *  - "option": small search-option pills (개수 / 종류), muted fill
 * `selected` gives the Apple-blue active treatment (used in popovers/segments).
 */
function Chip({
  children,
  role = "suggestion",
  selected = false,
  onClick,
  style,
  ...rest
}) {
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
    letterSpacing: "var(--tracking-tight)"
  };
  const roles = {
    suggestion: {
      padding: "6px 14px",
      fontSize: "var(--text-sm)",
      border: "1px solid var(--border)",
      background: hover ? "var(--accent)" : "var(--card)",
      color: hover ? "var(--foreground)" : "var(--muted-foreground)"
    },
    option: {
      padding: "4px 10px",
      fontSize: "var(--text-xs)",
      border: "1px solid var(--border)",
      background: hover ? "var(--accent)" : "var(--muted)",
      color: "var(--foreground)"
    }
  };
  const sel = selected ? {
    border: "1px solid var(--primary)",
    background: "color-mix(in srgb, var(--primary) 18%, transparent)",
    color: "var(--primary)"
  } : {};
  return /*#__PURE__*/React.createElement("button", _extends({
    type: "button",
    onClick: onClick,
    onMouseEnter: () => setHover(true),
    onMouseLeave: () => setHover(false),
    style: {
      ...base,
      ...(roles[role] || roles.suggestion),
      ...sel,
      ...style
    }
  }, rest), children);
}
Object.assign(__ds_scope, { Chip });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/core/Chip.jsx", error: String((e && e.message) || e) }); }

// components/core/Tabs.jsx
try { (() => {
function _extends() { return _extends = Object.assign ? Object.assign.bind() : function (n) { for (var e = 1; e < arguments.length; e++) { var t = arguments[e]; for (var r in t) ({}).hasOwnProperty.call(t, r) && (n[r] = t[r]); } return n; }, _extends.apply(null, arguments); }
/**
 * flayAI Tabs — horizontal tab/nav selector.
 *  - variant "segment": filled active tab (Apple-blue), used for mode switches
 *    like 텍스트→포스터 / 이미지→포스터.
 *  - variant "text": text-only nav (active = foreground, rest = muted), used in
 *    the AppHeader navigation.
 * items: [{ key, label }]. Controlled via `value` + `onChange`.
 */
function Tabs({
  items = [],
  value,
  onChange,
  variant = "segment",
  style,
  ...rest
}) {
  return /*#__PURE__*/React.createElement("div", _extends({
    style: {
      display: "flex",
      alignItems: "center",
      gap: variant === "text" ? 14 : 8,
      fontFamily: "var(--font-sans)",
      ...style
    }
  }, rest), items.map(it => {
    const active = it.key === value;
    if (variant === "text") {
      return /*#__PURE__*/React.createElement(TextTab, {
        key: it.key,
        active: active,
        onClick: () => onChange?.(it.key)
      }, it.label);
    }
    return /*#__PURE__*/React.createElement("button", {
      key: it.key,
      type: "button",
      onClick: () => onChange?.(it.key),
      style: {
        padding: "5px 12px",
        fontSize: "var(--text-sm)",
        borderRadius: "var(--radius-md)",
        border: "1px solid transparent",
        cursor: "pointer",
        fontWeight: "var(--weight-medium)",
        transition: "background 0.15s ease, color 0.15s ease",
        background: active ? "var(--primary)" : "var(--muted)",
        color: active ? "var(--primary-foreground)" : "var(--foreground)",
        whiteSpace: "nowrap"
      }
    }, it.label);
  }));
}
function TextTab({
  active,
  onClick,
  children
}) {
  const [hover, setHover] = React.useState(false);
  return /*#__PURE__*/React.createElement("button", {
    type: "button",
    onClick: onClick,
    onMouseEnter: () => setHover(true),
    onMouseLeave: () => setHover(false),
    style: {
      background: "none",
      border: "none",
      padding: 0,
      cursor: "pointer",
      fontSize: "var(--text-xs)",
      transition: "color 0.15s ease",
      color: active || hover ? "var(--foreground)" : "var(--muted-foreground)"
    }
  }, children);
}
Object.assign(__ds_scope, { Tabs });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/core/Tabs.jsx", error: String((e && e.message) || e) }); }

// components/product/Composer.jsx
try { (() => {
function _extends() { return _extends = Object.assign ? Object.assign.bind() : function (n) { for (var e = 1; e < arguments.length; e++) { var t = arguments[e]; for (var r in t) ({}).hasOwnProperty.call(t, r) && (n[r] = t[r]); } return n; }, _extends.apply(null, arguments); }
/**
 * flayAI Composer — the chat input box (Copilot/Claude-style): a rounded card
 * wrapping an auto-growing textarea on top, with an options row beneath (left:
 * option pills via `options`; right: send / stop button). Focus tints the
 * border blue with a soft ring.
 *
 * `hero` = large centered first-screen variant; otherwise the compact docked one.
 */
function Composer({
  value = "",
  onChange,
  onSubmit,
  onStop,
  busy = false,
  hero = false,
  placeholder = "무엇을 찾을까요?",
  options = null,
  style,
  ...rest
}) {
  const [focus, setFocus] = React.useState(false);
  const taRef = React.useRef(null);
  const grow = el => {
    if (!el) return;
    el.style.height = "auto";
    el.style.height = Math.min(el.scrollHeight, 200) + "px";
  };
  return /*#__PURE__*/React.createElement("form", _extends({
    onSubmit: e => {
      e.preventDefault();
      onSubmit?.(value);
    },
    style: {
      width: "100%",
      maxWidth: hero ? "var(--col-hero)" : "var(--col-header)",
      margin: hero ? 0 : "0 auto",
      ...style
    }
  }, rest), /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      flexDirection: "column",
      gap: 8,
      borderRadius: "var(--radius-2xl)",
      border: `1px solid ${focus ? "var(--primary)" : "var(--border)"}`,
      background: "var(--card)",
      padding: hero ? "14px 16px 8px" : "12px 12px 6px",
      boxShadow: hero ? "var(--shadow-lg)" : "var(--shadow-sm)",
      transition: "border-color 0.15s ease, box-shadow 0.15s ease",
      ...(focus ? {
        boxShadow: "var(--ring)"
      } : {})
    }
  }, /*#__PURE__*/React.createElement("textarea", {
    ref: taRef,
    rows: 1,
    value: value,
    placeholder: placeholder,
    disabled: busy,
    onFocus: () => setFocus(true),
    onBlur: () => setFocus(false),
    onChange: e => {
      onChange?.(e.target.value);
      grow(e.currentTarget);
    },
    onKeyDown: e => {
      if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
        e.preventDefault();
        onSubmit?.(value);
      }
    },
    style: {
      width: "100%",
      maxHeight: 200,
      resize: "none",
      outline: "none",
      border: "none",
      background: "transparent",
      color: "var(--foreground)",
      fontFamily: "var(--font-sans)",
      fontSize: hero ? "var(--text-lg)" : "var(--text-sm)",
      letterSpacing: "var(--tracking-tight)",
      lineHeight: "var(--leading-normal)"
    }
  }), /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      alignItems: "center",
      gap: 8
    }
  }, options, busy ? /*#__PURE__*/React.createElement("button", {
    type: "button",
    onClick: onStop,
    title: "\uC911\uB2E8",
    "aria-label": "\uC911\uB2E8",
    style: {
      marginLeft: "auto",
      display: "inline-flex",
      background: "none",
      border: "none",
      cursor: "pointer",
      color: "var(--destructive)"
    }
  }, /*#__PURE__*/React.createElement("svg", {
    width: hero ? 22 : 18,
    height: hero ? 22 : 18,
    viewBox: "0 0 24 24",
    fill: "currentColor"
  }, /*#__PURE__*/React.createElement("rect", {
    x: "6",
    y: "6",
    width: "12",
    height: "12",
    rx: "2"
  }))) : /*#__PURE__*/React.createElement("button", {
    type: "submit",
    title: "\uC804\uC1A1",
    "aria-label": "\uC804\uC1A1",
    disabled: !value.trim(),
    style: {
      marginLeft: "auto",
      display: "inline-flex",
      background: "none",
      border: "none",
      cursor: value.trim() ? "pointer" : "not-allowed",
      color: value.trim() ? "var(--primary)" : "var(--muted-foreground)",
      opacity: value.trim() ? 1 : 0.4
    }
  }, /*#__PURE__*/React.createElement("svg", {
    width: hero ? 24 : 20,
    height: hero ? 24 : 20,
    viewBox: "0 0 24 24",
    fill: "none",
    stroke: "currentColor",
    strokeWidth: "2",
    strokeLinecap: "round",
    strokeLinejoin: "round"
  }, /*#__PURE__*/React.createElement("polyline", {
    points: "9 10 4 15 9 20"
  }), /*#__PURE__*/React.createElement("path", {
    d: "M20 4v7a4 4 0 0 1-4 4H4"
  }))))));
}
Object.assign(__ds_scope, { Composer });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/product/Composer.jsx", error: String((e && e.message) || e) }); }

// components/product/ThemeToggle.jsx
try { (() => {
function _extends() { return _extends = Object.assign ? Object.assign.bind() : function (n) { for (var e = 1; e < arguments.length; e++) { var t = arguments[e]; for (var r in t) ({}).hasOwnProperty.call(t, r) && (n[r] = t[r]); } return n; }, _extends.apply(null, arguments); }
const ORDER = ["system", "light", "dark"];
const LABEL = {
  system: "시스템",
  light: "라이트",
  dark: "다크"
};
function applyTheme(t) {
  if (typeof window === "undefined") return;
  const dark = t === "dark" || t === "system" && window.matchMedia("(prefers-color-scheme: dark)").matches;
  const el = document.documentElement;
  el.classList.toggle("dark", dark);
  el.style.colorScheme = dark ? "dark" : "light";
}

/**
 * flayAI ThemeToggle — header button that cycles 시스템 → 라이트 → 다크, toggling
 * `.dark` on <html>. Icon: monitor (system) / sun (light) / moon (dark).
 * Persists to localStorage("flayai-theme") and follows the OS in system mode.
 */
function ThemeToggle({
  storageKey = "flayai-theme",
  style,
  ...rest
}) {
  const [theme, setTheme] = React.useState("system");
  React.useEffect(() => {
    let t = "system";
    try {
      t = localStorage.getItem(storageKey) || "system";
    } catch {}
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
    try {
      localStorage.setItem(storageKey, next);
    } catch {}
  };
  const [hover, setHover] = React.useState(false);
  const common = {
    width: 16,
    height: 16,
    viewBox: "0 0 24 24",
    fill: "none",
    stroke: "currentColor",
    strokeWidth: 2,
    strokeLinecap: "round",
    strokeLinejoin: "round"
  };
  return /*#__PURE__*/React.createElement("button", _extends({
    type: "button",
    onClick: cycle,
    onMouseEnter: () => setHover(true),
    onMouseLeave: () => setHover(false),
    title: `테마: ${LABEL[theme]} (클릭하여 전환)`,
    "aria-label": `테마: ${LABEL[theme]}`,
    style: {
      display: "inline-flex",
      background: "none",
      border: "none",
      cursor: "pointer",
      color: hover ? "var(--foreground)" : "var(--muted-foreground)",
      transition: "color 0.15s ease",
      ...style
    }
  }, rest), theme === "light" ? /*#__PURE__*/React.createElement("svg", common, /*#__PURE__*/React.createElement("circle", {
    cx: "12",
    cy: "12",
    r: "4"
  }), /*#__PURE__*/React.createElement("path", {
    d: "M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M6.34 17.66l-1.41 1.41M19.07 4.93l-1.41 1.41"
  })) : theme === "dark" ? /*#__PURE__*/React.createElement("svg", common, /*#__PURE__*/React.createElement("path", {
    d: "M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"
  })) : /*#__PURE__*/React.createElement("svg", common, /*#__PURE__*/React.createElement("rect", {
    x: "2",
    y: "3",
    width: "20",
    height: "14",
    rx: "2"
  }), /*#__PURE__*/React.createElement("path", {
    d: "M8 21h8M12 17v4"
  })));
}
Object.assign(__ds_scope, { ThemeToggle });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/product/ThemeToggle.jsx", error: String((e && e.message) || e) }); }

// components/product/ToolCallChip.jsx
try { (() => {
function _extends() { return _extends = Object.assign ? Object.assign.bind() : function (n) { for (var e = 1; e < arguments.length; e++) { var t = arguments[e]; for (var r in t) ({}).hasOwnProperty.call(t, r) && (n[r] = t[r]); } return n; }, _extends.apply(null, arguments); }
/**
 * flayAI ToolCallChip — the small centered "⚙ tool_name(args)" line shown while
 * the assistant invokes a tool, with a ▼ to expand truncated args. Mono, muted,
 * cyan tool name. Also renders the "↳ N items" / "↳ name → 0 items" result line
 * when `result` is provided instead of args.
 */
function ToolCallChip({
  name,
  args,
  result,
  style,
  ...rest
}) {
  const [expanded, setExpanded] = React.useState(false);

  // Result line variant
  if (result !== undefined) {
    return /*#__PURE__*/React.createElement("div", _extends({
      style: {
        fontFamily: "var(--font-mono)",
        fontSize: "var(--text-xs)",
        color: "var(--muted-foreground)",
        textAlign: "center",
        ...style
      }
    }, rest), "\u21B3 ", result);
  }
  const argsStr = args ? JSON.stringify(args) : "";
  const truncatable = argsStr.length > 80;
  const displayed = truncatable && !expanded ? argsStr.slice(0, 80) + "…" : argsStr;
  return /*#__PURE__*/React.createElement("div", _extends({
    style: {
      fontFamily: "var(--font-mono)",
      fontSize: "var(--text-xs)",
      color: "var(--muted-foreground)",
      display: "flex",
      alignItems: "flex-start",
      gap: 4,
      flexWrap: "wrap",
      justifyContent: "center",
      ...style
    }
  }, rest), /*#__PURE__*/React.createElement("span", {
    style: {
      color: "var(--primary)",
      flexShrink: 0
    }
  }, "\u2699 ", name), /*#__PURE__*/React.createElement("span", {
    style: {
      wordBreak: "break-all"
    }
  }, argsStr.length > 0 ? `(${displayed})` : "()"), truncatable && /*#__PURE__*/React.createElement("button", {
    type: "button",
    onClick: () => setExpanded(v => !v),
    title: expanded ? "접기" : "펼치기",
    style: {
      flexShrink: 0,
      background: "none",
      border: "none",
      cursor: "pointer",
      color: "var(--muted-foreground)",
      lineHeight: 1
    }
  }, expanded ? "▲" : "▼"));
}
Object.assign(__ds_scope, { ToolCallChip });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/product/ToolCallChip.jsx", error: String((e && e.message) || e) }); }

// components/product/VideoCard.jsx
try { (() => {
function _extends() { return _extends = Object.assign ? Object.assign.bind() : function (n) { for (var e = 1; e < arguments.length; e++) { var t = arguments[e]; for (var r in t) ({}).hasOwnProperty.call(t, r) && (n[r] = t[r]); } return n; }, _extends.apply(null, arguments); }
/**
 * flayAI VideoCard — the signature search-result poster card.
 * 400:269 poster with top + bottom protection scrims. Top overlay: opus code
 * (amber, mono), kind badge, rank stars, score. Bottom overlay: title + meta
 * (studio, year, actresses, plays, likes). Click opens the flay popup.
 *
 * Pass either a `hit` object or the individual fields. Poster image via
 * `poster` URL; falls back to a muted block if it fails to load.
 */
function VideoCard({
  hit = {},
  poster,
  onOpen,
  style,
  ...rest
}) {
  const h = hit;
  const title = h.title || h.title_ko || h.title_jp || h.opus;
  const posterUrl = poster || h.poster;
  const [hover, setHover] = React.useState(false);
  const [imgOk, setImgOk] = React.useState(true);
  const isInstance = h.kind === "instance";
  return /*#__PURE__*/React.createElement("div", _extends({
    onClick: () => onOpen?.(h.opus),
    onMouseEnter: () => setHover(true),
    onMouseLeave: () => setHover(false),
    title: h.opus ? `팝업으로 열기: ${h.opus}` : undefined,
    style: {
      position: "relative",
      aspectRatio: "400 / 269",
      borderRadius: "var(--radius-md)",
      overflow: "hidden",
      border: "1px solid var(--border)",
      cursor: onOpen ? "pointer" : "default",
      background: "var(--muted)",
      transform: hover && onOpen ? "translateY(-1px)" : "none",
      boxShadow: hover && onOpen ? "var(--shadow-md)" : "none",
      transition: "transform 0.15s ease, box-shadow 0.15s ease",
      ...style
    }
  }, rest), posterUrl && imgOk && /*#__PURE__*/React.createElement("img", {
    src: posterUrl,
    alt: h.opus || "",
    onError: () => setImgOk(false),
    style: {
      position: "absolute",
      inset: 0,
      width: "100%",
      height: "100%",
      objectFit: "cover"
    }
  }), /*#__PURE__*/React.createElement("div", {
    style: {
      position: "absolute",
      top: 0,
      left: 0,
      right: 0,
      padding: "8px",
      background: "var(--poster-scrim-top)",
      textShadow: "0 1px 2px rgba(0,0,0,0.9)"
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      alignItems: "center",
      gap: 6,
      flexWrap: "wrap"
    }
  }, h.opus && /*#__PURE__*/React.createElement("span", {
    style: {
      fontFamily: "var(--font-mono)",
      fontSize: "var(--text-sm)",
      color: "var(--opus-accent)"
    }
  }, h.opus), h.kind && /*#__PURE__*/React.createElement("span", {
    style: {
      fontFamily: "var(--font-mono)",
      fontSize: "var(--text-xs)",
      padding: "2px 6px",
      borderRadius: "var(--radius-sm)",
      color: isInstance ? "#bbf7d0" : "#e4e4e7",
      background: isInstance ? "rgba(16,185,129,0.3)" : "rgba(113,113,122,0.35)",
      border: `1px solid ${isInstance ? "rgba(16,185,129,0.5)" : "rgba(113,113,122,0.5)"}`
    }
  }, isInstance ? "INSTANCE" : "ARCHIVE"), typeof h.rank === "number" && h.rank > 0 && /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: "var(--text-xs)",
      padding: "2px 6px",
      borderRadius: "var(--radius-sm)",
      background: "rgba(234,179,8,0.3)",
      color: "#fef9c3"
    }
  }, "⭐".repeat(h.rank)), typeof h.score === "number" && /*#__PURE__*/React.createElement("span", {
    style: {
      marginLeft: "auto",
      fontFamily: "var(--font-mono)",
      fontSize: "var(--text-xs)",
      color: "#e5e5e5"
    }
  }, h.score.toFixed(3)))), /*#__PURE__*/React.createElement("div", {
    style: {
      position: "absolute",
      bottom: 0,
      left: 0,
      right: 0,
      padding: "32px 8px 8px",
      background: "var(--poster-scrim-bottom)",
      textShadow: "0 1px 2px rgba(0,0,0,0.95)"
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      fontWeight: "var(--weight-semibold)",
      fontSize: "var(--text-base)",
      color: "#fff",
      whiteSpace: "nowrap",
      overflow: "hidden",
      textOverflow: "ellipsis"
    }
  }, title), /*#__PURE__*/React.createElement("div", {
    style: {
      marginTop: 2,
      fontSize: "var(--text-sm)",
      color: "#e5e5e5",
      display: "flex",
      flexWrap: "wrap",
      gap: "0 8px"
    }
  }, h.studio && /*#__PURE__*/React.createElement("span", null, h.studio), h.year && /*#__PURE__*/React.createElement("span", null, h.year, h.month ? `-${String(h.month).padStart(2, "0")}` : ""), h.actresses && h.actresses.length > 0 && /*#__PURE__*/React.createElement("span", null, "\uD83D\uDC64 ", h.actresses.join(", ")), typeof h.play === "number" && h.play > 0 && /*#__PURE__*/React.createElement("span", null, "\u25B6\uFE0E ", h.play), typeof h.like_count === "number" && h.like_count > 0 && /*#__PURE__*/React.createElement("span", null, "\uD83D\uDC9B ", h.like_count))));
}
Object.assign(__ds_scope, { VideoCard });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/product/VideoCard.jsx", error: String((e && e.message) || e) }); }

// ui_kits/admin/screens.jsx
try { (() => {
// flayAI — Admin dashboard UI kit.
// Service status (Qdrant / SQLite / Ollama) + indexer KPIs + pipeline flow.
// Composes Card, Badge, Tabs, ThemeToggle from the design system.

const DS = window.FlayAIDesignSystem_105b78;
const {
  Card,
  Badge,
  Tabs,
  ThemeToggle,
  Button
} = DS;
const fmt = n => n.toLocaleString("ko-KR");
const QDRANT = [{
  name: "videos",
  desc: "영상 텍스트 임베딩 (bge-m3)",
  points: 8432,
  dim: 1024,
  status: "green"
}, {
  name: "posters_clip",
  desc: "포스터 이미지 임베딩 (CLIP ViT-L/14)",
  points: 8120,
  dim: 768,
  status: "green"
}, {
  name: "faces",
  desc: "얼굴 벡터 (InsightFace buffalo_l)",
  points: 19284,
  dim: 512,
  status: "green"
}, {
  name: "poster_ocr",
  desc: "포스터 OCR 텍스트 임베딩 (bge-m3)",
  points: 7651,
  dim: 1024,
  status: "yellow"
}];
const OLLAMA = [{
  name: "bge-m3:latest",
  param: "567M",
  quant: "F16",
  size: "1.2 GB",
  caps: ["embedding"],
  loaded: true,
  permanent: true
}, {
  name: "qwen2.5:7b",
  param: "7.6B",
  quant: "Q4_K_M",
  size: "4.7 GB",
  caps: ["completion", "tools"],
  loaded: true,
  permanent: false
}, {
  name: "llava:13b",
  param: "13B",
  quant: "Q4_0",
  size: "8.0 GB",
  caps: ["vision"],
  loaded: false
}];
const KPIS = [{
  label: "영상",
  value: 8432,
  sub: "번역 98% · 임베딩 100%"
}, {
  label: "포스터",
  value: 8120,
  sub: "CLIP 100% · OCR 94% · 얼굴 91%"
}, {
  label: "배우",
  value: 1247,
  sub: "6.8편/명"
}, {
  label: "얼굴 클러스터",
  value: 2103,
  sub: "라벨 1,842 · 88%"
}, {
  label: "클러스터 라벨",
  value: 1842,
  sub: "미라벨 261"
}];
const PIPELINE = [{
  label: "JSON 로드",
  group: "메타",
  status: "done"
}, {
  label: "포스터 스캔",
  group: "메타",
  status: "done"
}, {
  label: "번역",
  group: "AI",
  status: "done",
  pct: 98
}, {
  label: "포스터 캡션",
  group: "AI",
  status: "running",
  pct: 62
}, {
  label: "텍스트 임베딩",
  group: "AI",
  status: "idle",
  pct: 0
}, {
  label: "이미지 임베딩",
  group: "AI",
  status: "idle",
  pct: 0
}, {
  label: "얼굴 추출",
  group: "AI",
  status: "idle",
  pct: 0
}, {
  label: "포스터 OCR",
  group: "AI",
  status: "idle",
  pct: 0
}, {
  label: "페이로드 동기화",
  group: "메타",
  status: "idle"
}];
function ProgressBar({
  pct
}) {
  return /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      alignItems: "center",
      gap: 8,
      marginTop: 8
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      flex: 1,
      height: 6,
      background: "var(--muted)",
      borderRadius: 9999,
      overflow: "hidden"
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      height: "100%",
      width: `${pct}%`,
      background: "var(--success)",
      borderRadius: 9999
    }
  })), /*#__PURE__*/React.createElement("span", {
    style: {
      fontFamily: "var(--font-mono)",
      fontSize: "var(--text-xs)",
      color: "var(--muted-foreground)",
      width: 30,
      textAlign: "right"
    }
  }, pct, "%"));
}
const STATUS_MARK = {
  done: ["✓", "var(--success)"],
  running: ["●", "#d97706"],
  idle: ["○", "var(--muted-foreground)"],
  failed: ["✗", "var(--destructive)"]
};
function AdminScreen() {
  return /*#__PURE__*/React.createElement("main", {
    style: {
      flex: 1,
      display: "flex",
      flexDirection: "column",
      minHeight: 0
    }
  }, /*#__PURE__*/React.createElement("header", {
    style: {
      flexShrink: 0,
      margin: "0 auto",
      width: "100%",
      maxWidth: 1100,
      padding: "16px",
      borderBottom: "1px solid var(--border)",
      display: "flex",
      alignItems: "baseline",
      gap: 12
    }
  }, /*#__PURE__*/React.createElement("h1", {
    style: {
      fontSize: "var(--text-lg)",
      fontWeight: 600,
      margin: 0,
      color: "var(--foreground)"
    }
  }, "flayAI"), /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: "var(--text-sm)",
      color: "var(--muted-foreground)"
    }
  }, "\uAD00\uB9AC\uC790"), /*#__PURE__*/React.createElement("div", {
    style: {
      marginLeft: "auto",
      display: "flex",
      alignItems: "center",
      gap: 12
    }
  }, /*#__PURE__*/React.createElement(Button, {
    variant: "secondary",
    size: "sm"
  }, "\u21BB \uC0C8\uB85C\uACE0\uCE68"), /*#__PURE__*/React.createElement(ThemeToggle, null))), /*#__PURE__*/React.createElement("div", {
    style: {
      flex: 1,
      minHeight: 0,
      overflowY: "auto",
      width: "100%",
      maxWidth: 1100,
      margin: "0 auto",
      padding: "20px 16px",
      display: "flex",
      flexDirection: "column",
      gap: 16
    }
  }, /*#__PURE__*/React.createElement(Card, {
    title: "\uC778\uB371\uC11C",
    available: true
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      display: "grid",
      gridTemplateColumns: "repeat(5,1fr)",
      gap: 12,
      marginBottom: 20
    }
  }, KPIS.map(k => /*#__PURE__*/React.createElement("div", {
    key: k.label,
    style: {
      background: "var(--card)",
      borderRadius: "var(--radius-lg)",
      border: "1px solid var(--border)",
      padding: "10px 12px"
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      color: "var(--muted-foreground)",
      fontSize: "var(--text-xs)"
    }
  }, k.label), /*#__PURE__*/React.createElement("div", {
    style: {
      color: "var(--foreground)",
      fontFamily: "var(--font-mono)",
      fontSize: "var(--text-xl)",
      fontWeight: 600,
      marginTop: 2,
      fontVariantNumeric: "tabular-nums"
    }
  }, fmt(k.value)), /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 11,
      color: "var(--muted-foreground)",
      marginTop: 4
    }
  }, k.sub)))), /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      gap: 8,
      marginBottom: 16
    }
  }, /*#__PURE__*/React.createElement(Button, {
    variant: "secondary",
    size: "sm"
  }, "\uC99D\uBD84 \uC778\uB371\uC2F1 \xB7 \uC2E0\uADDC 124\uAC74"), /*#__PURE__*/React.createElement(Button, {
    variant: "danger",
    size: "sm"
  }, "\u26A0 \uC804\uCCB4 \uC7AC\uC778\uB371\uC2F1")), /*#__PURE__*/React.createElement("div", {
    style: {
      display: "grid",
      gap: 8,
      gridTemplateColumns: "repeat(auto-fill,minmax(300px,1fr))"
    }
  }, PIPELINE.map(s => {
    const [mark, color] = STATUS_MARK[s.status];
    const border = s.status === "running" ? "color-mix(in srgb, #d97706 50%, var(--border))" : s.status === "done" ? "color-mix(in srgb, var(--success) 35%, var(--border))" : "var(--border)";
    return /*#__PURE__*/React.createElement("div", {
      key: s.label,
      style: {
        borderRadius: "var(--radius-lg)",
        border: `1px solid ${border}`,
        background: "color-mix(in srgb, var(--card) 60%, transparent)",
        padding: "10px 12px"
      }
    }, /*#__PURE__*/React.createElement("div", {
      style: {
        display: "flex",
        alignItems: "center",
        gap: 8
      }
    }, /*#__PURE__*/React.createElement("span", {
      style: {
        width: 16,
        textAlign: "center",
        color
      }
    }, mark), /*#__PURE__*/React.createElement("span", {
      style: {
        fontSize: "var(--text-sm)",
        fontWeight: 600,
        color: "var(--foreground)"
      }
    }, s.label), /*#__PURE__*/React.createElement(Badge, {
      tone: s.group === "AI" ? "running" : "neutral",
      style: {
        marginLeft: "auto",
        fontSize: 10
      }
    }, s.group)), s.pct !== undefined && s.status !== "idle" && /*#__PURE__*/React.createElement(ProgressBar, {
      pct: s.pct
    }));
  }))), /*#__PURE__*/React.createElement("div", {
    style: {
      display: "grid",
      gridTemplateColumns: "1fr 1fr",
      gap: 16
    }
  }, /*#__PURE__*/React.createElement(Card, {
    title: "Qdrant \uBCA1\uD130 DB",
    badge: "4\uAC1C \uCEEC\uB809\uC158",
    available: true
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      flexDirection: "column",
      gap: 8
    }
  }, QDRANT.map(c => /*#__PURE__*/React.createElement("div", {
    key: c.name,
    style: {
      borderRadius: "var(--radius-md)",
      border: "1px solid color-mix(in srgb, var(--border) 60%, transparent)",
      background: "color-mix(in srgb, var(--card) 50%, transparent)",
      padding: "8px 12px",
      display: "flex",
      alignItems: "center",
      gap: 12
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      flex: 1,
      minWidth: 0
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      fontFamily: "var(--font-mono)",
      fontSize: "var(--text-sm)",
      color: "var(--foreground)"
    }
  }, c.name), /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 11,
      color: "var(--muted-foreground)",
      marginTop: 2
    }
  }, c.desc)), /*#__PURE__*/React.createElement("div", {
    style: {
      textAlign: "right"
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      fontFamily: "var(--font-mono)",
      fontSize: "var(--text-sm)",
      color: "var(--foreground)"
    }
  }, fmt(c.points)), /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 11,
      color: "var(--muted-foreground)"
    }
  }, "\uD3EC\uC778\uD2B8")), /*#__PURE__*/React.createElement(Badge, {
    tone: c.status === "green" ? "success" : "warning"
  }, c.status))))), /*#__PURE__*/React.createElement(Card, {
    title: "Ollama LLM",
    badge: "3\uAC1C \uC124\uCE58 \xB7 2\uAC1C VRAM \uB85C\uB4DC",
    available: true
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      flexDirection: "column",
      gap: 8
    }
  }, OLLAMA.map(m => /*#__PURE__*/React.createElement("div", {
    key: m.name,
    style: {
      borderRadius: "var(--radius-md)",
      border: `1px solid ${m.loaded ? "color-mix(in srgb, var(--success) 40%, var(--border))" : "var(--border)"}`,
      background: m.loaded ? "color-mix(in srgb, var(--success) 5%, transparent)" : "color-mix(in srgb, var(--card) 50%, transparent)",
      padding: "8px 12px"
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      alignItems: "center",
      gap: 8
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      width: 8,
      height: 8,
      borderRadius: 9999,
      flexShrink: 0,
      background: m.loaded ? "var(--success)" : "var(--muted)"
    }
  }), /*#__PURE__*/React.createElement("span", {
    style: {
      fontFamily: "var(--font-mono)",
      fontSize: "var(--text-sm)",
      color: "var(--foreground)"
    }
  }, m.name), m.permanent && /*#__PURE__*/React.createElement(Badge, {
    tone: "warning",
    style: {
      marginLeft: "auto",
      fontSize: 10
    }
  }, "\u267E \uC601\uAD6C")), /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      flexWrap: "wrap",
      gap: "2px 12px",
      fontSize: 11,
      color: "var(--muted-foreground)",
      marginTop: 4
    }
  }, /*#__PURE__*/React.createElement("span", null, "\uD30C\uB77C\uBBF8\uD130 ", m.param), /*#__PURE__*/React.createElement("span", null, "\uC591\uC790\uD654 ", m.quant), /*#__PURE__*/React.createElement("span", null, "\uD06C\uAE30 ", m.size)), /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      gap: 4,
      marginTop: 6
    }
  }, m.caps.map(c => /*#__PURE__*/React.createElement(Badge, {
    key: c,
    tone: "neutral",
    style: {
      fontSize: 10
    }
  }, c))))))))));
}
window.AdminScreen = AdminScreen;
})(); } catch (e) { __ds_ns.__errors.push({ path: "ui_kits/admin/screens.jsx", error: String((e && e.message) || e) }); }

// ui_kits/diary/screens.jsx
try { (() => {
// flayAI — Diary UI kit.
// The private journaling space: warm cream + serif (.diary-mood), past-entry
// "recall" cards, and a reflective assistant. Composes Composer + ThemeToggle.

const DS = window.FlayAIDesignSystem_105b78;
const {
  Composer,
  ThemeToggle,
  Badge
} = DS;
const WEATHER = {
  sunny: "☀️",
  cloudy: "☁️",
  rainy: "🌧️",
  snowy: "❄️"
};
const RECALL = [{
  date: "2025-06-20",
  weather: "sunny",
  title: "처음 카메라를 산 날",
  body: "큰맘 먹고 카메라를 샀다. 손에 쥐니 묵직하고 좋았다. 동네를 한 바퀴 돌며 아무거나 찍었는데, 평범한 골목도 뷰파인더 안에선 달라 보였다."
}, {
  date: "2025-12-31",
  weather: "snowy",
  title: "한 해의 끝",
  body: "눈이 내렸다. 올해는 유난히 빨리 지나갔다. 사진 폴더를 정리하다 보니 봄에 찍은 벚꽃이 벌써 아득하다."
}];
const SEED = [{
  role: "user",
  text: "오늘 오랜만에 카메라를 다시 꺼냈어. 작년 이맘때가 자꾸 생각나더라."
}, {
  role: "assistant",
  recall: RECALL,
  text: "작년 6월에 처음 카메라를 샀던 그 설렘이 떠올랐나 봐. 평범한 골목도 뷰파인더 안에선 달라 보인다고 적었었지. 오늘 다시 꺼낸 카메라로는 무엇을 담고 싶어?"
}];
function RecallCard({
  s
}) {
  return /*#__PURE__*/React.createElement("div", {
    style: {
      borderRadius: "var(--radius-2xl)",
      border: "1px solid color-mix(in srgb, var(--apple-amber) 25%, transparent)",
      background: "color-mix(in srgb, var(--apple-amber) 6%, transparent)",
      padding: "14px 16px",
      boxShadow: "var(--shadow-sm)"
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      alignItems: "center",
      gap: 8,
      marginBottom: 10
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      borderRadius: 9999,
      background: "color-mix(in srgb, var(--apple-amber) 15%, transparent)",
      padding: "2px 8px",
      fontSize: "var(--text-xs)",
      fontFamily: "var(--font-mono)",
      color: "var(--apple-amber)"
    }
  }, s.date), s.weather && /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: "var(--text-sm)"
    }
  }, WEATHER[s.weather]), s.title && /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: "var(--text-sm)",
      fontWeight: 600,
      color: "var(--foreground)"
    }
  }, s.title)), /*#__PURE__*/React.createElement("p", {
    style: {
      margin: 0,
      fontSize: "var(--text-sm)",
      lineHeight: "var(--leading-relaxed)",
      color: "color-mix(in srgb, var(--foreground) 90%, transparent)"
    }
  }, s.body));
}
function DiaryScreen() {
  const [messages, setMessages] = React.useState(SEED);
  const [input, setInput] = React.useState("");
  const [busy, setBusy] = React.useState(false);
  const [isDark, setIsDark] = React.useState(() => document.documentElement.classList.contains("dark"));
  const scrollRef = React.useRef(null);
  React.useEffect(() => {
    const el = document.documentElement;
    const sync = () => setIsDark(el.classList.contains("dark"));
    sync();
    const obs = new MutationObserver(sync);
    obs.observe(el, {
      attributes: true,
      attributeFilter: ["class"]
    });
    return () => obs.disconnect();
  }, []);
  const send = q => {
    const text = (q ?? input).trim();
    if (!text) return;
    setInput("");
    setMessages(m => [...m, {
      role: "user",
      text
    }, {
      role: "assistant",
      streaming: true
    }]);
    setBusy(true);
    setTimeout(() => {
      setMessages(m => m.map((msg, i) => i === m.length - 1 ? {
        role: "assistant",
        text: "그렇게 적어두니 좋다. 오늘의 마음이 나중에 또 너에게 말을 걸어줄 거야."
      } : msg));
      setBusy(false);
    }, 1100);
  };
  React.useEffect(() => {
    scrollRef.current?.scrollTo(0, scrollRef.current.scrollHeight);
  }, [messages]);
  return /*#__PURE__*/React.createElement("main", {
    className: "diary-mood" + (isDark ? " diary-mood-dark" : ""),
    style: {
      flex: 1,
      display: "flex",
      flexDirection: "column",
      minHeight: 0,
      background: "var(--background)",
      color: "var(--foreground)"
    }
  }, /*#__PURE__*/React.createElement("header", {
    style: {
      flexShrink: 0,
      margin: "0 auto",
      width: "100%",
      maxWidth: "var(--col-diary)",
      padding: "16px",
      borderBottom: "1px solid var(--border)",
      display: "flex",
      alignItems: "baseline",
      gap: 10,
      fontFamily: "var(--font-sans)"
    }
  }, /*#__PURE__*/React.createElement("h1", {
    style: {
      fontSize: "var(--text-lg)",
      fontWeight: 600,
      margin: 0
    }
  }, "flayAI"), /*#__PURE__*/React.createElement("span", {
    style: {
      display: "flex",
      alignItems: "center",
      gap: 4,
      fontSize: "var(--text-xs)",
      color: "var(--apple-amber)"
    }
  }, /*#__PURE__*/React.createElement("svg", {
    width: "12",
    height: "12",
    viewBox: "0 0 24 24",
    fill: "none",
    stroke: "currentColor",
    strokeWidth: "2",
    strokeLinecap: "round",
    strokeLinejoin: "round"
  }, /*#__PURE__*/React.createElement("path", {
    d: "M4 19.5v-15A2.5 2.5 0 0 1 6.5 2H20v20H6.5a2.5 2.5 0 0 1 0-5H20"
  })), "\uC77C\uAE30"), /*#__PURE__*/React.createElement("div", {
    style: {
      marginLeft: "auto",
      display: "flex",
      alignItems: "center",
      gap: 12
    }
  }, /*#__PURE__*/React.createElement("button", {
    style: {
      background: "none",
      border: "none",
      cursor: "pointer",
      fontSize: "var(--text-xs)",
      color: "var(--muted-foreground)",
      fontFamily: "var(--font-sans)"
    }
  }, "+ \uC0C8 \uB300\uD654"), /*#__PURE__*/React.createElement(ThemeToggle, null))), /*#__PURE__*/React.createElement("div", {
    ref: scrollRef,
    style: {
      flex: 1,
      minHeight: 0,
      overflowY: "auto",
      width: "100%",
      maxWidth: "var(--col-diary)",
      margin: "0 auto",
      padding: "16px",
      display: "flex",
      flexDirection: "column",
      gap: 20
    }
  }, messages.map((m, i) => m.role === "user" ? /*#__PURE__*/React.createElement("div", {
    key: i,
    style: {
      display: "flex",
      justifyContent: "flex-end"
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      borderRadius: "var(--radius-2xl)",
      borderTopRightRadius: "var(--radius-md)",
      background: "var(--primary)",
      color: "#fff",
      padding: "10px 14px",
      fontSize: "15px",
      maxWidth: "82%",
      boxShadow: "var(--shadow-sm)",
      lineHeight: "var(--leading-relaxed)"
    }
  }, m.text)) : /*#__PURE__*/React.createElement("div", {
    key: i,
    style: {
      display: "flex",
      justifyContent: "flex-start"
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      width: "100%",
      display: "flex",
      flexDirection: "column",
      gap: 10
    }
  }, m.recall && /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      flexDirection: "column",
      gap: 8
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      alignItems: "center",
      gap: 6,
      fontSize: "var(--text-xs)",
      color: "var(--muted-foreground)",
      fontFamily: "var(--font-sans)"
    }
  }, /*#__PURE__*/React.createElement("svg", {
    width: "13",
    height: "13",
    viewBox: "0 0 24 24",
    fill: "none",
    stroke: "currentColor",
    strokeWidth: "2",
    strokeLinecap: "round",
    strokeLinejoin: "round"
  }, /*#__PURE__*/React.createElement("path", {
    d: "M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"
  })), "\uADF8\uB54C \uC77C\uAE30 ", m.recall.length, "\uAC74"), m.recall.map(s => /*#__PURE__*/React.createElement(RecallCard, {
    key: s.date,
    s: s
  }))), m.streaming ? /*#__PURE__*/React.createElement("div", {
    style: {
      display: "inline-flex",
      alignItems: "center",
      gap: 4,
      alignSelf: "flex-start",
      borderRadius: "var(--radius-2xl)",
      borderTopLeftRadius: "var(--radius-md)",
      background: "color-mix(in srgb, var(--muted) 60%, transparent)",
      padding: "12px 16px"
    }
  }, [0, 0.15, 0.3].map(d => /*#__PURE__*/React.createElement("span", {
    key: d,
    style: {
      width: 6,
      height: 6,
      borderRadius: 9999,
      background: "var(--muted-foreground)",
      animation: `db 1s ${d}s infinite`
    }
  }))) : m.text && /*#__PURE__*/React.createElement("div", {
    style: {
      display: "inline-block",
      maxWidth: "88%",
      alignSelf: "flex-start",
      borderRadius: "var(--radius-2xl)",
      borderTopLeftRadius: "var(--radius-md)",
      background: "color-mix(in srgb, var(--muted) 60%, transparent)",
      padding: "10px 16px",
      fontSize: "15px",
      lineHeight: "var(--leading-relaxed)",
      color: "var(--foreground)"
    }
  }, m.text))))), /*#__PURE__*/React.createElement("div", {
    style: {
      flexShrink: 0,
      width: "100%",
      maxWidth: "var(--col-diary)",
      margin: "0 auto",
      padding: "12px 16px"
    }
  }, /*#__PURE__*/React.createElement(Composer, {
    value: input,
    onChange: setInput,
    onSubmit: send,
    busy: busy,
    placeholder: "\uC624\uB298 \uC788\uC5C8\uB358 \uC77C, \uB5A0\uC624\uB978 \uC0DD\uAC01\u2026"
  })));
}
window.DiaryScreen = DiaryScreen;
})(); } catch (e) { __ds_ns.__errors.push({ path: "ui_kits/diary/screens.jsx", error: String((e && e.message) || e) }); }

// ui_kits/search-chat/screens.jsx
try { (() => {
// flayAI — Search Chat UI kit screens.
// Composes design-system components (window.FlayAIDesignSystem_105b78) into the
// real chat product: centered hero empty-state → results stream with tool chips
// and VideoCard grid → docked composer. Posters are tasteful gradient stand-ins.

const DS = window.FlayAIDesignSystem_105b78;
const {
  Button,
  Badge,
  Chip,
  Tabs,
  VideoCard,
  Composer,
  ToolCallChip,
  ThemeToggle
} = DS;
const SUGGESTIONS = ["사무실에서 즐겁게 일하는 영상 보여줘", "2026년 1월에 찍은 영상 보여줘", "2026년 나온 영상에서 인기가 높은 영상", "온천에서 여러 남자랑 즐기는 영상"];
const POSTER_GRADS = ["linear-gradient(135deg,#3a4a63,#1c2533)", "linear-gradient(135deg,#6b4a52,#2b1d22)", "linear-gradient(135deg,#46603f,#1f2b1c)", "linear-gradient(135deg,#5a4b6b,#241d2b)", "linear-gradient(135deg,#63563a,#2b251c)", "linear-gradient(135deg,#3a5a63,#1c2a2d)"];
const RESULTS = [{
  opus: "SSIS-887",
  title: "사무실의 즐거운 하루",
  studio: "S1 NO.1 STYLE",
  year: 2026,
  month: 1,
  kind: "instance",
  rank: 3,
  score: 0.962,
  play: 124,
  like_count: 18,
  actresses: ["미카미 유아"]
}, {
  opus: "ABW-321",
  title: "야근 후의 비밀",
  studio: "Prestige",
  year: 2026,
  month: 1,
  kind: "instance",
  rank: 2,
  score: 0.918,
  play: 88,
  like_count: 11,
  actresses: ["카와키타 사이카"]
}, {
  opus: "PRED-540",
  title: "온천 여행의 추억",
  studio: "Premium",
  year: 2025,
  month: 11,
  kind: "archive",
  score: 0.881,
  play: 203,
  like_count: 27,
  actresses: ["아마미야 코토네", "유메노 아이카"]
}, {
  opus: "MIDV-112",
  title: "출근길의 설렘",
  studio: "MOODYZ",
  year: 2026,
  month: 2,
  kind: "instance",
  rank: 1,
  score: 0.844,
  play: 41,
  like_count: 6,
  actresses: ["히메노 코토하"]
}, {
  opus: "STARS-998",
  title: "회의실의 긴장",
  studio: "SOD Create",
  year: 2025,
  month: 12,
  kind: "archive",
  score: 0.802,
  play: 67,
  like_count: 9,
  actresses: ["토다 마코토"]
}, {
  opus: "FSDSS-743",
  title: "퇴근 후 한 잔",
  studio: "FALENO",
  year: 2026,
  month: 1,
  kind: "instance",
  score: 0.771,
  play: 35,
  like_count: 4,
  actresses: ["미야지마 메이"]
}];
function Header({
  go,
  active
}) {
  const NAV = [{
    key: "chat",
    label: "채팅"
  }, {
    key: "image",
    label: "이미지"
  }, {
    key: "face",
    label: "얼굴"
  }, {
    key: "labels",
    label: "라벨링"
  }, {
    key: "subtitle",
    label: "자막"
  }, {
    key: "admin",
    label: "관리자"
  }];
  return /*#__PURE__*/React.createElement("header", {
    style: {
      flexShrink: 0,
      margin: "0 auto",
      width: "100%",
      maxWidth: "var(--col-header)",
      padding: "16px",
      borderBottom: "1px solid var(--border)",
      display: "flex",
      alignItems: "baseline",
      gap: 8
    }
  }, /*#__PURE__*/React.createElement("h1", {
    style: {
      fontSize: "var(--text-lg)",
      fontWeight: 600,
      margin: 0,
      color: "var(--foreground)"
    }
  }, "flayAI"), /*#__PURE__*/React.createElement("nav", {
    style: {
      marginLeft: "auto",
      display: "flex",
      alignItems: "center",
      gap: 14
    }
  }, /*#__PURE__*/React.createElement(Tabs, {
    variant: "text",
    value: active,
    onChange: go,
    items: NAV
  }), /*#__PURE__*/React.createElement("span", {
    style: {
      height: 12,
      width: 1,
      background: "var(--border)"
    }
  }), /*#__PURE__*/React.createElement("a", {
    style: {
      display: "flex",
      alignItems: "center",
      gap: 4,
      fontSize: "var(--text-xs)",
      color: "var(--apple-amber)",
      textDecoration: "none",
      cursor: "pointer"
    },
    onClick: () => go("diary")
  }, /*#__PURE__*/React.createElement("svg", {
    width: "12",
    height: "12",
    viewBox: "0 0 24 24",
    fill: "none",
    stroke: "currentColor",
    strokeWidth: "2",
    strokeLinecap: "round",
    strokeLinejoin: "round"
  }, /*#__PURE__*/React.createElement("path", {
    d: "M4 19.5v-15A2.5 2.5 0 0 1 6.5 2H20v20H6.5a2.5 2.5 0 0 1 0-5H20"
  })), "\uC77C\uAE30"), /*#__PURE__*/React.createElement(ThemeToggle, null)));
}
function OptionsRow({
  limit,
  setLimit,
  kind,
  setKind
}) {
  return /*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement(Chip, {
    role: "option",
    selected: false
  }, limit), /*#__PURE__*/React.createElement(Chip, {
    role: "option",
    selected: kind !== "전체"
  }, kind));
}
function ChatScreen() {
  const [messages, setMessages] = React.useState([]);
  const [input, setInput] = React.useState("");
  const [busy, setBusy] = React.useState(false);
  const scrollRef = React.useRef(null);
  const send = q => {
    const query = (q ?? input).trim();
    if (!query) return;
    setInput("");
    setMessages(m => [...m, {
      role: "user",
      text: query
    }, {
      role: "assistant",
      streaming: true,
      query
    }]);
    setBusy(true);
    setTimeout(() => {
      setMessages(m => m.map((msg, i) => i === m.length - 1 ? {
        ...msg,
        streaming: false,
        hits: RESULTS,
        text: `'${query}' 와 관련된 영상 ${RESULTS.length}편을 찾았어요.`
      } : msg));
      setBusy(false);
    }, 900);
  };
  React.useEffect(() => {
    scrollRef.current?.scrollTo(0, scrollRef.current.scrollHeight);
  }, [messages]);
  const empty = messages.length === 0;
  const options = /*#__PURE__*/React.createElement(OptionsRow, {
    limit: 10,
    kind: "전체"
  });
  return /*#__PURE__*/React.createElement("main", {
    style: {
      flex: 1,
      display: "flex",
      flexDirection: "column",
      width: "100%",
      minHeight: 0
    }
  }, /*#__PURE__*/React.createElement(Header, {
    go: () => {},
    active: "chat"
  }), empty ? /*#__PURE__*/React.createElement("div", {
    style: {
      flex: 1,
      minHeight: 0,
      display: "flex",
      flexDirection: "column",
      alignItems: "center",
      justifyContent: "center",
      gap: 28,
      padding: "16px 16px 64px"
    }
  }, /*#__PURE__*/React.createElement("h2", {
    style: {
      fontSize: "var(--text-3xl)",
      fontWeight: 600,
      color: "var(--foreground)",
      margin: 0
    }
  }, "\uBB34\uC5C7\uC744 \uCC3E\uC744\uAE4C\uC694?"), /*#__PURE__*/React.createElement(Composer, {
    hero: true,
    value: input,
    onChange: setInput,
    onSubmit: send,
    busy: busy,
    options: options
  }), /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      flexWrap: "wrap",
      gap: 8,
      justifyContent: "center",
      maxWidth: "var(--col-hero)"
    }
  }, SUGGESTIONS.map(q => /*#__PURE__*/React.createElement(Chip, {
    key: q,
    onClick: () => send(q)
  }, q)))) : /*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement("div", {
    ref: scrollRef,
    style: {
      flex: 1,
      minHeight: 0,
      overflowY: "auto",
      width: "100%",
      padding: "16px 24px",
      display: "flex",
      flexDirection: "column",
      gap: 24
    }
  }, messages.map((m, i) => m.role === "user" ? /*#__PURE__*/React.createElement("div", {
    key: i,
    style: {
      display: "flex",
      justifyContent: "flex-end"
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      maxWidth: "80%",
      borderRadius: "var(--radius-lg)",
      background: "color-mix(in srgb, var(--primary) 15%, transparent)",
      border: "1px solid color-mix(in srgb, var(--primary) 40%, transparent)",
      padding: "8px 12px",
      fontSize: "var(--text-sm)",
      color: "var(--foreground)"
    }
  }, m.text)) : /*#__PURE__*/React.createElement("div", {
    key: i,
    style: {
      display: "flex",
      justifyContent: "flex-start"
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      width: "100%",
      display: "flex",
      flexDirection: "column",
      gap: 8
    }
  }, /*#__PURE__*/React.createElement(ToolCallChip, {
    name: "search_videos",
    args: {
      query: m.query,
      limit: 10
    }
  }), m.streaming ? /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: "var(--text-xs)",
      color: "var(--muted-foreground)",
      textAlign: "center"
    }
  }, "\uC0DD\uC131 \uC911\u2026") : /*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement(ToolCallChip, {
    result: `${m.hits.length} items`
  }), /*#__PURE__*/React.createElement("div", {
    style: {
      display: "grid",
      gap: 8,
      gridTemplateColumns: "repeat(auto-fill,minmax(440px,1fr))"
    }
  }, m.hits.map((h, j) => /*#__PURE__*/React.createElement(VideoCard, {
    key: h.opus,
    hit: h,
    style: {
      background: POSTER_GRADS[j % POSTER_GRADS.length]
    },
    onOpen: () => {}
  }))), /*#__PURE__*/React.createElement("div", {
    style: {
      whiteSpace: "pre-wrap",
      color: "var(--foreground)",
      lineHeight: "var(--leading-relaxed)",
      textAlign: "center"
    }
  }, m.text)))))), /*#__PURE__*/React.createElement("div", {
    style: {
      flexShrink: 0,
      padding: "12px 16px"
    }
  }, /*#__PURE__*/React.createElement(Composer, {
    value: input,
    onChange: setInput,
    onSubmit: send,
    busy: busy,
    options: options
  }))));
}
window.ChatScreen = ChatScreen;
})(); } catch (e) { __ds_ns.__errors.push({ path: "ui_kits/search-chat/screens.jsx", error: String((e && e.message) || e) }); }

__ds_ns.Badge = __ds_scope.Badge;

__ds_ns.Button = __ds_scope.Button;

__ds_ns.Card = __ds_scope.Card;

__ds_ns.Chip = __ds_scope.Chip;

__ds_ns.Tabs = __ds_scope.Tabs;

__ds_ns.Composer = __ds_scope.Composer;

__ds_ns.ThemeToggle = __ds_scope.ThemeToggle;

__ds_ns.ToolCallChip = __ds_scope.ToolCallChip;

__ds_ns.VideoCard = __ds_scope.VideoCard;

})();
