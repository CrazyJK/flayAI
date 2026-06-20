import React from "react";

export interface ChipProps {
  children?: React.ReactNode;
  /** "suggestion" = example-query pill, "option" = small search-option pill. @default "suggestion" */
  role?: "suggestion" | "option";
  /** Apple-blue active treatment (selected option / segment). */
  selected?: boolean;
  onClick?: (e: React.MouseEvent<HTMLButtonElement>) => void;
  style?: React.CSSProperties;
}

/**
 * Fully-rounded pill — example-query suggestions and small search-option chips.
 * @startingPoint section="Core" subtitle="Suggestion & option pills" viewport="700x120"
 */
export function Chip(props: ChipProps): React.JSX.Element;
