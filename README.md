# Vizard Auto-Clip

Công cụ tự động tạo clip highlight từ video bằng [Vizard.ai](https://vizard.ai) thông qua trình duyệt antidetect **GPM Login**. Chạy ẩn danh (không cần đăng nhập Vizard), hỗ trợ nhiều profile / nhiều tab song song, tự che logo Vizard, cắt 2.5s cuối, và tìm video YouTube để lấy highlight.

## Tính năng
- Upload **file video lẻ hoặc cả folder** (tự quét video con).
- Hoặc **tìm kiếm YouTube** theo từ khóa (lọc theo độ dài, hiện lượt view) → chọn video → tự đẩy link qua Vizard.
- Chạy **nhiều profile GPM × nhiều tab** song song cho nhanh.
- Tự **che (làm mờ) logo Vizard** ở 3 vị trí (phải-trên / phải-giữa / trái-giữa), không đụng mặt người.
- Tự **cắt 2.5s cuối** mỗi clip.
- **Chạy ẩn** (đẩy cửa sổ Chrome ra ngoài màn hình) để không vướng khi dùng máy.
- Tự xử lý khi hết credit (đổi profile), treo 98% (tải lại + up lại).
- Tải clip về `AI Vizard/<tên-video>/` ngay trong thư mục nguồn.

## Yêu cầu
- **Windows 10/11**
- **Python 3.10+** — tải tại https://www.python.org/downloads/ (nhớ tích *Add Python to PATH*)
- **GPM Login** (bản Global) đang chạy, bật Local API (`http://localhost:9495`)

Các thư viện khác (playwright, yt-dlp, Pillow, ffmpeg…) **tự động tải** khi chạy lần đầu.

## Cài đặt (máy mới)
```
git clone https://github.com/NaupUuh/Vizard_Auto_Clip.git
cd Vizard_Auto_Clip
run.bat
```
Lần đầu chạy sẽ tự tải thư viện + Chromium + ffmpeg (chờ vài phút).

## Cập nhật bản mới
Bấm nút **"Cập nhật"** trong phần mềm → tự kéo bản mới nhất từ GitHub → đóng và mở lại phần mềm.

Hoặc chạy tay:
```
git pull
```
