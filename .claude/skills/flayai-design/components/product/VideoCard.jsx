import React from "react";

/**
 * flayAI VideoCard — the signature search-result poster card.
 * 400:269 poster with top + bottom protection scrims. Top overlay: opus code
 * (amber, mono), kind badge, rank stars, score. Bottom overlay: title + meta
 * (studio, year, actresses, plays, likes). Click opens the flay popup.
 *
 * Pass either a `hit` object or the individual fields. Poster image via
 * `poster` URL; falls back to a muted block if it fails to load.
 */
export function VideoCard({ hit = {}, poster, onOpen, style, ...rest }) {
  const h = hit;
  const title = h.title || h.title_ko || h.title_jp || h.opus;
  const posterUrl = poster || h.poster;
  const [hover, setHover] = React.useState(false);
  const [imgOk, setImgOk] = React.useState(true);
  const isInstance = h.kind === "instance";

  return (
    <div
      onClick={() => onOpen?.(h.opus)}
      onMouseEnter={() => setHover(true)}
      onMouseLeave={() => setHover(false)}
      title={h.opus ? `팝업으로 열기: ${h.opus}` : undefined}
      style={{
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
        ...style,
      }}
      {...rest}
    >
      {posterUrl && imgOk && (
        <img
          src={posterUrl}
          alt={h.opus || ""}
          onError={() => setImgOk(false)}
          style={{ position: "absolute", inset: 0, width: "100%", height: "100%", objectFit: "cover" }}
        />
      )}

      {/* Top scrim */}
      <div
        style={{
          position: "absolute",
          top: 0,
          left: 0,
          right: 0,
          padding: "8px",
          background: "var(--poster-scrim-top)",
          textShadow: "0 1px 2px rgba(0,0,0,0.9)",
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: 6, flexWrap: "wrap" }}>
          {h.opus && (
            <span style={{ fontFamily: "var(--font-mono)", fontSize: "var(--text-sm)", color: "var(--opus-accent)" }}>{h.opus}</span>
          )}
          {h.kind && (
            <span
              style={{
                fontFamily: "var(--font-mono)",
                fontSize: "var(--text-xs)",
                padding: "2px 6px",
                borderRadius: "var(--radius-sm)",
                color: isInstance ? "#bbf7d0" : "#e4e4e7",
                background: isInstance ? "rgba(16,185,129,0.3)" : "rgba(113,113,122,0.35)",
                border: `1px solid ${isInstance ? "rgba(16,185,129,0.5)" : "rgba(113,113,122,0.5)"}`,
              }}
            >
              {isInstance ? "INSTANCE" : "ARCHIVE"}
            </span>
          )}
          {typeof h.rank === "number" && h.rank > 0 && (
            <span style={{ fontSize: "var(--text-xs)", padding: "2px 6px", borderRadius: "var(--radius-sm)", background: "rgba(234,179,8,0.3)", color: "#fef9c3" }}>
              {"⭐".repeat(h.rank)}
            </span>
          )}
          {typeof h.score === "number" && (
            <span style={{ marginLeft: "auto", fontFamily: "var(--font-mono)", fontSize: "var(--text-xs)", color: "#e5e5e5" }}>
              {h.score.toFixed(3)}
            </span>
          )}
        </div>
      </div>

      {/* Bottom scrim */}
      <div
        style={{
          position: "absolute",
          bottom: 0,
          left: 0,
          right: 0,
          padding: "32px 8px 8px",
          background: "var(--poster-scrim-bottom)",
          textShadow: "0 1px 2px rgba(0,0,0,0.95)",
        }}
      >
        <div style={{ fontWeight: "var(--weight-semibold)", fontSize: "var(--text-base)", color: "#fff", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
          {title}
        </div>
        <div style={{ marginTop: 2, fontSize: "var(--text-sm)", color: "#e5e5e5", display: "flex", flexWrap: "wrap", gap: "0 8px" }}>
          {h.studio && <span>{h.studio}</span>}
          {h.year && <span>{h.year}{h.month ? `-${String(h.month).padStart(2, "0")}` : ""}</span>}
          {h.actresses && h.actresses.length > 0 && <span>👤 {h.actresses.join(", ")}</span>}
          {typeof h.play === "number" && h.play > 0 && <span>▶︎ {h.play}</span>}
          {typeof h.like_count === "number" && h.like_count > 0 && <span>💛 {h.like_count}</span>}
        </div>
      </div>
    </div>
  );
}
