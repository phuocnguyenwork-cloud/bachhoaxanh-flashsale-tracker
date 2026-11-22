#!/usr/bin/env python3
"""notify_discord.py — Lọc sản phẩm flash sale BHX giảm >40% và gửi Discord webhook.

Dùng kèm fetch_flashsale.py:
  python fetch_flashsale.py --out flashsale.json
  python notify_discord.py flashsale.json

Hoặc chạy trực tiếp (tự gọi fetch rồi gửi):
  python notify_discord.py --fetch

Tuỳ chọn:
  --threshold <số>   Ngưỡng % giảm giá tối thiểu (mặc định 40)
  --webhook <url>    URL Discord webhook (ghi đè DISCORD_WEBHOOK env)
  --fetch            Chạy fetch_flashsale ngay trước khi lọc
  --province/--store/--ward  Truyền vào fetch khi dùng --fetch
"""
import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone, timedelta

# ─── Cấu hình mặc định ───────────────────────────────────────────────────────
DEFAULT_WEBHOOK = (
    "https://discord.com/api/webhooks/1572254460560801869/"
    "RuoaK1arL0AquKoBPq67_ukHMLiCpzDl9Ftkn2bmXjX6fCt61vSk7pNWiKiB9t-W0hQ-"
)
DEFAULT_THRESHOLD = 40          # % giảm tối thiểu
BHX_BASE_URL = "https://www.bachhoaxanh.com"

# Màu embed Discord theo mức giảm
def discount_color(pct: int) -> int:
    if pct >= 60:
        return 0xE74C3C   # đỏ — cực hot
    if pct >= 50:
        return 0xE67E22   # cam
    return 0xF1C40F       # vàng — 40–49 %


def fmt_money(v):
    if v is None:
        return "?"
    return f"{int(v):,}₫".replace(",", ".")


def calc_discount_percent(price: float | int | None, sys_price: float | int | None) -> int:
    """
    Tính phần trăm giảm giá từ giá bán (price) và giá gốc (sysPrice).
    Công thức: round((sysPrice - price) / sysPrice * 100)
    """
    try:
        if price is not None and sys_price is not None:
            p = float(price)
            sp = float(sys_price)
            if sp > 0 and sp > p:
                return int(round((sp - p) / sp * 100))
    except (ValueError, TypeError, ZeroDivisionError):
        pass
    return 0


def load_ignored_ids(filepath: str = "IgnoreProd.txt") -> set[str]:
    """Đọc danh sách productId cần bỏ qua từ file txt (1 ID/dòng hoặc cách nhau dấu phẩy/khoảng trắng)."""
    ignored = set()
    if not filepath or not os.path.exists(filepath):
        return ignored
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                parts = line.replace(",", " ").split()
                for part in parts:
                    clean = part.strip()
                    if clean:
                        ignored.add(clean)
    except Exception as e:
        print(f"⚠ Lỗi khi đọc file bỏ qua {filepath}: {e}", file=sys.stderr)
    return ignored


def filter_products(data: dict, threshold: int, ignored_ids: set[str] = None) -> list[dict]:
    """Trả list sản phẩm (kèm timeline_info) giảm >= threshold% và không nằm trong ignored_ids."""
    if ignored_ids is None:
        ignored_ids = set()
    hits = []
    now = datetime.now().astimezone()
    for tl in data.get("timelines", []):
        # Bỏ qua các ca đã kết thúc
        if tl.get("state") == "da_ket_thuc":
            continue
        date_end = tl.get("dateEnd")
        if date_end:
            try:
                dt_end = datetime.fromisoformat(date_end)
                if dt_end <= now:
                    continue
            except Exception:
                pass

        tl_info = {
            "timelineId": tl.get("timelineId"),
            "dateStart":  tl.get("dateStart"),
            "dateEnd":    tl.get("dateEnd"),
            "state":      tl.get("state"),
        }
        for p in tl.get("products", []):
            pid = str(p.get("id", "")).strip()
            if pid and pid in ignored_ids:
                continue

            # Quét tất cả các mức giá trong productPrices để tìm mức giảm sâu nhất
            best_price = p.get("price")
            best_sys = p.get("sysPrice")
            best_pct = calc_discount_percent(best_price, best_sys)

            prices = p.get("productPrices") or []
            for pr in prices:
                if isinstance(pr, dict):
                    pr_price = pr.get("price")
                    pr_sys = pr.get("sysPrice")
                    pct = calc_discount_percent(pr_price, pr_sys)
                    if pct > best_pct:
                        best_pct = pct
                        best_price = pr_price
                        best_sys = pr_sys

            if (best_price is None or best_sys is None) and prices and isinstance(prices[0], dict):
                best_price = prices[0].get("price")
                best_sys = prices[0].get("sysPrice")
                best_pct = calc_discount_percent(best_price, best_sys)

            p["price"] = best_price
            p["sysPrice"] = best_sys
            p["discountPercent"] = best_pct

            if best_pct >= threshold:
                hits.append({**p, "_timeline": tl_info})
    # Sắp xếp giảm dần theo discountPercent
    hits.sort(key=lambda x: x.get("discountPercent", 0), reverse=True)
    return hits


