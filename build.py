#!/usr/bin/env python3
"""
build.py v2 — 从 content.md 生成 index.html
用法: python build.py
修改 content.md 后运行此脚本即可更新网站内容。
"""
import re, os, sys, json
from html import escape as _esc
from urllib.parse import quote

# 切换工作目录 + 强制UTF-8
os.chdir(os.path.dirname(os.path.abspath(__file__)))
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')


def media_path(path, ver=False):
    """Auto-upgrade image paths to .webp if a compressed version exists.

    ver=True 时追加 `?v=<文件 mtime>`：立牌人物分层这类**文件名不变、内容会换**的素材
    必须带版本号，否则浏览器会用旧图盖在新立牌上（男女重影就是这么来的）。
    """
    if not path:
        return path
    # 自动补 media/ 前缀
    if not path.startswith('media/'):
        path = 'media/' + path
    full = os.path.join(os.path.dirname(os.path.abspath(__file__)), path)
    base, ext = os.path.splitext(path)
    if ext.lower() in ('.png', '.jpeg', '.jpg'):
        webp_path = base + '.webp'
        webp_full = os.path.join(os.path.dirname(os.path.abspath(__file__)), webp_path)
        if os.path.exists(webp_full):
            path, full = webp_path, webp_full
    if ver:
        try:
            path += '?v=%d' % int(os.path.getmtime(full))
        except OSError:
            pass
    return path


def _h2_at(text, name):
    """定位**整行独立**的二级标题 `^## name$`。

    ⚠️ 不要退化成 text.find('## xxx')：content.md 顶部「改哪里速查」表里也会
    出现 `## 激励模块` 这类行内引用，find 会命中那里，导致后面切出来的整段是空的。
    """
    m = re.search(r'(?m)^## ' + re.escape(name) + r'\s*$', text)
    return m.start() if m else -1


def _img_size(path):
    """读 PNG / WebP 的像素尺寸 (w, h)，纯标准库实现；读不到返回 None。

    用来给立牌这类「换张图就可能换比例」的元素算真实宽高比，
    避免把比例写死在 CSS 里（换图就变形）。
    """
    try:
        with open(path, 'rb') as f:
            head = f.read(32)
        if head[:8] == b'\x89PNG\r\n\x1a\n':
            return (int.from_bytes(head[16:20], 'big'),
                    int.from_bytes(head[20:24], 'big'))
        if head[:4] == b'RIFF' and head[8:12] == b'WEBP':
            fmt = head[12:16]
            if fmt == b'VP8X':                      # 扩展格式（带 alpha / 动画）
                return (int.from_bytes(head[24:27], 'little') + 1,
                        int.from_bytes(head[27:30], 'little') + 1)
            if fmt == b'VP8 ':                      # 有损
                return (int.from_bytes(head[26:28], 'little') & 0x3fff,
                        int.from_bytes(head[28:30], 'little') & 0x3fff)
            if fmt == b'VP8L':                      # 无损
                b = int.from_bytes(head[21:25], 'little')
                return ((b & 0x3fff) + 1, ((b >> 14) & 0x3fff) + 1)
    except Exception:
        pass
    return None


def _read_text_asset(path):
    """读纯文本资产（如 LQIP 的 data URI）；没有就返回空串。"""
    try:
        with open(path, encoding='ascii') as f:
            return f.read().strip()
    except Exception:
        return ''


def _board_manifest(name):
    """读 tools/mkboard.py 写出的立牌档位清单（没有就返回 None，退回单张图方案）。"""
    try:
        with open(media_path(name + '_variants.json'), encoding='utf-8') as f:
            m = json.load(f)
        return m if m.get('variants') else None
    except Exception:
        return None


def board_picture(name, alt, sizes, priority=False, lazy=False, cls='de-img'):
    """生成立牌 <picture>（AVIF 优先 / WebP 兜底 / 多档 srcset）+ 对应的预加载标签。

    AVIF 用 AV1 帧内压缩，同画质体积约 WebP 的 55%（实测 144KB → 65KB），
    且移动端能命中更小的 _m 档（手机 DPR2 只下 640w，不再下 1120w）。
    返回 (html, preload_html, 宽, 高)。
    """
    m = _board_manifest(name)
    if not m:
        p = media_path(name + '_1x.webp')
        if not os.path.exists(p):
            p = media_path(name + '.webp')
        sz = _img_size(p) or (0, 0)
        dim = ' width="%d" height="%d"' % sz if sz[0] else ''
        attr = 'fetchpriority="high"' if priority else ('loading="lazy"' if lazy else '')
        img = '<img class="%s" src="%s"%s alt="%s" decoding="async" %s>' % (cls, p, dim, alt, attr)
        return img, ('<link rel="preload" as="image" href="%s" fetchpriority="high">\n' % p
                     if priority else ''), sz[0], sz[1]

    v = m['variants']

    def srcset(ext):
        out = []
        for tag in ('_m', '_1x', ''):
            if tag not in v:
                continue
            f = media_path('%s%s.%s' % (name, tag, ext))
            if os.path.exists(f):
                out.append('%s %dw' % (f, v[tag]['w']))
        return ', '.join(out)

    avif, webp = srcset('avif'), srcset('webp')
    base = media_path(name + '_1x.webp')
    if not os.path.exists(base):
        base = media_path(name + '_1x.avif')
    size_1x = v.get('_1x') or v.get('') or {'w': 0, 'h': 0}
    dim = ' width="%d" height="%d"' % (size_1x['w'], size_1x['h']) if size_1x['w'] else ''
    attr = 'fetchpriority="high"' if priority else ('loading="lazy"' if lazy else '')
    img = ('<img class="%s" src="%s" srcset="%s" sizes="%s"%s alt="%s" decoding="async" %s>'
           % (cls, base, webp, sizes, dim, alt, attr))
    html = img
    if avif:
        html = ('<picture><source type="image/avif" srcset="%s" sizes="%s">%s</picture>'
                % (avif, sizes, img))
    preload = ''
    if priority:
        if avif:
            preload = ('<link rel="preload" as="image" type="image/avif" href="%s" '
                       'imagesrcset="%s" imagesizes="%s" fetchpriority="high">\n'
                       % (media_path(name + '_1x.avif'), avif, sizes))
        else:
            preload = ('<link rel="preload" as="image" href="%s" imagesrcset="%s" '
                       'imagesizes="%s" fetchpriority="high">\n' % (base, webp, sizes))
    return html, preload, size_1x.get('w', 0), size_1x.get('h', 0)


def board_lightbox(lid, name, alt, label, lqip=''):
    """「点击放大」弹层：先用已缓存的小图瞬间铺满，高清图到达后再渐进替换。

    关键点：`data-src` 挂在 `<img>` 上，首次点开才请求放大图（约 150KB），
    不点就不下载；鼠标悬停 / 手指按下按钮时预热，点开时通常已经就绪。
    两张图同为立牌比例，尺寸一致，替换过程无跳动。
    """
    zoom_avif = media_path(name + '_zoom.avif')
    zoom_webp = media_path(name + '_zoom.webp')
    disp = media_path(name + '_1x.webp')
    avif_attr = ' data-avif="%s"' % zoom_avif if os.path.exists(zoom_avif) else ''
    if not os.path.exists(zoom_webp):
        zoom_webp = media_path(name + '.webp')
    return f'''<div class="de-lb" id="{lid}" data-lb data-base="{disp}"{avif_attr} data-webp="{zoom_webp}">
  <span class="cl" title="关闭">✕</span>
  <div class="de-lb-stage">
    <img class="de-lb-base" alt="" aria-hidden="true">
    <img class="de-lb-hi" alt="{alt}" decoding="async">
  </div>
  <div class="de-lb-tip"><span class="ic">🔍</span> 点图片 1× / 2× 切换 · 点空白处或按 Esc 关闭</div>
</div>'''


def board_zoom_btn(lid, label):
    """立牌下方的「放大查看」按钮。"""
    return ('<div class="de-board-tools"><button class="de-lb-btn" type="button" '
            'data-lb-open="%s"><span class="ic">🔍</span>%s</button></div>' % (lid, label))


def _de_table(block, keys):
    """从 markdown 块中解析 | 字段 | 值 | 表，只保留 keys 中的字段"""
    out = {}
    for line in block.split('\n'):
        m = re.match(r'\|\s*(.+?)\s*\|\s*(.*?)\s*\|\s*$', line)
        if not m:
            continue
        k = m.group(1).strip()
        if k in keys and k not in ('字段', ''):
            out[k] = m.group(2).strip()
    return out


def parse_de_page(text):
    """解析 ## 数字员工页 整段配置"""
    start = _h2_at(text, '数字员工页')
    if start < 0:
        return None
    sec = text[start:]

    de = {'raw': sec}

    # ---- 主属性表 ----
    m = re.search(r'## 数字员工页\s*\n\s*((?:\|.+\|\s*\n)+)', sec)
    de['meta'] = _de_table(m.group(1), {
        '浏览器标题', '页头眉标', '页头主标题', '页头主标题链接', '页头主标题提示', '页头副标题',
        '页头副标题字号比', '页头标语', '页头描述',
        'KPI1数值', 'KPI1标签', 'KPI2数值', 'KPI2标签', 'KPI3数值', 'KPI3标签',
        'KPI4数值', 'KPI4标签',
        '立牌正面图', '立牌正面图小图', '立牌全图', '立牌显示宽度', '人物层前缀', '立牌占位图',
        '旋转提示', '翻转按钮', '背回按钮', '放大按钮',
        '返回按钮', '返回链接', '来源参数', '来源返回文字', '页尾标语',
        '能力集列数', '能力集列数断点', '能力集容器宽度', '能力集上间距',
    }) if m else {}

    def sub(name, keys=None, upto=None):
        # 只认整行独立的小节标题（^### xxx$），避免命中正文里 `### xxx` 这样的行内引用
        m = re.search(r'(?m)^### ' + re.escape(name) + r'\s*$', sec)
        if not m:
            return ''
        a = m.start()
        b = len(sec)
        for nxt in re.finditer(r'\n### ', sec[a + 4:]):
            b = a + 4 + nxt.start()
            break
        return sec[a:b]

    # ---- 立牌背面 ----
    blk = sub('立牌背面')
    de['back'] = _de_table(blk, {'背面眉标', '背面主标题', '背面副标题', '背面标语', '背面说明', '背面入口文字', '支架文字'})

    # ---- KPI 明细（悬浮面板）----
    de['kpi_meta'] = {}
    blk = sub('KPI 明细')
    for line in blk.split('\n'):
        if not line.strip().startswith('|'):
            continue
        cells = [c.strip() for c in line.strip().strip('|').split('|')]
        if len(cells) < 3:
            continue
        if cells[0] in ('键', '字段') or set(cells[0]) <= set('-: '):
            continue
        de['kpi_meta'][cells[0]] = {'title': cells[1], 'detail': cells[2]}

    # ---- 立牌控制按钮（放大镜等）----
    de['board_tools'] = []
    blk = sub('立牌控制')
    for line in blk.split('\n'):
        if not line.strip().startswith('|'):
            continue
        cells = [c.strip() for c in line.strip().strip('|').split('|')]
        if len(cells) < 3:
            continue
        if cells[0] in ('动作', '字段', 'id') or set(cells[0]) <= set('-: '):
            continue
        de['board_tools'].append({'id': cells[0], 'btn': cells[1], 'icon': cells[2]})

    # ---- 人物动作 ----
    de['actions'] = []
    blk = sub('人物动作')
    for line in blk.split('\n'):
        m = re.match(r'\|\s*([a-zA-Z][\w-]*)\s*\|\s*(.+?)\s*\|\s*(.+?)\s*\|\s*$', line)
        if m:
            de['actions'].append({'id': m.group(1).strip(), 'btn': m.group(2).strip(), 'say': m.group(3).strip()})

    # ---- 业务流头部 ----
    blk = sub('业务流头部')
    de['flow'] = _de_table(blk, {
        '眉标', '标题', '副标题', '说明', '底部说明', '日常标题', '日常说明', '日常动作', '日常跳转',
        '规划列脚注',
    })

    # ---- 业务流阶段 ----
    de['stages'] = []
    blk = sub('业务流阶段')
    for line in blk.split('\n'):
        m = re.match(r'\|\s*(\d+)\s*\|\s*(.+?)\s*\|\s*(.+?)\s*\|\s*(.+?)\s*\|\s*(.+?)\s*\|\s*(.+?)\s*\|\s*$', line)
        if m:
            de['stages'].append({
                'no': m.group(1).strip(),
                'name': m.group(2).strip(),
                'actions': [a.strip() for a in m.group(3).split(',') if a.strip()],
                'scene': m.group(4).strip(),
                'scene_no': m.group(5).strip(),
                'status': m.group(6).strip(),
            })

    # ---- 场景能力集头部 ----
    blk = sub('场景能力集头部')
    de['cap_head'] = _de_table(blk, {'眉标', '标题', '副标题', '统计', '入口提示'})

    # ---- 生态板块（夹在「跨阶段 · 通用能力」与「激励模块」之间）----
    # 左栏 = 可 180° 拖动的立牌，右栏 = 「卡片名称」指定的那张跨阶段能力卡
    blk = sub('生态板块')
    de['eco'] = _de_table(blk, {
        '标题', '说明', '卡片名称',
        '立牌正面图', '立牌正面图小图', '立牌显示宽度', '立牌占位图', '放大按钮', '旋转提示',
        '背面眉标', '背面主标题', '背面副标题', '背面标语', '背面说明',
        '背面入口文字', '支架文字',
    })

    # ---- 入口链接映射（能力表「入口 / 链接」列 → 跳转地址）----
    de['entry_links'] = {}
    m2 = re.search(r'### 入口链接映射\s*\n(.*?)(?=\n### |\n## |\Z)', sec, re.DOTALL)
    if m2:
        for line in m2.group(1).split('\n'):
            if not line.strip().startswith('|'):
                continue
            cells = [c.strip() for c in line.strip().strip('|').split('|')]
            if len(cells) < 2:
                continue
            if cells[0] in ('入口名称', '字段') or set(cells[0]) <= set('-: '):
                continue
            url = cells[1].strip()
            if url and url not in ('链接', '—', '-'):
                de['entry_links'][cells[0]] = url

    # ---- 场景能力 1..N ----
    de['caps'] = []
    heads = list(re.finditer(r'\n### (场景能力\d+ · .+)\n', sec))
    for i, h in enumerate(heads):
        a = h.start() + 1
        b = heads[i + 1].start() + 1 if i + 1 < len(heads) else len(sec)
        blk = sec[a:b]
        title = h.group(1)
        info = _de_table(blk, {'序号', '名称', '对应阶段', '主题色', '图标', '说明', '状态', '跳转链接', '跳转文字', '宽卡', '应用数量', '场景闭环', '操作路径'})
        if not info.get('名称'):
            nm = re.match(r'场景能力\d+\s*·\s*(.+)', title)
            info['名称'] = nm.group(1).strip() if nm else title
        # 能力行（表头含 skill / 功能）
        rows = []
        for line in blk.split('\n'):
            if not line.strip().startswith('|'):
                continue
            cells = [c.strip() for c in line.strip().strip('|').split('|')]
            if len(cells) < 4:
                continue
            if cells[0] in ('skill / 功能', 'skill/功能', '字段') or set(cells[0]) <= set('-: '):
                continue
            if cells[0] in ('序号', '名称', '对应阶段', '主题色', '图标', '说明', '状态', '跳转链接', '跳转文字', '宽卡', '应用数量', '场景闭环', '操作路径'):
                continue
            rows.append({'skill': cells[0], 'demo': cells[1], 'data': cells[2], 'entry': cells[3]})
        info['rows'] = rows
        de['caps'].append(info)

    # ---- 页尾 ----
    blk = sub('数字员工页尾')
    de['footer'] = _de_table(blk, {'主标题', '副标题', '主按钮文字', '主按钮链接', '次按钮文字', '署名'})

    return de


def parse_content(path):
    with open(path, 'r', encoding='utf-8') as f:
        text = f.read()
    
    data = {'global': {}, 'scenes': [], 'heroes': []}
    
    # ---- 全局信息 ----
    gm = re.search(r'## 全局信息\n\n((?:\|.+\|\n)+)', text)
    if gm:
        for line in gm.group(1).strip().split('\n'):
            m = re.match(r'\|\s*(.+?)\s*\|\s*(.+?)\s*\|', line)
            if m and m.group(1).strip() not in ('字段', ''):
                data['global'][m.group(1).strip()] = m.group(2).strip()
    
    # ---- 漫画角色 ----
    hm = re.search(r'## 漫画角色\n\n((?:\|.+\|\n)+)', text)
    if hm:
        for line in hm.group(1).strip().split('\n'):
            m = re.match(r'\|\s*(.+?)\s*\|\s*(.+?)\s*\|\s*(.+?)\s*\|', line)
            if m and m.group(1).strip() not in ('角色', '') and not m.group(1).startswith('--'):
                data['heroes'].append({
                    'name': m.group(1).strip(),
                    'bubble': m.group(2).strip(),
                    'avatar': m.group(3).strip()
                })
    
    # ---- 点赞评论模块 ----
    feedback = {'title': '👍 觉得有用吗？', 'subtitle': '您的反馈帮助我们持续改进'}
    fm = re.search(r'## 点赞评论模块\n\n((?:\|.+\|\n)+)', text)
    if fm:
        for line in fm.group(1).strip().split('\n'):
            m = re.match(r'\|\s*(标题|副标题)\s*\|\s*(.+?)\s*\|', line)
            if m:
                feedback[m.group(1)] = m.group(2).strip()
    data['feedback'] = feedback
    
    # ---- 未来规划（独立模块）----
    future = {'title': '未来规划', 'subtitle': '统一入口 · 整合资源 · 建设营销AI综合能力平台', 'status': '', 'directions': '', 'plan': ''}
    fp_start = _h2_at(text, '未来规划')
    fp_end = _h2_at(text, '点赞评论模块')
    if fp_start >= 0 and fp_end > fp_start:
        fp_section = text[fp_start:fp_end]
        # 提取属性表
        tbl_match = re.search(r'(\|.+\|\n)+', fp_section)
        if tbl_match:
            for line in tbl_match.group().strip().split('\n'):
                m = re.match(r'\|\s*(标题|副标题)\s*\|\s*(.+?)\s*\|', line)
                if m:
                    future[m.group(1)] = m.group(2).strip()
        # 当前现状
        sm = re.search(r'\*\*当前现状\*\*\s*\n(.*?)(?=\*\*规划方向\*\*)', fp_section, re.DOTALL)
        if sm: future['status'] = sm.group(1).strip()
        # 规划方向
        dm = re.search(r'\*\*规划方向\*\*(.*?)(?=\*\*推进计划\*\*)', fp_section, re.DOTALL)
        if dm: future['directions'] = dm.group(1).strip()
        # 推进计划
        pm = re.search(r'\*\*推进计划\*\*(.*?)(?=---)', fp_section, re.DOTALL)
        if pm: future['plan'] = pm.group(1).strip()
    data['future_plan'] = future
    
    # ---- 激励模块 ----
    inc = {'标题': '积极使用 AI，更有 丰厚激励 等你拿', '副标题': '积极使用AI工具，主动反馈优化建议，甚至自建提效Skill——优秀实践可获月度激励、专项大奖及年度荣誉！', 'cards': []}
    inc_start = _h2_at(text, '激励模块')
    _fut = _h2_at(text, '未来规划')
    inc_end = _fut if _fut > inc_start else len(text)
    if inc_start >= 0 and inc_end > inc_start:
        inc_section = text[inc_start:inc_end]
        # 提取模块标题/副标题
        tbl_match = re.search(r'(\|.+\|\n)+', inc_section[:inc_section.find('### 激励1')] if '### 激励1' in inc_section else inc_section[:200])
        if tbl_match:
            for line in tbl_match.group().strip().split('\n'):
                m = re.match(r'\|\s*(标题|副标题)\s*\|\s*(.+?)\s*\|', line)
                if m:
                    inc[m.group(1)] = m.group(2).strip()
        # 提取各激励卡片
        inc_card_blocks = re.split(r'\n### 激励\d+ · .+\n', inc_section)
        inc_card_headers = re.findall(r'### 激励(\d+) · (.+)\n', inc_section)
        for ci, (cid, cname) in enumerate(inc_card_headers):
            cb = inc_card_blocks[ci + 1] if ci + 1 < len(inc_card_blocks) else ''
            card = {'glow': 'gold', 'icon': '', 'title': cname.strip(), 'en': '', 'desc': '', 'stats': [], 'tags': [], 'link': '#', 'link_text': '敬请期待'}
            # 中英文字段映射
            field_map = {'光晕': 'glow', '图标': 'icon', '标题': 'title', '英文': 'en', '描述': 'desc', '链接': 'link', '链接文字': 'link_text'}
            # 属性表
            for line in cb.split('\n'):
                m = re.match(r'\|\s*(光晕|图标|标题|英文|描述|链接|链接文字)\s*\|\s*(.+?)\s*\|', line)
                if m:
                    key = field_map.get(m.group(1), m.group(1))
                    card[key] = m.group(2).strip()
            # 重点词
            kw_match = re.search(r'\*\*重点词\*\*\s*\n\n((?:\|.+\|\n)+)', cb)
            if kw_match:
                nums = []
                labels = []
                for line in kw_match.group(1).strip().split('\n'):
                    m = re.match(r'\|\s*(.+?)\s*\|\s*(.+?)\s*\|', line)
                    if m and m.group(1).strip() not in ('数字', '') and not m.group(1).strip().startswith('--'):
                        nums.append(m.group(1).strip())
                        labels.append(m.group(2).strip())
                card['stats'] = list(zip(nums, labels))
            # 标签
            tags_match = re.search(r'\*\*标签\*\*\s*\n\n(.+)', cb)
            if tags_match:
                card['tags'] = [t.strip() for t in tags_match.group(1).strip().split('、') if t.strip()]
            inc['cards'].append(card)
    data['incentive'] = inc
    
    # ---- 场景拆分 ----
    scene_blocks = re.split(r'\n## 场景\d+ · .+\n', text)
    scene_headers = re.findall(r'## 场景(\d+) · (.+)\n', text)
    
    for idx, (snum_str, sname) in enumerate(scene_headers):
        snum = int(snum_str)
        block = scene_blocks[idx + 1] if idx + 1 < len(scene_blocks) else ''
        # 截掉未来规划、点赞评论模块和漫画角色，避免串到场景解析中
        tail = re.search(r'\n## (?:激励模块|未来规划|点赞评论模块|漫画角色)', block)
        if tail:
            block = block[:tail.start()]
        
        scene = {
            'num': snum,
            'name': sname.strip(),
            'title': sname.strip(),
            'subtitle': '',
            'apps': [],
            'stats': []
        }
        
        # 场景属性表（只读到第一个 ### 之前）
        scene_table_end = block.find('\n###')
        scene_table = block[:scene_table_end] if scene_table_end != -1 else block
        for line in scene_table.split('\n'):
            m = re.match(r'\|\s*(图标|标题|副标题)\s*\|\s*(.+?)\s*\|', line)
            if m:
                scene[m.group(1)] = m.group(2).strip()
        
        if '标题' in scene:
            scene['title'] = scene['标题']
        if '副标题' in scene:
            scene['subtitle'] = scene['副标题']
        if '图标' in scene:
            scene['icon'] = scene['图标']
        
        # 数据展示
        data_block = re.search(r'### 数据展示\n\n((?:\|.+\|\n)+)', block)
        if data_block:
            nums = re.findall(r'\|\s*数据\d+数值\s*\|\s*(.+?)\s*\|', data_block.group(1))
            labels = re.findall(r'\|\s*数据\d+标签\s*\|\s*(.+?)\s*\|', data_block.group(1))
            scene['stats'] = [{'num': n, 'label': l} for n, l in zip(nums, labels)]
        
        # 应用拆分
        app_blocks = re.split(r'\n### 应用[\d.]+ · .+\n', block)
        app_headers = re.findall(r'### 应用([\d.]+) · (.+)\n', block)
        
        for ai, (aid, aname) in enumerate(app_headers):
            ab = app_blocks[ai + 1] if ai + 1 < len(app_blocks) else ''
            
            app = {
                'id': aid,
                'name': aname.strip(),
                'title': aname.strip(),
                'subtitle': '',
                'video': '',
                'images': [],
                'placeholder': None,
                'pain': '', 'solve': '', 'how': '',
                'paths': [], 'extra_info': [], 'stats': [], 'stats_note': ''
            }
            
            # 应用数据展示
            app_data_block = re.search(r'### 应用数据\n\n((?:\|.+\|\n)+)', ab)
            if app_data_block:
                data_nums = re.findall(r'\|\s*数据(\d+)数值\s*\|\s*(.+?)\s*\|', app_data_block.group(1))
                data_labels = re.findall(r'\|\s*数据(\d+)标签\s*\|\s*(.+?)\s*\|', app_data_block.group(1))
                data_note = re.search(r'\|\s*数据补充\s*\|\s*(.+?)\s*\|', app_data_block.group(1))
                app['stats'] = [{'num': n, 'label': dl} for (dk, n), (dlk, dl) in zip(data_nums, data_labels) if dk == dlk]
                if data_note:
                    app['stats_note'] = data_note.group(1).strip()
            
            # 应用属性表
            img_srcs = []
            img_caps = []
            bid_compare_data = None
            bid_steps_data = []
            for line in ab.split('\n'):
                m = re.match(r'\|\s*(标题|副标题|能力集截图|演示视频|视频说明|视频详情|截图(\d+)|截图(\d+)说明|演示类型|占位图标|占位文字|入口文字|入口链接|画像预览|画像标签|运营报告|运营报告标签|操作指南)\s*\|\s*(.+?)\s*\|', line)
                if m:
                    k = m.group(1)
                    v = m.group(4) if m.group(4) else ''
                    if k == '标题':
                        app['title'] = v
                    elif k == '副标题':
                        app['subtitle'] = v
                    elif k == '能力集截图':
                        app['cap_images'] = [media_path(x.strip()) for x in v.split(',') if x.strip()]
                    elif k == '演示视频':
                        app['video'] = v
                    elif k == '视频说明':
                        app['video_label'] = v
                    elif k == '视频详情':
                        app['video_detail'] = v
                    elif k == '演示类型':
                        app['placeholder'] = (v == 'placeholder')
                    elif k == '占位图标':
                        app['placeholder_icon'] = v
                    elif k == '占位文字':
                        app['placeholder_text'] = v
                    elif k == '入口文字':
                        app['entry_text'] = v
                    elif k == '入口链接':
                        app['entry_link'] = v
                    elif k == '画像预览':
                        app['profile_preview'] = v
                    elif k == '画像标签':
                        app['profile_label'] = v
                    elif k == '运营报告':
                        app['report_preview'] = v
                    elif k == '运营报告标签':
                        app['report_label'] = v
                    elif k == '操作指南':
                        app['guide_link'] = v
                    elif k.startswith('截图') and k.endswith('说明'):
                        img_caps.append(v)
                    elif k.startswith('截图'):
                        img_srcs.append(v)
            
            # 解析AI标讯对比数据（通用表格，支持任意列数）
            bid_compare_match = re.search(r'### AI标讯对比数据\n\n((?:\|.+\|\n)+)', ab)
            if bid_compare_match:
                rows_raw = bid_compare_match.group(1).strip().split('\n')
                # 过滤掉分隔符行（如 |------|------|...）
                data_rows = [r for r in rows_raw if not re.match(r'\s*\|[-:\s|]+\|', r)]
                if len(data_rows) >= 2:
                    # 第一行是表头
                    headers = [c.strip() for c in re.findall(r'\|\s*([^|]+?)\s*(?=\|)', data_rows[0]) if c.strip()]
                    # 后续行是数据
                    body_rows = []
                    for row in data_rows[1:]:
                        cells = [c.strip() for c in re.findall(r'\|\s*([^|]+?)\s*(?=\|)', row)]
                        if any(cells):
                            body_rows.append(cells)
                    if headers and body_rows:
                        bid_compare_data = {'headers': headers, 'rows': body_rows}
            app['bid_compare'] = bid_compare_data

            # 解析应用能力集（通用表格，支持任意列数，第一列空单元格自动合并到上一行）
            capability_data = None
            cap_match = re.search(r'### 应用能力集\n\n((?:\|.+\|\n)+)', ab)
            if cap_match:
                cap_rows_raw = cap_match.group(1).strip().split('\n')
                cap_data_rows = [r for r in cap_rows_raw if not re.match(r'\s*\|[-:\s|]+\|', r)]
                if len(cap_data_rows) >= 2:
                    cap_headers = [c.strip() for c in re.findall(r'\|\s*([^|]+?)\s*(?=\|)', cap_data_rows[0]) if c.strip()]
                    cap_body = []
                    for row in cap_data_rows[1:]:
                        cells = [c.strip() for c in re.findall(r'\|\s*([^|]+?)\s*(?=\|)', row)]
                        if any(cells):
                            cap_body.append(cells)
                    if cap_headers and cap_body:
                        capability_data = {'headers': cap_headers, 'rows': cap_body}
            app['capability'] = capability_data
            
            # 解析招投标流程步骤
            bid_steps_match = re.search(r'### 招投标流程步骤\n\n((?:\|.+\|\n)+)', ab)
            if bid_steps_match:
                for line in bid_steps_match.group(1).strip().split('\n'):
                    cells = re.findall(r'\|\s*(.+?)\s*(?=\|)', line)
                    if cells and cells[0].strip() not in ('步骤', '') and not cells[0].startswith('--'):
                        step = {
                            'icon': cells[1].strip() if len(cells) > 1 else '',
                            'title': cells[2].strip() if len(cells) > 2 else '',
                            'color': cells[3].strip() if len(cells) > 3 else '',
                            'items': [x.strip() for x in cells[4].split(',')] if len(cells) > 4 and cells[4].strip() else []
                        }
                        bid_steps_data.append(step)
            app['bid_steps'] = bid_steps_data if bid_steps_data else None
            
            # 解析一线增量情况
            increment_match = re.search(r'### 一线增量情况\n\n((?:\|.+\|\n)+)', ab)
            if increment_match:
                inc_data = {'images': [], 'stats': []}
                for line in increment_match.group(1).strip().split('\n'):
                    cells = re.findall(r'\|\s*(.+?)\s*(?=\|)', line)
                    if len(cells) >= 2:
                        k = cells[0].strip()
                        v = cells[1].strip()
                        if k == '截图1':
                            inc_data['images'].append({'src': media_path(v), 'caption': ''})
                        elif k == '截图1说明':
                            if inc_data['images']:
                                inc_data['images'][-1]['caption'] = v
                        elif k == '截图2':
                            inc_data['images'].append({'src': media_path(v), 'caption': ''})
                        elif k == '截图2说明':
                            if len(inc_data['images']) >= 2:
                                inc_data['images'][-1]['caption'] = v
                        elif k == '标题':
                            inc_data['title'] = v
                        elif k.startswith('数据') and '数值' in k:
                            num = re.search(r'数据(\d+)', k)
                            if num:
                                idx = int(num.group(1))
                                inc_data['stats'].append({'idx': idx, 'num': v, 'label': ''})
                        elif k.startswith('数据') and '标签' in k:
                            num = re.search(r'数据(\d+)', k)
                            if num:
                                idx = int(num.group(1))
                                for s in inc_data['stats']:
                                    if s['idx'] == idx:
                                        s['label'] = v
                                        break
                app['increment'] = inc_data
            
            if img_srcs:
                app['images'] = [{'src': media_path(s), 'caption': img_caps[i] if i < len(img_caps) else ''} 
                                 for i, s in enumerate(img_srcs)]
            
            if app.get('placeholder') and not isinstance(app['placeholder'], bool):
                app['placeholder'] = (app['placeholder'] == 'placeholder')
            
            # 解析三段内容
            pain_match = re.search(r'\*\*😩 (?:用户痛点|业务需求|当前现状)\*\*\n(.*?)(?=\n\*\*✅|\n\*\*🔧|\Z)', ab, re.DOTALL)
            solve_match = re.search(r'\*\*✅ (?:AI能帮你|整体方案|未来规划)\*\*\n(.*?)(?=\n\*\*🔧|\Z)', ab, re.DOTALL)
            how_match = re.search(r'\*\*🔧 (?:怎么操作|平台入口|推进计划)\*\*\n(.*?)(?=\n###|\n##|\Z)', ab, re.DOTALL)
            
            if pain_match:
                app['pain'] = pain_match.group(1).strip()
            if solve_match:
                app['solve'] = solve_match.group(1).strip()
            if how_match:
                raw_how = how_match.group(1).strip()
                # 预处理：同一行中的 "文本 | 操作路径 | xxx" 拆成两行
                lines = raw_how.split('\n')
                cleaned_lines = []
                for line in lines:
                    m_inline = re.search(r'\s*\|\s*(?:操作|快捷)路径\s*\|', line)
                    if m_inline:
                        desc_part = line[:m_inline.start()].strip()
                        path_part = line[m_inline.start():].strip()
                        if desc_part:
                            cleaned_lines.append(desc_part)
                        cleaned_lines.append(path_part)
                    else:
                        cleaned_lines.append(line)
                how_text = []
                paths = []
                path_links = {}
                extra = []
                for line in cleaned_lines:
                    # 路径链接N：给第 N 条「操作/快捷路径」配跳转（值可以是网址，也可以是「入口链接映射」里的入口名称）
                    m_plink = re.match(r'\|\s*路径链接(\d+)\s*\|\s*(.+?)\s*\|', line)
                    m_path = re.match(r'\|\s*(?:操作|快捷)路径(\d*)\s*\|\s*(.+?)\s*\|', line)
                    m_extra = re.match(r'\|\s*补充说明\s*\|\s*(.+?)\s*\|', line)
                    m_ptitle = re.match(r'\|\s*路径标题(\d*)\s*\|\s*(.+?)\s*\|', line)
                    if m_plink:
                        path_links[int(m_plink.group(1))] = m_plink.group(2).strip()
                    elif m_path:
                        paths.append({'text': m_path.group(2).strip(), 'link': ''})
                    elif m_extra:
                        extra.append(m_extra.group(1).strip())
                    elif m_ptitle:
                        extra.append(('path_title', m_ptitle.group(2), ''))
                    elif line.strip() and not line.startswith('|'):
                        how_text.append(line)
                for _i, _p in enumerate(paths, 1):
                    if path_links.get(_i):
                        _p['link'] = path_links[_i]
                app['how'] = '\n'.join(how_text).strip()
                app['paths'] = paths
                app['extra_info'] = extra
            
            scene['apps'].append(app)
        
        data['scenes'].append(scene)

    # ---- 超级数字员工页 ----
    data['de_page'] = parse_de_page(text)

    return data


# ============================================================
# HTML模板
# ============================================================

