// 섹션 카드 — 제목 + (선택) 배지 + (선택) UP/DOWN 가용성 표시.
// 관리자 대시보드(서비스 상태)와 자막 페이지에서 공용.
// available 을 넘기지 않으면 UP/DOWN 배지를 그리지 않는다(서비스 상태가 무의미한 화면용).

export default function SectionCard({
  title,
  badge,
  available,
  children,
}: {
  title: string;
  badge?: string;
  available?: boolean;
  children: React.ReactNode;
}) {
  return (
    <div className="border border-border rounded-lg overflow-hidden flex flex-col">
      <div className="px-4 py-2.5 bg-card flex items-center gap-2 border-b border-border">
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
      </div>
      <div className="p-4 flex-1">{children}</div>
    </div>
  );
}
