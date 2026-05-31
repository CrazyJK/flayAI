const fs = require("fs");
const {
  Document, Packer, Paragraph, TextRun, Table, TableRow, TableCell, ImageRun,
  AlignmentType, LevelFormat, TabStopType,
  TableOfContents, HeadingLevel, BorderStyle, WidthType, ShadingType,
  VerticalAlign, PageNumber, PageBreak, Header, Footer,
} = require("docx");

const ROOT = "C:/Handyground/Workspace/git/flayAI";
const IMG = ROOT + "/docs/_planbuild/sidepanel-mockup.png";
const LOGO = ROOT + "/docs/_planbuild/logo.png";

// ---- 상수/팔레트 ------------------------------------------------
const CW = 9026;
const ACCENT = "1F4E79";
const HEADER_FILL = "1F4E79";
const ZEBRA = "F4F8FC";
const LIGHT = "EAF1F8";
const BORDER = "BFBFBF";
const GREY = "808080";
const BODY = "맑은 고딕";
const CODE_FONT = "Consolas";

// ---- 인라인 파서 (**bold**, `code`, *italic*) -------------------
function inline(text, base = {}) {
  const out = [];
  const re = /(\*\*([^*]+)\*\*|`([^`]+)`|\*([^*]+)\*)/g;
  let last = 0, m;
  while ((m = re.exec(text)) !== null) {
    if (m.index > last) out.push(new TextRun({ ...base, text: text.slice(last, m.index) }));
    if (m[2] !== undefined) out.push(new TextRun({ ...base, text: m[2], bold: true }));
    else if (m[3] !== undefined) out.push(new TextRun({ ...base, text: m[3], font: CODE_FONT }));
    else if (m[4] !== undefined) out.push(new TextRun({ ...base, text: m[4], italics: true }));
    last = re.lastIndex;
  }
  if (last < text.length) out.push(new TextRun({ ...base, text: text.slice(last) }));
  if (!out.length) out.push(new TextRun({ ...base, text: "" }));
  return out;
}

// ---- 단락 헬퍼 --------------------------------------------------
function p(text, opts = {}) {
  return new Paragraph({ spacing: { after: 120, line: 276 }, children: inline(text, opts.run || {}), ...opts.pp });
}
function h1(text) { return new Paragraph({ heading: HeadingLevel.HEADING_1, children: [new TextRun(text)] }); }
function h2(text) { return new Paragraph({ heading: HeadingLevel.HEADING_2, children: [new TextRun(text)] }); }
function bullet(text, level = 0) {
  return new Paragraph({ numbering: { reference: "b", level }, spacing: { after: 60, line: 270 }, children: inline(text) });
}
function numbered(ref, text) {
  return new Paragraph({ numbering: { reference: ref, level: 0 }, spacing: { after: 60, line: 270 }, children: inline(text) });
}
function callout(text) {
  return new Paragraph({
    spacing: { before: 80, after: 160, line: 276 },
    shading: { type: ShadingType.CLEAR, fill: LIGHT },
    border: { left: { style: BorderStyle.SINGLE, size: 18, color: ACCENT, space: 8 } },
    indent: { left: 200, right: 140 },
    children: inline(text),
  });
}
function diffItem(title, bodyTxt, notes) {
  const arr = [
    new Paragraph({ spacing: { before: 180, after: 40 }, children: inline(title, { bold: true, color: ACCENT, size: 22 }) }),
    p(bodyTxt),
  ];
  (notes || []).forEach((n) =>
    arr.push(new Paragraph({ indent: { left: 360 }, spacing: { after: 40, line: 270 }, children: inline("↳ " + n) })));
  return arr;
}
function caption(text) {
  return new Paragraph({ alignment: AlignmentType.CENTER, spacing: { before: 40, after: 160 },
    children: inline(text, { italics: true, color: GREY, size: 16 }) });
}

// ---- 표 헬퍼 ----------------------------------------------------
const Bd = { style: BorderStyle.SINGLE, size: 4, color: BORDER };
const cellBorders = { top: Bd, bottom: Bd, left: Bd, right: Bd };
function cell(text, { width, fill, bold = false, white = false, align, size } = {}) {
  return new TableCell({
    width: { size: width, type: WidthType.DXA },
    borders: cellBorders,
    shading: fill ? { type: ShadingType.CLEAR, fill } : undefined,
    margins: { top: 60, bottom: 60, left: 100, right: 100 },
    verticalAlign: VerticalAlign.CENTER,
    children: [new Paragraph({ alignment: align, spacing: { after: 0, line: 252 },
      children: inline(String(text), { bold, color: white ? "FFFFFF" : undefined, size }) })],
  });
}
function table(colWidths, header, rows, { bodySize, firstColBold = false } = {}) {
  const trs = [];
  trs.push(new TableRow({ tableHeader: true,
    children: header.map((t, i) => cell(t, { width: colWidths[i], fill: HEADER_FILL, bold: true, white: true, align: AlignmentType.CENTER })) }));
  rows.forEach((r, ri) => {
    const fill = ri % 2 === 1 ? ZEBRA : undefined;
    trs.push(new TableRow({ children: r.map((t, i) => cell(t, { width: colWidths[i], fill, size: bodySize, bold: firstColBold && i === 0 })) }));
  });
  return new Table({ width: { size: colWidths.reduce((a, b) => a + b, 0), type: WidthType.DXA }, columnWidths: colWidths, rows: trs });
}
function spacer() { return new Paragraph({ spacing: { after: 80 }, children: [new TextRun("")] }); }
function ctr(text, size, opts = {}) {
  return new Paragraph({ alignment: AlignmentType.CENTER, spacing: opts.spacing || { after: 0 },
    children: [new TextRun({ text, size, ...opts })] });
}

// =================================================================
// 본문
// =================================================================
const body = [];

// ---- 표지 (Q1) ----
body.push(ctr("핸디소프트 (HANDYSOFT)", 26, { bold: true, color: ACCENT, spacing: { before: 1200, after: 0 } }));
body.push(ctr("서비스개발팀", 18, { color: "595959", spacing: { before: 40, after: 0 } }));
body.push(ctr("사내 업무 통합 검색 시스템 (RAG)", 46, { bold: true, color: ACCENT, spacing: { before: 760, after: 0 } }));
body.push(ctr("메일 · 게시물 · 결재문서 자연어 통합 검색", 25, { color: "404040", spacing: { before: 150, after: 0 } }));
body.push(ctr("개발 기획서 (초안)", 24, { bold: true, spacing: { before: 80, after: 0 } }));
// 제출 배너
body.push(new Paragraph({ alignment: AlignmentType.CENTER, spacing: { before: 620, after: 0 },
  shading: { type: ShadingType.CLEAR, fill: LIGHT },
  border: { top: { style: BorderStyle.SINGLE, size: 6, color: ACCENT, space: 6 }, bottom: { style: BorderStyle.SINGLE, size: 6, color: ACCENT, space: 6 } },
  children: [new TextRun({ text: "사내 해커톤 (바이브코딩) — 1차 기획안 공모 제출", size: 22, bold: true, color: ACCENT })] }));
body.push(ctr("작성자  남종관 (서비스개발팀 · 팀장/연구위원)", 20, { spacing: { before: 560, after: 0 } }));
body.push(ctr("버전 v1.0 (초안) · 작성일 2026-05-31", 20, { color: "595959", spacing: { before: 60, after: 0 } }));
body.push(ctr("분류: 사내 한정 (Confidential) · 온프레미스 전용", 20, { color: "C00000", spacing: { before: 40, after: 0 } }));
body.push(new Paragraph({ children: [new PageBreak()] }));

// ---- 목차 ----
body.push(h1("목차"));
// 필드(TOC) 대신 정적 목록 — 열람 시 '필드 업데이트' 경고가 뜨지 않도록.
[
  "요약",
  "1. 배경 & 문제",
  "2. 목표 & 범위",
  "3. 사용자 시나리오 (예시)",
  "4. 핵심 설계 원칙",
  "5. 차별화 포인트 (특장점)",
  "6. 아키텍처 (빅 픽처)",
  "7. 데이터 파이프라인 (소스 → 검색 가능 인덱스)",
  "8. 기술 스택 선택 (Linux · 멀티유저)",
  "9. 멀티유저 · 권한 · 보안",
  "10. 구성 옵션 — 무GPU(검색형) vs GPU(생성형)",
  "11. 성능 · 하드웨어 스펙",
  "12. 단계별 로드맵",
  "13. 리스크 & 대응",
  "14. 결정 필요 사항",
].forEach((t) => body.push(new Paragraph({
  spacing: { after: 70, line: 276 }, indent: { left: 220 },
  children: [new TextRun({ text: t, size: 22 })],
})));
body.push(new Paragraph({ children: [new PageBreak()] }));

// ---- 요약 ----
body.push(h1("요약"));
body.push(callout("사내에 흩어진 **메일 · 게시물 · 결재문서**를, 권한을 지키면서 **자연어 한 문장으로 통합 검색**할 수 있는 사내 전용 RAG 시스템입니다. 사내망·온프레미스 환경에서만 동작하며, 데이터를 외부로 내보내지 않습니다."));
body.push(h2("용어 빠른 정의 (AI/ML 입문자용)"));
body.push(bullet("**RAG (Retrieval-Augmented Generation)**: \"먼저 검색해서 찾은 문서를 LLM 에게 보여주고 답하게 한다\"는 방식입니다. LLM 단독이 아니라 *DB 검색 + LLM 종합*."));
body.push(bullet("**임베딩(embedding)**: 문장을 의미를 담은 숫자 벡터(예: 1024차원)로 바꾼 것입니다. 의미가 비슷하면 벡터도 가까워, \"예산 회의\"와 \"비용 검토\"를 키워드 없이도 연결합니다."));
body.push(bullet("**하이브리드 검색**: 키워드 검색(BM25)과 의미 검색(벡터)을 **함께** 돌려 합치는 방식입니다. 정확한 이름·번호는 키워드가, 자연어 의도는 벡터가 보완합니다."));
body.push(bullet("**리랭커(reranker)**: 1차로 넓게 찾은 후보를 질의와 **함께** 정밀 비교해 다시 순위를 매기는 모델(cross-encoder)입니다. 검색 정확도를 끌어올리는 RAG 표준 단계입니다."));
body.push(bullet("**청킹(chunking)**: 긴 문서를 검색 단위(문단/섹션)로 나누는 것입니다. 결재문서·긴 메일은 통째로 임베딩하면 정확도가 떨어져 나눕니다."));

// ---- 1. 배경 ----
body.push(h1("1. 배경 & 문제"));
body.push(bullet("사내 업무 정보가 **시스템별로 흩어져** 있습니다: 메일(메일서버), 공지·게시물(그룹웨어/게시판), 결재문서(전자결재 시스템)."));
body.push(bullet("필요할 때마다 시스템을 옮겨 다니며 키워드로 찾아야 하고, 정확한 제목·작성자·기간을 기억해야 합니다. \"작년 4분기 예산 관련 결재 건\" 같은 자연어 의도로는 찾기가 어렵습니다."));
body.push(bullet("그러다 보니 이미 사내에 있는 정보를 다시 묻거나, 찾지 못해 중복 작업이 생기기도 합니다."));
body.push(bullet("사내 데이터는 보안·컴플라이언스상 외부 SaaS LLM 에 올리기 어렵습니다 → **온프레미스 로컬 LLM** 이 필요합니다."));

// ---- 2. 목표 & 범위 ----
body.push(h1("2. 목표 & 범위"));
body.push(h2("2.1 목표"));
body.push(numbered("goals", "메일·게시물·결재문서를 **한 검색창**에서 자연어로 검색합니다."));
body.push(numbered("goals", "결과에 **출처(원문 링크·작성자·일자·시스템)**를 함께 보여 주고, 필요하면 **요약 답변 + 인용**을 제공합니다."));
body.push(numbered("goals", "**권한을 철저히 지킵니다** — 접근 권한이 없는 문서는 검색·답변·요약 어디에도 노출하지 않습니다."));
body.push(numbered("goals", "**다중 사용자 동시 접속**에서도 쾌적한 응답 속도를 목표로 합니다(목표 SLA 는 §11)."));
body.push(numbered("goals", "사내망 전용으로 운영하며, 외부 인터넷에는 노출하지 않습니다(전송·저장 암호화, 감사 로그)."));
body.push(h2("2.2 범위 (In Scope)"));
body.push(bullet("데이터 소스: **메일 · 게시물 · 결재문서**(1차). 첨부파일(pdf/docx/xlsx/hwp/이미지) 텍스트 추출을 포함합니다."));
body.push(bullet("검색 모드: ① 검색(문서 카드+스니펫) ② RAG 답변(요약+인용) — 둘 다 제공하거나 단계적으로 도입합니다(§4.2)."));
body.push(bullet("권한 기반 필터링, SSO 로그인, 감사 로그."));
body.push(h2("2.3 비범위 (Out of Scope, 1차 제외 — 결정 필요)"));
body.push(bullet("실시간 채팅/그룹웨어 대체, 문서 작성·결재 기능(본 시스템은 검색에 집중합니다)."));
body.push(bullet("외부(인터넷) 정보 검색."));
body.push(bullet("`[TBD]` 음성 검색, 모바일 전용 앱, 다국어 UI 등."));

// ---- 3. 시나리오 ----
body.push(h1("3. 사용자 시나리오 (예시)"));
body.push(table([3000, 6026], ["질의 예", "기대 동작"], [
  ["\"지난 분기 마케팅 예산 결재 문서 찾아줘\"", "결재문서, 기간(분기)·부서 필터 + 의미검색 → 카드 + 요약"],
  ["\"김부장이 보낸 보안 점검 관련 메일\"", "메일, 발신자=김부장 + 주제 의미검색"],
  ["\"재택근무 정책 최신 공지\"", "게시물, 의미검색 + 최신순"],
  ["\"이 프로젝트 관련 메일·결재·게시물 다 모아줘\"", "소스 통합 검색, 프로젝트명 의미검색"],
  ["\"작년 12월 출장비 정산 어떻게 했더라\"", "결재+메일, 기간 필터 + RAG 요약(인용)"],
]));
body.push(spacer());
body.push(callout("위 질의는 모두 *질의한 사용자가 볼 수 있는 문서 안에서만* 동작합니다."));

// ---- 4. 핵심 설계 원칙 ----
body.push(h1("4. 핵심 설계 원칙"));
body.push(h2("4.1 검색 코어"));
body.push(bullet("**하이브리드 검색**: 의미 검색(벡터)과 키워드 검색(BM25, 한국어 형태소)을 함께 수행하고 **RRF(Reciprocal Rank Fusion)** 로 결합합니다. 정확한 이름·번호는 키워드가, 자연어 의도는 벡터가 보완합니다."));
body.push(bullet("**리랭커**: RRF 상위 후보를 cross-encoder 로 다시 정렬해 정확도를 높입니다."));
body.push(bullet("**권한 우선(permission-first)**: 검색의 모든 단계에서 사용자가 볼 수 있는 문서만 후보로 둡니다(§9)."));
body.push(bullet("**증분·멱등 인덱싱**: 변경분만 반영하고 단계별 재실행이 안전하도록 설계해, 대량 초기 인덱싱과 운영 동기화를 안정적으로 처리합니다."));
body.push(bullet("**로컬 LLM**: 질의·문서가 외부로 나가지 않도록 온프레미스에서 추론합니다."));
body.push(callout("본 시스템에서 새로 풀어야 하는 핵심 과제는 **① 다양한 사내 소스 연동 ② 권한 정확성 ③ 멀티유저 성능** 세 가지입니다. 검색 알고리즘 자체보다 이 셋이 난이도를 좌우합니다."));
body.push(h2("4.2 검색 모드 (2가지 — 단계 도입 가능)"));
body.push(bullet("**모드 A: 검색(Retrieval-only)** — 문서 카드 + 강조 스니펫 + 출처. LLM 답변은 두지 않거나 1줄 요약만 둡니다. 빠르고 환각이 없습니다."));
body.push(bullet("**모드 B: RAG 답변(Generation)** — 상위 문서를 LLM 에 넣어 **요약 답변 + 인용 출처**를 만듭니다. \"요약해줘/정리해줘\" 류에 유용하지만 환각·권한 누출 가능성이 있어 인용 강제·권한 필터 후처리를 함께 둡니다."));
body.push(bullet("**제안**: 1차에는 모드 A 로 안전하게 시작하고, 검증 후 모드 B 를 더하는 방식을 권장합니다(또는 처음부터 B 포함)."));

// ---- 5. 차별화 ----
body.push(h1("5. 차별화 포인트 (특장점)"));
body.push(callout("2025~2026년 기준 **하이브리드 검색 · 리랭킹 · 권한 인식**은 이미 업계의 *기본기(table stakes)* 에 가깝습니다. 차별성은 그 위에 더하는 아래 설계에서 나옵니다. 업계가 공통으로 지적하는 RAG 실패 원인(근거가 약할 때의 환각 / stale·삭제 누락 / 시간 정보 오류 / 권한 누출 / 인용 부재)을 최대한 줄이는 것을 목표로 합니다."));
body.push(h2("5.1 한눈에 — 기본기 vs 본 시스템"));
body.push(table([3600, 5426], ["이미 업계 표준 (기본기)", "본 시스템이 더하는 차별화"], [
  ["하이브리드 검색 + 리랭커", "+ **결정론적 메타·시간 추출 가드레일** (§5.2-②)"],
  ["권한 인식 검색", "+ **삭제·권한회수 전파** + 누출 테스트 상시 (§5.2-⑤)"],
  ["출처 인용", "+ **근거 부족 시 답변 보류(abstain)** (§5.2-③)"],
  ["단일 소스별 검색", "+ **크로스소스 엔티티·스레드 통합** (§5.2-①)"],
  ["첨부 OCR 텍스트 색인", "+ **VLM 의미 캡션**(도표/스캔/표) (§5.2-④)"],
  ["블랙박스 유사도 정렬", "+ **점수 분해·감사 + 조직 신호 랭킹** (§5.2-⑥)"],
  ["별도 검색 포털(탭 전환)", "+ **브라우저 사이드패널 상주 검색**(컨텍스트 전환 0) (§5.2-⑧)"],
  ["결과 올 때까지 화면 대기", "+ **비동기 결과 + 포커스 없으면 OS(윈도우) 알림** (§5.2-⑨)"],
]));
body.push(h2("5.2 차별화 9선"));
diffItem("① 크로스소스 엔티티·스레드 통합",
  "같은 인물·프로젝트·안건이 메일·게시물·결재에 서로 다른 식별자(메일주소·사번·한글/영문 이름)로 흩어져 있습니다. 별칭을 **표준 엔티티(canonical)** 로 정규화하고 공통 키로 소스를 가로질러 묶어, 개별 문서를 나열하는 대신 **\"이 안건의 메일 → 결재 → 공지\" 한 묶음(맥락)** 으로 보여 줍니다.",
  ["*왜 다른가요?* 대부분의 사내 검색은 문서를 따로따로 돌려줍니다. 무거운 GraphRAG 없이도 **가벼운 결정론적 엔티티 해소**로 통합 맥락을 만듭니다."]).forEach((x) => body.push(x));
diffItem("② 결정론적 메타·시간 추출 가드레일",
  "질의에서 기간(\"작년 4분기\", \"2024-03\")·부서·문서종류·결재상태·작성자를 **코드(규칙)로 추출**해 *하드 필터*로 적용합니다. LLM 이 빠뜨리거나 잘못 채워도 보완됩니다.",
  ["*왜 다른가요?* 순수 임베딩 RAG 는 \"2024년 3분기\" 같은 표현을 의미 벡터로만 처리해 날짜·숫자에서 부정확해지기 쉽습니다(이른바 *temporal hallucination*). 메타데이터를 정확도·보안의 기준선으로 다룹니다."]).forEach((x) => body.push(x));
diffItem("③ 환각 없는 \"검색 우선\" + 근거 부족 시 답변 보류(abstain)",
  "기본은 출처 카드(생성 없음)라서 빠르고 거의 틀리지 않습니다. 요약 답변(생성)은 사용자가 요청할 때만 수행하고, 그때도 **인용을 함께 제시**하며 **근거(유사도)가 약하면 \"근거가 부족합니다\"라고 보류**합니다.",
  ["*왜 다른가요?* 많은 RAG 는 *항상* 생성하다 보니 자료에 없는 내용도 그럴듯하게 만들어내곤 합니다. 업무 환경에서는 부담이 크기 때문에, '확실하지 않으면 단정하지 않는다'를 기본값으로 둡니다."]).forEach((x) => body.push(x));
diffItem("④ 멀티모달 첨부 의미 이해 (OCR 너머)",
  "스캔 결재·표·PPT 도표·이미지 첨부를 비전 모델(VLM)이 **한국어 설명문**으로 바꿔 본문 임베딩에 합칩니다. 그 결과 \"그래프가 보여 주는 내용\"이나 \"도장 찍힌 스캔본\"까지 검색됩니다.",
  ["*왜 다른가요?* 많은 시스템은 OCR 로 뽑은 글자만 색인해 도표·레이아웃의 *의미*는 놓치는 경우가 많습니다."]).forEach((x) => body.push(x));
diffItem("⑤ 삭제·최신성 정합 (stale / 권한회수 방어)",
  "소스-인덱스 **공통 식별자** + 증분 동기화 + **삭제 전파**(원본에서 지워지면 인덱스에서도 곧바로 제거하고, 권한 회수도 함께 반영)로 인덱스를 항상 원본과 맞춥니다.",
  ["*왜 다른가요?* 주기적 전체 재색인에만 기대면 삭제·권한 회수가 누락돼 **지워졌거나 권한이 없는 문서가 검색에 남을** 수 있습니다. 업계에서도 특히 주의가 필요한 부분으로 꼽습니다."]).forEach((x) => body.push(x));
diffItem("⑥ 설명가능·감사가능 + 조직 신호 랭킹",
  "각 결과의 점수 분해(의미·키워드·조직 신호·최신성)를 보여 주어 \"왜 이 순위인지\"를 설명하고, 모든 질의·열람을 감사 로그로 남깁니다. 단순 유사도뿐 아니라 **최근성·열람 빈도·결재 완료·내 부서 관련성**을 함께 반영해 \"업무적으로 중요한\" 순서를 만듭니다. 가중치는 정답셋(eval)으로 조정합니다.",
  ["*왜 다른가요?* 블랙박스 검색에 비해 신뢰·튜닝·컴플라이언스 면에서 유리하고, 코사인 정렬만으로는 놓치기 쉬운 실무 우선순위를 반영합니다."]).forEach((x) => body.push(x));
diffItem("⑦ 한국어·한국 업무 특화 + 완전 온프레미스(데이터 주권)",
  "nori 형태소 + 한국어 리랭커 + **HWP/HWPX 파싱** + 사번·직급·부서·결재선 등 한국 조직 구조 이해. 로컬 LLM 으로 질의·문서를 **외부로 내보내지 않습니다**.",
  ["*왜 다른가요?* 글로벌 SaaS 형 솔루션은 HWP·결재선·한글 조직도·데이터 주권 측면에서 상대적으로 약한 편입니다. 규제·보안 환경에 자연스럽게 맞습니다."]).forEach((x) => body.push(x));
diffItem("⑧ 브라우저 사이드패널 상주 검색 (Side Panel API)",
  "크롬/엣지 확장의 **Side Panel API**(`chrome.sidePanel`, Manifest V3)로 검색 UI 를 브라우저 우측 패널에 상주시킵니다. 메일·그룹웨어·결재 화면을 **그대로 둔 채** 옆 패널에서 검색·참조할 수 있어 **탭 전환이나 별도 포털 이동이 필요 없습니다.** 패널은 현재 보고 있는 탭의 맥락(선택한 텍스트, 결재 문서번호·게시글 URL 등)을 읽어 \"지금 이 문서와 관련된 것\" 검색·요약으로 바로 이어 갈 수 있습니다. 사내 브라우저 정책으로 확장을 **일괄 배포**하면 모든 직원이 어느 업무 화면에서든 곧바로 사용할 수 있습니다.",
  ["*왜 다른가요?* 대부분의 사내 검색은 \"검색 포털에 따로 접속\"하는 방식이라 업무 흐름이 끊기기 쉽습니다. 사이드패널 상주 + 현재 화면 맥락 연동은 **업무를 멈추지 않는(in-context) 검색**이라는 점에서 실사용 경험이 다릅니다(웹 앱 단독 접속·기존 시스템 임베드 위젯과도 병행할 수 있습니다).",
   "*참고(범위/제약)*: 크로뮴 계열(Chrome 114+ · Edge) Side Panel API 에 의존합니다 → 표준 채택 브라우저·확장 배포 정책 확인이 필요합니다(§14). 비지원 환경에서는 웹 앱으로 자연스럽게 대체합니다."]).forEach((x) => body.push(x));
// ⑧ 예상 화면 목업 (Q2)
body.push(new Paragraph({ alignment: AlignmentType.CENTER, spacing: { before: 120, after: 40 },
  children: [new ImageRun({ type: "png", data: fs.readFileSync(IMG),
    transformation: { width: 624, height: 339 },
    altText: { title: "사내 포털 + 통합 검색 사이드패널", description: "실제 사내 포털 화면 우측 보조 패널을 통합 검색 패널로 대체한 합성", name: "portalSidepanelMockup" } })] }));
body.push(caption("[그림] 실제 사내 포털 화면 그대로에, 우측 보조 패널(기존 Copilot 자리)만 통합 검색 패널로 대체한 합성 예상 화면. 현재 화면 맥락 칩(⑧)·결과 카드(결재/메일/게시물)·비활성 시 Windows 알림(⑨)을 함께 나타냈으며, 실제 UI 와 다를 수 있습니다."));
diffItem("⑨ 비동기 결과 전달 — 브라우저 비활성 시 OS(윈도우) 알림",
  "무거운 질의(모드 B 요약 생성, 멀티소스 딥서치 등)는 시간이 조금 걸릴 수 있습니다. 사용자가 질의를 던지고 다른 일을 하더라도, 결과가 준비되면 **브라우저·탭이 포커스가 아니어도 윈도우 OS 알림(toast)** 으로 알려 주고, 알림을 클릭하면 사이드패널/웹 앱이 결과 화면으로 이동합니다. 웹 앱은 Web Notifications API(`Notification`), 사이드패널 확장은 `chrome.notifications`(확장 서비스 워커)로 구현하며, 후자는 브라우저가 최소화·비활성인 상태에서도 동작합니다.",
  ["*왜 다른가요?* 많은 사내 검색은 \"결과가 올 때까지 화면을 지켜보는\" 동기 방식입니다. **fire-and-forget + OS 알림**은 온프레미스 LLM 생성·딥서치의 대기 시간을 자연스럽게 가려 주고, 업무를 멈추지 않는 사용 흐름(⑧)을 완성합니다.",
   "*참고(범위/제약)*: OS 알림은 사용자 동의가 필요하고 사내 OS 알림 정책(집중 지원/방해 금지)의 영향을 받을 수 있습니다 → 인앱 배지·결과 큐로도 대체합니다. 짧은 질의(모드 A, 수초 이내)는 알림 없이 바로 표시합니다."]).forEach((x) => body.push(x));
body.push(callout("위 9가지는 §6 이후의 아키텍처·파이프라인·권한 설계로 구체화됩니다. ②③⑤는 §13 리스크의 핵심 실패 모드를 직접 완화하는 장치이고, ⑧⑨는 \"업무를 멈추지 않는\" 접근·결과 전달 경험으로 §12 로드맵 후반(접근 채널 확장)과 이어집니다."));

// ---- 6. 아키텍처 ----
body.push(h1("6. 아키텍처 (빅 픽처)"));
body.push(p("전체 구성을 계층으로 나타내면 다음과 같습니다. **질의는 위→아래**(사용자 → 검색/LLM → 데이터 저장소)로, **인덱싱은 아래→위**(소스 커넥터 → 데이터 저장소)로 흐르며, 두 서브시스템은 데이터 저장소를 통해 연결됩니다."));
body.push(table([2400, 6626], ["계층", "구성 / 역할"], [
  ["사용자 채널", "웹 앱(단독 접속) · 브라우저 사이드패널 확장(Side Panel API). 동일 API 호출 (§5.2-⑧)."],
  ["인증 · 게이트웨이", "SSO(OIDC/SAML) 로그인 → API Gateway(async, 다중 워커): 인증·권한(그룹/부서) 확보, 질의 라우팅, 권한 필터 주입, 감사 로그. HTTPS·사내망 전용."],
  ["검색 레이어", "① 하이브리드 검색(벡터 + 키워드) → ② RRF 결합 → ③ 리랭커(cross-encoder) → ④ 권한 ACL 필터."],
  ["LLM 서빙", "vLLM/TGI: 질의 라우팅, RAG 답변 + 인용 생성."],
  ["임베딩 서버", "임베딩 · 리랭커 모델 서빙(예: TEI)."],
  ["데이터 저장소", "벡터 DB(의미검색) · 전문검색(BM25, 한국어 형태소) · 메타/권한/감사 DB · 원문/첨부 스토리지."],
  ["인덱싱 · 소스 커넥터", "증분·멱등 인덱싱 파이프라인 ← 메일서버 · 게시판/그룹웨어 · 전자결재 시스템."],
]));

// ---- 7. 데이터 파이프라인 ----
body.push(h1("7. 데이터 파이프라인 (소스 → 검색 가능 인덱스)"));
body.push(h2("7.1 소스 커넥터 (증분 동기화)"));
body.push(table([1000, 3100, 3100, 1826], ["소스", "연동 방식 후보", "추출 대상", "비고"], [
  ["메일", "Exchange(EWS/Graph) · IMAP · 메일 아카이브 DB", "제목/본문/발신·수신/일자/첨부", "`[TBD]` 사내 메일 솔루션"],
  ["게시물", "게시판/그룹웨어 DB 직접 · REST API", "제목/본문/작성자/게시판/일자/첨부", "`[TBD]` 그룹웨어 제품"],
  ["결재문서", "전자결재 시스템 API/DB", "문서/기안자/결재선/부서/일자/본문/첨부", "`[TBD]` 전자결재 솔루션"],
], { bodySize: 17 }));
body.push(spacer());
body.push(bullet("**증분 전략**: 변경분만 수집합니다 — 타임스탬프 폴링 / CDC / webhook(시스템이 지원할 때). 마지막 처리 지점을 저장해 재실행 시 이어받습니다."));
body.push(bullet("**권한 메타데이터 동시 수집**: 각 문서의 **열람 허용 주체(사용자/그룹/부서/결재선)**를 함께 가져와 인덱스에 저장합니다 → §9 권한 필터의 근거가 됩니다."));
body.push(h2("7.2 문서 처리"));
body.push(numbered("docproc", "**포맷 파싱**: pdf(`pypdf`/PyMuPDF), docx(`python-docx`), xlsx(`openpyxl`), **hwp/hwpx**(한국 특화 난점, §13 리스크). 이미지/스캔본 → **OCR**(한국어 지원 엔진)."));
body.push(numbered("docproc", "**청킹**: 헤딩/문단 기준 의미 단위 분할 + **parent-child**(작은 청크로 검색 → 부모 섹션을 문맥으로 제공). 메타(작성자·일자·부서·문서종류·권한) 부착."));
body.push(numbered("docproc", "**임베딩**: 다국어 임베딩 모델 → 벡터 DB upsert(문서 단위 ID + 청크 단위 포인트)."));
body.push(numbered("docproc", "**전문검색 색인**: 한국어 형태소(예: nori) BM25 인덱스에 본문/메타 색인."));
body.push(numbered("docproc", "**메타/권한 DB 적재**: 문서·청크·ACL·동기화 상태."));
body.push(callout("각 단계는 **증분·멱등**으로 설계해 중단/재시작에도 안전합니다. 대량 초기 인덱싱은 야간 배치로 진행합니다."));

// ---- 8. 기술 스택 ----
body.push(h1("8. 기술 스택 선택 (Linux · 멀티유저)"));
body.push(callout("원칙: 멀티유저 프로덕션에 적합한, 검증된 오픈소스를 중심으로 선택합니다. 사내 인프라 표준이 있으면 그것을 우선합니다."));
body.push(h2("8.1 레이어별 후보 비교"));
body.push(table([1500, 3300, 4226], ["레이어", "후보", "권장(초안) & 근거"], [
  ["OS", "Ubuntu Server LTS · RHEL/Rocky", "**Ubuntu Server LTS**(드라이버/생태계, 사내 표준 우선) `[TBD]`"],
  ["LLM 서빙", "**vLLM** · TGI · Ollama", "**vLLM** — continuous batching 으로 동시 요청 처리량이 높고 OpenAI 호환 API 제공"],
  ["채팅 LLM", "Qwen2.5-Instruct(7B/14B/32B) · EXAONE · Llama 등", "한국어가 강한 **정식 instruct 모델**, 크기는 GPU 예산에 맞춰 선택 §11"],
  ["임베딩", "bge-m3 등 다국어 모델 + 전용 임베딩 서버(예: TEI)", "**bge-m3**(다국어·한국어 강점) + 고처리량 임베딩 서버"],
  ["리랭커", "bge-reranker-v2-m3 등 cross-encoder", "**추가** — 정확도 향상, RAG 표준 단계"],
  ["벡터 DB", "Qdrant · Milvus · pgvector · OpenSearch kNN", "**Qdrant**(운영 수월·복제·페이로드 필터) 또는 PG 중심이면 **pgvector**"],
  ["전문검색(한국어)", "**OpenSearch(nori)** · PostgreSQL FTS", "**OpenSearch + nori 형태소**(한국어 BM25 품질) 또는 단순화 시 PG FTS"],
  ["메타/권한/감사", "**PostgreSQL**", "**PostgreSQL**(트랜잭션·동시성·ACL·감사)"],
  ["원문/첨부 저장", "사내 NAS · MinIO(S3 호환)", "`[TBD]` 데이터량·기존 스토리지에 맞춰 선택"],
  ["인증/SSO", "Keycloak(OIDC) · 사내 AD/LDAP · SAML", "**사내 AD/LDAP 연동** + 필요 시 Keycloak `[TBD]`"],
  ["API", "Python(async) · 사내 표준 백엔드", "`[TBD]` 사내 표준 우선(async + 다중 워커)"],
  ["Web", "사내 표준 프론트엔드 프레임워크", "`[TBD]` 사내 표준 우선"],
  ["배포", "Docker Compose · **Kubernetes**", "소규모는 Compose, 확장 시 K8s `[TBD]`"],
  ["관측", "Prometheus + Grafana, 로그 수집", "멀티유저 운영에는 모니터링이 필요합니다"],
], { bodySize: 17, firstColBold: true }));
body.push(h2("8.2 \"단순화 옵션\" (소규모/빠른 PoC)"));
body.push(p("운영 부담을 줄이려면 저장소를 **PostgreSQL 단일**로 통합할 수도 있습니다:"));
body.push(bullet("메타/권한/감사 = PostgreSQL, 벡터 = **pgvector**, 전문검색 = PostgreSQL 한국어 FTS."));
body.push(bullet("장점: 운영 컴포넌트가 최소(엔진 1개)입니다. 단점: 초대규모·고난도 한국어 검색 품질은 OpenSearch(nori)·전용 벡터DB 에 비해 다소 아쉬울 수 있습니다."));
body.push(bullet("**제안**: 규모/품질 요구에 따라 [통합형(pgvector)] 과 [전용형(Qdrant+OpenSearch)] 중에서 선택합니다."));

// ---- 9. 멀티유저/권한/보안 ----
body.push(h1("9. 멀티유저 · 권한 · 보안 (가장 중요)"));
body.push(callout("사내 시스템에서는 검색 품질 못지않게 **\"권한이 새지 않는 것\"** 이 중요합니다."));
body.push(h2("9.1 권한 (ACL) 모델"));
body.push(bullet("인덱싱 시 각 문서/청크에 **열람 허용 주체**(사용자ID/그룹/부서/결재선) 메타데이터를 저장합니다."));
body.push(bullet("검색 시 로그인 사용자의 **소속 그룹·부서**를 권한 필터로 변환해 **벡터·키워드 검색 단계에서 pre-filter** 합니다(검색 결과 자체가 권한 내 문서만)."));
body.push(bullet("*post-filter(검색 후 거르기)는 권장하지 않습니다*: top-k 가 권한 문서로 다 채워지지 않거나 누락·누출이 생길 수 있어 **pre-filter 를 원칙**으로 둡니다.", 1));
body.push(bullet("RAG 답변(모드 B)도 **권한을 통과한 문서만** LLM 컨텍스트로 넣습니다(인용도 권한 내 출처만)."));
body.push(bullet("권한 변경 동기화: 원본 시스템에서 권한이 바뀌면 인덱스 ACL 도 함께 갱신합니다(증분 동기화에 포함)."));
body.push(h2("9.2 인증/세션"));
body.push(bullet("SSO: 사내 **AD/LDAP / OIDC / SAML** 연동. 무인증 접근은 허용하지 않습니다."));
body.push(bullet("API 는 stateless(토큰 검증)로 두어 수평 확장이 수월합니다."));
body.push(h2("9.3 보안/컴플라이언스"));
body.push(bullet("**사내망 전용**으로 운영하고 외부 인터넷은 차단합니다."));
body.push(bullet("전송 암호화(TLS), 저장 암호화(디스크/DB), 비밀정보(PII) 검색 로그 마스킹을 검토합니다."));
body.push(bullet("**감사 로그**: 누가·언제·무엇을 검색했고 어떤 문서를 열람했는지 기록합니다(컴플라이언스·오남용 추적)."));
body.push(bullet("**로컬 LLM**: 질의·문서가 외부 API 로 나가지 않습니다."));
body.push(bullet("`[TBD]` 데이터 보존/파기 정책, 로그 보존 기간."));
body.push(h2("9.4 동시성"));
body.push(bullet("API stateless + 다중 워커로 수평 확장하고, LLM 동시성은 vLLM 배치로 처리량을 확보합니다."));
body.push(bullet("임베딩/리랭커 서버 분리, 질의·임베딩 캐싱(권한 고려), rate limiting."));

// ---- 10. 성능/하드웨어 ----
body.push(h1("10. 구성 옵션 — 무GPU(검색형) vs GPU(생성형)"));
body.push(callout("GPU 는 본 시스템에서 비용이 가장 큰 요소입니다. 다행히 RAG 는 부품마다 GPU 필요도가 달라, **GPU 없이도 핵심 가치(통합 검색)를 먼저 제공**하고 이후 GPU 로 생성·멀티모달을 더하는 단계적 도입이 가능합니다."));
body.push(h2("10.1 부품별 GPU 필요도"));
body.push(table([3200, 2000, 3826], ["부품", "GPU 필요도", "비고"], [
  ["벡터 검색(Qdrant/pgvector)", "불필요", "ANN 검색은 CPU 기반"],
  ["키워드 검색(BM25/OpenSearch)", "불필요", "CPU"],
  ["질의 임베딩(검색어 1건)", "CPU로 충분", "단건이라 수십~수백 ms"],
  ["리랭커(cross-encoder)", "CPU 가능(경량 ONNX)", "후보 수십 개 한정, 또는 생략"],
  ["대량 초기 인덱싱 임베딩", "CPU 가능하나 느림", "야간 배치로 흡수"],
  ["답변 생성 LLM(모드 B)", "사실상 GPU 필요", "CPU 는 다중 사용자 실사용 곤란"],
  ["멀티모달 VLM 캡션(§5.2-④)", "GPU 권장", "CPU 는 매우 느림"],
], { bodySize: 17, firstColBold: true }));
body.push(p("즉 **검색해서 출처를 찾아 주는 RAG 의 핵심 절반은 GPU 없이도 동작**합니다. GPU 가 꼭 필요한 부분은 *생성형 답변(모드 B)* 과 *멀티모달·대규모 동시성*입니다."));
body.push(h2("10.2 두 가지 구성"));
body.push(table([2200, 3413, 3413], ["구분", "검색형 (무GPU)", "생성형 (GPU)"], [
  ["제공 기능", "통합 검색 + 출처 카드 + 코드 요약(건수·필터)", "+ 요약 답변(인용) + 멀티모달 캡션"],
  ["대응 모드", "모드 A", "모드 A + 모드 B"],
  ["하드웨어", "기존 CPU 서버(GPU 0)", "GPU 추가 (§11)"],
  ["환각", "없음(생성 안 함)", "인용·근거 부족 시 보류로 관리"],
  ["동시성", "검색은 CPU 로 확장 용이", "LLM 은 vLLM 배치로 확보"],
  ["적합 상황", "빠른 도입·예산 최소·가치 검증", "요약/정리 수요·시각자료 검색"],
], { bodySize: 17, firstColBold: true }));
body.push(h2("10.3 권고 (단계적 도입 · 예산 de-risking)"));
body.push(bullet("**1차는 검색형(무GPU)** 으로 출시해, 흩어진 문서를 한 번에 찾는 핵심 가치를 **GPU 0원**으로 먼저 입증합니다."));
body.push(bullet("효과가 확인되면 **생성형(GPU)** 으로 확장합니다(요약 답변·멀티모달 캡션)."));
body.push(bullet("무GPU 의 유일한 약점인 **초기 대량 인덱싱 속도**는 ① 야간 배치 ② 경량 임베딩 모델 ③ 초기 1회만 GPU 단기 사용 후 증분은 CPU — 의 방법으로 완화합니다."));
body.push(callout("이 구분은 §12 로드맵(P1~P2 검색형 → P3 부터 생성형)과 §11 하드웨어 산정에 그대로 반영됩니다. 다만 **모드 B(생성)는 CPU 로는 다중 사용자 실사용이 어려워 사실상 GPU 가 필요**하다는 점은 분명히 해 둡니다."));

// ---- 11. 성능/하드웨어 ----
body.push(h1("11. 성능 · 하드웨어 스펙 (규모별 시나리오)"));
body.push(callout("정확한 스펙은 **사용자 수 · 데이터량 · 동시성 · 응답 SLA · 모델 크기**에 따라 달라집니다. 아래는 **가정에 기반한 초안**이며, **PoC 로 실측한 뒤 확정**하기를 권장합니다."));
body.push(h2("11.1 성능 목표 (제안 SLA — 결정 필요)"));
body.push(bullet("검색(모드 A) 응답: p95 ≤ `[TBD: 1~2초]`"));
body.push(bullet("RAG 답변(모드 B) 첫 토큰: p95 ≤ `[TBD: 2~4초]`, 스트리밍 완료 ≤ `[TBD: 10초]`"));
body.push(bullet("동시 사용자(피크): `[TBD]` 명"));
body.push(h2("11.2 규모별 하드웨어 (초안 — vLLM + 양자화(AWQ/GPTQ) 가정)"));
body.push(table([1100, 1500, 2900, 2100, 1426],
  ["규모", "사용자 / 피크 동시", "LLM/임베딩 GPU", "API·DB·검색 노드", "스토리지"], [
  ["검색형(무GPU)", "~수백 / 동시 수십", "GPU 불필요 — 질의 임베딩·검색 모두 CPU (§10)", "16~32 vCPU / 64~128GB(검색·DB)", "NVMe 2~4TB"],
  ["PoC/소규모", "~50 / 5~10", "GPU 1× 24GB(RTX 4090 / L4 / A5000), 7~8B Q4 + 임베딩", "16 vCPU / 64GB RAM(단일 서버 동거 가능)", "NVMe 1~2TB"],
  ["중규모", "~500 / 30~50", "GPU 1~2× 40~48GB(A100 40GB / L40S 48GB), 14B + 임베딩/리랭커 분리", "32 vCPU / 128~256GB, 검색·DB 별도 노드", "NVMe 4TB+"],
  ["대규모", "~5,000 / 100+", "GPU 다수(A100/H100), LLM·임베딩 풀 분리 + 오토스케일", "API/검색/DB 분리 + K8s + 복제", "수십 TB + 백업"],
], { bodySize: 15, firstColBold: true }));
body.push(spacer());
body.push(p("**핵심 고려:**"));
body.push(bullet("**GPU VRAM 이 모델 크기와 동시 처리량을 좌우합니다**: 7~8B 모델 + 임베딩이 24GB 급에 안정적으로 들어가는 수준입니다. 더 큰 모델·높은 동시성이 필요하면 40GB 이상을 권장합니다. vLLM 은 VRAM 여유가 클수록 동시 처리량이 늘어납니다."));
body.push(bullet("**임베딩/리랭커는 별 GPU/배치 서버**로 분리하면 LLM 지연과의 간섭을 줄일 수 있습니다."));
body.push(bullet("**벡터 DB 메모리**: 문서·청크 수 × 차원 × 4byte + 인덱스. 데이터량을 추정한 뒤 RAM 을 산정합니다(`[TBD: 총 문서/청크 수]`)."));
body.push(bullet("**CPU/RAM**: 파싱·OCR·동기화 배치는 CPU 부하가 커서 인덱싱 노드를 분리하는 편이 좋습니다."));
body.push(bullet("온프레미스 vs 사내 클라우드(GPU 인스턴스) `[TBD]`."));
body.push(callout("**결정 필요(스펙 산정 입력값)**: ① 총 사용자/피크 동시 ② 총 문서·첨부 수와 증가율 ③ 응답 SLA ④ GPU 예산/조달 가능 모델 ⑤ 기존 인프라(쿠버네티스·NAS·DB 표준)."));

// ---- 11. 로드맵 ----
body.push(h1("12. 단계별 로드맵 (마일스톤 초안)"));
body.push(p("각 단계는 *산출물 + 수락 기준*으로 둡니다."));
body.push(table([1300, 4600, 3126], ["단계", "내용", "수락 기준(예)"], [
  ["P0 환경", "Linux 서버, (검색형은 CPU만) LLM·임베딩·벡터DB·DB 기동, SSO 연동 PoC", "한국어 검색 1건 end-to-end (모드 A)"],
  ["P1 단일 소스 MVP", "가장 쉬운 소스 1종(예: 게시물) 커넥터 + 인덱싱 + 하이브리드 검색 + 권한 pre-filter — **검색형(무GPU)**", "권한 지킨 검색, 정답률·지연 기준 통과"],
  ["P2 멀티소스", "메일 + 결재문서 커넥터, 첨부 파싱/OCR(hwp 포함), 증분 동기화 — 여전히 **무GPU 가능**", "3종 통합 검색, 증분 동기 안정"],
  ["P3 RAG 답변", "리랭커 + 모드 B(요약+인용), 환각/권한 누출 가드 — **GPU 도입 지점**", "인용 정확, 권한 누출 0"],
  ["P4 멀티유저/운영", "동시성·부하 테스트, 모니터링, 감사 로그, 백업/복구", "SLA 충족, 부하 테스트 통과"],
  ["P5 확장(선택)", "**브라우저 사이드패널 확장(§5.2-⑧) + 비동기 OS 알림(§5.2-⑨)**, 멀티모달 캡션, 추가 소스, K8s 오토스케일", "사이드패널 맥락 검색 + 비활성 시 알림 동작"],
], { bodySize: 17, firstColBold: true }));
body.push(spacer());
body.push(callout("**GPU 관점**: P1~P2 검색형은 **무GPU**(기존 CPU 서버)로 진행할 수 있고, GPU 는 **P3 생성형부터** 필요합니다(§10). 접근 채널도 **P1 웹 앱(단독 접속)** 으로 시작해, 검색이 안정된 뒤 **P5 에서 사이드패널**로 확장합니다 — 사이드패널은 별도 백엔드 없이 동일 API 를 호출하는 가벼운 확장입니다."));

// ---- 12. 리스크 ----
body.push(h1("13. 리스크 & 대응"));
body.push(table([2000, 1900, 5126], ["리스크", "영향", "대응"], [
  ["**권한 누출** (가장 주의)", "보안 사고", "pre-filter 원칙, ACL 증분 동기화, 누출 테스트 케이스 상시"],
  ["**HWP/한글 문서 파싱**", "결재문서 추출 실패", "hwp5/pyhwp + LibreOffice headless 변환 폴백, 실패분 큐·OCR"],
  ["한국어 검색 품질", "recall↓", "nori 형태소 + 다국어 임베딩 하이브리드 + 리랭커, 평가셋으로 튜닝"],
  ["전자결재/그룹웨어 연동 난이도", "일정 지연", "표준 API 없으면 DB 직접/배치, 소스별 PoC 선행"],
  ["RAG 환각", "잘못된 답변", "모드 A 우선, 모드 B 는 인용 강제·근거 약하면 \"검색 결과만 제시\""],
  ["GPU 비용/조달", "예산·일정", "양자화·모델 크기 조절, PoC 로 처리량 실측 후 증설"],
  ["동시성 병목", "지연↑", "vLLM 배치, 임베딩 서버 분리, 캐싱, 수평 확장"],
  ["데이터량 증가", "스토리지·인덱스 비용", "보존 정책, 청크 중복 제거, 콜드 데이터 분리"],
], { bodySize: 17 }));

// ---- 13. 결정 필요 ----
body.push(h1("14. 결정 필요 사항 (검토 회의 입력)"));
body.push(callout("보강 단계에서 아래 값들을 채우면 스펙·일정·비용이 구체화됩니다."));
body.push(numbered("decisions", "**규모**: 총 사용자 수 / 피크 동시 접속 / 총 문서·첨부 수 및 증가율."));
body.push(numbered("decisions", "**데이터 소스 제품**: 메일 솔루션, 그룹웨어/게시판 제품, 전자결재 솔루션(자체개발 여부, API 제공 여부)."));
body.push(numbered("decisions", "**권한 체계**: AD/LDAP 사용 여부, 부서/결재선 구조, 문서별 ACL 추출 가능 여부."));
body.push(numbered("decisions", "**검색 모드**: 모드 A 만 / A→B 단계 / 처음부터 B 포함."));
body.push(numbered("decisions", "**인프라 표준**: 온프레미스 vs 사내 클라우드, Kubernetes 사용 여부, 표준 DB·스토리지·모니터링·백엔드/프론트 프레임워크."));
body.push(numbered("decisions", "**GPU 예산/조달**: 가능한 GPU 등급 → 채택 가능 모델 크기 결정."));
body.push(numbered("decisions", "**SLA**: 검색/RAG 응답 목표, 가용성(이중화) 요구."));
body.push(numbered("decisions", "**보안/컴플라이언스**: PII 처리, 로그·데이터 보존 기간, 감사 요건."));
body.push(numbered("decisions", "**저장소 형태**: 통합형(PostgreSQL+pgvector) vs 전용형(Qdrant + OpenSearch)."));
body.push(numbered("decisions", "**접근 채널**: 사내 표준 브라우저(크롬/엣지 Side Panel API 지원 여부·버전), 확장 일괄 배포 정책(MDM/그룹정책), 웹 앱 단독 제공 범위."));

// =================================================================
// 조립
// =================================================================
const decimalCfg = (ref) => ({
  reference: ref,
  levels: [{ level: 0, format: LevelFormat.DECIMAL, text: "%1.", alignment: AlignmentType.LEFT,
    style: { paragraph: { indent: { left: 460, hanging: 280 } } } }],
});

const doc = new Document({
  creator: "핸디소프트 서비스개발팀 남종관",
  title: "사내 업무 통합 검색 시스템 (RAG) 개발 기획서",
  description: "사내 해커톤(바이브코딩) 1차 기획안 공모 제출",
  styles: {
    default: { document: { run: { font: BODY, size: 20 } } },
    paragraphStyles: [
      { id: "Heading1", name: "Heading 1", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { size: 30, bold: true, font: BODY, color: ACCENT },
        paragraph: { spacing: { before: 320, after: 160 }, outlineLevel: 0,
          border: { bottom: { style: BorderStyle.SINGLE, size: 8, color: ACCENT, space: 4 } } } },
      { id: "Heading2", name: "Heading 2", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { size: 24, bold: true, font: BODY, color: "2E5A88" },
        paragraph: { spacing: { before: 220, after: 100 }, outlineLevel: 1 } },
    ],
  },
  numbering: {
    config: [
      { reference: "b", levels: [
        { level: 0, format: LevelFormat.BULLET, text: "•", alignment: AlignmentType.LEFT,
          style: { paragraph: { indent: { left: 460, hanging: 260 } } } },
        { level: 1, format: LevelFormat.BULLET, text: "–", alignment: AlignmentType.LEFT,
          style: { paragraph: { indent: { left: 920, hanging: 260 } } } },
      ] },
      decimalCfg("goals"), decimalCfg("docproc"), decimalCfg("decisions"),
    ],
  },
  sections: [{
    properties: {
      titlePage: true,
      page: { size: { width: 11906, height: 16838 }, margin: { top: 1440, right: 1440, bottom: 1440, left: 1440 } },
    },
    headers: {
      default: new Header({ children: [new Paragraph({
        tabStops: [{ type: TabStopType.RIGHT, position: CW }],
        spacing: { after: 0 },
        border: { bottom: { style: BorderStyle.SINGLE, size: 4, color: "D8DDE6", space: 6 } },
        children: [
          new TextRun({ text: "사내 업무 통합 검색(RAG) 개발 기획서 · 서비스개발팀", size: 16, color: GREY }),
          new TextRun({ text: "\t" }),
          new ImageRun({ type: "png", data: fs.readFileSync(LOGO), transformation: { width: 92, height: 21 },
            altText: { title: "HANDYSOFT", description: "핸디소프트 로고", name: "headerLogo" } }),
        ],
      })] }),
      first: new Header({ children: [new Paragraph({ children: [new TextRun("")] })] }),
    },
    footers: {
      default: new Footer({ children: [new Paragraph({
        tabStops: [{ type: TabStopType.RIGHT, position: CW }],
        children: [
          new TextRun({ text: "사내 한정 (Confidential) · 사내 해커톤 1차 기획안 공모 제출", size: 16, color: GREY }),
          new TextRun({ text: "\t", size: 16 }),
          new TextRun({ children: [PageNumber.CURRENT], size: 16, color: GREY }),
          new TextRun({ text: " / ", size: 16, color: GREY }),
          new TextRun({ children: [PageNumber.TOTAL_PAGES], size: 16, color: GREY }),
        ],
      })] }),
      first: new Footer({ children: [new Paragraph({ children: [new TextRun("")] })] }),
    },
    children: body,
  }],
});

Packer.toBuffer(doc).then((buf) => {
  fs.writeFileSync(ROOT + "/docs/enterprise-rag-plan.docx", buf);
  console.log("WROTE docs/enterprise-rag-plan.docx", buf.length, "bytes");
});