CSS = '''<style>
*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
:root {
  --brand-deep: #060f25; --brand-blue: #0d2550; --brand-teal: #00a884;
  --blue:   #0d2550; --blue-d: #091c3e; --blue-l: #eaf2ff;
  --green:  #00a884; --green-l:#e8faf5;
  --purple: #5b3fd4; --purple-l:#f0eaff;
  --orange: #e8710a; --orange-l:#fff6ed;
  --text:   #121624; --muted:  #5c6370; --border: #e2e5ea;
  --border-warm: #e5dfd1; --border-card: #ece9e3;
  --bg:     #f7f8fb; --white:  #ffffff;
  --r: 16px; --r-lg: 24px;
  --shadow: 0 1px 3px rgba(0,0,0,.04),0 2px 12px rgba(0,0,0,.03);
  --shadow-md: 0 4px 16px rgba(0,0,0,.05),0 1px 3px rgba(0,0,0,.04);
  --shadow-lg: 0 8px 36px rgba(0,0,0,.07),0 2px 8px rgba(0,0,0,.04);
  --shadow-glow: 0 4px 24px rgba(13,37,80,.08);
  --transition: .28s cubic-bezier(.4,0,.2,1);
}
html { scroll-behavior: smooth; }
/* 固定顶部导航会遮住锚点落点，按各页导航高度留白 */
#future-home, #landing-scenes, #ai-arch, .cap-card[data-scene] { scroll-margin-top: 78px; }
body { font-family: 'PingFang SC','Microsoft YaHei','Inter',-apple-system,sans-serif; background: var(--bg); color: var(--text); line-height: 1.68; overflow-x: hidden; -webkit-font-smoothing:antialiased; }
::-webkit-scrollbar { width: 6px; }
::-webkit-scrollbar-thumb { background: #c8cdd5; border-radius: 3px; }
::-webkit-scrollbar-thumb:hover { background: #a8adb5; }
#prog { position:fixed; top:0; left:0; height:3px; z-index:999; background:linear-gradient(90deg,#4785d4,#7c5ce7,#10b981); transition:width .12s linear; border-radius:0 3px 3px 0; }
nav { position:fixed; top:0; left:0; right:0; z-index:200; height:60px; background:rgba(255,255,255,.88); backdrop-filter:blur(20px) saturate(180%); -webkit-backdrop-filter:blur(20px) saturate(180%); border-bottom:1px solid transparent; background-clip:padding-box; border-bottom:1px solid rgba(0,0,0,.06); display:flex; align-items:center; justify-content:space-between; padding:0 36px; box-shadow:0 1px 0 rgba(0,0,0,.04); transition:box-shadow var(--transition); }
nav.scrolled { box-shadow:0 1px 12px rgba(0,0,0,.06); }
.nav-brand { display:flex; align-items:center; gap:10px; font-weight:700; font-size:15px; color:var(--brand-deep); text-decoration:none; letter-spacing:-.2px; transition:opacity var(--transition); }
.nav-brand:hover { opacity:.8; }
.nav-brand img { height:30px; width:auto; }
.nav-brand span { color:var(--brand-deep); }
.nav-tabs { display:flex; gap:4px; }
.nav-tabs a { padding:8px 16px; border-radius:20px; font-size:16px; font-weight:500; color:var(--muted); text-decoration:none; transition:all var(--transition); display:flex; align-items:center; gap:5px; letter-spacing:-.1px; position:relative; }
.nav-tabs a::after { content:''; position:absolute; bottom:1px; left:50%; transform:translateX(-50%); width:0; height:2px; background:linear-gradient(90deg,#3b82f6,#8b5cf6); border-radius:1px; transition:width var(--transition); }
.nav-tabs a:hover { color:var(--blue); background:var(--blue-l); }
.nav-tabs a.active { color:var(--blue); font-weight:600; background:var(--blue-l); }
.nav-tabs a.active::after { width:24px; }
.nav-right { display:flex; align-items:center; gap:8px; font-size:12px; font-weight:600; color:var(--muted); background:var(--white); border:1px solid rgba(0,0,0,.06); padding:4px 14px 4px 4px; border-radius:24px; transition:all var(--transition); }
.nav-right img { height:24px; width:auto; border-radius:50%; background:#fff; padding:2px; box-shadow:0 0 8px rgba(0,168,132,.15); }
.nav-right-dept { white-space:nowrap; }
.hero { min-height:100vh; padding:48px 40px 50px; background:linear-gradient(170deg,#070e2a 0%,#0d1f52 20%,#0f2b5c 42%,#0b2248 65%,#060f25 100%); display:flex; align-items:center; justify-content:center; position:relative; overflow:hidden; }
.hero::before { content:''; position:absolute; inset:0; background:radial-gradient(ellipse 70% 50% at 50% 35%,rgba(59,130,246,.08) 0%,transparent 65%); pointer-events:none; }
.hero-bg-circles { position:absolute; inset:0; pointer-events:none; overflow:hidden; }
.hero-bg-circles::before { content:''; position:absolute; inset:0; background:radial-gradient(ellipse 60% 42% at 50% 28%, rgba(99,140,230,.12) 0%, transparent 70%); }
.hero-bg-circles::after { content:''; position:absolute; bottom:0; left:0; right:0; height:160px; background:linear-gradient(to top,rgba(7,14,42,.6),transparent); }
.hero-bg-circles span { position:absolute; border-radius:50%; background:rgba(255,255,255,.03); animation:drift 16s ease-in-out infinite; }
.hero-bg-circles span:nth-child(1){ width:560px;height:560px;top:-180px;right:-140px;animation-delay:0s; }
.hero-bg-circles span:nth-child(2){ width:360px;height:360px;bottom:-100px;left:-100px;animation-delay:-6s; }
.hero-bg-circles span:nth-child(3){ width:240px;height:240px;top:44%;left:6%;background:rgba(99,140,230,.05);animation-delay:-10s; }
@keyframes drift { 0%,100%{transform:translate(0,0)} 33%{transform:translate(14px,-14px)} 66%{transform:translate(-8px,8px)} }
.hero-inner { position:relative; z-index:2; max-width:1200px; width:100%; text-align:center; padding:0 60px; animation:fadeInUp .8s ease-out both; }
@keyframes fadeInUp { from{opacity:0;transform:translateY(24px)} to{opacity:1;transform:translateY(0)} }
.hero-eyebrow { display:inline-flex; align-items:center; gap:8px; background:rgba(255,255,255,.06); border:1px solid rgba(255,255,255,.12); color:rgba(255,255,255,.72); font-size:12px; font-weight:600; padding:6px 18px; border-radius:24px; margin-bottom:28px; backdrop-filter:blur(8px); }
.live-dot { width:7px;height:7px;border-radius:50%;background:#4ade80;animation:pulse 2s ease-in-out infinite; box-shadow:0 0 8px rgba(74,222,128,.5); }
@keyframes pulse { 0%,100%{opacity:1;transform:scale(1)} 50%{opacity:.4;transform:scale(.85)} }
.hero h1 { font-size:clamp(34px,5.5vw,58px); font-weight:900; line-height:1.12; color:#fff; margin-bottom:18px; letter-spacing:-.6px; text-shadow:0 2px 20px rgba(0,0,0,.3); }
.hero-logo-row { display:flex; flex-direction:column; align-items:center; justify-content:center; gap:6px; margin-bottom:36px; }
.hero-logo-img { height:56px; width:auto; filter:drop-shadow(0 0 24px rgba(59,130,246,.3)) drop-shadow(0 0 8px rgba(0,168,132,.2)); margin-bottom:8px; }
.hero-logo-dept { font-size:18px; color:rgba(255,255,255,.45); font-weight:500; letter-spacing:.8px; }
.hero h1 em { background:linear-gradient(135deg,#5eead4,#818cf8,#60a5fa); -webkit-background-clip:text; -webkit-text-fill-color:transparent; font-style:normal; }
.hero-sub { font-size:16px; color:rgba(255,255,255,.5); margin:0 auto 36px; max-width:640px; line-height:1.75; }
.hero-action { font-size:15px; color:#60a5fa; margin:-22px auto 0; max-width:760px; line-height:1.7; font-weight:500; letter-spacing:.2px; text-shadow:0 0 24px rgba(96,165,250,.35); }
/* ── Hero 右侧：超级数字员工 圆形入口（头像 + 旋转光环 + 手指引导） ── */
.hero-de-orb { position:absolute; right:max(34px, 3.4vw); top:118px; z-index:3; width:132px; height:188px; text-decoration:none; }
.orb-stage { position:relative; display:block; width:132px; height:132px;
  animation:orbIn .95s cubic-bezier(.2,.9,.3,1.18) .4s both; }
@keyframes orbIn { from{opacity:0; transform:scale(.7) translateY(16px)} to{opacity:1; transform:scale(1) translateY(0)} }
.orb-ring { position:absolute; inset:-9px; border-radius:50%; border:1.5px dashed rgba(125,178,255,.52);
  animation:orbSpin 24s linear infinite; }
@keyframes orbSpin { to { transform:rotate(360deg); } }
.orb-halo { position:absolute; inset:0; border-radius:50%; border:1.5px solid rgba(110,168,255,.8);
  animation:orbHalo 2.9s ease-out infinite; pointer-events:none; }
.orb-halo.d2 { animation-delay:1.45s; }
@keyframes orbHalo { 0%{transform:scale(.9); opacity:.75} 78%{transform:scale(1.42); opacity:0} 100%{transform:scale(1.42); opacity:0} }
.orb-core { position:absolute; inset:0; display:block; border-radius:50%; overflow:hidden;
  background:linear-gradient(150deg,#1b3f86,#0e2050); transform:translateZ(0);
  box-shadow:0 12px 34px rgba(4,14,38,.58), 0 0 0 1.5px rgba(125,178,255,.42), inset 0 0 22px rgba(96,150,255,.22);
  transition:box-shadow .34s, filter .34s; }
.orb-core img { width:100%; height:100%; display:block; object-fit:cover; }
.hero-de-orb:hover .orb-core { box-shadow:0 16px 46px rgba(92,142,255,.52), 0 0 0 2.5px rgba(160,200,255,.72), inset 0 0 26px rgba(120,170,255,.3); filter:brightness(1.06); }
.orb-label { position:absolute; left:50%; top:145px; transform:translateX(-50%);
  padding:5px 14px; border-radius:13px; font-size:12.5px; font-weight:800; color:#fff; white-space:nowrap; letter-spacing:.2px;
  background:linear-gradient(118deg,#1f5fd0,#5b3fd4 55%,#b026d3);
  box-shadow:0 6px 18px rgba(58,86,214,.42), inset 0 1px 0 rgba(255,255,255,.28);
  transition:transform .3s, box-shadow .3s; }
.hero-de-orb:hover .orb-label { transform:translateX(-50%) translateY(-2px); box-shadow:0 10px 24px rgba(58,86,214,.55), inset 0 1px 0 rgba(255,255,255,.34); }
.orb-hand { position:absolute; right:-21px; top:40px; font-size:25px; line-height:1; pointer-events:none;
  filter:drop-shadow(0 4px 10px rgba(0,0,0,.5)); }
.orb-hand b { display:block; font-weight:400; animation:orbTap 2.3s cubic-bezier(.4,0,.3,1) infinite; }
@keyframes orbTap {
  0%,60%,100% { transform:translate(0,0) rotate(-26deg) scale(1); opacity:.92; }
  14%         { transform:translate(-4px,-9px) rotate(-34deg) scale(1.08); opacity:1; }
  30%         { transform:translate(0,0) rotate(-26deg) scale(1); opacity:.92; }
  44%         { transform:translate(-3px,-6px) rotate(-31deg) scale(1.04); opacity:1; }
}
@media (max-width:1280px) { .hero-de-orb { top:106px; } }
@media (max-width:1180px) { .hero-de-orb { transform:scale(.86); transform-origin:top right; } }
@media (max-width:1080px) { .hero-de-orb { right:max(26px, 2.4vw); } .orb-hand { right:-17px; font-size:23px; } }
/* ≤1024px：改为主内容下方的横向居中胶囊入口（不再隐藏） */
@media (max-width:1024px) {
  .hero { flex-direction:column; }
  .hero-inner { order:1; }
  .hero-de-orb { position:relative; right:auto; top:auto; order:2; flex:none;
    width:auto; height:auto; display:inline-flex; align-items:center; gap:14px;
    margin:26px auto 6px; padding:8px 24px 8px 8px; border-radius:999px;
    background:linear-gradient(118deg, rgba(31,95,208,.30), rgba(91,63,212,.26));
    border:1px solid rgba(125,178,255,.34); backdrop-filter:blur(8px); -webkit-backdrop-filter:blur(8px);
    box-shadow:0 12px 34px rgba(4,14,38,.46); transform:none; transform-origin:center;
    transition:transform .3s, box-shadow .3s; }
  .hero-de-orb:active { transform:scale(.97); }
  .orb-stage { width:66px; height:66px; flex:none; animation:none; }
  .orb-ring { inset:-5px; border-width:1px; }
  .orb-halo { animation-duration:2.4s; }
  .orb-label { position:relative; left:auto; top:auto; transform:none; padding:0; white-space:nowrap;
    font-size:15px; background:none; box-shadow:none; }
  .hero-de-orb:hover .orb-label { transform:none; box-shadow:none; }
  .orb-hand { display:none; }
  .hero-de-orb::after { content:'👆'; order:3; margin-left:-4px; font-size:20px; line-height:1;
    filter:drop-shadow(0 4px 10px rgba(0,0,0,.5)); animation:orbTap 2.3s cubic-bezier(.4,0,.3,1) infinite; }
}
@media (max-width:640px) {
  .hero-de-orb { gap:11px; padding:7px 18px 7px 7px; margin-top:22px; }
  .orb-stage { width:58px; height:58px; }
  .orb-label { font-size:14px; }
  .hero-de-orb::after { font-size:18px; }
}
@media (prefers-reduced-motion: reduce) {
  .orb-stage, .orb-ring, .orb-halo, .orb-hand b, .hero-de-orb::after { animation:none !important; }
  .orb-halo { opacity:.35; }}
.text-highlight { background:linear-gradient(135deg,#5eead4,#818cf8,#60a5fa); -webkit-background-clip:text; -webkit-text-fill-color:transparent; font-style:normal; font-weight:700; }
.text-highlight-gold { background:linear-gradient(135deg,#fbbf24,#f59e0b,#fb923c); -webkit-background-clip:text; -webkit-text-fill-color:transparent; font-style:normal; font-weight:700; }
.hero-incentive-divider { width:80px; height:1px; background:rgba(255,255,255,.12); border-radius:1px; margin:44px auto 28px; }
.hero-incentive-label { text-align:center; font-size:24px; font-weight:900; background:linear-gradient(135deg,#fbbf24,#f59e0b,#fb923c); -webkit-background-clip:text; -webkit-text-fill-color:transparent; letter-spacing:4px; margin-bottom:24px; }
.hero-incentives-row { display:flex; justify-content:center; gap:20px; flex-wrap:wrap; margin-top:0; }
.hero-incentive-desc { margin-top:28px; text-align:center; color:rgba(255,255,255,.42); font-size:13px; line-height:1.8; max-width:700px; margin-left:auto; margin-right:auto; }
.hero-incentive-badge { background:rgba(255,255,255,.06); backdrop-filter:blur(16px); -webkit-backdrop-filter:blur(16px); border:1px solid rgba(255,255,255,.1); border-radius:18px; padding:18px 24px; color:#fff; text-align:center; transition:all var(--transition); min-width:160px; }
.hero-incentive-badge:hover { background:rgba(255,255,255,.12); transform:translateY(-4px); border-color:rgba(99,162,255,.35); box-shadow:0 8px 32px rgba(0,0,0,.3); }
a.hero-incentive-badge { text-decoration:none; color:#fff; display:block; position:relative; }
a.hero-incentive-badge .hb-title { color:#60a5fa; font-weight:800; }
a.hero-incentive-badge::after { content:'↗'; position:absolute; top:10px; right:16px; font-size:13px; color:rgba(96,165,250,.5); opacity:0; transition:opacity var(--transition); }
a.hero-incentive-badge:hover::after { opacity:1; }
a.hero-incentive-badge:hover { border-color:rgba(96,165,250,.4); }
.hero-incentive-badge .hb-icon { font-size:24px; margin-bottom:5px; }
.hero-incentive-badge .hb-title { font-size:14px; font-weight:800; letter-spacing:.5px; }
.hero-incentive-badge .hb-sub { font-size:11px; color:rgba(255,255,255,.55); margin-top:3px; }
.hero-incentive-badge .hb-link { font-size:10px; color:rgba(96,165,250,.65); margin-top:5px; letter-spacing:.3px; }
@media (max-width:768px) { .hero-incentives-row { gap:12px; } .hero-incentive-badge { min-width:0; padding:14px 16px; } }
.hero-char-cards { display:flex; justify-content:center; gap:18px; flex-wrap:wrap; margin-top:40px; }
.hero-card { background:linear-gradient(145deg,rgba(13,37,80,.8),rgba(26,67,118,.6)); border:1px solid rgba(255,255,255,.08); border-radius:20px; padding:28px 22px 24px; text-align:center; width:155px; backdrop-filter:blur(8px); -webkit-backdrop-filter:blur(8px); transition:all var(--transition); }
.hero-card:hover { background:linear-gradient(145deg,rgba(13,37,80,.92),rgba(30,79,138,.75)); transform:translateY(-6px); box-shadow:0 16px 48px rgba(0,0,0,.35),0 0 0 1px rgba(255,255,255,.06); }
.hero-card .hc-icon { font-size:40px; margin-bottom:10px; transition:transform var(--transition); }
.hero-card:hover .hc-icon { transform:scale(1.1); }
.hero-card .hc-name { font-size:15px; font-weight:800; color:#fff; letter-spacing:.5px; margin-bottom:8px; }
.hero-card .hc-desc { font-size:12px; color:rgba(255,255,255,.5); line-height:1.7; }
@media (max-width:768px) { .hero-char-cards { gap:12px; } .hero-card { width:135px; padding:20px 14px; } }
.scene-nav { position:sticky; top:60px; z-index:100; background:rgba(255,255,255,.82); backdrop-filter:blur(16px); -webkit-backdrop-filter:blur(16px); border-bottom:1px solid rgba(0,0,0,.05); padding:12px 0; transition:box-shadow var(--transition); }
.scene-nav.shadow { box-shadow:0 4px 20px rgba(0,0,0,.04); }
.scene-nav-inner { max-width:1120px; margin:0 auto; padding:0 28px; display:flex; gap:10px; flex-wrap:wrap; justify-content:center; }
.scene-nav-btn { padding:10px 22px; border-radius:24px; font-size:18px; font-weight:600; border:1px solid transparent; background:transparent; color:var(--muted); cursor:pointer; transition:all var(--transition); position:relative; }
.scene-nav-btn:hover { background:var(--blue-l); color:var(--blue); }
.scene-nav-btn.active { background:var(--blue-l); color:var(--blue); font-weight:700; box-shadow:0 2px 8px rgba(13,37,80,.08); }
.scene-nav-hint { font-size:12px; color:#10b981; align-self:center; white-space:nowrap; flex-shrink:0; opacity:.85; letter-spacing:.3px; }
.scene-section { max-width:1120px; margin:0 auto; padding:72px 28px 96px; }
.scene-header { display:flex; align-items:center; gap:18px; margin-bottom:56px; }
.scene-header-ico { width:56px;height:56px;border-radius:16px;display:flex;align-items:center;justify-content:center;font-size:24px;flex-shrink:0; box-shadow:0 4px 16px rgba(0,0,0,.08); }
.scene-title { font-size:32px; font-weight:900; color:var(--text); letter-spacing:-.4px; }
.scene-sub { font-size:15px; color:var(--muted); margin-top:4px; }
.scene-count { margin-left:auto; padding:6px 18px; border-radius:24px; font-size:12px; font-weight:700; background:var(--white); border:1px solid rgba(0,0,0,.06); color:var(--muted); }
/* ── 时间线串联 ── */
.scene-timeline { position:relative; max-width:1200px; margin:0 auto; padding:0 28px; }
.scene-timeline::before { content:''; position:absolute; left:56px; top:60px; bottom:60px; width:2px; background:linear-gradient(180deg,#3b82f6 0%,#8b5cf6 20%,#10b981 42%,#f59e0b 65%,#ef4444 100%); border-radius:1px; z-index:0; opacity:.35; }
.scene-timeline-item { position:relative; }
/* ── 折叠/展开按钮 ── */
.scene-toggle { width:34px; height:34px; border-radius:10px; background:var(--white); border:1px solid rgba(0,0,0,.06); cursor:pointer; font-size:11px; color:var(--muted); display:flex; align-items:center; justify-content:center; transition:all var(--transition); flex-shrink:0; box-shadow:var(--shadow); }
.scene-toggle:hover { background:#eaf2ff; color:#3b82f6; border-color:#93c5fd; transform:scale(1.05); }
.scene-toggle.collapsed { transform:rotate(-90deg); }
.scene-body { overflow:hidden; transition:max-height .5s ease, opacity .4s ease; max-height:8000px; opacity:1; }
.scene-body.collapsed { max-height:0; opacity:0; }
.app-block { background:var(--white); border:1px solid rgba(0,0,0,.05); border-radius:var(--r-lg); overflow:hidden; margin-bottom:36px; box-shadow:var(--shadow); transition:box-shadow var(--transition),transform var(--transition); }
.app-block:hover { box-shadow:var(--shadow-lg); transform:translateY(-2px); }
.app-block.revealed { opacity:1; transform:translateY(0); }
.app-block-header { display:flex; align-items:center; gap:16px; padding:24px 32px; border-bottom:1px solid rgba(0,0,0,.04); background:linear-gradient(180deg,#fcfdfe,#fff); }
.app-block-header > div:not(.app-num-badge) { min-width:0; flex:1; }
.app-num-badge { width:40px;height:40px;border-radius:12px;display:flex;align-items:center;justify-content:center;color:#fff;font-weight:800;font-size:15px;flex-shrink:0; box-shadow:0 2px 8px rgba(0,0,0,.12); transition:transform var(--transition); }
.app-block:hover .app-num-badge { transform:scale(1.08); }
.app-title { font-size:19px; font-weight:800; color:var(--text); letter-spacing:-.2px; }
.app-subtitle { margin-top:4px; font-size:13px; color:var(--muted); word-break:break-word; }
.app-guide-card { display:inline-flex; align-items:center; gap:8px; padding:10px 18px; border-radius:12px; background:linear-gradient(135deg,#4f46e5,#7c3aed); color:#fff; font-size:13px; font-weight:700; text-decoration:none; box-shadow:0 2px 10px rgba(79,70,229,.25); transition:all var(--transition); flex-shrink:0; white-space:nowrap; }
.app-guide-card:hover { transform:translateY(-2px); box-shadow:0 6px 20px rgba(79,70,229,.35); }
.app-guide-card svg { width:16px;height:16px; fill:none; stroke:#fff; stroke-width:2; stroke-linecap:round; stroke-linejoin:round; flex-shrink:0; }
.app-content { display:grid; grid-template-columns:1fr 1fr 1fr; gap:0; border-bottom:1px solid rgba(0,0,0,.04); align-items:stretch; }
.app-col { padding:32px 28px; position:relative; overflow:hidden; border-right:1px solid rgba(0,0,0,.04); display:flex; flex-direction:column; justify-content:space-between; }
.app-col-inner { flex:1; display:flex; flex-direction:column; justify-content:flex-start; }
.app-col-inner > *:first-child { margin-top:0; }
.app-col-inner > *:last-child { margin-bottom:0; }
.app-col:last-child { border-right:none; }
.col-label { font-size:13px; font-weight:800; margin-bottom:16px; display:flex; align-items:center; gap:8px; letter-spacing:.2px; }
.col-label-pain { color:#dc2626; }
.col-label-solve { color:#059669; }
.col-label-how { color:var(--blue); }
.app-col p { font-size:14px; color:var(--text); line-height:1.7; }
.app-col ul { margin-top:12px; padding-left:18px; font-size:14px; color:var(--text); }
.app-col li { margin-bottom:6px; }
.col-emoji-bg { position:absolute; bottom:-12px; right:-8px; font-size:72px; opacity:.04; pointer-events:none; user-select:none; }
.path-tag { display:inline-block; padding:8px 16px; border-radius:12px; font-size:13px; font-weight:700; background:linear-gradient(135deg,#eaf2ff,#dbe9ff); color:var(--blue); margin-top:12px; letter-spacing:.3px; border:1px solid rgba(59,130,246,.15); transition:all var(--transition); }
.path-tag:hover { transform:translateX(2px); box-shadow:0 2px 8px rgba(13,37,80,.08); }
.path-tag .arr { color:var(--muted); margin:0 3px; }
/* 可跳转的路径标签：深色实心 + ↗，和不可点的浅蓝标签一眼区分 */
a.path-tag-link { display:inline-block; text-decoration:none; cursor:pointer;
  background:linear-gradient(135deg,#0d2550,#1a3d6e); color:#fff; border-color:transparent;
  box-shadow:0 6px 16px rgba(13,37,80,.18); }
a.path-tag-link .arr { color:rgba(255,255,255,.55); }
a.path-tag-link .pt-arw { display:inline-block; font-style:normal; font-size:12px; color:#8fc0ff;
  margin-left:6px; transition:transform .25s; }
a.path-tag-link:hover { transform:translateX(3px); box-shadow:0 10px 24px rgba(13,37,80,.3); }
a.path-tag-link:hover .pt-arw { transform:translate(2px,-2px); }
a.path-tag-link:focus-visible { outline:2px solid #7fb2ff; outline-offset:2px; }
/* ---- 视频面板 ---- */
.app-video-panel { background:#f6f8fc; padding:24px 32px 28px; border-top:1px solid rgba(0,0,0,.05); }
.app-video-detail { background:#fff; padding:20px 32px; border-top:1px solid rgba(0,0,0,.04); }
.app-video-detail-content { font-size:14px; line-height:1.8; color:var(--text); }
.app-video-detail-content strong { color:var(--blue); font-size:15px; }
.app-video-detail-content ul { margin:8px 0; padding-left:20px; }
.app-video-detail-content li { margin:4px 0; color:#3a4a5c; }
.app-video-label { display:flex; align-items:center; gap:10px; font-size:12px; font-weight:700; color:#5f6b7a; letter-spacing:.6px; text-transform:uppercase; margin-bottom:14px; }
.app-video-label .vdot { width:9px;height:9px;border-radius:50%;background:#3b82f6; box-shadow:0 0 6px rgba(59,130,246,.4); }
.video-wrapper { position:relative; width:100%; border-radius:12px; overflow:hidden; background:#0a0d14; box-shadow:0 3px 16px rgba(0,0,0,.06); transition:all var(--transition); }
.video-wrapper video { width:100%; display:block; max-height:480px; object-fit:contain; background:#0a0d14; border-radius:12px; }
.video-placeholder { position:absolute; inset:0; display:flex; flex-direction:column; align-items:center; justify-content:center; gap:14px; cursor:pointer; z-index:2; transition:opacity var(--transition); background:linear-gradient(135deg,rgba(13,37,80,.06),rgba(13,37,80,.02)); }
.video-wrapper.playing .video-placeholder { opacity:0; pointer-events:none; }
.vp-icon { width:64px; height:64px; border-radius:50%; background:rgba(13,37,80,.85); color:#fff; font-size:26px; display:flex; align-items:center; justify-content:center; box-shadow:0 6px 24px rgba(0,0,0,.25); transition:all var(--transition); }
.video-placeholder:hover .vp-icon { transform:scale(1.12); background:rgba(13,37,80,.95); box-shadow:0 8px 32px rgba(0,0,0,.35); }
.vp-text { font-size:14px; color:#5f6b7a; font-weight:500; }
/* 视频加载进度 */
.vp-loading { display:none; flex-direction:column; align-items:center; gap:12px; position:absolute; z-index:3; }
.video-wrapper.loading .vp-loading { display:flex; }
.video-wrapper.loading .vp-icon-wrap { display:none; }
.vp-spinner { width:48px; height:48px; border:3px solid rgba(255,255,255,.15); border-top-color:#60a5fa; border-radius:50%; animation:vpSpin .8s linear infinite; }
@keyframes vpSpin { to{transform:rotate(360deg)} }
.vp-progress { font-size:13px; color:#94a3b8; font-weight:500; text-align:center; }
.vp-error { display:none; flex-direction:column; align-items:center; gap:8px; color:#f87171; font-size:13px; }
.video-wrapper.error .vp-error { display:flex; }
.video-wrapper.error .vp-icon-wrap,.video-wrapper.error .vp-loading { display:none; }
.vp-retry { margin-top:4px; padding:6px 18px; border-radius:20px; background:rgba(248,113,113,.15); color:#f87171; border:1px solid rgba(248,113,113,.3); font-size:12px; font-weight:600; cursor:pointer; transition:all .2s; }
.vp-retry:hover { background:rgba(248,113,113,.25); }
@media (max-width:768px) {
  .vp-icon { width:56px; height:56px; font-size:22px; }
  .vp-text { font-size:13px; }
}
.no-video { background:#fafbff; border-radius:12px; border:2px dashed #c7d2fe; padding:36px; text-align:center; color:#6366f1; }
.no-video .nv-ico { font-size:36px; margin-bottom:10px; }
.no-video p { font-size:14px; }
/* ---- 客户画像预览 ---- */
.profile-preview { background:#f6f8fc; border-top:1px solid rgba(0,0,0,.05); padding:0 32px 28px; }
.profile-preview-label { display:flex; align-items:center; gap:10px; font-size:12px; font-weight:700; color:#5f6b7a; letter-spacing:.5px; padding:22px 0 14px; }
.profile-preview-label .pdot { width:9px;height:9px;border-radius:50%;background:#10b981; box-shadow:0 0 6px rgba(16,185,129,.4); }
.profile-preview-label .pbeta { font-size:9px; background:#d1fae5; color:#047857; padding:3px 10px; border-radius:12px; font-weight:800; letter-spacing:1px; text-transform:uppercase; }
.profile-preview-frame { width:100%; height:560px; border-radius:12px; overflow:hidden; border:1px solid rgba(0,0,0,.06); background:#fff; box-shadow:var(--shadow); }
.profile-preview-frame iframe { width:100%; height:100%; border:none; }
@media (max-width:768px) { .profile-preview { padding:0 16px 24px; } .profile-preview-frame { height:420px; } }
/* ---- 运营报告长图预览 ---- */
.report-preview { background:#f6f8fc; border-top:1px solid rgba(0,0,0,.05); padding:0 32px 28px; }
.report-preview-label { display:flex; align-items:center; gap:10px; font-size:12px; font-weight:700; color:#5f6b7a; letter-spacing:.5px; padding:22px 0 14px; }
.report-preview-label .pdot { width:9px;height:9px;border-radius:50%;background:#f59e0b; box-shadow:0 0 6px rgba(245,158,11,.4); }
.report-preview-label .pbeta { font-size:9px; background:#fef3c7; color:#b45309; padding:3px 10px; border-radius:12px; font-weight:800; letter-spacing:1px; text-transform:uppercase; }
.report-preview-frame { width:100%; max-height:620px; border-radius:12px; overflow-y:auto; overflow-x:hidden; border:1px solid rgba(0,0,0,.06); background:#fff; box-shadow:var(--shadow); }
.report-preview-frame img { width:100%; display:block; }
@media (max-width:768px) { .report-preview { padding:0 16px 24px; } .report-preview-frame { max-height:460px; } }
/* ---- 截图画廊 ---- */
.img-gallery { display:grid; grid-template-columns:repeat(3,1fr); gap:18px; align-items:start; }
.img-gallery.col5 { grid-template-columns:repeat(5,1fr); }
.img-gallery.col2 { grid-template-columns:repeat(2,1fr); }
.img-gallery.col1 { grid-template-columns:1fr; }
.img-gallery figure { background:#fff; border-radius:12px; overflow:hidden; border:1px solid rgba(0,0,0,.06); margin:0; display:flex; flex-direction:column; height:100%; box-shadow:var(--shadow); transition:all var(--transition); }
.img-gallery figure:hover { box-shadow:var(--shadow-md); transform:translateY(-2px); }
.img-gallery img { width:100%; display:block; object-fit:contain; height:260px; background:#f6f8fc; line-height:0; flex-shrink:0; }
.img-gallery figcaption { padding:12px 16px; font-size:13px; color:#5f6b7a; background:#fff; border-top:1px solid rgba(0,0,0,.04); font-weight:500; }
/* 移动端截图缩小效果 */
.img-gallery figure.mobile-screenshot { transform:scale(0.92); transform-origin:center top; }
.img-gallery figure.pc-screenshot { grid-column:span 1; }
.bid-flow-platform { display:flex; gap:18px; align-items:flex-start; margin-bottom:0; }
.bid-flow-platform .app-video-panel { flex:1; min-width:0; }
.img-gallery-single { grid-template-columns:1fr; }
.img-gallery-single figure { max-width:100%; line-height:0; }
.img-gallery-single img { object-fit:contain; }
/* ---- 图片点击放大 Lightbox ---- */
.img-gallery figure { cursor:zoom-in; position:relative; }
.img-gallery figure::after { content:'🔍'; position:absolute; top:8px; right:10px; font-size:14px; background:rgba(255,255,255,.85); border-radius:50%; width:28px; height:28px; display:flex; align-items:center; justify-content:center; opacity:0; transition:opacity var(--transition); pointer-events:none; box-shadow:0 1px 4px rgba(0,0,0,.1); }
.img-gallery figure:hover::after { opacity:1; }
.lightbox-overlay { position:fixed; inset:0; z-index:9999; background:rgba(0,0,0,.92); display:flex; align-items:center; justify-content:center; padding:40px; opacity:0; visibility:hidden; transition:opacity .3s,visibility .3s; }
.lightbox-overlay.active { opacity:1; visibility:visible; }
.lightbox-overlay img { max-width:95%; max-height:90vh; object-fit:contain; border-radius:8px; box-shadow:0 8px 40px rgba(0,0,0,.5); }
.lightbox-overlay .lb-close { position:absolute; top:20px; right:30px; width:44px; height:44px; border-radius:50%; background:rgba(255,255,255,.12); color:#fff; font-size:24px; display:flex; align-items:center; justify-content:center; cursor:pointer; transition:background .2s; border:none; }
.lightbox-overlay .lb-close:hover { background:rgba(255,255,255,.25); }
.lightbox-overlay .lb-caption { position:absolute; bottom:20px; left:50%; transform:translateX(-50%); color:rgba(255,255,255,.7); font-size:14px; max-width:80%; text-align:center; }
.bid-compare { margin-top:0; background:#fff; border-radius:14px; border:1px solid rgba(0,0,0,.05); overflow:hidden; box-shadow:var(--shadow); }
.bid-compare-title { padding:16px 22px; font-size:17px; font-weight:700; color:#fff; background:linear-gradient(135deg,#0d2550,#1a3d6e,#235491); display:flex; align-items:center; gap:10px; }
.bid-compare-title .ai-dot { width:10px; height:10px; background:#60a5fa; border-radius:50%; box-shadow:0 0 10px #60a5fa,0 0 4px #60a5fa; animation:pulse-dot 2s infinite; }
@keyframes pulse-dot { 0%,100%{opacity:1;transform:scale(1)} 50%{opacity:.35;transform:scale(.85)} }
.bid-table { width:100%; border-collapse:collapse; table-layout:fixed; }
.bid-table thead th { padding:10px 14px; font-size:12px; font-weight:600; color:#5f6b7a; text-align:center; border-bottom:1px solid rgba(0,0,0,.05); background:#fafbfd; }
.bid-table thead th:first-child { text-align:left; width:140px; }
.bid-table td { padding:10px 14px; text-align:center; font-size:13px; color:var(--text); border-bottom:1px solid #f1f2f5; vertical-align:middle; }
.bid-table td:first-child { text-align:left; padding-left:18px; }
.bid-table td.td-desc { text-align:left; font-size:12px; line-height:1.6; }
.bid-table .old-row td { background:rgba(248,113,113,.03); }
.bid-table .new-row td { background:rgba(74,222,128,.03); }
.bid-ver-tag { display:inline-block; padding:4px 12px; border-radius:10px; font-size:11px; font-weight:600; white-space:nowrap; }
.bid-ver-tag.old { background:rgba(220,38,38,.08); color:#dc2626; }
.bid-ver-tag.new { background:rgba(5,150,105,.08); color:#059669; }
.bid-num { font-size:15px; font-weight:700; }
.bid-num.old { color:#dc2626; }
.bid-num.new { color:#059669; }
/* ---- 应用能力集表格 ---- */
.cap-board { margin:22px 32px 0; background:#fff; border-radius:14px; border:1px solid rgba(0,0,0,.05); overflow:hidden; box-shadow:var(--shadow); }
.cap-title { padding:16px 22px; font-size:17px; font-weight:700; color:#fff; background:linear-gradient(135deg,#0d2550,#1a3d6e,#235491); display:flex; align-items:center; gap:10px; }
.cap-title .ct-hint { margin-left:auto; font-size:11.5px; font-weight:600; color:rgba(196,216,250,.72); letter-spacing:.2px; }
.cap-title .ai-dot { width:10px; height:10px; background:#60a5fa; border-radius:50%; box-shadow:0 0 10px #60a5fa,0 0 4px #60a5fa; animation:pulse-dot 2s infinite; }
/* 能力集图片：长表格放进固定高度的滚动框里（和「客户画像」一样的下滑查看方式），避免整页被拉太长 */
.cap-img-wrap { border-radius:0 0 12px 12px; overflow-y:auto; overflow-x:hidden; max-height:660px;
  overscroll-behavior:contain; background:#fff; scrollbar-width:thin; }
.cap-img-wrap::-webkit-scrollbar { width:9px; }
.cap-img-wrap::-webkit-scrollbar-track { background:rgba(15,35,80,.045); }
.cap-img-wrap::-webkit-scrollbar-thumb { background:rgba(20,40,90,.2); border-radius:5px; }
.cap-img-wrap::-webkit-scrollbar-thumb:hover { background:rgba(20,40,90,.32); }
.cap-img-wrap img { width:100%; display:block; border:none; }
.cap-img-wrap img + img { margin-top:2px; }
.cap-table-wrap { overflow-x:auto; border-radius:0 0 12px 12px; }
.cap-table { width:100%; border-collapse:collapse; min-width:1200px; }
.cap-table thead th { padding:11px 16px; font-size:12px; font-weight:700; color:#fff; text-align:left; background:#16355f; border-bottom:2px solid rgba(255,255,255,.08); letter-spacing:.4px; white-space:nowrap; }
.cap-table td { padding:11px 16px; font-size:13px; color:var(--text); border-bottom:1px solid #eef0f4; vertical-align:middle; line-height:1.55; }
.cap-table tbody tr:nth-child(even) td { background:rgba(15,43,92,.02); }
.cap-table tbody tr:hover td { background:rgba(37,99,235,.045); }
.cap-table td.cap-cat { width:150px; background:#f2f6fc; border-right:1px solid #e3eaf4; font-weight:700; color:#16355f; text-align:center; vertical-align:middle; }
.cap-table .cap-cat-tag { display:inline-block; padding:5px 14px; border-radius:8px; background:linear-gradient(135deg,#0d2550,#1a3d6e); color:#fff; font-size:12px; font-weight:600; letter-spacing:.5px; }
.cap-table td.cap-skill { width:130px; font-weight:600; color:#0d2550; }
.cap-table td.cap-src { color:#5f6b7a; font-size:12px; white-space:nowrap; }
@media (max-width:768px) {
  .cap-board { margin:16px 16px 0; }
  .cap-table { min-width:640px; }
  .cap-table td { padding:10px 12px; font-size:12px; }
}
.bid-pct { font-size:26px; font-weight:900; }
.bid-pct.old { color:#dc2626; }
.bid-pct.new { color:#059669; }
.bid-note { font-size:11px; color:#5f6b7a; display:block; margin-top:2px; }
.bid-compare-footer { padding:12px 22px; background:#fafbfd; border-top:1px solid rgba(0,0,0,.04); font-size:11px; color:#5f6b7a; }
.bid-compare-footer .boost { color:#059669; font-weight:700; }
/* ---- 一线增量情况 ---- */
.increment-board { background:var(--white); border-radius:var(--r-lg); border:1px solid rgba(0,0,0,.05); margin:28px 0 36px; box-shadow:var(--shadow); overflow:hidden; }
.increment-title { padding:18px 24px; font-size:15px; font-weight:800; color:var(--text); background:linear-gradient(180deg,#fcfdfe,#fff); border-bottom:1px solid rgba(0,0,0,.04); display:flex; align-items:center; }
.increment-body { display:flex; gap:24px; padding:24px; align-items:center; }
.increment-gallery { display:grid; grid-template-columns:repeat(auto-fit, minmax(280px, 1fr)); gap:24px; padding:24px; }
.increment-footer { padding:14px 24px; background:#f8fafc; border-top:1px solid rgba(0,0,0,.04); font-size:13px; color:#5f6b7a; font-weight:600; text-align:right; }
.increment-img { flex:1; min-width:0; }
.increment-img figure, .increment-gallery figure { margin:0; border-radius:12px; overflow:hidden; border:1px solid rgba(0,0,0,.06); cursor:zoom-in; transition:transform .25s ease,box-shadow .25s ease; }
.increment-img figure:hover, .increment-gallery figure:hover { transform:scale(1.02); box-shadow:0 12px 40px rgba(0,0,0,.08); }
.increment-img img, .increment-gallery img { width:100%; display:block; object-fit:contain; background:#f6f8fc; }
.increment-img figcaption, .increment-gallery figcaption { padding:10px 14px; font-size:12px; color:#5f6b7a; background:#fff; border-top:1px solid rgba(0,0,0,.04); }
@media (max-width:768px) {
  .increment-gallery { grid-template-columns:1fr; }
}
@media (max-width:768px) { .bid-flow-platform { flex-direction:column; } .bid-table thead th:first-child { width:100px; } }
.scene-divider { max-width:1120px; margin:0 auto; border:none; border-top:1px solid rgba(0,0,0,.05); }
.bg-opp  { background:linear-gradient(180deg,#eaf2ff 0%,#f7f8fb 50%,#f7f8fb 100%); }
.bg-visit{ background:linear-gradient(180deg,#e8faf5 0%,#f7f8fb 50%,#f7f8fb 100%); }
.bg-proj { background:linear-gradient(180deg,#f0eaff 0%,#f7f8fb 50%,#f7f8fb 100%); }
.bg-bid  { background:linear-gradient(180deg,#fff6ed 0%,#f7f8fb 50%,#f7f8fb 100%); }
.bg-knowledge { background:linear-gradient(180deg,#eef1ff 0%,#f7f8fb 50%,#f7f8fb 100%); }
.bg-skill { background:linear-gradient(180deg,#e2f2ff 0%,#f7f8fb 50%,#f7f8fb 100%); }
.bg-channel { background:linear-gradient(180deg,#e6f7f5 0%,#f7f8fb 50%,#f7f8fb 100%); }
.stats-strip { background:linear-gradient(120deg,#060f25,#0d2550,#091c3e); border-radius:18px; padding:32px 48px; display:flex; flex-wrap:wrap; gap:40px; justify-content:space-around; margin:0 0 48px; box-shadow:0 8px 32px rgba(6,15,37,.15); }
.app-stats-strip { background:linear-gradient(135deg,#f6f9ff,#eaf2ff); border-radius:14px; padding:20px 32px; display:flex; flex-wrap:wrap; gap:32px; justify-content:space-around; margin:0 32px 24px; border:1px solid rgba(59,130,246,.1); }
.app-stats-item { text-align:center; }
.app-stats-num { font-size:28px; font-weight:900; line-height:1.1; background:linear-gradient(135deg,#0d2550,#3b82f6); -webkit-background-clip:text; -webkit-text-fill-color:transparent; }
.app-stats-label { font-size:11px; color:var(--muted); font-weight:500; margin-top:2px; }
.app-stats-note-inline { font-size:9px; color:var(--muted); font-weight:400; display:flex; align-items:center; justify-content:center; flex:0 0 auto; padding-left:12px; }
.ss-item { text-align:center; }
.ss-num { font-size:38px; font-weight:900; line-height:1; background:linear-gradient(90deg,#fbbf24,#fb923c,#f97316); -webkit-background-clip:text; -webkit-text-fill-color:transparent; }
.ss-label { font-size:13px; color:rgba(255,255,255,.5); margin-top:6px; }
footer { text-align:center; padding:40px 24px 72px; border-top:1px solid rgba(0,0,0,.05); font-size:13px; color:var(--muted); }
footer .ft-logo { font-size:18px; font-weight:900; color:var(--brand-teal); margin-bottom:8px; }
.view-counter { display:inline-flex; align-items:center; gap:6px; margin-top:12px; padding:8px 22px; background:linear-gradient(135deg,#0d2550,#1a3d6e); border-radius:28px; color:#fff; font-size:13px; font-weight:600; letter-spacing:.3px; box-shadow:0 4px 20px rgba(13,37,80,.25); transition:all var(--transition); }
.view-counter:hover { transform:translateY(-1px); box-shadow:0 6px 24px rgba(13,37,80,.3); }
.view-counter .vc-icon { font-size:16px; }
.view-counter .vc-num { font-size:22px; font-weight:900; background:linear-gradient(90deg,#60a5fa,#a78bfa); -webkit-background-clip:text; -webkit-text-fill-color:transparent; }

/* ============ 招投标步骤 ============ */
.bid-steps-grid { display:grid; grid-template-columns:1fr 40px 1fr 40px 1fr; gap:0; align-items:center; margin-bottom:40px; }
.bid-step-card { background:#fff; border-radius:16px; border:2px solid; padding:24px; text-align:center; box-shadow:var(--shadow); transition:all var(--transition); }
.bid-step-card:hover { box-shadow:var(--shadow-md); transform:translateY(-2px); }
.bid-step-title { font-weight:800; font-size:15px; margin-bottom:8px; }
.bid-step-list { font-size:13px; color:var(--muted); text-align:left; padding-left:16px; line-height:1.9; }
.bid-step-arrow { text-align:center; font-size:22px; color:#cbd5e1; font-weight:700; }

/* ============ 移动端适配 ============ */
@media (max-width:768px) {
  nav { height:52px; padding:0 14px; }
  .nav-brand { font-size:12px; gap:4px; }
  .nav-brand img { height:22px; }
  .nav-brand span { display:none; }
  .nav-tabs { gap:2px; overflow-x:auto; flex-wrap:nowrap; -webkit-overflow-scrolling:touch; scrollbar-width:none; }
  .nav-tabs::-webkit-scrollbar { display:none; }
  .nav-tabs a { padding:5px 8px; font-size:12px; border-radius:14px; white-space:nowrap; flex-shrink:0; }
  .nav-right { display:none; }

  .hero { padding:84px 16px 32px; min-height:auto; }
  .hero-inner { padding:0 8px; animation:none; }
  .hero-logo-img { height:38px; }
  .hero-logo-dept { font-size:14px; }
  .hero h1 { font-size:26px; }
  .hero-sub { font-size:13px; max-width:100%; }
  .hero-action { font-size:12px; max-width:100%; margin-top:-18px; padding:0 8px; }
  .hero-card { width:calc(50% - 8px); padding:16px 10px; border-radius:16px; }
  .hero-card .hc-icon { font-size:30px; }
  .hero-card .hc-name { font-size:13px; }
  .hero-card .hc-desc { font-size:11px; }
  .hero-incentive-badge { min-width:0; flex:1; padding:14px 10px; border-radius:14px; }
  .hero-incentive-badge .hb-title { font-size:12px; }
  .hero-incentive-badge .hb-sub { font-size:10px; }
  .hero-incentive-badge .hb-link { font-size:9px; }
  .hero-incentive-label { font-size:18px; }
  .hero-incentive-desc { font-size:11px; }

  .scene-nav { top:52px; padding:8px 0; }
  .scene-nav-inner { padding:0 12px; gap:6px; overflow-x:auto; flex-wrap:nowrap; -webkit-overflow-scrolling:touch; scrollbar-width:none; justify-content:flex-start; }
  .scene-nav-inner::-webkit-scrollbar { display:none; }
  .scene-nav-btn { padding:8px 14px; font-size:13px; white-space:nowrap; flex-shrink:0; border-radius:20px; }
  .scene-nav-hint { display:none; }

  .scene-section { padding:36px 14px 56px; }
  .scene-header { gap:10px; margin-bottom:32px; flex-wrap:wrap; }
  .scene-header-ico { width:40px; height:40px; font-size:18px; border-radius:12px; }
  .scene-title { font-size:21px; }
  .scene-sub { font-size:12px; }
  .scene-count { font-size:11px; padding:4px 12px; }
  .scene-timeline { padding:0 10px; }
  .scene-timeline::before { left:24px; top:40px; bottom:40px; }

  .app-block { margin-bottom:24px; border-radius:16px; }
  .app-block-header { padding:16px 18px; gap:10px; flex-wrap:wrap; }
  .app-num-badge { width:30px; height:30px; font-size:12px; border-radius:10px; }
  .app-title { font-size:16px; }
  .app-subtitle { font-size:11px; }
  .app-guide-card { padding:8px 14px; font-size:12px; gap:6px; border-radius:10px; }
  .app-guide-card svg { width:14px; height:14px; }

  .app-content { grid-template-columns:1fr; }
  .app-col { padding:20px 18px; border-right:none; border-bottom:1px solid rgba(0,0,0,.04); }
  .app-col:last-child { border-bottom:none; }
  .app-col p { font-size:13px; }
  .app-col ul { font-size:13px; }
  .col-emoji-bg { font-size:48px; }

  .app-stats-strip { padding:16px 18px; gap:16px; margin:0 16px 16px; }
  .app-stats-num { font-size:22px; }
  .app-stats-label { font-size:10px; }
  .app-stats-note-inline { font-size:8px; padding-left:8px; }

  .app-video-panel { padding:16px 16px 20px; }
  .video-wrapper video { max-height:240px; }
  .video-wrapper { min-height:200px; border-radius:10px; }
  .vp-icon { width:56px; height:56px; font-size:22px; }
  .img-gallery,.img-gallery.col2,.img-gallery.col1,.img-gallery.col5 { grid-template-columns:1fr; gap:12px; }
  .img-gallery img { max-height:300px; }

  .profile-preview { padding:0 14px 20px; }
  .profile-preview-frame { height:380px; }
  .profile-preview-label { font-size:11px; padding:16px 0 10px; }

  .bid-compare-title { font-size:14px; padding:12px 16px; }
  .bid-table { display:block; overflow-x:auto; -webkit-overflow-scrolling:touch; }
  .bid-table thead th { font-size:11px; padding:8px 10px; }
  .bid-table td { font-size:12px; padding:8px 10px; }
  .bid-table td.td-desc { font-size:11px; }
  .bid-pct { font-size:20px; }
  .bid-compare-footer { font-size:9px; padding:8px 16px; }

  .stats-strip { padding:20px 18px; gap:18px; border-radius:14px; }
  .ss-num { font-size:28px; }

  .bid-steps-grid { grid-template-columns:1fr !important; gap:10px !important; margin-bottom:28px; }
  .bid-step-arrow { display:none; }
  .bid-step-card { padding:16px 14px; border-radius:14px; }
  .bid-step-title { font-size:13px; }
  .bid-step-list { font-size:11px; }

  footer { padding:28px 16px 48px; font-size:12px; }
  .view-counter { padding:6px 16px; font-size:11px; }
  .view-counter .vc-num { font-size:16px; }
}
/* ── 未来规划（独立模块）── */
.future-section { max-width:1000px; margin:56px auto 0; padding:0 24px; }
.future-card { background:#fff; border-radius:18px; border:1px solid rgba(0,0,0,.05); overflow:hidden; box-shadow:var(--shadow); transition:box-shadow var(--transition); }
.future-card:hover { box-shadow:var(--shadow-lg); }
.future-header { background:linear-gradient(135deg,#0d2550 0%,#1a3d6e 40%,#2a5599 100%); padding:36px 40px; color:#fff; position:relative; overflow:hidden; }
.future-header::before { content:''; position:absolute; top:-30%; right:-10%; width:220px; height:220px; background:rgba(255,255,255,.04); border-radius:50%; }
.future-header::after { content:''; position:absolute; bottom:-20%; right:15%; width:140px; height:140px; background:rgba(255,255,255,.03); border-radius:50%; }
.future-header-inner { position:relative;z-index:1; }
.future-header h2 { font-size:24px;font-weight:700;margin:0 0 8px;letter-spacing:1px; }
.future-header p { font-size:14px;opacity:.85;margin:0; }
.future-body { padding:32px 40px 36px; }
.fp-item { margin-bottom:28px; }
.fp-item:last-child { margin-bottom:0; }
.fp-label { display:inline-flex;align-items:center;gap:8px;font-size:15px;font-weight:700;color:#0d2550;margin-bottom:12px;padding-bottom:8px;border-bottom:2px solid #e5e7eb; }
.fp-item p { font-size:14px;color:#374151;line-height:1.85;margin:8px 0; }
.fp-item ul { list-style:none;padding:0;margin:8px 0 0;padding-left:4px; }
.fp-item ul li { font-size:14px;color:#374151;padding:6px 0 6px 20px;position:relative;line-height:1.75; }
.fp-item ul li::before { content:'•';position:absolute;left:2px;color:#3b82f6;font-weight:700;font-size:16px;top:6px; }
.fp-item strong { color:#0d2550;font-weight:700; }
.fp-path-tag { display:inline-flex;align-items:center;gap:8px;padding:8px 20px;background:#eaf2ff;border-radius:10px;border:1px solid rgba(59,130,246,.2);font-size:13px;color:#1d4ed8;font-weight:600;margin-top:14px; transition:all var(--transition); }
.fp-path-tag:hover { background:#dbe9ff; transform:translateX(3px); }

@media(max-width:720px){
  .future-section { margin:36px auto 0; padding:0 16px; }
  .future-header { padding:24px 20px; }
  .future-header h2 { font-size:18px; }
  .future-body { padding:20px 18px; }
}
/* 点赞评论模块 */
.feedback-section { max-width:680px; margin:0 auto; padding:36px 24px 20px; }
.feedback-card { background:#fff; border-radius:14px; border:1px solid rgba(0,0,0,.05); padding:28px 32px; box-shadow:var(--shadow); transition:box-shadow var(--transition); }
.feedback-card:hover { box-shadow:var(--shadow-md); }
.feedback-header { text-align:center; margin-bottom:22px; }
.feedback-header h3 { font-size:18px; font-weight:700; color:var(--text); margin:0 0 6px; }
.feedback-header p { font-size:13px; color:var(--muted); margin:0; }
.fb-like-row { display:flex; align-items:center; justify-content:center; gap:14px; margin-bottom:22px; }
.fb-like-btn { display:inline-flex; align-items:center; gap:8px; padding:12px 26px; border-radius:28px; border:2px solid #e3e5e8; background:#fff; font-size:15px; font-weight:600; color:var(--text); cursor:pointer; transition:all var(--transition); user-select:none; }
.fb-like-btn:hover { border-color:#ef4444; color:#ef4444; transform:scale(1.02); }
.fb-like-btn.liked { border-color:#ef4444; background:#fef2f2; color:#ef4444; }
.fb-like-count { font-size:14px; color:var(--muted); }
.fb-comments { border-top:1px solid #f1f2f5; padding-top:18px; }
.fb-comment-form { display:flex; gap:10px; margin-bottom:16px; flex-wrap:wrap; }
.fb-comment-form input { flex:0 0 100px; padding:10px 14px; border:1px solid #e3e5e8; border-radius:10px; font-size:13px; outline:none; transition:border-color var(--transition); background:#f9fafb; }
.fb-comment-form input:focus { border-color:var(--brand-teal); background:#fff; }
.fb-comment-form textarea { flex:1; min-width:200px; padding:10px 14px; border:1px solid #e3e5e8; border-radius:10px; font-size:13px; resize:vertical; min-height:38px; outline:none; font-family:inherit; background:#f9fafb; transition:border-color var(--transition); }
.fb-comment-form textarea:focus { border-color:var(--brand-teal); background:#fff; }
.fb-comment-form button { padding:10px 22px; background:linear-gradient(135deg,#0d2550,#1a3d6e); color:#fff; border:none; border-radius:10px; font-size:13px; font-weight:600; cursor:pointer; transition:all var(--transition); }
.fb-comment-form button:hover { opacity:.92; transform:translateY(-1px); box-shadow:0 4px 12px rgba(13,37,80,.25); }
.fb-comment-list { max-height:320px; overflow-y:auto; }
.fb-comment-item { padding:12px 0; border-bottom:1px solid #f5f6f8; }
.fb-comment-item:last-child { border-bottom:none; }
.fb-comment-meta { font-size:11px; color:var(--muted); margin-bottom:4px; display:flex; justify-content:space-between; }
.fb-comment-meta strong { color:var(--text); font-size:13px; }
.fb-comment-text { font-size:14px; color:var(--text); line-height:1.6; }
.fb-comment-del { font-size:11px; color:#ccc; cursor:pointer; background:none; border:none; padding:0 4px; transition:color var(--transition); }
.fb-comment-del:hover { color:#ef4444; }
.fb-reply-btn { font-size:11px; color:var(--brand-teal); cursor:pointer; background:none; border:none; padding:0 4px; transition:opacity var(--transition); }
.fb-reply-btn:hover { text-decoration:underline; opacity:.8; }
.fb-reply-area { margin:8px 0 0 0; display:none; }
.fb-reply-area.show { display:block; }
.fb-reply-area textarea { width:100%; padding:8px 12px; border:1px solid #e3e5e8; border-radius:8px; font-size:12px; resize:vertical; min-height:32px; outline:none; font-family:inherit; box-sizing:border-box; background:#f9fafb; transition:border-color var(--transition); }
.fb-reply-area textarea:focus { border-color:var(--brand-teal); background:#fff; }
.fb-reply-area button { margin-top:6px; padding:5px 14px; background:var(--brand-teal); color:#fff; border:none; border-radius:8px; font-size:12px; cursor:pointer; transition:all var(--transition); }
.fb-reply-area button:hover { opacity:.9; transform:translateY(-1px); }
.fb-reply-item { padding:6px 0 6px 16px; margin:3px 0; border-left:2px solid #e3e5e8; font-size:13px; color:var(--text); }
.fb-reply-item strong { font-size:12px; color:var(--text); }
.fb-reply-item span { font-size:10px; color:var(--muted); margin-left:4px; }
.fb-empty { text-align:center; font-size:13px; color:var(--muted); padding:24px 0; }
.fb-loading { text-align:center; font-size:12px; color:var(--muted); padding:12px; }
@media (max-width:768px) {
  .feedback-section { padding:24px 14px 12px; }
  .feedback-card { padding:20px 16px; }
  .fb-comment-form { flex-direction:column; }
  .fb-comment-form input { flex:1; }
}
/* ═══════════ 首页卡片网格（Landing Cards）═══════════ */
.landing-section { background: linear-gradient(180deg, #070e2a 0%, #0a1638 40%, #0d1f52 100%); padding: 28px 28px 50px; position: relative; overflow: hidden; }
.landing-section::before { content:''; position:absolute; inset:0; background: radial-gradient(ellipse 60% 50% at 50% 20%, rgba(59,130,246,.06) 0%, transparent 70%); pointer-events:none; }
.landing-inner { max-width: 1120px; margin: 0 auto; position: relative; z-index: 1; }
.landing-title { text-align: center; font-size: 32px; font-weight: 900; color: #fff; margin-bottom: 8px; letter-spacing: -.3px; }
.landing-title em { background: linear-gradient(135deg, #5eead4, #818cf8, #60a5fa); -webkit-background-clip: text; -webkit-text-fill-color: transparent; font-style: normal; }
.landing-sub { text-align: center; font-size: 15px; color: rgba(255,255,255,.6); margin-bottom: 32px; line-height: 1.5; }
.cards-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 20px; }
@media (max-width: 900px) { .cards-grid { grid-template-columns: repeat(2, 1fr); } }
@media (max-width: 560px) { .cards-grid { grid-template-columns: 1fr; } }

.card-item { background: linear-gradient(145deg, rgba(15,43,92,.92), rgba(26,58,118,.78)); border: 1px solid rgba(255,255,255,.08); border-radius: 20px; padding: 28px; color: #fff; text-decoration: none; transition: all var(--transition); display: block; position: relative; overflow: hidden; cursor: pointer; }
.card-item:hover { transform: translateY(-6px); border-color: rgba(99,162,255,.3); box-shadow: 0 20px 56px rgba(0,0,0,.35), 0 0 0 1px rgba(255,255,255,.06); }
.card-item::before { content:''; position: absolute; top: 0; right: 0; width: 140px; height: 140px; background: rgba(255,255,255,.04); border-radius: 50%; transform: translate(40%, -40%); transition: all var(--transition); }
.card-item:hover::before { transform: translate(30%, -30%) scale(1.1); background: rgba(255,255,255,.07); }
.card-icon-wrap { display: flex; align-items: center; gap: 14px; margin-bottom: 16px; }
.card-icon { width: 48px; height: 48px; border-radius: 14px; display: flex; align-items: center; justify-content: center; font-size: 24px; flex-shrink: 0; box-shadow: 0 4px 16px rgba(0,0,0,.2); }
.card-title-group { min-width: 0; }
.card-title { font-size: 18px; font-weight: 800; margin-bottom: 3px; letter-spacing: -.2px; }
.card-en { font-size: 11px; color: rgba(255,255,255,.4); font-weight: 500; letter-spacing: 1px; text-transform: uppercase; }
.card-count { display: inline-block; margin-left: 8px; padding: 2px 10px; border-radius: 6px; font-size: 11px; font-weight: 700; background: rgba(99,162,255,.15); color: #60a5fa; border: 1px solid rgba(99,162,255,.2); vertical-align: middle; }
.card-desc { font-size: 13px; color: rgba(255,255,255,.55); line-height: 1.7; margin-bottom: 16px; min-height: 36px; }
.card-tags { display: flex; flex-wrap: wrap; gap: 8px; }
.card-tag { padding: 5px 12px; border-radius: 8px; font-size: 12px; font-weight: 500; background: rgba(255,255,255,.07); color: rgba(255,255,255,.65); border: 1px solid rgba(255,255,255,.06); transition: all .2s; }
.card-item:hover .card-tag { background: rgba(255,255,255,.12); color: rgba(255,255,255,.85); }
.card-arrow { position: absolute; bottom: 20px; right: 20px; font-size: 18px; color: rgba(255,255,255,.2); transition: all var(--transition); }
.card-item:hover .card-arrow { color: rgba(255,255,255,.6); transform: translateX(3px); }

/* ═══════════ 详情页导航栏 ═══════════ */
.scene-detail-nav { display: flex; align-items: center; gap: 16px; padding: 20px 28px; background: linear-gradient(135deg, #0d2550, #1a3d6e); color: #fff; border-radius: 0 0 16px 16px; margin-bottom: 24px; }
.scene-detail-nav .back-btn { display: inline-flex; align-items: center; gap: 6px; padding: 8px 16px; border-radius: 10px; background: rgba(255,255,255,.1); color: rgba(255,255,255,.8); font-size: 13px; font-weight: 600; text-decoration: none; border: 1px solid rgba(255,255,255,.1); transition: all var(--transition); }
.scene-detail-nav .back-btn:hover { background: rgba(255,255,255,.18); color: #fff; }
.scene-detail-nav .back-btn + .back-btn { background: rgba(94,234,212,.1); border-color: rgba(94,234,212,.2); color: #5eead4; }
.scene-detail-nav .back-btn + .back-btn:hover { background: rgba(94,234,212,.2); color: #fff; }
.scene-detail-nav .nav-title { font-size: 18px; font-weight: 700; flex: 1; text-align: center; }
/* 新增「超级数字员工」入口后，标题在宽屏下改为绝对居中 */
@media (min-width: 1100px) {
  .scene-detail-nav { position: relative; }
  .scene-detail-nav .nav-title { position: absolute; left: 50%; top: 50%; transform: translate(-50%,-50%);
    flex: none; text-align: center; white-space: nowrap; pointer-events: none; }
  .scene-detail-nav .nav-de-btn { margin-left: auto; }
}
.scene-detail-nav .nav-pager { display: flex; gap: 10px; }
.scene-detail-nav .pager-btn { padding: 8px 14px; border-radius: 10px; background: rgba(255,255,255,.08); color: rgba(255,255,255,.7); font-size: 13px; font-weight: 600; text-decoration: none; border: 1px solid rgba(255,255,255,.08); transition: all var(--transition); }
.scene-detail-nav .pager-btn:hover { background: rgba(255,255,255,.15); color: #fff; }
.scene-detail-nav .pager-btn.disabled { opacity: .3; pointer-events: none; }

/* 详情页容器 */
.detail-wrap { max-width: 1120px; margin: 0 auto; padding: 0 28px 60px; }

/* 移动端适配 */
@media (max-width: 768px) {
  .landing-section { padding: 24px 16px 32px; }
  .landing-title { font-size: 24px; }
  .landing-sub { font-size: 13px; margin-bottom: 32px; }
  .card-item { padding: 20px; border-radius: 16px; }
  .card-icon { width: 40px; height: 40px; font-size: 20px; border-radius: 12px; }
  .card-title { font-size: 16px; }
  .card-desc { font-size: 12px; margin-bottom: 12px; }
  .card-tag { font-size: 11px; padding: 4px 10px; }
  .scene-detail-nav { padding: 14px 16px; gap: 10px; flex-wrap: wrap; }
  .scene-detail-nav .nav-title { font-size: 15px; order: -1; width: 100%; text-align: left; margin-bottom: 4px; }
  .scene-detail-nav .back-btn { font-size: 12px; padding: 6px 12px; }
  .scene-detail-nav .pager-btn { font-size: 12px; padding: 6px 10px; }
  .detail-wrap { padding: 0 14px 40px; }
}

/* ═══════════ 营销+AI 业务架构section ═══════════ */
.arch-section { background: linear-gradient(180deg, #060f25 0%, #0a1638 60%, #070e2a 100%); padding: 40px 28px 55px; position: relative; overflow: hidden; }
.arch-section::before { content:''; position:absolute; inset:0; background: radial-gradient(ellipse 70% 50% at 50% 30%, rgba(91,63,212,.08) 0%, transparent 70%); pointer-events:none; }
.arch-section::after { content:''; position:absolute; inset:0; background-image: radial-gradient(circle at 1px 1px, rgba(99,140,230,.06) 1px, transparent 0); background-size: 28px 28px; pointer-events:none; }
.arch-inner { max-width: 1180px; margin: 0 auto; position: relative; z-index: 1; }
.arch-title { text-align: center; font-size: 38px; font-weight: 900; color: #fff; margin-bottom: 12px; letter-spacing: -.5px; }
.arch-title .at-pill { display: inline-block; padding: 2px 18px; margin: 0 6px; border-radius: 14px; background: linear-gradient(135deg, #5eead4 0%, #818cf8 50%, #60a5fa 100%); -webkit-background-clip: text; background-clip: text; -webkit-text-fill-color: transparent; }
.arch-sub { text-align: center; font-size: 15px; color: rgba(255,255,255,.6); margin: 0 auto 18px; line-height: 1.5; max-width: 100%; padding: 0 16px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.arch-sub strong { color: #5eead4; font-weight: 700; }

/* 4维卡片网格 */
.arch-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 20px; position: relative; }
.arch-card { background: linear-gradient(165deg, rgba(15,43,92,.85) 0%, rgba(26,58,118,.7) 100%); border: 1px solid rgba(255,255,255,.08); border-radius: 22px; padding: 28px 24px 24px; position: relative; transition: all var(--transition); overflow: hidden; }
.arch-card::before { content: ''; position: absolute; top: 0; left: 0; right: 0; height: 3px; }
.arch-card:hover { transform: translateY(-6px); border-color: rgba(99,162,255,.3); box-shadow: 0 20px 56px rgba(0,0,0,.4), 0 0 0 1px rgba(255,255,255,.06); }
.arch-card[data-color="blue"]::before { background: linear-gradient(90deg, #3b82f6, #60a5fa); }
.arch-card[data-color="purple"]::before { background: linear-gradient(90deg, #8b5cf6, #c084fc); }
.arch-card[data-color="orange"]::before { background: linear-gradient(90deg, #f59e0b, #fb923c); }
.arch-card[data-color="teal"]::before { background: linear-gradient(90deg, #10b981, #5eead4); }
.arch-card[data-color="blue"] .ac-icon { background: linear-gradient(135deg, #1e40af, #3b82f6); }
.arch-card[data-color="purple"] .ac-icon { background: linear-gradient(135deg, #6d28d9, #8b5cf6); }
.arch-card[data-color="orange"] .ac-icon { background: linear-gradient(135deg, #d97706, #f59e0b); }
.arch-card[data-color="teal"] .ac-icon { background: linear-gradient(135deg, #047857, #10b981); }
.arch-card-top { display: flex; align-items: center; gap: 12px; margin-bottom: 16px; }
.ac-icon { width: 44px; height: 44px; border-radius: 13px; display: flex; align-items: center; justify-content: center; font-size: 22px; box-shadow: 0 6px 18px rgba(0,0,0,.25); }
.ac-name { font-size: 18px; font-weight: 800; color: #fff; letter-spacing: -.2px; }
.ac-en { font-size: 11px; color: rgba(255,255,255,.4); font-weight: 600; letter-spacing: 1.2px; text-transform: uppercase; margin-top: 2px; }
.ac-desc { font-size: 12px; color: rgba(255,255,255,.55); line-height: 1.7; margin-bottom: 16px; min-height: 50px; }
.ac-divider { height: 1px; background: rgba(255,255,255,.06); margin: 14px 0 14px; }
.ac-divider-label { font-size: 11px; color: rgba(255,255,255,.35); font-weight: 600; letter-spacing: 1.5px; text-transform: uppercase; margin-bottom: 10px; }
.ac-apps { display: flex; flex-direction: column; gap: 8px; }
.ac-app { display: flex; align-items: center; gap: 8px; padding: 8px 12px; border-radius: 10px; background: rgba(255,255,255,.04); border: 1px solid rgba(255,255,255,.05); font-size: 12px; color: rgba(255,255,255,.78); transition: all .2s; }
.ac-app:hover { background: rgba(99,162,255,.1); border-color: rgba(99,162,255,.2); color: #fff; }
.ac-app-dot { width: 5px; height: 5px; border-radius: 50%; flex-shrink: 0; }
.arch-card[data-color="blue"] .ac-app-dot { background: #60a5fa; box-shadow: 0 0 6px #60a5fa; }
.arch-card[data-color="purple"] .ac-app-dot { background: #c084fc; box-shadow: 0 0 6px #c084fc; }
.arch-card[data-color="orange"] .ac-app-dot { background: #fb923c; box-shadow: 0 0 6px #fb923c; }
.arch-card[data-color="teal"] .ac-app-dot { background: #5eead4; box-shadow: 0 0 6px #5eead4; }
.ac-app-link { color: rgba(255,255,255,.78); text-decoration: none; transition: color .2s; }
.ac-app-link:hover { color: #5eead4; text-decoration: underline; }
.arch-card-linkable { display: block; text-decoration: none; color: inherit; cursor: pointer; transition: transform .2s, box-shadow .2s; }
.arch-card-linkable:hover { transform: translateY(-3px); box-shadow: 0 12px 36px rgba(94,234,212,.2); }

@media (max-width: 900px) { .arch-grid { grid-template-columns: repeat(2, 1fr); } .arch-title { font-size: 28px; } .arch-sub { font-size: 14px; margin-bottom: 16px; } }
@media (max-width: 560px) { .arch-grid { grid-template-columns: 1fr; } }

/* ═══════════ 激励section（浅色大卡片）═══════════ */
.inc-section { background: linear-gradient(180deg, #060f25 0%, #0a1638 50%, #0d1f52 100%); padding: 50px 28px 55px; position: relative; overflow: hidden; }
.inc-section::before { content:''; position:absolute; inset:0; background: radial-gradient(ellipse 60% 50% at 50% 25%, rgba(245,158,11,.06) 0%, transparent 70%); pointer-events:none; }
.inc-inner { max-width: 1120px; margin: 0 auto; position: relative; z-index: 1; }
.inc-header { text-align: center; margin-bottom: 32px; }
.inc-title { font-size: 32px; font-weight: 900; color: #fff; margin-bottom: 8px; letter-spacing: -.3px; }
.inc-title em { background: linear-gradient(135deg, #fbbf24, #f59e0b, #fb923c); -webkit-background-clip: text; -webkit-text-fill-color: transparent; font-style: normal; }
.inc-sub { font-size: 15px; color: rgba(255,255,255,.6); max-width: 100%; line-height: 1.5; padding: 0 16px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.inc-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 20px; }
.inc-action { text-align: center; margin-top: 32px; font-size: 14px; color: #60a5fa; font-weight: 500; letter-spacing: .2px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-shadow: 0 0 24px rgba(96,165,250,.3); }
@media (max-width: 900px) { .inc-grid { grid-template-columns: repeat(2, 1fr); } }
@media (max-width: 560px) { .inc-grid { grid-template-columns: 1fr; } }

.inc-card { background: linear-gradient(145deg, rgba(15,43,92,.92), rgba(26,58,118,.78)); border: 1px solid rgba(255,255,255,.08); border-radius: 20px; padding: 32px 28px 28px; color: #fff; text-decoration: none; transition: all var(--transition); display: block; position: relative; overflow: hidden; }
.inc-card::before { content:''; position: absolute; top: 0; left: 0; right: 0; height: 3px; }
.inc-card[data-glow="gold"]::before { background: linear-gradient(90deg, #fbbf24, #f59e0b, #fb923c); }
.inc-card[data-glow="blue"]::before { background: linear-gradient(90deg, #60a5fa, #818cf8); }
.inc-card[data-glow="purple"]::before { background: linear-gradient(90deg, #a78bfa, #c084fc); }
.inc-card:hover { transform: translateY(-6px); border-color: rgba(99,162,255,.3); box-shadow: 0 20px 56px rgba(0,0,0,.35), 0 0 0 1px rgba(255,255,255,.06); }
.inc-card-icon { width: 56px; height: 56px; border-radius: 16px; display: flex; align-items: center; justify-content: center; font-size: 28px; margin-bottom: 16px; box-shadow: 0 6px 18px rgba(0,0,0,.3); }
.inc-card[data-glow="gold"] .inc-card-icon { background: linear-gradient(135deg, #d97706, #f59e0b); }
.inc-card[data-glow="blue"] .inc-card-icon { background: linear-gradient(135deg, #1e40af, #3b82f6); }
.inc-card[data-glow="purple"] .inc-card-icon { background: linear-gradient(135deg, #6d28d9, #8b5cf6); }
.inc-card-title { font-size: 22px; font-weight: 800; margin-bottom: 4px; letter-spacing: -.2px; }
.inc-card-en { font-size: 11px; color: rgba(255,255,255,.4); font-weight: 600; letter-spacing: 1.5px; text-transform: uppercase; margin-bottom: 14px; }
.inc-card-desc { font-size: 13px; color: rgba(255,255,255,.65); line-height: 1.75; margin-bottom: 20px; min-height: 50px; }
.inc-card-stats { display: flex; gap: 16px; padding: 14px 0; border-top: 1px solid rgba(255,255,255,.06); border-bottom: 1px solid rgba(255,255,255,.06); margin-bottom: 16px; }
.inc-stat-num { font-size: 22px; font-weight: 900; line-height: 1.1; }
.inc-card[data-glow="gold"] .inc-stat-num { color: #fbbf24; }
.inc-card[data-glow="blue"] .inc-stat-num { color: #60a5fa; }
.inc-card[data-glow="purple"] .inc-stat-num { color: #c084fc; }
.inc-stat-label { font-size: 11px; color: rgba(255,255,255,.5); margin-top: 2px; }
.inc-card-tags { display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 16px; }
.inc-card-tag { padding: 4px 10px; border-radius: 6px; font-size: 11px; font-weight: 600; background: rgba(255,255,255,.06); color: rgba(255,255,255,.7); border: 1px solid rgba(255,255,255,.05); }
.inc-card-cta { display: inline-flex; align-items: center; gap: 6px; font-size: 13px; font-weight: 700; color: #60a5fa; transition: all .2s; }
.inc-card:hover .inc-card-cta { gap: 10px; color: #93c5fd; }
.inc-card-cta::after { content: '→'; }
.inc-card-cta.no-arrow { color: rgba(255,255,255,.5); }
.inc-card-cta.no-arrow::after { display: none; }
.inc-card:hover .inc-card-cta.no-arrow { color: rgba(255,255,255,.65); }

@media (max-width: 768px) { .inc-section { padding: 30px 16px 35px; } .inc-title { font-size: 24px; } .inc-card { padding: 24px 20px; } .inc-card-title { font-size: 18px; } .arch-sub, .inc-sub { white-space: normal; text-overflow: clip; } .inc-action { white-space: normal; font-size: 12px; } }

/* ═══════════ 未来规划 首页独立模块 ═══════════ */
.future-home-section { background: linear-gradient(180deg, #060f25 0%, #081530 40%, #050b18 100%); padding: 50px 28px 70px; position: relative; overflow: hidden; }
.future-home-section::before { content:''; position:absolute; inset:0; background: radial-gradient(ellipse 60% 50% at 50% 25%, rgba(94,234,212,.06) 0%, transparent 70%); pointer-events:none; }
.future-home-inner { max-width: 1180px; margin: 0 auto; position: relative; z-index: 1; }
.future-home-header { text-align: center; margin-bottom: 36px; }
.future-home-pill { display: inline-block; padding: 4px 14px; border-radius: 999px; font-size: 12px; font-weight: 700; letter-spacing: 1.5px; color: #5eead4; background: rgba(94,234,212,.08); border: 1px solid rgba(94,234,212,.25); margin-bottom: 12px; }
.future-home-title { font-size: 32px; font-weight: 900; color: #fff; margin-bottom: 8px; letter-spacing: -.3px; }
.future-home-title em { background: linear-gradient(135deg, #5eead4, #818cf8); -webkit-background-clip: text; background-clip: text; -webkit-text-fill-color: transparent; font-style: normal; }
.future-home-subtitle { font-size: 15px; color: rgba(255,255,255,.55); }
.future-home-card { display: grid; grid-template-columns: auto 1fr; gap: 40px; align-items: center; background: linear-gradient(135deg, rgba(13,37,80,.85) 0%, rgba(20,50,95,.6) 50%, rgba(13,37,80,.8) 100%); border: 1px solid rgba(99,140,230,.25); border-radius: 28px; padding: 40px 48px; box-shadow: 0 20px 60px rgba(0,0,0,.3), 0 0 0 1px rgba(94,234,212,.08); transition: all .3s ease; text-decoration: none; position: relative; overflow: hidden; }
.future-home-card:hover { transform: translateY(-6px); box-shadow: 0 28px 80px rgba(0,0,0,.4), 0 0 30px rgba(99,140,230,.15); border-color: rgba(99,140,230,.45); }
.future-home-card::before { content:''; position:absolute; top:0; left:0; width:100%; height:3px; background: linear-gradient(90deg, #5eead4, #818cf8, #60a5fa); }
.future-home-icon { width: 100px; height: 100px; border-radius: 28px; background: linear-gradient(135deg, #0d2550 0%, #1a3d6e 50%, #2a5599 100%); border: 1px solid rgba(99,140,230,.3); display: flex; align-items: center; justify-content: center; font-size: 48px; box-shadow: 0 12px 36px rgba(13,37,80,.5); position: relative; }
.future-home-icon::after { content:''; position:absolute; inset:-2px; border-radius:30px; background: linear-gradient(135deg, #5eead4, #818cf8, #60a5fa); opacity:.25; z-index:-1; filter:blur(12px); }
.future-home-card-title { font-size: 26px; font-weight: 800; color: #fff; margin-bottom: 12px; }
.future-home-card-desc { font-size: 15px; color: rgba(255,255,255,.6); line-height: 1.7; margin-bottom: 22px; }
.future-home-tags { display: flex; flex-wrap: wrap; gap: 10px; margin-bottom: 22px; }
.future-home-tag { padding: 6px 14px; border-radius: 8px; font-size: 13px; font-weight: 600; background: rgba(94,234,212,.08); color: rgba(94,234,212,.9); border: 1px solid rgba(94,234,212,.2); }
.future-home-cta { display: inline-flex; align-items: center; gap: 8px; font-size: 14px; font-weight: 700; color: #5eead4; transition: all .2s; }
.future-home-card:hover .future-home-cta { gap: 12px; color: #93c5fd; }
.future-home-cta::after { content: '→'; }
@media (max-width: 900px) { .future-home-card { grid-template-columns: 1fr; gap: 24px; text-align: center; padding: 32px; } .future-home-icon { width: 80px; height: 80px; font-size: 38px; margin: 0 auto; } .future-home-tags { justify-content: center; } }
@media (max-width: 768px) { .future-home-section { padding: 30px 16px 45px; } .future-home-title { font-size: 24px; } .future-home-card-title { font-size: 20px; } .future-home-card-desc { font-size: 14px; } }

/* ============ 全站移动端基础适配 (≤ 768px) ============ */
@media (max-width: 768px) {
  body { font-size: 14px; }
  h1 { font-size: 26px !important; line-height: 1.3 !important; }
  h1 em { font-size: 22px !important; }
  .hero { padding: 90px 16px 32px !important; min-height: 60vh !important; }
  .hero-inner { padding: 0 !important; }
  .hero-bg-circles span:nth-child(3) { display: none; }
  .hero-sub { font-size: 13px !important; padding: 0 8px; }
  nav { padding: 10px 14px !important; }
  .nav-brand span { font-size: 14px !important; }
  .nav-right { font-size: 11px !important; padding: 3px 10px 3px 3px !important; gap: 6px !important; }
  .nav-right img { height: 20px !important; }
  /* 卡片网格单列 */
  .cards-grid { grid-template-columns: 1fr !important; gap: 14px !important; padding: 20px 16px !important; }
  .card { padding: 18px !important; border-radius: 14px !important; }
  .card-icon { font-size: 28px !important; }
  .card-title { font-size: 18px !important; }
  .card-tags { font-size: 11px !important; }
  /* 场景页 header/title/h1 压缩 */
  .scene-header, .app-header, .scene-title, .inc-title, .arch-title { padding: 24px 16px !important; }
  .scene-title, .arch-title { font-size: 22px !important; }
  .scene-sub, .arch-sub { font-size: 13px !important; line-height: 1.5 !important; white-space: normal !important; }
  .app-title { font-size: 22px !important; line-height: 1.3 !important; }
  .app-subtitle { font-size: 13px !important; }
  .app-tag { font-size: 11px !important; padding: 3px 10px !important; }
  /* 痛点/AI能帮你 单列 */
  .app-col-grid, .bid-flow-platform { grid-template-columns: 1fr !important; flex-direction: column !important; gap: 12px !important; }
  .app-col { padding: 16px !important; }
  .app-col h3, .bid-flow-platform-card h3 { font-size: 15px !important; }
  .app-col ul, .bid-flow-platform-card ul { padding-left: 18px !important; font-size: 13px !important; }
  .app-col p, .bid-flow-platform-card p { font-size: 13px !important; line-height: 1.6 !important; }
  /* 表格横向滚动 */
  .bid-table-wrap, .app-table-wrap, .table-scroll { overflow-x: auto !important; -webkit-overflow-scrolling: touch; }
  .bid-table, .app-table { font-size: 12px !important; min-width: 480px !important; }
  /* 视频控件显示 */
  .video-wrapper video { max-height: 220px !important; }
  .video-wrapper video::-webkit-media-controls-panel { display: flex !important; }
  .app-video-panel, .app-video-detail { padding: 14px 16px !important; }
  /* 截图画廊单列 */
  .img-gallery, .img-gallery.col2, .img-gallery.col3, .img-gallery.col5 { grid-template-columns: 1fr !important; }
  .img-gallery img { height: 180px !important; }
  .img-gallery figcaption { font-size: 12px !important; padding: 8px 12px !important; }
  /* 场景导航按钮 */
  .scene-nav-buttons { padding: 12px 16px !important; gap: 8px !important; }
  .scene-nav-btn, .scene-toggle { font-size: 12px !important; padding: 6px 12px !important; }
  /* 反馈区 */
  .feedback-section, .fb-section { padding: 20px 14px !important; }
  /* 流程卡片栈式 */
  .bid-steps-grid { flex-direction: column !important; gap: 12px !important; }
  .bid-step-arrow { transform: rotate(90deg) !important; }
  .bid-step-card { padding: 16px !important; }
  .bid-step-title { font-size: 16px !important; }
  /* KPI 蓝框 */
  .app-stats-strip { flex-wrap: wrap !important; gap: 8px !important; }
  .app-stats-item { padding: 10px 14px !important; min-width: 90px !important; }
  .app-stats-num { font-size: 18px !important; }
  /* 能力集表格 */
  .cap-board { margin: 16px 14px 0 !important; }
  .cap-title { padding: 12px 16px !important; font-size: 15px !important; }
  .cap-table { min-width: 540px !important; font-size: 11px !important; }
  /* 标讯运营板 */
  .increment-board { margin: 18px 14px !important; }
  .increment-title { padding: 12px 16px !important; font-size: 13px !important; }
  .increment-board .img-gallery { padding: 12px !important; gap: 12px !important; }
  /* 未来规划 */
  .future-section, .inc-section { padding: 28px 16px !important; }
  /* 弹窗/反馈按钮 */
  .feedback-btn, .fb-btn { width: 48px !important; height: 48px !important; font-size: 18px !important; }
}
@media (max-width: 480px) {
  nav .nav-tabs { display: none; }   /* 小屏隐藏主导航,只用场景定位 */
  .app-title-block { gap: 8px !important; }
  .app-stats-num { font-size: 16px !important; }
  .cap-table { min-width: 420px !important; }
  /* 折叠到汉堡菜单其实没必要，已经够精简了 */
}

/* 让视频自动在所有浏览器可播放（点击播放）*/
.video-wrapper video { pointer-events: auto; }
@media (hover: none) and (pointer: coarse) {
  .video-wrapper video::-webkit-media-controls { display: flex !important; }
}

/* ============ 超级数字员工 导航入口按钮 ============ */
.nav-actions { display:flex; align-items:center; gap:10px; }
.nav-de-btn { position:relative; display:inline-flex; align-items:center; gap:7px; padding:7px 17px; border-radius:22px;
  font-size:13.5px; font-weight:700; color:#fff; text-decoration:none; letter-spacing:-.1px; white-space:nowrap;
  background:linear-gradient(118deg,#1f5fd0 0%,#5b3fd4 52%,#b026d3 100%);
  box-shadow:0 4px 16px rgba(58,86,214,.32), inset 0 1px 0 rgba(255,255,255,.3); overflow:hidden;
  transition:transform .28s cubic-bezier(.4,0,.2,1), box-shadow .28s; }
.nav-de-btn::after { content:''; position:absolute; top:0; left:-70%; width:42%; height:100%;
  background:linear-gradient(100deg,transparent,rgba(255,255,255,.5),transparent); transform:skewX(-18deg);
  animation:deShine 4s ease-in-out infinite; }
@keyframes deShine { 0%{left:-70%} 52%{left:135%} 100%{left:135%} }
.nav-de-btn:hover { transform:translateY(-1.5px); box-shadow:0 8px 24px rgba(58,86,214,.44), inset 0 1px 0 rgba(255,255,255,.34); }
.nav-de-btn .nde-dot { width:6px; height:6px; border-radius:50%; background:#7dffc4; box-shadow:0 0 9px #7dffc4; animation:dePulse 2.1s ease-in-out infinite; }
@keyframes dePulse { 0%,100%{opacity:1; transform:scale(1)} 50%{opacity:.3; transform:scale(.82)} }
.nav-de-btn.cur { background:linear-gradient(118deg,#0f2b5c,#24408c); box-shadow:0 3px 14px rgba(15,43,92,.28); }
.nav-de-btn.cur::after { display:none; }
.nav-back-btn { display:inline-flex; align-items:center; gap:6px; padding:7px 16px; border-radius:22px; font-size:13.5px;
  font-weight:600; color:var(--blue); text-decoration:none; background:var(--white); border:1px solid rgba(13,37,80,.14);
  box-shadow:var(--shadow); white-space:nowrap; transition:all .28s; }
.nav-back-btn:hover { background:var(--blue-l); border-color:rgba(13,37,80,.28); transform:translateX(-2px); }
@media (max-width:768px) {
  .nav-actions { gap:7px; }
  /* 窄屏保留文字，避免「超级数字员工」入口只剩一个小圆点 */
  .nav-de-btn { padding:6px 11px; font-size:12px; gap:5px; }
  .nav-de-btn .nde-dot { width:6px; height:6px; }
}
</style>'''


