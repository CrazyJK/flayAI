const pptxgen = require("pptxgenjs");
const ROOT = "C:/Handyground/Workspace/git/flayAI";
const PB = ROOT + "/docs/_planbuild";
const LOGO = PB + "/logo.png";
const IMG_NOGPU = PB + "/sidepanel-mockup-v2.png";
const IMG_GPU = PB + "/sidepanel-mockup-v2-gpu.png";

const NAVY = "1F4E79", NAVYDK = "143A5C", STEEL = "2E5A88", ICE = "EAF1F8",
  ICE2 = "DCE8F5", INK = "22262B", GREY = "5B6470", FAINT = "9AA3AF",
  WHITE = "FFFFFF", ORANGE = "E8743B", LINE = "D8DDE6";
const KF = "맑은 고딕";

const p = new pptxgen();
p.defineLayout({ name: "W16x9", width: 13.333, height: 7.5 });
p.layout = "W16x9";
const W = 13.333, H = 7.5;

function footer(s, n) {
  s.addText("핸디소프트 · 서비스개발팀 · 사내 해커톤(바이브코딩) 1차 기획안 공모", {
    x: 0.6, y: 7.05, w: 10, h: 0.3, fontFace: KF, fontSize: 9, color: FAINT, align: "left", valign: "middle",
  });
  s.addText(String(n), { x: 12.4, y: 7.05, w: 0.4, h: 0.3, fontFace: KF, fontSize: 9, color: FAINT, align: "right", valign: "middle" });
}
function title(s, t) {
  s.addText(t, { x: 0.6, y: 0.42, w: 12.1, h: 0.8, fontFace: KF, fontSize: 30, bold: true, color: NAVY, align: "left", valign: "middle" });
}
function circle(s, x, y, dia, fill, label, fc) {
  s.addShape("ellipse", { x, y, w: dia, h: dia, fill: { color: fill } });
  s.addText(label, { x, y, w: dia, h: dia, fontFace: KF, fontSize: 16, bold: true, color: fc || WHITE, align: "center", valign: "middle" });
}

// ============ S1 표지 ============
let s = p.addSlide();
s.addImage({ path: LOGO, x: 0.6, y: 0.55, w: 1.9, h: 1.9 * (77 / 339) });
s.addText("그룹웨어 통합 검색 (RAG)", { x: 0.6, y: 2.5, w: 12.0, h: 1.0, fontFace: KF, fontSize: 44, bold: true, color: NAVY, align: "left" });
s.addText("메일 · 게시판 · 결재를 자연어로 — 사내 활용 + 온프레미스 제품 강화", { x: 0.62, y: 3.55, w: 12.0, h: 0.6, fontFace: KF, fontSize: 19, color: STEEL, align: "left" });
s.addText("핸디소프트 · 서비스개발팀 · 팀장/연구위원 남종관", { x: 0.62, y: 4.5, w: 11, h: 0.4, fontFace: KF, fontSize: 14, color: GREY, align: "left" });
s.addShape("rect", { x: 0, y: 6.35, w: W, h: 1.15, fill: { color: NAVY } });
s.addText([
  { text: "사내 해커톤 (바이브코딩) · 1차 기획안 공모 제출", options: { bold: true } },
  { text: "        v2 · 2026-05-31 · 사내 한정(Confidential)", options: { color: "CADCFC" } },
], { x: 0.6, y: 6.35, w: 12.1, h: 1.15, fontFace: KF, fontSize: 15, color: WHITE, align: "left", valign: "middle" });

