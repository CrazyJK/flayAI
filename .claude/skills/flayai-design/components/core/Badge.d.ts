import React from "react";

export interface BadgeProps {
  children?: React.ReactNode;
  /** Semantic tone → tinted translucent fill + border. @default "neutral" */
  tone?: "instance" | "archive" | "success" | "running" | "info" | "failed" | "warning" | "neutral";
  /** Use the mono font (default true — most flayAI badges are mono codes/states). */
  mono?: boolean;
  style?: React.CSSProperties;
}

/**
 * Small tinted status/label pill (kind badges, job status, service UP/DOWN).
 * @startingPoint section="Core" subtitle="Status & kind badges" viewport="700x120"
 */
export function Badge(props: BadgeProps): React.JSX.Element;