# ============================================================
# 超级数字员工页 专用样式
# ============================================================

# 立牌缩略占位图（22×28 超轻量 WebP，内联进 HTML，0 请求）
# 作用：立牌主图到达前，页面立刻呈现一张模糊海报轮廓，避免长时间白板
DE_BOARD_LQIP = ('data:image/webp;base64,UklGRswAAABXRUJQVlA4IMAAAABwBQCdASoWABwAPwlus1KrpaSisBgIAXAhCWMArj'
                 'z2PLW3+Aex57HhSKwLXYv7X8sdjRU8AM4NINYvP+Vdv91FpKDbI1VrNLY5qvpwqhialuCVhhgmyscLoHHArq'
                 'vvxT9Xbv/9buEjGMc0AQ51h+PTSSgaK9dVABnaLoDDCipviTHJasysd20JO3hjAQKYPZFNFOcIFRBGJV8U7'
                 'Q5g2/NMEO8GjTTtzSMk+TB/KAnfeAJWCi6Gc16IN908UAOgAAA=')

DE_CSS = '''<style>
/* ============ 页面基础 ============ */
.de-body { background:var(--bg); }
.de-wrap { max-width:1280px; margin:0 auto; padding:0 32px; }
.de-pill { display:inline-flex; align-items:center; gap:7px; padding:5px 15px; border-radius:20px; font-size:12.5px; font-weight:700;
  color:#4b36c4; background:linear-gradient(120deg,#eef1ff,#f6efff); border:1px solid rgba(91,63,212,.18); letter-spacing:.2px; }
.de-h2 { font-size:38px; font-weight:800; letter-spacing:-1.15px; line-height:1.24; color:var(--brand-deep); margin:16px 0 12px; }
.de-h2 em { font-style:normal; background:linear-gradient(100deg,#1f5fd0,#7c5ce7 60%,#c026d3); -webkit-background-clip:text; background-clip:text; -webkit-text-fill-color:transparent;
  font-size:__H2_SUB__; }   /* 副标题字号比，content.md「页头副标题字号比」可配（如 .72 = 比主标题小两号） */
/* 页头主标题可点击：标题 + 「进入体验 ↗」提示胶囊 */
.de-h2-a { display:inline-flex; align-items:center; gap:14px; text-decoration:none; color:inherit; }
.de-h2-t { position:relative; }
.de-h2-t::after { content:''; position:absolute; left:0; right:0; bottom:3px; height:2.5px; border-radius:2px;
  background:linear-gradient(90deg,#1f5fd0,#7c5ce7); transform:scaleX(0); transform-origin:left; transition:transform .32s cubic-bezier(.4,0,.2,1); }
.de-h2-a:hover .de-h2-t::after, .de-h2-a:focus-visible .de-h2-t::after { transform:scaleX(1); }
.de-h2-go { display:inline-flex; align-items:center; gap:6px; padding:8px 15px; border-radius:999px;
  font-size:13px; font-weight:800; letter-spacing:.2px; line-height:1; white-space:nowrap; color:#fff;
  background:linear-gradient(135deg,#2f7bff,#7c5ce7);
  box-shadow:0 8px 22px rgba(60,110,255,.38), inset 0 1px 0 rgba(255,255,255,.3);
  animation:deGoGlow 2.8s ease-in-out infinite;
  transition:transform .26s, filter .26s; }
.de-h2-go i { font-style:normal; font-size:14px; line-height:1; transition:transform .26s; }
.de-h2-a:hover .de-h2-go { transform:translateY(-2px); filter:brightness(1.08); }
.de-h2-a:hover .de-h2-go i { transform:translate(2px,-2px); }
@keyframes deGoGlow {
  0%, 100% { box-shadow:0 8px 22px rgba(60,110,255,.34), inset 0 1px 0 rgba(255,255,255,.3); }
  50%      { box-shadow:0 8px 34px rgba(96,144,255,.66), inset 0 1px 0 rgba(255,255,255,.38); }
}
.de-slogan { display:inline-flex; align-items:center; gap:8px; font-size:13px; font-weight:700; color:#2b3a58; }
.de-slogan::before { content:''; width:3px; height:14px; border-radius:2px; flex:none;
  background:linear-gradient(180deg,#1f5fd0,#c026d3); }
.de-lead { font-size:15.5px; color:var(--muted); line-height:1.8; max-width:760px; }
/* 标语 + 描述 同一行 */
.de-tagline { display:flex; align-items:center; flex-wrap:wrap; margin:0 0 15px; }
.de-tagline .de-lead { font-size:13px; font-weight:600; line-height:1.5; max-width:none; color:#5a6784; }
.de-tagsep { width:1px; height:13px; background:rgba(15,35,80,.18); margin:0 10px; flex:none; }
@media (min-width:1160px){ .de-tagline { flex-wrap:nowrap; white-space:nowrap; } }
.de-sec { padding:88px 0; }
.de-sec-head { text-align:center; margin-bottom:48px; }
.de-sec-head .de-lead { margin:0 auto; }
.de-lead-sub { margin:12px auto 0; font-size:13px; color:#8b95a8; }

/* ============ 1. 3D 立牌 ============ */
.de-board-sec { position:relative; padding:64px 0 76px; overflow:hidden;
  background:radial-gradient(ellipse 60% 46% at 22% 34%, #e8efff 0%, transparent 62%),
             radial-gradient(ellipse 50% 40% at 82% 22%, #f2ecff 0%, transparent 60%),
             linear-gradient(180deg,#fbfcff,#f5f7fc); }
.de-board-sec::before { content:''; position:absolute; inset:0; pointer-events:none; opacity:.5;
  background-image:radial-gradient(rgba(30,60,140,.10) 1px, transparent 1px); background-size:26px 26px;
  -webkit-mask-image:radial-gradient(ellipse 62% 58% at 50% 46%, #000 0%, transparent 78%);
  mask-image:radial-gradient(ellipse 62% 58% at 50% 46%, #000 0%, transparent 78%); }
.de-bs-grid { position:relative; z-index:2; display:grid; grid-template-columns:minmax(0,48fr) minmax(0,52fr); gap:46px; align-items:center; }

.de-stage { position:relative; display:flex; align-items:center; justify-content:center; min-height:756px; }
.de-persp { perspective:2100px; perspective-origin:50% 44%; width:100%; display:flex; justify-content:center; position:relative; }
/* 立牌右下角浮层按钮组 */
.de-board-tools { position:absolute; right:calc(50% - min(280px,45%) + 12px); bottom:7%; z-index:9;
  display:flex; flex-direction:column; align-items:flex-end; gap:8px; }
.de-lb-btn { display:inline-flex; align-items:center; gap:6px; padding:8px 14px; border-radius:12px;
  font-size:12.5px; font-weight:700; color:#fff; border:none; cursor:pointer; font-family:inherit; white-space:nowrap;
  background:rgba(13,37,80,.78); backdrop-filter:blur(10px); -webkit-backdrop-filter:blur(10px);
  box-shadow:0 6px 20px rgba(13,37,80,.28); transition:background .25s, transform .25s, box-shadow .25s; }
.de-lb-btn:hover { background:rgba(13,37,80,.94); transform:translateY(-2px); box-shadow:0 10px 26px rgba(13,37,80,.36); }
.de-lb-btn .ic { font-size:14px; line-height:1; }
.de-board.dragging .de-board-tools { opacity:.35; transition:opacity .2s; }
.de-board { position:relative; width:min(560px,90%); aspect-ratio:4200/5360; transform-style:preserve-3d;
  transform:rotateX(var(--de-tilt,0deg)) rotateY(var(--de-rot,-15deg)); transition:transform .1s linear;
  cursor:grab; touch-action:pan-y; will-change:transform; }
.de-board.dragging { cursor:grabbing; transition:none; }
.de-board.settling { transition:transform .68s cubic-bezier(.22,1.05,.36,1); }
.de-board.dragging .de-bhint { opacity:0; }

.de-face { position:absolute; inset:0; border-radius:10px; backface-visibility:hidden; -webkit-backface-visibility:hidden; overflow:hidden; }
.de-front { transform:translateZ(9px); background:#fff; box-shadow:0 2px 0 rgba(255,255,255,.9) inset, 0 0 0 1px rgba(15,35,80,.07); }
.de-back { transform:translateZ(-9px) rotateY(180deg); background:#fff; box-shadow:0 0 0 1px rgba(15,35,80,.07); }
.de-img { position:absolute; inset:0; width:100%; height:100%; object-fit:fill; display:block; user-select:none; -webkit-user-drag:none; }
/* <picture> 只做格式分支，不要产生盒子，否则 .de-img 的绝对定位父级会错位 */
.de-face picture, .de-front picture, .de-eco-front picture { display:contents; }
/* 内联占位图：主图未到时先铺一层模糊海报轮廓（主图为不透明整图，加载完成后自然完全遮盖） */
.de-lqip { position:absolute; inset:0; width:100%; height:100%; object-fit:fill; display:block;
  filter:blur(6px) saturate(1.04); transform:scale(1.035); pointer-events:none; user-select:none; }

/* 底板边缘：模拟板材厚度 */
.de-edge { position:absolute; top:0; bottom:0; width:18px; pointer-events:none;
  background:linear-gradient(90deg,#e9edf3,#fbfcff 42%,#dfe5ee); }
.de-edge.l { left:0; transform:translateX(-9px) rotateY(-90deg); transform-origin:right center; }
.de-edge.r { right:0; transform:translateX(9px) rotateY(90deg); transform-origin:left center; }

/* 人物分层 */
.de-char { position:absolute; left:33.0952%; top:17.3507%; width:33.5714%; height:60.8209%; transform-origin:50% 100%;
  animation:deIdle 5.2s ease-in-out infinite;
  opacity:0; transition:opacity .42s ease; }
/* 5 个分层全部 load 完成后由 JS 加 .ready 整体淡入，避免"身体→头→手"逐块弹出的拼装感 */
.de-char.ready { opacity:1; }
.de-l { position:absolute; inset:0; width:100%; height:100%; display:block; pointer-events:none; }
/* ⚠️ 人物分层的转动轴心必须与 media/de_char_*.webp 对应：
   换立牌人物（男/女）后跑 tools/mkchar.py，把它打印的两个百分比抄到这里 */
.de-l-head { transform-origin:50.08% 22.30%; }
.de-l-arm  { transform-origin:38.16% 38.61%; }
.de-l-tab  { transform-origin:84.75% 41.87%; }
@keyframes deIdle { 0%,100%{ transform:translateY(0) rotate(0deg);} 50%{ transform:translateY(-5px) rotate(.3deg);} }
/* 动作：打招呼（挥手·不拿笔）/ 转身（人物侧身）/ 转到背面 / 复位 */
.de-arm-wave { opacity:0; transition:opacity .14s; }
.de-char.act-hello .de-l-arm:not(.de-arm-wave) { opacity:0; }
.de-char.act-hello .de-arm-wave { opacity:1; animation:deWave 1.8s cubic-bezier(.36,.07,.19,.97) both; }
.de-char.act-hello .de-l-head { animation:deNodG 1.8s ease-in-out both; }
.de-char.act-turn { transform-origin:50% 60%; animation:deTurnY 1.9s cubic-bezier(.36,.07,.19,.97) both; }
.de-char.act-turn .de-l-head { animation:deNodG 1.9s ease-in-out both; }
@keyframes deWave { 0%{transform:rotate(0)} 14%{transform:rotate(-16deg)} 34%{transform:rotate(9deg)} 54%{transform:rotate(-13deg)} 74%{transform:rotate(6deg)} 88%{transform:rotate(-3deg)} 100%{transform:rotate(0)} }
@keyframes deNodG  { 0%{transform:rotate(0)} 30%{transform:rotate(-2.4deg)} 66%{transform:rotate(1.4deg)} 100%{transform:rotate(0)} }
@keyframes deTurnY { 0%{transform:perspective(1200px) rotateY(0deg) translateX(0)} 26%{transform:perspective(1200px) rotateY(-34deg) translateX(-5px)} 62%{transform:perspective(1200px) rotateY(24deg) translateX(4px)} 100%{transform:perspective(1200px) rotateY(0deg) translateX(0)} }

/* 立牌高光 + 地面投影 */
.de-sheen { position:absolute; inset:0; pointer-events:none; border-radius:10px;
  background:linear-gradient(104deg,rgba(255,255,255,0) 34%,rgba(255,255,255,.5) 45%,rgba(255,255,255,0) 56%);
  mix-blend-mode:screen; opacity:.7; }
.de-floor { position:absolute; left:50%; bottom:3%; width:min(560px,90%); height:52px; transform:translateX(-50%);
  background:radial-gradient(ellipse at center, rgba(20,40,90,.24) 0%, rgba(20,40,90,.09) 44%, transparent 72%);
  filter:blur(7px); pointer-events:none; }
.de-bhint { position:absolute; left:50%; bottom:-14px; transform:translateX(-50%); z-index:6; pointer-events:none;
  font-size:12px; font-weight:600; color:#3a4a72; background:rgba(255,255,255,.9); border:1px solid rgba(20,40,90,.1);
  padding:5px 14px; border-radius:18px; box-shadow:var(--shadow); white-space:nowrap; transition:opacity .3s; }
.de-bhint .k { animation:deHintX 2.4s ease-in-out infinite; display:inline-block; }
@keyframes deHintX { 0%,100%{transform:translateX(-3px)} 50%{transform:translateX(3px)} }

/* 立牌背面 */
.de-bi { position:absolute; inset:0; padding:8% 14%; display:flex; flex-direction:column;
  background:linear-gradient(158deg,#fefefe 0%,#f7f9fc 46%,#eaeef5 100%); }
.de-bi::before { content:''; position:absolute; inset:0; opacity:.5;
  background-image:repeating-linear-gradient(115deg, rgba(20,40,90,.028) 0 1px, transparent 1px 5px); }
.de-bi > * { position:relative; z-index:2; }
.de-bi-top { display:flex; align-items:center; gap:8px; font-size:10.5px; font-weight:700; letter-spacing:.6px; color:#8b96ab; }
.de-bi-top i { width:16px; height:1.6px; background:#c3cbd9; display:inline-block; border-radius:1px; flex:none; }
.de-bi-mid { margin:auto 0; text-align:center; }
.de-bi-mid .n { font-size:29px; font-weight:800; color:#1b2b4d; letter-spacing:-.8px; }
.de-bi-mid .s { font-size:13px; font-weight:700; letter-spacing:2.4px; color:#7c88a0; margin-top:5px; }
.de-bi-mid .t { font-size:11.5px; color:#9aa4b8; margin-top:10px; }
.de-bi-sep { height:1px; background:repeating-linear-gradient(90deg,#cdd5e2 0 5px,transparent 5px 10px); margin:13px 14%; }
.de-bi-mid .d { font-size:10.5px; color:#98a3b7; line-height:1.85; margin-top:4px; }
.de-bi-spec { display:grid; grid-template-columns:1fr 1fr; gap:5px 10px; margin:14px 6% 0; }
.de-bi-spec span { font-size:9px; color:#a6afc0; letter-spacing:.2px; white-space:nowrap; }
.de-bi-spec b { color:#7f8b9f; font-weight:600; }
.de-bi-foot { display:flex; align-items:center; justify-content:space-between; gap:8px; }
.de-bi-foot .code { font-size:8.5px; color:#b3bccb; letter-spacing:.4px; }
.de-bi-foot .mat { font-size:9.5px; color:#9aa4b4; letter-spacing:.8px; font-weight:700; }
.de-bi-back-btn { margin-left:auto; font-size:10px; font-weight:700; color:#2b4b96; background:#eef2fb; border:1px solid #d9e1f2;
  padding:4px 10px; border-radius:14px; cursor:pointer; transition:all .25s; white-space:nowrap; }
.de-bi-back-btn:hover { background:#e2e9f8; }

/* 背撑支架 */
.de-strut { position:absolute; left:7.5%; right:7.5%; top:11%; bottom:11%; transform:translateZ(-30px) rotateY(180deg);
  backface-visibility:hidden; -webkit-backface-visibility:hidden; pointer-events:none;
  filter:drop-shadow(0 14px 24px rgba(15,30,60,.2)); }
.de-strut .rail { position:absolute; top:0; bottom:0; width:6.2%; border-radius:3px;
  background:linear-gradient(90deg,#98a2b2 0%,#e3e8f0 22%,#c3cbd8 46%,#f4f7fb 58%,#a8b1c0 80%,#838d9d 100%); }
.de-strut .rail.l { left:0; }
.de-strut .rail.r { right:0; }
.de-strut .cross { position:absolute; left:0; right:0; top:74%; height:5%; border-radius:3px;
  background:linear-gradient(180deg,#f2f5fa 0%,#c8d0dd 34%,#eef2f8 52%,#9aa4b4 100%); }
.de-strut .hinge { position:absolute; left:-4%; right:-4%; top:-3.2%; height:7%; border-radius:5px;
  background:linear-gradient(180deg,#dfe4ec,#aeb7c6 46%,#8b95a6); box-shadow:inset 0 1px 0 rgba(255,255,255,.7); }
.de-strut .foot { position:absolute; bottom:-2.2%; width:11%; height:4.6%; border-radius:4px; background:#5d6675; opacity:.92; }
.de-strut .foot.l { left:-2.4%; }
.de-strut .foot.r { right:-2.4%; }
.de-strut .tagline { position:absolute; left:0; right:0; bottom:11%; text-align:center; font-size:9px; font-weight:700;
  letter-spacing:1.5px; color:#9aa4b4; }

/* 讲解面板 */
.de-panel { position:relative; z-index:2; }
.de-kpis { display:grid; grid-template-columns:repeat(4,minmax(0,1fr)); gap:11px; margin:26px 0 22px; }
.de-kpi { position:relative; background:var(--white); border:1px solid rgba(15,35,80,.07); border-radius:16px;
  padding:17px 8px 15px; text-align:center; box-shadow:var(--shadow); cursor:pointer;
  transition:transform .3s cubic-bezier(.4,0,.2,1), box-shadow .3s, border-color .3s; }
.de-kpi:hover, .de-kpi:focus-visible, .de-kpi.open { transform:translateY(-3px); box-shadow:var(--shadow-md); border-color:rgba(91,63,212,.34); z-index:14; outline:none; }
.de-kpi b { display:block; font-size:37px; font-weight:800; letter-spacing:-1.8px; line-height:1.04;
  background:linear-gradient(120deg,#1f5fd0,#7c5ce7); -webkit-background-clip:text; background-clip:text; -webkit-text-fill-color:transparent; }
.de-kpi span { display:block; font-size:12.5px; color:var(--muted); margin-top:6px; font-weight:600; letter-spacing:-.1px; }
.de-kpi .kp-dot { position:absolute; top:10px; right:10px; width:19px; height:19px; border-radius:7px;
  display:flex; align-items:center; justify-content:center; font-size:13px; font-weight:700; line-height:1; font-style:normal;
  color:#7c5ce7; background:rgba(124,92,231,.09); border:1px solid rgba(124,92,231,.2);
  transition:transform .34s cubic-bezier(.34,1.4,.5,1), background .25s, color .25s, border-color .25s; }
.de-kpi .kp-dot::before { content:'+'; }
.de-kpi:hover .kp-dot, .de-kpi:focus-visible .kp-dot, .de-kpi.open .kp-dot {
  background:linear-gradient(120deg,#1f5fd0,#7c5ce7); color:#fff; border-color:transparent; }
.de-kpi.open .kp-dot { transform:rotate(135deg); }
/* 悬浮明细面板 */
.de-kpi-pop { position:absolute; left:50%; top:calc(100% + 11px); width:max-content; max-width:min(400px,76vw);
  background:#fff; border:1px solid rgba(15,35,80,.1); border-radius:14px; padding:14px 16px 15px;
  box-shadow:0 20px 48px rgba(12,28,64,.2); text-align:left; z-index:30;
  opacity:0; visibility:hidden; pointer-events:none; transform:translate(-50%,-7px);
  transition:opacity .22s, transform .22s, visibility .22s; }
.de-kpi-pop::before { content:''; position:absolute; top:-6px; left:50%; margin-left:-6px; width:11px; height:11px;
  background:#fff; border-left:1px solid rgba(15,35,80,.1); border-top:1px solid rgba(15,35,80,.1); transform:rotate(45deg); }
.de-kpi:first-child .de-kpi-pop { left:-6px; transform:translate(0,-7px); }
.de-kpi:first-child .de-kpi-pop::before { left:26px; margin-left:0; }
.de-kpi:last-child .de-kpi-pop { left:auto; right:-6px; transform:translate(0,-7px); }
.de-kpi:last-child .de-kpi-pop::before { left:auto; right:20px; margin-left:0; }
.de-kpi:hover .de-kpi-pop, .de-kpi:focus-visible .de-kpi-pop, .de-kpi.open .de-kpi-pop { opacity:1; visibility:visible; transform:translate(-50%,0); pointer-events:auto; }
.de-kpi:first-child:hover .de-kpi-pop, .de-kpi:first-child:focus-visible .de-kpi-pop, .de-kpi:first-child.open .de-kpi-pop,
.de-kpi:last-child:hover .de-kpi-pop, .de-kpi:last-child:focus-visible .de-kpi-pop, .de-kpi:last-child.open .de-kpi-pop { transform:translate(0,0); }
.de-kpi-pop .kp-t { font-size:12.5px; font-weight:800; color:#243352; margin-bottom:10px; letter-spacing:-.2px; }
.de-kpi-pop .kp-t em { font-style:normal; color:#7c5ce7; }
.de-kpi-pop .kp-l { display:flex; flex-wrap:wrap; gap:6px; max-height:212px; overflow-y:auto; overscroll-behavior:contain; }
.de-kpi-pop .kp-l::-webkit-scrollbar { width:5px; }
.de-kpi-pop .kp-l::-webkit-scrollbar-thumb { background:rgba(20,40,90,.18); border-radius:3px; }
.de-kpi-pop .kp-i { font-size:11.5px; font-weight:600; color:#33456a; background:#f2f5fc;
  border:1px solid rgba(15,35,80,.06); border-radius:8px; padding:4px 9px; white-space:nowrap; }
.de-kpi-pop .kp-i.plan { color:#9a6b1f; background:#fdf6e7; border-color:rgba(180,120,20,.18); }
.de-kpi-pop .kp-g { font-size:10.5px; font-weight:800; color:#8b95a8; letter-spacing:.4px; margin:9px 0 2px; width:100%; }
.de-bubble { position:relative; background:var(--white); border:1px solid rgba(15,35,80,.08); border-radius:16px;
  padding:15px 18px; font-size:14.5px; font-weight:600; color:#243352; box-shadow:var(--shadow); min-height:56px;
  display:flex; align-items:center; gap:10px; transition:opacity .25s; }
.de-bubble .bb-ic { font-size:19px; flex:none; }
.de-bubble .bb-tx { transition:opacity .2s; }
@keyframes deSayPop { from { opacity:0; transform:translateY(5px); } to { opacity:1; transform:none; } }
.de-bubble .bb-tx.pop { animation:deSayPop .42s cubic-bezier(.34,1.2,.5,1); }
/* 立牌控制：一行 4 个，不换行 */
.de-acts { display:flex; flex-wrap:nowrap; gap:8px; margin-top:15px; }
.de-act { flex:1 1 0; min-width:0; display:inline-flex; align-items:center; justify-content:center; gap:5px;
  padding:10px 6px; border-radius:12px; font-size:12.5px; font-weight:600; white-space:nowrap;
  color:#2b3a58; background:var(--white); border:1px solid rgba(15,35,80,.1); cursor:pointer; box-shadow:var(--shadow);
  transition:all .25s; font-family:inherit; }
.de-act .ic { font-size:14px; line-height:1; flex:none; }
.de-act:hover { border-color:rgba(91,63,212,.4); color:#4b36c4; transform:translateY(-2px); box-shadow:var(--shadow-md); }
.de-act.on { background:linear-gradient(118deg,#1f5fd0,#7c5ce7); color:#fff; border-color:transparent; box-shadow:0 5px 18px rgba(70,80,200,.32); }
.de-act.on .ic { filter:brightness(1.25); }
/* 人物可点击提示 */
.de-char { cursor:pointer; }
.de-char.cursor-tap::after { content:''; position:absolute; inset:0; border-radius:50%; pointer-events:none; }

/* 放大查看立牌 */
/* ---------- 放大查看（两处立牌共用） ----------
   两段式：.de-lb-base 用页面上已经缓存过的显示图，点开瞬间就有画面；
   .de-lb-hi 是点开后才拉的放大图（约 150KB，AVIF），加载完淡入替换。
   两张图同比例，尺寸完全一致，替换过程不跳动。 */
.de-lb { position:fixed; inset:0; z-index:900; background:rgba(6,12,30,.9); display:none;
  overflow:auto; overscroll-behavior:contain; padding:26px; cursor:zoom-out; }
.de-lb.open { display:flex; }
.de-lb-stage { position:relative; margin:auto; line-height:0; cursor:zoom-in; }
.de-lb-base, .de-lb-hi { display:block; max-width:min(94vw,1000px); max-height:88vh; width:auto; height:auto;
  border-radius:8px; box-shadow:0 30px 80px rgba(0,0,0,.5); }
.de-lb-base { filter:blur(1.2px); }
.de-lb.hi-ready .de-lb-base { filter:none; }
.de-lb-hi { position:absolute; inset:0; margin:auto; opacity:0; transition:opacity .32s ease; }
.de-lb.hi-ready .de-lb-hi { opacity:1; }
/* 2× 细节模式：图片放大到 2 倍，弹层可滚动查看小字 */
.de-lb.z2 { cursor:zoom-out; }
.de-lb.z2 .de-lb-stage { cursor:zoom-out; }
.de-lb.z2 .de-lb-base, .de-lb.z2 .de-lb-hi { max-width:min(184vw,2000px); max-height:none; }
.de-lb .cl { position:fixed; top:16px; right:22px; z-index:2; color:#fff; font-size:30px; line-height:1;
  cursor:pointer; opacity:.7; }
.de-lb .cl:hover { opacity:1; }
.de-lb-tip { position:fixed; left:50%; bottom:14px; transform:translateX(-50%); z-index:2;
  color:rgba(214,228,255,.62); font-size:12px; letter-spacing:.2px; white-space:nowrap;
  background:rgba(6,12,30,.55); padding:6px 13px; border-radius:20px; pointer-events:none; }
.de-lb-tip .ic { font-size:12px; }
@media (max-width:640px) { .de-lb { padding:12px; } .de-lb-tip { font-size:10.5px; padding:5px 10px; } }

/* ============ 2. 业务流（深色） ============ */
.de-flow-sec { position:relative; padding:86px 0 56px; overflow:hidden;
  background:linear-gradient(168deg,#061027 0%,#0b1e46 26%,#0e2a5e 52%,#0a1c3f 76%,#050c1e 100%); }
.de-flow-sec::before { content:''; position:absolute; inset:0; pointer-events:none; opacity:.34;
  background-image:linear-gradient(rgba(120,170,255,.09) 1px,transparent 1px),linear-gradient(90deg,rgba(120,170,255,.09) 1px,transparent 1px);
  background-size:56px 56px; -webkit-mask-image:radial-gradient(ellipse 74% 70% at 50% 42%,#000,transparent 76%);
  mask-image:radial-gradient(ellipse 74% 70% at 50% 42%,#000,transparent 76%); }
.de-flow-sec::after { content:''; position:absolute; width:760px; height:760px; left:50%; top:34%; transform:translate(-50%,-50%);
  background:radial-gradient(circle,rgba(70,120,255,.2) 0%,transparent 66%); pointer-events:none; }
.de-flow-inner { position:relative; z-index:2; max-width:1320px; margin:0 auto; padding:0 30px; }
.de-flow-head { text-align:center; margin-bottom:30px; }
.de-flow-head .de-pill { background:rgba(120,160,255,.14); border-color:rgba(130,170,255,.28); color:#a9c4ff; }
.de-flow-head h2 { font-size:38px; font-weight:800; letter-spacing:-1.15px; color:#fff; margin:0 0 16px; line-height:1.24; }
.de-flow-head h2 em { font-style:normal; background:linear-gradient(100deg,#6ea8ff,#a98bff 55%,#f0a6ff); -webkit-background-clip:text; background-clip:text; -webkit-text-fill-color:transparent; }
.de-flow-head p { font-size:15px; color:rgba(206,222,255,.66); line-height:1.8; max-width:790px; margin:0 auto; }
.de-flow-stat { display:inline-flex; flex-wrap:wrap; align-items:center; justify-content:center; gap:5px 11px;
  font-size:15px; font-weight:600; color:rgba(203,222,255,.8); letter-spacing:.1px; }
.de-flow-stat .seg { display:inline-flex; align-items:baseline; gap:6px; }
.de-flow-stat .seg b { font-size:24px; font-weight:800; letter-spacing:-.9px; line-height:1;
  background:linear-gradient(120deg,#7fb2ff,#a98bff 70%); -webkit-background-clip:text; background-clip:text; -webkit-text-fill-color:transparent; }
.de-flow-stat .dot { font-size:13px; color:rgba(150,180,240,.42); }

/* 日常带（置顶横贯条） */
.de-daily { display:flex; align-items:center; flex-wrap:wrap; gap:9px 12px; margin-bottom:15px; padding:12px 18px; border-radius:14px;
  background:linear-gradient(100deg,rgba(56,110,220,.22),rgba(56,110,220,.05));
  border:1px dashed rgba(120,170,255,.42); }
.de-daily .lb { flex:none; font-size:12.5px; font-weight:800; color:#0a1730; letter-spacing:.3px; padding:5px 14px; border-radius:9px;
  background:linear-gradient(118deg,#7fb2ff,#b79bff); box-shadow:0 3px 12px rgba(110,150,255,.3); }
.de-daily .it { display:inline-flex; align-items:center; gap:6px; font-size:12.5px; font-weight:600; color:#c2d6ff; white-space:nowrap; }
.de-daily .it::before { content:''; width:4px; height:4px; border-radius:50%; background:#6ea8ff; box-shadow:0 0 7px #6ea8ff; flex:none; }
.de-daily .ln { flex:1 1 46px; min-width:22px; height:1px; position:relative;
  background:repeating-linear-gradient(90deg,rgba(130,175,255,.5) 0 6px,transparent 6px 12px); }
.de-daily .ln::after { content:''; position:absolute; right:-1px; top:-4px; width:0; height:0;
  border-left:8px solid rgba(150,190,255,.7); border-top:4.5px solid transparent; border-bottom:4.5px solid transparent; }
.de-daily .ds { flex:none; font-size:12px; color:rgba(180,205,255,.72); font-weight:600; }

/* 8 阶段列 */
.flow-grid { display:grid; grid-template-columns:repeat(var(--flow-cols,8),minmax(0,1fr)); gap:11px; }
.flow-col { display:flex; flex-direction:column; border-radius:14px; overflow:hidden; transition:transform .3s, box-shadow .3s; }
.flow-col:hover { transform:translateY(-4px); box-shadow:0 14px 34px rgba(0,20,60,.42); }
.flow-head { position:relative; padding:14px 6px 12px; text-align:center; border-radius:14px 14px 0 0; overflow:hidden;
  background:linear-gradient(160deg,#3a7bd5 0%,#2558b8 48%,#1a3f92 100%); }
.flow-head::after { content:''; position:absolute; inset:0; background:linear-gradient(180deg,rgba(255,255,255,.2),transparent 54%); }
.flow-head .n { position:relative; z-index:2; display:block; font-size:22px; font-weight:800; color:#fff; line-height:1; letter-spacing:-.5px; }
.flow-head .t { position:relative; z-index:2; display:block; font-size:13.5px; font-weight:700; color:rgba(255,255,255,.94); margin-top:5px; letter-spacing:.4px; }
.flow-body { flex:1; padding:9px 8px; display:flex; flex-direction:column; gap:7px; border-radius:0 0 14px 14px;
  background:rgba(13,32,72,.72); border:1px solid rgba(96,146,255,.24); border-top:none; }
.flow-item { display:flex; align-items:center; gap:6px; padding:8px 8px; border-radius:8px; font-size:11.5px; line-height:1.32; font-weight:600;
  color:#c9dcff; background:rgba(255,255,255,.055); border:1px solid rgba(120,165,255,.14); transition:all .25s; }
.flow-item i { flex:none; font-style:normal; font-size:10px; font-weight:700; color:#7fb6ff; letter-spacing:.2px; }
.flow-item:hover { background:rgba(110,160,255,.2); border-color:rgba(150,195,255,.5); transform:translateX(3px); }
.flow-col.plan .flow-head { background:linear-gradient(160deg,#3c4864,#28324a); }
.flow-col.plan .flow-head::after { background:linear-gradient(180deg,rgba(255,255,255,.07),transparent 54%); }
.flow-col.plan .flow-body { background:rgba(16,22,40,.62); border:1px dashed rgba(120,145,200,.34); border-top:none; }
.flow-col.plan .flow-item { background:transparent; border:1px dashed rgba(120,145,200,.28); color:#8f9cba; }
.flow-col.plan .flow-item i { color:#77839e; }
.flow-col.plan .flow-item:hover { background:rgba(120,145,200,.1); border-color:rgba(150,170,220,.45); }
.flow-col.plan .plan-foot { margin-top:auto; align-self:center; padding:5px 12px; border-radius:20px; white-space:nowrap;
  font-size:10.5px; font-weight:700; letter-spacing:.6px; color:#8fa0c2; background:rgba(120,145,200,.12); border:1px solid rgba(130,155,210,.3); }

/* 底部说明带（L1 × L2） */
.flow-foot { margin-top:19px; display:flex; flex-wrap:wrap; align-items:center; justify-content:center; gap:10px 18px;
  padding:14px 22px; border-radius:14px; background:rgba(14,34,74,.66); border:1px solid rgba(96,146,255,.22); }
.flow-foot .ff-l { font-size:13.5px; font-weight:800; color:#cfe0ff; letter-spacing:.2px; white-space:nowrap; }
.flow-foot .ff-sep { width:1px; height:15px; background:rgba(130,170,255,.28); flex:none; }
.flow-foot .ff-r { font-size:13.5px; color:rgba(185,208,250,.82); font-weight:600; white-space:nowrap; }
.flow-foot .ff-r b { color:#7fb2ff; font-weight:800; font-size:15.5px; letter-spacing:-.3px; }
.flow-cap { text-align:center; margin-top:18px; font-size:11.5px; color:rgba(150,175,220,.5); letter-spacing:.2px; line-height:1.9; }

/* ============ 3. 场景能力集合 ============ */
.de-cap-sec { padding:__CAP_PT__px 0 76px; background:linear-gradient(180deg,#f7f9fd,#eef2f9); }
/* 场景能力集合这一屏单独放宽：表格 4 列，窄容器会把「介绍 / 输入示例」挤成一条。
   宽度与列数由 content.md「能力集容器宽度 / 能力集列数」控制（注入下面的 __CAP_W__ / __CAP_COLS__ 占位符） */
.de-cap-sec .de-wrap { max-width:__CAP_W__; }
/* 主能力卡：默认一行两张（`能力集列数`）。窗口收成一行一张的断点由
   `能力集列数断点` 控制（默认 1024 = PC 恒定两列），断点之上会启用紧凑表格
   样式，让每张卡窄到 ~470px 时 4 列表格依然读得下去 */
.cap-grid { display:grid; grid-template-columns:repeat(__CAP_COLS__,minmax(0,1fr)); gap:20px; }
@media (max-width:__CAP_BP__px) { .cap-grid { grid-template-columns:1fr; } }
/* 两列但还不够宽的区间（1025 ~ 1560）：压缩留白 + 允许表头换行，防止挤压换行 */
@media (min-width:__CAP_BP_NEXT__px) and (max-width:1560px) {
  .de-cap-sec .de-wrap { padding:0 24px; }
  .cap-top { padding:20px 18px 13px; gap:11px; }
  .cap-name { font-size:19px; }
  .cap-desc { padding:0 18px 12px; }
  .cap-loop { margin:0 18px 12px; padding:11px 13px 12px; }
  .cap-loop-chain .cp { font-size:11px; padding:3px 8px; }
  .cap-tbl-wrap { padding:0 10px 12px; }
  .cap-tbl { font-size:12px; }
  .cap-tbl th { white-space:normal; padding:9px 9px; font-size:11px; }
  .cap-tbl td { padding:9px 9px; }
  .cap-tbl td.sk { min-width:76px; }
  .cap-tbl td.ent { white-space:normal; }
  .cap-tbl th, .cap-tbl td { overflow-wrap:anywhere; }
  .cap-tbl th:nth-child(1), .cap-tbl td.sk { width:20%; }
  .cap-tbl th:nth-child(3), .cap-tbl td.dt { width:15%; }
  .cap-tbl th:nth-child(4), .cap-tbl td.ent, .cap-tbl td.ent-m { width:17%; }
  .cap-row-side { max-width:60%; }
}
.cap-card { position:relative; background:var(--white); border:1px solid rgba(15,35,80,.07); border-radius:20px; overflow:hidden;
  box-shadow:var(--shadow); transition:transform .34s cubic-bezier(.4,0,.2,1), box-shadow .34s; display:flex; flex-direction:column; }
.cap-card::before { content:''; position:absolute; top:0; left:0; right:0; height:4px; background:var(--cc,#1e6fd9); }
.cap-card:hover { transform:translateY(-5px); box-shadow:0 20px 46px rgba(15,35,80,.13); }
.cap-card.wide { grid-column:1 / -1; }
.cap-top { display:flex; align-items:flex-start; gap:14px; padding:23px 24px 15px; }
.cap-hd { flex:1 1 auto; min-width:0; }
.cap-count { flex:none; text-align:right; padding-left:8px; border-left:1px dashed rgba(15,35,80,.12); min-width:62px; }
.cap-count b { display:block; font-size:27px; font-weight:800; letter-spacing:-1.1px; line-height:1;
  background:linear-gradient(120deg,var(--cc,#1e6fd9),color-mix(in srgb,var(--cc,#1e6fd9) 45%,#7c5ce7));
  -webkit-background-clip:text; background-clip:text; -webkit-text-fill-color:transparent; }
.cap-count span { display:block; font-size:10.5px; font-weight:700; color:#8b95a8; margin-top:5px; letter-spacing:.2px; white-space:nowrap; }
.cap-count.plan b { background:none; -webkit-text-fill-color:#a8b0c0; color:#a8b0c0; }
/* 场景闭环链 */
.cap-loop { margin:0 24px 16px; padding:13px 15px 14px; border-radius:13px;
  background:color-mix(in srgb,var(--cc,#1e6fd9) 5%,#fff);
  border:1px solid color-mix(in srgb,var(--cc,#1e6fd9) 15%,#fff); }
.cap-loop-t { display:flex; align-items:center; gap:6px; font-size:11px; font-weight:800; letter-spacing:.4px;
  color:var(--cc,#1e6fd9); margin-bottom:10px; }
.cap-loop-t::before { content:''; width:12px; height:2px; border-radius:1px; background:currentColor; flex:none; opacity:.7; }
.cap-loop-chain { display:flex; flex-wrap:wrap; align-items:center; gap:5px 5px; }
.cap-loop-chain .cp { font-size:11.5px; font-weight:700; color:#2f3f60; background:#fff; border-radius:8px; padding:4px 9px; white-space:nowrap;
  border:1px solid color-mix(in srgb,var(--cc,#1e6fd9) 19%,#fff);
  box-shadow:0 1px 3px color-mix(in srgb,var(--cc,#1e6fd9) 9%,transparent); }
.cap-loop-chain i { font-style:normal; font-size:11px; color:color-mix(in srgb,var(--cc,#1e6fd9) 42%,#fff); flex:none; }
.cap-ico { flex:none; width:52px; height:52px; border-radius:15px; display:flex; align-items:center; justify-content:center; font-size:25px;
  background:color-mix(in srgb, var(--cc,#1e6fd9) 12%, #fff); border:1px solid color-mix(in srgb, var(--cc,#1e6fd9) 24%, #fff); }
.cap-num { font-size:13px; font-weight:800; color:var(--cc,#1e6fd9); letter-spacing:1px; }
.cap-name { font-size:20px; font-weight:800; color:var(--brand-deep); letter-spacing:-.5px; line-height:1.3; margin-top:2px; }
.cap-stage { display:inline-block; font-size:11.5px; font-weight:700; color:#7382a0; margin-top:6px; }
.cap-stage b { color:var(--cc,#1e6fd9); font-weight:800; }
.cap-desc { padding:0 24px 18px; font-size:13.5px; color:var(--muted); line-height:1.78; }
/* 表格撑满卡片剩余高度：并排两卡行数不同时，行数少的一侧自动加大行距，使两表底部对齐 */
.cap-tbl-wrap { padding:0 14px 14px; overflow-x:auto; flex:1 1 auto; display:flex; flex-direction:column; }
.cap-tbl { width:100%; flex:1 1 auto; min-height:0; border-collapse:separate; border-spacing:0; font-size:12.5px; table-layout:auto; }
.cap-tbl th:nth-child(1), .cap-tbl td.sk { width:17%; }
.cap-tbl th:nth-child(3), .cap-tbl td.dt { width:14%; }
.cap-tbl th:nth-child(4), .cap-tbl td.ent, .cap-tbl td.ent-m { width:16%; }
.cap-tbl th { background:color-mix(in srgb, var(--cc,#1e6fd9) 8%, #fff); color:#43506b; font-weight:700; font-size:11.5px; text-align:left;
  padding:10px 12px; border-bottom:1px solid rgba(15,35,80,.08); white-space:nowrap; }
.cap-tbl th:first-child { border-radius:10px 0 0 0; }
.cap-tbl th:last-child { border-radius:0 10px 0 0; }
.cap-tbl td { padding:11px 12px; border-bottom:1px solid rgba(15,35,80,.055); color:#4a5670; line-height:1.62; vertical-align:top; }
.cap-tbl tr:last-child td { border-bottom:none; }
.cap-tbl td.sk { font-weight:700; color:#1f2c48; min-width:104px; }
.cap-tbl td.sk .plan-tag, .plan-tag { display:block; font-style:normal; font-weight:700; font-size:10px; line-height:1.4;
  color:#e02b3c; margin-top:3px; letter-spacing:.1px; }
.cap-tbl td.ent { white-space:nowrap; font-size:12px; font-weight:700; color:var(--cc,#1e6fd9); }
/* 入口标签：没配链接的走「纯文字」，不做按钮外观，避免误导点击 */
.ent-chip { display:inline-flex; align-items:center; gap:4px; border-radius:9px; }
.ent-n { line-height:1.42; }
/* ── 可点击入口（配了链接的）：文字链接，主题色渐变 + 虚线底 + ↗ ──
   ⚠️ 渐变文字用 background-image（不能用 background 简写，否则 clip 会被重置） */
a.ent-a { display:inline-flex; align-items:center; gap:4px; padding:0 0 1px; text-decoration:none;
  border-bottom:1px dashed color-mix(in srgb, var(--cc,#1e6fd9) 48%, #fff);
  transition:border-color .2s, border-bottom-style .2s; }
a.ent-a .ent-n {
  background-image:linear-gradient(94deg, var(--cc,#1e6fd9) 0%,
    color-mix(in srgb, var(--cc,#1e6fd9) 46%, #6fb0ff) 100%);
  -webkit-background-clip:text; background-clip:text;
  color:transparent; -webkit-text-fill-color:transparent; }
.ent-arw { font-style:normal; font-size:10px; line-height:1; flex:none;
  color:color-mix(in srgb, var(--cc,#1e6fd9) 78%, #6b7a9b); transition:transform .2s; }
a.ent-a:hover, a.ent-a:focus-visible { outline:none;
  border-bottom-style:solid; border-bottom-color:var(--cc,#1e6fd9); }
a.ent-a:hover .ent-arw, a.ent-a:focus-visible .ent-arw { transform:translate(1.5px,-1.5px); }
/* 入口列提示条（content.md 里「入口提示」留空即不显示） */
.cap-ent-hint { display:flex; align-items:center; gap:7px; margin:0 24px 12px; padding:8px 12px; border-radius:9px;
  font-size:11.5px; font-weight:700; line-height:1.5; color:color-mix(in srgb, var(--cc,#1e6fd9) 62%, #4b5670);
  background:color-mix(in srgb, var(--cc,#1e6fd9) 6%, #fff);
  border:1px dashed color-mix(in srgb, var(--cc,#1e6fd9) 30%, #fff); }
.cap-ent-hint .ic { font-size:12px; line-height:1; }
/* 合并单元格：垂直居中 + 极淡底色，弱化“每行重复同一入口/同一数据来源” */
.cap-tbl td.ent-span, .cap-tbl td.dt-span { vertical-align:middle; background:color-mix(in srgb, var(--cc,#1e6fd9) 3.2%, #fff); }
.cap-tbl td.ent-m { display:none; }
.cap-tbl td.dt-m { display:none; }
.cap-tbl tbody tr { transition:background .2s; }
.cap-tbl tbody tr:hover { background:color-mix(in srgb, var(--cc,#1e6fd9) 4.5%, #fff); }
.cap-empty { padding:26px 24px 28px; text-align:center; border:1px dashed rgba(15,35,80,.16);
  border-radius:12px; margin:0 24px 24px; background:#fafbfd; }
.cap-empty b { display:block; font-size:14px; color:#5b6577; font-weight:700; }
.cap-empty span { display:block; font-size:12px; color:#98a2b3; margin-top:7px; line-height:1.7; }
.cap-jump { display:inline-flex; align-items:center; gap:6px; margin:0 24px 22px; padding:9px 16px; border-radius:11px; font-size:12.5px;
  font-weight:700; color:#fff; text-decoration:none; background:var(--cc,#1e6fd9); box-shadow:0 4px 14px color-mix(in srgb, var(--cc,#1e6fd9) 34%, transparent);
  transition:all .26s; align-self:flex-start; }
.cap-jump:hover { transform:translateX(3px); filter:brightness(1.08); }

/* ============ 优化5：板块衔接（圆角叠压，替代生硬直切） ============ */
.de-body > section { position:relative; }
.de-body > .de-flow-sec,
.de-body > .de-cap-sec,
.de-body > .de-eco-sec,
.de-body > .inc-section { border-radius:46px 46px 0 0; margin-top:-46px; }
.de-body > .de-flow-sec  { z-index:2; }
.de-body > .de-cap-sec   { z-index:3; }
.de-body > .de-eco-sec   { z-index:4; }
.de-body > .inc-section  { z-index:5; }
/* 深色板块顶部补一层柔光，弱化圆角切边 */
.de-body > .de-flow-sec,
.de-body > .de-eco-sec,
.de-body > .inc-section { box-shadow:inset 0 1px 0 rgba(150,190,255,.10); }
@media (max-width:768px){
  .de-body > .de-flow-sec,
  .de-body > .de-cap-sec,
  .de-body > .de-eco-sec,
  .de-body > .inc-section { border-radius:26px 26px 0 0; margin-top:-26px; }
}

/* ============ 页尾 CTA ============ */
.de-cta { position:relative; overflow:hidden; padding:78px 0; text-align:center;
  background:linear-gradient(160deg,#08132c 0%,#0e2450 42%,#0a1a3c 72%,#060d20 100%); }
.de-cta::before { content:''; position:absolute; width:620px; height:620px; left:50%; top:50%; transform:translate(-50%,-50%);
  background:radial-gradient(circle,rgba(90,130,255,.2) 0%,transparent 68%); }
.de-cta-in { position:relative; z-index:2; }
.de-cta h3 { font-size:33px; font-weight:800; color:#fff; letter-spacing:-1px; line-height:1.3; }
.de-cta p { font-size:15px; color:rgba(196,214,255,.62); margin-top:12px; }
.de-cta-btns { display:flex; flex-wrap:wrap; gap:14px; justify-content:center; margin-top:30px; }
.de-cta-a { display:inline-flex; align-items:center; gap:8px; padding:14px 30px; border-radius:13px; font-size:14.5px; font-weight:700;
  text-decoration:none; transition:all .28s; }
.de-cta-a.pri { color:#fff; background:linear-gradient(118deg,#2f6fe0,#7c5ce7); box-shadow:0 8px 26px rgba(70,90,220,.36); }
.de-cta-a.pri:hover { transform:translateY(-2px); box-shadow:0 12px 34px rgba(70,90,220,.46); }
.de-cta-a.sec { color:#c6d6ff; background:rgba(255,255,255,.07); border:1px solid rgba(160,190,255,.24); }
.de-cta-a.sec:hover { background:rgba(255,255,255,.13); }

/* ============ 跨阶段通用能力 ============ */
.de-sub-head { display:flex; align-items:center; gap:16px; margin:46px 0 20px; }
.de-sub-head span { font-size:15px; font-weight:800; color:var(--brand-deep); letter-spacing:-.3px; white-space:nowrap;
  display:inline-flex; align-items:center; gap:9px; }
.de-sub-head span::before { content:''; width:26px; height:3px; border-radius:2px; background:linear-gradient(90deg,#1f5fd0,#c026d3); }
.de-sub-head::after { content:''; flex:1; height:1px; background:linear-gradient(90deg,rgba(15,35,80,.14),transparent); }
.cap-sub-grid { display:grid; grid-template-columns:repeat(var(--sub-cols,3),minmax(0,1fr)); gap:20px; align-items:stretch; }
.cap-sub-grid > .cap-card { height:100%; }
.cap-sub-grid .cap-jump { margin-top:auto; }
.cap-sub-grid .cap-rows, .cap-sub-grid .cap-empty { flex:1; }
/* 窄卡：能力行卡片式 */
.cap-rows { padding:0 18px 18px; display:flex; flex-direction:column; gap:11px; }
.cap-row { border:1px solid rgba(15,35,80,.07); border-left:3px solid var(--cc,#1e6fd9); border-radius:12px;
  padding:13px 15px; background:#fbfcfe; transition:all .26s;
  display:flex; align-items:flex-start; gap:14px; }
.cap-row:hover { background:color-mix(in srgb, var(--cc,#1e6fd9) 5%, #fff); transform:translateX(3px); box-shadow:0 6px 18px rgba(15,35,80,.06); }
.cap-row-bd { flex:1 1 auto; min-width:0; }
/* 右侧列：右列只有一行「用在哪」的纯文字（操作路径 / 入口名），贴着卡片右边缘、和行首对齐 */
.cap-row-side { flex:none; display:flex; flex-direction:column; align-items:flex-end; gap:7px; max-width:66%; margin-left:auto; }
.cap-row-h { display:flex; align-items:center; flex-wrap:wrap; gap:6px 10px; margin-bottom:7px; }
.cap-row-h b { font-size:13.5px; font-weight:700; color:#1f2c48; letter-spacing:-.2px; }
.cap-row-h .ent { margin-left:auto; font-size:11px; font-weight:600; color:#828da1; padding:0; background:none; border:none; }
.cap-row-side .ent { font-size:11px; font-weight:600; color:#828da1; padding:0; background:none; border:none; white-space:nowrap; }
.cap-row-d { font-size:12.5px; color:#5a6579; line-height:1.72; }
.cap-row-m { font-size:11px; color:#98a2b3; margin-top:8px; display:flex; align-items:flex-start; gap:7px; line-height:1.6; }
.cap-row-m::before { content:'▸'; color:var(--cc,#1e6fd9); font-size:10px; flex:none; line-height:1.7; }
/* 「操作路径」：和「数据来源」同一位置风格，路径每段是独立小标签 */
.cap-row-path { margin-top:9px; padding-top:9px; border-top:1px dashed rgba(15,35,80,.1);
  display:flex; align-items:flex-start; gap:8px; flex-wrap:wrap; }
/* 在右侧列里：不画分隔线、不写「操作路径」标签，整块右对齐贴着卡片右边 */
.cap-row-side .cap-row-path { margin-top:0; padding-top:0; border-top:none; justify-content:flex-end; text-align:right; }
.cap-row-side .cap-row-path .crp-c { justify-content:flex-end; }
.cap-row-path .crp-c { display:flex; align-items:center; flex-wrap:wrap; gap:5px; }
/* 紧凑卡「操作路径」：纯文字展示，不做链接/按钮外观 */
.cap-row-path .pth { font-size:11px; font-weight:600; color:#828da1;
  background:none; border:none; border-radius:0; padding:0; line-height:1.5; text-decoration:none; }
.cap-row-path .pth-sep { font-style:normal; color:#b6c0d0; font-size:11px; }
a.pth-a:hover { background:color-mix(in srgb, var(--cc,#1e6fd9) 16%, #fff); }
a.pth-a .ent-arw { margin-left:3px; font-size:9px; }
/* 并排两卡等高拉伸，配合 .cap-tbl-wrap 的 flex:1 让行数少的一侧自动加大行距、两表底部对齐 */
.cap-grid { align-items:stretch; }
.cap-card > .cap-tbl-wrap { min-height:0; }
.cap-card > .cap-jump { margin-top:auto; }
@media (max-width:980px) { .cap-sub-grid { grid-template-columns:1fr; } }
/* 窄屏：紧凑卡右列（入口 + 操作路径）改成堆叠到下方并左对齐 */
@media (max-width:640px) {
  .cap-row { flex-direction:column; gap:9px; }
  .cap-row-side { align-items:flex-start; max-width:100%; margin-left:0; }
  .cap-row-side .cap-row-path { justify-content:flex-start; text-align:left; }
  .cap-row-side .cap-row-path .crp-c { justify-content:flex-start; }
}

/* ============ 响应式 ============ */
@media (max-width:1180px) {
  .de-bs-grid { grid-template-columns:1fr; gap:44px; }
  .de-stage { min-height:600px; }
  .de-panel { max-width:700px; margin:0 auto; }
  .flow-grid { grid-template-columns:repeat(4,minmax(0,1fr)); gap:12px; }
}
@media (max-width:980px) {
  .de-h2, .de-flow-head h2 { font-size:31px; }
  .de-h2-go { padding:7px 13px; font-size:12px; gap:5px; }
  .de-sec { padding:66px 0; }
  .de-wrap { padding:0 22px; }
  .de-flow-stat { font-size:14px; gap:4px 9px; }
  .de-flow-stat .seg b { font-size:21px; }
}
@media (max-width:768px) {
  .nav-de-btn { padding:6px 11px; font-size:12px; gap:5px; }
  .nav-back-btn { padding:6px 12px; font-size:12.5px; }
  .de-board-sec { padding:40px 0 54px; }
  .de-h2, .de-flow-head h2 { font-size:26px; }
  .de-h2-a { gap:10px; }
  .de-h2-go { padding:6px 11px; font-size:11px; gap:4px; }
  .de-h2-go i { font-size:12px; }
  .de-lead { font-size:14.5px; }
  .de-stage { min-height:470px; }
  .de-board { width:min(320px,84%); }
  .de-floor { width:min(320px,84%); }
  .de-board-tools { right:calc(50% - min(160px,42%) + 8px); bottom:5%; }
  .de-lb-btn { padding:7px 11px; font-size:11.5px; }
  .de-bi-mid .n { font-size:22px; }
  .de-bi-mid .s { font-size:11px; letter-spacing:1.6px; }
  .de-bi-mid .d, .de-bi-spec { display:none; }
  .de-kpis { gap:8px; }
  .de-kpi { padding:13px 6px 12px; border-radius:13px; }
  .de-kpi b { font-size:26px; letter-spacing:-1.2px; }
  .de-kpi span { font-size:10.5px; margin-top:4px; }
  .de-kpi-pop { max-width:min(320px,86vw); padding:12px 13px 13px; }
  .de-kpi-pop .kp-i { font-size:10.5px; padding:3px 8px; }
  .de-kpi:first-child .de-kpi-pop { left:-4px; }
  .de-kpi:last-child .de-kpi-pop { right:-4px; }
  .de-tagline .de-slogan, .de-tagline .de-lead { font-size:12.5px; }
  .de-tagsep { display:none; }
  .de-tagline .de-lead { width:100%; margin-top:5px; }
  .de-acts { gap:6px; }
  .de-act { padding:9px 4px; font-size:11.5px; border-radius:10px; }
  .de-act .ic { font-size:12.5px; }
  .flow-grid { grid-template-columns:repeat(2,minmax(0,1fr)); }
  .flow-head .n { font-size:18px; }
  .flow-head .t { font-size:12.5px; }
  .de-flow-sec, .de-cap-sec { padding:62px 0 56px; }
  .de-flow-inner { padding:0 18px; }
  .de-daily { flex-wrap:wrap; gap:8px 10px; padding:11px 14px; }
  .de-daily .ln { display:none; }
  .de-daily .ds { margin-left:auto; }
  .flow-foot { gap:8px 14px; padding:12px 16px; }
  .flow-foot .ff-l, .flow-foot .ff-r { font-size:12px; white-space:normal; }
  .flow-foot .ff-sep { display:none; }
  .de-cta h3 { font-size:25px; }
  .cap-top { padding:20px 18px 14px; gap:11px; }
  .cap-name { font-size:18px; }
  .cap-ico { width:44px; height:44px; border-radius:13px; font-size:21px; }
  .cap-count b { font-size:22px; }
  .cap-count { min-width:52px; }
  .cap-loop { margin:0 18px 13px; padding:11px 13px 12px; }
  .cap-loop-chain .cp { font-size:11px; padding:3px 8px; }
  .cap-desc { padding:0 18px 14px; }
  .cap-tbl-wrap { padding:0 10px 12px; }
}
@media (max-width:560px) {
  .de-kpis { grid-template-columns:repeat(2,minmax(0,1fr)); gap:8px; }
  .de-kpi b { font-size:29px; }
  .de-kpi span { font-size:11px; }
}
@media (max-width:768px) {
  .cap-tbl { font-size:12px; }
  .cap-tbl th { white-space:normal; padding:9px 9px; font-size:11px; }
  .cap-tbl td { padding:9px 9px; }
  .cap-tbl td.sk { min-width:72px; }
  .cap-tbl td.ent { white-space:normal; }
  .cap-tbl th, .cap-tbl td { overflow-wrap:anywhere; }
  .cap-stage { font-size:11px; }
}
@media (max-width:640px) {
  /* 能力表 → 堆叠卡片（避免 4 列在窄屏被挤压） */
  .cap-tbl-wrap { padding:0 12px 12px; overflow:visible; flex:none; display:block; }
  .cap-tbl { height:auto; }
  .cap-tbl thead { display:none; }
  .cap-tbl, .cap-tbl tbody { display:block; width:100%; }
  .cap-tbl tr { display:block; border:1px solid rgba(15,35,80,.08); border-left:3px solid var(--cc,#1e6fd9);
    border-radius:13px; padding:12px 13px; margin-bottom:11px; background:#fff; transition:box-shadow .25s; }
  .cap-tbl tr:last-child { margin-bottom:0; }
  .cap-tbl tbody tr:hover { background:#fff; box-shadow:0 6px 18px rgba(15,35,80,.07); }
  .cap-tbl td { display:block; padding:0; border:none; }
  /* 桌面端的百分比列宽在堆叠卡片里必须清掉，否则 skill 列会被挤到只剩 17% 宽，中文逐字换行 */
  .cap-tbl th:nth-child(n), .cap-tbl td, .cap-tbl td.sk, .cap-tbl td.dm,
  .cap-tbl td.dt, .cap-tbl td.dt-m, .cap-tbl td.ent, .cap-tbl td.ent-m { width:auto; max-width:none; min-width:0; }
  .cap-tbl td.sk { font-size:14px; font-weight:800; color:#1f2c48; margin-bottom:7px; letter-spacing:-.2px; }
  .cap-tbl td.dm { font-size:12.5px; color:#5a6579; line-height:1.72; }
  .cap-tbl td.dt, .cap-tbl td.dt-m, .cap-tbl td.ent, .cap-tbl td.ent-m { margin-top:9px; display:flex; align-items:flex-start; gap:8px;
    width:auto; max-width:none; font-size:11.5px; color:#8a94a6; line-height:1.6; }
  .cap-tbl td.dt::before, .cap-tbl td.dt-m::before, .cap-tbl td.ent::before, .cap-tbl td.ent-m::before { content:attr(data-l); flex:none; font-size:10.5px; font-weight:700;
    color:#aab2c0; padding:1px 7px; border-radius:6px; background:#f3f5f9; }
  .cap-tbl td.ent a.ent-a, .cap-tbl td.ent-m a.ent-a { white-space:normal; gap:5px; }
  .cap-tbl td.ent .ent-n, .cap-tbl td.ent-m .ent-n { font-size:12px; line-height:1.45; }
  .cap-tbl td.ent-span, .cap-tbl td.dt-span { background:transparent; }
}
@media (max-width:480px) {
  .de-act { font-size:11px; padding:8px 3px; gap:3px; }
  .cap-grid { gap:14px; }
  .flow-grid { gap:9px; }
  .flow-item { font-size:10.5px; padding:7px 6px; }
  .de-flow-stat { font-size:13px; }
  .de-flow-stat .seg b { font-size:19px; }
  .de-daily .it { font-size:11.5px; }
}
@media (prefers-reduced-motion: reduce) {
  .de-char, .de-char .de-l, .nav-de-btn::after, .de-bhint .k { animation:none !important; }
  .de-bubble .bb-tx.pop { animation:none !important; }
  .de-h2-go { animation:none !important; }
}

/* ============================================================
   深色主题：整页对齐「AI赋能营销」首页深色板块
   底色 #050b1c → #0b1e46 → #0d1f52；卡片 rgba(15,43,92) 系
   文字：标题纯白 / 正文 rgba(255,255,255,.7) / 弱化 .55 / 强调 #7fb2ff
   ============================================================ */
.de-body { background:#060f25; }

/* ---------- 顶部导航（深色玻璃） ---------- */
.de-body nav { background:rgba(6,14,36,.78); border-bottom-color:rgba(255,255,255,.07); box-shadow:none; }
.de-body nav.scrolled { border-bottom-color:rgba(255,255,255,.1); box-shadow:0 1px 16px rgba(0,0,0,.44); }
.de-body .nav-brand, .de-body .nav-brand span { color:#fff; }
.de-body .nav-brand img { filter:brightness(1.18); }
.de-body .nav-right { background:rgba(255,255,255,.07); border-color:rgba(255,255,255,.12); color:rgba(199,215,246,.72); }
.de-body .nav-back-btn { color:#d3e0ff; background:rgba(255,255,255,.08); border-color:rgba(255,255,255,.16); box-shadow:none; }
.de-body .nav-back-btn:hover { background:rgba(255,255,255,.15); border-color:rgba(255,255,255,.3); }

/* ---------- 1. 立牌区（深色舞台） ---------- */
.de-board-sec { background:
  radial-gradient(ellipse 58% 44% at 20% 30%, rgba(59,130,246,.20) 0%, transparent 62%),
  radial-gradient(ellipse 50% 40% at 84% 20%, rgba(139,92,246,.17) 0%, transparent 60%),
  linear-gradient(180deg,#050b1c 0%,#08142f 52%,#0a1a3d 100%); }
.de-board-sec::before { opacity:.46;
  background-image:radial-gradient(rgba(150,190,255,.13) 1px, transparent 1px); }
.de-floor { background:radial-gradient(ellipse at center, rgba(72,124,255,.30) 0%, rgba(72,124,255,.10) 44%, transparent 72%); }
.de-front, .de-back { box-shadow:0 0 0 1px rgba(255,255,255,.07), 0 26px 64px rgba(0,0,0,.52); }
.de-bhint { color:#c3d6ff; background:rgba(9,22,52,.86); border-color:rgba(130,170,255,.24);
  box-shadow:0 8px 22px rgba(0,0,0,.36); backdrop-filter:blur(9px); -webkit-backdrop-filter:blur(9px); }
.de-lb-btn { background:rgba(255,255,255,.14); border:1px solid rgba(255,255,255,.26); color:#eaf1ff;
  box-shadow:0 8px 22px rgba(0,0,0,.34); }
.de-lb-btn:hover { background:rgba(255,255,255,.24); box-shadow:0 12px 28px rgba(0,0,0,.42); }

/* 文案层级：白 → 浅蓝 */
.de-h2 { color:#fff; }
/* 注意：必须用 background-image，用 background 简写会重置 background-clip:text，文字会变成色块 */
.de-h2 em { background-image:linear-gradient(100deg,#6ea8ff,#b79bff 58%,#f0a6ff); }
.de-slogan { color:rgba(210,225,255,.92); }
.de-tagline .de-lead { color:rgba(184,204,242,.7); }
.de-tagsep { background:rgba(255,255,255,.18); }
.de-lead { color:rgba(190,209,245,.72); }
.de-lead-sub { color:rgba(160,182,224,.62); }
.de-sec-head .de-pill, .de-pill { color:#b9c9ff; background:rgba(120,160,255,.14); border-color:rgba(130,170,255,.28); }

/* KPI 卡 */
.de-kpi { background:linear-gradient(145deg, rgba(15,43,92,.92), rgba(26,58,118,.78));
  border:1px solid rgba(255,255,255,.09); box-shadow:0 12px 30px rgba(0,0,0,.3); }
.de-kpi:hover, .de-kpi:focus-visible, .de-kpi.open { border-color:rgba(140,120,255,.5);
  box-shadow:0 18px 42px rgba(0,0,0,.44), 0 0 0 1px rgba(140,120,255,.22); }
.de-kpi b { background-image:linear-gradient(120deg,#6ea8ff,#b79bff); }
.de-kpi span { color:rgba(182,203,242,.68); }
.de-kpi .kp-dot { color:#b9a5ff; background:rgba(124,92,231,.22); border-color:rgba(160,140,255,.34); }
.de-kpi-pop { background:#0e2450; border:1px solid rgba(130,170,255,.26);
  box-shadow:0 22px 52px rgba(0,0,0,.54); }
.de-kpi-pop::before { background:#0e2450; border-left-color:rgba(130,170,255,.26); border-top-color:rgba(130,170,255,.26); }
.de-kpi-pop .kp-t { color:#fff; }
.de-kpi-pop .kp-t em { color:#b79bff; }
.de-kpi-pop .kp-l::-webkit-scrollbar-thumb { background:rgba(255,255,255,.2); }
.de-kpi-pop .kp-i { color:#cfe0ff; background:rgba(255,255,255,.07); border-color:rgba(255,255,255,.1); }
.de-kpi-pop .kp-i.plan { color:#ffd08a; background:rgba(245,158,11,.14); border-color:rgba(245,158,11,.3); }
.de-kpi-pop .kp-g { color:rgba(160,185,230,.66); }

/* 气泡 + 动作按钮 */
.de-bubble { background:rgba(255,255,255,.06); border-color:rgba(255,255,255,.1); color:#dfe9ff; box-shadow:none; }
.de-act { color:#d6e2ff; background:rgba(255,255,255,.07); border-color:rgba(255,255,255,.13); box-shadow:none; }
.de-act:hover { color:#fff; background:rgba(255,255,255,.13); border-color:rgba(150,170,255,.5); }
.de-act.on { color:#fff; border-color:transparent; }

/* ---------- 3. 场景能力集合（深色） ---------- */
.de-cap-sec { background:
  radial-gradient(ellipse 62% 34% at 50% 2%, rgba(70,120,255,.15) 0%, transparent 68%),
  linear-gradient(180deg,#0a1735 0%,#0b1e46 42%,#0a1c3f 74%,#081430 100%); }
.de-body > .de-cap-sec { box-shadow:inset 0 1px 0 rgba(150,190,255,.10); }

.cap-card { background:linear-gradient(145deg, color-mix(in srgb, var(--cc,#1e6fd9) 10%, #0f2b5c),
  color-mix(in srgb, var(--cc,#1e6fd9) 5%, #13306b));
  border:1px solid rgba(255,255,255,.09); box-shadow:0 18px 44px rgba(0,0,0,.32); }
.cap-card:hover { border-color:color-mix(in srgb, var(--cc,#1e6fd9) 42%, transparent);
  box-shadow:0 24px 56px rgba(0,0,0,.44), 0 0 0 1px rgba(255,255,255,.05); }
.cap-num { color:color-mix(in srgb, var(--cc,#1e6fd9) 44%, #ffffff); }
.cap-name { color:#fff; }
.cap-stage { color:rgba(158,180,218,.75); }
.cap-stage b { color:color-mix(in srgb, var(--cc,#1e6fd9) 40%, #cfe0ff); }
.cap-count { border-left-color:rgba(255,255,255,.14); }
.cap-count b { background-image:linear-gradient(120deg, color-mix(in srgb, var(--cc,#1e6fd9) 52%, #ffffff),
  color-mix(in srgb, var(--cc,#1e6fd9) 26%, #b79bff)); }
.cap-count span { color:rgba(170,192,230,.66); }
.cap-count.plan b { -webkit-text-fill-color:#8e9cb8; color:#8e9cb8; background:none; }
.cap-ico { background:color-mix(in srgb, var(--cc,#1e6fd9) 20%, rgba(255,255,255,.04));
  border-color:color-mix(in srgb, var(--cc,#1e6fd9) 36%, transparent); }
.cap-desc { color:rgba(198,214,244,.76); }
.cap-loop { background:color-mix(in srgb, var(--cc,#1e6fd9) 13%, rgba(255,255,255,.03));
  border-color:color-mix(in srgb, var(--cc,#1e6fd9) 28%, transparent); }
.cap-loop-t { color:color-mix(in srgb, var(--cc,#1e6fd9) 38%, #dbe8ff); }
.cap-loop-chain .cp { color:#e7eeff; background:rgba(255,255,255,.075);
  border-color:color-mix(in srgb, var(--cc,#1e6fd9) 30%, transparent); box-shadow:none; }
.cap-loop-chain i { color:color-mix(in srgb, var(--cc,#1e6fd9) 30%, #7f93bb); }
.cap-empty { border-color:rgba(255,255,255,.16); background:rgba(255,255,255,.03); }
.cap-empty b { color:rgba(205,220,248,.82); }
.cap-empty span { color:rgba(162,182,218,.66); }

/* 能力表 */
.cap-tbl th { background:rgba(255,255,255,.06); color:rgba(198,215,248,.78); border-bottom-color:rgba(255,255,255,.1); }
.cap-tbl td { color:rgba(193,210,242,.76); border-bottom-color:rgba(255,255,255,.06); }
.cap-tbl td.sk { color:#fff; }
.cap-tbl tbody tr:hover { background:rgba(255,255,255,.05); }
.plan-tag { color:#ff7583; }
.cap-tbl td.ent { color:rgba(214,230,255,.62); }
.cap-tbl td.ent-span, .cap-tbl td.dt-span { background:rgba(255,255,255,.035); }
/* 可点击入口（深色底）：亮白 → 浅蓝渐变文字 + 亮色虚线下划，和不可点的灰字拉开对比 */
a.ent-a { color:#fff;
  border-bottom-color:rgba(150,185,255,.6); }
a.ent-a .ent-n {
  background-image:linear-gradient(94deg, #ffffff 0%,
    color-mix(in srgb, var(--cc,#1e6fd9) 36%, #cfe4ff) 100%);
  -webkit-background-clip:text; background-clip:text;
  color:transparent; -webkit-text-fill-color:transparent; }
a.ent-a .ent-arw { color:#7fb2ff; }
a.ent-a:hover, a.ent-a:focus-visible { border-bottom-color:#9dc4ff; }
.cap-ent-hint { color:rgba(228,240,255,.92); background:rgba(255,255,255,.055);
  border-color:color-mix(in srgb, var(--cc,#1e6fd9) 44%, transparent); }

/* 跨阶段紧凑卡（能力行） */
.de-sub-head span { color:#fff; }
.de-sub-head::after { background:linear-gradient(90deg,rgba(255,255,255,.16),transparent); }
.cap-row { background:rgba(255,255,255,.045); border-color:rgba(255,255,255,.08); border-left-color:var(--cc,#1e6fd9); }
.cap-row:hover { background:color-mix(in srgb, var(--cc,#1e6fd9) 14%, rgba(255,255,255,.06)); box-shadow:none; }
.cap-row-h b { color:#fff; }
.cap-row-h .ent { color:rgba(170,190,222,.72); background:none; border:none; }
.cap-row-side .ent { color:rgba(170,190,222,.72); background:none; border:none; }
.cap-row-d { color:rgba(198,214,244,.76); }
.cap-row-m { color:rgba(158,180,218,.62); }
.cap-row-m::before { color:color-mix(in srgb, var(--cc,#1e6fd9) 40%, #9fb6e8); }
.cap-row-path { border-top-color:rgba(255,255,255,.12); }
.cap-row-path .pth { color:rgba(178,198,230,.78); background:none; border:none; }
.cap-row-path .pth-sep { color:rgba(166,188,224,.48); }
a.pth-a:hover { background:rgba(255,255,255,.13); }

/* 深色下重定义 ≤640px 堆叠卡配色 */
@media (max-width:640px) {
  .cap-tbl tr { background:linear-gradient(145deg, rgba(15,43,92,.92), rgba(26,58,118,.78)); border-color:rgba(255,255,255,.09); }
  .cap-tbl tbody tr:hover { background:linear-gradient(145deg, rgba(20,52,108,.95), rgba(31,68,134,.82)); box-shadow:0 8px 22px rgba(0,0,0,.34); }
  .cap-tbl td.sk { color:#fff; }
  .cap-tbl td.dm { color:rgba(197,213,244,.76); }
  .cap-tbl td.dt, .cap-tbl td.dt-m, .cap-tbl td.ent, .cap-tbl td.ent-m { color:rgba(168,188,224,.7); }
  .cap-tbl td.dt::before, .cap-tbl td.dt-m::before, .cap-tbl td.ent::before, .cap-tbl td.ent-m::before {
    color:rgba(178,198,232,.74); background:rgba(255,255,255,.08); }
}

/* ============ 业务流「点哪跳哪」：点阶段列 / 日常带 → 滚到对应能力卡并高亮 ============ */
.flow-col.jumpable, .de-daily.jumpable { cursor:pointer; }
.flow-col.jumpable:focus-visible, .de-daily.jumpable:focus-visible { outline:2px solid #7fb2ff; outline-offset:3px; }
.flow-col.jumpable:hover .flow-head { filter:brightness(1.12); }
.flow-col.jumpable .flow-body { border-color:rgba(120,165,255,.42); }
.de-daily.jumpable { transition:border-color .28s, background .28s; }
.de-daily.jumpable:hover { border-color:rgba(130,170,255,.5); background:rgba(40,74,138,.5); }
.de-daily.jumpable .ds::after { content:' ↘'; font-size:11px; opacity:.75; }
@keyframes capFlash {
  0%   { box-shadow:0 0 0 0 rgba(127,178,255,0), 0 18px 44px rgba(0,0,0,0); }
  16%  { box-shadow:0 0 0 3px rgba(127,178,255,.9), 0 22px 62px rgba(64,124,255,.5); }
  60%  { box-shadow:0 0 0 3px rgba(127,178,255,.36), 0 14px 38px rgba(64,124,255,.22); }
  100% { box-shadow:0 0 0 0 rgba(127,178,255,0), 0 18px 44px rgba(0,0,0,0); }
}
.cap-card.cap-flash { animation:capFlash 1.6s cubic-bezier(.22,.9,.3,1) 1; border-color:rgba(127,178,255,.8) !important; }
/* 未来规划模块不是 .cap-card，单独给它也来一下高亮，从详情页返回时才看得见落点 */
#future-home.cap-flash,
#future-home.cap-flash .future-home-card { animation:capFlash 1.6s cubic-bezier(.22,.9,.3,1) 1; }
@media (prefers-reduced-motion:reduce) { .cap-card.cap-flash { animation-duration:.01s; } }

/* ============ 生态板块（夹在「跨阶段 · 通用能力」与「激励模块」之间） ============ */
/* 左栏：可 180° 拖动的立牌；右栏：从跨阶段卡里摘出来的那张能力卡 */
.de-eco-sec { padding:74px 0 80px;
  background:
    radial-gradient(ellipse 52% 40% at 20% 26%, rgba(16,185,129,.16) 0%, transparent 64%),
    radial-gradient(ellipse 46% 36% at 84% 74%, rgba(70,120,255,.13) 0%, transparent 66%),
    linear-gradient(180deg,#0a1735 0%,#0b1e46 46%,#0a1c3f 78%,#081430 100%); }
.de-eco-sec .de-wrap { max-width:1400px; }
.de-eco-sec .de-sub-head { margin:0 0 18px; }
.de-eco-lead { font-size:13.5px; color:rgba(180,200,238,.66); line-height:1.85; margin:0 0 34px; max-width:820px; }
.de-eco-grid { display:grid; grid-template-columns:minmax(0,0.84fr) minmax(0,1.16fr); gap:52px; align-items:center; }

/* 左栏：立牌（与页头立牌同机制，独立变量 --eco-rot / --eco-tilt） */
.de-eco-stage { position:relative; display:flex; flex-direction:column; align-items:center; justify-content:center;
  min-height:600px; padding-bottom:36px; }
.de-eco-persp { position:relative; z-index:2; width:100%; display:flex; justify-content:center;
  perspective:1900px; perspective-origin:50% 45%; }
.de-eco-board { position:relative; width:min(520px,92%); aspect-ratio:4200/5360; transform-style:preserve-3d;
  transform:rotateX(var(--eco-tilt,0deg)) rotateY(var(--eco-rot,-15deg)); transition:transform .1s linear;
  cursor:grab; touch-action:pan-y; will-change:transform; }
.de-eco-board.dragging { cursor:grabbing; transition:none; }
.de-eco-board.settling { transition:transform .68s cubic-bezier(.22,1.05,.36,1); }
.de-eco-board .de-face { border-radius:10px; }
.de-eco-front { transform:translateZ(9px); background:#fff; box-shadow:0 2px 0 rgba(255,255,255,.9) inset, 0 0 0 1px rgba(255,255,255,.16); }
.de-eco-back  { transform:translateZ(-9px) rotateY(180deg); background:#fff; box-shadow:0 0 0 1px rgba(255,255,255,.16); }
.de-eco-stage .de-floor { bottom:8px; width:min(520px,92%); height:46px;
  background:radial-gradient(ellipse at center, rgba(0,0,0,.52) 0%, rgba(0,0,0,.22) 44%, transparent 72%); }
.de-eco-stage .de-bhint { bottom:0; color:#cfdcff; background:rgba(255,255,255,.07);
  border-color:rgba(255,255,255,.14); box-shadow:none; }
.de-eco-stage.dragging .de-bhint { opacity:0; }
/* 生态立牌的「放大查看」：贴在立牌右下角，与页头立牌同款位置（提示文字上方） */
.de-eco-stage { position:relative; }
.de-eco-stage .de-board-tools { right:calc(50% - min(260px,46%) + 10px); bottom:44px; }

/* 右栏：能力卡（与左栏立牌等高，按钮贴底） */
.de-eco-side { min-width:0; }
.de-eco-side .cap-card { height:100%; }
.de-eco-side .cap-jump { margin-top:auto; }

@media (max-width:980px) {
  .de-eco-grid { grid-template-columns:1fr; gap:36px; }
  .de-eco-stage { min-height:0; padding-bottom:32px; }
  .de-eco-sec { padding:62px 0 70px; }
}
</style>'''


