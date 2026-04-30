# Tác nhân nghiên cứu đầu tư

**Ngôn ngữ README** · [English](../../README.md) · [繁體中文](README.zh-Hant.md) · [简体中文](README.zh-Hans.md) · [日本語](README.ja.md) · [Tiếng Việt](README.vi.md) · [한국어](README.ko.md)

README tiếng Anh là bản chính thức; các ngôn ngữ khác chỉ là bản dịch để tiện đọc.

Repo này là không gian làm việc cục bộ cho tác nhân nghiên cứu đầu tư AI. Thực tế nó phục vụ ba việc chính:

1. Trả lời câu hỏi nghiên cứu dựa trên cài đặt và lịch sử giao dịch của bạn.
2. Tạo báo cáo danh mục HTML hằng ngày.
3. Ghi các giao dịch mới (BUY / SELL / DEPOSIT / WITHDRAW / DIVIDEND / FEE / FX_CONVERT) từ tin nhắn ngôn ngữ tự nhiên, CSV hoặc file JSON vào cơ sở dữ liệu SQLite cục bộ.

Phù hợp nhất khi dùng trong môi trường tác nhân có thể đọc file và chạy lệnh như OpenAI Codex, Claude Code, Gemini CLI hoặc công cụ tương tự.

**Tầng model:** Để phân tích đáng tin cậy và tuân thủ hợp đồng của repo (`AGENTS.md`, hướng dẫn báo cáo và giao dịch), hãy dùng **Claude Sonnet 4.6** với mức suy luận **High**—hoặc tầng model mới hơn có khả năng tương đương trở lên. Model nhẹ hơn có thể bỏ bước kiểm, đọc sai giao dịch hoặc làm nghiên cứu nông hơn.

## Tệp quan trọng

- `AGENTS.md`: quy cách suy nghĩ và viết của tác nhân nghiên cứu
- `SETTINGS.md`: ngôn ngữ, toàn bộ `Investment Style And Strategy`, tiền tệ gốc và giới hạn vị thế. Chỉ lưu cục bộ
- `transactions.db`: SQLite cục bộ cho mọi giao dịch (mua/bán, nạp/rút, cổ tức, phí, đổi FX) kèm lý do và thẻ. Hai bảng phái sinh (`open_lots`, `cash_balances`) tự dựng lại sau mỗi lần INSERT và là khung vị thế mở dự kiến.**Điều khiển P&L đã thực hiện, P&L chưa thực hiện và bảng lợi nhuận.** Chỉ lưu cục bộ. Xem `docs/transactions_agent_guidelines.md`.
- `docs/portfolio_report_agent_guidelines.md`: hợp đồng báo cáo, gồm bao phủ tin tức/sự kiện đầy đủ, Strategy readout và reviewer pass; tác nhân còn phải đọc toàn bộ các phần được liên kết trong `docs/portfolio_report_agent_guidelines/`
- `docs/transactions_agent_guidelines.md`: hợp đồng sổ cái giao dịch duy nhất—lược đồ DB, luồng parse → plan → confirm → write bằng ngôn ngữ tự nhiên, đường nhập CSV/JSON/tin nhắn, khớp lot, bảng lợi nhuận, di chuyển dữ liệu
- `scripts/fetch_prices.py`: script chuẩn lấy giá và FX mới nhất. Đọc vị thế từ `transactions.db`
- `scripts/fetch_history.py`: script đồng hành lấy lịch sử đóng cửa và FX (phục vụ bảng lợi nhuận; ghi `_history` / `_fx_history` vào prices.json). Đọc vị thế từ `transactions.db`
- `scripts/transactions.py`: lưu SQLite + nhập (CSV/JSON/tin nhắn), engine phát lại, dựng lại số dư, P&L đã thực hiện + chưa thực hiện, bảng lợi nhuận cho 1D / 7D / MTD / 1M / YTD / 1Y / ALLTIME
- `scripts/generate_report.py`: script chuẩn dựng HTML; tiêu thụ `strategy_readout`, `reviewer_pass`, `profit_panel`, `realized_unrealized` từ `report_context.json`. Đọc vị thế từ `transactions.db`
- `reports/`: thư mục đầu ra. Chỉ lưu cục bộ

## Thiết lập lần đầu

```sh
cp SETTINGS.example.md SETTINGS.md
python scripts/transactions.py db init        # tạo transactions.db
```

Sau đó chọn một trong các hướng:

