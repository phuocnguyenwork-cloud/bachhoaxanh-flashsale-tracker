#!/data/data/com.termux/files/usr/bin/bash
# run.sh — Script kích hoạt tự động quét Flash Sale BHX trên Termux Android
cd /data/data/com.termux/files/home/bachhoaxanh-flashsale-tracker || exit 1
python notify_discord.py --fetch
