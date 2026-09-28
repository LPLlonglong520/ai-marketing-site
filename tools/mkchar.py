#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
营销AI小秘 · 立牌「可点击角色」分层素材生成（多块立牌 / 男女版本切换用）

背景
----
页头立牌 = **无人版底图**（`tools/mkplate.py` 出的，里面没有人） + 叠在上面的可点击角色分层
（`media/de_char*_*.webp`，本脚本切出来的这几层）。正面和翻过去的背面各是一块立牌，
两块都要分层 —— 只用底图的话，翻到背面点「打招呼」就没人动。

    ⚠️ 底图里绝不能烘焙人物：一旦烘焙，做「打招呼 / 转身」时底图那个人不跟着动，
       就会和分层叠成重影（挥手多一只手、转身整个人变两个）。
    ⚠️ 每块立牌的分层必须来自它自己那张立牌源图（人物位置/大小不同，不能混用）。

切法：从立牌源目录里的 `assets/character_standee.png`（带 alpha 的人物素材）按立牌图的几何
对齐，切成 head / arm / tab / body 四块（+ 一份 wave_arm 备用），写回媒体目录。
每层 mask 会向外膨胀 1px，让相邻层边缘互相压住，避免浏览器缩放后出现发丝缝。

用法
----
    python tools/mkchar.py            # 两块都切（hero + back）
    python tools/mkchar.py hero       # 只切页头正面
    python tools/mkchar.py back       # 只切背面
    python tools/mkchar.py --dry      # 只校验、不写文件

源图取自 content.md 的「页头立牌源图 / 背面立牌源图」，同目录下的 assets/character_standee.png；
人物在立牌上的摆放位置直接读该目录 poster.html 里那行人物 <img> 的 left/top/width，
不再手工维护一套 CHAR_* 数字（那是重影的来源）。

切分参数（CUT_N）用「相对人物外接矩形」的**归一化比例**表达 —— 两块立牌人物大小不同，
归一化之后同一套参数直接复用，不用为每块立牌重调：
  · head_y  头部/身体的分界线（脖子高度）
  · arm     手臂区（左侧，用亮度筛出浅色衣袖/手，避免把深色裙摆切进去）
  · tab     平板区（这一层没有任何动画引用，切不准也不会露馅）
  · 其余 = body
分层之和严格等于原人物轮廓（脚本会校验，差值为 0）。

