"""
监控 content.md 变动 → 自动重建 index.html
双击 启动监测.bat 即可，保存 md 后浏览器刷新即可看到最新效果。
"""
import os, time, subprocess, sys

DIR = os.path.dirname(os.path.abspath(__file__))
MD_FILE = os.path.join(DIR, 'content.md')
PYTHON = r'C:\ProgramData\WorkBuddy\users\d3002b4\.workbuddy\binaries\python\envs\default\Scripts\python.exe'
BUILD_SCRIPT = os.path.join(DIR, 'build.py')

print('=' * 50)
print('  🔍 监测中: content.md')
print(f'  📂 {DIR}')
print('  保存 content.md 后自动生成 index.html')
print('  关闭此窗口即停止监测')
print('=' * 50)

last_mtime = 0

while True:
    try:
        current_mtime = os.path.getmtime(MD_FILE)
    except OSError:
        time.sleep(1)
        continue

    if current_mtime != last_mtime:
        if last_mtime != 0:
            print(f'\n🔄 {time.strftime("%H:%M:%S")} content.md 已改动 → 重新生成...')
            try:
                subprocess.run([PYTHON, BUILD_SCRIPT], cwd=DIR, check=True,
                              stdin=subprocess.DEVNULL, capture_output=True, text=True)
                print('✅ 生成完毕！刷新浏览器即可查看')
            except subprocess.CalledProcessError as e:
                print(f'❌ 生成失败: {e.stderr}')
        last_mtime = current_mtime

    time.sleep(0.5)
