@echo off
cd /d "%~dp0"
where py >nul 2>nul
if errorlevel 1 (
  python article_vocab.py
) else (
  py -3 article_vocab.py
)
if errorlevel 1 pause