DE_JS = '''<script>
(function(){
  /* ---------- 滚动进度条 ---------- */
  var prog = document.getElementById('prog');
  window.addEventListener('scroll', function(){
    if(!prog) return;
    var h = document.documentElement.scrollHeight - window.innerHeight;
    prog.style.width = (h > 0 ? window.scrollY / h * 100 : 0) + '%';
  }, {passive:true});

  /* ---------- 生态板块立牌（第二块立牌，独立变量，与页头立牌互不影响） ---------- */
  (function(){
    var eco = document.getElementById('ecoBoard');
    if(!eco) return;
    var F = -15, B = 195;
    var rot = F, dragging = false, sx = 0, srot = 0;
    var stage = eco.closest('.de-eco-stage');
    function apply(){ eco.style.setProperty('--eco-rot', rot + 'deg'); }
    function settle(){ eco.classList.add('settling');
      setTimeout(function(){ eco.classList.remove('settling'); }, 720); }
    apply();
    eco.addEventListener('pointerdown', function(e){
      dragging = true; sx = e.clientX; srot = rot;
      eco.classList.add('dragging'); eco.classList.remove('settling');
      if(stage) stage.classList.add('dragging');
      try { eco.setPointerCapture(e.pointerId); } catch(err){}
    });
    eco.addEventListener('pointermove', function(e){
      if(!dragging) return;
      rot = Math.max(-30, Math.min(210, srot + (e.clientX - sx) * 0.45));
      apply();
    });
    function end(){
      if(!dragging) return;
      dragging = false;
      eco.classList.remove('dragging');
      if(stage) stage.classList.remove('dragging');
      rot = (rot < 90) ? F : B;
      apply(); settle();
    }
    eco.addEventListener('pointerup', end);
    eco.addEventListener('pointercancel', end);
    eco.addEventListener('pointerleave', end);
    /* 背面上的「转回正面」 */
    var fb = eco.querySelector('[data-eco-front]');
    if(fb){
      fb.addEventListener('click', function(e){
        e.stopPropagation();
        rot = F; apply(); settle();
      });
    }
  })();

  /* ---------- 3D 立牌 ---------- */
  var board = document.getElementById('deBoard');
  if(!board) return;
  var FRONT = -15, BACK = 195;
  var rot = FRONT, tilt = 0, dragging = false, sx = 0, srot = 0, moved = 0;

  function apply(){
    board.style.setProperty('--de-rot', rot + 'deg');
    board.style.setProperty('--de-tilt', tilt + 'deg');
  }
  apply();

  function snap(){
    board.classList.add('settling');
    rot = (rot < 90) ? FRONT : BACK;
    apply();
    setTimeout(function(){ board.classList.remove('settling'); }, 720);
  }

  board.addEventListener('pointerdown', function(e){
    dragging = true; moved = 0; sx = e.clientX; srot = rot;
    board.classList.add('dragging');
    board.classList.remove('settling');
    try { board.setPointerCapture(e.pointerId); } catch(err){}
  });
  board.addEventListener('pointermove', function(e){
    if(!dragging) return;
    var dx = e.clientX - sx;
    moved = Math.max(moved, Math.abs(dx));
    rot = Math.max(-30, Math.min(210, srot + dx * 0.45));
    apply();
  });
  function endDrag(){
    if(!dragging) return;
    dragging = false;
    board.classList.remove('dragging');
    snap();
  }
  board.addEventListener('pointerup', endDrag);
  board.addEventListener('pointercancel', endDrag);
  board.addEventListener('pointerleave', endDrag);

  /* 非拖拽时：鼠标纵向位置带来轻微俯仰，强化立体感 */
  var stage = board.closest('.de-stage');
  if(stage && window.matchMedia('(hover:hover)').matches){
    stage.addEventListener('pointermove', function(e){
      if(dragging) return;
      var r = stage.getBoundingClientRect();
      tilt = ((e.clientY - r.top) / r.height - 0.5) * -12;
      apply();
    });
    stage.addEventListener('pointerleave', function(){ tilt = 0; apply(); });
  }

  /* 转到背面 / 复位 */
  function flipBoard(toBack){
    board.classList.add('settling');
    rot = toBack ? BACK : FRONT;
    if(!toBack) tilt = 0;
    apply();
    setTimeout(function(){ board.classList.remove('settling'); }, 720);
  }
  /* 背面上的"转回正面" */
  var frontBtn = document.querySelector('[data-de-front]');
  if(frontBtn){
    frontBtn.addEventListener('click', function(e){
      e.stopPropagation();
      flipBoard(false);
    });
  }

  /* ---------- 放大查看（页头立牌 + 生态板块立牌共用一套） ----------
     两段式：先用页面上已缓存的小图瞬间铺满（点开零等待），
     放大图（AVIF，约 150KB）到达后淡入替换；鼠标悬停 / 手指按下就预热。
     放大图不点不下载，不占首屏体积。 */
  (function(){
    var AVIF_OK = (function(){
      try { return document.createElement('canvas').toDataURL('image/avif').indexOf('data:image/avif') === 0; }
      catch(e){ return false; }
    })();
    var boxes = document.querySelectorAll('[data-lb]');
    Array.prototype.forEach.call(boxes, function(lb){
      var btn  = document.querySelector('[data-lb-open="' + lb.id + '"]');
      var base = lb.querySelector('.de-lb-base');
      var hi   = lb.querySelector('.de-lb-hi');
      var url  = (AVIF_OK && lb.getAttribute('data-avif')) || lb.getAttribute('data-webp') || '';
      var warm = 0;
      function warmup(){
        if(warm || !url) return;
        warm = 1;
        var im = new Image();
        im.onload = function(){ hi.src = url; lb.classList.add('hi-ready'); };
        im.src = url;
      }
      function open(){
        if(base && !base.getAttribute('src')) base.setAttribute('src', lb.getAttribute('data-base') || '');
        lb.classList.add('open');
        document.body.style.overflow = 'hidden';
        warmup();
      }
      function close(){
        lb.classList.remove('open', 'z2');
        document.body.style.overflow = '';
      }
      if(btn){
        btn.addEventListener('click', function(e){ e.stopPropagation(); open(); });
        btn.addEventListener('pointerenter', warmup);                       // 桌面：悬停即预热
        btn.addEventListener('touchstart', warmup, {passive:true});         // 触屏：按下即预热
      }
      lb.addEventListener('click', function(e){
        if(e.target === base || e.target === hi){ lb.classList.toggle('z2'); return; }  // 点图 1×↔2×
        close();
      });
      lb.lbClose = close;
    });
    document.addEventListener('keydown', function(e){
      if(e.key !== 'Escape') return;
      Array.prototype.forEach.call(boxes, function(lb){ if(lb.lbClose) lb.lbClose(); });
    });
  })();

  /* ---------- KPI 悬浮明细（触屏点击展开） ---------- */
  var kpiCards = Array.prototype.slice.call(document.querySelectorAll('.de-kpi'));
  kpiCards.forEach(function(k){
    k.addEventListener('click', function(e){
      e.stopPropagation();
      var on = k.classList.contains('open');
      kpiCards.forEach(function(o){ o.classList.remove('open'); });
      if(!on) k.classList.add('open');
    });
  });
  document.addEventListener('click', function(){
    kpiCards.forEach(function(o){ o.classList.remove('open'); });
  });

  /* ---------- 人物动作：打招呼 / 转身 / 转到背面 / 复位 ---------- */
  var charEl = document.getElementById('deChar');
  /* 5 个分层图全部就绪后整体淡入，避免逐块弹出；2.5s 兜底强制显示，防止图片异常时人物消失 */
  (function(){
    if(!charEl) return;
    var imgs = Array.prototype.slice.call(charEl.querySelectorAll('img'));
    var left = imgs.length, shown = false;
    function ready(){ if(shown) return; shown = true; charEl.classList.add('ready'); }
    imgs.forEach(function(im){
      function one(){ if(--left <= 0) ready(); }
      if(im.complete && im.naturalWidth){ one(); }
      else { im.addEventListener('load', one); im.addEventListener('error', one); }
    });
    if(left <= 0) ready();
    setTimeout(ready, 2500);
  })();
  var sayEl = document.getElementById('deSay');  var btns = Array.prototype.slice.call(document.querySelectorAll('.de-act'));
  var CLS = ['act-hello', 'act-turn'];
  var CYCLE = ['hello', 'turn', 'back', 'reset'];
  var ci = -1;
  var reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  function play(a){
    if(!charEl) return;
    CLS.forEach(function(c){ charEl.classList.remove(c); });
    void charEl.offsetWidth;
    if(a === 'hello' || a === 'turn') charEl.classList.add('act-' + a);
    btns.forEach(function(b){ b.classList.toggle('on', b.getAttribute('data-act') === a); });
    if(a === 'back') flipBoard(true);
    else if(a === 'reset') flipBoard(false);
    var b = document.querySelector('.de-act[data-act="' + a + '"]');
    if(b && sayEl){
      sayEl.textContent = b.getAttribute('data-say');
      sayEl.classList.remove('pop');
      void sayEl.offsetWidth;
      sayEl.classList.add('pop');
    }
  }

  btns.forEach(function(b){
    var a = b.getAttribute('data-act');
    b.addEventListener('click', function(){
      play(a);
      ci = CYCLE.indexOf(a);
    });
  });

  /* 点击人物：按 打招呼 → 转身 → 转到背面 → 复位 循环 */
  if(charEl){
    charEl.addEventListener('click', function(e){
      e.stopPropagation();
      ci = (ci + 1) % CYCLE.length;
      play(CYCLE[ci]);
    });
  }

  /* 入场时自动打一次招呼 */
  if(!reduce && charEl){
    setTimeout(function(){ play('hello'); ci = 0; }, 2400);
  }
})();
</script>'''

