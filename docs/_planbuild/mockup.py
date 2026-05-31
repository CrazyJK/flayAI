# 실제 사내 포털 스크린샷(portal.png)은 그대로 두고,
# 우측 M365 Copilot(다크) 패널 영역만 우리 '통합 검색' 패널로 덮어 합성한다.
# 측정값: 패널 좌측 경계 x0=1916, 브라우저 상단 바 아래 y_top≈80.
from PIL import Image, ImageDraw, ImageFont
from functools import lru_cache

SRC = "C:/Handyground/Workspace/git/flayAI/docs/_planbuild/portal.png"
OUT = "C:/Handyground/Workspace/git/flayAI/docs/_planbuild/sidepanel-mockup.png"

img = Image.open(SRC).convert("RGB")
W, H = img.size
d = ImageDraw.Draw(img)

X0 = 1914          # 패널 좌측(덮기 시작) — 다크 패널 완전히 가리도록 한 픽셀 여유
YT = 80            # 브라우저 상단 바 아래(창 제어·탭은 그대로 유지)
PL = X0 + 24       # 패널 내부 좌측 여백
PR = W - 24        # 패널 내부 우측 여백
PW = PR - PL

F = "C:/Windows/Fonts/malgun.ttf"
FB = "C:/Windows/Fonts/malgunbd.ttf"

INK = "#22262B"; SUB = "#5B6470"; FAINT = "#98A1AD"
ACC = "#1F4E79"; ACC2 = "#2E5A88"; ACCBG = "#EAF1F8"
LINE = "#E4E8EE"; CARDLINE = "#E2E8F0"
BLUE = "#1F6FEB"; GREEN = "#1F9D55"; AMBER = "#E08600"

@lru_cache(None)
def fnt(sz, b=False):
    return ImageFont.truetype(FB if b else F, sz)

def rrect(x0, y0, x1, y1, r, fill=None, outline=None, width=1):
    d.rounded_rectangle([x0, y0, x1, y1], radius=r, fill=fill, outline=outline, width=width)

def line(x0, y0, x1, y1, fill, width=1):
    d.line([x0, y0, x1, y1], fill=fill, width=width)

def ell(x0, y0, x1, y1, fill=None, outline=None, width=1):
    d.ellipse([x0, y0, x1, y1], fill=fill, outline=outline, width=width)

def text(x, y, s, sz, color=INK, b=False):
    d.text((x, y), s, font=fnt(sz, b), fill=color)

def tw(s, sz, b=False):
    return d.textlength(s, font=fnt(sz, b))

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

# ── 패널 영역을 흰색으로 덮고 좌측 경계선 ───────────────
d.rectangle([X0, YT, W, H], fill="#FFFFFF")
line(X0, YT, X0, H, "#D8DDE6", 2)

# ── 패널 헤더 ─────────────────────────────────────────
text(PL, YT + 16, "통합 검색", 30, INK, True)
ix = PR - 14
line(ix, YT + 22, ix + 16, YT + 38, FAINT, 3); line(ix + 16, YT + 22, ix, YT + 38, FAINT, 3)   # ×
d.arc([ix - 52, YT + 22, ix - 34, YT + 40, ], 30, 300, fill=FAINT, width=3)                      # 새로고침
rrect(ix - 86, YT + 22, ix - 70, YT + 38, 3, outline=FAINT, width=2)                             # 새창
line(X0, YT + 56, W, YT + 56, LINE, 2)

y = YT + 70
# 검색창
rrect(PL, y, PR, y + 50, 13, fill="#F6F8FB", outline=LINE, width=2)
text(PL + 18, y + 13, "메일 · 게시물 · 결재 자연어 검색…", 22, FAINT)
cx, cy = PR - 30, y + 25
ell(cx - 9, cy - 9, cx + 5, cy + 5, outline=SUB, width=3); line(cx + 4, cy + 4, cx + 12, cy + 12, SUB, 3)
y += 66
# 현재 화면 맥락 칩(⑧)
chip = "현재 화면(결재 HSO-29491) 맥락"
cw = tw(chip, 20) + 34
rrect(PL, y, PL + cw, y + 34, 17, fill=ACCBG)
ell(PL + 12, y + 11, PL + 24, y + 23, outline=ACC2, width=2)
text(PL + 32, y + 7, chip, 20, ACC2, True)
y += 50
# 사용자 질의 버블
q = "지난 분기 마케팅 예산 결재 문서 찾아줘"
ql = wrap(q, 23, PW - 120)
qh = 22 + len(ql) * 34
qw = max(tw(l, 23) for l in ql) + 40
rrect(PR - qw, y, PR, y + qh, 18, fill="#DCE8F5")
for i, l in enumerate(ql):
    text(PR - qw + 20, y + 12 + i * 34, l, 23, "#1B2A3A")
y += qh + 18
# 코드 요약 한 줄
text(PL, y, "결재문서 3건 · 기간 2026 Q1 · 부서 마케팅", 20, SUB, True)
y += 40
# 결과 카드
cards = [
    ("결재", BLUE, "2026-03-18", "2026년 1분기 마케팅 예산 집행 결재", "기안 김마케팅 · 전자결재", "디지털 광고·전시 예산 집행 내역, 잔액 12% 현황"),
    ("메일", GREEN, "2026-03-20", "[공유] Q1 마케팅 예산 정산 안내", "발신 이팀장 · 메일", "정산 마감일과 증빙 양식을 안내드립니다"),
    ("게시물", AMBER, "2026-02-28", "마케팅실 분기 예산 운영 지침", "작성 기획팀 · 게시판", "분기별 예산 편성·이월 기준 정리"),
]
ch = 150
for badge, col, date, title, meta, snip in cards:
    rrect(PL, y, PR, y + ch, 13, fill="#FFFFFF", outline=CARDLINE, width=2)
    bw = tw(badge, 19, True) + 26
    rrect(PL + 18, y + 16, PL + 18 + bw, y + 46, 11, fill=col)
    text(PL + 31, y + 20, badge, 19, "#FFFFFF", True)
    text(PR - 18 - tw(date, 19), y + 21, date, 19, FAINT)
    text(PL + 18, y + 56, elp(title, 25, PW - 36, True), 25, INK, True)
    text(PL + 18, y + 92, elp(meta, 20, PW - 36), 20, SUB)
    text(PL + 18, y + 120, elp(snip, 20, PW - 36), 20, FAINT)
    y += ch + 16

# Windows 알림 토스트(⑨)
y += 8
text(PL, y, "브라우저가 비활성일 때 — Windows 알림", 20, ACC2, True)
y += 34
rrect(PL, y, PR, y + 116, 13, fill="#FBFBFD", outline="#DADDE3", width=2)
rrect(PL + 18, y + 22, PL + 62, y + 66, 9, fill=ACC)
text(PL + 25, y + 31, "통검", 20, "#FFFFFF", True)
text(PL + 78, y + 22, "통합 검색 · 결과 준비됨", 23, INK, True)
text(PL + 78, y + 56, "‘마케팅 예산 결재’ 결과 3건 도착", 20, SUB)
text(PL + 78, y + 84, "클릭하면 사이드패널에서 결과 확인", 19, FAINT)
text(PR - 64, y + 18, "지금", 18, FAINT)

# 패널 푸터
foot = "사내 통합 검색 · 온프레미스 · 사내망 전용"
text(PL + (PW - tw(foot, 19)) / 2, H - 36, foot, 19, FAINT)

img.save(OUT)
print("WROTE", OUT, img.size)