- **Khởi động từ `HOLDINGS.md` có sẵn** (người dùng iteration-2):

  ```sh
  python scripts/transactions.py migrate --holdings HOLDINGS.md
  python scripts/transactions.py verify
  rm HOLDINGS.md HOLDINGS.md.bak HOLDINGS.example.md
  ```

  `migrate` tổng hợp một BUY cho mỗi lot hiện có và một DEPOSIT cho mỗi loại tiền mặt, sao cho dựng lại số dư khớp dữ liệu bạn đã gieo. Sau khi verify thành công, các file markdown trên không còn cần thiết.

- **Hoặc nhập sao kê nhà môi giới** (CSV hoặc JSON):

  ```sh
  python scripts/transactions.py db import-csv --input statements/2026-04-schwab.csv
  python scripts/transactions.py db import-json --input transactions.json
  ```

- **Hoặc** đưa từng giao dịch cho tác nhân bằng tiếng Anh đơn giản (ví dụ: "bought 30 NVDA at $185 yesterday"). Tác nhân phân tích, hiển thị JSON chuẩn, và sau `yes` chạy `db add`. Xem `docs/transactions_agent_guidelines.md` §3.

Sau mỗi lần ghi, chạy `python scripts/transactions.py verify` để xác nhận các bảng vật lý `open_lots` + `cash_balances` khớp phát lại toàn bộ nhật ký.

`SETTINGS.md`, `transactions.db`, báo cáo sinh ra và file thời chạy (`prices.json`, `report_context.json`, `temp/`) đều nằm trong `.gitignore`.

### Cách dùng `SETTINGS.md` và `transactions.db`

- Cập nhật `SETTINGS.md` mỗi khi bạn đổi ngôn ngữ ưa thích, chiến lược đầu tư đầy đủ, tiền tệ gốc, giới hạn vị thế hoặc mặc định báo cáo.
- Viết toàn bộ phần `Investment Style And Strategy` như kiểu nhà đầu tư bạn muốn tác nhân nhập vai: tính khí, khả năng chịu drawdown, cách sizing, thời gian nắm giữ, kỷ luật vào lệnh, mức chấp nhận đi ngược đồng thuận, mức chịu hype, vùng cấm và phong cách ra quyết định.
- Coi `transactions.db` là nguồn sự thật duy nhất cho vị thế và tiền mặt hiện tại; mọi luồng mới đi qua tác nhân hoặc nhập CSV/JSON; khung phái sinh `open_lots` + `cash_balances` tự cập nhật.
- Sau mỗi giao dịch đã khớp lệnh, yêu cầu tác nhân ghi sổ ngay để phân tích chính xác.
- Trước khi tạo báo cáo, rà nhanh `SETTINGS.md` và chạy `transactions.py db stats` để phát hiện dữ liệu cũ.

## Ba workflow thường dùng

Thông thường chỉ cần yêu cầu tác nhân làm một trong ba việc sau.

### 1. Nghiên cứu

Ví dụ:

- "Phân tích NVDA trong bối cảnh danh mục hiện tại của tôi."
- "Mức phơi bày AI hiện tại của tôi là bao nhiêu?"
- "Có nên giảm vị thế ngắn hạn trước mùa kết quả kinh doanh không?"

Tác nhân đọc toàn bộ `Investment Style And Strategy` trong `SETTINGS.md`, tải vị thế từ `transactions.db` (`open_lots` + `cash_balances`), rồi trả lời theo `AGENTS.md` ở ngôi thứ nhất theo chiến lược của bạn.

### 2. Báo cáo danh mục

Ví dụ:

- "Tạo báo cáo sức khỏe danh mục hôm nay."
- "Chạy báo cáo trước giờ mở cửa."

Kết quả là một file HTML tự chứa trong `reports/`.

Với `auto mode`, `routine`, hoặc bất kỳ môi trường không giám sát nào khác, nên để tác nhân xin sự đồng ý rõ ràng trước khi gửi mã ticker danh mục của bạn tới nguồn dữ liệu thị trường bên ngoài để lấy giá. Ví dụ câu đồng ý rõ ràng: `Tôi đồng ý cho bạn gửi mã ticker danh mục của tôi tới các nguồn dữ liệu thị trường bên ngoài để lấy giá và tạo báo cáo hôm nay.` Bản tiếng Anh là: `I agree to let you send my holdings tickers to external market data sources to retrieve prices and generate today's report.`

Một lần chạy báo cáo đầy đủ có bốn pha: Gather để thu thập dữ liệu; Think chỉ sau khi giá, chỉ số, tin tức và sự kiện đã có đủ; Review với vai trò PM cấp cao trước khi render; rồi Render. Pha Gather phải tìm tin tức mới và sự kiện 30 ngày tới cho mọi vị thế không phải tiền mặt, không chỉ các vị thế lớn nhất. Pha Review chỉ thêm ghi chú phản biện khi hữu ích, không thay thế nội dung phân tích của bạn.