# 业务流「点哪跳哪」：独立脚本，避免被上面 IIFE 里的早退影响
JUMP_JS = '''<script>
(function(){
  var HEAD_OFFSET = 78;   // 顶部导航高度留白

  function flash(el){
    el.classList.remove('cap-flash');
    void el.offsetWidth;                    // 强制重排，保证连续点同一张也能重新播动画
    el.classList.add('cap-flash');
    setTimeout(function(){ el.classList.remove('cap-flash'); }, 1800);
  }

  // 定位目标：优先按能力卡的 data-scene 名（如「渠道赋能」），
  // 其次按元素 id（如未来规划模块 future-home）
  function findTarget(name){
    var cards = document.querySelectorAll('.cap-card[data-scene]');
    for (var i = 0; i < cards.length; i++){
      if (cards[i].getAttribute('data-scene') === name) return cards[i];
    }
    if (/^[A-Za-z][\\w-]*$/.test(name)) return document.getElementById(name);
    return null;
  }

  function goto(name){
    var target = findTarget(name);
    if (!target) return;
    var y = target.getBoundingClientRect().top + window.pageYOffset - HEAD_OFFSET;
    var reduce = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    try {
      window.scrollTo({ top: y, behavior: reduce ? 'auto' : 'smooth' });
    } catch (e) {
      window.scrollTo(0, y);            // 极老浏览器不支持 options 对象时的兜底
    }
    setTimeout(function(){ flash(target); }, reduce ? 0 : 420);
  }

  // 从详情页点「返回」回到本页时会带 ?to=<卡名>，自动滚到那张卡并高亮一下
  try {
    var _to = new URLSearchParams(window.location.search).get('to');
    if (_to){
      if ('scrollRestoration' in history) history.scrollRestoration = 'manual';  // 别让浏览器恢复旧滚动位置盖掉定位
      setTimeout(function(){ goto(_to); }, 460);
    }
  } catch (e) {}

  var triggers = document.querySelectorAll('[data-jump]');
  for (var i = 0; i < triggers.length; i++){
    (function(el){
      el.addEventListener('click', function(){ goto(el.getAttribute('data-jump')); });
      el.addEventListener('keydown', function(e){
        if (e.key === 'Enter' || e.key === ' '){ e.preventDefault(); goto(el.getAttribute('data-jump')); }
      });
    })(triggers[i]);
  }
})();
</script>'''