跑完会写 `media/de_char_layout.json`：每块立牌的 `.de-char` 盒（left/top/width/height 百分比）
与转动轴心（head/arm 的 transform-origin 百分比）。`build.py` 直接读它，不用手工抄数字。
"""
import json
import os
import re
import sys

from PIL import Image

# ---------------- 路径 ----------------

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # ai-marketing-site/
CONTENT = os.path.join(BASE, 'content.md')
MEDIA = os.path.join(BASE, 'media')
LAYOUT_JSON = os.path.join(MEDIA, 'de_char_layout.json')

# 立牌海报画布（与 立牌/refresh.py 的 PAGE_W / PAGE_H 一致）
POSTER_W, POSTER_H = 2100.0, 2680.0

# 层画布的横向像素数（各层图片尺寸 = 画布宽 × 画布宽×盒高/盒宽）。
# 分层的显示尺寸 ≈ 立牌显示宽度 560px × 盒宽占比，420 是"清晰度 vs 体积"调过的值：
# 4 层合计约 50KB；再加倍到 840 体积涨到 ~190KB，收益不值。
CANVAS_W = 420

# 人物外接矩形四周留白 = 人头宽的 2%（人物在层画布里永远落在同一个相对位置，
# 所以 CUT_N 那套归一化参数两块立牌通用）
PAD_FRAC = 0.02

# ---------------- 两块立牌 ----------------

FACES = {
    'hero': dict(label='页头正面（场景版女 · 人物站立中间）', src_key='页头立牌源图',
                 prefix='media/de_char_'),
    'back': dict(label='背面（现有版女）', src_key='背面立牌源图',
                 prefix='media/de_char_b_'),
}

# ---------------- 切分参数（相对人物外接矩形的归一化比例） ----------------
# 由原先「按第一块立牌手调好的像素值 ÷ 它的人物矩形」反推得到，两块立牌通用。
CUT_N = dict(
    head_y=0.21810,
    arm=dict(x0=0.02005, x1=0.44110, y0=0.19490, y1=0.39095, lum_min=118),
    tab=dict(x0=0.63409, x1=0.86717, y0=0.22274, y1=0.31323),
)

LAYERS = ('body', 'head', 'tab', 'arm', 'wave_arm')


def read_source(src_key):
    """从 content.md 读源图路径，返回 (立牌 PNG, 人物素材 PNG)。"""
    text = open(CONTENT, encoding='utf-8').read()
    sec = text.split('### 立牌素材源', 1)
    if len(sec) < 2:
        raise SystemExit('× content.md 里找不到「### 立牌素材源」')
    m = re.search(r'^\|\s*' + re.escape(src_key) + r'\s*\|\s*(.+?)\s*\|\s*$', sec[1], re.M)
    if not m:
        raise SystemExit('× content.md 里找不到「%s」' % src_key)
    board = m.group(1).strip()
    standee = os.path.join(os.path.dirname(board), 'assets', 'character_standee.png')
    for p in (board, standee):
        if not os.path.exists(p):
            raise SystemExit('× 找不到文件：%s' % p)
    return board, standee


def read_char_rect(board, standee_size):
    """读 poster.html 里人物 <img> 的摆放（left/top/width），算出 CSS 像素外接矩形。"""
    poster = os.path.join(os.path.dirname(board), 'poster.html')
    html = open(poster, encoding='utf-8').read()
    m = re.search(r'<img\s+src="assets/character_standee\.png"[^>]*style="([^"]*)"', html)
    if not m:
        raise SystemExit('× poster.html 里找不到人物 <img>（模板结构变了？）')
    style = m.group(1)

    def px(name):
        mm = re.search(r'(?:^|;)\s*' + name + r'\s*:\s*([\d.]+)px', style)
        return float(mm.group(1)) if mm else None

    left, top, width = px('left'), px('top'), px('width')
    if None in (left, top, width):
        raise SystemExit('× poster.html 人物 <img> 的 left/top/width 没写全：%s' % style)
    sw, sh = standee_size
    return left, top, width, width * sh / sw


def face_layout(rect):
    """由人物矩形推出：层画布尺寸、人物在画布里的贴图位置、以及 .de-char 盒的百分比。"""
    x, y, w, h = rect
    pad = PAD_FRAC * w
    bx, by, bw, bh = x - pad, y - pad, w + 2 * pad, h + 2 * pad
    cw = CANVAS_W
    for _ in range(40):                       # 最多放大 80px，正常一圈就够
        ch = int(round(cw * bh / bw))
        k = cw / bw
        size = (int(round(w * k)), int(round(h * k)))
        pos = (int(round(pad * k)), int(round(pad * k)))
        if pos[0] + size[0] <= cw and pos[1] + size[1] <= ch:
            break
        cw += 2
    else:
        raise SystemExit('× 层画布自适应失败')
    box = (bx / POSTER_W * 100, by / POSTER_H * 100, bw / POSTER_W * 100, bh / POSTER_H * 100)
    return dict(canvas=(cw, ch), size=size, pos=pos, box=box)


def build_canvas(standee_path, canvas_size, size, pos):
    """把人物素材按立牌图的几何放进层画布。"""
    src = Image.open(standee_path).convert('RGBA')
    canvas = Image.new('RGBA', canvas_size, (0, 0, 0, 0))
    canvas.paste(src.resize(size, Image.LANCZOS), pos)
    return canvas


def cut_px(canvas_size, rect_pos, rect_size):
    """归一化切分参数 → 本块立牌的像素坐标。"""
    x0, y0 = rect_pos
    w, h = rect_size
    X = lambda f: x0 + f * w
    Y = lambda f: y0 + f * h
    return dict(
        head_y=Y(CUT_N['head_y']),
        arm=dict(x0=X(CUT_N['arm']['x0']), x1=X(CUT_N['arm']['x1']),
                 y0=Y(CUT_N['arm']['y0']), y1=Y(CUT_N['arm']['y1']),
                 lum_min=CUT_N['arm']['lum_min']),
        tab=dict(x0=X(CUT_N['tab']['x0']), x1=X(CUT_N['tab']['x1']),
                 y0=Y(CUT_N['tab']['y0']), y1=Y(CUT_N['tab']['y1'])),
    )


def split(canvas, cut):
    """按 head_y / arm / tab 把人物轮廓切成 4 块（和为全体）。

    轮廓阈值取 alpha > 8（不是 > 100）：把人物最外圈的半透明描边也带上，
    这样几层拼回去 == 原素材（含软边），底图换成"无人版"后边缘才不会发硬。
    """
    A = canvas.getchannel('A').load()
    L = canvas.convert('L').load()
    w, h = canvas.size
    HEAD_Y, ARM, TAB = cut['head_y'], cut['arm'], cut['tab']
    parts = {k: set() for k in ('head', 'arm', 'tab')}
    sil = set()
    for y in range(h):
        for x in range(w):
            if A[x, y] <= 8:
                continue
            sil.add((x, y))
            if y < HEAD_Y:
                parts['head'].add((x, y))
            elif (ARM['x0'] <= x <= ARM['x1'] and ARM['y0'] <= y <= ARM['y1']
                  and L[x, y] >= ARM['lum_min']):
                parts['arm'].add((x, y))
            elif TAB['x0'] <= x <= TAB['x1'] and TAB['y0'] <= y <= TAB['y1']:
                parts['tab'].add((x, y))
    parts['body'] = sil - parts['head'] - parts['arm'] - parts['tab']
    return parts, sil


def dilate(pts, w, h):
    """mask 向外膨胀 1px：相邻层边缘互相压住，避免缩放后出现发丝缝。"""
    out = set(pts)
    for (x, y) in pts:
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            nx, ny = x + dx, y + dy
            if 0 <= nx < w and 0 <= ny < h:
                out.add((nx, ny))
    return out


def to_image(canvas, pts):
    """把像素集合还原成一张透明图。"""
    w, h = canvas.size
    mask = Image.new('L', (w, h), 0)
    mp = mask.load()
    for (x, y) in pts:
        mp[x, y] = 255
    layer = Image.new('RGBA', (w, h), (0, 0, 0, 0))
    layer.paste(canvas, (0, 0), mask)
    return layer


def composite(layers):
    out = Image.new('RGBA', layers[0].size, (0, 0, 0, 0))
    for im in layers:
        out = Image.alpha_composite(out, im)
    return out


def do_face(key, dry=False):
    cfg = FACES[key]
    board, standee = read_source(cfg['src_key'])
    ssize = Image.open(standee).size
    rect = read_char_rect(board, ssize)
    lay = face_layout(rect)
    canvas = build_canvas(standee, lay['canvas'], lay['size'], lay['pos'])
    cut = cut_px(lay['canvas'], lay['pos'], lay['size'])

    print('─' * 70)
    print('【%s】' % cfg['label'])
    print('立牌源图  %s  %s' % (os.path.basename(board), Image.open(board).size))
    print('人物素材  %s  %s' % (os.path.basename(standee), ssize))
    print('人物摆放  left=%.0f top=%.0f width=%.0f height=%.1f  （读自 poster.html）' % rect)
    print('层画布 %dx%d   人物贴图 %dx%d @ (%d,%d)'
          % (lay['canvas'] + lay['size'] + lay['pos']))
    print('.de-char 盒  left:%.4f%%  top:%.4f%%  width:%.4f%%  height:%.4f%%' % lay['box'])

    parts, sil = split(canvas, cut)
    print('像素：' + '  '.join('%s %d' % (n, len(parts[n])) for n in ('head', 'arm', 'tab', 'body')))

    imgs = {n: to_image(canvas, parts[n]) for n in ('body', 'head', 'tab', 'arm')}
    imgs['wave_arm'] = imgs['arm']

    # 校验：四层之和 == 原人物轮廓（只允许半透明描边像素缺失）
    back = composite([imgs['body'], imgs['tab'], imgs['arm'], imgs['head']])
    a1, a2 = canvas.load(), back.load()
    diff = faint = 0
    for y in range(canvas.size[1]):
        for x in range(canvas.size[0]):
            p, q = a1[x, y], a2[x, y]
            if abs(p[3] - q[3]) > 2 or (p[3] and q[3] and max(abs(p[i] - q[i]) for i in range(3)) > 2):
                diff += 1
                if p[3] <= 100:
                    faint += 1
    print('校验：分层合成 vs 原人物  差异像素 %d（其中边缘半透明 %d → 属正常）' % (diff, faint))

    # 手臂转动轴 = 肩点（手臂与身体相连处：手臂中下部的最右一撮）
    ays = [y for (x, y) in parts['arm']]
    if ays:
        lo = min(ays) + (max(ays) - min(ays)) * 0.4
        lower = [(x, y) for (x, y) in parts['arm'] if y >= lo]
        x_piv = max(x for (x, y) in lower)
        edge = [y for (x, y) in lower if x >= x_piv - 12]
        pivot = (float(x_piv - 4), float(sum(edge) / len(edge)))
    else:
        pivot = (0.0, 0.0)
    # 头部转动轴 = 脖子中点
    hx = [x for (x, y) in parts['head'] if y > cut['head_y'] - 6] or [0]
    neck = (sum(hx) / len(hx), cut['head_y'])

    cw, ch = lay['canvas']
    origins = dict(head=(neck[0] / cw * 100, neck[1] / ch * 100),
                   arm=(pivot[0] / cw * 100, pivot[1] / ch * 100))
    print('CSS： .de-l-head { transform-origin:%.2f%% %.2f%%; }   /* 脖子 %s */'
          % (origins['head'] + (tuple(round(v) for v in neck),)))
    print('CSS： .de-l-arm  { transform-origin:%.2f%% %.2f%%; }   /* 肩点 %s */'
          % (origins['arm'] + (tuple(round(v) for v in pivot),)))

    if dry:
        print('（--dry 只校验，未写文件）')
        return dict(box=lay['box'], origins=origins, canvas=lay['canvas'],
                    prefix=cfg['prefix'], size=lay['size'], pos=lay['pos'])

    # 写文件时用「膨胀 1px」的 mask（相邻层边缘互相压住，缩放后没有发丝缝）
    out_imgs = {n: to_image(canvas, dilate(parts[n], cw, ch)) for n in ('body', 'head', 'tab', 'arm')}
    out_imgs['wave_arm'] = out_imgs['arm']
    prefix = cfg['prefix']
    for n in LAYERS:
        out = os.path.join(MEDIA, os.path.basename(prefix) + n + '.webp')
        out_imgs[n].save(out, 'WEBP', quality=92, alpha_quality=100, method=6)
        print('  写出 %-26s %6.1f KB  %s' % (os.path.basename(out), os.path.getsize(out) / 1024, out_imgs[n].size))
    return dict(box=lay['box'], origins=origins, canvas=lay['canvas'],
                prefix=prefix, size=lay['size'], pos=lay['pos'])


def main():
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass
    dry = '--dry' in sys.argv
    args = [a for a in sys.argv[1:] if not a.startswith('-')]
    keys = [a for a in args if a in FACES] or list(FACES)

    layout = {}
    for k in keys:
        info = do_face(k, dry)
        if info:
            layout[k] = info

    if not dry:
        old = {}
        if os.path.exists(LAYOUT_JSON):
            try:
                old = json.load(open(LAYOUT_JSON, encoding='utf-8'))
            except Exception:
                old = {}
        old.update(layout)
        with open(LAYOUT_JSON, 'w', encoding='utf-8') as f:
            json.dump(old, f, ensure_ascii=False, indent=1)
        print('─' * 70)
        print('· 版式已写入 %s（build.py 直接读，不用手抄 CSS 数字）' % os.path.relpath(LAYOUT_JSON, BASE))
    return 0


if __name__ == '__main__':
    sys.exit(main())
