import React from "react";

/**
 * flayAI Composer — the chat input box (Copilot/Claude-style): a rounded card
 * wrapping an auto-growing textarea on top, with an options row beneath (left:
 * option pills via `options`; right: send / stop button). Focus tints the
 * border blue with a soft ring.
 *
 * `hero` = large centered first-screen variant; otherwise the compact docked one.
 */
export function Composer({
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

  const grow = (el) => {
    if (!el) return;
    el.style.height = "auto";
    el.style.height = Math.min(el.scrollHeight, 200) + "px";
  };

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        onSubmit?.(value);
      }}
      style={{ width: "100%", maxWidth: hero ? "var(--col-hero)" : "var(--col-header)", margin: hero ? 0 : "0 auto", ...style }}
      {...rest}
    >
      <div
        style={{
          display: "flex",
          flexDirection: "column",
          gap: 8,
          borderRadius: "var(--radius-2xl)",
          border: `1px solid ${focus ? "var(--primary)" : "var(--border)"}`,
          background: "var(--card)",
          padding: hero ? "14px 16px 8px" : "12px 12px 6px",
          boxShadow: hero ? "var(--shadow-lg)" : "var(--shadow-sm)",
          transition: "border-color 0.15s ease, box-shadow 0.15s ease",
          ...(focus ? { boxShadow: "var(--ring)" } : {}),
        }}
      >
        <textarea
          ref={taRef}
          rows={1}
          value={value}
          placeholder={placeholder}
          disabled={busy}
          onFocus={() => setFocus(true)}
          onBlur={() => setFocus(false)}
          onChange={(e) => { onChange?.(e.target.value); grow(e.currentTarget); }}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
              e.preventDefault();
              onSubmit?.(value);
            }
          }}
          style={{
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
            lineHeight: "var(--leading-normal)",
          }}
        />
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          {options}
          {busy ? (
            <button
              type="button"
              onClick={onStop}
              title="중단"
              aria-label="중단"
              style={{ marginLeft: "auto", display: "inline-flex", background: "none", border: "none", cursor: "pointer", color: "var(--destructive)" }}
            >
              <svg width={hero ? 22 : 18} height={hero ? 22 : 18} viewBox="0 0 24 24" fill="currentColor"><rect x="6" y="6" width="12" height="12" rx="2" /></svg>
            </button>
          ) : (
            <button
              type="submit"
              title="전송"
              aria-label="전송"
              disabled={!value.trim()}
              style={{ marginLeft: "auto", display: "inline-flex", background: "none", border: "none", cursor: value.trim() ? "pointer" : "not-allowed", color: value.trim() ? "var(--primary)" : "var(--muted-foreground)", opacity: value.trim() ? 1 : 0.4 }}
            >
              <svg width={hero ? 24 : 20} height={hero ? 24 : 20} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <polyline points="9 10 4 15 9 20" />
                <path d="M20 4v7a4 4 0 0 1-4 4H4" />
              </svg>
            </button>
          )}
        </div>
      </div>
    </form>
  );
}