Tác nhân nên dùng thẳng các script chuẩn, không viết lại quy trình. Cả ba đều tự đọc vị thế từ `transactions.db`.

```sh
python scripts/fetch_prices.py --settings SETTINGS.md --output prices.json
# Nếu còn dòng nào có agent_web_search:TODO_required, fetch_prices sẽ thoát với mã khác 0.
# Phải hoàn tất fallback giá tier 3 / tier 4 trước khi render.

# Bắt buộc cho bảng lợi nhuận: lấy đóng cửa theo ngày + lịch sử FX
python scripts/fetch_history.py \
    --settings SETTINGS.md \
    --merge-into prices.json --output prices_history.json

# Ảnh chụp P&L đã thực hiện + chưa thực hiện trọn đời
python scripts/transactions.py pnl \
    --prices prices.json --settings SETTINGS.md \
    > realized_unrealized.json

# Bảng lợi nhuận theo kỳ (1D / 7D / MTD / 1M / YTD / 1Y / ALLTIME)
python scripts/transactions.py profit-panel \
    --prices prices.json \
    --settings SETTINGS.md --output profit_panel.json

# Trước khi render, gộp profit_panel.json + realized_unrealized.json
# vào report_context.json dưới khóa "profit_panel" và "realized_unrealized".

python scripts/generate_report.py \
    --settings SETTINGS.md \
    --prices prices.json --context report_context.json \
    --output reports/2026-04-28_1330_portfolio_report.html
```

Nếu ngôn ngữ báo cáo không phải một trong các từ điển UI tích hợp `english`, `traditional chinese`, `simplified chinese`, tác nhân đang chạy phải dịch `scripts/i18n/report_ui.en.json` thành overlay tạm và truyền qua `--ui-dict`.

`report_context.json` có thể chứa `strategy_readout` cho Strategy readout ở ngôi thứ nhất và `reviewer_pass` cho ghi chú/tóm tắt phản biện. Khóa cũ `style_readout` vẫn render, nhưng context mới nên dùng `strategy_readout`.

### 3. Ghi nhận giao dịch

Ví dụ:

- "Hôm qua tôi mua 30 cổ NVDA ở giá 185 USD."
- "Hôm nay bán 10 cổ TSLA ở giá 400 USD."
- "Cổ tức Q1 GOOG, 80 USD."
- "Nạp 5.000 USD để chuẩn bị vòng mua tiếp theo."
- "Đây là CSV Schwab của tôi — hãy nhập."

Quy tắc cứng: tác nhân không được INSERT vào `transactions.db` cho đến khi đã hiển thị kế hoạch phân tích, (các) blob JSON chuẩn, và nhận được `yes` rõ ràng trong cùng lượt. Trước mỗi lần ghi phải sao lưu `transactions.db.bak`, sau đó tự động dựng lại số dư, rồi `verify`. Xem `docs/transactions_agent_guidelines.md` §3.

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
- `docs/transactions_agent_guidelines.md`

Không đưa dữ liệu cá nhân vào các file quy cách.

## Quyền riêng tư

Được git theo dõi:

- quy cách tác nhân
- mẫu ví dụ
- script Python
- README
- file tham chiếu giao diện

Không được git theo dõi:

- `SETTINGS.md`
- `transactions.db`
- `transactions.db.bak`
- báo cáo sinh ra
- artifact chạy thông dụng như `prices.json`, `prices_history.json`, `report_context.json`, `temp/`

## Dữ liệu bên thứ ba

Dự án này không sở hữu hay bảo đảm bất kỳ nguồn dữ liệu giá hoặc FX nào. Luồng lấy giá có thể dùng endpoint công khai (Stooq JSON, Yahoo v8 chart, Binance, CoinGecko, Frankfurter/ECB, Open ExchangeRate-API, TWSE/TPEx MIS), khóa API tùy chọn (Twelve Data, Finnhub, Alpha Vantage, FMP, Tiingo, Polygon, J-Quants, CoinGecko Demo) và wrapper như `yfinance`. Với cổ phiếu Đài Loan, fallback MIS không cần token thử cả kênh niêm yết (`tse_`) và OTC (`otc_`) để giảm lỗi thiếu giá do phân loại nhầm `[TW]` / `[TWO]`. Việc tuân thủ điều khoản, giới hạn tốc độ, yêu cầu ghi nguồn và điều kiện trả phí là trách nhiệm của người dùng.

## Miễn trừ

Repo này chỉ phục vụ nghiên cứu cá nhân, không phải khuyến nghị đầu tư. Hãy tự xác minh các dữ kiện quan trọng trước khi giao dịch.
