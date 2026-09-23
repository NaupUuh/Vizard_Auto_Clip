# Vizard Auto-Clip v1.1.0

Công cụ tự động tạo clip highlight từ video bằng [Vizard.ai](https://vizard.ai) thông qua trình duyệt antidetect **GPM Login**. Chạy ẩn danh (không cần đăng nhập Vizard), hỗ trợ nhiều profile / nhiều tab song song, tự che logo Vizard, cắt 2.5s cuối, và tìm video YouTube để lấy highlight.

## Tính năng
- Upload **file video lẻ hoặc cả folder** (tự quét video con).
- Hoặc **tìm kiếm YouTube** theo từ khóa (lọc theo độ dài, hiện lượt view) → chọn video → tự đẩy link qua Vizard.
- Chạy **nhiều profile GPM × nhiều tab** song song cho nhanh.
- Tự **che (làm mờ) logo Vizard** ở 3 vị trí (phải-trên / phải-giữa / trái-giữa), không đụng mặt người.
- Tự **cắt 2.5s cuối** mỗi clip.
- **Chạy ẩn** (đẩy cửa sổ Chrome ra ngoài màn hình) để không vướng khi dùng máy.
- Tự xử lý khi hết credit (đổi profile), treo 98% (reload + tiếp tục).
- **Gộp output phẳng**: tất cả clip của 1 bộ phim (nhiều tập) → 1 folder `AI Vizard/<tên-bộ-phim>/`, không chia theo tập.
- **Tự cập nhật** từ GitHub bằng nút trong tool.

## Yêu cầu
- **Windows 10/11**
- **Python 3.10+** — tải tại https://www.python.org/downloads/ (nhớ tích *Add Python to PATH*)
- **GPM Login** (bản Global) đang chạy, bật Local API (`http://localhost:9495`)

## Cài đặt

### Máy mới (chưa có gì)

**Bước 1:** Tải file `install.bat` từ repo:
- Vào https://github.com/NaupUuh/Vizard_Auto_Clip
- Bấm **Code** → **Download ZIP**
- Giải nén, tìm file `install.bat`

**Bước 2:** **Click phải** `install.bat` → **"Run as administrator"**
- Script tự tải portable git (không cần cài)
- Clone repo về Desktop
- Cài thư viện Python + Chromium
- Mở tool

**Bước 3:** Xong! Từ giờ:
- Chạy tool: bấm `run.bat` trong thư mục `Vizard_Auto_Clip`
- Cập nhật: bấm nút **"Cập nhật"** trong tool → đóng mở lại

---

### Máy đã có git

```bash
git clone https://github.com/NaupUuh/Vizard_Auto_Clip.git
cd Vizard_Auto_Clip
run.bat
```

Lần đầu chạy sẽ tự tải thư viện + Chromium (chờ vài phút).

## Cập nhật bản mới

Bấm nút **"Cập nhật"** trong phần mềm → tự kéo bản mới nhất từ GitHub → đóng và mở lại tool.

Hoặc chạy tay (trong thư mục tool):
```bash
git pull
```

## Cấu trúc output mới (v1.1.0)

**Chạy 1 video:**
```
Video_nguon.mp4
AI Vizard/
  Video_nguon/
    clip1.mp4
    clip2.mp4
```

**Chạy cả folder (nhiều bộ phim):**
```
Folder_cha/           ← chọn đây
  Phim_A/
    001.mp4
    002.mp4
  Phim_B/
    001.mp4
  AI Vizard/          ← gộp chung 1 chỗ
    Phim_A/           ← tất cả clip của 001+002 gộp vào đây
      clip1.mp4
      clip2.mp4
      clip3.mp4
    Phim_B/
      clip1.mp4
```

## Lưu ý

- **Nút "Cập nhật"** chỉ chạy nếu tool được cài qua `install.bat` hoặc `git clone` (có thư mục `.git`). 
- Nếu tải kiểu ZIP thủ công → không tự update được, phải tải lại ZIP mới.
- `state.json` (cấu hình riêng từng máy) đã được `.gitignore` loại ra → update không đè mất cấu hình.

## Changelog

### v1.1.0 (2026-09-23)
- **Download mới**: bỏ `expect_download`, để Chrome tự tải, tool chờ file xuất hiện trong Downloads rồi move vào đích (fix timeout 45s).
- **Tiến độ theo bước**: log hiển thị `buoc 3/6: Xu ly video` thay vì % nhảy loạn; tự reload khi treo >180s.
- **Flatten output**: gộp tất cả clip của 1 bộ phim (nhiều tập) vào `AI Vizard/<tên-folder-con>/`, không chia theo tập nữa.

### v1.0.0 (2026-09-22)
- Phiên bản đầu tiên