def state_label(state: str) -> str:
    return {"dang_dien_ra": "🟢 Đang diễn ra",
            "sap_dien_ra":  "🕐 Sắp diễn ra",
            "da_ket_thuc":  "🔴 Đã kết thúc"}.get(state, state)


def build_embeds(hits: list[dict], fetched_at: str, threshold: int) -> list[dict]:
    """Tạo danh sách embed Discord. Discord giới hạn 10 embed/message."""
    if not hits:
        return []

    embeds = []

    # ── Header embed ──────────────────────────────────────────────────────────
    try:
        dt = datetime.fromisoformat(fetched_at)
        ts = dt.strftime("%H:%M %d/%m/%Y")
    except (TypeError, ValueError):
        ts = fetched_at or "?"

    embeds.append({
        "title": f"Flash Sale BHX — Các sản phẩm giảm ≥{threshold}%",
        "description": (
            f"**{len(hits)} sản phẩm** · 🕒 `{ts}`"
        ),
        "color": 0xE74C3C,
    })

    # ── 1 embed / sản phẩm (tất cả sản phẩm thỏa mãn ngưỡng) ──────────────────
    for p in hits:
        tl  = p.get("_timeline", {})
        pct = p.get("discountPercent", 0)
        url = p.get("url", "")
        full_url = BHX_BASE_URL + url if url.startswith("/") else url or BHX_BASE_URL

        remaining = p.get("remainingQuantity")
        stock_txt = f"**{remaining}** suất" if remaining is not None else "?"

        # Thời gian ca
        def _fmt_time(iso):
            try:
                return datetime.fromisoformat(iso).strftime("%H:%M")
            except Exception:
                return iso or "?"
        time_range = f"{_fmt_time(tl.get('dateStart'))}–{_fmt_time(tl.get('dateEnd'))}"

        pid = p.get("id")
        pid_txt = f"`{pid}`" if pid is not None else "?"

        embeds.append({
            "title": p.get("name", "Sản phẩm"),
            "url":   full_url,
            "color": discount_color(pct),
            "fields": [
                {"name": "💰 Giá sale",    "value": fmt_money(p.get("price")),    "inline": True},
                {"name": "🏷️ Giá gốc",    "value": fmt_money(p.get("sysPrice")), "inline": True},
                {"name": "📉 Giảm",        "value": f"**{pct}%**",               "inline": True},
                {"name": "📦 Số suất",     "value": stock_txt,                   "inline": True},
                {"name": "⏰ Ca sale",      "value": f"{time_range} · {state_label(tl.get('state', ''))}",
                                                                                  "inline": True},
                {"name": "🆔 ID",          "value": pid_txt,                     "inline": True},
            ],
        })

    return embeds


def send_to_discord(webhook_url: str, embeds: list[dict], components: list[dict] = None, content: str = None):
    """Gửi tối đa 10 embed và components (nút bấm) lên Discord. Trả (ok: bool, msg: str)."""
    payload = {
        "embeds": embeds[:10],
    }
    if content:
        payload["content"] = content
    if components:
        payload["components"] = components[:5]
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        webhook_url, data=data, method="POST",
        headers={"Content-Type": "application/json; charset=utf-8",
                 "User-Agent": "BHX-FlashSale-Notifier/1.0"}
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return True, f"HTTP {resp.status}"
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        return False, f"HTTP {e.code}: {body[:300]}"
    except Exception as ex:
        return False, str(ex)


def run_fetch(args) -> str:
    """Chạy fetch_flashsale.py như subprocess, trả path file JSON."""
    import subprocess, tempfile, os
    out = args.out or ("flashsale-" + datetime.now().strftime("%Y%m%d-%H%M") + ".json")
    cmd = [
        sys.executable, "fetch_flashsale.py",
        "--province", str(args.province),
        "--store",    str(args.store),
        "--ward",     str(args.ward),
        "--out",      out,
    ]
    if args.page_size:
        cmd += ["--page-size", str(args.page_size)]
    print("▶ Đang chạy:", " ".join(cmd))
    result = subprocess.run(cmd, capture_output=False)
    if result.returncode != 0:
        print("fetch_flashsale.py trả lỗi, kiểm tra output phía trên.", file=sys.stderr)
        sys.exit(1)
    return out