// ============ S2 취지(왜) ============
s = p.addSlide();
title(s, "왜? — 흩어진 그룹웨어 정보");
const pains = [
  ["1", "따로 검색", "메일 · 게시판 · 결재를 각각 옮겨 다니며 찾아야 합니다."],
  ["2", "자연어가 약함", "\"재택근무 최신 공지\" 같은 의도로는 키워드 검색이 잘 안 잡습니다."],
  ["3", "중복 · 사일로", "이미 있는 정보를 다시 묻고, 못 찾아 중복 작업이 생깁니다."],
];
pains.forEach((row, i) => {
  const y = 1.75 + i * 1.25;
  circle(s, 0.75, y, 0.62, NAVY, row[0]);
  s.addText(row[1], { x: 1.6, y: y - 0.05, w: 11, h: 0.45, fontFace: KF, fontSize: 19, bold: true, color: INK, valign: "middle" });
  s.addText(row[2], { x: 1.6, y: y + 0.4, w: 11, h: 0.45, fontFace: KF, fontSize: 14, color: GREY, valign: "middle" });
});
s.addShape("roundRect", { x: 0.6, y: 5.75, w: 12.1, h: 0.95, fill: { color: ICE }, rectRadius: 0.08, line: { color: NAVY, width: 1 } });
s.addText([
  { text: "사내 데이터는 외부 SaaS LLM 에 올리기 어렵습니다  →  ", options: { color: INK } },
  { text: "온프레미스 로컬 RAG 가 필요합니다.", options: { bold: true, color: NAVY } },
], { x: 0.95, y: 5.75, w: 11.5, h: 0.95, fontFace: KF, fontSize: 16, valign: "middle" });
footer(s, 2);

// ============ S3 개요 + 사업성 + ROI ============
s = p.addSlide();
title(s, "무엇을 — 그룹웨어 자연어 통합 검색");
s.addText([
  { text: "한 검색창에서 자연어로 검색", options: { bullet: { indent: 18 } } },
  { text: "결과에 출처(작성자·일자·게시판)를 함께 제시", options: { bullet: { indent: 18 } } },
  { text: "권한 준수 — 1차는 사내 게시판 공개 게시물부터", options: { bullet: { indent: 18 } } },
  { text: "검색은 GPU 없이도 동작 (무GPU 검색형)", options: { bullet: { indent: 18 } } },
], { x: 0.6, y: 1.7, w: 5.5, h: 2.8, fontFace: KF, fontSize: 16, color: INK, lineSpacingMultiple: 1.3, valign: "top" });
s.addText([
  { text: "사내 도구를 넘어  →  ", options: { color: INK } },
  { text: "온프레미스 그룹웨어 제품 기능", options: { bold: true, color: NAVY } },
  { text: "  (신규 매출 기회)", options: { color: STEEL } },
], { x: 0.6, y: 4.7, w: 5.6, h: 1.6, fontFace: KF, fontSize: 15, valign: "top", lineSpacingMultiple: 1.2 });
// ROI 스탯 카드 2x2
const stats = [
  ["100명", "사내 사용자(추정)"],
  ["5회/일", "1인 검색"],
  ["≈500건/일", "사내 검색량"],
  ["월 ~330h", "절감(가정·실측 권장)"],
];
stats.forEach((st, i) => {
  const col = i % 2, rw = Math.floor(i / 2);
  const x = 6.5 + col * 3.2, y = 1.75 + rw * 1.75;
  s.addShape("roundRect", { x, y, w: 3.0, h: 1.55, fill: { color: ICE }, rectRadius: 0.08, line: { color: LINE, width: 1 } });
  s.addText(st[0], { x, y: y + 0.18, w: 3.0, h: 0.7, fontFace: KF, fontSize: 30, bold: true, color: ORANGE, align: "center" });
  s.addText(st[1], { x, y: y + 0.92, w: 3.0, h: 0.45, fontFace: KF, fontSize: 12.5, color: GREY, align: "center" });
});
footer(s, 3);

