# HANDYSOFT_CI.jpg(4분할 CI 시트)에서 '흰 배경 + 영문 HANDYSOFT' 로고를 잘라 logo.png 로 저장.
# 머리글/표지 장식용. 셀 테두리를 피해 안쪽만 보고, 잉크(비흰색) 바운딩박스로 타이트 크롭.
from PIL import Image

src = "C:/Handyground/Workspace/git/flayAI/docs/_planbuild/HANDYSOFT_CI.jpg"
out = "C:/Handyground/Workspace/git/flayAI/docs/_planbuild/logo.png"

im = Image.open(src).convert("RGB")
W, H = im.size
print("CI sheet size:", W, H)

# 좌상단 셀 내부(테두리 제외) 영역
rx0, ry0, rx1, ry1 = int(W * 0.04), int(H * 0.06), int(W * 0.46), int(H * 0.42)
px = im.load()

def is_ink(p):
    r, g, b = p
    return not (r > 232 and g > 232 and b > 232)

minx = miny = 10 ** 9
maxx = maxy = -1
for y in range(ry0, ry1):
    for x in range(rx0, rx1):
        if is_ink(px[x, y]):
            if x < minx: minx = x
            if x > maxx: maxx = x
            if y < miny: miny = y
            if y > maxy: maxy = y

pad = 18
minx = max(rx0, minx - pad); miny = max(ry0, miny - pad)
maxx = min(rx1, maxx + pad); maxy = min(ry1, maxy + pad)
logo = im.crop((minx, miny, maxx, maxy))
print("logo bbox:", (minx, miny, maxx, maxy), "->", logo.size)
logo.save(out)
print("WROTE", out, logo.size)