def main():
    ap = argparse.ArgumentParser(description="Lọc flash sale BHX và gửi Discord")
    ap.add_argument("json_file", nargs="?",
                    help="File JSON từ fetch_flashsale.py (bỏ qua nếu dùng --fetch)")
    ap.add_argument("--fetch",   action="store_true",
                    help="Chạy fetch_flashsale.py trước rồi mới lọc")
    ap.add_argument("--threshold", type=int, default=DEFAULT_THRESHOLD,
                    help=f"Ngưỡng %% giảm tối thiểu (mặc định {DEFAULT_THRESHOLD})")
    ap.add_argument("--webhook", default=DEFAULT_WEBHOOK,
                    help="Discord webhook URL")
    ap.add_argument("--dry-run", action="store_true",
                    help="In ra embed JSON mà không gửi Discord")
    ap.add_argument("--ignore-file", default="IgnoreProd.txt",
                    help="File chứa danh sách ID sản phẩm không muốn gửi (mặc định IgnoreProd.txt)")
    # Các tham số khi --fetch
    ap.add_argument("--province",  default="1027")
    ap.add_argument("--store",     default="8916")
    ap.add_argument("--ward",      default="100731")
    ap.add_argument("--page-size", type=int, default=0)
    ap.add_argument("--out",       help="Tên file JSON khi --fetch")
    args = ap.parse_args()

    # ── Đọc danh sách ID bỏ qua nếu có ───────────────────────────────────────
    ignored_ids = load_ignored_ids(args.ignore_file)
    if ignored_ids:
        print(f"🚫 Đã nạp {len(ignored_ids)} product ID cần bỏ qua từ '{args.ignore_file}'.")

    # ── Bước 1: lấy dữ liệu ──────────────────────────────────────────────────
    if args.fetch:
        json_path = run_fetch(args)
    elif args.json_file:
        json_path = args.json_file
    else:
        ap.error("Cần cung cấp file JSON hoặc dùng --fetch")

    with open(json_path, encoding="utf-8") as f:
        data = json.load(f)

    # ── Bước 2: lọc ──────────────────────────────────────────────────────────
    hits = filter_products(data, args.threshold, ignored_ids=ignored_ids)
    fetched_at = data.get("fetched_at", "")

    print(f"\n✅ Tìm thấy {len(hits)} sản phẩm giảm ≥{args.threshold}%:")
    for p in hits:
        tl = p.get("_timeline", {})
        print(f"  [ID: {p.get('id')}] [{p.get('discountPercent'):3d}%] {p.get('name')} "
              f"| {fmt_money(p.get('price'))} (gốc {fmt_money(p.get('sysPrice'))}) "
              f"| còn {p.get('remainingQuantity')} suất")

    if not hits:
        print("Không có sản phẩm nào đủ điều kiện — không gửi Discord.")
        return 0

    # ── Bước 3: build embed ───────────────────────────────────────────────────
    embeds = build_embeds(hits, fetched_at, args.threshold)

    if args.dry_run:
        print("\n── DRY RUN: payload sẽ gửi Discord ──")
        print(json.dumps({"embeds": embeds}, ensure_ascii=False, indent=2))
        return 0

    # ── Bước 4: gửi (chia batch 10 embed nếu > 10, kèm nút đặt hàng) ─────────
    all_product_embeds = embeds[1:]
    header_embed       = embeds[0]
    batches            = [all_product_embeds[i:i+9] for i in range(0, max(len(all_product_embeds), 1), 9)]
    hit_batches        = [hits[i:i+9] for i in range(0, max(len(hits), 1), 9)]

    target_webhook = args.webhook
    if "?" not in target_webhook:
        target_webhook += "?wait=true"
    elif "wait=true" not in target_webhook:
        target_webhook += "&wait=true"

    for idx, batch in enumerate(batches):
        send_embeds = ([header_embed] + batch) if idx == 0 else batch
        curr_hits   = hit_batches[idx] if idx < len(hit_batches) else []
        start_num   = idx * 9 + 1
        end_num     = start_num + len(curr_hits) - 1

        # Tạo nút Link Button cho từng sản phẩm trong batch
        buttons = []
        for p in curr_hits:
            url = p.get("url", "")
            full_url = BHX_BASE_URL + url if url.startswith("/") else url or BHX_BASE_URL
            raw_name = p.get("name", "Sản phẩm")
            short_name = (raw_name[:26] + "...") if len(raw_name) > 28 else raw_name
            buttons.append({
                "type": 2,        # Button
                "style": 5,       # Link Button (URL)
                "label": f"🛒 Mua: {short_name}",
                "url": full_url
            })

        action_rows = []
        for i in range(0, min(len(buttons), 25), 5):
            action_rows.append({
                "type": 1,
                "components": buttons[i:i+5]
            })

        ok, msg = send_to_discord(target_webhook, send_embeds, components=action_rows)
        status = "✅" if ok else "❌"
        print(f"  Batch {idx+1}/{len(batches)} (SP {start_num}–{end_num}, {len(buttons)} nút đặt hàng): {status} {msg}")
        if not ok:
            return 1

        # if idx < len(batches) - 1:
        #     time.sleep(1.5)

    print(f"\n🎉 Đã gửi {len(hits)} sản phẩm lên Discord!")
    return 0


if __name__ == "__main__":
    sys.exit(main())
