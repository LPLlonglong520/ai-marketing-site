#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
立牌「无人版底图」生成器（消除页头立牌动作重影的关键）

背景
----
页头立牌 = 底图 + 叠在上面的可点击角色分层（media/de_char*.webp）。
如果底图里已经烘焙了人物，那么分层做任何位移/旋转时，底图里那个"不会动的人物"
就留在原地 → 用户看到的"重影"（打招呼挥手时多出一只手、转身时整个人变成两个）。

本脚本用立牌源目录的 poster.html 重新渲一张 **隐藏人物 <img>** 的底图：

    <源目录>/<源图名>-无人版.png

底图从此"没有人"，人物只由可动分层提供 → 任何动作都不会重影。

两块立牌都要出无人版（页头正面 / 翻过去的背面），否则翻到背面一样会重影。

用法
----
    python tools/mkplate.py            # 两块都出（hero + back）
    python tools/mkplate.py hero       # 只出页头正面
    python tools/mkplate.py back       # 只出背面
    python tools/mkplate.py hero <目录>  # 直接指定立牌目录（覆盖 content.md）

源图路径取自 content.md `### 立牌素材源` 的「页头立牌源图 / 背面立牌源图」。
"""
import os
import re
import shutil
import subprocess
import sys
import tempfile

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONTENT = os.path.join(BASE, 'content.md')

PAGE_W, PAGE_H = 2100, 2680          # 与 立牌/refresh.py 一致
PLATE_SUFFIX = '-无人版'
CHAR_TAG_RE = re.compile(r'<img\s+src="assets/character_standee\.png"[^>]*>')

# 两块立牌的源图字段名（都在 content.md 的 `### 立牌素材源` 里）
TARGETS = {
    'hero': dict(label='页头正面立牌', src_key='页头立牌源图',
                 default_src=(r'C:\Users\龙仔\WorkBuddy\2026-09-20-14-29-28\立牌\小秘场景版女'
                              r'\营销AI小秘-场景版立牌（人物站立中间）.png')),
    'back': dict(label='背面立牌', src_key='背面立牌源图',
                 default_src=(r'C:\Users\龙仔\WorkBuddy\2026-09-20-14-29-28\立牌\小秘现有版女'
                              r'\营销AI小秘-场景能力立牌.png')),
}

CHROME_CANDIDATES = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
]

HIDE_CSS = ('<style id="mkplate">'
            'img[src="assets/character_standee.png"]{display:none !important}'
            '</style>')


def source_of(src_key, default_src):
    """content.md `### 立牌素材源` 里的源图路径；没写就用内置默认。"""
    try:
        text = open(CONTENT, encoding='utf-8').read()
    except OSError:
        return default_src
    sec = text.split('### 立牌素材源', 1)
    if len(sec) == 2:
        m = re.search(r'^\|\s*' + re.escape(src_key) + r'\s*\|\s*(.+?)\s*\|\s*$', sec[1], re.M)
        if m and m.group(1).strip() not in ('', '无', '-'):
            return os.path.expanduser(m.group(1).strip())
    return default_src


def find_browser():
    for p in CHROME_CANDIDATES:
        if os.path.exists(p):
            return p
    raise SystemExit('× 找不到 Chrome / Edge')


def plate_path(source):
    """无人版底图的输出路径：与源图同目录、同主名 + `-无人版.png`。"""
    d, f = os.path.split(source)
    stem = os.path.splitext(f)[0]
    if stem.endswith(PLATE_SUFFIX):
        return source                      # 传进来的已经是无人版，直接用
    return os.path.join(d, stem + PLATE_SUFFIX + '.png')


def render_plate(source, out):
    """用源图所在目录的 poster.html 重渲一张隐藏人物的底图。"""
    d = os.path.dirname(source)
    poster = os.path.join(d, 'poster.html')
    if not os.path.exists(poster):
        raise SystemExit('× 找不到海报模板：%s' % poster)

    html = open(poster, encoding='utf-8').read()
    if not CHAR_TAG_RE.search(html):
        raise SystemExit('× poster.html 里找不到人物 <img>（模板结构变了？）')
    html = html.replace('</head>', HIDE_CSS + '</head>', 1)

    tmp_dir = tempfile.mkdtemp(prefix='mkplate-')
    # 模板里的 assets/ 是相对路径，临时文件必须放在源目录旁边才能取到图
    tmp_html = os.path.join(d, '_plate_tmp.html')
    open(tmp_html, 'w', encoding='utf-8').write(html)

    profile = tempfile.mkdtemp(prefix='plate-profile-')
    try:
        cmd = [find_browser(), '--headless=new', '--disable-gpu', '--no-sandbox',
               '--hide-scrollbars', '--allow-file-access-from-files',
               '--virtual-time-budget=8000', '--user-data-dir=' + profile,
               '--force-device-scale-factor=2', '--window-size=%d,%d' % (PAGE_W, PAGE_H),
               '--screenshot=' + out,
               'file:///' + tmp_html.replace('\\', '/')]
        subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    finally:
        shutil.rmtree(profile, ignore_errors=True)
        for p in (tmp_html,):
            if os.path.exists(p):
                os.remove(p)
        shutil.rmtree(tmp_dir, ignore_errors=True)

    if not os.path.exists(out):
        raise SystemExit('× 出图失败：%s' % out)


def main():
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

    args = [a for a in sys.argv[1:] if not a.startswith('-')]
    which = args[0].lower() if args and args[0] in TARGETS else 'all'
    override_dir = args[1] if (args and args[0] in TARGETS and len(args) > 1) else (
        args[0] if (args and args[0] not in TARGETS) else None)

    keys = list(TARGETS) if which == 'all' else [which]
    for k in keys:
        cfg = TARGETS[k]
        if override_dir:
            # 直接指定目录：取目录里第一张非无人版的海报 PNG
            import glob
            cands = [p for p in glob.glob(os.path.join(override_dir, '*.png'))
                     if not os.path.basename(p).endswith(PLATE_SUFFIX + '.png')]
            if not cands:
                raise SystemExit('× 目录里找不到海报 PNG：%s' % override_dir)
            src = sorted(cands, key=os.path.getsize)[-1]
        else:
            src = source_of(cfg['src_key'], cfg['default_src'])
        if not os.path.exists(src):
            print('· %-10s 源图不存在，跳过：%s' % (cfg['label'], src))
            continue
        out = plate_path(src)
        render_plate(src, out)
        print('· %-10s 无人版底图  %s  %.1f MB'
              % (cfg['label'], out, os.path.getsize(out) / 1024 / 1024))
    return 0


if __name__ == '__main__':
    sys.exit(main())
