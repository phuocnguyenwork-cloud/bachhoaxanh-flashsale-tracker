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


def parse_money_val(raw: str) -> float | None:
    """Chuyển đổi chuỗi tiền tệ (10000, 10.000, 10k, 1.5tr) thành số float."""
    raw = str(raw).strip().lower().replace("đ", "").replace("₫", "").replace(" ", "")
    if not raw:
        return None
    try:
        multiplier = 1.0
        if raw.endswith("k"):
            multiplier = 1000.0
            raw = raw[:-1]
        elif raw.endswith("tr") or raw.endswith("m"):
            multiplier = 1000000.0
            raw = raw[:-2] if raw.endswith("tr") else raw[:-1]
        raw = raw.replace(".", "").replace(",", "")
        return float(raw) * multiplier
    except (ValueError, TypeError):
        return None


def load_target_prices(filepath: str = "TargetPrice.txt") -> dict[str, float]:
    """Đọc file TargetPrice.txt trả về dict: {product_id: max_target_price}."""
    targets = {}
    if not filepath or not os.path.exists(filepath):
        return targets
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                sep = ":" if ":" in line else ("," if "," in line else None)
                if sep:
                    parts = line.split(sep, 1)
                else:
                    parts = line.split(None, 1)
                if len(parts) == 2:
                    pid = parts[0].strip()
                    val = parse_money_val(parts[1])
                    if pid and val is not None:
                        targets[pid] = val
    except Exception as e:
        print(f"⚠ Lỗi khi đọc file theo dõi giá {filepath}: {e}", file=sys.stderr)
    return targets


def check_target_prices(data: dict, target_prices: dict[str, float], ignored_ids: set[str] = None) -> list[dict]:
    """
    Quét tất cả các khung giờ và mọi mức giá có thể có của sản phẩm trong target_prices.
    Trả về danh sách các thời điểm (ca sale) có giá <= giá mong muốn.
    """
    if not target_prices:
        return []
    if ignored_ids is None:
        ignored_ids = set()

    hits = []
    now = datetime.now().astimezone()

    for tl in data.get("timelines", []):
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
            if not pid or pid in ignored_ids or pid not in target_prices:
                continue

            target_max = target_prices[pid]
            matching_prices = []

            # Quét tất cả các mức giá trong productPrices
            prices = p.get("productPrices") or []
            for pr in prices:
                if isinstance(pr, dict):
                    pr_price = pr.get("price")
                    if pr_price is not None:
                        try:
                            val = float(pr_price)
                            if val <= target_max:
                                matching_prices.append((val, pr.get("sysPrice")))
                        except (ValueError, TypeError):
                            pass

            top_price = p.get("price")
            if top_price is not None:
                try:
                    val = float(top_price)
                    if val <= target_max:
                        matching_prices.append((val, p.get("sysPrice")))
                except (ValueError, TypeError):
                    pass

            if matching_prices:
                best_actual, best_sys = min(matching_prices, key=lambda x: x[0])
                pct = calc_discount_percent(best_actual, best_sys)
                hits.append({
                    **p,
                    "price": best_actual,
                    "sysPrice": best_sys,
                    "discountPercent": pct,
                    "target_price": target_max,
                    "_timeline": tl_info,
                })

    hits.sort(key=lambda x: (x.get("_timeline", {}).get("timelineId", 0), x.get("price", 0)))
    return hits


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
        "title": f"🔥 Flash Sale BHX — Giảm ≥{threshold}%",
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