def build_increment_board(increment_data):
    if not increment_data:
        return ''
    imgs = increment_data.get('images', [])
    if not imgs:
        return ''
    
    # 两张截图并排网格
    figures = ''
    for img in imgs[:2]:
        cap = img.get('caption', '')
        figures += f'<figure><img src="{img["src"]}" alt="">{"<figcaption>"+cap+"</figcaption>" if cap else ""}</figure>'
    
    title = increment_data.get('title', '一线增量情况')
    grid_style = 'grid-template-columns:repeat(2, 1fr);' if len(imgs) >= 2 else ''
    
    return f'''      <div class="increment-board">
        <div class="increment-title"><span class="ai-dot"></span>{title}</div>
        <div class="img-gallery col2" style="{grid_style}">{figures}</div>
      </div>'''


def build_bid_steps(bid_steps_data):
    if not bid_steps_data:
        return ''
    colors_all = [('#fecdd3','#be123c'),('#bbf7d0','#15803d'),('#bfdbfe','#1d4ed8')]
    cards = []
    for i, step in enumerate(bid_steps_data):
        bc, tc = colors_all[i] if i < len(colors_all) else colors_all[0]
        items = ''.join(f'<li>{item}</li>' for item in step['items'])
        cards.append(f'''<div class="bid-step-card" style="border-color:{bc}">
<div style="font-size:28px;margin-bottom:6px">{step['icon']}</div>
<div class="bid-step-title" style="color:{tc}">{step['title'].replace('·','<br>')}</div>
<ul class="bid-step-list">{items}</ul></div>''')
    arrows_html = '<div class="bid-step-arrow">→</div>'
    return f'<div class="bid-steps-grid">\n{cards[0]}\n{arrows_html}\n{cards[1]}\n{arrows_html}\n{cards[2]}</div>'


JS = '''<script>
window.addEventListener('scroll',()=>{const h=document.documentElement.scrollHeight-window.innerHeight;document.getElementById('prog').style.width=(h>0?window.scrollY/h*100:0)+'%'});
function gotoScene(id){const el=document.getElementById(id);if(!el)return;const top=el.getBoundingClientRect().top+window.scrollY-118;window.scrollTo({top,behavior:'smooth'})}
// 场景导航按钮 — 用 addEventListener 避免 CSP 拦截 onclick
document.querySelectorAll('.scene-nav-btn').forEach(function(btn){
  btn.addEventListener('click',function(){var sid=this.getAttribute('data-scene');if(sid) gotoScene(sid);});
});
// 场景折叠/展开 — 点击标题旁 ▼ 按钮收起内容
document.querySelectorAll('.scene-toggle').forEach(function(btn){
  btn.addEventListener('click',function(){
    var targetId=this.getAttribute('data-target');
    var body=document.getElementById(targetId);
    if(!body) return;
    var isCollapsed=body.classList.toggle('collapsed');
    this.classList.toggle('collapsed',isCollapsed);
  });
});
const navLinks=document.querySelectorAll('.nav-tabs a');
const sceneButtons=document.querySelectorAll('.scene-nav-btn');
const scenes=[{id:'scene-opp',navIdx:0},{id:'scene-visit',navIdx:1},{id:'scene-proj',navIdx:2},{id:'scene-bid',navIdx:3},{id:'scene-channel',navIdx:4},{id:'scene-skill',navIdx:5},{id:'scene-knowledge',navIdx:6}];
const io=new IntersectionObserver(entries=>{entries.forEach(e=>{if(e.isIntersecting){const idx=scenes.findIndex(s=>s.id===e.target.id);if(idx===-1)return;navLinks.forEach(a=>a.classList.remove('active'));sceneButtons.forEach(b=>b.classList.remove('active'));if(navLinks[idx])navLinks[idx].classList.add('active');if(sceneButtons[idx])sceneButtons[idx].classList.add('active')}})},{threshold:0.25});
scenes.forEach(s=>{const el=document.getElementById(s.id);if(el)io.observe(el)});

// 视频懒加载 + 进度指示 + 移动端友好
function loadVideo(wrapper){
  if(wrapper.dataset.loading==='1') return;
  var vid=wrapper.querySelector('video'),src=wrapper.getAttribute('data-video-src');
  if(!vid||!src) return;
  wrapper.dataset.loading='1';
  wrapper.classList.add('loading');
  wrapper.classList.remove('error');
  vid.innerHTML='<source src="'+src+'" type="video/mp4">';
  vid.load();
  vid.addEventListener('canplay',function(){
    wrapper.classList.remove('loading');
    wrapper.classList.add('playing');
    // 不自动播放，等待用户点击
  },{once:true});
  vid.addEventListener('error',function(){
    wrapper.classList.remove('loading');wrapper.classList.add('error');
    wrapper.dataset.loading='0';
  },{once:true});
}
// 进入视口附近时触发加载
var videoObs=new IntersectionObserver(function(entries){
  entries.forEach(function(e){ if(e.isIntersecting) loadVideo(e.target); });
},{rootMargin:'400px'});
document.querySelectorAll('.video-wrapper').forEach(function(w){videoObs.observe(w);});
// 点击占位区域触发加载 + 播放（pointerdown 同时覆盖 mouse + touch，无 300ms 延迟）
document.addEventListener('pointerdown',function(e){
  var ph=e.target.closest('.video-placeholder');
  if(!ph) return;
  var w=ph.closest('.video-wrapper');
  if(!w||w.dataset.loading==='1') return;
  if(e.target.classList.contains('vp-retry')){ loadVideo(w); return; }
  loadVideo(w);
  // 利用用户手势立即尝试播放（如果已缓存则直接播，否则 canplay 后再播）
  var vid=w.querySelector('video');
  if(vid) vid.play().catch(function(){});
});
const cards=document.querySelectorAll('.app-block');
const cardIO=new IntersectionObserver(entries=>{entries.forEach(e=>{if(e.isIntersecting){e.target.style.opacity='1';e.target.style.transform='translateY(0)'}})},{threshold:0.06});
cards.forEach(c=>{c.style.opacity='0';c.style.transform='translateY(24px)';c.style.transition='opacity .45s ease,transform .45s ease,box-shadow .25s';cardIO.observe(c)});
// 点赞评论模块 — MantleDB云端共享存储，所有人可见可累加
var FB_URL='https://mantledb.sh/v2/ah-mkt-feedback/data';
var FB_LIKE_URL='https://mantledb.sh/v2/increment/ah-mkt-feedback/data';
var fbLikedKey='fb-liked-'+new Date().toISOString().slice(0,10);
var fbLiked=localStorage.getItem(fbLikedKey)==='1';
var fbLikes=0,fbComments=[];

function fbGet(){
  return fetch(FB_URL).then(function(r){return r.json();}).then(function(d){
    // 兜底：如果MantleDB数据为空，尝试从localStorage恢复
    if((!d.likes&&!d.comments)||(d.likes===0&&(!d.comments||d.comments.length===0))){
      var backup=localStorage.getItem('fb-backup');
      if(backup){try{var b=JSON.parse(backup);if(b.likes||(b.comments&&b.comments.length)){return b;}}catch(e){}}
    }
    return d;
  });
}
function fbPut(data){
  return fetch(FB_URL,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)}).then(function(r){return r.json();});
}
function fbIncrement(key,by){
  return fetch(FB_LIKE_URL,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({key:key,by:by})}).then(function(r){return r.json();});
}

// 检测用户是否正在输入（避免同步时重绘DOM导致滚动/焦点丢失）
var fbTyping=false;
document.addEventListener('focusin',function(e){
  if(e.target.closest('#fb-name')||e.target.closest('#fb-text')||e.target.closest('.fb-reply-area textarea')) fbTyping=true;
});
document.addEventListener('focusout',function(e){
  if(e.target.closest('#fb-name')||e.target.closest('#fb-text')||e.target.closest('.fb-reply-area textarea')){
    setTimeout(function(){ fbTyping=false; },200);
  }
});

function syncFromCloud(){
  fbGet().then(function(d){
    fbLikes=d.likes||0; fbComments=d.comments||[];
    if(!fbTyping) renderFeedback();
    // 成功后写入localStorage备份
    try{localStorage.setItem('fb-backup',JSON.stringify({likes:fbLikes,comments:fbComments}));}catch(e){}
  }).catch(function(){});
}

function renderFeedback(){
  var lc=document.getElementById('fb-like-count'); if(!lc) return;
  lc.textContent=fbLikes+' 人觉得很赞';
  document.getElementById('fb-cmt-count').textContent=fbComments.length;
  var btn=document.getElementById('fb-like-btn');
  if(btn){ if(fbLiked) btn.classList.add('liked'); else btn.classList.remove('liked'); }
  var list=document.getElementById('fb-comment-list');
  if(!list) return;
  if(!fbComments.length){ list.innerHTML='<div class="fb-empty">暂无评论，来坐沙发吧 ☕</div>'; return; }
  list.innerHTML=fbComments.slice().reverse().map(function(c){
    var t=new Date(c.time),ts=t.getFullYear()+'-'+String(t.getMonth()+1).padStart(2,'0')+'-'+String(t.getDate()).padStart(2,'0')+' '+String(t.getHours()).padStart(2,'0')+':'+String(t.getMinutes()).padStart(2,'0');
    var rs=(c.replies||[]).map(function(r){var rt=new Date(r.time),rts=rt.getFullYear()+'-'+String(rt.getMonth()+1).padStart(2,'0')+'-'+String(rt.getDate()).padStart(2,'0')+' '+String(rt.getHours()).padStart(2,'0')+':'+String(rt.getMinutes()).padStart(2,'0');return '<div class="fb-reply-item"><strong>'+esc(r.name)+'</strong><span>'+rts+'</span>：'+esc(r.text)+'</div>';}).join('');
    return '<div class="fb-comment-item" data-cid="'+c.id+'"><div class="fb-comment-meta"><strong>'+esc(c.name)+'</strong><span>'+ts+'<button class="fb-reply-btn" data-cid="'+c.id+'" title="回复">💬 回复</button><button class="fb-comment-del" data-cid="'+c.id+'" title="删除">✕</button></span></div><div class="fb-comment-text">'+esc(c.text)+'</div>'+rs+'<div class="fb-reply-area" id="reply-area-'+c.id+'"><textarea id="reply-text-'+c.id+'" placeholder="写下回复…" rows="2" maxlength="200"></textarea><button data-cid="'+c.id+'" class="fb-reply-submit">回复</button></div></div>';
  }).join('');
}
function esc(s){var d=document.createElement('div');d.textContent=s;return d.innerHTML}

// 点赞按钮 — 原子递增，并发安全
var _fbLikeBtn=document.getElementById('fb-like-btn');
if(_fbLikeBtn) _fbLikeBtn.addEventListener('click',function(){
  if(fbLiked) return;
  fbLiked=true; fbLikes++;
  localStorage.setItem(fbLikedKey,'1');
  renderFeedback();
  fbIncrement('likes',1).then(function(d){
    if(d&&d.likes!==undefined) fbLikes=d.likes;
    renderFeedback();
    try{localStorage.setItem('fb-backup',JSON.stringify({likes:fbLikes,comments:fbComments}));}catch(e){}
  }).catch(function(){ syncFromCloud(); });
});

// 初始加载 + 15秒定时同步（仅在反馈模块存在时）
if(document.getElementById('fb-like-btn')){ syncFromCloud(); setInterval(syncFromCloud,15000); }

function submitComment(){
  var nameEl=document.getElementById('fb-name'),textEl=document.getElementById('fb-text');
  var name=nameEl.value.trim(),text=textEl.value.trim();
  if(!name||!text){alert('请填写昵称和评论内容');return}
  if(name.length>20||text.length>500){alert('昵称或内容超出限制');return}
  var c={id:'c_'+Date.now()+'_'+Math.random().toString(36).slice(2,6),name:name,text:text,time:new Date().toISOString(),replies:[]};
  // 乐观更新 + 云端同步 + localStorage备份
  fbComments.push(c); renderFeedback();
  nameEl.value=''; textEl.value=''; fbTyping=false;
  var data={likes:fbLikes,comments:fbComments};
  fbPut(data).then(function(){
    try{localStorage.setItem('fb-backup',JSON.stringify({likes:fbLikes,comments:fbComments}));}catch(e){}
  }).catch(function(){ syncFromCloud(); });
}
var _fbSubmitBtn=document.getElementById('fb-submit-btn');
if(_fbSubmitBtn) _fbSubmitBtn.addEventListener('click',submitComment);

function delComment(id){
  if(!confirm('确定删除这条评论吗？')) return;
  fbComments=fbComments.filter(function(c){return c.id!==id});
  renderFeedback();
  var data={likes:fbLikes,comments:fbComments};
  fbPut(data).then(function(){
    try{localStorage.setItem('fb-backup',JSON.stringify({likes:fbLikes,comments:fbComments}));}catch(e){}
  }).catch(function(){ syncFromCloud(); });
}

// 评论列表事件代理
var _fbCmtList=document.getElementById('fb-comment-list');
if(_fbCmtList) _fbCmtList.addEventListener('click',function(e){
  var delBtn=e.target.closest('.fb-comment-del');
  if(delBtn){ var cid=delBtn.getAttribute('data-cid'); if(cid) delComment(cid); return; }
  var replyBtn=e.target.closest('.fb-reply-btn');
  if(replyBtn){ var cid=replyBtn.getAttribute('data-cid'); if(cid) toggleReply(cid); return; }
  var replySubmit=e.target.closest('.fb-reply-submit');
  if(replySubmit){ var cid=replySubmit.getAttribute('data-cid'); if(cid) submitReply(cid); return; }
});

function toggleReply(cid){
  var area=document.getElementById('reply-area-'+cid);
  if(!area) return;
  area.classList.toggle('show');
  if(area.classList.contains('show')){ var ta=document.getElementById('reply-text-'+cid); if(ta) setTimeout(function(){ta.focus()},100); }
}
function submitReply(cid){
  var ta=document.getElementById('reply-text-'+cid);
  if(!ta) return;
  var text=ta.value.trim();
  if(!text){alert('请输入回复内容');return}
  if(text.length>200){alert('回复不能超过200字');return}
  var cmt=fbComments.find(function(c){return c.id===cid});
  if(!cmt) return;
  if(!cmt.replies) cmt.replies=[];
  var r={id:'r_'+Date.now()+'_'+Math.random().toString(36).slice(2,6),name:'网友',text:text,time:new Date().toISOString()};
  cmt.replies.push(r); renderFeedback(); fbTyping=false;
  var data={likes:fbLikes,comments:fbComments};
  fbPut(data).then(function(){
    try{localStorage.setItem('fb-backup',JSON.stringify({likes:fbLikes,comments:fbComments}));}catch(e){}
  }).catch(function(){ syncFromCloud();   });
}
// ---- 图片点击放大 Lightbox ----
(function(){
  var overlay=document.createElement('div');
  overlay.className='lightbox-overlay';
  overlay.innerHTML='<button class="lb-close" type="button">&times;</button><img src="" alt=""><div class="lb-caption"></div>';
  document.body.appendChild(overlay);
  var lbImg=overlay.querySelector('img');
  var lbCap=overlay.querySelector('.lb-caption');
  var lbClose=overlay.querySelector('.lb-close');
  function open(src,cap){
    lbImg.src=src; lbCap.textContent=cap||'';
    overlay.classList.add('active');
    document.body.style.overflow='hidden';
  }
  function close(){
    overlay.classList.remove('active');
    document.body.style.overflow='';
    lbImg.src='';
  }
  overlay.addEventListener('click',function(e){ if(e.target===overlay||e.target===lbClose) close(); });
  document.addEventListener('keydown',function(e){ if(e.key==='Escape') close(); });
  document.addEventListener('click',function(e){
    var fig=e.target.closest('.img-gallery figure');
    if(!fig) return;
    var img=fig.querySelector('img');
    if(!img) return;
    var cap=fig.querySelector('figcaption');
    open(img.src, cap?cap.textContent:'');
  });
})();
</script>'''


def md_to_html(md_text):
    """将markdown格式文本转为HTML片段"""
    text = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', md_text)
    parts = text.split('\n\n')
    result = []
    for p in parts:
        p = p.strip()
        if not p: continue
        lines = p.split('\n')
        if lines[0].startswith('- '):
            items = [li[2:] for li in lines if li.startswith('- ')]
            result.append('<ul>\n          ' + '\n          '.join(f'<li>{item}</li>' for item in items) + '\n        </ul>')
        elif any(li.startswith('- ') for li in lines):
            out = []
            buf = []
            for li in lines:
                li = li.strip()
                if li.startswith('- '):
                    buf.append(li[2:])
                else:
                    if buf:
                        out.append('<ul>\n          ' + '\n          '.join(f'<li>{item}</li>' for item in buf) + '\n        </ul>')
                        buf = []
                    if li:
                        out.append(f'<p>{li}</p>')
            if buf:
                out.append('<ul>\n          ' + '\n          '.join(f'<li>{item}</li>' for item in buf) + '\n        </ul>')
            result.extend(out)
        elif len(lines) > 1:
            result.append(f'<p>{"<br>".join(lines)}</p>')
        else:
            result.append(f'<p>{p}</p>')
    return '\n        '.join(result)


def build_bid_compare(bid_compare_data):
    if not bid_compare_data:
        return ''
    headers = bid_compare_data['headers']
    rows = bid_compare_data['rows']
    if not headers or not rows:
        return ''
    
    # 表头（第一列留空作为行标签列）
    headers_html = ''.join(f'<th>{h}</th>' for h in headers[1:])  # 跳过第一列（版本/上线时间）
    
    # 数据行
    rows_html = ''
    for cells in rows:
        if not cells:
            continue
        # 第一列作为行标签（带版本标签样式）
        row_label = cells[0] if len(cells) > 0 else ''
        label_cls = 'new'
        if 'V1.0' in row_label or '治理前' in row_label:
            label_cls = 'old'
        label_html = f'<span class="bid-ver-tag {label_cls}">{row_label}</span>'
        
        # 其余列
        data_cells = ''
        for i, cell in enumerate(cells[1:], 1):
            # 数据治理列、数量列等较长文本用 td-desc
            if i < len(headers) and headers[i] in ('数据治理', '数量'):
                data_cells += f'<td class="td-desc">{cell}</td>'
            else:
                data_cells += f'<td>{cell}</td>'
        
        rows_html += f'\n            <tr class="{label_cls}-row"><td>{label_html}</td>{data_cells}</tr>'
    
    return f'''      <div class="bid-compare">
        <div class="bid-compare-title"><span class="ai-dot"></span>AI助力高价值标讯</div>
        <table class="bid-table">
          <thead><tr><th></th>{headers_html}</tr></thead>
          <tbody>{rows_html}
          </tbody>
        </table>
      </div>'''


