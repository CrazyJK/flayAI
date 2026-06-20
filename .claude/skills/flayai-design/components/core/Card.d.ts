import React from "react";

export interface CardProps {
  /** Header title. Omit for a plain bordered container (no header). */
  title?: string;
  /** Optional mono sub-label next to the title (e.g. "5개 컬렉션"). */
  badge?: string;
  /** When set, renders a UP/DOWN availability pill on the right. */
  available?: boolean;
  collapsible?: boolean;
  defaultCollapsed?: boolean;
  children?: React.ReactNode;
  style?: React.CSSProperties;
}

/**
 * Bordered rounded section container with optional header, badge, UP/DOWN pill, and collapse.
 * @startingPoint section="Core" subtitle="Section card with header" viewport="700x200"
 */
export function Card(props: CardProps): React.JSX.Element;
