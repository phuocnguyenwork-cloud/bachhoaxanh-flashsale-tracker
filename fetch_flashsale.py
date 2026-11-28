#!/usr/bin/env python3
import argparse
import gzip
import json
import ssl
import sys
import time
import urllib.error
import urllib.request
import uuid
from datetime import datetime

try:
    import certifi
    SSL_CTX = ssl.create_default_context(cafile=certifi.where())
except ImportError:
    SSL_CTX = ssl.create_default_context()

BASE = "https://api.bachhoaxanh.com"
REVERSE_HOST = "http://bhxapi.live"  
XAPIKEY = "bhx-api-core-2022"
PLATFORM = "webnew"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/130.0 Safari/537.36")
TIMEOUT = 15
MAX_PAGES = 60  # chốt an toàn khi lật trang


def _headers():
    return {
        "User-Agent": UA,
        "Accept": "application/json",
        "Content-Type": "application/json",
        "ReverseHost": REVERSE_HOST,
        "xapikey": XAPIKEY,
        "platform": PLATFORM,
        "deviceid": str(uuid.uuid4()),
        "customer-id": "",
    }


def http_json(method, path, payload=None, retries=2):
    """Gọi 1 endpoint API. Trả (status, json|None, error|None). Tự động retry khi gặp sự cố mạng tạm thời."""
    url = BASE + path
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    last_err = None

    for attempt in range(retries + 1):
        req = urllib.request.Request(url, data=data, method=method)
        for k, v in _headers().items():
            req.add_header(k, v)
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT, context=SSL_CTX) as resp:
                body = resp.read()
                if resp.headers.get("Content-Encoding") == "gzip":
                    body = gzip.decompress(body)
                text = body.decode("utf-8", errors="replace")
                try:
                    return resp.status, json.loads(text), None
                except json.JSONDecodeError:
                    return resp.status, None, "not-json: " + text[:200]
        except urllib.error.HTTPError as e:
            try:
                text = e.read().decode("utf-8", errors="replace")
                try:
                    return e.code, json.loads(text), None
                except json.JSONDecodeError:
                    return e.code, None, "not-json: " + text[:200]
            except Exception as ex:  # noqa: BLE001
                return e.code, None, str(ex)
        except Exception as ex:  # noqa: BLE001
            last_err = str(ex)
            if attempt < retries:
                time.sleep(1.0)
                continue
            return None, None, last_err


def is_network_error(err):
    """Lỗi tầng mạng (reset/từ chối/hết giờ/DNS) — khác lỗi gateway."""
    if not err:
        return False
    text = str(err).lower()
    markers = ("connection reset", "connectionreset", "connection refused",
               "connection aborted", "remote end closed", "timed out",
               "timeout", "temporary failure", "name or service not known",
               "nodename nor servname", "eof occurred", "broken pipe",
               "forcibly closed", "reset by peer", "winerror 10054",
               "winerror 10060", "winerror 10061")
    return any(m in text for m in markers)


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


def pick_price(prod):
    """Chọn phần tử giá có mức giảm phần trăm sâu nhất trong productPrices.
    Quét toàn bộ các mức giá, chỉ chấp nhận các mức hợp lệ (price <= sysPrice) để tránh
    lỗi dữ liệu lệch đơn vị cân ký của BHX."""
    prices = prod.get("productPrices") or []
    if not prices:
        return None

    best_item = None
    best_pct = 0
    valid_prices = []

    for p in prices:
        if isinstance(p, dict):
            pr = p.get("price")
            spr = p.get("sysPrice")
            if pr is not None and spr is not None:
                try:
                    pr_val, spr_val = float(pr), float(spr)
                    # Chỉ chấp nhận biến thể hợp lệ khi giá bán <= giá gốc và giá gốc > 0
                    if pr_val <= spr_val and spr_val > 0:
                        pct = int(round((spr_val - pr_val) / spr_val * 100))
                        valid_prices.append((pct, pr_val, spr_val, p))
                        if pct > best_pct:
                            best_pct = pct
                            best_item = p
                except (ValueError, TypeError):
                    pass

    # Nếu có biến thể giảm giá (>0%), lấy biến thể giảm sâu nhất
    if best_item is not None:
        pr = best_item.get("price")
        spr = best_item.get("sysPrice")
        source = f"type_{best_item.get('type')}"
        is_can_buy = best_item.get("isCanBuy")
    elif valid_prices:
        # Nếu không có giảm giá, ưu tiên biến thể chuẩn 1kg (netUnitValue == 1 hoặc 0)
        chosen = None
        for pct, pr_val, spr_val, p in valid_prices:
            if p.get("netUnitValue") in (1, 1.0, 0):
                chosen = p
                break
        if chosen is None:
            chosen = valid_prices[0][3]
        pr = chosen.get("price")
        spr = chosen.get("sysPrice")
        best_pct = 0
        source = f"type_{chosen.get('type')}"
        is_can_buy = chosen.get("isCanBuy")
    else:
        # Fallback cuối cùng nếu toàn bộ đều lỗi
        fallback = prices[0] if isinstance(prices[0], dict) else {}
        pr = fallback.get("price")
        spr = fallback.get("sysPrice")
        best_pct = calc_discount_percent(pr, spr)
        source = "fallback"
        is_can_buy = fallback.get("isCanBuy")

    return {"price": pr, "sysPrice": spr,
            "discountPercent": best_pct,
            "isCanBuy": is_can_buy,
            "source": source,
            "all": prices}


