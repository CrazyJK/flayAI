import React from "react";

export interface ThemeToggleProps {
  /** localStorage key for the persisted theme. @default "flayai-theme" */
  storageKey?: string;
  style?: React.CSSProperties;
}

/**
 * Header button that cycles 시스템 → 라이트 → 다크 and toggles `.dark` on <html>.
 * @startingPoint section="Product" subtitle="System/light/dark cycle toggle" viewport="700x90"
 */
export function ThemeToggle(props: ThemeToggleProps): React.JSX.Element;
