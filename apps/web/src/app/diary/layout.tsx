// 일기장 무드 래퍼 — /diary 이하에만 .diary-mood(슬레이트 색조 + Poor Story 손글씨체) 적용.
// 시맨틱 CSS 변수를 이 스코프에서 덮어쓰므로 페이지 코드는 그대로 둔다(globals.css 참조).
import { Poor_Story } from "next/font/google";

// 구글폰트 Poor Story(한글 손글씨체). next/font 가 빌드 타임에 self-host → 런타임 외부 요청 없음.
// preload:false + subsets 생략 = 한글 글리프 포함(모든 subset) & 불필요한 프리로드 회피.
const poorStory = Poor_Story({
  weight: "400",
  display: "swap",
  variable: "--font-poor-story",
  preload: false,
});

export default function DiaryLayout({ children }: { children: React.ReactNode }) {
  return (
    <div
      className={`${poorStory.variable} diary-mood flex-1 flex flex-col min-h-0 bg-background text-foreground`}
    >
      {children}
    </div>
  );
}
