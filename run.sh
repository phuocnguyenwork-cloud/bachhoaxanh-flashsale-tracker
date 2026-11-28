#!/data/data/com.termux/files/usr/bin/bash
# run.sh — Script kích hoạt tự động quét Flash Sale BHX trên Termux Android
cd /data/data/com.termux/files/home/bachhoaxanh-flashsale-tracker || exit 1

# Giữ CPU thức trong lúc quét mạng (tránh bị Android tắt ngắt giữa chừng khi tắt màn hình)
if command -v termux-wake-lock >/dev/null 2>&1; then
    termux-wake-lock
    trap 'termux-wake-unlock' EXIT
fi

# Tự động cập nhật code hoặc danh sách IgnoreProd.txt / TargetPrice.txt mới nhất từ GitHub nếu có
git pull --rebase >/dev/null 2>&1

# Chạy tool quét và gửi Discord (truyền thêm --alarm hoặc đặt BHX_ALARM=1 để bật báo thức trước 1 phút)
python notify_discord.py --fetch "$@"