def build_target_embeds(target_hits: list[dict], fetched_at: str) -> list[dict]:
    """Tạo danh sách embed Discord cho các sản phẩm đạt mức giá kỳ vọng (Target Price)."""
    if not target_hits:
        return []

    try:
        dt = datetime.fromisoformat(fetched_at)
        ts = dt.strftime("%H:%M %d/%m/%Y")
    except (TypeError, ValueError):
        ts = fetched_at or "?"

    embeds = [{
        "title": "🎯 Flash Sale BHX — Sản Phẩm Đạt Giá Kỳ Vọng!",
        "description": (
            f"Phát hiện **{len(target_hits)} thời điểm** có giá bán ≤ mức mong muốn!\n"
            f"🕒 Cập nhật lúc: `{ts}`"
        ),
        "color": 0x2ECC71,  # Màu xanh lá
    }]

    for p in target_hits:
        tl  = p.get("_timeline", {})
        pct = p.get("discountPercent", 0)
        url = p.get("url", "")
        full_url = BHX_BASE_URL + url if url.startswith("/") else url or BHX_BASE_URL

        remaining = p.get("remainingQuantity")
        stock_txt = f"**{remaining}** suất" if remaining is not None else "?"

        def _fmt_time(iso):
            try:
                return datetime.fromisoformat(iso).strftime("%H:%M")
            except Exception:
                return iso or "?"
        time_range = f"{_fmt_time(tl.get('dateStart'))}–{_fmt_time(tl.get('dateEnd'))}"

        pid = p.get("id")
        pid_txt = f"`{pid}`" if pid is not None else "?"

        embeds.append({
            "title": f"🎯 {p.get('name', 'Sản phẩm')}",
            "url":   full_url,
            "color": 0x2ECC71,
            "fields": [
                {"name": "🎯 Giá kỳ vọng",  "value": f"≤ **{fmt_money(p.get('target_price'))}**", "inline": True},
                {"name": "💰 Giá thực tế",   "value": f"**{fmt_money(p.get('price'))}**",          "inline": True},
                {"name": "📉 Giảm",          "value": f"**{pct}%** (gốc {fmt_money(p.get('sysPrice'))})", "inline": True},
                {"name": "⏰ Khi nào (Ca sale)", "value": f"{time_range} (Ca {tl.get('timelineId', '?')}) · {state_label(tl.get('state', ''))}", "inline": True},
                {"name": "📦 Số suất",      "value": stock_txt,                                   "inline": True},
                {"name": "🆔 ID",           "value": pid_txt,                                     "inline": True},
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


def send_hits_to_discord(hits: list[dict], embeds: list[dict], webhook_url: str, batch_title: str = "") -> bool:
    """Gửi các batch embeds và buttons lên Discord."""
    if not hits or not embeds:
        return True
    all_product_embeds = embeds[1:]
    header_embed       = embeds[0]
    batches            = [all_product_embeds[i:i+9] for i in range(0, max(len(all_product_embeds), 1), 9)]
    hit_batches        = [hits[i:i+9] for i in range(0, max(len(hits), 1), 9)]

    target_webhook = webhook_url
    if "?" not in target_webhook:
        target_webhook += "?wait=true"
    elif "wait=true" not in target_webhook:
        target_webhook += "&wait=true"

    for idx, batch in enumerate(batches):
        send_embeds = ([header_embed] + batch) if idx == 0 else batch
        curr_hits   = hit_batches[idx] if idx < len(hit_batches) else []
        start_num   = idx * 9 + 1
        end_num     = start_num + len(curr_hits) - 1

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
        prefix = f"[{batch_title}] " if batch_title else ""
        print(f"  {prefix}Batch {idx+1}/{len(batches)} (SP {start_num}–{end_num}, {len(buttons)} nút đặt hàng): {status} {msg}")
        if not ok:
            return False

    return True


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
    ap.add_argument("--target-file", default="TargetPrice.txt",
                    help="File chứa danh sách ID sản phẩm và giá kỳ vọng (mặc định TargetPrice.txt)")
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

    # ── Đọc danh sách giá kỳ vọng nếu có (Chức năng phụ) ─────────────────────
    target_prices = load_target_prices(args.target_file)
    if target_prices:
        print(f"🎯 [Chức năng phụ] Đã nạp {len(target_prices)} sản phẩm theo dõi giá kỳ vọng từ '{args.target_file}'.")

    # ── Bước 1: lấy dữ liệu ──────────────────────────────────────────────────
    if args.fetch:
        json_path = run_fetch(args)
    elif args.json_file:
        json_path = args.json_file
    else:
        ap.error("Cần cung cấp file JSON hoặc dùng --fetch")

    with open(json_path, encoding="utf-8") as f:
        data = json.load(f)
    fetched_at = data.get("fetched_at", "")

    # ── Bước 2 (CHỨC NĂNG CHÍNH): Lọc sản phẩm flash sale chung (≥ threshold%) ──
    hits = filter_products(data, args.threshold, ignored_ids=ignored_ids)

    print(f"\n🔥 [Chức năng chính] Tìm thấy {len(hits)} sản phẩm Flash Sale giảm ≥{args.threshold}%:")
    for p in hits:
        tl = p.get("_timeline", {})
        print(f"  [ID: {p.get('id')}] [{p.get('discountPercent'):3d}%] {p.get('name')} "
              f"| {fmt_money(p.get('price'))} (gốc {fmt_money(p.get('sysPrice'))}) "
              f"| còn {p.get('remainingQuantity')} suất")

    # ── Bước 3 (CHỨC NĂNG PHỤ): Kiểm tra giá kỳ vọng (Target Price) ──────────
    target_hits = []
    if target_prices:
        target_hits = check_target_prices(data, target_prices, ignored_ids=ignored_ids)
        if target_hits:
            print(f"\n🎯 [Chức năng phụ] TÌM THẤY {len(target_hits)} THỜI ĐIỂM ĐẠT GIÁ KỲ VỌNG:")
            for th in target_hits:
                tl = th.get("_timeline", {})
                t_start = (tl.get('dateStart') or '')[11:16]
                t_end = (tl.get('dateEnd') or '')[11:16]
                t_range = f"{t_start}–{t_end}" if t_start and t_end else "Trong ngày"
                print(f"  • [ID: {th.get('id')}] {th.get('name')}")
                print(f"    -> Giá sale: {fmt_money(th.get('price'))} (Kỳ vọng: ≤ {fmt_money(th.get('target_price'))}, giảm {th.get('discountPercent')}%)")
                print(f"    -> Khi nào: Ca {tl.get('timelineId', '?')} ({t_range}) · {state_label(tl.get('state', ''))}")
        else:
            print(f"\nℹ [Chức năng phụ] Rà soát {len(target_prices)} sản phẩm theo dõi: Chưa có ca nào đạt giá kỳ vọng.")

    if not hits and not target_hits:
        print("\nKhông có sản phẩm nào đủ điều kiện — không gửi Discord.")
        return 0

    # ── Bước 4: build embeds ──────────────────────────────────────────────────
    general_embeds = build_embeds(hits, fetched_at, args.threshold)
    target_embeds = build_target_embeds(target_hits, fetched_at)

    if args.dry_run:
        print("\n── DRY RUN: payload sẽ gửi Discord ──")
        if general_embeds:
            print("\n--- 🔥 Embeds Flash Sale Chung (Chính) ---")
            print(json.dumps({"embeds": general_embeds}, ensure_ascii=False, indent=2))
        if target_embeds:
            print("\n--- 🎯 Embeds Mục Tiêu Đạt Giá Kỳ Vọng (Phụ) ---")
            print(json.dumps({"embeds": target_embeds}, ensure_ascii=False, indent=2))
        return 0

    # ── Bước 5: gửi Discord ───────────────────────────────────────────────────
    # Ưu tiên gửi chức năng chính: Flash Sale giảm sâu
    if hits and general_embeds:
        print(f"\n▶ Đang gửi {len(hits)} sản phẩm Flash Sale chính lên Discord...")
        send_hits_to_discord(hits, general_embeds, args.webhook, batch_title="FlashSale")

    # Gửi bổ sung chức năng phụ nếu có sản phẩm đạt kỳ vọng
    if target_hits and target_embeds:
        print(f"\n▶ Đang gửi {len(target_hits)} sản phẩm đạt giá kỳ vọng (phụ) lên Discord...")
        send_hits_to_discord(target_hits, target_embeds, args.webhook, batch_title="Mục tiêu")

    total_sent = len(hits) + len(target_hits)
    print(f"\n🎉 Đã hoàn thành thông báo lên Discord (Tổng cộng {total_sent} lượt sản phẩm)!")
    return 0


if __name__ == "__main__":
    sys.exit(main())
