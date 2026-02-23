@echo off
cd /d "%~dp0"

:: venv があればその python を使う（activate 不要）
if exist venv\Scripts\python.exe (
    venv\Scripts\python.exe main.py
) else (
    python main.py
)
