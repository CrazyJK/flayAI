# 사내 통합 검색 — 브라우저 사이드패널 예상 화면 목업 (기획서 삽입용)
# Pillow 로 그려 PNG 저장. 한글은 맑은 고딕(C:/Windows/Fonts) 사용.
from PIL import Image, ImageDraw, ImageFont
from functools import lru_cache

S = 2                       # 2x 렌더링(선명도)
W, H = 472, 772             # 논리 캔버스 크기
F = "C:/Windows/Fonts/malgun.ttf"
FB = "C:/Windows/Fonts/malgunbd.ttf"

# 색상
INK = "#22262B"; SUB = "#6B7480"; FAINT = "#9AA3AF"
ACC = "#1F4E79"; ACC2 = "#2E5A88"; ACCBG = "#EAF1F8"
LINE = "#E4E8EE"; CARDLINE = "#E2E8F0"
BLUE = "#1F6FEB"; GREEN = "#1F9D55"; ORANGE = "#E08600"

img = Image.new("RGB", (W * S, H * S), "#FFFFFF")
d = ImageDraw.Draw(img)

@lru_cache(None)
def fnt(sz, b=False):
    return ImageFont.truetype(FB if b else F, int(sz * S))

def rrect(x0, y0, x1, y1, r, fill=None, outline=None, width=1):
    d.rounded_rectangle([x0 * S, y0 * S, x1 * S, y1 * S], radius=r * S,
                        fill=fill, outline=outline, width=max(1, int(width * S)))

def line(x0, y0, x1, y1, fill, width=1):
    d.line([x0 * S, y0 * S, x1 * S, y1 * S], fill=fill, width=max(1, int(width * S)))

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

def ellipsize(s, sz, maxw, b=False):
    if tw(s, sz, b) <= maxw:
        return s
    while s and tw(s + "…", sz, b) > maxw:
        s = s[:-1]
    return s + "…"

# ── 헤더 ──────────────────────────────────────────────
text(16, 16, "통합 검색", 16, INK, True)
# 우측 아이콘(대략): 새창 / 새로고침 / 닫기
ix = W - 22
# 닫기 ×
line(ix, 20, ix + 11, 31, FAINT, 2); line(ix + 11, 20, ix, 31, FAINT, 2)
# 새로고침(원호)
d.arc([(ix - 34) * S, 20 * S, (ix - 23) * S, 31 * S], 30, 300, fill=FAINT, width=int(1.6 * S))
# 새창(사각+점)
rrect(ix - 56, 20, ix - 46, 30, 2, outline=FAINT, width=1.4)
line(52, 0, 52, H, "#EDEFF3", 1)   # 좌측 부착 경계선
line(0, 52, W, 52, LINE, 1)        # 헤더 하단선

# ── 검색 입력 ─────────────────────────────────────────
rrect(14, 66, W - 14, 106, 10, fill="#F6F8FB", outline=LINE, width=1.2)
text(26, 79, "메일 · 게시물 · 결재 자연어 검색…", 12, FAINT)
# 돋보기
cx, cy = W - 34, 86
d.ellipse([(cx - 6) * S, (cy - 6) * S, (cx + 4) * S, (cy + 4) * S], outline=SUB, width=int(1.6 * S))
line(cx + 3, cy + 3, cx + 8, cy + 8, SUB, 2)

# ── 현재 화면 맥락 칩(⑧) ───────────────────────────────
chip = "현재 화면(결재 HSO-29491) 맥락 포함"
cw = tw(chip, 10.5) + 22
rrect(14, 116, 14 + cw, 142, 13, fill=ACCBG)
d.ellipse([(22) * S, (126) * S, (28) * S, (132) * S], outline=ACC2, width=int(1.4 * S))
text(34, 122, chip, 10.5, ACC2, True)

# ── 사용자 질의 버블 ──────────────────────────────────
q = "지난 분기 마케팅 예산 결재 문서 찾아줘"
qlines = wrap(q, 12.5, 250)
qh = 14 + len(qlines) * 19
qw = max(tw(l, 12.5) for l in qlines) + 24
qx1 = W - 14; qx0 = qx1 - qw
rrect(qx0, 154, qx1, 154 + qh, 12, fill="#DCE8F5")
for i, l in enumerate(qlines):
    text(qx0 + 12, 162 + i * 19, l, 12.5, "#1B2A3A")
y = 154 + qh + 10

# ── 코드 요약 한 줄(건수+필터) ─────────────────────────
text(16, y, "결재문서 3건 · 기간 2026 Q1 · 부서 마케팅", 11, SUB, True)
y += 24

# ── 결과 카드 3장 ─────────────────────────────────────
cards = [
    ("결재", BLUE, "2026-03-18", "2026년 1분기 마케팅 예산 집행 결재",
     "기안 김마케팅 · 전자결재", "디지털 광고·전시 예산 집행 내역과 잔액 12% 현황"),
    ("메일", GREEN, "2026-03-20", "[공유] Q1 마케팅 예산 정산 안내",
     "발신 이팀장 · 메일", "정산 마감일과 증빙 양식을 안내드립니다"),
    ("게시물", ORANGE, "2026-02-28", "마케팅실 분기 예산 운영 지침",
     "작성 기획팀 · 게시판", "분기별 예산 편성·이월 기준을 정리한 안내"),
]
ch = 112
for badge, col, date, title, meta, snip in cards:
    rrect(14, y, W - 14, y + ch, 10, fill="#FFFFFF", outline=CARDLINE, width=1.2)
    bw = tw(badge, 10, True) + 16
    rrect(26, y + 12, 26 + bw, y + 32, 9, fill=col)
    text(34, y + 15, badge, 10, "#FFFFFF", True)
    text(W - 26 - tw(date, 10), y + 16, date, 10, FAINT)
    text(26, y + 40, ellipsize(title, 13.5, W - 56, True), 13.5, INK, True)
    text(26, y + 63, ellipsize(meta, 10.5, W - 56), 10.5, SUB)
    text(26, y + 82, ellipsize(snip, 10.5, W - 56), 10.5, FAINT)
    y += ch + 12

# ── Windows 알림 토스트(⑨) ────────────────────────────
y += 2
text(16, y, "브라우저가 비활성일 때 — Windows 알림", 10.5, ACC2, True)
y += 20
rrect(14, y, W - 14, y + 84, 10, fill="#FBFBFD", outline="#DADDE3", width=1.2)
# 앱 아이콘
rrect(26, y + 16, 58, y + 48, 7, fill=ACC)
text(31, y + 24, "통검", 11, "#FFFFFF", True)
text(70, y + 16, "통합 검색 · 결과 준비됨", 12, INK, True)
text(70, y + 38, "‘마케팅 예산 결재’ 결과 3건이 도착했습니다.", 10.5, SUB)
text(70, y + 56, "클릭하면 사이드패널에서 결과를 봅니다.", 10, FAINT)
text(W - 64, y + 12, "지금", 9.5, FAINT)

# ── 푸터 ──────────────────────────────────────────────
foot = "사내 통합 검색 · 온프레미스 · 사내망 전용"
text((W - tw(foot, 9.5)) / 2, H - 26, foot, 9.5, FAINT)

out = "C:/Handyground/Workspace/git/flayAI/docs/_planbuild/sidepanel-mockup.png"
img.save(out)
print("WROTE", out, img.size)
