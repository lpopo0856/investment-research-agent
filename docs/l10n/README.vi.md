# Trợ lý nghiên cứu đầu tư (AI Agent)

**Ngôn ngữ README** · [English](../../README.md) · [繁體中文](README.zh-Hant.md) · [简体中文](README.zh-Hans.md) · [日本語](README.ja.md) · [Tiếng Việt](README.vi.md) · [한국어](README.ko.md)

README tiếng Anh là bản chuẩn được duy trì; các ngôn ngữ khác là bản dịch để đọc cho tiện.

Repo này là không gian làm việc **trợ lý nghiên cứu đầu tư AI** chạy trên máy bạn. Mở repo trong **Claude Code, OpenAI Codex, Gemini CLI**, hoặc bất kỳ môi trường agent nào đọc được file và chạy lệnh — rồi cứ trò chuyện bằng tiếng Việt thường ngày.

**Gợi ý model:** Dùng **Claude Sonnet 4.6** với mức suy luận **High**, hoặc model mới hơn có năng lực tương đương trở lên. Model nhẹ hơn dễ bỏ bước hoặc làm phần phân tích nông hơn.

## Report Demo

**[Report Demo](https://lpopo0856.github.io/investment-research-agent/)**

## Cứ nhờ trợ lý

Bạn không cần học lệnh, schema hay cấu trúc file trước. Chọn đoạn nào đúng việc bạn muốn và dán vào.

**Mới dùng lần đầu?**

> "Giúp tôi bắt đầu." *(hoặc đính kèm sao kê / bảng kê nhà môi giới ở bất kỳ định dạng nào — PDF, CSV, JSON, XLSX, ảnh chụp màn hình, chữ dán — và nói "onboard giúp tôi" / "hướng dẫn tôi làm quen với hệ thống")*

Script tự dùng tài khoản đang hoạt động (thiết lập bằng `--account <name>` trên dòng lệnh hoặc `accounts/.active`; mặc định là `accounts/default/`).

**Muốn biết làm được gì ở đây?**

> "Ở đây tôi có thể làm những gì?"

**Chỉnh cách trợ lý “đóng vai” bạn (khẩu vị rủi ro, khối lượng vị thế, ranh giới không đụng tới, ngôn ngữ, tiền tệ gốc):**

> "Đi qua phần cài đặt với tôi."
> "Xem SETTINGS của tôi." / "Đổi tiền tệ gốc của tôi sang TWD."

**Ghi một giao dịch hoặc dòng tiền:**

> "Hôm qua tôi mua 30 cổ phiếu NVDA giá 185 đô."
> "Hôm nay bán 10 cổ phiếu TSLA giá 400 đô."
> "Cổ tức quý 1 của GOOG, 80 đô."
> "Nạp 5,000 đô vào tài khoản."
> "Đây là CSV tôi xuất từ Schwab — nhập giúp tôi." *(file xuất từ broker khác cũng được xử lý theo `docs/`)*

**Mẹo nhập liệu:** Nếu bạn có cổ phiếu Đài Loan, khi có bản xuất từ Sở giao dịch chứng khoán Đài Loan (TWSE) thì nên đính kèm. PDF có mật khẩu: mở bằng trình duyệt, dùng **In** để lưu bản không mật khẩu rồi mới nhập. Tệp rất lớn (nhất là PDF): chia nhỏ và nhập từng đợt một.

**Hỏi kiểu nghiên cứu:**

> "Phân tích NVDA so với danh mục hiện tại của tôi."
> "Mức phơi nhiễm AI của tôi hiện tới đâu?"
> "Có nên giảm vị thế ngắn hạn trước mùa báo cáo không?"

**Tạo báo cáo danh mục trong ngày:**

> "Tạo báo cáo ‘sức khỏe’ danh mục hôm nay."
> "Chạy báo cáo trước giờ mở cửa."

Mọi thao tác làm thay đổi dữ liệu đã lưu đều cần bạn xác nhận trước. Bạn nói tiếng Việt đời thường là được; trợ lý làm theo tài liệu trong `docs/` suốt quy trình và lo phần kỹ thuật.

## Đa tài khoản

Mỗi tài khoản có cài đặt, sổ cáo giao dịch và báo cáo riêng dưới `accounts/<name>/` (ví dụ `accounts/default/SETTINGS.md`, `accounts/default/transactions.db`, `accounts/default/reports/`).

**Thứ tự ưu tiên chọn tài khoản** (cao → thấp):
1. Cờ `--account <name>` trên dòng lệnh
2. File con trỏ `accounts/.active` (một dòng chứa tên tài khoản)
3. `accounts/default/` nếu tồn tại

**Di chuyển bố cục gốc:** Nếu `SETTINGS.md` hoặc `transactions.db` nằm ở thư mục gốc repo và không có thư mục `accounts/`, mọi script sẽ phát hiện bố cục cũ và hỏi `Migrate? [y/N]`. Trả lời `y` sẽ chuyển file vào `accounts/default/`, ghi bản sao lưu vào `.pre-migrate-backup/`, rồi tiếp tục lệnh của bạn. Người dùng mới hoàn toàn không gặp nhắc này — onboarding tạo thẳng `accounts/default/`.

**Không thuộc phạm vi tài khoản:** `market_data_cache.db` (bộ nhớ đệm giá / FX dùng chung) và `demo/` vẫn ở gốc repo và không được chuyển vào `accounts/`.

**Lệnh quản lý tài khoản:**
```bash
python scripts/transactions.py account list          # liệt kê tài khoản, đánh dấu đang hoạt động
python scripts/transactions.py account use <name>    # đổi tài khoản hoạt động
python scripts/transactions.py account create <name> # tạo khung tài khoản mới
```

## Quyền riêng tư

Cài đặt, cơ sở dữ liệu giao dịch (SQLite) và mọi báo cáo được tạo đều nằm cục bộ dưới `accounts/<name>/` — **không** được Git theo dõi. Trong version control chỉ có đặc tả agent, mẫu ví dụ và script Python.

## Dữ liệu bên thứ ba

Luồng giá có thể gọi API dữ liệu thị trường và tỷ giá công khai (Stooq, Yahoo, Binance, CoinGecko, Frankfurter / ECB, Open ExchangeRate-API, TWSE / TPEx, …) cùng khóa API tùy chọn do bạn cấu hình. Dự án không vận hành hay chứng thực bất kỳ nhà cung cấp nào — điều khoản, giới hạn tốc độ gọi và phí dịch vụ do bạn tự kiểm tra và chịu trách nhiệm.

## Miễn trừ trách nhiệm

Chỉ phục vụ nghiên cứu cá nhân và ghi chép; **không phải** khuyến nghị đầu tư hay tư vấn pháp lý. Trước khi giao dịch, hãy tự kiểm chứng các thông tin quan trọng và chịu trách nhiệm với quyết định của mình.
