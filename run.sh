#!/data/data/com.termux/files/usr/bin/bash
# run.sh — Script kích hoạt tự động quét Flash Sale BHX trên Termux Android
cd /data/data/com.termux/files/home/bachhoaxanh-flashsale-tracker || exit 1

# Tự động cập nhật code hoặc danh sách IgnoreProd.txt / TargetPrice.txt mới nhất từ GitHub nếu có
git pull --rebase >/dev/null 2>&1

# Chạy tool quét và gửi Discord
python notify_discord.py --fetch
