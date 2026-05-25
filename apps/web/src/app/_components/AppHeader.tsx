"use client";

import Link from "next/link";
import ThemeToggle from "./ThemeToggle";

// 전 페이지 공용 네비게이션 항목 (채팅 헤더 기준)
const NAV = [
  { key: "chat", href: "/", label: "채팅" },
  { key: "image", href: "/image", label: "이미지" },
  { key: "face", href: "/face", label: "얼굴" },
  { key: "labels", href: "/labels", label: "라벨링" },
  { key: "admin", href: "/admin", label: "관리자" },
] as const;

export type NavKey = (typeof NAV)[number]["key"];

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
    <header className="shrink-0 mx-auto w-full max-w-[900px] px-4 py-4 border-b border-border flex items-baseline gap-2">
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
        <ThemeToggle />
      </nav>
    </header>
  );
}
