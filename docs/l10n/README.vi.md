# Tác nhân nghiên cứu đầu tư

**Ngôn ngữ README** · [English](../../README.md) · [繁體中文](README.zh-Hant.md) · [简体中文](README.zh-Hans.md) · [日本語](README.ja.md) · [Tiếng Việt](README.vi.md) · [한국어](README.ko.md)

README tiếng Anh là bản chính thức; các ngôn ngữ khác chỉ là bản dịch để tiện đọc.

Repo này là không gian làm việc cục bộ cho tác nhân nghiên cứu đầu tư AI. Mở repo trong **Claude Code, OpenAI Codex, Gemini CLI**, hoặc bất kỳ tác nhân nào đọc được file và chạy lệnh — rồi cứ nói chuyện với nó.

**Tầng model:** Dùng **Claude Sonnet 4.6** với mức suy luận **High**, hoặc model mới hơn có khả năng tương đương trở lên. Model nhẹ hơn có thể bỏ bước hoặc làm nông phần phân tích.

## Cứ nhờ tác nhân

Bạn không cần học lệnh, schema hay file trước. Chọn khối nào khớp việc bạn muốn và dán vào.

**Mới vào?**

> "Giúp tôi bắt đầu." *(hoặc đính kèm sao kê nhà môi giới ở bất kỳ định dạng nào — PDF, CSV, JSON, XLSX, ảnh chụp màn hình, text dán — và nói "onboard tôi")*

**Muốn biết có thể làm gì?**

> "Ở đây tôi có thể làm gì?"

**Chỉnh cách tác nhân đóng vai bạn (khẩu vị rủi ro, sizing, vùng cấm, ngôn ngữ, tiền tệ gốc):**

> "Đi qua cài đặt với tôi."
> "Xem SETTINGS của tôi." / "Đổi tiền tệ gốc của tôi sang TWD."

**Ghi một giao dịch hoặc dòng tiền:**

> "Hôm qua tôi mua 30 cổ NVDA ở $185."
> "Hôm nay bán 10 cổ TSLA ở $400."
> "Cổ tức Q1 GOOG, $80."
> "Nạp $5,000."
> "Đây là CSV Schwab của tôi — hãy nhập."

**Hỏi nghiên cứu:**

> "Phân tích NVDA so với danh mục hiện tại của tôi."
> "Mức phơi bày AI của tôi hiện là bao nhiêu?"
> "Có nên giảm vị thế ngắn hạn trước mùa báo cáo không?"

**Tạo báo cáo danh mục hôm nay:**

> "Tạo báo cáo sức khỏe danh mục hôm nay."
> "Chạy báo cáo trước giờ mở cửa."

Tác nhân xác nhận trước mọi ghi vào dữ liệu của bạn, và làm theo tài liệu hợp đồng trong `docs/` từ đầu đến cuối. Bạn nói ngôn ngữ thường ngày; phần còn lại do tác nhân lo.

## Quyền riêng tư

Cài đặt, cơ sở dữ liệu giao dịch và mọi báo cáo sinh ra đều ở máy bạn — không có thứ nào được git theo dõi. Chỉ có đặc tả tác nhân, mẫu ví dụ và script Python nằm trong kiểm soát phiên bản.

## Dữ liệu bên thứ ba

Luồng giá có thể dùng endpoint dữ liệu thị trường và FX công khai (Stooq, Yahoo, Binance, CoinGecko, Frankfurter / ECB, Open ExchangeRate-API, TWSE / TPEx) và khóa API tùy chọn do bạn cung cấp. Dự án không vận hành hay xác nhận bất kỳ nhà cung cấp nào — bạn chịu trách nhiệm điều khoản, giới hạn tốc độ và truy cập trả phí.

## Miễn trừ

Chỉ phục vụ nghiên cứu cá nhân, không phải khuyến nghị đầu tư. Hãy tự xác minh các dữ kiện quan trọng trước khi giao dịch.
