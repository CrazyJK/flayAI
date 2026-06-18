"use client";

import Link from "next/link";
import ThemeToggle from "./ThemeToggle";

// 전 페이지 공용 네비게이션 항목 (채팅 헤더 기준).
// 일기는 컬렉션 도구가 아니라 사적 공간이라 NAV 에서 빼고 구분선 뒤에 따로 그린다.
const NAV = [
  { key: "chat", href: "/", label: "채팅" },
  { key: "image", href: "/image", label: "이미지" },
  { key: "face", href: "/face", label: "얼굴" },
  { key: "labels", href: "/labels", label: "라벨링" },
  { key: "stabilize", href: "/stabilize", label: "안정화" },
  { key: "subtitle", href: "/subtitle", label: "자막" },
  { key: "admin", href: "/admin", label: "관리자" },
] as const;

export type NavKey = (typeof NAV)[number]["key"] | "diary";

/**
 * 모든 페이지 공통 상단 헤더.
 * 채팅 화면과 동일하게 상단 중앙에 900px 고정폭으로 고정(shrink-0).
 * actions: 제목과 네비게이션 사이에 들어가는 페이지별 추가 버튼(예: 관리자 새로고침).
 */
export default function AppHeader({
  active,
  actions,
}: {
  active: NavKey;
  actions?: React.ReactNode;
}) {
  return (
    <header className="shrink-0 mx-auto w-full max-w-[900px] px-4 py-4 border-b border-border flex items-baseline gap-2 font-sans">
      <h1 className="text-lg font-semibold">flayAI</h1>
      {actions}
      <nav className="ml-auto flex items-center gap-3 text-xs">
        {NAV.map((n) => (
          <Link
            key={n.key}
            href={n.href}
            className={
              n.key === active
                ? "text-foreground"
                : "text-muted-foreground hover:text-foreground"
            }
          >
            {n.label}
          </Link>
        ))}
        <span aria-hidden className="h-3 w-px bg-border" />
        <Link
          href="/diary"
          className={`flex items-center gap-1 ${
            active === "diary"
              ? "text-amber-600 dark:text-amber-400"
              : "text-amber-700/60 hover:text-amber-600 dark:text-amber-500/70 dark:hover:text-amber-400"
          }`}
        >
          <svg
            width="12"
            height="12"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
            aria-hidden
          >
            <path d="M4 19.5v-15A2.5 2.5 0 0 1 6.5 2H20v20H6.5a2.5 2.5 0 0 1 0-5H20" />
          </svg>
          일기
        </Link>
        <ThemeToggle />
      </nav>
    </header>
  );
}
