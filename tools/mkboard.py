# -*- coding: utf-8 -*-
"""立牌图片资产生成器 —— 从源 PNG 生成网站要用的多档位图片。

用法（在项目根目录执行）：
    python tools/mkboard.py            # 两张立牌都刷新
    python tools/mkboard.py hero       # 只刷页头「营销AI小秘」立牌
    python tools/mkboard.py eco        # 只刷生态板块「渠道数字员工」立牌

每张立牌输出 4 档 × 2 种格式（都放在媒体目录）：

    档位        文件名后缀    宽度            用途
    ----------  ------------  --------------  --------------------------------
    移动端 2x   _m            640 / 720       手机（iOS/Android）高清屏
    普通屏 1x   _1x           显示宽度         桌面普通屏（DPR=1）
    高清屏 2x   无后缀         显示宽度 × 2     桌面高清屏（DPR=2）
    放大图      _zoom         2000            点「放大查看」时弹的大图

    WebP：所有浏览器都能用（兜底）
    AVIF：同画质体积约为 WebP 的 45%~55%（Chrome/Edge/Firefox/Safari 现代版全支持）

另外会写两个辅助文件：
    {name}_variants.json  各档位真实像素宽高 + 源图路径，`build.py` 读它拼 srcset
    {name}_lqip.txt       22px 模糊占位图的 data URI，主图到达前先铺一层轮廓

源图路径、显示宽度都来自 `content.md`：
    `### 立牌素材源` 里的「页头立牌源图 / 生态立牌源图」
    `立牌显示宽度`（页头那节 / 生态板块那节各一个）
"""
import base64
import io
import json
import os
import re
import shutil
import subprocess
import sys

from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MEDIA = os.path.join(ROOT, 'media')
CONTENT = os.path.join(ROOT, 'content.md')
TMP = os.path.join(ROOT, '.workbuddy', '_trash')

# 本机 ffmpeg（含 libsvtav1，用于 AVIF 编码）。换机器时改这里，或设环境变量 FFMPEG。
FFMPEG = os.environ.get('FFMPEG') or (
    r'C:\Users\龙仔\AppData\Local\Microsoft\WinGet\Packages'
    r'\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe'
    r'\ffmpeg-9.0.1-full_build\bin\ffmpeg.exe'
)

BOARDS = {
    'hero': {
        'name': 'de_board_front',
        'label': '页头 · 营销AI小秘立牌',
        'm': 640,           # 移动端 2x（手机显示宽度约 320px × 2）
        'zoom': 2000,
        'src_key': '页头立牌源图',
        'width_anchor': None,          # 取第一处「立牌显示宽度」
        'default_src': (r'C:\Users\龙仔\WorkBuddy\2026-09-20-14-29-28\立牌\小秘现有版男'
                        r'\营销AI小秘-场景能力立牌.png'),
    },
    'eco': {
        'name': 'eco_board',
        'label': '生态板块 · 渠道数字员工立牌',
        'm': 720,           # 移动端 2x（手机显示宽度约 92vw ≈ 360px × 2）
        'zoom': 2000,
        'src_key': '生态立牌源图',
        'width_anchor': '### 生态板块',   # 取该节之后的「立牌显示宽度」
        'default_src': (r'C:\Users\龙仔\WorkBuddy\2026-09-20-14-29-28\立牌\渠道男'
                        r'\渠道数字员工-能力立牌.png'),
    },
}

# 档位 → (文件名后缀, 质量参数)：WebP 质量 / AVIF CRF（越小越清晰、越大越小）
PLAN = (
    ('_m', 86, 32),
    ('_1x', 88, 30),
    ('', 88, 30),
    ('_zoom', 90, 28),
)


def read_content():
    with io.open(CONTENT, encoding='utf-8') as f:
        return f.read()


def _table_value(text, key):
    m = re.search(r'^\|\s*' + re.escape(key) + r'\s*\|\s*(.+?)\s*\|\s*$', text, re.M)
    return m.group(1).strip() if m else ''


def resolve_source(text, cfg):
    """源图路径：content.md「### 立牌素材源」优先，其次内置默认。"""
    sec = text.split('### 立牌素材源', 1)
    if len(sec) == 2:
        v = _table_value(sec[1], cfg['src_key'])
        if v and v not in ('无', '-'):
            return os.path.expanduser(v)
    return cfg['default_src']


def section_of(text, heading):
    """切出 `### 标题` 这一节（到下一个 ## / ### 标题为止），避免串到别节的同名字段。"""
    m = re.search(r'^' + re.escape(heading) + r'\s*$', text, re.M)
    if not m:
        return ''
    nxt = re.search(r'^#{2,3} \S', text[m.end():], re.M)
    return text[m.end(): m.end() + nxt.start()] if nxt else text[m.end():]


