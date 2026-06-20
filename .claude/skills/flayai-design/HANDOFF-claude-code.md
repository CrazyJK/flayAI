# flayAI — Apple(apple.com) 리스타일 적용 핸드오프 (Claude Code용)

이 문서를 Claude Code에 그대로 전달하세요. 목표: **flayAI 코드베이스를 apple.com 에디토리얼 디자인 언어(DESIGN.md)에 맞춰 리스타일**. 도구 화면 레이아웃은 유지하고, 토큰·컴포넌트 스타일만 Apple화합니다.

- **코드베이스**: https://github.com/CrazyJK/flayAI/tree/main/apps/web (Next.js 16 / React 19 / Tailwind v4)
- **참조 디자인 시스템(스킬)**: `.claude/skills/flayai-design/` — `SKILL.md` → `README.md` → `tokens/`, `components/*.prompt.md`
- **핵심 원칙**: 단일 액센트 **Action Blue `#0066cc`**(라이트) / **Sky Link `#2997ff`**(다크). primary는 **풀 pill**, press는 **scale(0.95)**. 그림자는 제품/포스터 이미지에만 1개. 그라데이션 금지. 시스템 폰트(SF Pro 스택) 유지. 한국어·다크모드 유지.

---

## 1) `apps/web/src/app/globals.css` 토큰 교체

`:root`와 `.dark` 블록의 컬러 토큰을 아래 값으로 변경하세요. **가장 중요한 변경은 `--primary`** (라이트 `#0071e3`→`#0066cc`, 다크 `#0a84ff`→`#2997ff`). 나머지는 apple.com 표면(near-black 타일, hairline 보더)에 정렬.

```css
:root {
  --background: #ffffff;        /* was #f5f5f7 — apple.com 기본 캔버스는 흰색이 지배.
                                   parchment(#f5f5f7)는 --muted/교차 타일로 강등 */
  --foreground: #1d1d1f;
  --card: #ffffff;
  --card-foreground: #1d1d1f;
  --popover: #ffffff;
  --popover-foreground: #1d1d1f;
  --muted: #f5f5f7;             /* parchment */
  --muted-foreground: #6e6e73;
  --accent: #f5f5f7;            /* was #ebebf0 */
  --accent-foreground: #1d1d1f;
  --border: #e0e0e0;            /* was #d2d2d7 — DESIGN.md hairline */
  --input: #e0e0e0;            /* was #d2d2d7 */
  --primary: #0066cc;          /* was #0071e3 — THE Action Blue */
  --primary-foreground: #ffffff;
  --success: #34c759;
  --destructive: #ff3b30;
}

.dark {
  --background: #000000;
  --foreground: #ffffff;        /* was #f5f5f7 */
  --card: #272729;             /* was #1c1c1e — surface-tile-1 */
  --card-foreground: #ffffff;
  --popover: #2a2a2c;          /* was #1c1c1e — surface-tile-2 */
  --popover-foreground: #ffffff;
  --muted: #2a2a2c;            /* was #2c2c2e */
  --muted-foreground: #cccccc; /* was #98989d — body-muted-dark */
  --accent: #2a2a2c;           /* was #2c2c2e */
  --accent-foreground: #ffffff;
  --border: #424245;           /* was #38383a */
  --input: #424245;            /* was #48484a */
  --primary: #2997ff;          /* was #0a84ff — Sky Link Blue (다크 표면용) */
  --primary-foreground: #ffffff;
  --success: #30d158;
  --destructive: #ff453a;
}
```

- `@theme inline { ... }` 블록, 폰트 토큰(`--font-sans`/`--font-mono`), `.diary-mood` / 스크롤바 규칙은 **그대로 둡니다.** 폰트는 이미 SF Pro 시스템 스택이라 변경 불필요.
- ⚠️ 라이트 `--background`를 `#ffffff`로 바꾸는 건 시각적 변화가 큽니다. flayAI는 사실상 다크 우선이라 영향은 작지만, parchment 캔버스를 유지하고 싶으면 `--background: #f5f5f7`로 두고 나머지만 적용하세요.

## 2) 컴포넌트 레벨 규칙 (Tailwind 클래스 — globals.css 밖)

토큰만으로는 안 되는 부분. `apps/web/src/app/_components/` 및 각 화면의 버튼/카드/입력에 적용:

- **Primary 버튼 = 풀 pill**: `rounded-full bg-primary text-primary-foreground px-[22px] py-[11px] active:scale-95 transition-transform`. (Tailwind `rounded-full` = 9999px)
- **유틸리티/secondary 버튼 = 8px**: `rounded-lg bg-muted text-foreground border border-border active:scale-95`. (`rounded-lg` = 8px)
- **검색/단일줄 입력 = pill**: `rounded-full`. 멀티라인 composer는 `rounded-[18px]` 카드.
- **카드**: `rounded-[18px] border border-border bg-card` — **그림자 없음.** 깊이는 표면색 변화(라이트 타일 ↔ near-black 타일)로.
- **그림자는 단 하나** — 제품/포스터 이미지가 표면에 놓일 때만: `shadow-[3px_5px_30px_rgba(0,0,0,0.22)]`. 카드·버튼·텍스트엔 절대 금지.
- **타입 ladder**: 헤드라인 `font-semibold`(600) + 음수 자간(`tracking-tight` 또는 `-tracking-[0.011em]`), 본문 `text-[17px] font-normal`(16px 아님), 캡션 14px. **weight 500 금지** (300/400/600/700만).
- **그라데이션 배경 금지**, 텍스처 금지. 로고는 "flayAI" 플레인 semibold 텍스트.

## 3) 적용 순서 (권장)

1. `globals.css` 토큰 교체 → 전역 컬러가 Action Blue 계열로 전환되는지 확인 (`npm run dev`).
2. 공용 버튼 컴포넌트(있으면)부터 pill/`active:scale-95` 적용 → 전 화면 전파.
3. 카드·입력의 radius/border/shadow를 위 규칙으로 정리.
4. 헤드라인/본문 사이즈·weight를 ladder에 맞춤 (특히 본문 17px, weight 500 제거).
5. 화면별(chat·admin·diary) 시각 점검. 도구 레이아웃 구조는 변경하지 않음.

## 4) 더 깊은 디테일

`.claude/skills/flayai-design/` 안에서:
- `tokens/*.css` — 컬러/타입/스페이싱/반경 전체 토큰 (이 패치의 원본)
- `components/**/*.prompt.md` — Button/Card/Composer/Chip/Tabs/Badge 사용법
- `ui_kits/{search-chat,admin,diary}/` — 도구 레이아웃 유지 + Apple 컴포넌트 적용 예시
- `guidelines/*.card.html` — 컬러/타입/스페이싱/elevation 스펙 카드
- 원본 디자인 분석: https://github.com/CrazyJK/flayAI-design/blob/main/DESIGN.md
