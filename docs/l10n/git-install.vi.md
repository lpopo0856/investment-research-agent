# Cài bằng Git: hướng dẫn cho người mới

**Ngôn ngữ hướng dẫn** · [English](../git-install.md) · [繁體中文](git-install.zh-Hant.md) · [简体中文](git-install.zh-Hans.md) · [日本語](git-install.ja.md) · [Tiếng Việt](git-install.vi.md) · [한국어](git-install.ko.md)

Dùng hướng dẫn này nếu bạn chưa từng dùng Git, hoặc máy tính chưa cài Git. Nên cài repo này bằng Git vì sau này trợ lý có thể cập nhật bản cục bộ của bạn an toàn hơn.

## Bạn cần chuẩn bị gì

- Một máy tính có thể cài ứng dụng.
- Một coding assistant cục bộ như Codex, Claude Code hoặc trợ lý khác có thể mở thư mục và sửa file.
- URL repo này: `https://github.com/lpopo0856/investment-research-agent.git`

Bạn không cần hiểu sâu về Git. Bạn chỉ cần có một bản repo được cài bằng Git.

## Cách dễ nhất: GitHub Desktop

Đây là cách thân thiện nhất nếu bạn muốn dùng nút bấm thay vì dòng lệnh.

1. Cài GitHub Desktop từ trang tải chính thức: <https://desktop.github.com/download/>.
2. Mở GitHub Desktop.
3. Chọn **Clone a repository from the Internet**.
4. Chọn tab **URL**.
5. Dán URL này:

   ```text
   https://github.com/lpopo0856/investment-research-agent.git
   ```

6. Chọn thư mục cục bộ nơi bạn muốn lưu repo.
7. Bấm **Clone**.
8. Mở thư mục `investment-research-agent` vừa clone bằng trợ lý của bạn.
9. Nói: “Hãy chuyển repo này sang release tag mới nhất, rồi giúp tôi bắt đầu.”

   Giao diện GitHub Desktop không trực tiếp chuyển sang release tag, nên trợ lý sẽ làm thay. Trợ lý tự chọn tag mới nhất nên bạn không cần biết số phiên bản.

Khi cần cập nhật sau này, mở cùng thư mục đó bằng trợ lý và nói: “Hãy giúp tôi nâng cấp repo này một cách an toàn.”

## Cách dùng terminal: cài Git và clone

Dùng cách này nếu bạn thấy ổn khi mở Terminal, PowerShell hoặc Command Prompt.

1. Cài Git từ trang tải chính thức: <https://git-scm.com/downloads>.
2. Mở Terminal, PowerShell hoặc Command Prompt.
3. Đi tới thư mục bạn muốn lưu repo, ví dụ Documents hoặc Projects.
4. Clone repo và chuyển sang release tag mới nhất:

   ```bash
   git clone https://github.com/lpopo0856/investment-research-agent.git
   cd investment-research-agent
   git checkout "$(git tag --sort=-v:refname | head -n 1)"
   ```

   Dòng cuối tự động lấy release tag mới nhất nên bạn không cần nhập số phiên bản. Thông báo “detached HEAD” là bình thường; các bản cập nhật sau sẽ được trợ lý xử lý an toàn qua quy trình nâng cấp.

5. Mở thư mục `investment-research-agent` bằng trợ lý của bạn.
6. Nói: “Giúp tôi bắt đầu.”

## Liên kết hữu ích

- Repo dự án: <https://github.com/lpopo0856/investment-research-agent>
- Demo báo cáo: <https://lpopo0856.github.io/investment-research-agent/>
- Tải Git chính thức: <https://git-scm.com/downloads>
- Tải GitHub Desktop: <https://desktop.github.com/download/>
- Tài liệu cài GitHub Desktop: <https://docs.github.com/en/desktop/installing-and-authenticating-to-github-desktop/installing-github-desktop>
- Tài liệu clone của GitHub: <https://docs.github.com/repositories/creating-and-managing-repositories/cloning-a-repository>
