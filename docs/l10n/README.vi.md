# Investments — Nghiên cứu cá nhân & báo cáo danh mục

**Ngôn ngữ README** · [English](../../README.md) · [繁體中文](README.zh-Hant.md) · [简体中文](README.zh-Hans.md) · [日本語](README.ja.md) · [Tiếng Việt](README.vi.md) · [한국어](README.ko.md)

[README tiếng Anh](../../README.md) ở thư mục gốc là bản chuẩn, luôn được cập nhật. Các bản ngôn ngữ khác chỉ để tiện đọc; khi lệch nghĩa, ưu tiên bản tiếng Anh.

Repo này là workspace cá nhân cho tác nhân nghiên cứu đầu tư AI, gồm:

1. Quy cách tác nhân (cách suy nghĩ và viết).
2. Dữ liệu riêng (danh mục, cài đặt) — không commit git.
3. Báo cáo HTML trong `reports/` — cũng bị bỏ qua git.
4. Mẫu HTML tham chiếu giao diện báo cáo.
5. Hai mẫu Python trong `scripts/`, tác nhân chạy trực tiếp mỗi phiên, không cần viết lại từ đầu phần lấy giá hay dựng HTML.

Tác nhân chạy trong ứng dụng LLM (ví dụ Cowork / Claude). Khi bạn yêu cầu “kiểm tra sức khỏe danh mục”, tác nhân đọc quy cách và dữ liệu, chạy `scripts/fetch_prices.py` lấy giá mới nhất và tỷ giá FX quy đổi tự động qua nguồn phù hợp từng thị trường (theo giới hạn tốc độ và dự phòng trong spec), rồi `scripts/generate_report.py` tạo HTML tự gói trong `reports/`.

## Cấu trúc repo

```
.
├── README.md
├── docs/
│   ├── l10n/
│   ├── portfolio_report_agent_guidelines.md
│   ├── portfolio_report_agent_guidelines/
│   └── holdings_update_agent_guidelines.md
├── AGENTS.md
├── SETTINGS.md
├── SETTINGS.example.md
├── HOLDINGS.md
├── HOLDINGS.md.bak
├── HOLDINGS.example.md
├── scripts/
│   ├── fetch_prices.py
│   ├── generate_report.py
│   └── i18n/
│       ├── report_ui.en.json
│       ├── report_ui.zh-Hant.json
│       └── report_ui.zh-Hans.json
├── .gitignore
└── reports/
    ├── _sample_redesign.html
    └── *_portfolio_report.html
```

## Thiết lập lần đầu

1. Sao chép file mẫu và điền dữ liệu thật:

   ```sh
   cp SETTINGS.example.md SETTINGS.md
   cp HOLDINGS.example.md HOLDINGS.md
   ```

2. Sửa `SETTINGS.md`: ngôn ngữ, phong cách đầu tư, (tuỳ chọn) ngưỡng cảnh báo quy mô vị thế.

3. Sửa `HOLDINGS.md`: bốn ngăn `Long Term`, `Mid Term`, `Short Term`, `Cash Holdings`. Mỗi lô một dòng: `<TICKER>: số lượng @ giá vốn on <YYYY-MM-DD> [<MARKET>]` — ngày mua dùng cho thống kê thời gian nắm; thẻ `[<MARKET>]` cho mã `yfinance` và chuỗi dự phòng. Thẻ thường dùng: `[US]`, `[TW]`, `[TWO]`, `[JP]`, `[HK]`, `[LSE]`, `[crypto]`, `[FX]`, `[cash]`. Bảng đầy đủ trong `HOLDINGS.example.md` và `docs/portfolio_report_agent_guidelines.md` §4.1. Dùng `?` nếu vốn hoặc ngày không rõ — ô liên quan hiển thị `n/a` (các ô không áp dụng dùng `—`).

Các `HOLDINGS*`, `SETTINGS.md` nằm trong `.gitignore` và không bị đẩy lên git.

## Cách dùng tác nhân

**Mô hình:** Để phân tích và báo cáo tốt hơn, nên dùng **ít nhất Claude Sonnet 4.6 (High), hoặc mô hình tương đương/mạnh hơn về suy luận**. Bảng nắm giữ dài, tuân thủ checklist và tổng hợp cần khả năng suy luận đủ — mô hình nhẹ có thể bỏ bước hoặc sót mục.

**Môi trường:** Mở thư mục này trong trợ lý/công cụ coding có đọc file và chạy lệnh — ví dụ **Claude Code**, **OpenAI Codex** (CLI hoặc IDE), **Google Gemini** (CLI hoặc client khác). Không bắt buộc một sản phẩm duy nhất; miễn là áp dụng được `AGENTS.md` và tài liệu trong `docs/` cho repo này.

### 1. Câu hỏi nghiên cứu

