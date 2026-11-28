# Tool lấy sản phẩm giảm giá bhx:
    Chỉ fetch sản phẩm giảm giá của cả ngày và gửi vào discord. 
    Chức năng tự động đặt hàng và mua cần auth, refresh token nên không đính kèm trong folder này.

---

## Tính năng chính & Tính năng phụ:
1. **Chức năng chính (Flash Sale chung)**: 
   - Tự động lấy tất cả các ca Flash Sale đang và sắp diễn ra trong ngày.
   - Quét mọi biến thể trọng lượng/giá để chọn ra mức giảm sâu nhất.
   - Lọc các sản phẩm có mức giảm $\ge$ ngưỡng `--threshold` (mặc định 40%) và gửi Embeds lên Discord kèm nút bấm đặt hàng trực tiếp.
   - Bỏ qua các ca đã kết thúc và các sản phẩm nằm trong danh sách chặn `IgnoreProd.txt`.

2. **Chức năng phụ (`TargetPrice.txt`)**:
   - Chạy song song độc lập.
   - Cho phép bạn chỉ định các sản phẩm cụ thể và mức giá kỳ vọng mong muốn.
   - Khi chạy, bot quét mọi ca sale trong ngày để tìm chính xác ca nào có giá bán $\le$ giá kỳ vọng của bạn và gửi thêm thông báo riêng.
   - **Lưu ý**: Nếu bạn không điền sản phẩm nào vào `TargetPrice.txt`, bot sẽ chỉ chạy chức năng Flash Sale chính như bình thường.

---

## Cách cấu hình:
### 1. Cấu hình discord webhook vào tool:
   * *Cách 1 :* Mở file `notify_discord.py`, tìm dòng 25 và dán URL webhook vào biến `DEFAULT_WEBHOOK`:
     ```python
     DEFAULT_WEBHOOK = "https://discord.com/api/webhooks/..."
     ```
   * *Cách 2:* Truyền trực tiếp qua dòng lệnh bằng cờ `--webhook`:
     ```bash
     python notify_discord.py --fetch --webhook "https://discord.com/api/webhooks/..."
     ```

---

### 2. Cấu hình mã Tỉnh (`province`), Cửa hàng (`store`), Phường xã (`ward`)
Mặc định tool đang cấu hình sẵn cho khu vực TP.HCM (`province=1027`, `store=8916`, `ward=100731`). Nếu bạn ở khu vực khác hãy lấy mã như sau:

1. Mở trình duyệt và truy cập `https://www.bachhoaxanh.com`.
2. Bấm vào phần **Chọn địa chỉ giao hàng** ở góc trên website và chọn đúng Tỉnh / Quận / Phường của bạn.
3. Nhấn **F12** (hoặc chuột phải chọn *Kiểm tra / Inspect*).
4. Chuyển sang tab **Application (Ứng dụng)** -> menu bên trái chọn **Cookies** -> bấm vào `https://www.bachhoaxanh.com`.
5. Tìm 3 dòng tương ứng:
   * `location_provID`: Mã Tỉnh/Thành
   * `location_storeID`: Mã Cửa hàng / Kho giao hàng gần bạn nhất
   * `location_wardID`: Mã Phường/Xã
   (cookie mặc định lấy địa chỉ được set default)
6. **Truyền vào lệnh chạy:**
   ```bash
   python notify_discord.py --fetch --province <MÃ_TỈNH> --store <MÃ_STORE> --ward <MÃ_PHƯỜNG>
   ```
   *(Hoặc sửa trực tiếp giá trị mặc định ở dòng `ap.add_argument("--province", ...)` trong file `notify_discord.py` để không phải gõ lại mỗi lần).*

---

## Hướng Dẫn Cài Đặt & Chạy

### 1. Chuẩn bị môi trường
```bash
pip install -r requirements.txt
```

### 2. Các câu lệnh chạy chính

* **Chạy quét các ca đang và sắp diễn ra trong ngày & gửi Discord:**
  ```powershell
  python notify_discord.py --fetch
  ```

* **Chạy thử nghiệm (Xem danh sách sản phẩm trên terminal, không gửi Discord):**
  ```powershell
  python notify_discord.py --fetch --dry-run
  ```

* **Chỉ lọc sản phẩm giảm sâu (Ví dụ từ 50% trở lên):**
  ```powershell
  python notify_discord.py --fetch --threshold 50
  ```

---

### 3. Chặn các sản phẩm không muốn nhận thông báo (`IgnoreProd.txt`)
Nếu có sản phẩm bạn không bao giờ muốn mua và không muốn bot gửi thông báo (ví dụ: dưa leo, rau củ lặp lại...):

