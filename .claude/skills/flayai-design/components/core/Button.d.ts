import React from "react";

export interface ButtonProps {
  children?: React.ReactNode;
  /** Visual style. @default "primary" */
  variant?: "primary" | "secondary" | "ghost" | "danger";
  /** @default "md" */
  size?: "sm" | "md" | "lg";
  disabled?: boolean;
  /** Optional leading icon node (e.g. a Lucide SVG). */
  icon?: React.ReactNode;
  type?: "button" | "submit" | "reset";
  onClick?: (e: React.MouseEvent<HTMLButtonElement>) => void;
  style?: React.CSSProperties;
}

/**
 * Apple-style button with primary / secondary / ghost / danger variants.
 * @startingPoint section="Core" subtitle="Apple-style action button" viewport="700x140"
 */
export function Button(props: ButtonProps): React.JSX.Element;