Đọc `SETTINGS.md` và `HOLDINGS.md`, theo khung `AGENTS.md` (kết luận trước, cơ bản, định giá, kỹ thuật, rủi ro, kế hoạch, chấm điểm, tổng kết).

### 2. Kiểm tra sức khỏe danh mục

Theo `docs/portfolio_report_agent_guidelines.md` (và các phần được liên kết từ mục lục), tạo một file HTML tự gói trong `reports/`. 11 mục: tóm tắt, bảng điều khiển KPI, bảng vị thế (P/L, popover từng lô), thời gian nắm & nhịp, phơi bày theme/ngành, tin mới, lịch 30 ngày, rủi ro/cơ hội, điều chỉnh gợi ý, việc cần làm, nguồn & lỗ hổng dữ liệu. Có cảnh báo ưu tiên thì hiển thị phía trên.

Tác nhân chạy hai script Python mẫu:

```sh
python scripts/fetch_prices.py --holdings HOLDINGS.md --settings SETTINGS.md --output prices.json

python scripts/generate_report.py \
    --holdings HOLDINGS.md --settings SETTINGS.md \
    --prices prices.json --context report_context.json \
    --output reports/2026-04-28_1330_portfolio_report.html
```

`report_context.json` là lớp biên tập: nhận xét, tin, gợi ý, hành động; không chứa tỷ giá FX thủ công. Dữ liệu FX quy đổi được `scripts/fetch_prices.py` tự động ghi vào `prices.json["_fx"]`; số liệu do script tính tự động.

Nếu `SETTINGS.md` yêu cầu ngôn ngữ không có trong từ điển UI mặc định (`english`, `traditional chinese`, `simplified chinese`), **agent đang chạy** nên dịch `scripts/i18n/report_ui.en.json` sang file JSON overlay tạm và truyền qua `--ui-dict` (hoặc `ui_dictionary` trong context) cho `scripts/generate_report.py`. Trình render không gọi dịch vụ dịch bên ngoài.

### 3. Cập nhật danh mục bằng ngôn tự nhiên

Mô tả giao dịch. Tác nhân sẽ phân tích, hiển thị diff, chờ `yes` rõ ràng, sao lưu `HOLDINGS.md.bak` rồi ghi. Không ghi đè thầm, không bịa dữ liệu. Quy tắc đầy đủ: `docs/holdings_update_agent_guidelines.md`.

## Báo cáo sinh ra

Mẫu tên: `reports/<YYYY-MM-DD>_<HHMM>_portfolio_report.html` — một file, không phụ thuộc tài nguyên ngoài. `scripts/generate_report.py` nạp từ điển UI từ `scripts/i18n/report_ui.en.json`, `report_ui.zh-Hant.json`, `report_ui.zh-Hans.json`; ngôn ngữ khác dùng overlay dịch từ bản tiếng Anh (xem `--ui-dict` ở trên). `reports/_sample_redesign.html` là tham chiếu thiết kế, không xóa; `generate_report.py` đọc CSS từ đó (mặc định `--sample`).

## Sửa quy cách tác nhân

`AGENTS.md`, `docs/portfolio_report_agent_guidelines.md` (và các file được liên kết trong `docs/portfolio_report_agent_guidelines/`), và `docs/holdings_update_agent_guidelines.md` là hợp đồng hành vi. Đổi khi muốn đổi cách suy nghĩ/viết; không đưa dữ liệu cá nhân vào. Sau chỉnh lớn, nên tạo lại một báo cáo kiểm tra.

## Quyền riêng tư

Các tệp cá nhân, báo cáo tạo ra, và artifact chạy `prices.json` / `report_context.json` bị git bỏ qua; chỉ mẫu và quy cách được theo dõi. Khi fork, vị thế thật vẫn ở máy bạn.

## Dữ liệu bên thứ ba, API và giới hạn tốc độ

**Dự án này không sở hữu, vận hành hay bảo đảm** bất kỳ API giá hay FX nào. `scripts/fetch_prices.py` và luồng liên quan có thể dùng endpoint công khai, khóa API tùy chọn trong `SETTINGS.md`, và thư viện như `yfinance` bọc nguồn bên thứ ba. **Bạn phải tuân thủ** điều khoản dịch vụ, chính sách sử dụng chấp nhận được và giới hạn tốc độ của từng nhà cung cấp. Lạm dụng có thể khiến khóa hoặc IP bị giới hạn. Spec có nhịp và fallback nhưng **việc dùng hợp pháp, đúng điều khoản là trách nhiệm của bạn**. Nếu nguồn yêu cầu ghi công, hợp đồng hoặc trả phí, hãy làm theo quy tắc của họ.

## Tuyên bố miễn trừ

Repo và báo cáo chỉ phục vụ nghiên cứu cá nhân, không phải tư vấn tài chính hay lời mời mua bán. Hãy tự xác minh trước khi giao dịch. Tác nhân có thể vẫn sai dù đã nêu khoảng trống dữ liệu.