1. Mở file JSON thu được sau khi fetch (ví dụ `flashsale-xxxxxxxx-xxxx.json`) hoặc xem trực tiếp mã `[ID: ...]` in trên terminal / discord.
2. Mở file **`IgnoreProd.txt`** và dán mã ID vào (mỗi dòng một ID, hoặc cách nhau bằng dấu phẩy).
   ```text
   # Bỏ qua thịt heo xay và dưa leo
   333450
   283165
   ```
3. Khi chạy, tool sẽ tự động đọc file này và bỏ qua toàn bộ sản phẩm có ID trùng khớp.
*(Có thể đổi sang file khác bằng cờ `--ignore-file <duong_dan>`)*.

---

### 4. (Chức năng phụ) Theo dõi sản phẩm theo giá kỳ vọng (`TargetPrice.txt`)
Nếu bạn muốn theo dõi sản phẩm cụ thể và muốn biết **khi nào (ca nào)** sản phẩm đó có giá bán **thấp hơn hoặc bằng** mức bạn mong muốn:

1. Lấy mã ID sản phẩm từ Discord hoặc file JSON (ví dụ ID `333450` là Thịt heo xay).
2. Mở file **`TargetPrice.txt`** và thêm dòng theo cú pháp `<ID_SẢN_PHẨM> : <GIÁ_MONG_MUỐN>`.
   ```text
   # Khi thịt heo xay <= 10.000đ thì báo
   333450: 10.000
   
   # Khi nước điện giải <= 150.000đ thì báo (hỗ trợ viết tắt 150k, 10k, 1.5tr)
   283165: 150k
   ```
3. Khi chạy lệnh fetch, chương trình sẽ:
   * Quét **mọi khung giờ** và **tất cả mức giá có thể có** (tất cả quy cách đóng gói, trọng lượng...) của sản phẩm đó.
   * Gom và hiển thị **đầy đủ mọi ca sale trong ngày** có mức giá $\le$ mức bạn kỳ vọng trong một thông báo duy nhất trên Discord (kèm nút bấm đặt mua nhanh).
   * In chi tiết từng ca trên Terminal.
   * **Báo thức trước giờ mở bán & Chạy liên tục 24/7 (`--alarm` / `--daemon`)**:
     - Chạy 1 ngày (từ lúc bật đến hết các ca trong ngày):
       ```powershell
       python notify_discord.py --fetch --alarm
       ```
     - Chạy **1 lần dùng mãi mãi 24/7** qua các ngày (`--daemon` tự bật `--fetch` và `--alarm`, tự quét lại ngày mới lúc `06:00`):
       ```bash
       nohup ./run.sh --daemon > tracker.log 2>&1 &
       ```
     - **Các tham số cấu hình cho Alarm / Daemon** (dùng được cả cờ CLI hoặc biến môi trường):
       - `--alarm-lead <phút>` (`BHX_ALARM_LEAD`, mặc định `1`): Báo thức trước giờ mở bán bao nhiêu phút (ví dụ `--alarm-lead 2` hoặc `0.5`).
       - `--alarm-mention <tag>` (`BHX_ALARM_MENTION`, mặc định `@everyone`): Tag trên Discord khi báo thức (`@everyone`, `@here`, `none` để tắt tag, hoặc `<@&ROLE_ID>`).
       - `--no-local-alarm` (`BHX_NO_LOCAL_ALARM=1`): Tắt chuông/rung cục bộ trên máy/điện thoại, chỉ gửi Discord.
       - `--daily-at <HH:MM>` (`BHX_DAILY_AT`, mặc định `06:00`): Giờ tự động quét lại cho ngày mới khi bật `--daemon`.
       - `--rescan-hours <giờ>` (`BHX_RESCAN_HOURS`, mặc định `0`): Quét lại mỗi X giờ trong ngày (ví dụ `4`) để cập nhật nếu BHX thêm deal giữa ngày.
*(Nếu file này để trống, chương trình chỉ quét và thông báo Flash Sale chính bình thường)*.

---

### 5. Chạy tự động 24/7 trên Đám mây (GitHub Actions)
Bạn không cần bật máy tính! GitHub Actions sẽ tự động chạy ngầm trên máy chủ GitHub theo lịch trước mỗi ca Flash Sale (07:55, 09:55, 11:55, 13:55, 15:55, 17:55, 19:55, 21:55) và gửi thông báo vào Discord của bạn.

#### Cấu hình Secret (Khuyên dùng để bảo mật Webhook):
1. Vào repo GitHub của bạn: `Settings` -> `Secrets and variables` -> `Actions`.
2. Bấm **New repository secret**.
3. Điền:
   - **Name**: `DISCORD_WEBHOOK`
   - **Secret**: Dán URL Webhook Discord của bạn.
4. Bấm **Add secret**.

#### Kích hoạt thủ công từ điện thoại hoặc máy tính:
- Vào tab **Actions** trên GitHub -> Chọn workflow **BHX FlashSale Tracker** -> Bấm **Run workflow**. Tool sẽ lập tức chạy quét và gửi kết quả về Discord mà không cần mở terminal!
