---
applyTo: "apps/web/**/*.ts,apps/web/**/*.tsx,apps/web/**/*.js,apps/web/**/*.jsx,apps/web/**/*.mjs"
description: "Next.js 16 + React 19 + Tailwind 4 프론트 규칙"
---

# 프론트엔드 지침

`apps/web` — Next.js 16 (App Router) + React 19 + Tailwind 4 + TypeScript. Prettier(2 space, printWidth 100), ESLint(`eslint-config-next`).

## 페이지 구성 (App Router)

| 경로 | 파일 | 내용 |
|------|------|------|
| `/` | `src/app/page.tsx` | 채팅 (SSE 스트리밍) |
| `/image` | `src/app/image/page.tsx` | CLIP 텍스트/이미지 → 포스터 검색 |
| `/face` | `src/app/face/page.tsx` | 얼굴 사진 → 배우 매칭 → 출연작 |
| `/labels` | `src/app/labels/page.tsx` | 얼굴 클러스터 수동 라벨링 |
| `/admin` | `src/app/admin/page.tsx` | 시스템 모니터링 + 인덱서 작업 트리거 |

새 페이지 추가 시 우측 상단 네비게이션 링크도 함께 추가.

## 디자인 — Apple(apple.com 에디토리얼) 스타일 **기본 적용**

화면을 새로 만들거나 고칠 때 **별도 지시가 없어도 이 스타일을 기본**으로 한다. 근거 디자인
시스템은 `.claude/skills/flayai-design/`(`SKILL.md`/`tokens/`/`components/*.prompt.md`),
적용 핸드오프는 `.claude/skills/flayai-design/HANDOFF-claude-code.md`.

- **색·폰트는 토큰으로**: `bg-background`·`text-foreground`·`bg-card`·`text-muted-foreground`·
  `border-border`·`bg-primary` 등 시맨틱 토큰만 쓰면 Apple 팔레트·SF Pro 가 자동 적용된다.
  원시 색(`bg-neutral-*`, `text-blue-*` 등) 하드코딩 금지 — 단일 액센트는 **`primary` 토큰**.
  팔레트 값은 `globals.css`(라이트 `:root`/다크 `.dark`) 한 곳에서만 관리.
- **Primary 버튼 = Action-Blue 풀 pill**: `rounded-full bg-primary text-primary-foreground px-[22px] py-[11px] active:scale-95 transition-transform`.
- **보조/유틸 버튼 = 8px**: `rounded-lg ... border border-border active:scale-95`.
- **입력**: 단일줄 = `rounded-full`(pill), 멀티라인 composer·카드 = `rounded-[18px]`.
- **카드 = `rounded-[18px]`, 그림자 없음.** 깊이는 표면색(타일) 변화로. **그림자는 제품/포스터
  이미지에만 1개**: `shadow-[3px_5px_30px_rgba(0,0,0,0.22)]`. 버튼·카드·텍스트엔 금지.
- **타입**: 헤드라인 `font-semibold`(600) + 음수 자간(`tracking-tight`), 본문 `font-normal`.
  **weight 500(`font-medium`) 금지** — 300/400/600/700만.
- **그라데이션 배경·텍스처 금지.** (단 VideoCard 포스터 위 가독용 스크림 그라데이션은 예외로 유지.)
- **라이트/다크 둘 다 유지**(헤더 토글). 한국어 UI 유지.
- **예외**: `/admin` 은 정보 밀도가 높아 **여백·radius 를 절제**해 적용. `/diary` 는 의도적으로
  별도 무드(`.diary-mood` 세리프·따뜻한 색조) 유지 — Apple 토큰으로 덮지 말 것.

## ESLint 규칙 (준수)

- 내부 페이지 링크에 `<a href="/...">` 금지 → `import Link from "next/link"` 후 `<Link href="/...">` (`@next/next/no-html-link-for-pages`).
- `useEffect` 내 동기 `setState` 는 데이터 로딩 reset 같은 정상 패턴일 때만 `// eslint-disable-next-line react-hooks/set-state-in-effect` 로 억제.
- `useEffect` 제어 흐름에서 로컬 변수 할당 후 미사용 금지.

## API 연동

- 백엔드 베이스 URL 은 환경/호스트(`https://ai.kamoru.jk:8000`)에 따라 다르므로 절대 URL 을 하드코딩하지 말고 기존 페이지의 fetch 패턴을 따른다.
- 채팅은 `POST /api/chat` SSE: `data:` 줄마다 JSON 1건, 이벤트 타입 `tool_call`/`tool_result`/`token`/`done`/`error`. 이 계약은 `packages/rag/router.py` 와 공유 — 한쪽만 바꾸지 말 것.
- 검색 결과 카드는 `hit` 구조(opus, title(ko 우선), studio, release_date, kind, actresses[], poster_path, playable, score?)를 사용. 포스터 이미지는 `GET /static/posters/{opus}`.
- 관리자 페이지는 `GET /api/admin/dashboard`(Qdrant·SQLite·Ollama·인덱서) + `POST /api/admin/jobs/{job}`. 자동 폴링 없이 **수동 새로고침**.

## 실행 / HTTPS

- 개발: `npm run dev` → `next dev -H ai.kamoru.jk --experimental-https` (`.cert/` 인증서 사용).
- 운영: `npm run build` → `node server.js` (커스텀 HTTPS 서버, `bin\prod.bat` 이 호출).
- 코딩 스타일: 들여쓰기 2 space, LF, UTF-8, 파일 끝 개행 (`.editorconfig`).
