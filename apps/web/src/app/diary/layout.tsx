// 일기장 무드 래퍼 — /diary 이하에만 .diary-mood(세리프 + 따뜻한 색조) 적용.
// 시맨틱 CSS 변수를 이 스코프에서 덮어쓰므로 페이지 코드는 그대로 둔다(globals.css 참조).
export default function DiaryLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="diary-mood flex-1 flex flex-col min-h-0 bg-background text-foreground">
      {children}
    </div>
  );
}
