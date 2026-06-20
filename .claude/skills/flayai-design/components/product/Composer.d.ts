import React from "react";

export interface ComposerProps {
  value?: string;
  onChange?: (value: string) => void;
  /** Submit (Enter without Shift, or send button). */
  onSubmit?: (value: string) => void;
  /** Stop a streaming response (shown while busy). */
  onStop?: () => void;
  busy?: boolean;
  /** Large centered first-screen variant. @default false */
  hero?: boolean;
  placeholder?: string;
  /** Left-side controls in the options row (e.g. count / kind Chips). */
  options?: React.ReactNode;
  style?: React.CSSProperties;
}

/**
 * Chat input box — rounded card with auto-growing textarea + options row + send/stop.
 * @startingPoint section="Product" subtitle="Chat composer (hero & docked)" viewport="760x180"
 */
export function Composer(props: ComposerProps): React.JSX.Element;