// ============ S4 차별화 4선 ============
s = p.addSlide();
title(s, "차별화 4선");
const diffs = [
  ["①", "온프레미스 · 자사 그룹웨어 내장", "데이터가 밖으로 안 나감 + 우리 제품이라 연동·이식이 쉬움"],
  ["②", "권한 정합", "사용자가 볼 수 있는 문서만. 1차는 공개 게시물만 → 안전하게 시작"],
  ["③", "무GPU → GPU 단계 도입", "GPU 0원으로 가치 입증 후 생성형에만 GPU. 고객 도입 부담↓"],
  ["④", "사이드패널 상주 검색", "그룹웨어 화면 옆에서 바로 — 탭 전환 없는 in-context 검색"],
];
diffs.forEach((dd, i) => {
  const col = i % 2, rw = Math.floor(i / 2);
  const x = 0.6 + col * 6.15, y = 1.7 + rw * 2.35;
  s.addShape("roundRect", { x, y, w: 5.95, h: 2.1, fill: { color: WHITE }, rectRadius: 0.08, line: { color: NAVY, width: 1.25 } });
  circle(s, x + 0.28, y + 0.28, 0.6, NAVY, dd[0]);
  s.addText(dd[1], { x: x + 1.05, y: y + 0.28, w: 4.7, h: 0.65, fontFace: KF, fontSize: 17, bold: true, color: NAVY, valign: "middle" });
  s.addText(dd[2], { x: x + 0.3, y: y + 1.05, w: 5.35, h: 0.9, fontFace: KF, fontSize: 13.5, color: GREY, valign: "top", lineSpacingMultiple: 1.15 });
});
footer(s, 4);

// ============ S5 무GPU 결과 + 화면 ============
s = p.addSlide();
title(s, "무GPU — 검색형 (모드 A)  ·  해커톤 데모 범위");
s.addText([
  { text: "GPU 0원으로 시작 (기존 CPU 서버 1대)", options: { bullet: { indent: 18 } } },
  { text: "결과 = 출처 게시물 카드 + 스니펫", options: { bullet: { indent: 18 } } },
  { text: "환각 없음 — 지어내지 않고 출처만 제시", options: { bullet: { indent: 18 } } },
  { text: "100명 · 일 500건엔 CPU 1대로 충분", options: { bullet: { indent: 18 } } },
  { text: "사이드패널에서 현재 화면 맥락으로 검색", options: { bullet: { indent: 18 } } },
], { x: 0.6, y: 1.7, w: 5.0, h: 4.0, fontFace: KF, fontSize: 16, color: INK, lineSpacingMultiple: 1.35, valign: "top" });
s.addImage({ path: IMG_NOGPU, x: 5.95, y: 1.55, w: 6.9, h: 6.9 * (1327 / 2441) });
s.addText("화면: 검색 결과 = 공개 게시물 출처 카드", { x: 5.95, y: 5.45, w: 6.9, h: 0.35, fontFace: KF, fontSize: 11, italic: true, color: GREY, align: "center" });
footer(s, 5);

// ============ S6 GPU 결과 + 화면 ============
s = p.addSlide();
title(s, "GPU — 생성형 (모드 B)  ·  확장 단계");
s.addText([
  { text: "요약 답변 + 인용 출처 [1][2]", options: { bullet: { indent: 18 } } },
  { text: "근거 부족 시 보류(abstain) — 검색 결과만 제시", options: { bullet: { indent: 18 } } },
  { text: "GPU 는 이 단계부터 (1× 24GB급)", options: { bullet: { indent: 18 } } },
  { text: "이후 멀티모달·시각자료 검색으로 확장", options: { bullet: { indent: 18 } } },
  { text: "온프레미스 고객도 옵션으로 선택", options: { bullet: { indent: 18 } } },
], { x: 0.6, y: 1.7, w: 5.0, h: 4.0, fontFace: KF, fontSize: 16, color: INK, lineSpacingMultiple: 1.35, valign: "top" });
s.addImage({ path: IMG_GPU, x: 5.95, y: 1.55, w: 6.9, h: 6.9 * (1327 / 2441) });
s.addText("화면: 질문에 요약 답변 + [1][2] 인용 (출처 카드 동반)", { x: 5.95, y: 5.45, w: 6.9, h: 0.35, fontFace: KF, fontSize: 11, italic: true, color: GREY, align: "center" });
footer(s, 6);

