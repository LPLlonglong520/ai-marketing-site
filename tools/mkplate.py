#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
立牌「无人版底图」生成器（消除页头立牌动作重影的关键）

背景
----
页头立牌 = 底图 + 叠在上面的可点击角色分层（media/de_char_*.webp）。
如果底图里已经烘焙了人物，那么分层做任何位移/旋转时，底图里那个"不会动的人物"
就留在原地 → 用户看到的"重影"（打招呼挥手时多出一只手、转身时整个人变成两个）。

本脚本用立牌源目录的 poster.html 重新渲一张 **隐藏人物 <img>** 的底图：

    <源目录>/营销AI小秘-场景能力立牌-无人版.png

底图从此"没有人"，人物只由可动分层提供 → 任何动作都不会重影。

用法
----
    python tools/mkplate.py            # 读 content.md 的「页头立牌源图」所在目录
    python tools/mkplate.py <目录>      # 指定立牌目录
"""
import os
import re
import shutil
import subprocess
import sys
import tempfile

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONTENT = os.path.join(BASE, 'content.md')

PLATE_NAME = '营销AI小秘-场景能力立牌-无人版.png'
PAGE_W, PAGE_H = 2100, 2680          # 与 立牌/refresh.py 一致
CHAR_TAG_RE = re.compile(r'<img\s+src="assets/character_standee\.png"[^>]*>')

CHROME_CANDIDATES = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
]

HIDE_CSS = ('<style id="mkplate">'
            'img[src="assets/character_standee.png"]{display:none !important}'
            '</style>')


def board_dir_from_content():
    text = open(CONTENT, encoding='utf-8').read()
    m = re.search(r'^\|\s*(?:页头立牌底图|页头立牌源图)\s*\|\s*(.+?)\s*\|\s*$', text, re.M)
    if not m:
        raise SystemExit('× content.md 里找不到「页头立牌源图」')
    return os.path.dirname(m.group(1).strip())


def find_browser():
    for p in CHROME_CANDIDATES:
        if os.path.exists(p):
            return p
    raise SystemExit('× 找不到 Chrome / Edge')


def main():
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

    d = sys.argv[1] if len(sys.argv) > 1 and not sys.argv[1].startswith('-') else board_dir_from_content()
    poster = os.path.join(d, 'poster.html')
    out = os.path.join(d, PLATE_NAME)
    if not os.path.exists(poster):
        raise SystemExit('× 找不到海报模板：%s' % poster)

    html = open(poster, encoding='utf-8').read()
    if not CHAR_TAG_RE.search(html):
        raise SystemExit('× poster.html 里找不到人物 <img>（模板结构变了？）')
    html = html.replace('</head>', HIDE_CSS + '</head>', 1)

    tmp_dir = tempfile.mkdtemp(prefix='mkplate-')
    tmp_html = os.path.join(tmp_dir, 'plate.html')
    # 模板里的 assets/ 是相对路径，把临时文件放在源目录旁边才能取到图
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
        raise SystemExit('× 出图失败')
    print('· 无人版底图  %s  %.1f MB' % (out, os.path.getsize(out) / 1024 / 1024))
    return 0


if __name__ == '__main__':
    sys.exit(main())
