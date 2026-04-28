# Investments — Không gian làm việc nghiên cứu đầu tư AI

**Ngôn ngữ README** · [English](../../README.md) · [繁體中文](README.zh-Hant.md) · [简体中文](README.zh-Hans.md) · [日本語](README.ja.md) · [Tiếng Việt](README.vi.md) · [한국어](README.ko.md)

README tiếng Anh là bản chính thức; các ngôn ngữ khác chỉ là bản dịch để tiện đọc.

Repo này là không gian làm việc cục bộ cho tác nhân nghiên cứu đầu tư AI. Thực tế nó phục vụ ba việc chính:

1. Trả lời câu hỏi nghiên cứu dựa trên cài đặt và danh mục của bạn.
2. Tạo báo cáo danh mục HTML hằng ngày.
3. Cập nhật `HOLDINGS.md` từ chỉ dẫn giao dịch bằng ngôn ngữ tự nhiên.

Phù hợp nhất khi dùng trong môi trường tác nhân có thể đọc file và chạy lệnh như OpenAI Codex, Claude Code, Gemini CLI hoặc công cụ tương tự.

**Mức model:** Để phân tích tin cậy và tuân thủ quy cách của repo (`AGENTS.md`, hướng dẫn báo cáo và danh mục), hãy dùng **Claude Sonnet 4.6** với mức suy luận **High**—hoặc model mới hơn có khả năng tương đương trở lên. Model nhẹ hơn có thể bỏ bước kiểm, đọc sai danh mục hoặc làm nghiên cứu nông hơn.

## Tệp quan trọng

- `AGENTS.md`: quy cách suy nghĩ và viết của tác nhân nghiên cứu
- `SETTINGS.md`: ngôn ngữ, khẩu vị rủi ro, tiền tệ gốc. Chỉ lưu cục bộ
- `HOLDINGS.md`: danh mục của bạn. Chỉ lưu cục bộ
- `docs/portfolio_report_agent_guidelines.md`: quy cách chính của báo cáo; tác nhân còn phải đọc toàn bộ các phần được liên kết trong `docs/portfolio_report_agent_guidelines/`
- `docs/holdings_update_agent_guidelines.md`: quy cách cập nhật danh mục
- `scripts/fetch_prices.py`: script chuẩn lấy giá và FX
- `scripts/generate_report.py`: script chuẩn dựng HTML
- `reports/`: thư mục đầu ra. Chỉ lưu cục bộ

## Thiết lập lần đầu

```sh
cp SETTINGS.example.md SETTINGS.md
cp HOLDINGS.example.md HOLDINGS.md
```

Sau đó:

- Điền `SETTINGS.md`.
- Điền `HOLDINGS.md`.
- Giữ bốn nhóm trong `HOLDINGS.md`: `Long Term`, `Mid Term`, `Short Term`, `Cash Holdings`.
- Mỗi lô một dòng: `<TICKER>: <quantity> shares @ <cost basis> on <YYYY-MM-DD> [<MARKET>]`
- Nếu không rõ giá vốn hoặc ngày mua, dùng `?`.

Thẻ thị trường phổ biến: `[US]`, `[TW]`, `[TWO]`, `[JP]`, `[HK]`, `[LSE]`, `[crypto]`, `[FX]`, `[cash]`

`SETTINGS.md`, `HOLDINGS.md`, `HOLDINGS.md.bak`, báo cáo sinh ra và các artifact chạy thông dụng đều nằm trong `.gitignore`.

## Ba workflow thường dùng

Thông thường chỉ cần yêu cầu tác nhân làm một trong ba việc sau.

### 1. Nghiên cứu

Ví dụ:

- "Phân tích NVDA trong bối cảnh danh mục hiện tại của tôi."
- "Mức phơi bày AI hiện tại của tôi là bao nhiêu?"
- "Có nên giảm vị thế ngắn hạn trước mùa kết quả kinh doanh không?"

Tác nhân sẽ đọc `SETTINGS.md`, `HOLDINGS.md` và trả lời theo `AGENTS.md`.

### 2. Báo cáo danh mục

Ví dụ:

- "Tạo báo cáo sức khỏe danh mục hôm nay."
- "Chạy báo cáo trước giờ mở cửa."

Kết quả là một file HTML tự chứa trong `reports/`.

Tác nhân nên dùng thẳng các script chuẩn, không viết lại quy trình:

```sh
python scripts/fetch_prices.py --holdings HOLDINGS.md --settings SETTINGS.md --output prices.json

python scripts/generate_report.py \
    --holdings HOLDINGS.md --settings SETTINGS.md \
    --prices prices.json --context report_context.json \
    --output reports/2026-04-28_1330_portfolio_report.html
```

Nếu ngôn ngữ báo cáo không phải một trong các từ điển UI tích hợp `english`, `traditional chinese`, `simplified chinese`, tác nhân đang chạy phải dịch `scripts/i18n/report_ui.en.json` thành overlay tạm và truyền qua `--ui-dict`.

### 3. Cập nhật danh mục bằng ngôn ngữ tự nhiên

Ví dụ:

- "Hôm qua tôi mua 30 cổ NVDA ở giá 185 USD."
- "Hôm nay bán 10 cổ TSLA ở giá 400 USD."
- "Sửa lô GOOG tháng 9 năm ngoái thành 70 cổ, không phải 75."

Quy tắc cứng: tác nhân không được ghi `HOLDINGS.md` cho đến khi đã hiển thị kế hoạch phân tích và unified diff, rồi nhận được `yes` rõ ràng từ bạn ngay trong cùng lượt. Trước mỗi lần ghi phải tạo `HOLDINGS.md.bak`.

## Đầu ra báo cáo

Mẫu tên file:

```text
reports/<YYYY-MM-DD>_<HHMM>_portfolio_report.html
```

HTML là file đơn, không phụ thuộc CSS, JS, font hay thư viện biểu đồ bên ngoài.

`reports/_sample_redesign.html` là file tham chiếu giao diện, không xóa.

## Khi muốn đổi hành vi tác nhân

Hãy sửa các file sau:

- `AGENTS.md`
- `docs/portfolio_report_agent_guidelines.md`
- mọi phần được liên kết trong `docs/portfolio_report_agent_guidelines/`
- `docs/holdings_update_agent_guidelines.md`

Không đưa dữ liệu cá nhân vào các file quy cách.

## Quyền riêng tư

Được git theo dõi:

- quy cách tác nhân
- file mẫu
- script Python
- README
- file tham chiếu giao diện

Không được git theo dõi:

- `SETTINGS.md`
- `HOLDINGS.md`
- `HOLDINGS.md.bak`
- báo cáo sinh ra
- artifact chạy phổ biến như `prices.json`, `report_context.json`

## Dữ liệu bên thứ ba

Dự án này không sở hữu hay bảo đảm bất kỳ nguồn dữ liệu giá hoặc FX nào. Luồng lấy giá có thể dùng endpoint công khai, API key tùy chọn và wrapper như `yfinance`. Việc tuân thủ điều khoản, giới hạn tốc độ, yêu cầu ghi nguồn và điều kiện trả phí là trách nhiệm của người dùng.

## Miễn trừ

Repo này chỉ phục vụ nghiên cứu cá nhân, không phải khuyến nghị đầu tư. Hãy tự xác minh các dữ kiện quan trọng trước khi giao dịch.