def build_capability_table(capability_data):
    """渲染应用能力集表格：支持第一列空单元格合并（rowspan），放在视频上方"""
    if not capability_data:
        return ''
    headers = capability_data['headers']
    rows = capability_data['rows']
    if not headers or not rows:
        return ''

    ncols = len(headers)
    # 第一列做合并分组
    groups = []  # (label, rows_list)
    for cells in rows:
        if len(cells) < ncols:
            cells = cells + [''] * (ncols - len(cells))
        label = cells[0].strip()
        if label:
            groups.append({'label': label, 'items': [cells[1:]]})
        else:
            if groups:
                groups[-1]['items'].append(cells[1:])
            else:
                groups.append({'label': '', 'items': [cells[1:]]})

    rows_html = ''
    for gi, g in enumerate(groups):
        items = g['items']
        rowspan = len(items)
        # 第一列单元格（跨行）
        first_td = f'<td class="cap-cat" rowspan="{rowspan}"><span class="cap-cat-tag">{g["label"]}</span></td>' if rowspan > 1 else f'<td class="cap-cat"><span class="cap-cat-tag">{g["label"]}</span></td>'
        for ii, cells in enumerate(items):
            tds = ''
            for ci, cell in enumerate(cells):
                if ci == 0:
                    tds += f'<td class="cap-skill">{cell}</td>'
                else:
                    cls = 'cap-src' if ci == len(cells) - 1 else ''
                    tds += f'<td class="{cls}">{cell}</td>'
            if ii == 0:
                rows_html += f'<tr>{first_td}{tds}</tr>\n            '
            else:
                rows_html += f'<tr>{tds}</tr>\n            '

    headers_html = ''.join(f'<th>{h}</th>' for h in headers)

    return f'''      <div class="cap-board">
        <div class="cap-title"><span class="ai-dot"></span>应用能力集</div>
        <div class="cap-table-wrap">
          <table class="cap-table">
            <thead><tr>{headers_html}</tr></thead>
            <tbody>{rows_html}
            </tbody>
          </table>
        </div>
      </div>'''


def render_scene(data, scene):
    """渲染单个场景为 HTML 字符串（详情页用）"""
    scene_id_map = {1:'scene-opp',2:'scene-visit',3:'scene-proj',4:'scene-bid',5:'scene-channel',6:'scene-skill',7:'scene-knowledge'}
    bg_map = {1:'bg-opp',2:'bg-visit',3:'bg-proj',4:'bg-bid',5:'bg-channel',6:'bg-skill',7:'bg-knowledge'}
    icon_colors = ["linear-gradient(135deg,#0f2b5c,#1e4f8a)","linear-gradient(135deg,#00a884,#00b894)","linear-gradient(135deg,#0f2b5c,#5b3fd4)","linear-gradient(135deg,#e8710a,#dc2626)","linear-gradient(135deg,#0d9488,#14b8a6)","linear-gradient(135deg,#0ea5e9,#0284c7)","linear-gradient(135deg,#6366f1,#8b5cf6)"]
    badge_maps = {
        1: [("linear-gradient(135deg,#0f2b5c,#1e4f8a)","1"),("linear-gradient(135deg,#0284c7,#0891b2)","2"),("linear-gradient(135deg,#0891b2,#0e7490)","3"),("linear-gradient(135deg,#0e7490,#059669)","4")],
        2: [("linear-gradient(135deg,#00a884,#00b894)","1"),("linear-gradient(135deg,#0284c7,#4f46e5)","2")],
        3: [("linear-gradient(135deg,#0f2b5c,#5b3fd4)","1"),("linear-gradient(135deg,#5b3fd4,#e8710a)","2")],
        4: [("linear-gradient(135deg,#e8710a,#dc2626)","AI")],
        5: [("linear-gradient(135deg,#0d9488,#14b8a6)","1"),("linear-gradient(135deg,#14b8a6,#0ea5e9)","2")],
        6: [("linear-gradient(135deg,#0ea5e9,#0284c7)","1"),("linear-gradient(135deg,#0284c7,#0891b2)","2")],
        7: [("linear-gradient(135deg,#6366f1,#8b5cf6)","AI")]
    }
    pain_emojis = {1:'📊',2:'🔍',3:'🔀',4:'😰',5:'📈',6:'🛠️',7:'📚'}
    solve_emojis = {1:'⚡',2:'✨',3:'⚡',4:'🏆',5:'⚡',6:'✨',7:'💡'}
    how_emojis = {1:'🗺️',2:'🎯',3:'🗝️',4:'🗝️',5:'🏭',6:'🔧',7:'🔮'}
    # 路径链接可以写网址，也可以写「入口链接映射」里的入口名称 → 这里统一取一次映射表
    entry_links = ((data.get('de_page') or {}).get('entry_links') or {})

    profile_preview = '''    <div class="profile-preview">
      <div class="profile-preview-label"><span class="pdot"></span>{profile_label} <span class="pbeta">NEW</span> — 下滑查看最新画像内容</div>
      <div class="profile-preview-frame"><iframe src="{profile_src}" title="客户安全画像"></iframe></div>
    </div>'''

    report_preview = '''    <div class="report-preview">
      <div class="report-preview-label"><span class="pdot"></span>{report_label} <span class="pbeta">REPORT</span> — 下滑查看完整报告</div>
      <div class="report-preview-frame"><img src="{report_src}" alt="{report_label}" loading="lazy"></div>
    </div>'''

    snum = scene['num']
    sid = scene_id_map.get(snum, f'scene-{snum}')
    bg = bg_map.get(snum,'')
    icon = scene.get('icon','🎯')
    title = scene.get('title','')
    subtitle = scene.get('subtitle','')
    icon_color = icon_colors[min(snum-1, len(icon_colors)-1)]
    count = f'{len(scene["apps"])}个应用' if snum not in (4,) else '3大能力'

    stats = ''
    if scene.get('stats'):
        items = [f'<div class="ss-item"><div class="ss-num">{st["num"]}</div><div class="ss-label">{st["label"]}</div></div>' for st in scene['stats']]
        stats = f'\n<div class="stats-strip">{"" .join(items)}</div>\n'

    bid_steps = ''
    if snum == 4:
        bid_app = next((a for a in scene['apps'] if a.get('bid_steps')), None)
        bid_steps = build_bid_steps(bid_app['bid_steps']) if bid_app else ''

    apps_html = ''
    for ai, app in enumerate(scene['apps']):
        bc = badge_maps.get(snum, [])
        badge_style, badge_num = bc[ai] if ai < len(bc) else bc[0] if bc else ('linear-gradient(135deg,#0f2b5c,#1e4f8a)','1')

        pain = md_to_html(app.get('pain',''))
        solve = md_to_html(app.get('solve',''))

        how_parts = []
        if app.get('how'):
            how_parts.append(f'<p>{re.sub(r"\*\*(.+?)\*\*",r"<strong>\1</strong>",app["how"])}</p>')
        for p in app.get('paths', []):
            if isinstance(p, str):
                p = {'text': p, 'link': ''}
            tag_html = ' <span class="arr">→</span> '.join(f'<span>{tp.strip()}</span>' for tp in p['text'].split('→'))
            _lk = (p.get('link') or '').strip()
            if _lk and not re.match(r'(?:https?|dingtalk)://', _lk, re.I):
                _lk = entry_links.get(_lk, '')          # 写的是入口名称 → 查映射表
            if _lk:
                how_parts.append(
                    f'<a class="path-tag path-tag-link" href="{_lk.replace("&", "&amp;")}"'
                    f' target="_blank" rel="noopener noreferrer" title="点击跳转前往体验">'
                    f'{tag_html}<i class="pt-arw">↗</i></a>')
            else:
                how_parts.append(f'<div class="path-tag">{tag_html}</div>')
        for e in app.get('extra_info', []):
            if isinstance(e,tuple) and e[0]=='path_title':
                how_parts.append(f'<p style="font-weight:700;margin:10px 0 4px;">{e[1]}</p>')
            else:
                how_parts.append(f'<p style="font-size:12px;color:var(--muted);margin-top:8px;">{e}</p>')
        # 入口链接（可点击跳转）
        if app.get('entry_link') and app.get('entry_text'):
            how_parts.append(f'<a href="{app["entry_link"]}" target="_blank" rel="noopener" style="display:inline-flex;align-items:center;gap:6px;margin-top:10px;padding:10px 20px;background:linear-gradient(135deg,#0d2550,#1a3d6e);color:#fff;border-radius:10px;font-weight:600;font-size:14px;text-decoration:none;transition:all .28s;">{app["entry_text"]} <span style="font-size:12px;">↗</span></a>')
        how_html = '\n        '.join(how_parts)

        pe = pain_emojis.get(snum,'📊')
        se = solve_emojis.get(snum,'⚡')
        he = how_emojis.get(snum,'🗝️')

        app_stats_html = ''
        if app.get('stats'):
            stats_items = [f'<div class="app-stats-item"><div class="app-stats-num">{st["num"]}</div><div class="app-stats-label">{st["label"]}</div></div>' for st in app['stats']]
            note = f'<div class="app-stats-item app-stats-note-inline">{app["stats_note"]}</div>' if app.get('stats_note') else ''
            app_stats_html = f'\n<div class="app-stats-strip">{"" .join(stats_items)}{note}</div>\n'

        video_panel = ''
        # 应用能力集（图片优先，否则表格）
        if app.get('cap_images'):
            cap_imgs_html = '\n          '.join(f'<img src="{img}" alt="应用能力集" loading="lazy" style="width:100%;display:block;border:none;">' for img in app['cap_images'])
            _n = len(app['cap_images'])
            _hint = (f'<span class="ct-hint">共 {_n} 张 · 框内下滑查看 ⇅</span>' if _n > 1 else '')
            video_panel += f'''    <div class="cap-board">
      <div class="cap-title"><span class="ai-dot"></span>应用能力集{_hint}</div>
      <div class="cap-img-wrap">
        {cap_imgs_html}
      </div>
    </div>\n'''
        else:
            _cap = build_capability_table(app.get('capability'))
            if _cap:
                video_panel += _cap + '\n'
        # 渲染视频（如果有）
        if app.get('placeholder'):
            video_panel += f'''    <div class="app-video-panel">
      <div class="app-video-label"><span class="vdot"></span>应用演示视频（移动端演示）</div>
      <div class="no-video"><div class="nv-ico">{app.get('placeholder_icon','📱')}</div><p>{app.get('placeholder_text','')}</p></div>
    </div>'''
        elif app.get('video'):
            vlabel = app.get('video_label', '应用演示视频')
            video_panel += f'''    <div class="app-video-panel">
      <div class="app-video-label"><span class="vdot"></span>{vlabel}</div>
      <div class="video-wrapper" data-video-src="media/{app['video']}"><video controls playsinline webkit-playsinline x5-playsinline preload="none" controlslist="nodownload" style="position:relative;z-index:1" poster="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 16 9'><rect fill='%230a0d14' width='16' height='9'/></svg>"></video><div class="video-placeholder"><div class="vp-icon-wrap" style="display:flex;flex-direction:column;align-items:center;gap:14px"><span class="vp-icon">▶</span></div><div class="vp-loading"><span class="vp-spinner"></span><span class="vp-progress">视频加载中...</span></div><div class="vp-error"><span>⚠️ 加载失败</span><button class="vp-retry" type="button">重新加载</button></div></div></div>
    </div>'''
        
        # 渲染截图（如果有）——可与视频同时存在
        if app.get('images') and not app.get('placeholder'):
            imgs = app['images']
            _bid = build_bid_compare(app.get('bid_compare'))
            if _bid and len(imgs) >= 2:
                video_panel += f'''    <div class="bid-flow-platform">
      <div class="app-video-panel">
        <div class="app-video-label"><span class="vdot" style="background:#38bdf8;"></span>业务流</div>
        <div class="img-gallery img-gallery-single"><figure><img src="{imgs[0]["src"]}" alt=""><figcaption>{imgs[0].get("caption","")}</figcaption></figure></div>
      </div>
      <div class="app-video-panel">
        <div class="app-video-label"><span class="vdot" style="background:#f59e0b;"></span>平台</div>
        <div class="img-gallery img-gallery-single"><figure><img src="{imgs[1]["src"]}" alt=""><figcaption>{imgs[1].get("caption","")}</figcaption></figure></div>
      </div>
    </div>'''
                if _bid: video_panel += '\n' + _bid
            else:
                # 区分移动端和PC端截图
                figs = []
                for img in imgs:
                    cap = img.get('caption', '')
                    # 根据说明中的emoji判断是移动端还是PC端
                    is_mobile = '📱' in cap
                    is_pc = '💻' in cap
                    mobile_cls = ' mobile-screenshot' if is_mobile else ''
                    pc_cls = ' pc-screenshot' if is_pc else ''
                    fig_cls = mobile_cls + pc_cls
                    figs.append(f'<figure class="{fig_cls.strip()}"><img src="{img["src"]}" alt="">{"<figcaption>"+cap+"</figcaption>" if cap else ""}</figure>')
                n = len(imgs)
                gcol = 'col1' if n==1 else ('col2' if n==2 else ('col5' if n==5 else ''))
                video_panel += f'''    <div class="app-video-panel">
      <div class="app-video-label"><span class="vdot" style="background:#38bdf8;"></span>应用演示截图</div>
      <div class="img-gallery {gcol}">{chr(10).join(figs)}</div>
    </div>'''

        apps_html += f'''
  <div class="app-block" id="app-s{snum}-{ai+1}">
    <div class="app-block-header">
      <div class="app-num-badge" style="background:{badge_style};{'font-size:13px;' if badge_num=='AI' else ''}">{badge_num}</div>
      <div><div class="app-title">{app['title']}</div><div class="app-subtitle">{app.get('subtitle','')}</div></div>
      {f'<a href="{app["guide_link"]}" class="app-guide-card" target="_blank" rel="noopener"><svg viewBox="0 0 24 24"><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"></path><polyline points="15 3 21 3 21 9"></polyline><line x1="10" y1="14" x2="21" y2="3"></line></svg>操作指南</a>' if app.get('guide_link') else ''}
    </div>{app_stats_html}
    <div class="app-content">
      <div class="app-col"><div class="app-col-inner"><div class="col-label col-label-pain">😩 用户痛点</div>{pain}</div><div class="col-emoji-bg">{pe}</div></div>
      <div class="app-col"><div class="app-col-inner"><div class="col-label col-label-solve">✅ AI能帮你</div>{solve}</div><div class="col-emoji-bg">{se}</div></div>
      <div class="app-col"><div class="app-col-inner"><div class="col-label col-label-how">🔧 平台入口</div>{how_html}</div><div class="col-emoji-bg">{he}</div></div>
    </div>
{video_panel}
    {report_preview.format(report_src=media_path(app.get('report_preview','')), report_label=app.get('report_label','运营报告')) if app.get('report_preview') else ''}
    {profile_preview.format(profile_src=app.get('profile_preview','media/天津大学_安全画像.html'), profile_label=app.get('profile_label','客户画像 2.0 优化中')) if (snum==2 and ai==0 and app.get('profile_preview')) else ''}  </div>'''
        
        # 渲染一线增量情况（如果该应用有）
        if app.get('increment'):
            apps_html += '\n' + build_increment_board(app['increment'])

    return f'''<div class="scene-timeline-item" id="{sid}">
<div class="{bg}">
<div class="scene-section">
  <div class="scene-header">
    <div class="scene-header-ico" style="background:{icon_color};color:#fff;">{icon}</div>
    <div><div class="scene-title">{title}</div><div class="scene-sub">{subtitle}</div></div>
    <div class="scene-count">{count}</div>
  </div>
  <div class="scene-body">
{stats}{bid_steps}{apps_html}
  </div>
</div>
</div>
</div>'''


def build_arch_section():
    """AI应用矩阵section：中央Hub + 4个维度分支（按PPT 1:1文案，带跳转链接）"""
    dimensions = [
        {
            'color': 'blue', 'icon': '🚀', 'name': '抓增量', 'en': 'GROWTH',
            'desc': '看清市场空间、数据驱动作战',
            'apps': [('市场空间报告', None), ('标讯推送', None), ('......', None)],
            'card_link': 'scene-1.html'  # 整卡跳转机会点增量
        },
        {
            'color': 'purple', 'icon': '✨', 'name': '抓质量', 'en': 'QUALITY',
            'desc': '提升拜访、招投标方案质量',
            'apps': [('AI对练', 'scene-2.html#app-s2-2'), ('标书制作及检查', 'scene-4.html'), ('......', None)],
            'card_link': None  # 不整卡跳转，各app独立跳转
        },
        {
            'color': 'orange', 'icon': '⚡', 'name': '提能效', 'en': 'EFFICIENCY',
            'desc': '整合行销能力，全面搜集客户信息',
            'apps': [('行销数字员工', 'scene-3.html#app-s3-2'), ('客户画像', 'scene-2.html#app-s2-1'), ('......', None)],
            'card_link': None  # 不整卡跳转
        },
        {
            'color': 'teal', 'icon': '🛠️', 'name': '助管理', 'en': 'MANAGEMENT',
            'desc': '辅助管理决策、业务关键信息查询',
            'apps': [('营销AI小秘', None), ('查企业、查价格', None), ('......', None)],
            'card_link': 'scene-3.html#app-s3-1'  # 整卡跳转营销AI小秘
        }
    ]

    def with_source(link):
        if not link:
            return link
        if '?' in link:
            if '#' in link:
                base_q, frag = link.split('#', 1)
                return f'{base_q}&from=ai-arch#{frag}'
            return f'{link}&from=ai-arch'
        if '#' in link:
            base, frag = link.split('#', 1)
            return f'{base}?from=ai-arch#{frag}'
        return f'{link}?from=ai-arch'

    cards_html = ''
    for d in dimensions:
        apps_html = ''
        for app_name, app_link in d['apps']:
            if app_link:
                apps_html += f'<div class="ac-app"><span class="ac-app-dot"></span><a href="{with_source(app_link)}" class="ac-app-link">{app_name}</a></div>\n'
            else:
                apps_html += f'<div class="ac-app"><span class="ac-app-dot"></span>{app_name}</div>\n'

        if d.get('card_link'):
            card_link = with_source(d['card_link'])
            cards_html += (
                f'<a href="{card_link}" class="arch-card arch-card-linkable" data-color="{d["color"]}">\n'
                f'  <div class="arch-card-top">\n'
                f'    <div class="ac-icon">{d["icon"]}</div>\n'
                f'    <div>\n'
                f'      <div class="ac-name">{d["name"]}</div>\n'
                f'      <div class="ac-en">{d["en"]}</div>\n'
                f'    </div>\n'
                f'  </div>\n'
                f'  <div class="ac-desc">{d["desc"]}</div>\n'
                f'  <div class="ac-divider"></div>\n'
                f'  <div class="ac-divider-label">AI 应用</div>\n'
                f'  <div class="ac-apps">\n'
                f'{apps_html}\n'
                f'  </div>\n'
                f'</a>\n'
            )
        else:
            cards_html += (
                f'<div class="arch-card" data-color="{d["color"]}">\n'
                f'  <div class="arch-card-top">\n'
                f'    <div class="ac-icon">{d["icon"]}</div>\n'
                f'    <div>\n'
                f'      <div class="ac-name">{d["name"]}</div>\n'
                f'      <div class="ac-en">{d["en"]}</div>\n'
                f'    </div>\n'
                f'  </div>\n'
                f'  <div class="ac-desc">{d["desc"]}</div>\n'
                f'  <div class="ac-divider"></div>\n'
                f'  <div class="ac-divider-label">AI 应用</div>\n'
                f'  <div class="ac-apps">\n'
                f'{apps_html}\n'
                f'  </div>\n'
                f'</div>\n'
            )

    return (
        '<section class="arch-section" id="ai-arch">\n'
        '  <div class="arch-inner">\n'
        '    <div class="arch-title">\n'
        '      <span class="at-pill">AI应用矩阵</span>\n'
        '    </div>\n'
        '    <div class="arch-sub">围绕提升<strong>增量、质量、能效、管理</strong>四大目标，设计营销AI应用，<strong>赋能全链路营销业务</strong></div>\n'
        '    <div class="arch-grid">\n'
        + cards_html +
        '    </div>\n'
        '  </div>\n'
        '</section>'
    )


def build_incentive_section(data=None):
    """激励section：3张大卡片（与6场景卡片同尺寸）+ 底部行动信息 — 从content.md读取配置"""
    action_text = ''
    if data and data.get('global', {}).get('Hero行动信息'):
        action_text = data['global']['Hero行动信息']
    
    # 从 data['incentive'] 读取，fallback到硬编码
    inc_data = data.get('incentive', {}) if data else {}
    inc_title = inc_data.get('标题', '积极使用 AI，更有 丰厚激励 等你拿')
    inc_sub = inc_data.get('副标题', '积极使用AI工具，主动反馈优化建议，甚至自建提效Skill——优秀实践可获月度激励、专项大奖及年度荣誉！')
    cards = inc_data.get('cards', [
        {
            'glow': 'gold', 'icon': '🏆', 'title': '10W专项激励', 'en': 'SPECIAL AWARD',
            'desc': '针对AI应用有突出贡献的个人/团队，提供10万元专项激励基金，授予年度AI应用先锋荣誉。',
            'stats': [('10W', '专项基金'), ('营销全员', '参与范围')],
            'tags': ['突出贡献', '先锋团队', '专项基金'],
            'link': 'https://365.kdocs.cn/l/cqQpJWaDnycr', 'link_text': '查看激励详情'
        },
        {
            'glow': 'blue', 'icon': '📅', 'title': '常态化月度激励', 'en': 'MONTHLY AWARD',
            'desc': '每月评选AI应用之星，月度公示、月度激励，让AI使用习惯持续渗透到每一个一线团队。',
            'stats': [('月度', '评选节奏'), ('全国助理', '综合管理部激励'), ('行销部全员', '行销激励')],
            'tags': ['月度之星', '持续激励', '全员覆盖'],
            'link': 'https://ah-marketing-2026.github.io/honor/', 'link_text': '查看荣誉榜单'
        },
        {
            'glow': 'purple', 'icon': '🎯', 'title': '年底综合激励', 'en': 'YEAR-END AWARD',
            'desc': '年底综合评定，AI应用标杆团队/个人额外奖励，颁发年度AI赋能营销奖项，纳入绩效考核。',
            'stats': [('年度', '综合评优'), ('标杆', '示范效应')],
            'tags': ['年度评优', '绩效加分', '示范标杆'],
            'link': '#', 'link_text': '敬请期待'
        }
    ])

    cards_html = ''
    for c in cards:
        stats_html = ''.join(
            f'<div><div class="inc-stat-num">{n}</div><div class="inc-stat-label">{l}</div></div>'
            for n, l in c['stats']
        )
        tags_html = ''.join(
            f'<span class="inc-card-tag">{t}</span>' for t in c['tags']
        )
        card_link = c.get('link', '') or '#'
        is_disabled = card_link == '#' or not card_link.strip() or card_link.strip() == '敬请期待'
        cta_class = 'inc-card-cta no-arrow' if is_disabled else 'inc-card-cta'
        cta_html = f'<div class="{cta_class}">{c["link_text"]}</div>'
        if is_disabled:
            # 无跳转：普通 div 卡片
            cards_html += (
                f'<div class="inc-card" data-glow="{c["glow"]}">\n'
                f'  <div class="inc-card-icon">{c["icon"]}</div>\n'
                f'  <div class="inc-card-title">{c["title"]}</div>\n'
                f'  <div class="inc-card-en">{c["en"]}</div>\n'
                f'  <div class="inc-card-desc">{c["desc"]}</div>\n'
                f'  <div class="inc-card-stats">{stats_html}</div>\n'
                f'  <div class="inc-card-tags">{tags_html}</div>\n'
                f'  {cta_html}\n'
                f'</div>\n'
            )
        else:
            cards_html += (
                f'<a href="{card_link}" target="_blank" class="inc-card" data-glow="{c["glow"]}">\n'
                f'  <div class="inc-card-icon">{c["icon"]}</div>\n'
                f'  <div class="inc-card-title">{c["title"]}</div>\n'
                f'  <div class="inc-card-en">{c["en"]}</div>\n'
                f'  <div class="inc-card-desc">{c["desc"]}</div>\n'
                f'  <div class="inc-card-stats">{stats_html}</div>\n'
                f'  <div class="inc-card-tags">{tags_html}</div>\n'
                f'  {cta_html}\n'
                f'</a>\n'
            )

    action_line = f'    <div class="inc-action">{action_text}</div>\n' if action_text else ''

    return (
        '<section class="inc-section">\n'
        '  <div class="inc-inner">\n'
        '    <div class="inc-header">\n'
        f'      <div class="inc-title">{inc_title}</div>\n'
        f'      <div class="inc-sub">{inc_sub}</div>\n'
        '    </div>\n'
        '    <div class="inc-grid">\n'
        + cards_html +
        '    </div>\n'
        + action_line +
        '  </div>\n'
        '</section>'
    )


def build_future_section_home(data, tag_origin=False):
    """未来规划 首页独立模块：放在激励模块下方"""
    g = data['global']
    fp = data.get('future_plan', {})
    title = fp.get('标题', '未来规划')
    subtitle = fp.get('副标题', '统一入口 · 整合资源 · 建设营销AI综合能力平台')
    status = fp.get('status', '')
    if not status:
        status = '当前各类AI应用分散在不同平台，一线员工在外部AI工具上积累了大量实战经验。未来我们将统一整合、沉淀推广，形成完整营销AI工具矩阵。'

    # 页面若挂在「超级数字员工」下（tag_origin=True），链接带上 ?from=xx&to=future-home，
    # 未来页的「返回」就会指回超级数字员工页的这块未来规划模块（id=future-home）
    _p, _u, _t = _src_back(data)
    furl = 'future.html' + (('?from=' + _p + '&to=future-home') if (tag_origin and _p) else '')
    furl = furl.replace('&', '&amp;')   # 放进 HTML href 前先按规范转义

    return (
        '<section class="future-home-section" id="future-home">\n'
        '  <div class="future-home-inner">\n'
        '    <div class="future-home-header">\n'
        '      <div class="future-home-pill">FUTURE PLAN</div>\n'
        '      <div class="future-home-title">' + title + '</div>\n'
        '      <div class="future-home-subtitle">' + subtitle + '</div>\n'
        '    </div>\n'
        '    <a href="' + furl + '" class="future-home-card">\n'
        '      <div class="future-home-icon">🚀</div>\n'
        '      <div class="future-home-card-body">\n'
        '        <div class="future-home-card-title">建设营销AI综合能力平台</div>\n'
        '        <div class="future-home-card-desc">' + status + '</div>\n'
        '        <div class="future-home-tags">\n'
        '          <span class="future-home-tag">统一入口</span>\n'
        '          <span class="future-home-tag">整合资源</span>\n'
        '          <span class="future-home-tag">持续迭代</span>\n'
        '        </div>\n'
        '        <div class="future-home-cta">查看未来规划</div>\n'
        '      </div>\n'
        '    </a>\n'
        '  </div>\n'
        '</section>'
    )


def _src_back(data, param=None):
    """返回联动：从「超级数字员工」页跳去详情页时带 ?from=xx，
    目标页读到该参数就把「返回」指回本页。返回 (param, back_url, back_text)。"""
    de = data.get('de_page') or {}
    meta = de.get('meta', {}) or {}
    g = data.get('global', {})
    p = (param if param is not None else meta.get('来源参数', '')) or ''
    url = (g.get('数字员工入口链接', '') or 'digital-employee.html').strip()
    txt = (meta.get('来源返回文字', '') or '').strip()
    return p.strip(), url, txt


def _back_js(data, selector='.back-to-module'):
    """生成「返回指回来处」的 JS 片段（要塞进已有 <script> 里，params 变量需已存在）。

    - 只改「返回」那一枚按钮（`.back-to-module`），不动「← 返回首页」
    - 把跳进来时带的 `?to=<卡名>` 透传回去，让超级数字员工页定位到对应的场景卡
    - 按钮文字默认保持原样（「返回」）；`来源返回文字` 填了才替换
    """
    p, url, txt = _src_back(data)
    if not p:
        return ''
    joiner = '&' if '?' in url else '?'
    return (
        f"  if (params.get('from') === {json.dumps(p)}) {{\n"
        f"    var _to = params.get('to') || '';\n"
        f"    var _x = {json.dumps(txt, ensure_ascii=False)};\n"
        f"    var _t = {json.dumps(url, ensure_ascii=False)} + (_to ? ({json.dumps(joiner)} + 'to=' + encodeURIComponent(_to)) : '');\n"
        f"    var _ls = document.querySelectorAll({json.dumps(selector)});\n"
        f"    for (var _i = 0, _a; (_a = _ls[_i]); _i++) _a.setAttribute('href', _t);\n"
        f"    if (_ls[0] && _x) _ls[0].textContent = _x;\n"
        f"  }}"
    )


def _de_nav_btn(g):
    """超级数字员工 导航入口按钮。文案/链接来自 content.md「全局信息」的
    「数字员工入口文字」/「数字员工入口链接」，改 md 即可全站生效。"""
    txt = (g.get('数字员工入口文字', '') or '超级数字员工').strip()
    lnk = (g.get('数字员工入口链接', '') or 'digital-employee.html').strip()
    return (f'<a class="nav-de-btn" href="{lnk}" title="进入 {txt} 专页">'
            f'<span class="nde-dot"></span><span class="nde-txt">{txt}</span></a>')


def build_home(data):
    """生成首页 index.html — Hero + 卡片网格"""
    g = data['global']
    logo = media_path(g.get('Logo图片', 'media/image2.png'))
    # 超级数字员工入口（导航按钮 + hero 圆形入口）—— 全部来自 content.md「全局信息」
    orb_text = (g.get('数字员工入口文字', '') or '超级数字员工').strip()
    orb_link = (g.get('数字员工入口链接', '') or 'digital-employee.html').strip()
    orb_face = media_path(g.get('数字员工入口头像', 'media/de_orb_face.png'))
    orb_title = (g.get('数字员工入口标题', '') or f'点击查看 {orb_text}').strip()

    nav = f'''<nav>
  <a class="nav-brand" href="index.html"><img src="{logo}" alt="安恒信息"><span>AI赋能营销</span></a>
  <div class="nav-actions">
    <a class="nav-de-btn" href="{orb_link}" title="进入 {orb_text} 专页"><span class="nde-dot"></span><span class="nde-txt">{orb_text}</span></a>
    <div class="nav-right"><img src="{logo}" alt=""><span class="nav-right-dept">{g.get('页脚部门','安恒信息 · 营销中心 · 综合管理部')}</span></div>
  </div>
</nav>'''

    hero = f'''<section class="hero" id="hero" style="min-height:auto;padding:80px 40px 24px;">
  <div class="hero-bg-circles"><span></span><span></span><span></span></div>
  <a class="hero-de-orb" href="{orb_link}" title="{orb_title}" aria-label="{orb_title}">
    <span class="orb-stage">
      <span class="orb-halo"></span><span class="orb-halo d2"></span>
      <span class="orb-ring"></span>
      <span class="orb-core"><img src="{orb_face}" alt="{orb_text}"></span>
      <span class="orb-hand"><b>👆</b></span>
    </span>
    <span class="orb-label">{orb_text}</span>
  </a>
  <div class="hero-inner">
    <h1>{g.get('Hero大标题','AI赋能营销')}<br><em>{g.get('Hero副标题','让每一线都更强')}</em></h1>
    <p class="hero-sub">{g.get('Hero描述','')}</p>
  </div>
</section>'''

    cards_data = [
        ('scene-1.html','📈','机会点增量','Opportunity Growth','市场空间 · 价值线索 · 精细化运营','4个AI应用',['市场分析','标讯运营','市场报告','标讯AI分析'],'linear-gradient(135deg,#0f2b5c,#1e4f8a)'),
        ('scene-2.html','🤝','客户拜访','Customer Visit','拜访前充分准备，现场沟通稳定发挥','2个AI应用',['客户画像','AI对练','支持移动端'],'linear-gradient(135deg,#00a884,#00b894)'),
        ('scene-3.html','🚀','项目推进','Project Delivery','7×24h智能支持，适配项目推进全流程','2个AI应用',['营销AI小秘','行销数字员工'],'linear-gradient(135deg,#0f2b5c,#5b3fd4)'),
        ('scene-4.html','📋','招投标','Bidding','招标文件解析→商务标生成→投标检查','3大AI能力',['招标解析','商务标生成','投标检查'],'linear-gradient(135deg,#e8710a,#dc2626)'),
        ('scene-5.html','🏭','渠道赋能','Channel Empowerment','渠道AI数字员工 · 渠道市场分析空间','2个AI应用',['安小渠','渠道市场分析'],'linear-gradient(135deg,#0d9488,#14b8a6)'),
        ('scene-6.html','🛠️','Skill共享','Skill Sharing','整合一线实战经验，共建共享工具箱','1个应用',['30+大比武','40+提质增效','共建共享'],'linear-gradient(135deg,#0ea5e9,#0284c7)'),
        ('scene-7.html','🧠','知识助手','Knowledge AI','20s获答，效率提升100%','1个AI应用',['5万+文档','20s获答','效率提升100%'],'linear-gradient(135deg,#6366f1,#8b5cf6)'),
    ]

    cards_html = ''
    for href, icon, title, en, desc, app_count, tags, grad in cards_data:
        tags_html = ''.join(f'<span class="card-tag">{t}</span>' for t in tags)
        count_badge = f'<span class="card-count">{app_count}</span>' if app_count else ''
        cards_html += (
            '    <a href="' + href + '" class="card-item">\n'
            '      <div class="card-icon-wrap">\n'
            '        <div class="card-icon" style="background:' + grad + ';">' + icon + '</div>\n'
            '        <div class="card-title-group">\n'
            '          <div class="card-title">' + title + count_badge + '</div>\n'
            '          <div class="card-en">' + en + '</div>\n'
            '        </div>\n'
            '      </div>\n'
            '      <div class="card-desc">' + desc + '</div>\n'
            '      <div class="card-tags">' + tags_html + '</div>\n'
            '      <div class="card-arrow">→</div>\n'
            '    </a>\n'
        )

    cards_section = (
        '<section class="landing-section" id="landing-scenes">\n'
        '  <div class="landing-inner">\n'
        '    <div class="landing-title">七大场景，<em>全面覆盖</em></div>\n'
        '    <div class="landing-sub">点击<span class="text-highlight">卡片</span>深入了解每个场景的<span class="text-highlight">应用与操作</span></div>\n'
        '    <div class="cards-grid">\n'
        + cards_html +
        '    </div>\n'
        '  </div>\n'
        '</section>'
    )

    footer = (
        '<footer style="background:linear-gradient(180deg,#0a1638,#070e2a);border-top:1px solid rgba(255,255,255,.06);color:rgba(255,255,255,.4);">\n'
        '  <div class="ft-logo" style="color:rgba(255,255,255,.8);"><img src="' + logo + '" alt="安恒信息" style="height:32px;vertical-align:middle;margin-right:6px;filter:brightness(1.2);">AI赋能营销</div>\n'
        '  <p>' + g.get("页脚部门","营销中心") + ' · ' + g.get("页脚日期","2026年") + '</p>\n'
        '  <section class="view-counter" style="margin-top:12px;"><span class="vc-icon">👁️</span><span>本页已浏览</span><span class="vc-num">99+</span><span>次</span></section>\n'
        '</footer>'
    )

    title = g.get('页面标题','AI赋能营销 · 营销中心综合管理部')
    arch_section = build_arch_section()
    incentive_section = build_incentive_section(data)
    future_home_section = build_future_section_home(data)
    return '<!DOCTYPE html>\n<html lang="zh-CN">\n<head>\n<meta charset="UTF-8">\n<meta name="viewport" content="width=device-width,initial-scale=1.0">\n<title>' + title + '</title>\n' + CSS + '\n</head>\n<body>\n<div id="prog"></div>\n\n' + nav + '\n\n' + hero + '\n\n' + cards_section + '\n\n' + arch_section + '\n\n' + incentive_section + '\n\n' + future_home_section + '\n\n' + footer + '\n\n<script>window.addEventListener(\'scroll\',()=>{const h=document.documentElement.scrollHeight-window.innerHeight;document.getElementById(\'prog\').style.width=(h>0?window.scrollY/h*100:0)+\'%\'});</script>\n</body>\n</html>'


def build_scene_page(data, scene, prev_scene=None, next_scene=None):
    """生成单个场景详情页"""
    g = data['global']
    logo = media_path(g.get('Logo图片', 'media/image2.png'))

    prev_link = f'<a href="scene-{prev_scene["num"]}.html" class="pager-btn">← 上一场景</a>' if prev_scene else '<span class="pager-btn disabled">← 上一场景</span>'
    next_link = f'<a href="scene-{next_scene["num"]}.html" class="pager-btn">下一场景 →</a>' if next_scene else '<span class="pager-btn disabled">下一场景 →</span>'

    detail_nav = f'''<div class="scene-detail-nav">
  <a href="index.html" class="back-btn">← 返回首页</a>
  <a href="index.html#landing-scenes" class="back-btn back-to-module">返回</a>
  <div class="nav-title">{scene.get("icon","")} {scene.get("title","")}</div>
  {_de_nav_btn(g)}
  <div class="nav-pager">{prev_link}{next_link}</div>
</div>
<script>
(function() {{
  var params = new URLSearchParams(window.location.search);
  var back = document.querySelector('.back-to-module');
  if (back && params.get('from') === 'ai-arch') {{
    back.href = 'index.html#ai-arch';
  }}
{_back_js(data)}
}})();
</script>'''

    scene_html = render_scene(data, scene)

    footer = f'''<footer style="border-top:1px solid rgba(0,0,0,.05);">
  <div class="ft-logo"><img src="{logo}" alt="安恒信息" style="height:32px;vertical-align:middle;margin-right:6px;">AI赋能营销</div>
  <p>{g.get("页脚部门","营销中心")} · {g.get("页脚日期","2026年")}</p>
</footer>'''

    title = f'{scene.get("title","")} — AI赋能营销'
    return f'''<!DOCTYPE html>\n<html lang="zh-CN">\n<head>\n<meta charset="UTF-8">\n<meta name="viewport" content="width=device-width,initial-scale=1.0">\n<title>{title}</title>\n{CSS}\n</head>\n<body>\n<div id="prog"></div>\n\n{detail_nav}\n\n<div class="detail-wrap">\n{scene_html}\n</div>\n\n{footer}\n\n{JS}\n</body>\n</html>'''


