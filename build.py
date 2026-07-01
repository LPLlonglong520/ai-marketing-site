#!/usr/bin/env python3
"""
build.py v2 — 从 content.md 生成 index.html
用法: python build.py
修改 content.md 后运行此脚本即可更新网站内容。
"""
import re, os, sys

# 切换工作目录 + 强制UTF-8
os.chdir(os.path.dirname(os.path.abspath(__file__)))
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')


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
    fp_start = text.find('## 未来规划')
    fp_end = text.find('## 点赞评论模块')
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
    
    # ---- 场景拆分 ----
    scene_blocks = re.split(r'\n## 场景\d+ · .+\n', text)
    scene_headers = re.findall(r'## 场景(\d+) · (.+)\n', text)
    
    for idx, (snum_str, sname) in enumerate(scene_headers):
        snum = int(snum_str)
        block = scene_blocks[idx + 1] if idx + 1 < len(scene_blocks) else ''
        # 截掉未来规划、点赞评论模块和漫画角色，避免串到场景解析中
        tail = re.search(r'\n## (?:未来规划|点赞评论模块|漫画角色)', block)
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
                m = re.match(r'\|\s*(标题|副标题|演示视频|截图(\d+)|截图(\d+)说明|演示类型|占位图标|占位文字)\s*\|\s*(.+?)\s*\|', line)
                if m:
                    k = m.group(1)
                    v = m.group(4) if m.group(4) else ''
                    if k == '标题':
                        app['title'] = v
                    elif k == '副标题':
                        app['subtitle'] = v
                    elif k == '演示视频':
                        app['video'] = v
                    elif k == '演示类型':
                        app['placeholder'] = (v == 'placeholder')
                    elif k == '占位图标':
                        app['placeholder_icon'] = v
                    elif k == '占位文字':
                        app['placeholder_text'] = v
                    elif k.startswith('截图') and k.endswith('说明'):
                        img_caps.append(v)
                    elif k.startswith('截图'):
                        img_srcs.append(v)
            
            # 解析AI标讯对比数据
            bid_compare_match = re.search(r'### AI标讯对比数据\n\n((?:\|.+\|\n)+)', ab)
            if bid_compare_match:
                rows = bid_compare_match.group(1).strip().split('\n')
                data_rows = []
                compare_footer = ''
                for row in rows:
                    cells = re.findall(r'\|\s*(.+?)\s*(?=\|)', row)
                    if cells and cells[0].strip() not in ('维度', '') and not cells[0].startswith('--'):
                        dim = cells[0].strip()
                        v1 = cells[1].strip() if len(cells) > 1 else ''
                        v2 = cells[2].strip() if len(cells) > 2 else ''
                        if dim == '总结':
                            compare_footer = v1
                        else:
                            data_rows.append({'dim': dim, 'v1': v1, 'v2': v2})
                if data_rows:
                    bid_compare_data = {'rows': data_rows, 'footer': compare_footer}
            app['bid_compare'] = bid_compare_data
            
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
            
            if img_srcs:
                app['images'] = [{'src': s, 'caption': img_caps[i] if i < len(img_caps) else ''} 
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
                    m_inline = re.search(r'\s*\|\s*操作路径\s*\|', line)
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
                extra = []
                for line in cleaned_lines:
                    m_path = re.match(r'\|\s*操作路径(\d*)\s*\|\s*(.+?)\s*\|', line)
                    m_extra = re.match(r'\|\s*补充说明\s*\|\s*(.+?)\s*\|', line)
                    m_ptitle = re.match(r'\|\s*路径标题(\d*)\s*\|\s*(.+?)\s*\|', line)
                    if m_path:
                        paths.append(m_path.group(2).strip())
                    elif m_extra:
                        extra.append(m_extra.group(1).strip())
                    elif m_ptitle:
                        extra.append(('path_title', m_ptitle.group(2), ''))
                    elif line.strip() and not line.startswith('|'):
                        how_text.append(line)
                app['how'] = '\n'.join(how_text).strip()
                app['paths'] = paths
                app['extra_info'] = extra
            
            scene['apps'].append(app)
        
        data['scenes'].append(scene)
    
    return data


# ============================================================
# HTML模板
# ============================================================

CSS = '''<style>
*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
:root {
  --brand-deep: #0b1a3b; --brand-blue: #0f2b5c; --brand-teal: #00a884;
  --blue:   #0f2b5c; --blue-d: #0a1f42; --blue-l: #e6f0fa;
  --green:  #00a884; --green-l:#e6f7f2;
  --purple: #5b3fd4; --purple-l:#eee8ff;
  --orange: #e8710a; --orange-l:#fef3e2;
  --text:   #1b1f2e; --muted:  #6b7280; --border: #e3e5e8;
  --border-warm: #e8dcc8; --border-card: #ebe7de;
  --bg:     #f8f9fb; --white:  #ffffff;
  --r: 14px; --r-lg: 20px;
  --shadow: 0 1px 8px rgba(0,0,0,.04);
  --shadow-lg: 0 6px 28px rgba(0,0,0,.08);
}
html { scroll-behavior: smooth; }
body { font-family: 'PingFang SC','Microsoft YaHei','Inter',-apple-system,sans-serif; background: var(--bg); color: var(--text); line-height: 1.65; overflow-x: hidden; -webkit-font-smoothing:antialiased; }
::-webkit-scrollbar { width: 6px; }
::-webkit-scrollbar-thumb { background: #c8cdd5; border-radius: 3px; }
#prog { position:fixed; top:0; left:0; height:3px; z-index:999; background:linear-gradient(90deg,#3b7fc4,#8b5cf6); transition:width .15s linear; }
nav { position:fixed; top:0; left:0; right:0; z-index:200; height:58px; background:rgba(255,255,255,.92); backdrop-filter:blur(16px); border-bottom:1px solid var(--border-warm); display:flex; align-items:center; justify-content:space-between; padding:0 32px; box-shadow:0 1px 6px rgba(0,0,0,.03); }
.nav-brand { display:flex; align-items:center; gap:10px; font-weight:700; font-size:15px; color:var(--brand-deep); text-decoration:none; letter-spacing:-.2px; }
.nav-brand img { height:30px; width:auto; }
.nav-brand span { color:var(--brand-deep); }
.nav-tabs { display:flex; gap:2px; }
.nav-tabs a { padding:7px 16px; border-radius:12px; font-size:17px; font-weight:500; color:var(--muted); text-decoration:none; transition:all .2s; display:flex; align-items:center; gap:5px; letter-spacing:-.1px; }
.nav-tabs a:hover, .nav-tabs a.active { background:var(--blue-l); color:var(--blue); }
.nav-right { font-size:12px; font-weight:600; color:var(--muted); background:var(--white); border:1px solid var(--border-warm); padding:5px 14px; border-radius:20px; }
.hero { min-height:100vh; padding:120px 40px 100px; background:linear-gradient(174deg,#1e3a6e 0%,#144480 22%,#0d3468 48%,#0b264d 72%,#091d3a 100%); display:flex; align-items:center; justify-content:center; position:relative; overflow:hidden; }
.hero-bg-circles { position:absolute; inset:0; pointer-events:none; overflow:hidden; }
.hero-bg-circles::before { content:''; position:absolute; inset:0; background:radial-gradient(ellipse 60% 42% at 50% 28%, rgba(99,140,230,.15) 0%, transparent 70%); }
.hero-bg-circles span { position:absolute; border-radius:50%; background:rgba(255,255,255,.04); animation:drift 14s ease-in-out infinite; }
.hero-bg-circles span:nth-child(1){ width:520px;height:520px;top:-160px;right:-120px;animation-delay:0s; }
.hero-bg-circles span:nth-child(2){ width:320px;height:320px;bottom:-90px;left:-90px;animation-delay:-5s; }
.hero-bg-circles span:nth-child(3){ width:220px;height:220px;top:42%;left:8%;background:rgba(139,92,246,.06);animation-delay:-9s; }
@keyframes drift { 0%,100%{transform:translate(0,0)} 50%{transform:translate(18px,-18px)} }
.hero-inner { position:relative; z-index:2; max-width:1200px; width:100%; text-align:center; padding:0 60px; }
.hero-eyebrow { display:inline-flex; align-items:center; gap:8px; background:rgba(255,255,255,.08); border:1px solid rgba(255,255,255,.15); color:rgba(255,255,255,.78); font-size:12px; font-weight:600; padding:5px 16px; border-radius:20px; margin-bottom:24px; }
.live-dot { width:7px;height:7px;border-radius:50%;background:#4ade80;animation:pulse 1.5s ease-in-out infinite; }
@keyframes pulse { 0%,100%{opacity:1} 50%{opacity:.3} }
.hero h1 { font-size:clamp(32px,5.5vw,56px); font-weight:900; line-height:1.15; color:#fff; margin-bottom:16px; letter-spacing:-.5px; }
.hero-logo-row { display:flex; flex-direction:column; align-items:center; justify-content:center; gap:4px; margin-bottom:32px; }
.hero-logo-img { height:52px; width:auto; filter:drop-shadow(0 0 18px rgba(0,168,132,.25)); margin-bottom:6px; }
.hero-logo-dept { font-size:18px; color:rgba(255,255,255,.5); font-weight:500; letter-spacing:1px; }
.hero h1 em { color:#5eead4; font-style:normal; }
.hero-sub { font-size:16px; color:rgba(255,255,255,.55); margin:0 auto 32px; max-width:620px; line-height:1.7; }
.hero-incentive-divider { width:60px; height:2px; background:rgba(255,255,255,.15); border-radius:1px; margin:40px auto 24px; }
.hero-incentive-label { text-align:center; font-size:24px; font-weight:900; background:linear-gradient(135deg,#fbbf24,#f59e0b,#fb923c); -webkit-background-clip:text; -webkit-text-fill-color:transparent; letter-spacing:4px; margin-bottom:20px; }
.hero-incentives-row { display:flex; justify-content:center; gap:20px; flex-wrap:wrap; margin-top:0; }
.hero-incentive-desc { margin-top:26px; text-align:center; color:rgba(255,255,255,.5); font-size:13px; line-height:1.8; max-width:700px; margin-left:auto; margin-right:auto; }
.hero-incentive-badge { background:rgba(255,255,255,.1); backdrop-filter:blur(12px); border:1px solid rgba(255,255,255,.18); border-radius:16px; padding:16px 22px; color:#fff; text-align:center; transition:all .3s; min-width:160px; }
.hero-incentive-badge:hover { background:rgba(255,255,255,.18); transform:translateY(-3px); border-color:rgba(99,162,255,.4); }
a.hero-incentive-badge { text-decoration:none; color:#fff; display:block; position:relative; }
a.hero-incentive-badge .hb-title { color:#60a5fa; font-weight:800; }
a.hero-incentive-badge::after { content:'↗'; position:absolute; top:8px; right:14px; font-size:13px; color:rgba(96,165,250,.6); opacity:0; transition:opacity .25s; }
a.hero-incentive-badge:hover::after { opacity:1; }
a.hero-incentive-badge:hover { border-color:rgba(96,165,250,.45); }
.hero-incentive-badge .hb-icon { font-size:22px; margin-bottom:4px; }
.hero-incentive-badge .hb-title { font-size:14px; font-weight:800; letter-spacing:.5px; }
.hero-incentive-badge .hb-sub { font-size:11px; color:rgba(255,255,255,.6); margin-top:2px; }
.hero-incentive-badge .hb-link { font-size:10px; color:rgba(96,165,250,.7); margin-top:5px; letter-spacing:.3px; }
@media (max-width:768px) { .hero-incentives-row { gap:12px; } .hero-incentive-badge { min-width:0; padding:12px 16px; } }
.hero-char-cards { display:flex; justify-content:center; gap:18px; flex-wrap:wrap; margin-top:36px; }
.hero-card { background:linear-gradient(145deg,rgba(15,43,92,.75),rgba(30,79,138,.55)); border:1px solid rgba(255,255,255,.12); border-radius:18px; padding:26px 20px 22px; text-align:center; width:155px; backdrop-filter:blur(6px); transition:all .3s; }
.hero-card:hover { background:linear-gradient(145deg,rgba(15,43,92,.9),rgba(30,79,138,.7)); transform:translateY(-4px); box-shadow:0 12px 36px rgba(0,0,0,.3); }
.hero-card .hc-icon { font-size:38px; margin-bottom:10px; }
.hero-card .hc-name { font-size:15px; font-weight:800; color:#fff; letter-spacing:.5px; margin-bottom:8px; }
.hero-card .hc-desc { font-size:12px; color:rgba(255,255,255,.55); line-height:1.7; }
@media (max-width:768px) { .hero-char-cards { gap:12px; } .hero-card { width:135px; padding:20px 14px; } }
.scene-nav { position:sticky; top:58px; z-index:100; background:rgba(255,255,255,.85); backdrop-filter:blur(12px); border-bottom:1px solid var(--border-warm); padding:10px 0; }
.scene-nav-inner { max-width:1100px; margin:0 auto; padding:0 28px; display:flex; gap:10px; flex-wrap:wrap; }
.scene-nav-btn { padding:10px 24px; border-radius:24px; font-size:19px; font-weight:600; border:1px solid var(--border-card); background:var(--white); color:var(--muted); cursor:pointer; transition:all .18s; }
.scene-nav-btn:hover, .scene-nav-btn.active { background:var(--blue-l); color:var(--blue); border-color:#93b5e0; }
.scene-nav-hint { font-size:12px; color:#10b981; align-self:center; white-space:nowrap; flex-shrink:0; opacity:.85; letter-spacing:.3px; }
.scene-section { max-width:1100px; margin:0 auto; padding:60px 28px 80px; }
.scene-header { display:flex; align-items:center; gap:16px; margin-bottom:48px; }
.scene-header-ico { width:52px;height:52px;border-radius:14px;display:flex;align-items:center;justify-content:center;font-size:23px;flex-shrink:0; }
.scene-title { font-size:30px; font-weight:900; color:var(--text); letter-spacing:-.3px; }
.scene-sub { font-size:14px; color:var(--muted); margin-top:2px; }
.scene-count { margin-left:auto; padding:4px 16px; border-radius:20px; font-size:12px; font-weight:700; background:var(--white); border:1px solid var(--border-card); color:var(--muted); }
/* ── 时间线串联（无圆点） ── */
.scene-timeline { position:relative; max-width:1200px; margin:0 auto; padding:0 28px; }
.scene-timeline::before { content:''; position:absolute; left:54px; top:0; bottom:0; width:2px; background:linear-gradient(180deg,#3b82f6 0%,#8b5cf6 25%,#10b981 50%,#f59e0b 75%,#ef4444 100%); border-radius:1px; z-index:0; opacity:.4; }
.scene-timeline-item { position:relative; }
/* ── 折叠/展开按钮 ── */
.scene-toggle { width:32px; height:32px; border-radius:8px; background:var(--border-light); border:1px solid var(--border-card); cursor:pointer; font-size:11px; color:var(--muted); display:flex; align-items:center; justify-content:center; transition:all .25s; flex-shrink:0; }
.scene-toggle:hover { background:#dbeafe; color:#3b82f6; border-color:#93c5fd; }
.scene-toggle.collapsed { transform:rotate(-90deg); }
.scene-body { overflow:hidden; transition:max-height .45s ease, opacity .35s ease; max-height:6000px; opacity:1; }
.scene-body.collapsed { max-height:0; opacity:0; }
.app-block { background:var(--white); border:1px solid var(--border-card); border-radius:var(--r-lg); overflow:hidden; margin-bottom:32px; box-shadow:var(--shadow); transition:box-shadow .3s; }
.app-block:hover { box-shadow:var(--shadow-lg); border-color:var(--border-warm); }
.app-block-header { display:flex; align-items:center; gap:14px; padding:22px 28px; border-bottom:1px solid var(--border-card); background:linear-gradient(180deg,#fbfcfd,#fff); }
.app-block-header > div:not(.app-num-badge) { min-width:0; flex:1; }
.app-num-badge { width:36px;height:36px;border-radius:10px;display:flex;align-items:center;justify-content:center;color:#fff;font-weight:800;font-size:14px;flex-shrink:0; }
.app-title { font-size:18px; font-weight:800; color:var(--text); letter-spacing:-.2px; }
.app-subtitle { margin-top:3px; font-size:12px; color:var(--muted); word-break:break-word; }
.app-content { display:grid; grid-template-columns:1fr 1fr 1fr; gap:0; border-bottom:1px solid var(--border-card); }
.app-col { padding:28px 24px; position:relative; overflow:hidden; border-right:1px solid var(--border-card); }
.app-col:last-child { border-right:none; }
.col-label { font-size:12px; font-weight:800; margin-bottom:14px; display:flex; align-items:center; gap:6px; letter-spacing:.2px; }
.col-label-pain { color:#dc2626; }
.col-label-solve { color:#00a884; }
.col-label-how { color:#0f2b5c; }
.app-col p { font-size:13px; color:var(--text); line-height:1.65; }
.app-col ul { margin-top:10px; padding-left:16px; font-size:13px; color:var(--text); }
.app-col li { margin-bottom:4px; }
.col-emoji-bg { position:absolute; bottom:-8px; right:-4px; font-size:64px; opacity:.05; pointer-events:none; user-select:none; }
.path-tag { display:inline-block; padding:6px 14px; border-radius:10px; font-size:12px; font-weight:700; background:var(--blue-l); color:var(--blue); margin-top:10px; letter-spacing:.3px; }
.path-tag .arr { color:var(--muted); margin:0 2px; }
/* ---- 视频面板（浅色科技风） ---- */
.app-video-panel { background:#f4f5f8; padding:20px 32px 24px; border-top:1px solid #e3e5e8; }
.app-video-label { display:flex; align-items:center; gap:8px; font-size:12px; font-weight:700; color:#5f6b7a; letter-spacing:.5px; text-transform:uppercase; margin-bottom:12px; }
.app-video-label .vdot { width:8px;height:8px;border-radius:50%;background:#3b82f6; }
.video-wrapper { position:relative; width:100%; border-radius:10px; overflow:hidden; background:linear-gradient(135deg,#e8eaef,#dce1e8); box-shadow:0 2px 12px rgba(0,0,0,.06); min-height:280px; display:flex; align-items:center; justify-content:center; }
.video-wrapper video { width:100%; display:block; max-height:480px; object-fit:contain; background:#0f172a; border-radius:10px; }
.video-wrapper.loaded { background:#0f172a; min-height:0; }
.video-wrapper.loaded video { background:transparent; }
.video-placeholder { position:absolute; inset:0; display:flex; flex-direction:column; align-items:center; justify-content:center; gap:12px; cursor:pointer; z-index:2; transition:opacity .3s; }
.video-wrapper.loaded .video-placeholder { opacity:0; pointer-events:none; }
.vp-icon { width:60px; height:60px; border-radius:50%; background:rgba(30,58,110,.85); color:#fff; font-size:24px; display:flex; align-items:center; justify-content:center; box-shadow:0 4px 20px rgba(0,0,0,.25); transition:transform .2s,background .2s; }
.video-placeholder:hover .vp-icon { transform:scale(1.1); background:rgba(30,58,110,.95); }
.vp-text { font-size:14px; color:#5f6b7a; font-weight:500; }
.no-video { background:#f8faff; border-radius:10px; border:2px dashed #c7d2fe; padding:32px; text-align:center; color:#6366f1; }
.no-video .nv-ico { font-size:32px; margin-bottom:8px; }
.no-video p { font-size:13px; }
/* ---- 客户画像预览（浅色科技风） ---- */
.profile-preview { background:#f4f5f8; border-top:1px solid #e3e5e8; padding:0 32px 24px; }
.profile-preview-label { display:flex; align-items:center; gap:8px; font-size:12px; font-weight:700; color:#5f6b7a; letter-spacing:.5px; padding:20px 0 12px; }
.profile-preview-label .pdot { width:8px;height:8px;border-radius:50%;background:#10b981; }
.profile-preview-label .pbeta { font-size:9px; background:#d1fae5; color:#047857; padding:2px 8px; border-radius:10px; font-weight:800; letter-spacing:1px; text-transform:uppercase; }
.profile-preview-frame { width:100%; height:560px; border-radius:10px; overflow:hidden; border:1px solid #d4d8e0; background:#fff; }
.profile-preview-frame iframe { width:100%; height:100%; border:none; }
@media (max-width:768px) { .profile-preview { padding:0 16px 20px; } .profile-preview-frame { height:420px; } }
/* ---- 截图画廊（浅色科技风） ---- */
.img-gallery { display:grid; grid-template-columns:repeat(3,1fr); gap:16px; align-items:start; }
.img-gallery.col2 { grid-template-columns:repeat(2,1fr); }
.img-gallery.col1 { grid-template-columns:1fr; }
.img-gallery figure { background:#f8f9fb; border-radius:10px; overflow:hidden; border:1px solid #e3e5e8; margin:0; display:flex; flex-direction:column; height:100%; }
.img-gallery img { width:100%; display:block; object-fit:contain; height:260px; background:#f4f5f8; line-height:0; flex-shrink:0; }
.img-gallery figcaption { padding:10px 14px; font-size:12px; color:#5f6b7a; background:#fff; border-top:1px solid #e3e5e8; }
.bid-flow-platform { display:flex; gap:16px; align-items:flex-start; margin-bottom:0; }
.bid-flow-platform .app-video-panel { flex:1; min-width:0; }
.img-gallery-single { grid-template-columns:1fr; }
.img-gallery-single figure { max-width:100%; line-height:0; }
.img-gallery-single img { object-fit:contain; }
.bid-compare { margin-top:0; background:#fff; border-radius:12px; border:1px solid var(--border-card); overflow:hidden; }
.bid-compare-title { padding:14px 20px; font-size:16px; font-weight:700; color:#fff; background:linear-gradient(135deg,#1e3a6e,#2a5298); display:flex; align-items:center; gap:8px; }
.bid-compare-title .ai-dot { width:10px; height:10px; background:#60a5fa; border-radius:50%; box-shadow:0 0 8px #60a5fa; animation:pulse-dot 2s infinite; }
@keyframes pulse-dot { 0%,100%{opacity:1;} 50%{opacity:.4;} }
.bid-table { width:100%; border-collapse:collapse; table-layout:fixed; }
.bid-table thead th { padding:8px 12px; font-size:12px; font-weight:600; color:#5f6b7a; text-align:center; border-bottom:1px solid var(--border-card); background:#fafbfc; }
.bid-table thead th:first-child { text-align:left; width:140px; }
.bid-table td { padding:8px 12px; text-align:center; font-size:13px; color:var(--text); border-bottom:1px solid #f0f1f3; vertical-align:middle; }
.bid-table td:first-child { text-align:left; padding-left:16px; }
.bid-table td.td-desc { text-align:left; font-size:12px; line-height:1.5; }
.bid-table .old-row td { background:rgba(248,113,113,.04); }
.bid-table .new-row td { background:rgba(74,222,128,.04); }
.bid-ver-tag { display:inline-block; padding:4px 12px; border-radius:10px; font-size:11px; font-weight:600; white-space:nowrap; }
.bid-ver-tag.old { background:rgba(220,38,38,.1); color:#dc2626; }
.bid-ver-tag.new { background:rgba(0,168,132,.1); color:#0a7a5a; }
.bid-num { font-size:15px; font-weight:700; }
.bid-num.old { color:#dc2626; }
.bid-num.new { color:#0a7a5a; }
.bid-pct { font-size:24px; font-weight:900; }
.bid-pct.old { color:#dc2626; }
.bid-pct.new { color:#0a7a5a; }
.bid-note { font-size:11px; color:#5f6b7a; display:block; margin-top:2px; }
.bid-compare-footer { padding:10px 20px; background:#fafbfc; border-top:1px solid #f0f1f3; font-size:11px; color:#5f6b7a; }
.bid-compare-footer .boost { color:#0a7a5a; font-weight:700; }
@media (max-width:768px) { .bid-flow-platform { flex-direction:column; } .bid-table thead th:first-child { width:100px; } }
.scene-divider { max-width:1100px; margin:0 auto; border:none; border-top:2px solid var(--border); }
.bg-opp  { background:linear-gradient(180deg,#e6f0fa 0%,#f8f9fb 100%); }
.bg-visit{ background:linear-gradient(180deg,#e6f7f2 0%,#f8f9fb 100%); }
.bg-proj { background:linear-gradient(180deg,#eee8ff 0%,#f8f9fb 100%); }
.bg-bid  { background:linear-gradient(180deg,#fef3e2 0%,#f8f9fb 100%); }
.bg-knowledge { background:linear-gradient(180deg,#eef0ff 0%,#f8f9fb 100%); }
.bg-skill { background:linear-gradient(180deg,#e0f4ff 0%,#f8f9fb 100%); }
.stats-strip { background:linear-gradient(120deg,#0b1a3b,#0f2b5c,#0a1f42); border-radius:16px; padding:28px 40px; display:flex; flex-wrap:wrap; gap:32px; justify-content:space-around; margin:0 0 40px; }
.app-stats-strip { background:linear-gradient(135deg,#f0f4fa,#e6f0fa); border-radius:12px; padding:18px 28px; display:flex; flex-wrap:wrap; gap:24px; justify-content:space-around; margin:0 28px 20px; border:1px solid #d4e0f0; }
.app-stats-item { text-align:center; }
.app-stats-num { font-size:26px; font-weight:900; line-height:1.1; background:linear-gradient(135deg,#0f2b5c,#00a884); -webkit-background-clip:text; -webkit-text-fill-color:transparent; }
.app-stats-label { font-size:11px; color:var(--muted); font-weight:500; }
.app-stats-note { text-align:center; font-size:11px; color:var(--muted); margin-top:-8px; margin-bottom:14px; }
.ss-item { text-align:center; }
.ss-num { font-size:36px; font-weight:900; line-height:1; background:linear-gradient(90deg,#fbbf24,#fb923c); -webkit-background-clip:text; -webkit-text-fill-color:transparent; }
.ss-label { font-size:12px; color:rgba(255,255,255,.55); margin-top:4px; }
footer { text-align:center; padding:36px 24px 60px; border-top:1px solid var(--border); font-size:13px; color:var(--muted); }
footer .ft-logo { font-size:18px; font-weight:900; color:var(--brand-teal); margin-bottom:6px; }
.view-counter { display:inline-flex; align-items:center; gap:6px; margin-top:10px; padding:8px 20px; background:linear-gradient(135deg,#0f2b5c,#1a3a6a); border-radius:24px; color:#fff; font-size:13px; font-weight:600; letter-spacing:.3px; box-shadow:0 4px 16px rgba(15,43,92,.3); }
.view-counter .vc-icon { font-size:16px; }
.view-counter .vc-num { font-size:22px; font-weight:900; background:linear-gradient(90deg,#60a5fa,#a78bfa); -webkit-background-clip:text; -webkit-text-fill-color:transparent; }

/* ============ 招投标步骤 ============ */
.bid-steps-grid { display:grid; grid-template-columns:1fr 40px 1fr 40px 1fr; gap:0; align-items:center; margin-bottom:36px; }
.bid-step-card { background:#fff; border-radius:14px; border:2px solid; padding:20px; text-align:center; box-shadow:var(--shadow); }
.bid-step-title { font-weight:800; font-size:14px; margin-bottom:6px; }
.bid-step-list { font-size:12px; color:var(--muted); text-align:left; padding-left:14px; line-height:1.8; }
.bid-step-arrow { text-align:center; font-size:20px; color:#cbd5e1; font-weight:700; }

/* ============ 移动端适配 ============ */
@media (max-width:768px) {
  nav { height:48px; padding:0 12px; }
  .nav-brand { font-size:12px; gap:4px; }
  .nav-brand img { height:22px; }
  .nav-brand span { display:none; }
  .nav-tabs { gap:0; }
  .nav-tabs a { padding:4px 8px; font-size:13px; }
  .nav-right { display:none; }

  .hero { padding:80px 16px 60px; min-height:auto; }
  .hero-inner { padding:0 8px; }
  .hero-logo-img { height:36px; }
  .hero-logo-dept { font-size:14px; }
  .hero h1 { font-size:28px; }
  .hero-sub { font-size:13px; max-width:100%; }
  .hero-card { width:calc(50% - 8px); padding:16px 10px; }
  .hero-card .hc-icon { font-size:30px; }
  .hero-card .hc-name { font-size:13px; }
  .hero-card .hc-desc { font-size:11px; }
  .hero-incentive-badge { min-width:0; flex:1; padding:12px 10px; }
  .hero-incentive-badge .hb-title { font-size:12px; }
  .hero-incentive-badge .hb-sub { font-size:10px; }
  .hero-incentive-badge .hb-link { font-size:9px; }
  .hero-incentive-label { font-size:18px; }
  .hero-incentive-desc { font-size:11px; }

  .scene-nav { top:48px; padding:6px 0; }
  .scene-nav-inner { padding:0 12px; gap:6px; overflow-x:auto; flex-wrap:nowrap; -webkit-overflow-scrolling:touch; }
  .scene-nav-btn { padding:8px 14px; font-size:14px; white-space:nowrap; flex-shrink:0; }
  .scene-nav-hint { display:none; }

  .scene-section { padding:32px 14px 48px; }
  .scene-header { gap:10px; margin-bottom:28px; flex-wrap:wrap; }
  .scene-header-ico { width:38px; height:38px; font-size:18px; border-radius:10px; }
  .scene-title { font-size:20px; }
  .scene-sub { font-size:12px; }
  .scene-count { font-size:11px; padding:3px 10px; }
  .scene-timeline { padding:0 10px; }
  .scene-timeline::before { left:20px; }

  .app-block { margin-bottom:20px; border-radius:14px; }
  .app-block-header { padding:14px 16px; gap:10px; flex-wrap:wrap; }
  .app-num-badge { width:28px; height:28px; font-size:12px; }
  .app-title { font-size:15px; }
  .app-subtitle { font-size:11px; }

  .app-content { grid-template-columns:1fr; }
  .app-col { padding:18px 16px; border-right:none; border-bottom:1px solid var(--border-card); }
  .app-col:last-child { border-bottom:none; }
  .app-col p { font-size:12px; }
  .app-col ul { font-size:12px; }
  .col-emoji-bg { font-size:44px; }

  .app-stats-strip { padding:14px 16px; gap:14px; margin:0 14px 14px; }
  .app-stats-num { font-size:20px; }
  .app-stats-label { font-size:10px; }

  .app-video-panel { padding:14px 14px 18px; }
  .video-wrapper video { max-height:240px; }
  .video-wrapper { min-height:180px; }
  .vp-icon { width:48px; height:48px; font-size:20px; }
  .img-gallery,.img-gallery.col2,.img-gallery.col1 { grid-template-columns:1fr; gap:10px; }
  .img-gallery img { max-height:300px; }

  .profile-preview { padding:0 14px 18px; }
  .profile-preview-frame { height:380px; }
  .profile-preview-label { font-size:11px; padding:14px 0 8px; }

  .bid-compare-title { font-size:14px; padding:10px 14px; }
  .bid-table { display:block; overflow-x:auto; -webkit-overflow-scrolling:touch; }
  .bid-table thead th { font-size:11px; padding:8px 10px; }
  .bid-table td { font-size:12px; padding:8px 10px; }
  .bid-table td.td-desc { font-size:11px; }
  .bid-pct { font-size:20px; }
  .bid-compare-footer { font-size:9px; padding:8px 14px; }

  .stats-strip { padding:18px 16px; gap:16px; border-radius:12px; }
  .ss-num { font-size:26px; }

  .bid-steps-grid { grid-template-columns:1fr !important; gap:8px !important; margin-bottom:24px; }
  .bid-step-arrow { display:none; }
  .bid-step-card { padding:14px 14px; }
  .bid-step-title { font-size:13px; }
  .bid-step-list { font-size:11px; }

  footer { padding:24px 16px 40px; font-size:12px; }
  .view-counter { padding:6px 14px; font-size:11px; }
  .view-counter .vc-num { font-size:16px; }
}
/* ── 未来规划（独立模块）── */
.future-section { max-width:960px; margin:48px auto 0; padding:0 24px; }
.future-card { background:#fff; border-radius:16px; border:1px solid var(--border-card); overflow:hidden; box-shadow:var(--shadow); }
.future-header { background:linear-gradient(135deg,#1e3a5f 0%,#2d5a8e 40%,#3b7bc4 100%); padding:32px 36px; color:#fff; position:relative; overflow:hidden; }
.future-header::before { content:''; position:absolute; top:-30%; right:-10%; width:200px; height:200px; background:rgba(255,255,255,.06); border-radius:50%; }
.future-header::after { content:''; position:absolute; bottom:-20%; right:15%; width:120px; height:120px; background:rgba(255,255,255,.04); border-radius:50%; }
.future-header-inner { position:relative;z-index:1; }
.future-header h2 { font-size:22px;font-weight:700;margin:0 0 6px;letter-spacing:1px; }
.future-header p { font-size:14px;opacity:.88;margin:0; }
.future-body { padding:28px 36px 32px; }
.fp-item { margin-bottom:24px; }
.fp-item:last-child { margin-bottom:0; }
.fp-label { display:inline-flex;align-items:center;gap:6px;font-size:14px;font-weight:700;color:#1e3a5f;margin-bottom:10px;padding-bottom:6px;border-bottom:2px solid #e5e7eb; }
.fp-item p { font-size:14px;color:#374151;line-height:1.8;margin:6px 0; }
.fp-item ul { list-style:none;padding:0;margin:8px 0 0;padding-left:4px; }
.fp-item ul li { font-size:14px;color:#374151;padding:5px 0 5px 18px;position:relative;line-height:1.7; }
.fp-item ul li::before { content:'•';position:absolute;left:0;color:#3b82f6;font-weight:700;font-size:15px;top:5px; }
.fp-item strong { color:#1e3a5f;font-weight:700; }
.fp-path-tag { display:inline-flex;align-items:center;gap:8px;padding:8px 18px;background:#eff6ff;border-radius:8px;border:1px solid #bfdbfe;font-size:13px;color:#1d4ed8;font-weight:600;margin-top:12px; }

@media(max-width:720px){
  .future-section { margin:32px auto 0; padding:0 16px; }
  .future-header { padding:24px 20px; }
  .future-header h2 { font-size:18px; }
  .future-body { padding:20px 18px; }
}
/* 点赞评论模块 */
.feedback-section { max-width:680px; margin:0 auto; padding:32px 24px 16px; }
.feedback-card { background:#fff; border-radius:12px; border:1px solid var(--border-card); padding:24px 28px; }
.feedback-header { text-align:center; margin-bottom:18px; }
.feedback-header h3 { font-size:18px; font-weight:700; color:var(--text); margin:0 0 4px; }
.feedback-header p { font-size:13px; color:var(--muted); margin:0; }
.fb-like-row { display:flex; align-items:center; justify-content:center; gap:12px; margin-bottom:18px; }
.fb-like-btn { display:inline-flex; align-items:center; gap:6px; padding:10px 22px; border-radius:24px; border:2px solid #e3e5e8; background:#fff; font-size:15px; font-weight:600; color:var(--text); cursor:pointer; transition:all .2s; user-select:none; }
.fb-like-btn:hover { border-color:#ef4444; color:#ef4444; }
.fb-like-btn.liked { border-color:#ef4444; background:#fef2f2; color:#ef4444; }
.fb-like-count { font-size:14px; color:var(--muted); }
.fb-comments { border-top:1px solid #f0f1f3; padding-top:16px; }
.fb-comment-form { display:flex; gap:8px; margin-bottom:14px; flex-wrap:wrap; }
.fb-comment-form input { flex:0 0 100px; padding:8px 12px; border:1px solid #e3e5e8; border-radius:8px; font-size:13px; outline:none; }
.fb-comment-form input:focus { border-color:var(--brand-teal); }
.fb-comment-form textarea { flex:1; min-width:200px; padding:8px 12px; border:1px solid #e3e5e8; border-radius:8px; font-size:13px; resize:vertical; min-height:36px; outline:none; font-family:inherit; }
.fb-comment-form textarea:focus { border-color:var(--brand-teal); }
.fb-comment-form button { padding:8px 18px; background:linear-gradient(135deg,#0f2b5c,#1e4f8a); color:#fff; border:none; border-radius:8px; font-size:13px; font-weight:600; cursor:pointer; transition:opacity .2s; }
.fb-comment-form button:hover { opacity:.9; }
.fb-comment-list { max-height:300px; overflow-y:auto; }
.fb-comment-item { padding:10px 0; border-bottom:1px solid #f5f6f7; }
.fb-comment-item:last-child { border-bottom:none; }
.fb-comment-meta { font-size:11px; color:var(--muted); margin-bottom:3px; display:flex; justify-content:space-between; }
.fb-comment-meta strong { color:var(--text); font-size:13px; }
.fb-comment-text { font-size:13px; color:var(--text); line-height:1.5; }
.fb-comment-del { font-size:11px; color:#ccc; cursor:pointer; background:none; border:none; padding:0 4px; }
.fb-comment-del:hover { color:#ef4444; }
.fb-reply-btn { font-size:11px; color:var(--brand-teal); cursor:pointer; background:none; border:none; padding:0 4px; }
.fb-reply-btn:hover { text-decoration:underline; }
.fb-reply-area { margin:6px 0 0 0; display:none; }
.fb-reply-area.show { display:block; }
.fb-reply-area textarea { width:100%; padding:6px 10px; border:1px solid #e3e5e8; border-radius:6px; font-size:12px; resize:vertical; min-height:30px; outline:none; font-family:inherit; box-sizing:border-box; }
.fb-reply-area textarea:focus { border-color:var(--brand-teal); }
.fb-reply-area button { margin-top:4px; padding:4px 12px; background:var(--brand-teal); color:#fff; border:none; border-radius:6px; font-size:12px; cursor:pointer; }
.fb-reply-area button:hover { opacity:.9; }
.fb-reply-item { padding:4px 0 4px 14px; margin:2px 0; border-left:2px solid #e3e5e8; font-size:12px; color:var(--text); }
.fb-reply-item strong { font-size:12px; color:var(--text); }
.fb-reply-item span { font-size:10px; color:var(--muted); margin-left:4px; }
.fb-empty { text-align:center; font-size:13px; color:var(--muted); padding:20px 0; }
.fb-loading { text-align:center; font-size:12px; color:var(--muted); padding:10px; }
@media (max-width:768px) {
  .feedback-section { padding:20px 14px 8px; }
  .feedback-card { padding:16px; }
  .fb-comment-form { flex-direction:column; }
  .fb-comment-form input { flex:1; }
}
</style>'''


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
const scenes=[{id:'scene-opp',navIdx:0},{id:'scene-visit',navIdx:1},{id:'scene-proj',navIdx:2},{id:'scene-bid',navIdx:3},{id:'scene-knowledge',navIdx:4}];
const io=new IntersectionObserver(entries=>{entries.forEach(e=>{if(e.isIntersecting){const idx=scenes.findIndex(s=>s.id===e.target.id);if(idx===-1)return;navLinks.forEach(a=>a.classList.remove('active'));sceneButtons.forEach(b=>b.classList.remove('active'));if(navLinks[idx])navLinks[idx].classList.add('active');if(sceneButtons[idx])sceneButtons[idx].classList.add('active')}})},{threshold:0.25});
scenes.forEach(s=>{const el=document.getElementById(s.id);if(el)io.observe(el)});

// 视频懒加载 — 只加载视口附近的视频，避免首屏全部视频同时请求
var videoObs=new IntersectionObserver(function(entries){
  entries.forEach(function(e){
    if(!e.isIntersecting) return;
    var w=e.target,vid=w.querySelector('video'),src=w.getAttribute('data-video-src');
    if(!vid||!src||w.classList.contains('loaded')) return;
    vid.innerHTML='<source src="'+src+'" type="video/mp4">';
    vid.load(); w.classList.add('loaded');
    videoObs.unobserve(w);
  });
},{rootMargin:'300px'});
document.querySelectorAll('.video-wrapper').forEach(function(w){videoObs.observe(w);});

// 点击占位符也触发加载
document.addEventListener('click',function(e){
  var ph=e.target.closest('.video-placeholder');
  if(!ph) return;
  var w=ph.closest('.video-wrapper'),vid=w.querySelector('video'),src=w.getAttribute('data-video-src');
  if(!vid||!src||w.classList.contains('loaded')) return;
  vid.innerHTML='<source src="'+src+'" type="video/mp4">';
  vid.load(); w.classList.add('loaded');
  videoObs.unobserve(w);
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
  document.getElementById('fb-like-count').textContent=fbLikes+' 人觉得很赞';
  document.getElementById('fb-cmt-count').textContent=fbComments.length;
  var btn=document.getElementById('fb-like-btn');
  if(fbLiked) btn.classList.add('liked'); else btn.classList.remove('liked');
  var list=document.getElementById('fb-comment-list');
  if(!fbComments.length){ list.innerHTML='<div class="fb-empty">暂无评论，来坐沙发吧 ☕</div>'; return; }
  list.innerHTML=fbComments.slice().reverse().map(function(c){
    var t=new Date(c.time),ts=t.getFullYear()+'-'+String(t.getMonth()+1).padStart(2,'0')+'-'+String(t.getDate()).padStart(2,'0')+' '+String(t.getHours()).padStart(2,'0')+':'+String(t.getMinutes()).padStart(2,'0');
    var rs=(c.replies||[]).map(function(r){var rt=new Date(r.time),rts=rt.getFullYear()+'-'+String(rt.getMonth()+1).padStart(2,'0')+'-'+String(rt.getDate()).padStart(2,'0')+' '+String(rt.getHours()).padStart(2,'0')+':'+String(rt.getMinutes()).padStart(2,'0');return '<div class="fb-reply-item"><strong>'+esc(r.name)+'</strong><span>'+rts+'</span>：'+esc(r.text)+'</div>';}).join('');
    return '<div class="fb-comment-item" data-cid="'+c.id+'"><div class="fb-comment-meta"><strong>'+esc(c.name)+'</strong><span>'+ts+'<button class="fb-reply-btn" data-cid="'+c.id+'" title="回复">💬 回复</button><button class="fb-comment-del" data-cid="'+c.id+'" title="删除">✕</button></span></div><div class="fb-comment-text">'+esc(c.text)+'</div>'+rs+'<div class="fb-reply-area" id="reply-area-'+c.id+'"><textarea id="reply-text-'+c.id+'" placeholder="写下回复…" rows="2" maxlength="200"></textarea><button data-cid="'+c.id+'" class="fb-reply-submit">回复</button></div></div>';
  }).join('');
}
function esc(s){var d=document.createElement('div');d.textContent=s;return d.innerHTML}

// 点赞按钮 — 原子递增，并发安全
document.getElementById('fb-like-btn').addEventListener('click',function(){
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

// 初始加载 + 15秒定时同步
syncFromCloud();
setInterval(syncFromCloud,15000);

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
document.getElementById('fb-submit-btn').addEventListener('click',submitComment);

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
document.getElementById('fb-comment-list').addEventListener('click',function(e){
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
  }).catch(function(){ syncFromCloud(); });
}
</script>'''


def md_to_html(md_text):
    """将markdown格式文本转为HTML片段"""
    text = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', md_text)
    parts = text.split('\n\n')
    result = []
    for p in parts:
        p = p.strip()
        if not p: continue
        if p.startswith('- '):
            items = [li[2:] for li in p.split('\n') if li.startswith('- ')]
            result.append('<ul>\n          ' + '\n          '.join(f'<li>{item}</li>' for item in items) + '\n        </ul>')
        else:
            result.append(f'<p>{p}</p>')
    return '\n        '.join(result)


def build_bid_compare(bid_compare_data):
    if not bid_compare_data:
        return ''
    r = bid_compare_data['rows']
    # 取主要维度（排除总结和质量说明）
    main = [row for row in r if row['dim'] not in ('总结','质量说明')]
    qn = next((row for row in r if row['dim'] == '质量说明'), None)
    headers = ''.join(f'<th>{d["dim"]}</th>' for d in main)
    
    def cell(d, ver):
        if d['dim'] == '数据治理':
            return f'<td class="td-desc">{d[ver]}</td>'
        elif d['dim'] == '推送数量':
            return f'<td class="td-desc">{d[ver]}</td>'
        else:
            note = qn[ver] if qn else ''
            return f'<td class="td-desc">{d[ver]}<br>{note}</td>'
    
    cls = {'v1':'old','v2':'new'}
    ver_label = {'v1':('old','V1.0（治理前）'), 'v2':('new','V2.0（治理后）')}
    rows_html = ''
    for v in ['v1','v2']:
        c, lbl = ver_label[v]
        cells = ''.join(cell(d, v) for d in main)
        rows_html += f'\n            <tr class="{c}-row"><td><span class="bid-ver-tag {c}">{lbl}</span></td>{cells}</tr>'
    
    footer = bid_compare_data.get('footer','')
    return f'''      <div class="bid-compare">
        <div class="bid-compare-title"><span class="ai-dot"></span>AI助力高价值标讯</div>
        <table class="bid-table">
          <thead><tr><th></th>{headers}</tr></thead>
          <tbody>{rows_html}
          </tbody>
        </table>
        <div class="bid-compare-footer">
          <span>🎯 {footer}</span>
        </div>
      </div>'''


def build(data):
    g = data['global']
    scene_id_map = {1:'scene-opp',2:'scene-visit',3:'scene-proj',4:'scene-bid',5:'scene-knowledge',6:'scene-skill'}
    bg_map = {1:'bg-opp',2:'bg-visit',3:'bg-proj',4:'bg-bid',5:'bg-knowledge',6:'bg-skill'}
    icon_colors = ["linear-gradient(135deg,#0f2b5c,#1e4f8a)","linear-gradient(135deg,#00a884,#00b894)","linear-gradient(135deg,#0f2b5c,#5b3fd4)","linear-gradient(135deg,#e8710a,#dc2626)","linear-gradient(135deg,#6366f1,#8b5cf6)","linear-gradient(135deg,#0ea5e9,#0284c7)"]
    badge_maps = {
        1: [("linear-gradient(135deg,#0f2b5c,#1e4f8a)","1"),("linear-gradient(135deg,#0284c7,#0891b2)","2"),("linear-gradient(135deg,#0891b2,#0e7490)","3")],
        2: [("linear-gradient(135deg,#00a884,#00b894)","1"),("linear-gradient(135deg,#0284c7,#4f46e5)","2")],
        3: [("linear-gradient(135deg,#0f2b5c,#5b3fd4)","1"),("linear-gradient(135deg,#5b3fd4,#e8710a)","2")],
        4: [("linear-gradient(135deg,#e8710a,#dc2626)","AI")],
        5: [("linear-gradient(135deg,#6366f1,#8b5cf6)","AI")],
        6: [("linear-gradient(135deg,#0ea5e9,#0284c7)","1"),("linear-gradient(135deg,#0284c7,#0891b2)","2")]
    }
    pain_emojis = {1:'📊',2:'🔍',3:'🔀',4:'😰',5:'📚'}
    solve_emojis = {1:'⚡',2:'✨',3:'⚡',4:'🏆',5:'💡'}
    how_emojis = {1:'🗺️',2:'🎯',3:'🗝️',4:'🗝️',5:'🔮'}
    char_colors = ["linear-gradient(135deg,#dbeafe,#93c5fd)","linear-gradient(135deg,#fce7f3,#f9a8d4)","linear-gradient(135deg,#fef9c3,#fde047)","linear-gradient(135deg,#dcfce7,#4ade80)"]
    
    profile_preview = '''    <div class="profile-preview">
      <div class="profile-preview-label"><span class="pdot"></span>客户画像 2.0 优化中 <span class="pbeta">NEW</span> — 下滑查看最新画像内容</div>
      <div class="profile-preview-frame"><iframe src="media/天津大学_安全画像.html" title="天津大学安全画像"></iframe></div>
    </div>'''
    
    # -- NAV --
    nav_links = []
    scene_btns = []
    for s in data['scenes']:
        idx = s['num']-1
        sid = scene_id_map.get(s['num'], f'scene-{s["num"]}')
        icon = s.get('icon','🎯')
        name = s.get('title',s.get('name',''))
        nav_links.append(f'    <a href="#{sid}">{icon} {name}</a>')
        scene_btns.append(f'    <button class="scene-nav-btn" data-scene="{sid}"><span class="sn-ico">{icon}</span>{name}</button>')
    
    # -- CHIPS (removed per user request, keep chips list empty for compat) --
    # -- HERO --
    
    nav = f'''<nav>
  <a class="nav-brand" href="#hero"><img src="media/image2.png" alt="安恒信息"><span>AI赋能营销</span></a>
  <div class="nav-tabs">\n{chr(10).join(nav_links)}\n  </div>
  <div class="nav-right">{g.get('页脚部门','营销中心综合管理部')}</div>
</nav>'''
    
    # -- HERO --
    chips = []
    for s in data['scenes']:
        chips.append(f'      <div class="hero-chip"><span class="ci">{s.get("icon","🎯")}</span>{s.get("title","")}</div>')
    chips.append('      <div class="hero-chip"><span class="ci">⚡</span>10+ AI工具</div>')
    
    heroes_chars = ''
    for idx, h in enumerate(data['heroes']):
        heroes_chars += f'      <div class="hero-card"><div class="hc-icon">{h["avatar"]}</div><div class="hc-name">{h["name"]}</div><div class="hc-desc">{h["bubble"].replace("\\n","<br>")}</div></div>\n'
    
    hero = f'''<section class="hero" id="hero">
  <div class="hero-bg-circles"><span></span><span></span><span></span></div>
  <div class="hero-inner">
    <div class="hero-logo-row"><img class="hero-logo-img" src="media/image2.png" alt="安恒信息"><div class="hero-logo-dept">营销中心 · 综合管理部</div></div>
    <h1>{g.get('Hero大标题','AI赋能营销')}<br><em>{g.get('Hero副标题','让每一线都更强')}</em></h1>
    <p class="hero-sub">{g.get('Hero描述','')}</p>
    <div class="hero-char-cards">\n{heroes_chars}    </div>
    <div class="hero-incentive-divider"></div>
    <div class="hero-incentive-label">✨ 激励 ✨</div>
    <div class="hero-incentives-row">
      <a href="https://ah-marketing-2026.github.io/honor/" target="_blank" class="hero-incentive-badge"><div class="hb-icon">📅</div><div class="hb-title">常态化月度</div><div class="hb-sub">月度AI应用激励</div><div class="hb-link">查看详情 →</div></a>
      <a href="https://365.kdocs.cn/l/cqQpJWaDnycr" target="_blank" class="hero-incentive-badge"><div class="hb-icon">🏆</div><div class="hb-title">10W专项</div><div class="hb-sub">特别贡献激励</div><div class="hb-link">查看详情 →</div></a>
      <div class="hero-incentive-badge"><div class="hb-icon">🎯</div><div class="hb-title">年底激励</div><div class="hb-sub">敬请期待</div></div>
    </div>
    <div class="hero-incentive-desc">积极使用AI工具，主动反馈优化建议，甚至自建提效Skill——优秀实践可获月度激励、专项大奖及年度荣誉！</div>
  </div>
</section>'''
    
    scene_nav = f'<div class="scene-nav"><div class="scene-nav-inner">\n{chr(10).join(scene_btns)}\n    <span class="scene-nav-hint">💡 点击按钮快速跳转对应场景</span>\n</div></div>'
    
    # -- SCENES --
    scenes_html = ''
    for s in data['scenes']:
        snum = s['num']
        sid = scene_id_map.get(snum, f'scene-{snum}')
        bg = bg_map.get(snum,'')
        icon = s.get('icon','🎯')
        title = s.get('title','')
        subtitle = s.get('subtitle','')
        icon_color = icon_colors[min(snum-1, len(icon_colors)-1)]
        count = f'{len(s["apps"])}个应用' if snum not in (4,) else '3大能力'
        
        # Stats
        stats = ''
        if s.get('stats'):
            items = [f'<div class="ss-item"><div class="ss-num">{st["num"]}</div><div class="ss-label">{st["label"]}</div></div>' for st in s['stats']]
            stats = f'\n<div class="stats-strip">{"".join(items)}</div>\n'
        
        # 招投标三步流程（动态从content.md读取；兼容旧版：若应用无bid_steps则用场景默认）
        bid_steps = ''
        if snum == 4:
            bid_app = next((a for a in s['apps'] if a.get('bid_steps')), None)
            bid_steps = build_bid_steps(bid_app['bid_steps']) if bid_app else ''
        
        # Apps
        apps_html = ''
        for ai, app in enumerate(s['apps']):
            bc = badge_maps.get(snum, [])
            badge_style, badge_num = bc[ai] if ai < len(bc) else bc[0]
            
            pain = md_to_html(app.get('pain',''))
            solve = md_to_html(app.get('solve',''))
            
            # How
            how_parts = []
            if app.get('how'):
                how_parts.append(f'<p>{re.sub(r"\*\*(.+?)\*\*",r"<strong>\\1</strong>",app["how"])}</p>')
            for p in app.get('paths', []):
                tag_html = ' <span class="arr">→</span> '.join(f'<span>{tp.strip()}</span>' for tp in p.split('→'))
                how_parts.append(f'<div class="path-tag">{tag_html}</div>')
            for e in app.get('extra_info', []):
                if isinstance(e,tuple) and e[0]=='path_title':
                    how_parts.append(f'<p style="font-weight:700;margin:10px 0 4px;">{e[1]}</p>')
                else:
                    how_parts.append(f'<p style="font-size:12px;color:var(--muted);margin-top:8px;">{e}</p>')
            how_html = '\n        '.join(how_parts)
            
            pe = pain_emojis.get(snum,'📊')
            se = solve_emojis.get(snum,'⚡')
            he = how_emojis.get(snum,'🗝️')
            
            # App stats strip
            app_stats_html = ''
            if app.get('stats'):
                stats_items = [f'<div class="app-stats-item"><div class="app-stats-num">{st["num"]}</div><div class="app-stats-label">{st["label"]}</div></div>' for st in app['stats']]
                note = f'<div class="app-stats-note">{app["stats_note"]}</div>' if app.get('stats_note') else ''
                app_stats_html = f'\n<div class="app-stats-strip">{"".join(stats_items)}</div>\n{note}'
            
            # Video panel
            video_panel = ''
            if app.get('placeholder'):
                video_panel = f'''    <div class="app-video-panel">
      <div class="app-video-label"><span class="vdot"></span>应用演示视频（移动端演示）</div>
      <div class="no-video"><div class="nv-ico">{app.get('placeholder_icon','📱')}</div><p>{app.get('placeholder_text','')}</p></div>
    </div>'''
            elif app.get('images'):
                imgs = app['images']
                _bid = build_bid_compare(app.get('bid_compare'))
                if _bid and len(imgs) >= 2:
                    # 标讯运营：业务流 + 平台 并排，表格在下方
                    video_panel = f'''    <div class="bid-flow-platform">
      <div class="app-video-panel">
        <div class="app-video-label"><span class="vdot" style="background:#38bdf8;"></span>业务流</div>
        <div class="img-gallery img-gallery-single"><figure><img src="{imgs[0]["src"]}" alt=""><figcaption>{imgs[0].get("caption","")}</figcaption></figure></div>
      </div>
      <div class="app-video-panel">
        <div class="app-video-label"><span class="vdot" style="background:#f59e0b;"></span>平台</div>
        <div class="img-gallery img-gallery-single"><figure><img src="{imgs[1]["src"]}" alt=""><figcaption>{imgs[1].get("caption","")}</figcaption></figure></div>
      </div>
    </div>'''
                    if _bid:
                        video_panel += '\n' + _bid
                else:
                    figs = [f'<figure><img src="{img["src"]}" alt="">{"<figcaption>"+img.get("caption","")+"</figcaption>" if img.get("caption","") else ""}</figure>' for img in imgs]
                    n = len(imgs)
                    gcol = 'col1' if n==1 else ('col2' if n==2 else '')
                    video_panel = f'''    <div class="app-video-panel">
      <div class="app-video-label"><span class="vdot" style="background:#38bdf8;"></span>应用演示截图</div>
      <div class="img-gallery {gcol}">{chr(10).join(figs)}</div>
    </div>'''
            elif app.get('video'):
                video_panel = f'''    <div class="app-video-panel">
      <div class="app-video-label"><span class="vdot"></span>应用演示视频</div>
      <div class="video-wrapper" data-video-src="media/{app['video']}"><video controls playsinline webkit-playsinline x5-playsinline preload="none" controlslist="nodownload" style="position:relative;z-index:1"></video><div class="video-placeholder"><span class="vp-icon">▶</span><span class="vp-text">点击播放演示视频</span></div></div>
    </div>'''
            
            apps_html += f'''
  <div class="app-block">
    <div class="app-block-header">
      <div class="app-num-badge" style="background:{badge_style};{'font-size:13px;' if badge_num=='AI' else ''}">{badge_num}</div>
      <div><div class="app-title">{app['title']}</div><div class="app-subtitle">{app.get('subtitle','')}</div></div>
    </div>{app_stats_html}
    <div class="app-content">
      <div class="app-col"><div class="col-label col-label-pain">😩 用户痛点</div>{pain}<div class="col-emoji-bg">{pe}</div></div>
      <div class="app-col"><div class="col-label col-label-solve">✅ AI能帮你</div>{solve}<div class="col-emoji-bg">{se}</div></div>
      <div class="app-col"><div class="col-label col-label-how">🔧 平台入口</div>{how_html}<div class="col-emoji-bg">{he}</div></div>
    </div>
{video_panel}
    {profile_preview if snum==2 and ai==0 else ''}  </div>'''
        
        scenes_html += f'\n<div class="scene-timeline-item" id="{sid}">\n<div class="{bg}">\n<div class="scene-section">\n  <div class="scene-header">\n    <button class="scene-toggle" data-target="{sid}-body" aria-label="折叠/展开">▼</button>\n    <div class="scene-header-ico" style="background:{icon_color};color:#fff;">{icon}</div>\n    <div><div class="scene-title">{title}</div><div class="scene-sub">{subtitle}</div></div>\n    <div class="scene-count">{count}</div>\n  </div>\n  <div class="scene-body" id="{sid}-body">\n{stats}{bid_steps}{apps_html}\n  </div>\n</div>\n</div>\n</div>'
    
    # Future plan module（独立展示，不用场景模板）
    fp = data.get('future_plan', {})
    if fp.get('directions') or fp.get('status'):
        import html as _html_mod
        # 简单markdown→HTML：**bold** → <strong>，- 列表 → <li>
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

        future_html = f'''<section class="future-section">
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
    else:
        future_html = ''
    
    # Feedback module
    fb = data.get('feedback', {})
    feedback_html = f'''<section class="feedback-section">
  <div class="feedback-card">
    <div class="feedback-header"><h3>{fb.get("标题","👍 觉得有用吗？")}</h3><p>{fb.get("副标题","您的反馈帮助我们持续改进")}</p></div>
    <div class="fb-like-row"><button class="fb-like-btn" id="fb-like-btn"><span id="fb-like-icon">👍</span><span id="fb-like-text">有用</span></button><span class="fb-like-count" id="fb-like-count">0 人觉得很赞</span></div>
    <div class="fb-comments">
      <h4 style="font-size:14px;font-weight:600;margin:0 0 10px;color:var(--text)">💬 评论 (<span id="fb-cmt-count">0</span>)</h4>
      <div class="fb-comment-form"><input type="text" id="fb-name" placeholder="昵称" maxlength="20"><textarea id="fb-text" placeholder="写下您的想法…" rows="2" maxlength="500"></textarea><button id="fb-submit-btn">发布</button></div>
      <div class="fb-comment-list" id="fb-comment-list"><div class="fb-empty">暂无评论，来坐沙发吧 ☕</div></div>
      <div class="fb-loading" id="fb-loading" style="display:none">加载中…</div>
    </div>
  </div>
</section>'''
    
    # Footer
    footer = feedback_html + f'<footer><div class="ft-logo"><img src="media/image2.png" alt="安恒信息" style="height:32px;vertical-align:middle;margin-right:6px;">AI赋能营销</div><p>{g.get("页脚部门","营销中心")} · {g.get("页脚日期","2026年6月")}</p><section class="view-counter"><span class="vc-icon">👁️</span><span>本页已浏览</span><span class="vc-num">99+</span><span>次</span></section></footer>'
    
    title = g.get('页面标题','AI赋能营销 · 营销中心综合管理部')
    return f'<!DOCTYPE html>\n<html lang="zh-CN">\n<head>\n<meta charset="UTF-8">\n<meta name="viewport" content="width=device-width,initial-scale=1.0">\n<title>{title}</title>\n{CSS}\n</head>\n<body>\n<div id="prog"></div>\n\n{nav}\n\n{hero}\n\n{scene_nav}\n\n<div class="scene-timeline">\n{scenes_html}\n</div>\n\n{future_html}\n\n{footer}\n\n{JS}\n</body>\n</html>'


def main():
    from datetime import datetime
    print('='*50)
    print(f'  生成时间：{datetime.now().strftime("%Y-%m-%d %H:%M:%S")}')
    print(f'  读取文件：content.md')
    print('='*50)
    data = parse_content('content.md')
    html = build(data)
    with open('index.html', 'w', encoding='utf-8') as f:
        f.write(html)
    print(f'\n✅ 生成成功！index.html ({len(html):,} 字节)')
    print(f'  Scenes: {len(data["scenes"])}  Apps: {sum(len(s["apps"]) for s in data["scenes"])}  Heroes: {len(data["heroes"])}')
    for s in data['scenes']:
        print(f'  Scene {s["num"]}: {s.get("title","?")} ({len(s["apps"])} apps)')
        for a in s['apps']:
            print(f'    {a.get("title","?")} [video={a.get("video","")} images={len(a.get("images",[]))}]')


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
