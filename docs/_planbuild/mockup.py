# 사내 포털 전체 화면 + 우측 통합 검색 사이드패널 합성 목업 (기획서 삽입용)
# Pillow + 맑은 고딕. 좌측 아이콘 레일 / 상단 탭 / 포털 대시보드 위젯 / 우측 통합 검색 패널.
from PIL import Image, ImageDraw, ImageFont
from functools import lru_cache

S = 2
W, H = 1640, 940
RAIL_W = 54
TOP_H = 46
PANEL_W = 392
PX0 = W - PANEL_W

F = "C:/Windows/Fonts/malgun.ttf"
FB = "C:/Windows/Fonts/malgunbd.ttf"

# 색상
INK = "#22262B"; SUB = "#5B6470"; FAINT = "#9AA3AF"
ACC = "#1F4E79"; ACC2 = "#2E5A88"; ACCBG = "#EAF1F8"
RAIL = "#3346C9"; RAILHI = "#536BEA"
CONTENTBG = "#EDF0F5"; CARD = "#FFFFFF"; LINE = "#E4E8EE"; CARDLINE = "#E3E8EF"
ORANGE = "#F26B21"; BLUE = "#1F6FEB"; GREEN = "#1F9D55"; AMBER = "#E08600"
BAR = "#DDE3EC"

img = Image.new("RGB", (W * S, H * S), "#FFFFFF")
d = ImageDraw.Draw(img)

@lru_cache(None)
def fnt(sz, b=False):
    return ImageFont.truetype(FB if b else F, int(sz * S))

def rrect(x0, y0, x1, y1, r, fill=None, outline=None, width=1):
    d.rounded_rectangle([x0 * S, y0 * S, x1 * S, y1 * S], radius=r * S,
                        fill=fill, outline=outline, width=max(1, int(width * S)))

def rect(x0, y0, x1, y1, fill=None, outline=None, width=1):
    d.rectangle([x0 * S, y0 * S, x1 * S, y1 * S], fill=fill, outline=outline, width=max(1, int(width * S)))

def line(x0, y0, x1, y1, fill, width=1):
    d.line([x0 * S, y0 * S, x1 * S, y1 * S], fill=fill, width=max(1, int(width * S)))

def ell(x0, y0, x1, y1, fill=None, outline=None, width=1):
    d.ellipse([x0 * S, y0 * S, x1 * S, y1 * S], fill=fill, outline=outline, width=max(1, int(width * S)))

def text(x, y, s, sz, color=INK, b=False):
    d.text((x * S, y * S), s, font=fnt(sz, b), fill=color)

def tw(s, sz, b=False):
    return d.textlength(s, font=fnt(sz, b)) / S

def wrap(s, sz, maxw, b=False):
    out, cur = [], ""
    for w in s.split(" "):
        t = (cur + " " + w).strip()
        if tw(t, sz, b) <= maxw:
            cur = t
        else:
            if cur:
                out.append(cur)
            cur = w
    if cur:
        out.append(cur)
    return out

def elp(s, sz, maxw, b=False):
    if tw(s, sz, b) <= maxw:
        return s
    while s and tw(s + "…", sz, b) > maxw:
        s = s[:-1]
    return s + "…"

# ── 배경 영역 ─────────────────────────────────────────
rect(0, 0, W, H, fill="#FFFFFF")
rect(RAIL_W, TOP_H, PX0, H, fill=CONTENTBG)          # 포털 콘텐츠 배경
rect(0, 0, RAIL_W, H, fill=RAIL)                     # 좌측 레일

# ── 좌측 아이콘 레일 ──────────────────────────────────
rrect(14, 12, 40, 38, 6, fill="#FFFFFF")             # 앱 로고 자리
rrect(18, 16, 26, 34, 2, fill=ORANGE); rrect(28, 16, 36, 34, 2, fill=BLUE)
for i in range(9):                                   # 메뉴 아이콘(대략)
    cy = 70 + i * 56
    if i == 0:
        rrect(16, cy, 38, cy + 22, 5, fill=RAILHI)   # 선택된 메뉴
    ell(19, cy + 3, 35, cy + 19, outline="#DCE2FF", width=2)
    ell(25, cy + 9, 29, cy + 13, fill="#DCE2FF")

# ── 상단 바 (탭) ──────────────────────────────────────
rect(RAIL_W, 0, W, TOP_H, fill="#FFFFFF")
line(RAIL_W, TOP_H, W, TOP_H, LINE, 1)
text(RAIL_W + 18, 14, "Home", 13, INK, True)
line(RAIL_W + 18, TOP_H - 3, RAIL_W + 18 + tw("Home", 13, True), TOP_H - 3, ACC, 2)
tx = RAIL_W + 18 + tw("Home", 13, True) + 28
for tab in ["메일", "결재"]:
    text(tx, 14, tab, 13, SUB)
    cx = tx + tw(tab, 13) + 10
    line(cx, 16, cx + 8, 24, FAINT, 1.4); line(cx + 8, 16, cx, 24, FAINT, 1.4)
    tx = cx + 26
