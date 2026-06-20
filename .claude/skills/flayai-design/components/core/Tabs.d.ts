import React from "react";

export interface TabItem {
  key: string;
  label: React.ReactNode;
}

export interface TabsProps {
  items: TabItem[];
  /** Currently-selected key. */
  value?: string;
  onChange?: (key: string) => void;
  /** "segment" = filled active tab; "text" = header-nav text tabs. @default "segment" */
  variant?: "segment" | "text";
  style?: React.CSSProperties;
}

/**
 * Horizontal tab / nav selector — mode switches (segment) or header nav (text).
 * @startingPoint section="Core" subtitle="Tab & nav selector" viewport="700x110"
 */
export function Tabs(props: TabsProps): React.JSX.Element;
