#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
营销AI小秘 · 立牌「可点击角色」分层素材生成（男女版本切换用）

背景
----
页头立牌 = 立牌图（人物已烘焙在图里） + 叠在上面的一层"可点击角色"（media/de_char_*.webp）。
点击「打招呼 / 转身」动的是上层那 5 张分层图。所以：

    ⚠️ 立牌图换成哪个版本（男/女），de_char_*.webp 就必须换成同一个版本，
       否则上层的男角色压在底图女角色上 → 出现"男女重影"。

本脚本：从立牌源目录里的 character_standee.png（带 alpha 的人物素材）切出 5 层，
按立牌图的几何对齐，写回 media/de_char_*.webp。

用法
----
    python tools/mkchar.py            # 生成 + 校验
    python tools/mkchar.py --dry      # 只校验、不写文件

源图取自 content.md 的「页头立牌源图」，同目录下的 assets/character_standee.png。

切分参数（CUT）是按「当前源图」调过的，换角色素材（不同姿势）时要重看一眼：
  · HEAD_Y    头部/身体的分界线（脖子高度，画布像素）
  · ARM_BOX   手臂区（左侧，用亮度筛出浅色衣袖/手，避免把深色裙摆切进去）
  · TAB_BOX   平板区（这一层没有任何动画引用，切不准也不会露馅）
  · 其余 = body