# 우측 유틸 아이콘 (프로필 / 알림종 / 메뉴)
ell(W - 94, 14, W - 76, 32, outline=FAINT, width=1.4)        # 프로필
ell(W - 88, 18, W - 82, 24, fill=FAINT)
ell(W - 66, 15, W - 54, 27, outline=FAINT, width=1.4)        # 종
line(W - 62, 27, W - 58, 29, FAINT, 1.4)
for k in range(3):                                           # 햄버거
    line(W - 42, 16 + k * 5, W - 26, 16 + k * 5, FAINT, 1.6)

# ── 포털 로고 + 인사 ──────────────────────────────────
rrect(RAIL_W + 18, TOP_H + 14, RAIL_W + 36, TOP_H + 32, 4, fill=ORANGE)
rrect(RAIL_W + 26, TOP_H + 14, RAIL_W + 44, TOP_H + 32, 4, fill="#2B6BD8")
text(RAIL_W + 52, TOP_H + 16, "HANDYSOFT", 15, "#222A35", True)
greet = "남종관 님 환영합니다 · 2026년 5월 29일 (금)"
text(PX0 - 16 - tw(greet, 11), TOP_H + 19, greet, 11, SUB)

# ── 포털 위젯 카드 (대략) ─────────────────────────────
cx0 = RAIL_W + 16
cx1 = PX0 - 16
gap = 14
colw = (cx1 - cx0 - 2 * gap) / 3
cols = [cx0, cx0 + colw + gap, cx0 + 2 * (colw + gap)]
row_y = [TOP_H + 56, TOP_H + 56 + 190, TOP_H + 56 + 380]
cardh = 176

widgets = [
    ("메일", [("받은 편지함 · 안 읽음 0 / 305", SUB),
              ("[서울보증보험] 보증보험계약현황 안내", FAINT),
              ("[발송실패] 웰기안기 모듈 전달 d2026…", FAINT),
              ("You're doing Champion-level work", FAINT)]),
    ("게시판 / 공지", [("[공지] 2026년 5월 회계 결산 일정", FAINT),
                      ("사내 해커톤(바이브코딩) 1차 기획안 공모", ACC2),
                      ("[공지] 2026년도 건강검진 시행 안내", FAINT),
                      ("[공지] 귀속 건강보험 연말정산 반영", FAINT)]),
    ("결재", [("결재 대기 0 · 공람 대기 0", SUB),
             ("접수 대기 0 · 개인 접수 0", SUB),
             ("수신 반송 0 · 반려 문서 0", SUB)]),
    ("최근 게시물", [("스팸메일(세금계산서) 주의", FAINT),
                  ("루카스 서버 점검 (5/29 17:00~)", FAINT),
                  ("클라우드전환팀 팀명 변경/전환배치", FAINT)]),
    ("일정", [("2026.05", SUB),
             ("29일(금) · 가정의 날", FAINT),
             ("오전 12:00 ~ 자정", FAINT)]),
    ("스퀘어", [("김용세 · 연구총괄 | AI 정보공유", SUB),
              ("오픈소스 HWP 앱 'HOP' 소개", FAINT),
              ("HWP/HWPX 보기·편집 데스크톱 앱", FAINT)]),
    ("나의 출퇴근정보", [("출근 08:59:56", SUB),
                    ("퇴근 -", FAINT),
                    ("정상출근", GREEN)]),
    ("나의 휴가 정보", [("연차잔여 18일", SUB),
                   ("월차잔여 0일", FAINT),
                   ("대체잔여 1.5일", FAINT)]),
    ("바로가기", [("LUKAS · BIS · CSD", SUB),
               ("JIRA · 스마트어카운트", FAINT),
               ("증명서신청 · 명함신청 · 휴머니스트", FAINT)]),
]

for idx, (title, lines) in enumerate(widgets):
    r = idx // 3
    c = idx % 3
    x = cols[c]; y = row_y[r]
    rrect(x, y, x + colw, y + cardh, 9, fill=CARD, outline=CARDLINE, width=1.2)
    text(x + 14, y + 12, title, 12.5, "#2A3340", True)
    text(x + colw - 14 - tw(">", 12), y + 12, ">", 12, FAINT)
    line(x + 14, y + 36, x + colw - 14, y + 36, "#EEF1F6", 1)
    ly = y + 46
    for s, col in lines:
        ell(x + 16, ly + 5, x + 21, ly + 10, fill=col if col != FAINT else "#C7CEDA")
        text(x + 28, ly, elp(s, 10.5, colw - 44), 10.5, col)
        ly += 25

# ── 우측 사이드패널 (통합 검색) ───────────────────────
line(PX0, TOP_H, PX0, H, "#E2E6EE", 1)
rect(PX0, TOP_H, W, H, fill="#FFFFFF")

def P(x):  # 패널 내부 x
    return PX0 + x
PW = PANEL_W

