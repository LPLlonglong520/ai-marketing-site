@echo off
chcp 65001 >nul
title 监测中 - content.md → index.html
C:\ProgramData\WorkBuddy\users\d3002b4\.workbuddy\binaries\python\envs\default\Scripts\python.exe "%~dp0watch.py"
pause
