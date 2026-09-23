@echo off
chcp 65001 >nul
cd /d "%~dp0"
title Vizard Auto-Clip

echo ================================================
echo   VIZARD AUTO-CLIP - dang khoi dong...
echo   (lan dau chay se tu dong tai thu vien, cho chut)
echo ================================================
echo.

REM --- tim Python tren may ---
set "PY="
where py >nul 2>&1 && set "PY=py"
if not defined PY (
  where python >nul 2>&1 && set "PY=python"
)
if not defined PY (
  if exist "%LOCALAPPDATA%\Programs\Python\Python313\python.exe" set "PY=%LOCALAPPDATA%\Programs\Python\Python313\python.exe"
)
if not defined PY (
  if exist "%LOCALAPPDATA%\Programs\Python\Python312\python.exe" set "PY=%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
)

if not defined PY (
  echo [LOI] Khong tim thay Python tren may.
  echo Hay cai Python 3.10+ tai https://www.python.org/downloads/
  echo Nho tich "Add Python to PATH" khi cai.
  echo.
  pause
  exit /b 1
)

echo Dung Python: %PY%
echo.
"%PY%" main.py
echo.
pause
