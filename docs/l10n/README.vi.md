# Trợ lý nghiên cứu đầu tư

**Ngôn ngữ README** · [English](../../README.md) · [繁體中文](README.zh-Hant.md) · [简体中文](README.zh-Hans.md) · [日本語](README.ja.md) · [Tiếng Việt](README.vi.md) · [한국어](README.ko.md)

README tiếng Anh là bản được duy trì chính; các ngôn ngữ khác là bản dịch để đọc thuận tiện.

Investment Research Agent là trợ lý đầu tư riêng tư chạy trong máy của bạn. Nó giúp theo dõi danh mục, ghi nhận giao dịch, nhập dữ liệu từ công ty chứng khoán, rồi biến các khoản nắm giữ thành nghiên cứu và kế hoạch hành động rõ ràng. Điểm vào khuyến nghị là UI web cục bộ: khởi động UI server trực tiếp từ terminal thường, dùng giao diện trình duyệt cho các thao tác tài khoản/vị thế/báo cáo/cài đặt hằng ngày, và chỉ dùng agent CLI nhúng khi cần tự động hóa hoặc phân tích bằng ngôn ngữ tự nhiên.

## Ví dụ báo cáo

**[Report Demo](https://lpopo0856.github.io/investment-research-agent/)**

## Bắt đầu nhanh

### Bạn cần chuẩn bị gì

- Một coding assistant cục bộ như Codex, Claude Code hoặc trợ lý khác có thể đọc và sửa file trong workspace này.
- Nên cài repo này từ GitHub bằng Git. Nếu bạn chưa biết Git hoặc chưa cài Git, hãy bắt đầu với [hướng dẫn cài Git cho người mới](git-install.vi.md). Tải ZIP vẫn dùng được để thử một lần, nhưng đó là bản sao độc lập và không dùng được quy trình nâng cấp do trợ lý quản lý.
- Dữ liệu công ty chứng khoán tùy chọn nếu bạn muốn trợ lý dựng danh mục thật, như sao kê, CSV, bảng tính, PDF, ảnh chụp màn hình hoặc lịch sử giao dịch dán vào.

Bạn không cần hiểu nội bộ dự án. Hãy khởi động UI cục bộ từ terminal thường, rồi dùng giao diện trình duyệt trực tiếp cho công việc thường ngày. Agent CLI nhúng dành cho các việc hợp với ngôn ngữ tự nhiên hơn, như nhập file phức tạp, ghi hoạt động phức tạp, nghiên cứu đầu tư, tạo báo cáo mới hoặc bảo trì.

### Bắt đầu sử dụng

1. **Cài repo này bằng Git (khuyến nghị).** Clone từ `https://github.com/lpopo0856/investment-research-agent.git`, rồi mở thư mục. Nếu Git còn mới với bạn, hãy làm theo [hướng dẫn cài Git cho người mới](git-install.vi.md). Nếu bạn chỉ tải ZIP, bạn vẫn có thể dùng thử, nhưng cập nhật sau này phải làm thủ công; để dùng lâu dài, nên cài bằng Git.
2. **Khởi động UI cục bộ từ terminal.** Chạy UI server từ repo root để server nằm trong một cửa sổ terminal nhìn thấy được và bạn có thể đóng khi xong:

   ```bash
   python3 -m venv .venv-ui
   source .venv-ui/bin/activate
   pip install -r requirements-ui.txt
   python3 scripts/run_ui_server.py
   ```

   Nếu trình duyệt không tự mở, hãy mở `http://127.0.0.1:8765/`. Từ đó bạn có thể dùng UI trực tiếp để chọn hoặc tạo tài khoản, xem vị thế, mở báo cáo đã có, sửa cài đặt và xem trước thay đổi.

3. **Dùng UI trước; dùng agent CLI nhúng khi hữu ích.** Điều hướng và chỉnh sửa đơn giản thường nên làm bằng các điều khiển trong trình duyệt. Dùng Claude/Codex agent CLI nhúng cho các việc bằng ngôn ngữ tự nhiên như:

   > "Hãy chuyển repo này sang release tag mới nhất, rồi giúp tôi bắt đầu."
   > "Nhập sao kê công ty chứng khoán này và cho tôi xem bạn đọc được gì trước khi lưu."
   > "Ghi các giao dịch này từ ghi chú của tôi."
   > "Tạo báo cáo danh mục từ dữ liệu demo."
   > "Phân tích NVDA so với danh mục hiện tại của tôi."

   Câu mở đầu nên dùng đúng dòng chuyển release tag ở trên — nó đảm bảo bạn đang ở bản phát hành mới nhất trước khi có dữ liệu danh mục nào bị ghi, và hoạt động cho cả người cài bằng Git CLI lẫn GitHub Desktop.

4. **Xem lại trước khi lưu.** Trợ lý sẽ xem trước các thay đổi về cài đặt, giao dịch và dữ liệu nhập trước khi ghi dữ liệu danh mục, để bạn có thể xác nhận hoặc chỉnh sửa kế hoạch trước.

## Nếu bạn đã tải ZIP

Tải ZIP vẫn ổn để thử demo nhanh, nhưng đó là bản sao độc lập. Nó không có Git history, nên trợ lý không thể tự động căn chỉnh branch hoặc release tag để nâng cấp an toàn.

Để dùng lâu dài:

1. Giữ bản ZIP cho đến khi bạn chắc chắn các file danh mục riêng tư đã an toàn.
2. Cài lại repo bằng Git hoặc GitHub Desktop.
3. Nếu bản ZIP đã chứa dữ liệu danh mục thật, đừng xóa nó. Mở thư mục đó bằng trợ lý và nói: “Giúp tôi chuyển bản cài ZIP này sang bản cài Git một cách an toàn.”

## Nâng cấp

Để cập nhật một repo đã có trên máy, hãy mở thư mục này bằng trợ lý và nói:

> "Hãy giúp tôi nâng cấp repo này một cách an toàn."

Trợ lý sẽ dùng skill `upgrade-management` để sao lưu dữ liệu danh mục riêng tư khi cần, cập nhật code repo và dependency đối với bản cài bằng Git, kiểm tra layout tài khoản, và dừng lại để xin xác nhận trước mọi migration hoặc ghi dữ liệu danh mục. Bản cài bằng Git có thể theo branch hiện tại hoặc release tag một cách an toàn; bản ZIP/archive được xem là bản sao độc lập, nên trợ lý chỉ hướng dẫn cập nhật thủ công và khuyến nghị chuyển sang Git cho các lần nâng cấp sau.

## Tính năng chính

Bạn không cần biết chi tiết kỹ thuật. Hãy dùng UI cục bộ làm trang chính: bấm qua tài khoản, vị thế, báo cáo và cài đặt trực tiếp, rồi dùng agent CLI nhúng cho tự động hóa hoặc phân tích bằng ngôn ngữ tự nhiên. Nếu có thao tác thay đổi dữ liệu danh mục đã lưu, luồng UI/agent sẽ cho bạn xem thay đổi dự kiến và chờ xác nhận trước khi lưu.

- **Bắt đầu sử dụng** — tạo tài khoản đầu tiên, nhập danh mục ban đầu và thiết lập phong cách đầu tư của bạn.
- **Thiết lập chiến lược** — xác định khẩu vị rủi ro, cách phân bổ vị thế, thời gian nắm giữ, ngôn ngữ, tiền tệ gốc và những lĩnh vực không muốn đụng tới.
- **Quản lý nhiều tài khoản** — tạo, chuyển đổi, xem và gộp nhiều tài khoản chứng khoán, hưu trí, khu vực hoặc chiến lược.
- **Ghi nhận hoạt động** — thêm mua, bán, nạp tiền, rút tiền, cổ tức, phí và đổi tiền bằng cách nói bình thường.
- **Nhập file từ công ty chứng khoán** — nhập sao kê, file xuất, bảng tính, PDF, ảnh chụp màn hình hoặc lịch sử giao dịch dán vào.
- **Sửa dữ liệu** — sửa giao dịch sai, xóa bản ghi trùng, đối chiếu tiền mặt và kiểm tra lô đang mở với sao kê.
- **Nghiên cứu đầu tư** — phân tích cổ phiếu, ETF, chủ đề, ngành, thị trường và mức phơi nhiễm danh mục theo chiến lược của bạn.
- **Báo cáo hằng ngày** — tạo bảng điều khiển quyết định trong ngày với giá, tin tức, sự kiện, cảnh báo, cơ hội, đề xuất điều chỉnh và danh sách hành động hôm nay.
- **Báo cáo danh mục** — xem vị thế, tiền mặt, phân bổ, lãi lỗ, mức tập trung, nhịp đầu tư và cấu trúc danh mục, không bị nhiễu bởi giao dịch trong ngày.
- **Báo cáo tổng hợp** — gộp mọi tài khoản thành góc nhìn cấp cao, trong khi dữ liệu của từng tài khoản vẫn tách riêng.
- **Kiểm tra rủi ro và phơi nhiễm** — hỏi phần nào quá tập trung, trùng lặp, rủi ro cao, thiếu vốn hoặc cần chú ý trước.

## Cách dùng chi tiết

### Mở UI cục bộ

UI cục bộ là cách dễ nhất để dùng dự án hằng ngày. Khởi động nó từ terminal nhìn thấy được trong repo root:

```bash
source .venv-ui/bin/activate  # nếu bạn đã tạo venv ở trên
python3 scripts/run_ui_server.py
```

Sau đó mở `http://127.0.0.1:8765/`. Dashboard trong trình duyệt trở thành cửa vào chính. Ưu tiên dùng điều khiển UI cho công việc thường ngày:

- chọn, tạo và chuyển tài khoản
- xem vị thế và dùng thao tác nhanh
- mở báo cáo đã có trong trình xem báo cáo
- sửa cài đặt từng phần kèm bản xem trước
- chỉ mở Claude/Codex agent CLI nhúng khi tác vụ cần trợ giúp bằng ngôn ngữ tự nhiên

Agent CLI nhúng phù hợp với việc dễ mô tả bằng chữ hơn là bấm qua: ghi giao dịch từ ghi chú, nhập file công ty chứng khoán, đối chiếu bản ghi phức tạp, nghiên cứu một khoản nắm giữ, tạo báo cáo mới, hoặc nâng cấp/bảo trì repo. Các gate xác nhận vẫn áp dụng trước khi lưu cài đặt hoặc dữ liệu ledger.

### Hỏi xem có thể làm gì

Nếu chưa biết bắt đầu từ đâu, trước tiên hãy xem các tab tài khoản, vị thế, báo cáo và cài đặt trong UI. Nếu vẫn muốn được hướng dẫn, hãy hỏi agent CLI nhúng:

> "Ở đây tôi có thể làm gì?"
> "Cho tôi xem các tính năng."
> "Trợ giúp."

Agent nhúng sẽ đưa một menu đơn giản cho việc bắt đầu, ghi giao dịch, nghiên cứu đầu tư và tạo báo cáo.

### Bắt đầu hoặc thiết lập danh mục

Khi thiết lập lần đầu, nếu chỉ cần tạo hoặc chọn tài khoản thì có thể làm trực tiếp trong UI. Dùng agent CLI nhúng khi bạn muốn được hướng dẫn hoặc cần nhập dữ liệu công ty chứng khoán:

> "Giúp tôi bắt đầu."
> "Onboard giúp tôi."
> "Dùng sao kê này để lập danh mục cho tôi."
> "Nhập file công ty chứng khoán này và thiết lập danh mục cho tôi."

Bạn có thể đính kèm sao kê, bảng tính, PDF, ảnh chụp màn hình hoặc lịch sử giao dịch dán vào. Trợ lý sẽ giúp tạo tài khoản, hiểu phong cách đầu tư, chuẩn bị dữ liệu và kiểm tra rằng thiết lập dùng được.

### Thiết lập hoặc xem lại phong cách đầu tư

Các thay đổi cài đặt đơn giản có thể sửa trực tiếp trong trình biên tập cài đặt của UI, có xem trước từng phần. Dùng agent CLI nhúng khi bạn muốn trợ giúp viết chiến lược, kiểm tra tính nhất quán hoặc đổi nhiều cài đặt liên quan:

> "Đi qua phần cài đặt với tôi."
> "Xem lại chiến lược đầu tư của tôi."
> "Cập nhật khẩu vị rủi ro của tôi."
> "Đổi tiền tệ gốc của tôi sang VND."
> "Dùng tiếng Việt cho báo cáo."
> "Tôi không muốn đầu tư vào các ngành này."

Nội dung có thể gồm khẩu vị rủi ro, quy mô vị thế, thời gian nắm giữ, kỷ luật điểm mua, ngôn ngữ ưu tiên, tiền tệ gốc và những lĩnh vực muốn tránh.

### Thêm và quản lý tài khoản

"Tài khoản" ở đây chỉ là sổ ghi chép tách riêng. Bạn chia sao cũng được: theo người (bạn, vợ/chồng, quỹ học vấn của con), theo mục đích (hưu trí, mua nhà, quỹ khẩn cấp), theo chiến lược (lõi, vệ tinh, vị thế thử nghiệm), theo phân loại thuế, hoặc nếu quen, theo thị trường (Việt Nam, Mỹ, Nhật Bản). Công cụ không bắt buộc cách chia.

Với thao tác tạo, liệt kê và chuyển tài khoản thông thường, nên dùng điều khiển tài khoản trong UI. Chỉ dùng agent CLI nhúng khi thiết lập tài khoản cần giải thích, nhiều bước, hoặc cần tạo báo cáo/hành động từ tài khoản đã chọn:

> "Tạo tài khoản chiến lược vệ tinh (vị thế nhỏ, rủi ro cao)."
> "Tạo tài khoản mới cho danh mục Nhật Bản của tôi."
> "Tạo báo cáo cho tài khoản hưu trí."
> "Gộp tất cả tài khoản để tạo báo cáo tổng hợp."

Mỗi tài khoản có cài đặt, giao dịch, tiền mặt, vị thế và báo cáo riêng. Báo cáo tổng hợp tạo góc nhìn cấp cao nhưng dữ liệu gốc của từng tài khoản vẫn tách biệt.

### Ghi nhận giao dịch và dòng tiền

Mô tả hoạt động đầu tư bằng lời nói thường ngày:

> "Hôm qua tôi mua 30 cổ phiếu NVDA giá 185 đô."
> "Hôm nay bán 10 cổ phiếu TSLA giá 400 đô."
> "Cổ tức quý 1 của GOOG, 80 đô."
> "Nạp 5,000 đô."
> "Rút 1,000 đô để đóng thuế."
> "Tôi trả 12 đô phí giao dịch."
> "Tôi đổi USD 2,000 sang VND."

Trợ lý sẽ đọc nội dung, hiển thị bản ghi dự kiến và chờ bạn xác nhận trước khi cập nhật danh mục.

### Sửa hoặc đối chiếu dữ liệu

Nếu có dữ liệu sai, hãy mô tả điều cần sửa:

> "Sửa lô GOOG từ tháng 9 năm ngoái."
> "Giao dịch NVDA đó phải là 20 cổ phiếu, không phải 30."
> "Xóa bản ghi cổ tức bị trùng."
> "Đối chiếu số dư tiền mặt với sao kê này."
> "Kiểm tra các lô đang mở có khớp với file công ty chứng khoán không."

Trợ lý sẽ giải thích thay đổi dự kiến trước khi lưu.

### Nhập file từ công ty chứng khoán

Đính kèm file và nói điều bạn muốn:

> "Đây là file xuất từ công ty chứng khoán, nhập giúp tôi."
> "Nhập lịch sử giao dịch này."
> "Nhập sao kê PDF này và cho tôi xem bạn đọc được gì trước khi lưu."
> "File này có cổ tức và giao dịch; thêm vào tài khoản của tôi."

Mẹo nhập liệu:

- Nếu PDF có mật khẩu, hãy tự mở và lưu một bản không mật khẩu trước khi nhập.
- Nếu file rất lớn, đặc biệt là PDF, hãy chia thành các phần nhỏ hơn.
- Nếu nội dung nhập có điểm mơ hồ, trợ lý sẽ hỏi bạn xác nhận cách hiểu trước khi lưu.

### Nghiên cứu cổ phiếu, ETF, chủ đề hoặc thị trường

Bạn có thể hỏi nghiên cứu gắn với danh mục:

> "Phân tích NVDA so với danh mục hiện tại của tôi."
> "Theo chiến lược của tôi, giờ có nên mua TSM không?"
> "So sánh TSM, NVDA và AMD."
> "Mức phơi nhiễm AI của tôi hiện là bao nhiêu?"
> "Có nên giảm vị thế ngắn hạn trước mùa báo cáo không?"
> "Xem lại mức phơi nhiễm Nhật Bản của tôi."
> "Tuần này ngành bán dẫn cần theo dõi gì?"

Ghi chú nghiên cứu tập trung vào quyết định: mua, giữ, giảm, tránh hay chờ; quy mô vị thế phù hợp; điều gì chứng minh nhận định sai; và cần theo dõi biến số nào tiếp theo.

### Tạo báo cáo hằng ngày

Dùng báo cáo hằng ngày khi bạn muốn bảng điều khiển quyết định cho hôm nay:

> "Tạo báo cáo hằng ngày hôm nay."
> "Chạy báo cáo trước giờ mở cửa."
> "Cho tôi bản kiểm tra sức khỏe danh mục hôm nay."
> "Hôm nay tôi nên làm gì với danh mục?"

Báo cáo hằng ngày có thể gồm giá mới nhất, sức khỏe danh mục, tin tức quan trọng, sự kiện sắp tới, cảnh báo rủi ro, cơ hội đáng chú ý, đề xuất điều chỉnh và danh sách hành động rõ ràng trong ngày.

### Tạo báo cáo danh mục

Dùng báo cáo danh mục khi bạn muốn xem cấu trúc, không phải nhiễu giao dịch trong ngày:

> "Tạo báo cáo danh mục của tôi."
> "Cho tôi xem phân bổ và hiệu suất."
> "Xem lại vị thế, tiền mặt và mức tập trung của tôi."
> "Danh mục của tôi hoạt động ra sao?"

Báo cáo danh mục tập trung vào vị thế, tiền mặt, phân bổ, lãi lỗ, mức tập trung, nhịp đầu tư và cấu trúc danh mục. Nó phù hợp để xem toàn bộ sổ đầu tư hơn là tạo quyết định giao dịch trong ngày.

### Tạo báo cáo tổng hợp nhiều tài khoản

Khi có nhiều tài khoản, hãy yêu cầu góc nhìn gộp:

> "Gộp tất cả tài khoản để tạo báo cáo tổng hợp."
> "Cho tôi xem tổng danh mục."
> "Gộp mọi tài khoản và tóm tắt mức phơi nhiễm."

Báo cáo tổng hợp cung cấp góc nhìn cấp cao trên nhiều tài khoản và tránh đưa ra gợi ý giao dịch riêng cho một tài khoản.

### Hỏi về rủi ro và phơi nhiễm

Bạn có thể hỏi câu hỏi tập trung mà không cần tạo báo cáo đầy đủ:

> "Rủi ro tập trung lớn nhất của tôi là gì?"
> "Tôi đang có bao nhiêu tiền mặt?"
> "Vị thế nào trùng lặp nhiều nhất?"
> "Tôi có quá tập trung vào bán dẫn AI không?"
> "Vị thế nào hiện rủi ro cao nhất?"
> "Sự kiện nào sắp tới ảnh hưởng đến danh mục của tôi?"

### Xin kế hoạch hành động

Nếu chỉ muốn danh sách quyết định ngắn, hãy nói:

> "Cho tôi danh sách hành động hôm nay."
> "Tôi nên mua, giảm hay để yên?"
> "Vị thế nào cần chú ý trước?"
> "Tuần này tôi cần theo dõi gì?"

Khi không có lợi thế rõ ràng, trợ lý sẽ ưu tiên không hành động thay vì ép tạo giao dịch.

## Quyền riêng tư

Cài đặt, lịch sử giao dịch và báo cáo tạo ra đều ở lại trong không gian làm việc cục bộ này. Dự án này không công khai dữ liệu của bạn. Bạn kiểm soát file nào chia sẻ với trợ lý và thay đổi nào được lưu.

## Dữ liệu thị trường bên thứ ba

Báo cáo và nghiên cứu có thể dùng nguồn dữ liệu giá và tỷ giá công khai, cùng quyền truy cập dữ liệu bạn tự cung cấp. Tính sẵn có, độ trễ, giới hạn sử dụng và độ chính xác phụ thuộc vào từng nhà cung cấp.

## Tuyên bố miễn trừ

Chỉ dùng cho nghiên cứu cá nhân và ghi chép. Không phải lời khuyên đầu tư, pháp lý hay thuế. Hãy tự kiểm chứng các sự kiện quan trọng trước khi giao dịch; bạn chịu trách nhiệm cho quyết định và kết quả của mình.