def resolve_width(text, cfg):
    """显示宽度：页头（`### 页头…` 节内）与生态（`### 生态板块` 节内）各取自己那节。"""
    anchor = cfg['width_anchor']
    seg = section_of(text, anchor) if anchor else text
    v = _table_value(seg, '立牌显示宽度')
    v = re.sub(r'[^\d.]', '', v)
    try:
        return int(float(v)) or (560 if cfg['name'] == 'de_board_front' else 520)
    except Exception:
        return 560 if cfg['name'] == 'de_board_front' else 520


def enc_avif(png_path, out_path, crf, preset=7):
    """用 ffmpeg（libsvtav1）编码单帧 AVIF。"""
    cmd = [FFMPEG, '-y', '-loglevel', 'error', '-i', png_path,
           '-c:v', 'libsvtav1', '-preset', str(preset), '-crf', str(crf),
           '-still-picture', '1', out_path]
    subprocess.run(cmd, check=True)


def build(key):
    cfg = BOARDS[key]
    text = read_content()
    src = resolve_source(text, cfg)
    if not os.path.exists(src):
        print('  源图不存在，跳过：%s' % src)
        return None
    disp = resolve_width(text, cfg)
    name = cfg['name']
    if not os.path.isdir(TMP):
        os.makedirs(TMP)

    im = Image.open(src).convert('RGB')
    print('  %s\n    源图 %s  %s' % (cfg['label'], im.size, src))

    variants = {}
    report = []
    for tag, wq, crf in PLAN:
        w = disp if tag == '_1x' else (disp * 2 if tag == '' else (cfg['m'] if tag == '_m' else cfg['zoom']))
        h = int(round(w * im.size[1] / im.size[0]))
        small = im.resize((w, h), Image.LANCZOS)
        png = os.path.join(TMP, '_mk_%s%s.png' % (name, tag or '_2x'))
        small.save(png)

        wp = os.path.join(MEDIA, '%s%s.webp' % (name, tag))
        small.save(wp, 'WEBP', quality=wq, method=6)
        ap = os.path.join(MEDIA, '%s%s.avif' % (name, tag))
        try:
            enc_avif(png, ap, crf)
        except Exception as e:
            print('    AVIF 编码失败（%s），跳过：%s' % (tag or '2x', e))
            ap = None
        try:
            os.remove(png)
        except OSError:
            pass

        variants[tag] = {'w': w, 'h': h}
        report.append((tag or '2x', w, h, os.path.getsize(wp),
                       os.path.getsize(ap) if ap else 0))

    # LQIP：22px 宽的小图内联成 data URI（不占请求）
    lw = 22
    lh = max(1, int(round(lw * im.size[1] / im.size[0])))
    buf = io.BytesIO()
    im.resize((lw, lh), Image.LANCZOS).save(buf, 'WEBP', quality=62, method=6)
    lqip = 'data:image/webp;base64,' + base64.b64encode(buf.getvalue()).decode('ascii')
    with io.open(os.path.join(MEDIA, name + '_lqip.txt'), 'w', encoding='ascii') as f:
        f.write(lqip)

    with io.open(os.path.join(MEDIA, name + '_variants.json'), 'w', encoding='utf-8') as f:
        json.dump({'name': name, 'display': disp, 'source': src,
                   'variants': variants}, f, ensure_ascii=False, indent=1)

    print('    档位     宽×高              WebP        AVIF')
    tot_w = tot_a = 0
    for tag, w, h, sw, sa in report:
        print('    %-8s %-18s %8.1fKB %8.1fKB' % (tag, '%d × %d' % (w, h), sw / 1024, sa / 1024))
        if tag in ('_m', '_1x', ''):
            tot_w += sw
            tot_a += sa
    print('    首屏合计（不含放大图） WebP %.1fKB → AVIF %.1fKB' % (tot_w / 1024, tot_a / 1024))
    return variants


def main():
    which = (sys.argv[1] if len(sys.argv) > 1 else 'all').lower()
    keys = list(BOARDS) if which == 'all' else [which]
    if not os.path.isdir(TMP):
        os.makedirs(TMP)
    print('源图路径可写在 content.md 的「### 立牌素材源」（缺省用脚本内置默认值）')
    for k in keys:
        if k not in BOARDS:
            print('未知目标：%s（可选 hero / eco / all）' % k)
            continue
        build(k)
    print('完成。')


if __name__ == '__main__':
    main()
