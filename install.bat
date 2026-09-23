@echo off
chcp 65001 >nul
setlocal EnableDelayedExpansion
color 0A
title Vizard Auto-Clip - Cài đặt tự động

echo ════════════════════════════════════════════════════════════
echo    VIZARD AUTO-CLIP - CÀI ĐẶT TỰ ĐỘNG
echo ════════════════════════════════════════════════════════════
echo.

REM Kiểm tra Python
python --version >nul 2>&1
if errorlevel 1 (
    echo [LỖI] Chưa cài Python!
    echo.
    echo Vui lòng tải Python tại: https://www.python.org/downloads/
    echo Nhớ tích "Add Python to PATH" khi cài.
    echo.
    pause
    exit /b 1
)
echo [✓] Đã có Python

REM Tạo thư mục làm việc
set "INSTALL_DIR=%USERPROFILE%\Desktop\Vizard_Auto_Clip"
if exist "%INSTALL_DIR%" (
    echo.
    echo [!] Thư mục đã tồn tại: %INSTALL_DIR%
    set /p "OVERWRITE=Xóa và cài lại? (y/n): "
    if /i "!OVERWRITE!"=="y" (
        echo Đang xóa thư mục cũ...
        rd /s /q "%INSTALL_DIR%" 2>nul
    ) else (
        echo Hủy cài đặt.
        pause
        exit /b 0
    )
)

echo.
echo ════════════════════════════════════════════════════════════
echo    BƯỚC 1: Tải Portable Git (không cần cài đặt)
echo ════════════════════════════════════════════════════════════
echo.

set "GIT_DIR=%TEMP%\PortableGit"
set "GIT_EXE=%GIT_DIR%\bin\git.exe"

if not exist "%GIT_EXE%" (
    echo Đang tải Git Portable...
    set "GIT_URL=https://github.com/git-for-windows/git/releases/download/v2.47.1.windows.1/PortableGit-2.47.1-64-bit.7z.exe"
    set "GIT_ZIP=%TEMP%\PortableGit.7z.exe"
    
    curl -L -o "!GIT_ZIP!" "!GIT_URL!" 2>nul
    if errorlevel 1 (
        echo [LỖI] Không tải được Git. Kiểm tra kết nối mạng.
        pause
        exit /b 1
    )
    
    echo Đang giải nén Git...
    mkdir "%GIT_DIR%" 2>nul
    "!GIT_ZIP!" -o"%GIT_DIR%" -y >nul 2>&1
    del /f /q "!GIT_ZIP!" 2>nul
)

if not exist "%GIT_EXE%" (
    echo [LỖI] Không tìm thấy git.exe sau khi giải nén.
    pause
    exit /b 1
)
echo [✓] Git sẵn sàng

echo.
echo ════════════════════════════════════════════════════════════
echo    BƯỚC 2: Clone từ GitHub
echo ════════════════════════════════════════════════════════════
echo.

cd /d "%USERPROFILE%\Desktop"
"%GIT_EXE%" clone https://github.com/NaupUuh/Vizard_Auto_Clip.git 2>&1
if errorlevel 1 (
    echo [LỖI] Clone thất bại. Kiểm tra kết nối mạng.
    pause
    exit /b 1
)
echo [✓] Clone thành công

echo.
echo ════════════════════════════════════════════════════════════
echo    BƯỚC 3: Cài đặt thư viện Python
echo ════════════════════════════════════════════════════════════
echo.

cd /d "%INSTALL_DIR%"
python -m pip install --upgrade pip >nul 2>&1
python -m pip install playwright yt-dlp pillow requests >nul 2>&1
python -m playwright install chromium >nul 2>&1
echo [✓] Thư viện đã cài

echo.
echo ════════════════════════════════════════════════════════════
echo    CÀI ĐẶT HOÀN TẤT!
echo ════════════════════════════════════════════════════════════
echo.
echo Tool đã được cài vào: %INSTALL_DIR%
echo.
echo Cách sử dụng:
echo   1. Mở GPM Login (Global) và bật Local API
echo   2. Chạy run.bat trong thư mục Vizard_Auto_Clip
echo   3. Bấm nút "Cập nhật" trong tool để tự kéo bản mới từ GitHub
echo.
echo Nhấn phím bất kỳ để mở tool...
pause >nul

start "" "%INSTALL_DIR%\run.bat"