def build_future_page(data):
    """生成未来规划详情页"""
    g = data['global']
    logo = media_path(g.get('Logo图片', 'media/image2.png'))

    detail_nav = f'''<div class="scene-detail-nav">
  <a href="index.html" class="back-btn">← 返回首页</a>
  <a href="index.html#future-home" class="back-btn back-to-module">返回</a>
  <div class="nav-title">🚀 未来规划</div>
  {_de_nav_btn(g)}
  <div class="nav-pager"></div>
</div>
<script>
(function() {{
  var params = new URLSearchParams(window.location.search);
{_back_js(data)}
}})();
</script>'''

    fp = data.get('future_plan', {})
    import html as _html_mod
    def md2html(txt):
        if not txt: return ''
        r = _html_mod.escape(txt)
        r = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', r)
        lines = r.split('\n')
        out = []
        in_ul = False
        for line in lines:
            s = line.strip()
            if s.startswith('- '):
                if not in_ul: out.append('<ul>'); in_ul = True
                out.append(f'<li>{s[2:]}</li>')
            else:
                if in_ul: out.append('</ul>'); in_ul = False
                if s: out.append(f'<p>{s}</p>')
        if in_ul: out.append('</ul>')
        return '\n'.join(out)

    status_html = md2html(fp.get('status',''))
    dirs_html = md2html(fp.get('directions',''))
    plan_html = md2html(fp.get('plan',''))

    future_html = f'''<section class="future-section" style="margin-top:0;">
  <div class="future-card">
    <div class="future-header">
      <div class="future-header-inner">
        <h2>🚀 {fp.get("title","未来规划")}</h2>
        <p>{fp.get("subtitle","统一入口 · 整合资源 · 建设营销AI综合能力平台")}</p>
      </div>
    </div>
    <div class="future-body">
      <div class="fp-item">
        <div class="fp-label">🔍 当前现状</div>
        {status_html}
      </div>
      <div class="fp-item">
        <div class="fp-label">✅ 规划方向</div>
        {dirs_html}
      </div>
      <div class="fp-item">
        <div class="fp-label">🎯 推进计划</div>
        {plan_html}
      </div>
    </div>
  </div>
</section>'''

    footer = f'''<footer style="border-top:1px solid rgba(0,0,0,.05);">
  <div class="ft-logo"><img src="{logo}" alt="安恒信息" style="height:32px;vertical-align:middle;margin-right:6px;">AI赋能营销</div>
  <p>{g.get("页脚部门","营销中心")} · {g.get("页脚日期","2026年")}</p>
</footer>'''

    title = '未来规划 — AI赋能营销'
    return f'''<!DOCTYPE html>\n<html lang="zh-CN">\n<head>\n<meta charset="UTF-8">\n<meta name="viewport" content="width=device-width,initial-scale=1.0">\n<title>{title}</title>\n{CSS}\n</head>\n<body>\n<div id="prog"></div>\n\n{detail_nav}\n\n<div class="detail-wrap">\n{future_html}\n</div>\n\n{footer}\n\n{JS}\n</body>\n</html>'''


# 能力表 skill 名后的「圆形备注」统一拆成名字下方的小字标签（同字号/位置/颜色），涵盖：
#   新建客户（2026Q4上线） / 报价单（试用中） / 商机跟进记录（仅限销售使用） / 创建项目（仅限行销使用）
_PLAN_TAG = re.compile(
    r'[（(]\s*([^（()）]{0,20}?(?:上线|试用中|试用|仅限[^（()）]{0,10}?使用))\s*[)）]')


def build_eco_section(ec, cards_html):
    """生态板块：左栏 = 可 180° 拖动的立牌，右栏 = 从跨阶段卡里摘出来的那张能力卡。

    立牌沿用页头立牌同一套 3D 机制（rotateX 俯仰 + rotateY 翻转 + 正/背两面），
    但用独立的 `--eco-rot` 变量和 `#ecoBoard` 节点，与页头立牌互不影响。
    全部字段取自 content.md 的「### 生态板块」。
    """
    title = (ec.get('标题') or '').strip()
    lead = (ec.get('说明') or '').strip()
    hint = (ec.get('旋转提示') or '').strip()

    bimg = media_path(ec.get('立牌正面图', 'media/eco_board.png'))
    _bname = os.path.splitext(os.path.basename(bimg))[0]
    _bw = re.sub(r'[^\d.]', '', ec.get('立牌显示宽度', '') or '')
    try:
        BW = int(float(_bw)) or 520
    except Exception:
        BW = 520
    # 与页头立牌同一套 <picture>（AVIF 优先 + _m/_1x/2× 三档）；立牌在视口外，走懒加载
    bsrc, _bpre, _bw_real, _bh_real = board_picture(
        _bname, '渠道数字员工 能力立牌', f'(max-width:980px) 92vw, {BW}px', lazy=True)
    # 模糊占位图：主图到达前先铺一层 22px 轮廓
    _blq = (ec.get('立牌占位图', '') or '').strip()
    if _blq in ('无', '关闭', 'none', 'None', 'off', 'OFF'):
        blqip_html = ''
    else:
        blqip_src = (_blq if _blq.startswith('data:')
                     else (media_path(_blq) if _blq
                           else _read_text_asset(media_path(_bname + '_lqip.txt'))))
        blqip_html = (f'<img class="de-lqip" src="{blqip_src}" alt="" aria-hidden="true">'
                      if blqip_src else '')
    lb_label = (ec.get('放大按钮', '放大查看') or '').strip()
    # 立牌宽高比取图片真实尺寸（换任意比例的立牌图都不会变形）
    _sz = (_bw_real, _bh_real) if _bw_real else None
    _sz = _sz or _img_size(bimg)
    _ar = f'{_sz[0]}/{_sz[1]}' if _sz else '4200/5360'

    # 背板结构与页头立牌背面同款（复用 .de-bi 的样式），只换文案
    back_panel = f'''<div class="de-bi">
  <div class="de-bi-top"><i></i>{ec.get('背面眉标','')}<span class="de-bi-back-btn" data-eco-front>{ec.get('背面入口文字','查看正面能力全景 →')}</span></div>
  <div class="de-bi-mid">
    <div class="n">{ec.get('背面主标题','')}</div>
    <div class="s">{ec.get('背面副标题','')}</div>
    <div class="de-bi-sep"></div>
    <div class="t">{ec.get('背面标语','')}</div>
    <div class="d">{ec.get('背面说明','')}</div>
    <div class="de-bi-spec">
      <span><b>面板</b> 5mm 复合板</span><span><b>支架</b> 铝合金背撑</span>
      <span><b>工艺</b> 高清微喷</span><span><b>尺寸</b> 420 × 536 mm</span>
    </div>
  </div>
  <div class="de-bi-foot">
    <span class="code">DAS-SECURITY · CHANNEL AI · 2026</span>
    <span class="mat">{ec.get('支架文字','')}</span>
  </div>
</div>'''

    return f'''<section class="de-eco-sec" id="de-eco">
  <div class="de-wrap">
    <div class="de-sub-head"><span>{title}</span></div>
    {f'<p class="de-eco-lead">{lead}</p>' if lead else ''}
    <div class="de-eco-grid">
      <div class="de-eco-stage">
        <div class="de-floor"></div>
        <div class="de-eco-persp">
          <div class="de-eco-board" id="ecoBoard" style="aspect-ratio:{_ar}" role="img" aria-label="渠道数字员工能力立牌，可按住左右拖动翻转">
            <div class="de-edge l"></div>
            <div class="de-edge r"></div>
            <div class="de-face de-eco-back">{back_panel}</div>
            <div class="de-face de-eco-front">
              {blqip_html}
              {bsrc}
            </div>
            <div class="de-sheen"></div>
          </div>
        </div>
        {f'<div class="de-bhint"><span class="k">↔</span> {hint}</div>' if hint else ''}
        {board_zoom_btn('ecoLb', lb_label)}
      </div>
      <div class="de-eco-side">{cards_html}</div>
    </div>
  </div>
  {board_lightbox('ecoLb', _bname, '渠道数字员工 能力立牌 放大图', lb_label)}
</section>'''


def build_digital_employee_page(data):
    """生成超级数字员工独立页 digital-employee.html"""
    g = data['global']
    de = data.get('de_page') or {}
    meta = de.get('meta', {})
    back = de.get('back', {})
    fl = de.get('flow', {})
    ch = de.get('cap_head', {})
    ft = de.get('footer', {})
    logo = media_path(g.get('Logo图片', 'media/image2.png'))
    dept = g.get('页脚部门', '安恒信息 · 营销中心 · 综合管理部')

    # ---------- 导航 ----------
    nav = f'''<nav>
  <a class="nav-brand" href="index.html"><img src="{logo}" alt="安恒信息"><span>AI赋能营销</span></a>
  <div class="nav-actions">
    <a class="nav-back-btn" href="{meta.get('返回链接','index.html')}">{meta.get('返回按钮','← 返回 AI赋能营销')}</a>
    <div class="nav-right"><img src="{logo}" alt=""><span class="nav-right-dept">{dept}</span></div>
  </div>
</nav>'''

    # ---------- 1. 立牌 ----------
    board_img = media_path(meta.get('立牌正面图', 'media/de_board_front.webp'))
    prefix = meta.get('人物层前缀', 'media/de_char_')
    # 「立牌显示宽度」= 立牌在页面上的实际显示宽度（px）。
    # 图片档位（_m / _1x / 2×）与 avif/webp 由 tools/mkboard.py 生成，
    # srcset 直接从 {name}_variants.json 读真实像素宽度拼出来。
    _bw_raw = re.sub(r'[^\d.]', '', meta.get('立牌显示宽度', '') or '')
    try:
        BW = int(float(_bw_raw)) or 560
    except Exception:
        BW = 560
    BW_SM = int(round(BW * 4 / 7))         # 窄屏（≤768px）显示宽度，约等于大屏的 4/7
    _bname = os.path.splitext(os.path.basename(board_img))[0]
    board_src, board_preload, _bw_real, _bh_real = board_picture(
        _bname, '营销AI小秘 场景能力立牌',
        f'(max-width:768px) {BW_SM}px, {BW}px', priority=True)
    # 模糊占位图（LQIP）：主图到达前先显示轮廓，避免白板期。
    # content.md 写「无」可关闭；写 data:image/... 或图片路径可替换；留空用 mkboard.py 产物。
    _lq = (meta.get('立牌占位图', '') or '').strip()
    if _lq in ('无', '关闭', 'none', 'None', 'off', 'OFF'):
        lqip_html = ''
    else:
        _lqip_file = media_path(_bname + '_lqip.txt')
        lqip_src = (_lq if _lq.startswith('data:')
                    else (media_path(_lq) if _lq else (_read_text_asset(_lqip_file) or DE_BOARD_LQIP)))
        lqip_html = f'<img class="de-lqip" src="{lqip_src}" alt="" aria-hidden="true">'
    layers = ''
    for nm in ('body', 'tab', 'arm', 'head'):
        layers += f'<img class="de-l de-l-{nm}" src="{media_path(prefix + nm + ".png", ver=True)}" alt="" decoding="async">'
    # 挥手版手臂（打招呼时切换显示，去掉手中的笔）
    layers += f'<img class="de-l de-l-arm de-arm-wave" src="{media_path(prefix + "wave_arm.png", ver=True)}" alt="" decoding="async">'

    kpi_meta = de.get('kpi_meta', {})
    kpi = ''
    for i in (1, 2, 3, 4):
        v = meta.get(f'KPI{i}数值', '').strip()
        lb = meta.get(f'KPI{i}标签', '').strip()
        if not v:
            continue
        det = kpi_meta.get(f'KPI{i}', {})
        dt = det.get('title') or f'{v} {lb}'
        items = [x.strip() for x in det.get('detail', '').split(',') if x.strip()]
        chips = ''
        for it in items:
            # 「建设中」这颗的全部条目都走橙色（plan）样式；其它 KPI 里以「建设中·」开头的手写前缀也认
            is_plan = it.startswith('建设中·') or i == 4
            chips += f'<span class="kp-i{" plan" if is_plan else ""}">{it}</span>'
        if not chips:
            chips = f'<span class="kp-i">{dt}</span>'
        pop = (f'<div class="de-kpi-pop"><div class="kp-t">{dt}</div>'
               f'<div class="kp-l">{chips}</div></div>')
        kpi += f'<div class="de-kpi" tabindex="0" data-kpi="KPI{i}">{pop}<b>{v}</b><span>{lb}</span><i class="kp-dot"></i></div>'

    acts = de.get('actions', [])
    act_btns = ''
    act_icons = {'hello': '👋', 'turn': '🔄', 'back': '🔃', 'reset': '↺', 'idle': '💤'}
    for a in acts:
        aid = a['id']
        ic = act_icons.get(aid, '✨')
        lb = a.get('btn') or a.get('say', '')[:4]
        act_btns += (f'<button class="de-act" data-act="{aid}" data-say="{a.get("say","")}">'
                     f'<span class="ic">{ic}</span>{lb}</button>')

    bubble_say = acts[0]['say'] if acts else ''
    lb_label = meta.get('放大按钮', '放大查看')

    # 页头主标题：配了链接 → 可点击 + 「进入体验 ↗」提示胶囊
    h2_t = meta.get('页头主标题', '').strip()
    h2_url = meta.get('页头主标题链接', '').strip()
    h2_tip = meta.get('页头主标题提示', '进入体验').strip()
    if h2_url:
        h2_main = (f'<a class="de-h2-a" href="{h2_url}" target="_blank" rel="noopener noreferrer"'
                   f' title="点击进入「{h2_t}」体验">'
                   f'<span class="de-h2-t">{h2_t}</span>'
                   f'<span class="de-h2-go">{h2_tip}<i>↗</i></span></a>')
    else:
        h2_main = h2_t

    back_panel = f'''<div class="de-bi">
  <div class="de-bi-top"><i></i>{back.get('背面眉标','')}<span class="de-bi-back-btn" data-de-front>{back.get('背面入口文字','查看正面能力全景 →')}</span></div>
  <div class="de-bi-mid">
    <div class="n">{back.get('背面主标题','')}</div>
    <div class="s">{back.get('背面副标题','')}</div>
    <div class="de-bi-sep"></div>
    <div class="t">{back.get('背面标语','')}</div>
    <div class="d">{back.get('背面说明','')}</div>
    <div class="de-bi-spec">
      <span><b>面板</b> 5mm 复合板</span><span><b>支架</b> 铝合金背撑</span>
      <span><b>工艺</b> 高清微喷</span><span><b>尺寸</b> 420 × 536 mm</span>
    </div>
  </div>
  <div class="de-bi-foot">
    <span class="code">DAS-SECURITY · MARKETING AI · 2026</span>
    <span class="mat">背面视图 · BACK</span>
  </div>
</div>'''

    board_html = f'''<div class="de-board-sec" id="de-board">
  <div class="de-wrap">
    <div class="de-bs-grid">
      <div class="de-stage">
        <div class="de-floor"></div>
        <div class="de-persp">
          <div class="de-board" id="deBoard">
            <div class="de-edge l"></div>
            <div class="de-edge r"></div>
            <div class="de-face de-back">{back_panel}</div>
            <div class="de-strut">
              <div class="hinge"></div>
              <div class="rail l"></div>
              <div class="rail r"></div>
              <div class="cross"></div>
              <div class="foot l"></div>
              <div class="foot r"></div>
              <div class="tagline">{back.get('支架文字','')}</div>
            </div>
            <div class="de-face de-front">
              {lqip_html}
              {board_src}
              <div class="de-char" id="deChar" title="点我切换动作">{layers}</div>
              <div class="de-sheen"></div>
            </div>
          </div>
          {board_zoom_btn('deLb', lb_label)}
        </div>
        <div class="de-bhint"><span class="k">⇄</span> {meta.get('旋转提示','按住立牌左右拖动，可 180° 转动查看')}</div>
      </div>

      <div class="de-panel">
        <h2 class="de-h2">{h2_main}<br><em>{meta.get('页头副标题','')}</em></h2>
        <div class="de-tagline">
          <span class="de-slogan">{meta.get('页头标语','')}</span>
          <span class="de-tagsep"></span>
          <span class="de-lead">{meta.get('页头描述','')}</span>
        </div>
        <div class="de-kpis">{kpi}</div>
        <div class="de-bubble"><span class="bb-ic">💬</span><span class="bb-tx" id="deSay">{bubble_say}</span></div>
        <div class="de-acts">{act_btns}</div>
      </div>
    </div>
  </div>
  {board_lightbox('deLb', _bname, '营销AI小秘 场景能力立牌 放大图', lb_label, lqip_html)}
</div>'''

    # ---------- 2. 业务流 ----------
    # 点哪跳哪：阶段列 / 日常带 → 下方场景能力集合里对应的那张卡（按卡片「名称」匹配）
    _cap_names = {c.get('名称', '').strip() for c in de.get('caps', [])}

    def _jump_attr(name):
        n = (name or '').strip()
        return f' data-jump="{n}" role="link" tabindex="0"' if n and n in _cap_names else ''

    daily_items = [x.strip() for x in fl.get('日常动作', '').split(',') if x.strip()]
    daily_html = ''.join(f'<span class="it">{x}</span>' for x in daily_items)

    cols = ''
    plan_foot = (fl.get('规划列脚注', '') or '').strip()
    plan_foot_html = f'<span class="plan-foot">{plan_foot}</span>' if plan_foot else ''
    for st in de.get('stages', []):
        plan = 'plan' if st.get('status') != '已建设' else ''
        items = ''
        for i, a in enumerate(st['actions'], 1):
            items += f'<div class="flow-item"><i>{st["no"]}.{i}</i><span>{a}</span></div>'
        if plan:
            items += plan_foot_html
        _jb = _jump_attr(st.get('scene'))
        _cls = ' '.join([x for x in ['flow-col', plan, ('jumpable' if _jb else '')] if x])
        cols += f'''<div class="{_cls}"{_jb}>
  <div class="flow-head"><span class="n">{st['no']}</span><span class="t">{st['name']}</span></div>
  <div class="flow-body">{items}</div>
</div>'''

    # 说明行：拆成「数字 + 单位」片段，数字高亮
    segs = [x.strip() for x in fl.get('说明', '').split('·') if x.strip()]
    parts = []
    for seg in segs:
        mm = re.match(r'^(\d+)\s*(.*)$', seg)
        if mm:
            parts.append(f'<span class="seg"><b>{mm.group(1)}</b>{mm.group(2)}</span>')
        else:
            parts.append(f'<span class="seg">{seg}</span>')
    stat_html = '<span class="dot">·</span>'.join(parts)

    # 底部说明带
    ff_raw = fl.get('底部说明', 'L1 业务阶段 × L2 业务动作')
    if '｜' in ff_raw:
        ff_a, ff_b = [x.strip() for x in ff_raw.split('｜', 1)]
    else:
        ff_a, ff_b = ff_raw.strip(), ''
    ff_b_html = re.sub(r'(\d+)', r'<b>\1</b>', ff_b)

    flow_html = f'''<section class="de-flow-sec" id="de-flow">
  <div class="de-flow-inner">
    <div class="de-flow-head">
      <h2>{fl.get('标题','营销全场景业务流')}</h2>
      <div class="de-flow-stat">{stat_html}</div>
    </div>

    <div class="de-daily{' jumpable' if _jump_attr(fl.get('日常跳转')) else ''}"{_jump_attr(fl.get('日常跳转'))}>
      <span class="lb">{fl.get('日常标题','9. 日常')}</span>
      {daily_html}
      <span class="ln"></span>
      <span class="ds">{fl.get('日常说明','贯穿全流程的时间维度')}</span>
    </div>

    <div class="flow-grid" style="--flow-cols:{max(1, len(de.get('stages', [])))}">{cols}</div>

    <div class="flow-foot">
      <span class="ff-l">{ff_a}</span>
      <span class="ff-sep"></span>
      <span class="ff-r">{ff_b_html}</span>
    </div>
  </div>
</section>'''

    # ---------- 3. 场景能力集合 ----------
    def skill_html(name):
        """skill 名里的圆形备注（2026Q4上线 / 试用中 / 仅限销售使用…）统一拆成名字下方的小字标签。
        一行里可以带多个备注（如「商机跟进记录（2026Q4上线）（仅限销售使用）」），全部拆出来。"""
        tags = []

        def _take(m):
            tags.append(m.group(1))
            return ''

        main = _PLAN_TAG.sub(_take, name).strip()
        if not tags:
            return name
        return main + ''.join(f'<i class="plan-tag">{t}</i>' for t in tags)

    entry_links = de.get('entry_links', {})
    SRC = (meta.get('来源参数', '') or '').strip()               # 跳去详情页时带的 ?from=xx
    BACK_TXT = (meta.get('来源返回文字', '') or '').strip()      # 目标页「返回」按钮文案

    def ent_tag(name, no_link=False):
        """入口：配了链接的 → 文字本身就是链接（主题色渐变 + 虚线底 + ↗）；没配的 → 普通灰字。
        no_link=True：强制纯文字。
            - **跨阶段紧凑卡（渠道赋能/知识助手/Skill共享平台）固定传 True**：用户要求这三张
              概览卡只做文字展示、不要链接感（入口和操作路径都一样）。
            - 主卡（数字员工页 8 张场景卡 + 场景详情页表格）默认 False，走「入口链接映射」。"""
        if not name:
            return '—'
        url = None if no_link else entry_links.get(name)
        if not url:
            return f'<span class="ent ent-chip"><span class="ent-n">{name}</span></span>'
        href = url.replace('&', '&amp;')      # 链接里带 & 时按 HTML 规范转义
        return ('<a class="ent ent-chip ent-a" href="%s" target="_blank" rel="noopener noreferrer"'
                ' title="点击跳转前往体验">'
                '<span class="ent-n">%s</span><i class="ent-arw">↗</i></a>') % (href, name)

    def demo_html(s):
        """「介绍 / 输入示例」列：介绍在上、输入示例在下，换行展示。
        content.md 里用 `；` 分隔两段（原 PPT 就是两行），这里转成 <br>。"""
        if not s:
            return ''
        t = _esc(s)
        for sep in ('；', ';'):
            t = t.replace(sep, '<br>')
        return t

    def path_tag(name):
        """操作路径里的一段：配了链接 → 可点标签；没配 → 纯文字标签。"""
        url = entry_links.get(name)
        if not url:
            return f'<span class="pth">{name}</span>'
        href = url.replace('&', '&amp;')
        return ('<a class="pth pth-a" href="%s" target="_blank" rel="noopener noreferrer"'
                ' title="点击跳转">%s<i class="ent-arw">↗</i></a>') % (href, name)

    def path_chain(raw):
        """把「A → B → C」渲染成一串路径标签。"""
        nodes = [x.strip() for x in (raw or '').split('→') if x.strip()]
        if not nodes:
            return ''
        return '<i class="pth-sep">→</i>'.join(path_tag(n) for n in nodes)

    def cap_card(c, wide=False, compact=False):
        cc = c.get('主题色', '#1e6fd9')
        rows = c.get('rows', [])
        has_link = any((r.get('entry') or '').strip() in entry_links for r in rows)
        _hint = (ch.get('入口提示', '') or '').strip()
        hint_html = (f'<div class="cap-ent-hint"><span class="ic">💡</span>{_hint}</div>'
                     ) if (_hint and has_link) else ''
        if rows and not compact:
            # 入口列 / 数据来源列：空值向上继承上一行的值，连续同值合并为一格（rowspan）
            # （还原 PPT 原表的合并单元格：如「客户管理系统」跨 3 行）
            def _merge_col(key):
                vals, last = [], ''
                for r in rows:
                    v = (r.get(key) or '').strip()
                    if v:
                        last = v
                    vals.append(last)
                sp = [1] * len(rows)
                i = 0
                while i < len(rows):
                    if not vals[i]:
                        i += 1
                        continue
                    j = i
                    while j + 1 < len(rows) and vals[j + 1] == vals[i]:
                        j += 1
                    sp[i] = j - i + 1
                    for k in range(i + 1, j + 1):
                        sp[k] = 0          # 被上一格的 rowspan 覆盖
                    i = j + 1
                return vals, sp

            ent_vals, spans = _merge_col('entry')
            dat_vals, dspans = _merge_col('data')

            body = ('<div class="cap-tbl-wrap"><table class="cap-tbl">'
                    '<thead><tr><th>skill / 功能</th><th>介绍 / 输入示例</th>'
                    '<th>数据来源</th><th>入口 / 链接</th></tr></thead><tbody>')
            for idx, r in enumerate(rows):
                ent = ent_vals[idx]
                inner = ent_tag(ent)
                if spans[idx] > 1:
                    ent_html = (f'<td class="ent ent-span" rowspan="{spans[idx]}" data-l="入口">'
                                f'{inner}</td>')
                elif spans[idx] == 1:
                    ent_html = f'<td class="ent" data-l="入口">{inner}</td>'
                else:
                    # 桌面端由 rowspan 覆盖，移动端堆叠时补一份（保证每张卡都带入口）
                    ent_html = f'<td class="ent-m" data-l="入口">{inner}</td>'
                _dv = dat_vals[idx]
                _d = _esc(_dv) if _dv else '—'
                if dspans[idx] > 1:
                    dt_html = (f'<td class="dt dt-span" rowspan="{dspans[idx]}" data-l="数据来源">'
                               f'{_d}</td>')
                elif dspans[idx] == 1:
                    dt_html = f'<td class="dt" data-l="数据来源">{_d}</td>'
                else:
                    # 桌面端由 rowspan 覆盖，移动端堆叠时补一份
                    dt_html = f'<td class="dt-m" data-l="数据来源">{_d}</td>'
                body += (f'<tr><td class="sk">{skill_html(r["skill"])}</td>'
                         f'<td class="dm">{demo_html(r["demo"])}</td>'
                         f'{dt_html}{ent_html}</tr>')
            body += '</tbody></table></div>'
        elif compact:
            # 跨阶段紧凑卡：右列只放一行「用在哪」的纯文字说明，位置和渠道赋能卡的入口文案对齐 ——
            # 卡上写了「操作路径」就显示路径（贴在原入口 chip 的位置），没写的显示该行入口名；
            # 显示路径的那一行不再重复渲染入口 chip（用户要求：去掉入口 chip 与「操作路径」标签文字）
            _pth = (c.get('操作路径', '') or '').strip()
            _pth_row = -1
            if _pth:
                for _i, _r in enumerate(c['rows']):
                    if (_r.get('entry') or '').strip():
                        _pth_row = _i          # 多行都有入口时挂最后一行
            def _path_block():
                return ('<div class="cap-row-path"><span class="crp-c">%s</span></div>'
                        ) % path_chain(_pth)
            body = '<div class="cap-rows">'
            for _i, r in enumerate(c['rows']):
                _e = (r.get('entry') or '').strip()
                _has_pth = bool(_pth) and _i == _pth_row
                ent = ent_tag(_e, no_link=True) if (_e and not _has_pth) else ''
                dat = ('<div class="cap-row-m">数据来源 · %s</div>' % r['data']) if r['data'] else ''
                side = ''
                if ent or _has_pth:
                    side = ('<div class="cap-row-side">%s%s</div>'
                            % (ent, _path_block() if _has_pth else ''))
                body += ('<div class="cap-row"><div class="cap-row-bd">'
                         '<div class="cap-row-h"><b>%s</b></div>'
                         '<div class="cap-row-d">%s</div>%s</div>%s</div>'
                         ) % (skill_html(r['skill']), r['demo'], dat, side)
            if _pth and _pth_row < 0:           # 兜底：整卡没有入口时，路径仍放底部
                body += _path_block()
            body += '</div>'
        else:
            body = ('<div class="cap-empty"><b>本期暂未建设</b>'
                    '<span>该阶段能力正在规划中，上线后将持续补充到本清单</span></div>')
        jump = ''
        if c.get('跳转链接'):            # 从本页跳去详情页时带上 ?from=xx&to=<卡名>：
            # 目标页的「返回」据此指回超级数字员工页，并定位到本卡位置
            jump_url = c['跳转链接']
            if SRC and not jump_url.startswith('#'):
                _nm = (c.get('名称', '') or '').strip()
                if 'from=' not in jump_url:
                    jump_url += ('&' if '?' in jump_url else '?') + 'from=' + SRC
                if _nm and 'to=' not in jump_url:
                    jump_url += ('&' if '?' in jump_url else '?') + 'to=' + quote(_nm)
            _hu = jump_url.replace('&', '&amp;')   # 链接里带 & 时按 HTML 规范转义
            jump = f'<a class="cap-jump" href="{_hu}">{c.get("跳转文字","查看完整介绍 →")}</a>'

        # 应用数量
        cnt = str(c.get('应用数量', '')).strip()
        is_plan = (c.get('状态', '') == '本期未建设') or cnt in ('0', '')
        if cnt:
            count_html = (f'<div class="cap-count{" plan" if is_plan else ""}">'
                          f'<b>{cnt}</b><span>{"本期未建设" if is_plan else "项应用"}</span></div>')
        else:
            count_html = ''
        # 场景闭环链
        loop = str(c.get('场景闭环', '')).strip()
        loop_html = ''
        if loop:
            nodes = [x.strip() for x in loop.split('→') if x.strip()]
            chain = '<i>→</i>'.join(f'<span class="cp">{n}</span>' for n in nodes)
            loop_html = (f'<div class="cap-loop"><span class="cap-loop-t">{c.get("名称","")}闭环</span>'
                         f'<div class="cap-loop-chain">{chain}</div></div>')

        if compact:
            # 跨阶段紧凑卡：闭环链放在头部下方
            return f'''<div class="cap-card compact" style="--cc:{cc}" data-scene="{c.get('名称','')}">
  <div class="cap-top">
    <div class="cap-ico">{c.get('图标','')}</div>
    <div class="cap-hd">
      <div class="cap-num">{c.get('序号','')}</div>
      <div class="cap-name">{c.get('名称','')}</div>
    </div>
    {count_html}
  </div>
  <div class="cap-desc">{c.get('说明','')}</div>
  {loop_html}
  {hint_html}
  {body}
  {jump}
</div>'''
        return f'''<div class="cap-card{' wide' if wide else ''}" style="--cc:{cc}" data-scene="{c.get('名称','')}">
  <div class="cap-top">
    <div class="cap-ico">{c.get('图标','')}</div>
    <div class="cap-hd">
      <div class="cap-num">{c.get('序号','')}</div>
      <div class="cap-name">{c.get('名称','')}</div>
    </div>
    {count_html}
  </div>
  <div class="cap-desc">{c.get('说明','')}</div>
  {loop_html}
  {hint_html}
  {body}
  {jump}
</div>'''

    caps = de.get('caps', [])
    main_caps = caps[:8]
    sub_caps = caps[8:]
    # 生态板块：把 content.md「### 生态板块 → 卡片名称」指定的那张跨阶段卡从
    # 「跨阶段 · 通用能力」里摘出来，单独放到下面的生态板块（左立牌 + 右这张卡）
    ec = de.get('eco') or {}
    _eco_name = (ec.get('卡片名称') or '').strip()
    eco_cards = []
    if _eco_name:
        eco_cards = [c for c in sub_caps if (c.get('名称') or '').strip() == _eco_name]
        sub_caps = [c for c in sub_caps if (c.get('名称') or '').strip() != _eco_name]
    main_html = ''.join(cap_card(c) for c in main_caps)
    sub_html = ''.join(cap_card(c, compact=True) for c in sub_caps)
    eco_html = (build_eco_section(ec, ''.join(cap_card(c, compact=True) for c in eco_cards))
                if eco_cards else '')

    _ch_pill = (ch.get('眉标', '') or '').strip()
    _ch_sub = (ch.get('副标题', '') or '').strip()
    _ch_stat = (ch.get('统计', '') or '').strip()
    # 「跨阶段 · 通用能力」列数随剩余卡数自适应（最多 3 列），避免少一张卡时右边空一格
    _sub_block = ''
    if sub_html:
        _n_sub = min(len(sub_caps), 3)
        _sub_block = (f'<div class="de-sub-head"><span>跨阶段 · 通用能力</span></div>'
                      f'<div class="cap-sub-grid" style="--sub-cols:{_n_sub}">{sub_html}</div>')
    cap_html = f'''<section class="de-cap-sec" id="de-cap">
  <div class="de-wrap">
    <div class="de-sec-head">
      {f'<span class="de-pill">🧩 {_ch_pill}</span>' if _ch_pill else ''}
      <h2 class="de-h2">{ch.get('标题','超级数字员工 · 场景能力集合')}</h2>
      {f'<p class="de-lead">{_ch_sub}</p>' if _ch_sub else ''}
      {f'<p class="de-lead de-lead-sub">{_ch_stat}</p>' if _ch_stat else ''}
    </div>
    <div class="cap-grid">{main_html}</div>
    {_sub_block}
  </div>
</section>'''

    # ---------- 4. 页尾 CTA ----------
    cta = f'''<section class="de-cta">
  <div class="de-cta-in de-wrap">
    <h3>{ft.get('主标题','')}</h3>
    <p>{ft.get('副标题','')}</p>
    <div class="de-cta-btns">
      <a class="de-cta-a pri" href="{ft.get('主按钮链接','index.html')}">{ft.get('主按钮文字','← 返回 AI赋能营销完整版')}</a>
      <a class="de-cta-a sec" href="#de-board">{ft.get('次按钮文字','回到顶部 ↑')}</a>
    </div>
  </div>
</section>'''

    footer = f'''<footer style="background:linear-gradient(180deg,#0a1638,#070e2a);border-top:1px solid rgba(255,255,255,.06);color:rgba(255,255,255,.4);">
  <div class="ft-logo" style="color:rgba(255,255,255,.8);"><img src="{logo}" alt="安恒信息" style="height:32px;vertical-align:middle;margin-right:6px;filter:brightness(1.2);">AI赋能营销</div>
  <p>{ft.get('署名', dept)}</p>
</footer>'''

    incentive_section = build_incentive_section(data)
    future_section = build_future_section_home(data, tag_origin=True)

    title = meta.get('浏览器标题', '超级数字员工 — 安恒信息 AI赋能营销')
    # 立牌用 <picture>（AVIF 优先），预加载也要带 type，否则不支持 AVIF 的浏览器会白下一份
    preload = (board_preload
               + f'<link rel="preload" as="image" href="{media_path(prefix + "body.png")}">\n')
    # 副标题字号比（content.md「页头副标题字号比」，如 .72）：注入 DE_CSS 占位符
    _sub_raw = re.sub(r'[^\d.]', '', meta.get('页头副标题字号比', '') or '')
    try:
        _sv = float(_sub_raw) if _sub_raw else 0.72
    except Exception:
        _sv = 0.72
    _ss = f'{_sv:g}'
    h2_sub = (_ss[1:] if _ss.startswith('0.') else _ss) + 'em'
    de_css = DE_CSS.replace('__H2_SUB__', h2_sub)
    # 能力集主卡列数 / 容器宽度 / 顶部间距（content.md 同名三个字段）
    _cols = re.sub(r'\D', '', meta.get('能力集列数', '') or '') or '2'
    _cw = re.sub(r'[^\d.]', '', meta.get('能力集容器宽度', '') or '')
    _pt = re.sub(r'\D', '', meta.get('能力集上间距', '') or '') or '56'
    # 每张主卡至少 ~660px 才放得下 4 列表格。断点默认 1024（PC 就一直两列，
    # 不受系统缩放 / 高分屏影响），可在 content.md 用「能力集列数断点」改。
    _bp_raw = re.sub(r'\D', '', meta.get('能力集列数断点', '') or '')
    _bp = _bp_raw or str(max(1, int(_cols)) * 660 + 64)
    de_css = (de_css.replace('__CAP_COLS__', _cols)
                    .replace('__CAP_W__', (_cw + 'px') if _cw else '1760px')
                    .replace('__CAP_PT__', _pt)
                    .replace('__CAP_BP__', _bp)
                    .replace('__CAP_BP_NEXT__', str(int(_bp) + 1)))
    return ('<!DOCTYPE html>\n<html lang="zh-CN">\n<head>\n<meta charset="UTF-8">\n'
            '<meta name="viewport" content="width=device-width,initial-scale=1.0">\n'
            f'<title>{title}</title>\n{CSS}\n{de_css}\n{preload}</head>\n<body class="de-body">\n'
            '<div id="prog"></div>\n\n' + nav + '\n\n' + board_html + '\n\n' + flow_html + '\n\n'
            + cap_html + '\n\n' + eco_html + '\n\n' + incentive_section + '\n\n' + future_section + '\n\n'
            + cta + '\n\n' + footer + '\n\n' + DE_JS + '\n' + JUMP_JS + '\n</body>\n</html>')


def build(data):
    """保留旧版单页生成（兼容用）"""
    return build_home(data)


def main():
    from datetime import datetime
    print('='*50)
    print(f'  生成时间：{datetime.now().strftime("%Y-%m-%d %H:%M:%S")}')
    print(f'  读取文件：content.md')
    print('='*50)
    data = parse_content('content.md')

    # 1. 首页
    home_html = build_home(data)
    with open('index.html', 'w', encoding='utf-8') as f:
        f.write(home_html)
    print(f'\n✅ 首页生成成功！index.html ({len(home_html):,} 字节)')

    # 2. 场景详情页
    scenes = data['scenes']
    for i, s in enumerate(scenes):
        prev = scenes[i-1] if i > 0 else None
        next_s = scenes[i+1] if i < len(scenes)-1 else None
        scene_html = build_scene_page(data, s, prev, next_s)
        fname = f'scene-{s["num"]}.html'
        with open(fname, 'w', encoding='utf-8') as f:
            f.write(scene_html)
        print(f'  ✅ {fname} ({len(scene_html):,} 字节) — {s.get("title","?")}')

    # 3. 未来规划页
    future_html = build_future_page(data)
    with open('future.html', 'w', encoding='utf-8') as f:
        f.write(future_html)
    print(f'  ✅ future.html ({len(future_html):,} 字节) — 未来规划')

    # 4. 超级数字员工专页
    if data.get('de_page'):
        de_html = build_digital_employee_page(data)
        with open('digital-employee.html', 'w', encoding='utf-8') as f:
            f.write(de_html)
        de = data['de_page']
        print(f'  ✅ digital-employee.html ({len(de_html):,} 字节) — 超级数字员工'
              f'（{len(de.get("stages", []))} 阶段 / {len(de.get("caps", []))} 场景能力集）')
    else:
        print('  ⚠️  未在 content.md 中找到「## 数字员工页」，跳过 digital-employee.html')

    print(f'\n总计：{1 + len(scenes) + 1 + (1 if data.get("de_page") else 0)} 个文件')
    for s in data['scenes']:
        print(f'  Scene {s["num"]}: {s.get("title","?")} ({len(s["apps"])} apps)')


if __name__ == '__main__':
    try:
        main()
    except Exception as e:
        print(f'\n❌ 出错：{e}')
        import traceback
        traceback.print_exc()
    finally:
        import os
        if os.name == 'nt' and sys.stdin and sys.stdin.isatty():
            print('\n按回车键关闭窗口...')
            try: input()
            except EOFError: pass
