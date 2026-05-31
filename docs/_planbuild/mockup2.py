# v2: 실제 사내 포털 스크린샷(portal.png)은 그대로, 우측 Copilot(다크) 패널만
# '통합 검색' 패널로 덮어 합성. v2 범위(사내 게시판)에 맞춰 결과는 공지/게시물 중심,
# 비동기 알림 토스트는 제외(차별화 축소 반영).
from PIL import Image, ImageDraw, ImageFont
from functools import lru_cache

SRC = "C:/Handyground/Workspace/git/flayAI/docs/_planbuild/portal.png"
OUT = "C:/Handyground/Workspace/git/flayAI/docs/_planbuild/sidepanel-mockup-v2.png"

img = Image.open(SRC).convert("RGB")
W, H = img.size
d = ImageDraw.Draw(img)

X0 = 1914
YT = 80
PL = X0 + 24
PR = W - 24
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

# 패널 영역 흰색 + 좌측 경계선
d.rectangle([X0, YT, W, H], fill="#FFFFFF")
line(X0, YT, X0, H, "#D8DDE6", 2)

# 헤더
text(PL, YT + 16, "통합 검색", 30, INK, True)
ix = PR - 14
line(ix, YT + 22, ix + 16, YT + 38, FAINT, 3); line(ix + 16, YT + 22, ix, YT + 38, FAINT, 3)
d.arc([ix - 52, YT + 22, ix - 34, YT + 40], 30, 300, fill=FAINT, width=3)
rrect(ix - 86, YT + 22, ix - 70, YT + 38, 3, outline=FAINT, width=2)
line(X0, YT + 56, W, YT + 56, LINE, 2)

y = YT + 70
# 검색창
rrect(PL, y, PR, y + 50, 13, fill="#F6F8FB", outline=LINE, width=2)
text(PL + 18, y + 13, "사내 게시판·공지 자연어 검색…", 22, FAINT)
cx, cy = PR - 30, y + 25
ell(cx - 9, cy - 9, cx + 5, cy + 5, outline=SUB, width=3); line(cx + 4, cy + 4, cx + 12, cy + 12, SUB, 3)
y += 66
# 현재 화면 맥락 칩(사이드패널)
chip = "현재 화면(게시판) 맥락"
cw = tw(chip, 20) + 34
rrect(PL, y, PL + cw, y + 34, 17, fill=ACCBG)
ell(PL + 12, y + 11, PL + 24, y + 23, outline=ACC2, width=2)
text(PL + 32, y + 7, chip, 20, ACC2, True)
y += 50
# 사용자 질의 버블
q = "재택근무 정책 최신 공지 찾아줘"
ql = wrap(q, 23, PW - 120)
qh = 22 + len(ql) * 34
qw = max(tw(l, 23) for l in ql) + 40
rrect(PR - qw, y, PR, y + qh, 18, fill="#DCE8F5")
for i, l in enumerate(ql):
    text(PR - qw + 20, y + 12 + i * 34, l, 23, "#1B2A3A")
y += qh + 18
# 코드 요약 한 줄
text(PL, y, "게시물 3건 · 게시판 · 최신순", 20, SUB, True)
y += 40
# 결과 카드 (게시판 공개글)
cards = [
    ("공지", BLUE, "2026-05-22", "[공지] 2026년 5월 회계 결산 일정", "작성 재무팀 · 게시판", "5월 결산 마감일과 증빙 제출 절차 안내"),
    ("게시물", GREEN, "2026-05-19", "사내 해커톤(바이브코딩) 1차 기획안 공모", "작성 혁신팀 · 게시판", "주제·일정·제출 양식 안내"),
    ("공지", AMBER, "2026-05-20", "[공지] 2026년도 건강검진 시행 안내", "작성 인사팀 · 게시판", "검진 기관·기간·대상자 안내"),
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

# 출처 안내(환각 없는 검색 우선)
y += 6
text(PL, y, "결과는 출처 게시물 카드로 — 지어내지 않습니다.", 19, ACC2, True)

# 푸터
foot = "그룹웨어 통합 검색 · 온프레미스 · 사내망 전용"
text(PL + (PW - tw(foot, 19)) / 2, H - 36, foot, 19, FAINT)

img.save(OUT)
print("WROTE", OUT, img.size)
