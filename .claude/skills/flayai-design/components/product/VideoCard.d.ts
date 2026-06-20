import React from "react";

export interface VideoHit {
  opus?: string;
  title?: string | null;
  title_ko?: string | null;
  title_jp?: string | null;
  studio?: string | null;
  year?: number | null;
  month?: number | null;
  kind?: "instance" | "archive" | null;
  rank?: number | null;
  play?: number | null;
  like_count?: number | null;
  actresses?: string[];
  score?: number;
  poster?: string;
}

export interface VideoCardProps {
  /** The result hit (opus, title, meta…). */
  hit?: VideoHit;
  /** Poster image URL (overrides hit.poster). */
  poster?: string;
  /** Click handler — receives the opus code. */
  onOpen?: (opus: string) => void;
  style?: React.CSSProperties;
}

/**
 * Signature 400:269 search-result poster card with scrim overlays, opus code,
 * kind badge, rank stars, score and meta row.
 * @startingPoint section="Product" subtitle="Search-result poster card" viewport="460x320"
 */
export function VideoCard(props: VideoCardProps): React.JSX.Element;
