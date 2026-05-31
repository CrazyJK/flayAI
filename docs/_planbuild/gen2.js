const fs = require("fs");
const {
  Document, Packer, Paragraph, TextRun, Table, TableRow, TableCell, ImageRun,
  AlignmentType, LevelFormat, TabStopType,
  HeadingLevel, BorderStyle, WidthType, ShadingType,
  VerticalAlign, PageNumber, PageBreak, Header, Footer,
} = require("docx");

const ROOT = "C:/Handyground/Workspace/git/flayAI";
const IMG = ROOT + "/docs/_planbuild/sidepanel-mockup-v2.png";
const LOGO = ROOT + "/docs/_planbuild/logo.png";

const CW = 9026, ACCENT = "1F4E79", HEADER_FILL = "1F4E79", ZEBRA = "F4F8FC",
  LIGHT = "EAF1F8", BORDER = "BFBFBF", GREY = "808080", BODY = "맑은 고딕", CODE_FONT = "Consolas";

function inline(text, base = {}) {
  const out = []; const re = /(\*\*([^*]+)\*\*|`([^`]+)`|\*([^*]+)\*)/g; let last = 0, m;
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
function p(text) { return new Paragraph({ spacing: { after: 120, line: 276 }, children: inline(text) }); }
function h1(t) { return new Paragraph({ heading: HeadingLevel.HEADING_1, children: [new TextRun(t)] }); }
function h2(t) { return new Paragraph({ heading: HeadingLevel.HEADING_2, children: [new TextRun(t)] }); }
function bullet(text, level = 0) { return new Paragraph({ numbering: { reference: "b", level }, spacing: { after: 60, line: 270 }, children: inline(text) }); }
function numbered(ref, text) { return new Paragraph({ numbering: { reference: ref, level: 0 }, spacing: { after: 60, line: 270 }, children: inline(text) }); }
function callout(text) {
  return new Paragraph({ spacing: { before: 80, after: 160, line: 276 },
    shading: { type: ShadingType.CLEAR, fill: LIGHT },
    border: { left: { style: BorderStyle.SINGLE, size: 18, color: ACCENT, space: 8 } },
    indent: { left: 200, right: 140 }, children: inline(text) });
}
function diffItem(title, bodyTxt, notes) {
  const arr = [new Paragraph({ spacing: { before: 180, after: 40 }, children: inline(title, { bold: true, color: ACCENT, size: 22 }) }), p(bodyTxt)];
  (notes || []).forEach((n) => arr.push(new Paragraph({ indent: { left: 360 }, spacing: { after: 40, line: 270 }, children: inline("↳ " + n) })));
  return arr;
}
function caption(text) { return new Paragraph({ alignment: AlignmentType.CENTER, spacing: { before: 40, after: 160 }, children: inline(text, { italics: true, color: GREY, size: 16 }) }); }
const Bd = { style: BorderStyle.SINGLE, size: 4, color: BORDER };
const cellBorders = { top: Bd, bottom: Bd, left: Bd, right: Bd };
function cell(text, { width, fill, bold = false, white = false, align, size } = {}) {
  return new TableCell({ width: { size: width, type: WidthType.DXA }, borders: cellBorders,
    shading: fill ? { type: ShadingType.CLEAR, fill } : undefined,
    margins: { top: 60, bottom: 60, left: 100, right: 100 }, verticalAlign: VerticalAlign.CENTER,
    children: [new Paragraph({ alignment: align, spacing: { after: 0, line: 252 }, children: inline(String(text), { bold, color: white ? "FFFFFF" : undefined, size }) })] });
}
function table(colWidths, header, rows, { bodySize, firstColBold = false } = {}) {
  const trs = [new TableRow({ tableHeader: true, children: header.map((t, i) => cell(t, { width: colWidths[i], fill: HEADER_FILL, bold: true, white: true, align: AlignmentType.CENTER })) })];
  rows.forEach((r, ri) => { const fill = ri % 2 === 1 ? ZEBRA : undefined; trs.push(new TableRow({ children: r.map((t, i) => cell(t, { width: colWidths[i], fill, size: bodySize, bold: firstColBold && i === 0 })) })); });
  return new Table({ width: { size: colWidths.reduce((a, b) => a + b, 0), type: WidthType.DXA }, columnWidths: colWidths, rows: trs });
}
function spacer() { return new Paragraph({ spacing: { after: 80 }, children: [new TextRun("")] }); }
function ctr(text, size, opts = {}) { return new Paragraph({ alignment: AlignmentType.CENTER, spacing: opts.spacing || { after: 0 }, children: [new TextRun({ text, size, ...opts })] }); }

const body = [];

// ===== 표지 =====
body.push(ctr("핸디소프트 (HANDYSOFT)", 26, { bold: true, color: ACCENT, spacing: { before: 1100, after: 0 } }));
body.push(ctr("서비스개발팀", 18, { color: "595959", spacing: { before: 40, after: 0 } }));
body.push(ctr("그룹웨어 통합 검색 (RAG)", 46, { bold: true, color: ACCENT, spacing: { before: 720, after: 0 } }));
body.push(ctr("메일 · 게시판 · 결재를 자연어로 — 사내 활용 + 온프레미스 제품 강화", 23, { color: "404040", spacing: { before: 150, after: 0 } }));
body.push(ctr("개발 기획서 (v2)", 24, { bold: true, spacing: { before: 80, after: 0 } }));
body.push(new Paragraph({ alignment: AlignmentType.CENTER, spacing: { before: 560, after: 0 },
  shading: { type: ShadingType.CLEAR, fill: LIGHT },
  border: { top: { style: BorderStyle.SINGLE, size: 6, color: ACCENT, space: 6 }, bottom: { style: BorderStyle.SINGLE, size: 6, color: ACCENT, space: 6 } },
  children: [new TextRun({ text: "사내 해커톤 (바이브코딩) — 1차 기획안 공모 제출", size: 22, bold: true, color: ACCENT })] }));
body.push(ctr("작성자  남종관 (서비스개발팀 · 팀장/연구위원)", 20, { spacing: { before: 520, after: 0 } }));
body.push(ctr("버전 v2.0 · 작성일 2026-05-31", 20, { color: "595959", spacing: { before: 60, after: 0 } }));
body.push(ctr("분류: 사내 한정 (Confidential) · 온프레미스 전용", 20, { color: "C00000", spacing: { before: 40, after: 0 } }));
body.push(new Paragraph({ children: [new PageBreak()] }));

// ===== 목차(정적) =====
body.push(h1("목차"));
[
  "요약", "1. 배경 & 문제", "2. 사업성 — 그룹웨어 제품 강화 & 온프레미스",
  "3. 목표 & 범위 (1차: 사내 게시판)", "4. 사용자 시나리오 (예시)", "5. 핵심 설계 원칙",
  "6. 차별화 4선", "7. 아키텍처 (그룹웨어 내 통합 검색)", "8. 데이터 파이프라인 (게시판부터)",
  "9. 권한 · 보안", "10. 구성 옵션 — 무GPU(검색형) vs GPU(생성형)", "11. 성능 · 하드웨어 (100명 규모)",
  "12. 단계별 로드맵", "13. 리스크 & 대응", "14. 결정 필요 사항",
].forEach((t) => body.push(new Paragraph({ spacing: { after: 70, line: 276 }, indent: { left: 220 }, children: [new TextRun({ text: t, size: 22 })] })));
body.push(new Paragraph({ children: [new PageBreak()] }));

// ===== 요약 =====
body.push(h1("요약"));
body.push(callout("우리 그룹웨어(메일 · 게시판 · 결재 등 하부 컴포넌트)에 **자연어 통합 검색(RAG)** 을 더하는 기능입니다. 사내 업무 효율을 높이는 동시에, **온프레미스로 판매 중인 그룹웨어 제품의 경쟁력**을 강화합니다. **1차는 열람 제한이 없는 사내 게시판**부터 시작하고, 검증 후 메일 · 결재로 확장합니다."));
body.push(h2("용어 빠른 정의 (AI/ML 입문자용)"));
body.push(bullet("**RAG (Retrieval-Augmented Generation)**: \"먼저 검색해서 찾은 문서를 LLM 에게 보여주고 답하게 한다\"는 방식. LLM 단독이 아니라 *검색 + LLM 종합*."));
body.push(bullet("**임베딩(embedding)**: 문장을 의미를 담은 숫자 벡터로 바꾼 것. 의미가 비슷하면 벡터도 가까워, 키워드가 안 겹쳐도 연결됩니다."));
body.push(bullet("**하이브리드 검색**: 키워드 검색(BM25)과 의미 검색(벡터)을 함께 돌려 합치는 방식. 정확한 이름은 키워드가, 자연어 의도는 벡터가 보완합니다."));
body.push(bullet("**리랭커(reranker)**: 넓게 찾은 후보를 질의와 함께 정밀 비교해 다시 순위 매기는 모델. 검색 정확도를 끌어올리는 RAG 표준 단계."));

// ===== 1. 배경 =====
body.push(h1("1. 배경 & 문제"));
body.push(bullet("그룹웨어 안에 메일 · 게시판 · 결재가 함께 있지만 **각각 따로 검색**해야 하고, 정확한 제목 · 작성자 · 기간을 기억해야 찾을 수 있습니다."));
body.push(bullet("\"재택근무 정책 최신 공지\" 같은 **자연어 의도로는 찾기 어렵습니다.** 키워드 검색의 한계입니다."));
body.push(bullet("그러다 보니 이미 사내에 있는 정보를 다시 묻거나, 못 찾아 중복 작업 · 지식 사일로가 생깁니다."));
body.push(bullet("사내 데이터는 보안상 외부 SaaS LLM 에 올리기 어렵습니다 → **온프레미스 로컬 LLM** 이 필요합니다. (이 점은 우리 그룹웨어 고객사도 동일합니다.)"));

// ===== 2. 사업성 =====
body.push(h1("2. 사업성 — 그룹웨어 제품 강화 & 온프레미스 사업화"));
body.push(callout("메일 · 게시판 · 결재는 **우리 회사 그룹웨어의 하부 컴포넌트**입니다. 그룹웨어는 사내에서 실제로 쓰이는 동시에, **온프레미스로 판매하는 제품**이기도 합니다. 따라서 이 통합 검색은 *사내 도구*에 그치지 않고 **제품 경쟁력 강화 → 신규 매출 기회**로 이어집니다."));
body.push(h2("2.1 두 가지 가치"));
body.push(bullet("**사내(내부)**: 흩어진 그룹웨어 정보를 자연어로 한 번에 찾아 업무 효율을 높입니다."));
body.push(bullet("**제품(외부)**: 그룹웨어에 통합 검색을 기능으로 탑재해 **제품 차별화 · 신규 매출 기회**를 만듭니다."));
body.push(h2("2.2 우리가 유리한 이유"));
body.push(bullet("**자사 제품이 곧 데이터 소스**: 게시판 · 메일 · 결재의 스키마 · API · 권한 모델을 우리가 가장 잘 압니다 → 외부 솔루션보다 연동 · 이식이 쉽습니다."));
body.push(bullet("**Dogfooding**: 사내에서 먼저 검증하고 안정화한 뒤 제품에 탑재 → 고객에게 검증된 기능으로 제공합니다."));
body.push(bullet("**온프레미스 정합**: 고객도 데이터 외부 반출을 꺼립니다. 로컬 RAG 는 우리 제품 포지션과 정확히 일치하고, **무GPU 검색형**(§10)이면 고객 도입 부담도 낮습니다."));
body.push(h2("2.3 기대 효과 (추정)"));
body.push(bullet("사내 **약 100명 · 1인 일 5회** → 약 **500건/일**(영업일 20일 기준 ≈ 1만 건/월, 약 12만 건/년)."));
body.push(bullet("검색 1건당 평균 **2분 절감** 가정 시 일 ≈ 1,000분(약 16.7시간), 월 ≈ 330시간 절감. *가정치이며 PoC 로 실측 권장.*"));
body.push(bullet("정성 효과: 재질문 · 중복 작업 감소, 신규 입사자 온보딩 가속, 지식 사일로 완화."));
body.push(bullet("이 규모(100명 · 일 500건)는 **무GPU 검색형으로 충분**해 도입 비용이 최소입니다(§11)."));
body.push(bullet("제품 매출 기여는 영업 추정이 필요합니다(§14)."));

// ===== 3. 목표 & 범위 =====
body.push(h1("3. 목표 & 범위 (1차: 사내 게시판)"));
body.push(h2("3.1 목표"));
body.push(numbered("goals", "그룹웨어 정보를 **한 검색창**에서 자연어로 검색합니다."));
body.push(numbered("goals", "결과에 **출처(원문 링크 · 작성자 · 일자 · 게시판)**를 함께 보여 줍니다."));
body.push(numbered("goals", "**권한을 지킵니다** — 접근 권한이 없는 문서는 노출하지 않습니다(1차는 공개 게시물만)."));
body.push(numbered("goals", "쾌적한 응답 속도를 목표로 합니다(목표 SLA 는 §11)."));
body.push(numbered("goals", "사내망 전용으로 운영하고 외부 인터넷에 노출하지 않습니다."));
body.push(h2("3.2 1차 범위 (In Scope)"));
body.push(bullet("**사내 게시판 — 열람 제한이 없는 공개 게시물만** 대상으로 합니다."));
body.push(bullet("**열람 제한이 있는 게시물은 인덱싱 대상에서 아예 제외**합니다(권한을 단순하게, 누출 위험을 원천 차단)."));
body.push(bullet("게시물 본문 + 첨부 텍스트 추출, 하이브리드 검색(모드 A, 무GPU), **사이드패널** 제공."));
body.push(h2("3.3 확장 (향후)"));
body.push(bullet("메일 · 결재로 소스 확장 — 이때 **권한 정합**(§9)이 본격 적용됩니다."));
body.push(bullet("생성형 요약 답변(모드 B, GPU), 멀티모달 첨부 이해 등."));
body.push(h2("3.4 비범위 (Out of Scope)"));
body.push(bullet("문서 작성 · 결재 기능(본 기능은 검색에 집중), 외부 인터넷 검색."));
body.push(bullet("열람 제한 · 기밀 게시물(1차 제외)."));

// ===== 4. 시나리오 =====
body.push(h1("4. 사용자 시나리오 (예시 — 1차 게시판)"));
body.push(table([3300, 5726], ["질의 예", "기대 동작"], [
  ["\"재택근무 정책 최신 공지 찾아줘\"", "게시물 의미검색 + 최신순 → 카드"],
  ["\"작년 보안 점검 관련 공지\"", "기간 필터 + 주제 의미검색"],
  ["\"해커톤 공모 안내 어디 있더라\"", "게시물 검색 → 출처 카드"],
  ["\"복지 포인트 사용법 정리된 글\"", "자연어 의미검색"],
]));
body.push(spacer());
body.push(callout("1차에서는 위 질의가 모두 *공개 게시물 범위 안에서* 동작합니다. 메일 · 결재 확장 시에는 *질의한 사용자가 볼 수 있는 문서* 로 권한이 확장됩니다(§9)."));

// ===== 5. 핵심 설계 원칙 =====
body.push(h1("5. 핵심 설계 원칙"));
body.push(h2("5.1 검색 코어"));
body.push(bullet("**하이브리드 검색**: 의미 검색(벡터)과 키워드 검색(BM25, 한국어 형태소)을 함께 수행하고 **RRF** 로 결합합니다."));
body.push(bullet("**리랭커**: 상위 후보를 cross-encoder 로 다시 정렬해 정확도를 높입니다."));
body.push(bullet("**권한 우선**: 검색의 모든 단계에서 사용자가 볼 수 있는 문서만 후보로 둡니다(§9)."));
body.push(bullet("**증분 · 멱등 인덱싱**: 변경분만 반영하고 재실행이 안전하도록 설계합니다."));
body.push(bullet("**로컬 LLM**: 질의 · 문서가 외부로 나가지 않도록 온프레미스에서 처리합니다."));
body.push(h2("5.2 검색 모드 (단계 도입)"));
body.push(bullet("**모드 A: 검색(무GPU)** — 출처 카드 + 스니펫. 빠르고 환각이 없습니다. **1차는 모드 A.**"));
body.push(bullet("**모드 B: RAG 답변(GPU, 향후)** — 요약 + 인용. 근거가 약하면 **\"근거 부족\"으로 보류(abstain)** 해 지어내지 않습니다."));

// ===== 6. 차별화 =====
body.push(h1("6. 차별화 4선"));
body.push(callout("하이브리드 검색 · 리랭킹 · 권한 인식은 이미 업계의 *기본기*입니다. 본 기획의 차별성은 아래 네 가지에 있습니다 — 특히 **그룹웨어 제품의 일부**라는 점이 토대입니다."));
diffItem("① 온프레미스 · 데이터 주권 + 자사 그룹웨어 내장",
  "로컬 LLM 으로 질의 · 문서가 외부로 나가지 않습니다. 한국어 · HWP 등 한국 업무 환경에 맞추고, 무엇보다 **데이터 소스가 자사 그룹웨어 컴포넌트**라 연동과 제품 이식이 자연스럽습니다.",
  ["*왜 다른가요?* 외부 SaaS 는 데이터 반출 · 한국어/HWP · 결재선 구조에 약합니다. 우리는 제품을 직접 만드는 입장이라 연동 · 이식 · 온프레미스 배포가 유리합니다."]).forEach((x) => body.push(x));
diffItem("② 권한 정합 (permission parity)",
  "검색의 모든 단계에서 사용자가 볼 수 있는 문서만 후보로 둡니다(pre-filter). **1차는 열람 제한이 없는 공개 게시물만** 대상이라 권한이 단순하고 누출 위험이 낮습니다. 메일 · 결재로 확장할 때 권한 정합이 진짜 차별점이 됩니다.",
  ["*왜 다른가요?* 사내 검색이 권한을 느슨하게 다루면 보안 사고로 이어집니다. 처음부터 pre-filter 원칙 + 제한 게시물 제외로 안전하게 시작합니다."]).forEach((x) => body.push(x));
diffItem("③ 무GPU(검색형) → GPU(생성형) 단계 도입",
  "검색(모드 A)은 GPU 없이 동작합니다. **GPU 0원**으로 핵심 가치를 먼저 입증하고, 이후 생성형(모드 B)에만 GPU 를 더합니다. 비용이라는 최대 걸림돌을 단계로 분리합니다.",
  ["*왜 다른가요?* GPU 는 도입 최대 장벽입니다. 무GPU 로 시작하면 사내는 물론 **온프레미스 고객의 도입 부담**도 낮아집니다(§10)."]).forEach((x) => body.push(x));
diffItem("④ 사이드패널 상주(in-context) 검색",
  "그룹웨어 화면을 그대로 둔 채 브라우저 우측 패널(Side Panel API)에서 검색 · 참조합니다. 탭 전환 없이 \"지금 보고 있는 화면\" 맥락으로 이어 검색할 수 있고, **제품에 그대로 탑재할 수 있는 UX** 입니다.",
  ["*왜 다른가요?* 별도 검색 포털은 업무 흐름이 끊깁니다. 그룹웨어에 바로 붙는 상주 검색은 실사용 경험이 다릅니다.",
   "*참고*: 크로뮴 계열(Chrome 114+ · Edge) Side Panel API 의존 → 확장 배포 정책 확인이 필요합니다(§14). 비지원 환경은 웹 화면으로 대체합니다."]).forEach((x) => body.push(x));
body.push(new Paragraph({ alignment: AlignmentType.CENTER, spacing: { before: 120, after: 40 },
  children: [new ImageRun({ type: "png", data: fs.readFileSync(IMG), transformation: { width: 624, height: 339 },
    altText: { title: "그룹웨어 + 통합 검색 사이드패널", description: "실제 포털 화면 우측 보조 패널을 통합 검색으로 대체한 합성", name: "v2mock" } })] }));
body.push(caption("[그림] 실제 그룹웨어 포털 화면 그대로에, 우측 보조 패널을 통합 검색 패널로 대체한 합성 예상 화면(1차 게시판 기준). 현재 화면 맥락 칩 · 공개 게시물 결과 카드 · 출처 강조를 나타낸 개념 시안이며, 실제 UI 와 다를 수 있습니다."));
body.push(callout("위 네 가지는 §7 이후의 아키텍처 · 파이프라인 · 권한 설계로 구체화됩니다. ②는 §9 권한 · 보안, ③은 §10 구성 옵션 · §11 하드웨어, ④는 §12 로드맵과 이어집니다."));

// ===== 7. 아키텍처 =====
body.push(h1("7. 아키텍처 (그룹웨어 내 통합 검색)"));
body.push(p("그룹웨어의 일부로 동작합니다. **질의는 위→아래**, **인덱싱은 아래→위**로 흐르며, 그룹웨어의 기존 인증 · 조직정보를 재사용해 별도 구축 부담을 줄입니다."));
body.push(table([2400, 6626], ["계층", "구성 / 역할"], [
  ["사용자 채널", "그룹웨어 화면 + 브라우저 사이드패널(Side Panel API). 동일 검색 API 호출 (§6-④)."],
  ["인증 · 게이트웨이", "**그룹웨어 SSO/세션 재사용** + 사용자 권한(부서/그룹) 확보, 질의 라우팅, 권한 필터 주입, 감사 로그."],
  ["검색 레이어", "① 하이브리드 검색(벡터 + 키워드) → ② RRF 결합 → ③ 리랭커 → ④ 권한 필터(1차: 공개 게시물)."],
  ["LLM 서빙 (향후)", "생성형 답변(모드 B) 단계에서 추가 — vLLM 등."],
  ["임베딩 서버", "임베딩 · 리랭커 모델 서빙(질의/인덱싱). 검색형은 CPU 로 충분(§10)."],
  ["데이터 저장소", "벡터 DB(의미검색) · 전문검색(BM25, 한국어 형태소) · 메타/감사 DB."],
  ["인덱싱 · 커넥터", "증분 · 멱등 인덱싱 ← **1차: 사내 게시판(공개)** / 향후: 메일 · 결재."],
]));

// ===== 8. 파이프라인 =====
body.push(h1("8. 데이터 파이프라인 (게시판부터)"));
body.push(h2("8.1 소스 커넥터 (1차: 게시판)"));
body.push(bullet("**게시판 연동**: 그룹웨어 DB/REST 에 직접 접근(자사 제품이라 유리). **공개 게시물만** 수집하고 제한 게시물은 가져오지 않습니다."));
body.push(bullet("**증분 동기화**: 변경분만 수집(타임스탬프/변경 로그), 마지막 처리 지점 저장. **삭제 전파**(원본에서 지워지면 인덱스에서도 제거)."));
body.push(bullet("향후 메일 · 결재 커넥터를 같은 방식으로 추가합니다(권한 메타 동시 수집 — §9)."));
body.push(h2("8.2 문서 처리"));
body.push(numbered("docproc", "**파싱**: 게시글 본문(HTML) + 첨부(pdf · docx · xlsx · **hwp/hwpx** — §13 리스크). 이미지/스캔본은 OCR."));
body.push(numbered("docproc", "**청킹**: 문단/섹션 단위 분할 + 메타(작성자 · 일자 · 게시판) 부착."));
body.push(numbered("docproc", "**임베딩**: 다국어 임베딩 모델 → 벡터 DB upsert."));
body.push(numbered("docproc", "**전문검색 색인**: 한국어 형태소(예: nori) BM25 인덱스."));
body.push(numbered("docproc", "**메타 적재**: 문서 · 청크 · 동기화 상태(공개 게시물만)."));
body.push(callout("각 단계는 **증분 · 멱등**으로 설계해 중단/재시작에도 안전합니다. 대량 초기 인덱싱은 야간 배치로 진행합니다."));

// ===== 9. 권한 · 보안 =====
body.push(h1("9. 권한 · 보안"));
body.push(callout("사내 시스템에서는 검색 품질 못지않게 **\"권한이 새지 않는 것\"** 이 중요합니다. 1차는 **공개 게시물만** 다뤄 위험을 원천적으로 낮춥니다."));
body.push(h2("9.1 1차 — 공개 게시물 한정"));
body.push(bullet("열람 제한이 없는 공개 게시물만 인덱싱합니다. **제한 게시물은 인덱싱 자체에서 제외** → 검색 결과에 나타날 수 없습니다."));
body.push(bullet("그래도 검색 단계에서 사용자 권한 필터를 적용하는 구조는 처음부터 둡니다(확장 대비)."));
body.push(h2("9.2 확장 시 — 권한 정합"));
body.push(bullet("메일 · 결재로 확장하면 그룹웨어 권한(게시판 공개범위 · 부서 · 결재선)을 **pre-filter** 로 정합합니다(검색 결과 자체가 권한 내 문서만)."));
body.push(bullet("권한 변경 · 회수도 증분 동기화에 포함해 인덱스와 원본을 일치시킵니다."));
body.push(h2("9.3 공통 보안"));
body.push(bullet("사내망 전용, 전송 암호화(TLS), 감사 로그(질의 · 열람 기록), 로컬 LLM(외부 반출 없음)."));
body.push(bullet("프라이버시: 1차는 공개 게시물이라 민감도가 낮습니다. 메일 확장 시 사내 동의 · 정책 검토가 필요합니다(§14)."));

// ===== 10. 구성 옵션 =====
body.push(h1("10. 구성 옵션 — 무GPU(검색형) vs GPU(생성형)"));
body.push(callout("GPU 는 비용이 가장 큰 요소입니다. RAG 는 부품마다 GPU 필요도가 달라 **GPU 없이도 핵심 가치(검색)를 제공**하고, 이후 GPU 로 생성을 더할 수 있습니다. (이 단계론은 온프레미스 고객 도입 부담도 낮춥니다.)"));
body.push(h2("10.1 부품별 GPU 필요도"));
body.push(table([3200, 2000, 3826], ["부품", "GPU 필요도", "비고"], [
  ["벡터 검색 / 키워드 검색", "불필요", "CPU 기반"],
  ["질의 임베딩(검색어 1건)", "CPU로 충분", "단건이라 빠름"],
  ["리랭커(cross-encoder)", "CPU 가능(경량)", "후보 수십 개 한정, 또는 생략"],
  ["대량 초기 인덱싱 임베딩", "CPU 가능하나 느림", "야간 배치로 흡수"],
  ["답변 생성 LLM(모드 B)", "사실상 GPU 필요", "CPU 는 다중 사용자 곤란"],
], { bodySize: 17, firstColBold: true }));
body.push(h2("10.2 두 가지 구성"));
body.push(table([2200, 3413, 3413], ["구분", "검색형 (무GPU) — 1차", "생성형 (GPU) — 향후"], [
  ["제공 기능", "통합 검색 + 출처 카드", "+ 요약 답변(인용)"],
  ["대응 모드", "모드 A", "모드 A + 모드 B"],
  ["하드웨어", "기존 CPU 서버(GPU 0)", "GPU 추가 (§11)"],
  ["환각", "없음(생성 안 함)", "인용 · 근거 부족 시 보류"],
  ["적합", "빠른 도입 · 가치 검증 · 고객 부담↓", "요약/정리 수요"],
], { bodySize: 17, firstColBold: true }));

// ===== 11. 성능 · 하드웨어 =====
body.push(h1("11. 성능 · 하드웨어 (100명 규모)"));
body.push(h2("11.1 성능 목표 (제안 SLA)"));
body.push(bullet("검색(모드 A) 응답: p95 ≤ `[TBD: 1~2초]`"));
body.push(bullet("동시 사용자(피크): 수~수십 명 수준(전체 ~100명 · 일 ~500건 기준)."));
body.push(h2("11.2 규모별 하드웨어 (초안)"));
body.push(table([1600, 2200, 3300, 1926], ["구분", "전제", "컴퓨팅", "비고"], [
  ["**1차 — 검색형(무GPU)**", "100명 · 일 ~500건", "1대 · 16~32 vCPU / 64~128GB / GPU 0", "벡터+전문검색+API 동거 가능"],
  ["확장 — 생성형(GPU)", "요약 답변 도입 시", "GPU 1× 24GB(7~8B) 추가", "vLLM, 검색/인덱싱과 분리"],
], { bodySize: 17 }));
body.push(spacer());
body.push(bullet("**100명 · 일 500건 규모는 무GPU 검색형 1대로 충분**합니다 — 동시성이 낮아 CPU 로 여유 있게 처리됩니다."));
body.push(bullet("초기 대량 인덱싱만 CPU 라 다소 느릴 수 있어 야간 배치로 처리합니다(또는 초기 1회만 GPU 단기 사용)."));
body.push(callout("**결정 필요(스펙 입력값)**: ① 게시물/첨부 총량과 증가율 ② 응답 SLA ③ 무GPU→GPU 전환 시점 ④ 기존 그룹웨어 서버 재사용 여부."));

// ===== 12. 로드맵 =====
body.push(h1("12. 단계별 로드맵 (마일스톤 초안)"));
body.push(p("각 단계는 *산출물 + 수락 기준*으로 둡니다."));
body.push(table([1300, 4600, 3126], ["단계", "내용", "수락 기준(예)"], [
  ["P0 환경", "Linux 서버(검색형은 CPU만), 벡터 DB · 전문검색 · DB 기동, 그룹웨어 연동 PoC", "게시판 글 1건 검색 end-to-end"],
  ["P1 게시판 MVP", "게시판(공개) 커넥터 + 인덱싱 + 하이브리드 검색 + **사이드패널** — **검색형(무GPU)**", "공개 게시물 자연어 검색, 정확도 · 지연 기준 통과 (해커톤 데모)"],
  ["P2 권한 · 확장", "권한 정합 + 메일/결재 커넥터, 첨부 파싱(hwp)", "권한 지킨 통합 검색, 증분 동기 안정"],
  ["P3 생성형(GPU)", "리랭커 + 모드 B(요약+인용), 환각/누출 가드 — **GPU 도입 지점**", "인용 정확, 권한 누출 0"],
  ["P4 제품화", "그룹웨어 제품 탑재 · 온프레미스 패키징 · 설치/운영 문서", "고객 환경 설치 PoC 성공"],
  ["P5 운영 · 확장", "모니터링 · 감사 · 백업, 스케일링, 추가 소스", "SLA 충족, 무인 운영"],
], { bodySize: 17, firstColBold: true }));
body.push(spacer());
body.push(callout("**핵심 메시지**: 해커톤 데모는 **P1(게시판 · 무GPU · 사이드패널)** 입니다. GPU 는 P3 부터, 제품화는 P4 에서 다룹니다. 작게 시작해 검증하고 제품으로 키웁니다."));

// ===== 13. 리스크 =====
body.push(h1("13. 리스크 & 대응"));
body.push(table([2000, 1900, 5126], ["리스크", "영향", "대응"], [
  ["게시판 데이터/첨부 품질", "검색 누락", "본문 우선 색인, 첨부 파싱 실패분 큐 · OCR"],
  ["**HWP/한글 문서 파싱**", "첨부 추출 실패", "hwp5/pyhwp + LibreOffice 변환 폴백"],
  ["한국어 검색 품질", "recall↓", "nori 형태소 + 다국어 임베딩 하이브리드 + 리랭커, 평가셋 튜닝"],
  ["확장 시 권한 정합(메일/결재)", "보안", "pre-filter 원칙, 권한/삭제 증분 동기화, 누출 테스트 상시"],
  ["제품화 시 고객 환경 다양성", "이식 비용", "구성 옵션화(무GPU 기본), 패키징 · 설치 자동화"],
  ["GPU 비용", "예산", "무GPU 검색형 우선, 생성형은 단계 도입(§10)"],
  ["프라이버시(메일 확장)", "신뢰 · 컴플라이언스", "공개 게시물부터, 동의 · 정책 검토 후 확장"],
]));

// ===== 14. 결정 필요 =====
body.push(h1("14. 결정 필요 사항 (검토 회의 입력)"));
body.push(callout("보강 단계에서 아래 값들을 채우면 범위 · 일정 · 비용 · 사업성이 구체화됩니다."));
body.push(numbered("decisions", "**게시판 연동 방식**: DB 직접 vs REST, 공개/제한 판정 기준(어떤 필드로 공개 여부를 가리나)."));
body.push(numbered("decisions", "**데이터 규모**: 게시물 · 첨부 총량과 증가율."));
body.push(numbered("decisions", "**확장 우선순위**: 메일 먼저인가 결재 먼저인가, 권한 모델 정의."));
body.push(numbered("decisions", "**제품화**: 그룹웨어 제품 로드맵 반영 시점 · 패키징 · 가격(영업)."));
body.push(numbered("decisions", "**무GPU→GPU 전환 시점**: 생성형(모드 B) 도입 기준."));
body.push(numbered("decisions", "**SLA**: 검색 응답 목표, 가용성 요구."));
body.push(numbered("decisions", "**사이드패널 배포**: 사내 표준 브라우저(Side Panel API 지원), 확장 일괄 배포 정책."));
body.push(numbered("decisions", "**평가셋**: 게시판 질의 골든셋 구성 · 라벨링 주체."));

// ===== 조립 =====
const decimalCfg = (ref) => ({ reference: ref, levels: [{ level: 0, format: LevelFormat.DECIMAL, text: "%1.", alignment: AlignmentType.LEFT, style: { paragraph: { indent: { left: 460, hanging: 280 } } } }] });
const doc = new Document({
  creator: "핸디소프트 서비스개발팀 남종관",
  title: "그룹웨어 통합 검색 (RAG) 개발 기획서 v2",
  description: "사내 해커톤(바이브코딩) 1차 기획안 공모 제출",
  styles: {
    default: { document: { run: { font: BODY, size: 20 } } },
    paragraphStyles: [
      { id: "Heading1", name: "Heading 1", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { size: 30, bold: true, font: BODY, color: ACCENT },
        paragraph: { spacing: { before: 320, after: 160 }, outlineLevel: 0, border: { bottom: { style: BorderStyle.SINGLE, size: 8, color: ACCENT, space: 4 } } } },
      { id: "Heading2", name: "Heading 2", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { size: 24, bold: true, font: BODY, color: "2E5A88" },
        paragraph: { spacing: { before: 220, after: 100 }, outlineLevel: 1 } },
    ],
  },
  numbering: { config: [
    { reference: "b", levels: [
      { level: 0, format: LevelFormat.BULLET, text: "•", alignment: AlignmentType.LEFT, style: { paragraph: { indent: { left: 460, hanging: 260 } } } },
      { level: 1, format: LevelFormat.BULLET, text: "–", alignment: AlignmentType.LEFT, style: { paragraph: { indent: { left: 920, hanging: 260 } } } },
    ] },
    decimalCfg("goals"), decimalCfg("docproc"), decimalCfg("decisions"),
  ] },
  sections: [{
    properties: { titlePage: true, page: { size: { width: 11906, height: 16838 }, margin: { top: 1440, right: 1440, bottom: 1440, left: 1440 } } },
    headers: {
      default: new Header({ children: [new Paragraph({
        tabStops: [{ type: TabStopType.RIGHT, position: CW }], spacing: { after: 0 },
        border: { bottom: { style: BorderStyle.SINGLE, size: 4, color: "D8DDE6", space: 6 } },
        children: [
          new TextRun({ text: "그룹웨어 통합 검색(RAG) 개발 기획서 v2 · 서비스개발팀", size: 16, color: GREY }),
          new TextRun({ text: "\t" }),
          new ImageRun({ type: "png", data: fs.readFileSync(LOGO), transformation: { width: 92, height: 21 }, altText: { title: "HANDYSOFT", description: "핸디소프트 로고", name: "headerLogo" } }),
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
Packer.toBuffer(doc).then((buf) => { fs.writeFileSync(ROOT + "/docs/enterprise-rag-plan-v2.docx", buf); console.log("WROTE docs/enterprise-rag-plan-v2.docx", buf.length, "bytes"); });