def find_crm(obj):
    """Quét đệ quy tìm crmProgramId(s) trong 1 sản phẩm (thường nằm trong
    lstCampaingInfo) — GetCurrentStockFS cần giá trị này."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k.lower() in ("crmprogramids", "crmprogramid") \
                    and isinstance(v, (int, str)) and v:
                return v
        for v in obj.values():
            r = find_crm(v)
            if r is not None:
                return r
    elif isinstance(obj, list):
        for it in obj:
            r = find_crm(it)
            if r is not None:
                return r
    return None


def parse_dt(value):
    try:
        return datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return None


def fetch_timelines(ctx):
    """Bước 1: lấy các ca flash sale trong ngày. Trả (timelines, error)."""
    status, payload, err = http_json(
        "POST", "/game/gw/Home/GetLineTabHome",
        {"LineTabId": [1], "ProvinceId": ctx["ProvinceId"],
         "StoreId": ctx["StoreId"], "WardId": ctx["wardId"], "isNew": True})
    if err:
        return None, err
    if not payload or payload.get("code") != 0:
        return None, f"code={(payload or {}).get('code')} status={status}"
    data = payload.get("data") or {}
    return data.get("lstTimeLineFS") or [], None


def fetch_timeline_products(ctx, timeline_id, page_size, delay):
    """Bước 2: lật trang GetListProductFlashSale cho 1 ca.
    Dừng khi: trang rỗng, đủ totalPage (đọc từ phần tử đầu của trang đầu),
    trang ngắn hơn page_size, hoặc chạm MAX_PAGES."""
    products, page, total_page = [], 0, None
    while True:
        status, payload, err = http_json(
            "POST", "/game/gw/FlashSale/GetListProductFlashSale",
            {"ProvinceId": ctx["ProvinceId"], "StoreId": ctx["StoreId"],
             "wardId": ctx["wardId"], "TimeLineId": timeline_id,
             "PageIndex": page, "PageSize": page_size, "customerId": 0})
        if err:
            return products, err
        if not payload or payload.get("code") != 0:
            return products, f"code={(payload or {}).get('code')} status={status}"
        batch = (payload.get("data") or {}).get("lstProduct") or []
        if total_page is None and batch and isinstance(batch[0], dict):
            tp = batch[0].get("totalPage")
            total_page = tp if isinstance(tp, int) and tp > 0 else None
        products.extend(batch)
        if not batch:
            break
        if total_page is not None and page + 1 >= total_page:
            break
        if len(batch) < page_size:
            break
        page += 1
        if page >= MAX_PAGES:
            break
        time.sleep(delay)
    return products, None


def fetch_stock(ctx, products, delay):
    """Bước 3: số suất còn lại cho các sản phẩm có đủ bộ
    (CrmProgramIds, ProductCode, ProductId). Trả ({productId: remaining}, số đã hỏi)."""
    reqs = []
    for p in products:
        crm = find_crm(p)
        if crm is not None and p.get("productCode") and p.get("id"):
            reqs.append({"CrmProgramIds": crm,
                         "ProductCode": p["productCode"],
                         "ProductId": p["id"]})
    remaining = {}
    for i in range(0, len(reqs), 20):
        chunk = reqs[i:i + 20]
        status, payload, err = http_json(
            "POST", "/gw/FlashSale/GetCurrentStockFS",
            {"LstReqs": chunk, "ProvinceId": ctx["ProvinceId"],
             "StoreId": ctx["StoreId"], "wardId": ctx["wardId"]})
        if payload and payload.get("code") == 0:
            for row in payload.get("data") or []:
                if isinstance(row, dict) and row.get("productId") is not None:
                    remaining[row["productId"]] = row.get("remainingQuantity")
        if i + 20 < len(reqs):
            time.sleep(delay)
    return remaining, len(reqs)


def fmt_money(v):
    if v is None:
        return "?"
    return f"{int(v):,}".replace(",", ".") + "₫"


def main():
    ap = argparse.ArgumentParser(
        description="Lấy danh sách sản phẩm flash sale Bách Hoá XANH qua API")
    ap.add_argument("--province", default="1027", help="ProvinceId (mặc định 1027)")
    ap.add_argument("--store", default="8916", help="StoreId (mặc định 8916)")
    ap.add_argument("--ward", default="100731", help="WardId (mặc định 100731)")
    ap.add_argument("--timeline", type=int, help="Chỉ lấy 1 ca theo timelineId")
    ap.add_argument("--all", action="store_true", help="Lấy mọi ca trong ngày (kể cả ca đã qua)")
    ap.add_argument("--page-size", type=int, default=10, help="Sản phẩm/trang (mặc định 10)")
    ap.add_argument("--no-stock", action="store_true", help="Bỏ qua bước lấy số suất còn lại")
    ap.add_argument("--delay", type=float, default=0.5, help="Giãn cách request, giây (mặc định 0.5)")
    ap.add_argument("--out", help="File JSON đầu ra (mặc định flashsale-<ngày giờ>.json)")
    args = ap.parse_args()

    ctx = {"ProvinceId": int(args.province), "StoreId": int(args.store),
           "wardId": int(args.ward)}

    timelines, err = fetch_timelines(ctx)
    if err:
        if is_network_error(err):
            print("Lỗi tầng mạng (kết nối bị cắt/hết giờ) — không nói lên điều "
                  "gì về API. Chỉ chạy khi trình duyệt trên máy đang mở được "
                  "bachhoaxanh.com bình thường.", file=sys.stderr)
        else:
            print(f"Không lấy được danh sách ca: {err}", file=sys.stderr)
        return 1

    now = None
    for t in timelines:
        dt = parse_dt(t.get("dateStart"))
        if dt is not None:
            now = datetime.now(dt.tzinfo)
            break
    if now is None:
        now = datetime.now().astimezone()

    def classify(t):
        start, end = parse_dt(t.get("dateStart")), parse_dt(t.get("dateEnd"))
        if start is None or end is None:
            return "khong_ro"
        if end <= now:
            return "da_ket_thuc"
        if start > now:
            return "sap_dien_ra"
        return "dang_dien_ra"

    selected = []
    for t in timelines:
        state = classify(t)
        t["_state"] = state
        if args.timeline is not None:
            if t.get("timelineId") == args.timeline:
                selected.append(t)
        elif args.all or state in ("dang_dien_ra", "sap_dien_ra"):
            selected.append(t)
    if not selected:
        print("Không có ca nào phù hợp để lấy.")
        return 0

    output = {"fetched_at": now.isoformat(timespec="seconds"),
              "context": ctx, "timelines": []}
    for t in selected:
        tid = t.get("timelineId")
        print(f"\n=== Ca {tid}: {t.get('dateStart')} -> {t.get('dateEnd')} "
              f"({t['_state']}) ===")
        products, err = fetch_timeline_products(ctx, tid, args.page_size, args.delay)
        if err:
            print(f"  Lỗi khi lấy sản phẩm ca {tid}: {err}", file=sys.stderr)
            if is_network_error(err):
                print("Lỗi tầng mạng — dừng toàn bộ.", file=sys.stderr)
                return 1
            continue
        remaining, asked = ({}, 0)
        if not args.no_stock and products:
            remaining, asked = fetch_stock(ctx, products, args.delay)
        records = []
        for p in products:
            price = pick_price(p)
            rec = {"id": p.get("id"), "name": p.get("name"),
                   "url": p.get("url"), "productCode": p.get("productCode"),
                   "unit": p.get("unit"),
                   "maxQuantityOnBill": p.get("maxQuantityOnBill"),
                   "remainingQuantity": remaining.get(p.get("id")),
                   **({k: price[k] for k in ("price", "sysPrice",
                                             "discountPercent", "isCanBuy",
                                             "source")} if price else {}),
                   "productPrices": p.get("productPrices")}
            records.append(rec)
            stock_txt = (f" | còn {rec['remainingQuantity']} suất"
                         if rec["remainingQuantity"] is not None else "")
            print(f"  - {rec['name']}: {fmt_money(rec.get('price'))}"
                  f" (gốc {fmt_money(rec.get('sysPrice'))}, "
                  f"-{rec.get('discountPercent')}%)"
                  f" | tối đa {rec['maxQuantityOnBill']}/đơn{stock_txt}")
        print(f"  Tổng: {len(records)} sản phẩm"
              + (f", đã hỏi suất còn lại cho {asked} sản phẩm." if asked else "."))
        output["timelines"].append({
            "timelineId": tid, "dateStart": t.get("dateStart"),
            "dateEnd": t.get("dateEnd"), "state": t["_state"],
            "products": records})
        time.sleep(args.delay)

    out_path = args.out or ("flashsale-" + now.strftime("%Y%m%d-%H%M") + ".json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"\nĐã ghi {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
