# GPU(생성형, 모드 B) 결과 화면: 무GPU 검색 결과 위에 '요약 답변(인용)'이 추가된 모습.
# 실제 포털 스크린샷 우측 패널만 통합 검색(생성형) 패널로 합성.
from PIL import Image, ImageDraw, ImageFont
from functools import lru_cache

SRC = "C:/Handyground/Workspace/git/flayAI/docs/_planbuild/portal.png"
OUT = "C:/Handyground/Workspace/git/flayAI/docs/_planbuild/sidepanel-mockup-v2-gpu.png"

img = Image.open(SRC).convert("RGB"); W, H = img.size; d = ImageDraw.Draw(img)
X0, YT = 1914, 80
PL, PR = X0 + 24, W - 24; PW = PR - PL
F = "C:/Windows/Fonts/malgun.ttf"; FB = "C:/Windows/Fonts/malgunbd.ttf"
INK="#22262B"; SUB="#5B6470"; FAINT="#98A1AD"; ACC="#1F4E79"; ACC2="#2E5A88"; ACCBG="#EAF1F8"
LINE="#E4E8EE"; CARDLINE="#E2E8F0"; BLUE="#1F6FEB"; GREEN="#1F9D55"; AMBER="#E08600"

@lru_cache(None)
def fnt(s,b=False): return ImageFont.truetype(FB if b else F, s)
def rrect(x0,y0,x1,y1,r,fill=None,outline=None,width=1): d.rounded_rectangle([x0,y0,x1,y1],radius=r,fill=fill,outline=outline,width=width)
def line(x0,y0,x1,y1,fill,width=1): d.line([x0,y0,x1,y1],fill=fill,width=width)
def ell(x0,y0,x1,y1,fill=None,outline=None,width=1): d.ellipse([x0,y0,x1,y1],fill=fill,outline=outline,width=width)
def text(x,y,s,sz,color=INK,b=False): d.text((x,y),s,font=fnt(sz,b),fill=color)
def tw(s,sz,b=False): return d.textlength(s,font=fnt(sz,b))
def wrap(s,sz,maxw,b=False):
    out,cur=[],""
    for w in s.split(" "):
        t=(cur+" "+w).strip()
        if tw(t,sz,b)<=maxw: cur=t
        else:
            if cur: out.append(cur)
            cur=w
    if cur: out.append(cur)
    return out
def elp(s,sz,maxw,b=False):
    if tw(s,sz,b)<=maxw: return s
    while s and tw(s+"…",sz,b)>maxw: s=s[:-1]
    return s+"…"

# 패널 배경/경계
d.rectangle([X0,YT,W,H],fill="#FFFFFF"); line(X0,YT,X0,H,"#D8DDE6",2)
# 헤더
text(PL,YT+16,"통합 검색",30,INK,True)
ix=PR-14
line(ix,YT+22,ix+16,YT+38,FAINT,3); line(ix+16,YT+22,ix,YT+38,FAINT,3)
d.arc([ix-52,YT+22,ix-34,YT+40],30,300,fill=FAINT,width=3)
rrect(ix-86,YT+22,ix-70,YT+38,3,outline=FAINT,width=2)
line(X0,YT+56,W,YT+56,LINE,2)
y=YT+70
# 검색창
rrect(PL,y,PR,y+50,13,fill="#F6F8FB",outline=LINE,width=2)
text(PL+18,y+13,"사내 게시판·공지 자연어 검색…",22,FAINT)
cx,cy=PR-30,y+25; ell(cx-9,cy-9,cx+5,cy+5,outline=SUB,width=3); line(cx+4,cy+4,cx+12,cy+12,SUB,3)
y+=66
# 모드 토글 칩(생성형 ON)
chip="요약 답변(생성형) ON · 인용 기반"
cw=tw(chip,20)+34
rrect(PL,y,PL+cw,y+34,17,fill=ACCBG); ell(PL+12,y+11,PL+24,y+23,outline=ACC2,width=2)
text(PL+32,y+7,chip,20,ACC2,True)
y+=50
# 질의 버블
q="재택근무 며칠까지 가능한지 정리해줘"
ql=wrap(q,23,PW-120); qh=22+len(ql)*34; qw=max(tw(l,23) for l in ql)+40
rrect(PR-qw,y,PR,y+qh,18,fill="#DCE8F5")
for i,l in enumerate(ql): text(PR-qw+20,y+12+i*34,l,23,"#1B2A3A")
y+=qh+18
# ── 요약 답변 블록(생성형) ──
ans="사내 공지 기준, 재택근무는 주 2일까지 신청할 수 있고 부서장 승인 후 적용됩니다. 신청은 전자결재 ‘재택근무 신청서’로 합니다."
al=wrap(ans,21,PW-40)
abh=54+len(al)*30+64
rrect(PL,y,PR,y+abh,13,fill="#F2F7FC",outline="#CFE0F0",width=2)
line(PL,y,PL,y+abh,ACC,6)
text(PL+18,y+12,"요약 답변 (RAG · 인용 기반)",19,ACC,True)
yy=y+44
for l in al: text(PL+18,yy,l,21,INK); yy+=30
text(PL+18,yy+4,"출처: [1] 재택근무 운영지침  [2] 신청 절차 안내",18,ACC2,True)
text(PL+18,yy+32,"근거가 부족하면 답하지 않고 검색 결과만 보여 줍니다.",17,FAINT)
y+=abh+18
# 출처 카드
text(PL,y,"출처 게시물 3건",20,SUB,True); y+=34
cards=[
    ("[1] 공지",BLUE,"2026-04-30","[공지] 재택근무 운영지침 개정","작성 인사팀 · 게시판"),
    ("[2] 게시물",GREEN,"2026-04-12","재택근무 신청 절차 안내","작성 총무팀 · 게시판"),
    ("[3] 게시물",AMBER,"2026-03-08","유연근무제 자주 묻는 질문(FAQ)","작성 인사팀 · 게시판"),
]
ch=104
for badge,col,date,title,meta in cards:
    rrect(PL,y,PR,y+ch,13,fill="#FFFFFF",outline=CARDLINE,width=2)
    bw=tw(badge,19,True)+26
    rrect(PL+18,y+16,PL+18+bw,y+46,11,fill=col); text(PL+31,y+20,badge,19,"#FFFFFF",True)
    text(PR-18-tw(date,19),y+21,date,19,FAINT)
    text(PL+18,y+56,elp(title,24,PW-36,True),24,INK,True)
    text(PL+18,y+86,elp(meta,20,PW-36),20,SUB)
    y+=ch+14
# 푸터
foot="그룹웨어 통합 검색 · 생성형(GPU) · 인용 기반"
text(PL+(PW-tw(foot,19))/2,H-36,foot,19,FAINT)

img.save(OUT); print("WROTE",OUT,img.size)