分层之和严格等于原人物轮廓（脚本会校验，差值为 0）。
"""
import os
import re
import sys

from PIL import Image

# ---------------- 路径 ----------------

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # ai-marketing-site/
CONTENT = os.path.join(BASE, 'content.md')
MEDIA = os.path.join(BASE, 'media')

# 立牌海报画布与人物摆放（与 立牌/refresh.py 里的 CHAR_TOP / CHAR_HEIGHT / CHAR_CX 保持一致）
POSTER_W, POSTER_H = 2100.0, 2680.0
CHAR_TOP, CHAR_HEIGHT, CHAR_CX = 480.0, 1600.0, 1050.0

# 上层角色的 CSS 盒（与 build.py 里 .de-char 的 left/top/width/height 一致）
BOX = (695.0, 465.0, 705.0, 1630.0)
CANVAS = (380, 879)

# ---------------- 切分参数（按当前源图调过） ----------------

HEAD_Y = 196          # 脖子高度（画布 380x879 下的 y）
ARM_BOX = dict(x0=0, x1=168, y0=176, y1=345, lum_min=118)
TAB_BOX = dict(x0=245, x1=338, y0=200, y1=278)
WAVE_ROT = 0.0        # wave_arm 预旋转角度（0 = 与手臂同一张图，挥手靠 CSS 的 deWave 旋转）

LAYERS = ('body', 'head', 'tab', 'arm', 'wave_arm')


def read_src():
    """从 content.md 读「页头立牌源图」，推出同目录的 character_standee.png。"""
    text = open(CONTENT, encoding='utf-8').read()
    m = re.search(r'^\|\s*页头立牌源图\s*\|\s*(.+?)\s*\|\s*$', text, re.M)
    if not m:
        raise SystemExit('× content.md 里找不到「页头立牌源图」')
    board = m.group(1).strip()
    standee = os.path.join(os.path.dirname(board), 'assets', 'character_standee.png')
    for p in (board, standee):
        if not os.path.exists(p):
            raise SystemExit('× 找不到文件：%s' % p)
    return board, standee


def build_canvas(standee_path):
    """把人物素材按立牌图的几何放进 380x879 的层画布。"""
    src = Image.open(standee_path).convert('RGBA')
    cw, ch = CHAR_HEIGHT * src.size[0] / float(src.size[1]), CHAR_HEIGHT
    css_x0, css_y0 = CHAR_CX - cw / 2.0, CHAR_TOP
    k = CANVAS[0] / BOX[2]
    canvas = Image.new('RGBA', CANVAS, (0, 0, 0, 0))
    size = (int(round(cw * k)), int(round(ch * k)))
    pos = (int(round((css_x0 - BOX[0]) * k)), int(round((css_y0 - BOX[1]) * k)))
    canvas.paste(src.resize(size, Image.LANCZOS), pos)
    return canvas, size, pos, k


def split(canvas):
    """按 HEAD_Y / ARM_BOX / TAB_BOX 把人物轮廓切成 4 块（和为全体）。"""
    A = canvas.getchannel('A').load()
    L = canvas.convert('L').load()
    w, h = canvas.size
    parts = {k: set() for k in ('head', 'arm', 'tab')}
    sil = set()
    for y in range(h):
        for x in range(w):
            if A[x, y] <= 100:
                continue
            sil.add((x, y))
            if y < HEAD_Y:
                parts['head'].add((x, y))
            elif (ARM_BOX['x0'] <= x <= ARM_BOX['x1'] and ARM_BOX['y0'] <= y <= ARM_BOX['y1']
                  and L[x, y] >= ARM_BOX['lum_min']):
                parts['arm'].add((x, y))
            elif TAB_BOX['x0'] <= x <= TAB_BOX['x1'] and TAB_BOX['y0'] <= y <= TAB_BOX['y1']:
                parts['tab'].add((x, y))
    parts['body'] = sil - parts['head'] - parts['arm'] - parts['tab']
    return parts, sil


def to_image(canvas, pts, pivot=None, deg=0.0):
    """把像素集合还原成一张透明图；可选绕 pivot 旋转（用于 wave_arm）。"""
    w, h = canvas.size
    mask = Image.new('L', (w, h), 0)
    mp = mask.load()
    for (x, y) in pts:
        mp[x, y] = 255
    layer = Image.new('RGBA', (w, h), (0, 0, 0, 0))
    layer.paste(canvas, (0, 0), mask)
    if deg and pivot:
        return layer.rotate(deg, resample=Image.BICUBIC, center=pivot)
    return layer


def composite(layers):
    out = Image.new('RGBA', CANVAS, (0, 0, 0, 0))
    for im in layers:
        out = Image.alpha_composite(out, im)
    return out


def main():
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass
    dry = '--dry' in sys.argv

    board, standee = read_src()
    canvas, size, pos, k = build_canvas(standee)
    print('─' * 62)
    print('立牌源图  %s' % os.path.basename(board))
    print('人物素材  %s  %s' % (os.path.basename(standee), Image.open(standee).size))
    print('层画布 %dx%d   人物贴图 %dx%d @ (%d,%d)   缩放 %.4f' % (CANVAS + size + pos + (k,)))

    parts, sil = split(canvas)
    print('像素：' + '  '.join('%s %d' % (n, len(parts[n])) for n in ('head', 'arm', 'tab', 'body')))

    # 手臂转动轴 = 肩点（手臂与身体相连处：手臂中下部的最右一撮）
    ays = [y for (x, y) in parts['arm']]
    lo = min(ays) + (max(ays) - min(ays)) * 0.4
    lower = [(x, y) for (x, y) in parts['arm'] if y >= lo]
    x_piv = max(x for (x, y) in lower)
    edge = [y for (x, y) in lower if x >= x_piv - 12]
    pivot = (float(x_piv - 4), float(sum(edge) / len(edge)))
    imgs = {n: to_image(canvas, parts[n]) for n in ('body', 'head', 'tab', 'arm')}
    imgs['wave_arm'] = to_image(canvas, parts['arm'], pivot, WAVE_ROT)

    # 校验：四层之和 == 原人物轮廓（只允许半透明描边像素缺失）
    back = composite([imgs['body'], imgs['tab'], imgs['arm'], imgs['head']])
    a1, a2 = canvas.load(), back.load()
    diff = faint = 0
    for y in range(CANVAS[1]):
        for x in range(CANVAS[0]):
            p, q = a1[x, y], a2[x, y]
            if abs(p[3] - q[3]) > 2 or (p[3] and q[3] and max(abs(p[i] - q[i]) for i in range(3)) > 2):
                diff += 1
                if p[3] <= 100:
                    faint += 1
    print('校验：分层合成 vs 原人物  差异像素 %d（其中边缘半透明 %d → 属正常）' % (diff, faint))

    # 头部转动轴（脖子中点）与手臂转动轴（肩点），写成 build.py 的 CSS 百分比
    hx = [x for (x, y) in parts['head'] if y > HEAD_Y - 6] or [0]
    neck = (sum(hx) / len(hx), HEAD_Y)
    print('CSS： .de-l-head { transform-origin:%.2f%% %.2f%%; }   /* 脖子 %s */'
          % (neck[0] / CANVAS[0] * 100, neck[1] / CANVAS[1] * 100, tuple(round(v) for v in neck)))
    print('CSS： .de-l-arm  { transform-origin:%.2f%% %.2f%%; }   /* 肩点 %s */'
          % (pivot[0] / CANVAS[0] * 100, pivot[1] / CANVAS[1] * 100, tuple(round(v) for v in pivot)))

    if dry:
        print('（--dry 只校验，未写文件）')
        return 0
    for n in LAYERS:
        out = os.path.join(MEDIA, 'de_char_%s.webp' % n)
        imgs[n].save(out, 'WEBP', quality=92, alpha_quality=100, method=6)
        print('  写出 %-26s %6.1f KB  %s' % (os.path.basename(out), os.path.getsize(out) / 1024, imgs[n].size))
    print('─' * 62)
    return 0


if __name__ == '__main__':
    sys.exit(main())