// ============ S7 단계 / 로드맵 ============
s = p.addSlide();
title(s, "작게 시작해 제품으로 — 단계 도입");
const steps = [
  ["P0", "환경", false],
  ["P1", "게시판 MVP\n(무GPU·데모)", true],
  ["P2", "권한·메일/결재", false],
  ["P3", "생성형\n(GPU)", false],
  ["P4", "제품화\n(온프레미스)", false],
  ["P5", "운영·확장", false],
];
const sw = 1.92, gap = 0.13, sx0 = 0.6, sy = 2.5;
steps.forEach((st, i) => {
  const x = sx0 + i * (sw + gap);
  const hl = st[2];
  s.addShape("roundRect", { x, y: sy, w: sw, h: 1.9, rectRadius: 0.08, fill: { color: hl ? NAVY : ICE }, line: { color: hl ? NAVY : LINE, width: 1 } });
  s.addText(st[0], { x, y: sy + 0.18, w: sw, h: 0.55, fontFace: KF, fontSize: 22, bold: true, color: hl ? WHITE : NAVY, align: "center" });
  s.addText(st[1], { x: x + 0.1, y: sy + 0.78, w: sw - 0.2, h: 1.0, fontFace: KF, fontSize: 12.5, color: hl ? "CADCFC" : GREY, align: "center", valign: "top", lineSpacingMultiple: 1.05 });
});
s.addText([
  { text: "무GPU: P1~P2", options: { bold: true, color: NAVY } },
  { text: "   ·   GPU: P3부터   ·   제품화: P4   ·   ", options: { color: INK } },
  { text: "해커톤 데모 = P1 (게시판·무GPU·사이드패널)", options: { bold: true, color: ORANGE } },
], { x: 0.6, y: 5.0, w: 12.1, h: 0.6, fontFace: KF, fontSize: 15, align: "center", valign: "middle" });
s.addShape("roundRect", { x: 0.6, y: 5.85, w: 12.1, h: 0.85, fill: { color: ICE }, rectRadius: 0.08 });
s.addText("작게 시작해 검증하고, 검증된 기능을 그룹웨어 제품으로 키웁니다.", { x: 0.9, y: 5.85, w: 11.5, h: 0.85, fontFace: KF, fontSize: 15, color: STEEL, bold: true, valign: "middle" });
footer(s, 7);

// ============ S8 마무리 ============
s = p.addSlide();
s.background = { color: NAVY };
s.addText("작게 시작해 검증하고,\n그룹웨어 제품으로 키운다.", { x: 0.8, y: 1.5, w: 11.7, h: 1.8, fontFace: KF, fontSize: 34, bold: true, color: WHITE, valign: "top", lineSpacingMultiple: 1.1 });
s.addText([
  { text: "핵심 결정 사항 (검토 회의)", options: { bold: true, color: "CADCFC", fontSize: 16 } },
  { text: "\n· 게시판 연동 방식 · 공개/제한 판정 기준", options: { color: WHITE, fontSize: 15 } },
  { text: "\n· 제품화(그룹웨어 탑재) 시점 · 패키징", options: { color: WHITE, fontSize: 15 } },
  { text: "\n· 확장 우선순위 (메일 vs 결재)", options: { color: WHITE, fontSize: 15 } },
], { x: 0.85, y: 3.5, w: 11, h: 2.0, fontFace: KF, valign: "top", lineSpacingMultiple: 1.25 });
s.addText("감사합니다.  핸디소프트 · 서비스개발팀 · 남종관", { x: 0.85, y: 6.5, w: 11.6, h: 0.5, fontFace: KF, fontSize: 14, color: "CADCFC" });

p.writeFile({ fileName: ROOT + "/docs/enterprise-rag-plan-v2-deck.pptx" }).then((f) => console.log("WROTE", f));