# 패널 헤더
text(P(16), TOP_H + 13, "통합 검색", 16, INK, True)
ix = W - 22
line(ix, TOP_H + 16, ix + 11, TOP_H + 27, FAINT, 2); line(ix + 11, TOP_H + 16, ix, TOP_H + 27, FAINT, 2)
d.arc([(ix - 34) * S, (TOP_H + 16) * S, (ix - 23) * S, (TOP_H + 27) * S], 30, 300, fill=FAINT, width=int(1.6 * S))
rrect(ix - 56, TOP_H + 16, ix - 46, TOP_H + 26, 2, outline=FAINT, width=1.4)
line(PX0, TOP_H + 42, W, TOP_H + 42, LINE, 1)

y = TOP_H + 54
# 검색창
rrect(P(14), y, W - 14, y + 38, 9, fill="#F6F8FB", outline=LINE, width=1.2)
text(P(26), y + 11, "메일 · 게시물 · 결재 자연어 검색…", 11.5, FAINT)
cxx, cyy = W - 34, y + 19
ell(cxx - 6, cyy - 6, cxx + 4, cyy + 4, outline=SUB, width=1.6)
line(cxx + 3, cyy + 3, cxx + 8, cyy + 8, SUB, 2)
y += 50
# 맥락 칩(⑧)
chip = "현재 화면(결재 HSO-29491) 맥락"
cw = tw(chip, 10) + 20
rrect(P(14), y, P(14) + cw, y + 24, 12, fill=ACCBG)
ell(P(21), y + 8, P(27), y + 14, outline=ACC2, width=1.4)
text(P(32), y + 6, chip, 10, ACC2, True)
y += 36
# 질의 버블
q = "지난 분기 마케팅 예산 결재 문서 찾아줘"
ql = wrap(q, 12, 230)
qh = 12 + len(ql) * 18
qw = max(tw(l, 12) for l in ql) + 22
rrect(W - 14 - qw, y, W - 14, y + qh, 11, fill="#DCE8F5")
for i, l in enumerate(ql):
    text(W - 14 - qw + 11, y + 7 + i * 18, l, 12, "#1B2A3A")
y += qh + 10
# 요약 한 줄
text(P(16), y, "결재문서 3건 · 기간 2026 Q1 · 부서 마케팅", 10.5, SUB, True)
y += 22
# 결과 카드
cards = [
    ("결재", BLUE, "03-18", "2026년 1분기 마케팅 예산 집행 결재", "기안 김마케팅 · 전자결재", "디지털 광고·전시 예산 집행 내역, 잔액 12%"),
    ("메일", GREEN, "03-20", "[공유] Q1 마케팅 예산 정산 안내", "발신 이팀장 · 메일", "정산 마감일과 증빙 양식을 안내드립니다"),
    ("게시물", AMBER, "02-28", "마케팅실 분기 예산 운영 지침", "작성 기획팀 · 게시판", "분기별 예산 편성·이월 기준 정리"),
]
ch = 104
for badge, col, date, title, meta, snip in cards:
    rrect(P(14), y, W - 14, y + ch, 9, fill="#FFFFFF", outline=CARDLINE, width=1.2)
    bw = tw(badge, 9.5, True) + 14
    rrect(P(24), y + 11, P(24) + bw, y + 29, 8, fill=col)
    text(P(31), y + 13, badge, 9.5, "#FFFFFF", True)
    text(W - 24 - tw(date, 9.5), y + 13, date, 9.5, FAINT)
    text(P(24), y + 36, elp(title, 12.5, PW - 52, True), 12.5, INK, True)
    text(P(24), y + 57, elp(meta, 10, PW - 52), 10, SUB)
    text(P(24), y + 75, elp(snip, 10, PW - 52), 10, FAINT)
    y += ch + 11

# Windows 알림 토스트(⑨)
y += 4
text(P(16), y, "브라우저가 비활성일 때 — Windows 알림", 10.5, ACC2, True)
y += 20
rrect(P(14), y, W - 14, y + 80, 9, fill="#FBFBFD", outline="#DADDE3", width=1.2)
rrect(P(24), y + 15, P(54), y + 45, 7, fill=ACC)
text(P(28), y + 22, "통검", 10.5, "#FFFFFF", True)
text(P(66), y + 15, "통합 검색 · 결과 준비됨", 11.5, INK, True)
text(P(66), y + 35, "‘마케팅 예산 결재’ 결과 3건 도착", 10, SUB)
text(P(66), y + 53, "클릭하면 사이드패널에서 결과 확인", 9.5, FAINT)
text(W - 52, y + 12, "지금", 9, FAINT)

# 패널 푸터
foot = "사내 통합 검색 · 온프레미스 · 사내망 전용"
text(P((PW - tw(foot, 9.5)) / 2), H - 24, foot, 9.5, FAINT)

out = "C:/Handyground/Workspace/git/flayAI/docs/_planbuild/sidepanel-mockup.png"
img.save(out)
print("WROTE", out, img.size)
