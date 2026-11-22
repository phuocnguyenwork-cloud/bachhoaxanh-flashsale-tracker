# Tool lấy sản phẩm giảm giá bhx:
    Chỉ fetch sản phẩm giảm giá của cả ngày và gửi vào discord. 
    Chức năng tự động đặt hàng và mua cần auth, refresh token nên không đính kèm trong folder này.
## Cách cấu hình:
### 1. Cấu hình discord webhook vào tool:
   * *Cách 1 :* Mở file `notify_discord.py`, tìm dòng 25 và dán URL webhook vào biến `DEFAULT_WEBHOOK`:
     ```python
     DEFAULT_WEBHOOK = "https://discord.com/api/webhooks/..."
     ```
   * *Cách 2:* Truyền trực tiếp qua dòng lệnh bằng cờ `--webhook`:
     ```bash
     .\.venv\bin\python.exe notify_discord.py --fetch --webhook "https://discord.com/api/webhooks/..."
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
   .\.venv\bin\python.exe notify_discord.py --fetch --province <MÃ_TỈNH> --store <MÃ_STORE> --ward <MÃ_PHƯỜNG>
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
  .\.venv\bin\python.exe notify_discord.py --fetch
  ```

* **Chạy thử nghiệm (Xem danh sách sản phẩm trên terminal, không gửi Discord):**
  ```powershell
  .\.venv\bin\python.exe notify_discord.py --fetch --dry-run
  ```

* **Chỉ lọc sản phẩm giảm sâu (Ví dụ từ 50% trở lên):**
  ```powershell
  .\.venv\bin\python.exe notify_discord.py --fetch --threshold 50
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

### 4. Theo dõi sản phẩm theo giá kỳ vọng (`TargetPrice.txt`)
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
   * Tìm chính xác **ca sale nào (thời gian nào)** có mức giá $\le$ mức bạn kỳ vọng.
   * In chi tiết trên Terminal và gửi Embed riêng nổi bật màu xanh lá lên Discord kèm nút bấm đặt mua nhanh.
*(Có thể đổi sang file khác bằng cờ `--target-file <duong_dan>`)*.
