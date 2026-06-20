import React from "react";

export interface ToolCallChipProps {
  /** Tool name (rendered cyan after the ⚙). */
  name?: string;
  /** Tool arguments — JSON-stringified, truncated past 80 chars with a ▼ toggle. */
  args?: Record<string, unknown>;
  /** When set, renders the result line "↳ {result}" instead of a call. */
  result?: React.ReactNode;
  style?: React.CSSProperties;
}

/**
 * Centered mono tool-call trace line ("⚙ search_videos(...)") with expand, plus a result-line mode.
 * @startingPoint section="Product" subtitle="Tool-call trace line" viewport="700x110"
 */
export function ToolCallChip(props: ToolCallChipProps): React.JSX.Element;
