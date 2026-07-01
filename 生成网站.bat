@echo off
chcp 65001 >nul
echo ==========================================
echo   AI赋能营销网站 - 正在生成...
echo ==========================================
cd /d "%~dp0"

"C:\ProgramData\WorkBuddy\users\d3002b4\.workbuddy\binaries\python\envs\default\Scripts\python.exe" build.py

if %ERRORLEVEL% EQU 0 (
    echo.
    echo ✅ 生成成功！请用浏览器打开 index.html
    echo.
    echo 正在自动打开网站...
    start "" index.html
) else (
    echo.
    echo ❌ 生成失败，请查看上方错误信息
)

echo.
pause
