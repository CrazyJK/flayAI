"use client";

import { useState } from "react";

// 섹션 카드 — 제목 + (선택) 배지 + (선택) UP/DOWN 가용성 표시.
// 관리자 대시보드(서비스 상태)와 자막 페이지에서 공용.
// - available 을 넘기지 않으면 UP/DOWN 배지를 그리지 않는다(서비스 상태가 무의미한 화면용).
// - collapsible=true 면 헤더가 토글 버튼이 되어 본문을 접고 펼친다(아이템이 많은 섹션용).
//   defaultCollapsed 로 초기 상태 지정. 상태는 카드별 메모리(새로고침하면 기본값으로 복귀).

export default function SectionCard({
  title,
  badge,
  available,
  collapsible = false,
  defaultCollapsed = false,
  children,
}: {
  title: string;
  badge?: string;
  available?: boolean;
  collapsible?: boolean;
  defaultCollapsed?: boolean;
  children: React.ReactNode;
}) {
  const [collapsed, setCollapsed] = useState(collapsible && defaultCollapsed);

  // 접혔으면 본문이 없으므로 헤더 하단 구분선을 그리지 않는다(허공에 뜬 줄 방지).
  const headerClass =
    "px-4 py-2.5 bg-card flex items-center gap-2" + (collapsed ? "" : " border-b border-border");

  const headerInner = (
    <>
      {collapsible && (
        <span className="text-muted-foreground text-xs w-3 shrink-0 text-center" aria-hidden>
          {collapsed ? "▶" : "▼"}
        </span>
      )}
      <span className="font-semibold text-base">{title}</span>
      {badge && <span className="text-sm font-mono text-muted-foreground ml-1">{badge}</span>}
      {available !== undefined && (
        <span
          className={
            "ml-auto text-xs px-1.5 py-0.5 rounded font-mono " +
            (available
              ? "bg-emerald-500/15 text-emerald-400 border border-emerald-500/30"
              : "bg-red-500/15 text-red-400 border border-red-500/30")
          }
        >
          {available ? "UP" : "DOWN"}
        </span>
      )}
    </>
  );

  return (
    <div className="border border-border rounded-lg overflow-hidden flex flex-col">
      {collapsible ? (
        <button
          type="button"
          onClick={() => setCollapsed((c) => !c)}
          aria-expanded={!collapsed}
          className={"w-full text-left transition-colors hover:bg-accent/40 " + headerClass}
          title={collapsed ? "펼치기" : "접기"}
        >
          {headerInner}
        </button>
      ) : (
        <div className={headerClass}>{headerInner}</div>
      )}
      {!collapsed && <div className="p-4 flex-1">{children}</div>}
    </div>
  );
}
