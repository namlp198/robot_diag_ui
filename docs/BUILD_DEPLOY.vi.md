# Hướng dẫn build, đóng gói và triển khai robot_diag_ui

Tài liệu này đi từ máy trắng đến file cài đặt chạy được trên máy khác. Bản tiếng Anh: [BUILD_DEPLOY.en.md](BUILD_DEPLOY.en.md).
Mọi lệnh là PowerShell, chạy từ thư mục gốc repo (`robot_diag_ui`), trừ khi ghi khác.

## 1. Tổng quan: ba cách chạy

| Cách | Dùng khi | Cần trên máy |
|---|---|---|
| **Từ mã nguồn** (`rdt serve`, `scripts\start.ps1`) | Phát triển, sửa mã, chạy test | Python 3.12, Node (để build giao diện), các gói pip |
| **Thư mục đóng gói** `dist\RobotDiag\RobotDiag.exe` | Thử bản build trước khi phát hành | Chỉ Windows + WebView2 |
| **Bộ cài đặt** `RobotDiag-Setup-<phiên bản>.exe` | Phát cho người dùng / máy khác | Chỉ Windows + WebView2 |

Kiến trúc không đổi giữa ba cách: một daemon (`rdt`, FastAPI, chỉ nghe `127.0.0.1`) giữ các probe ST-LINK và phục vụ giao diện web
(Svelte, đã build sẵn vào `ui\dist`). Cửa sổ của ứng dụng (`rdt app`) là pywebview trên Microsoft Edge WebView2; trình duyệt thường cũng
mở được cùng địa chỉ. Daemon là chương trình duy nhất giữ probe: một probe chỉ phục vụ một phiên (đóng CubeIDE debug trước khi đọc).

```
rdt/            mã Python (daemon, CLI, đọc SWD, phân tích, nạp, chat)
ui/             giao diện Svelte + Vite  ->  ui/dist (build)
targets.yaml    cấu hình hai board (serial ST-LINK, ELF, vùng flash)
scripts/        start.ps1, check.ps1, build_exe.ps1, robot_diag.spec, installer.iss, ...
tests/          pytest
docs/ decisions/ handoff/ tasks/   tài liệu, quyết định, bàn giao
```

## 2. Yêu cầu

**Máy phát triển / build** (Windows 10/11 x64):

| Thành phần | Phiên bản | Ghi chú |
|---|---|---|
| Python | 3.12 | `scripts\toolchain.psd1` ghi phiên bản đã ghim |
| Node.js | 17.x trở lên (đã dùng 17.9.1) | Chỉ để build giao diện; Vite 4.5.5 và Svelte 4.2.19 được chọn vì chạy được trên Node 17 |
| Inno Setup | 6 (`ISCC.exe`) | Chỉ để dựng bộ cài đặt; `winget install JRSoftware.InnoSetup` |
| STM32CubeProgrammer | 2.20.0 | Chỉ khi nạp firmware hoặc dùng trang Programmer CLI |
| Driver ST-LINK | STSW-LINK009 của ST | Khi đọc board thật |

**Máy người dùng cuối** (chỉ chạy bản cài): Windows 10/11, **Edge WebView2 runtime** (có sẵn trên Windows 11 và Edge hiện hành),
driver ST-LINK, STM32CubeProgrammer nếu muốn nạp, và đăng nhập Claude nếu muốn dùng khung chat. Không cần Python, Node hay Git.

## 3. Thiết lập môi trường phát triển

```powershell
git clone https://github.com/namlp198/robot_diag_ui.git
cd robot_diag_ui
python -m venv .venv
.venv\Scripts\python -m pip install -e .[dev,daemon,probe,chat,app]
.venv\Scripts\python -m pip install pyinstaller==6.22.3      # chỉ khi đóng gói
cd ui; npm install; npm run build; cd ..                      # tạo ui\dist
.\scripts\check.ps1                                           # pytest + smoke CLI
```

Các extra trong `pyproject.toml`:

| Extra | Có gì | Cần cho |
|---|---|---|
| (mặc định) | pyelftools, pyyaml | đọc ELF, cấu hình |
| `dev` | pytest | test |
| `daemon` | fastapi, uvicorn, httpx | daemon và giao diện |
| `probe` | pyocd 0.46.1, pyserial | đọc SWD, log VCP |
| `chat` | claude-agent-sdk 0.2.180 | khung chat Claude |
| `app` | pywebview 6.2.1 | cửa sổ riêng (`rdt app`) |

Phiên bản đã ghim nằm ở `scripts\toolchain.psd1`. Đổi phiên bản phải kèm một ghi chú trong `decisions\` (quy tắc của repo).

Firmware: `targets.yaml` trỏ tương đối tới các repo cạnh nhau (`..\robot_s_rtos`, `..\robot_rc_rtos`). Build firmware bằng CubeIDE trước
để có file `.elf` (bản Debug có DWARF để đặt tên biến; bản Release chỉ cần cho địa chỉ).

## 4. Chạy và kiểm tra

```powershell
.\scripts\start.ps1              # cửa sổ riêng (rdt app); đóng cửa sổ thì daemon dừng
.\scripts\start.ps1 -Edge        # cửa sổ Edge kiểu app (tự dùng khi thiếu pywebview)
.\scripts\start.ps1 -Browser     # tab trình duyệt; dừng bằng Ctrl+C
.\scripts\make_shortcut.ps1      # shortcut "Robot Diag" trên desktop
.venv\Scripts\rdt serve          # chỉ daemon, giao diện ở http://127.0.0.1:8765
.venv\Scripts\rdt --help         # watch, record, replay, analyze, sweep, flash-plan, resolve, serve, app
```

`start.ps1` so thời điểm sửa mã với daemon đang chạy và tự khởi động lại daemon cũ hơn mã (daemon cũ phục vụ giao diện mới với endpoint cũ
làm các trang như Frames trống).

Kiểm tra trước khi commit hoặc build:

```powershell
.\scripts\check.ps1                                  # pytest + rdt --help
$env:RDT_HW_TESTS = "1"; .venv\Scripts\python -m pytest   # thêm test dùng probe thật (đóng CubeIDE debug trước)
.venv\Scripts\python -I scripts\gen_reference.py     # sinh lại docs\REFERENCE.*.md sau khi sửa rdt\reference.py
```

Test cần ELF hoặc probe sẽ bỏ qua (skip), không fail, khi thiếu. Test kiểm tra rằng mọi biến hiển thị trên giao diện đều có trong tài
liệu tham khảo và tài liệu sinh ra không bị cũ.

Biến môi trường tùy chọn: `RDT_CHAT_MODEL` (mặc định `claude-sonnet-5-5`), `RDT_CHAT_MAX_USD` (trần chi phí chat, mặc định 2.0). Model,
effort và trần chi phí còn chỉnh được ở trang Cài đặt.

## 5. Build giao diện

```powershell
cd ui
npm install        # lần đầu
npm run build      # ra ui\dist (giao diện tĩnh, daemon phục vụ)
npm run dev        # tùy chọn: Vite dev server khi sửa giao diện
```

`ui\dist` không nằm trong git. Daemon đọc `ui\dist` khi chạy từ mã nguồn; bản đóng gói nhúng sẵn bản build.

## 6. Đóng gói thành .exe và bộ cài đặt

```powershell
.\scripts\build_exe.ps1
```

Một lệnh làm tuần tự:

1. Build giao diện (`npm run build`), trừ khi `-SkipUi`.
2. **PyInstaller** (`scripts\robot_diag.spec`, chế độ một thư mục, không console) tạo `dist\RobotDiag\RobotDiag.exe` (khoảng 420 MB: kèm pyOCD,
   `claude.exe` của Agent SDK, pywebview, giao diện), trừ khi `-SkipBuild`.
3. **Smoke test** exe vừa build: chạy `RobotDiag.exe serve --port 8897`, kiểm tra giao diện được phục vụ, API trả lời, Claude SDK có đi kèm, quét
   ST-LINK chạy được (`-NoSmoke` để bỏ qua).
4. **Inno Setup** (`scripts\installer.iss`) tạo `dist\installer\RobotDiag-Setup-<phiên bản>.exe` (khoảng 180 MB), trừ khi `-NoInstaller`.

| Tùy chọn | Tác dụng |
|---|---|
| `-SkipUi` | dùng lại `ui\dist` (không chạy npm) |
| `-SkipBuild` | dùng lại `dist\RobotDiag` (chỉ smoke test và bộ cài) |
| `-NoSmoke` | bỏ smoke test |
| `-NoInstaller` | chỉ build thư mục, không dựng bộ cài |

Lần build đầu mất vài phút (PyInstaller thu thập pyOCD, SDK, pywebview). `dist\` và `build\` bị git bỏ qua (`.gitignore`).

Các file liên quan:

| File | Vai trò |
|---|---|
| `scripts\rdt_entry.py` | điểm vào của PyInstaller; dùng import tuyệt đối (script gốc của PyInstaller không import tương đối được) |
| `rdt\launcher.py` | không đối số: mở cửa sổ (`rdt app`); có đối số: chạy như lệnh `rdt` (ví dụ `RobotDiag.exe serve --port 8765`); ghi log ra file |
| `rdt\paths.py` | tách thư mục chỉ-đọc (bundle) với thư mục dữ liệu của người dùng |
| `scripts\robot_diag.spec` | gói nào cần `collect_all` (pyOCD, libusb, claude_agent_sdk, webview, pythonnet...) và metadata |
| `scripts\installer.iss` | bộ cài Inno Setup |
| `scripts\robot_diag.ico`, `scripts\make_icon.py` | biểu tượng và script sinh ra nó |

### Phiên bản

Phiên bản nằm ở hai chỗ phải bằng nhau: `rdt\__init__.py` (`__version__`) và `pyproject.toml` (`version`). Một test kiểm tra điều này; bộ cài lấy
số phiên bản từ `rdt.__version__`.

## 7. Bộ cài đặt

- Cài theo từng người dùng, **không cần quyền admin**: ứng dụng vào `%LOCALAPPDATA%\Programs\RobotDiag`, có Start menu và shortcut desktop tùy chọn.
- Cài im lặng: `RobotDiag-Setup-0.2.0.exe /VERYSILENT /NORESTART /SUPPRESSMSGBOXES` (thêm `/DIR="D:\Apps\RobotDiag"` để đổi thư mục,
  `/TASKS="desktopicon"` để có shortcut desktop).
- Nâng cấp: chạy bộ cài mới đè lên (cùng `AppId`); dữ liệu người dùng không bị đụng.
- Gỡ: Settings > Apps, hoặc `%LOCALAPPDATA%\Programs\RobotDiag\unins000.exe /VERYSILENT`. **Dữ liệu người dùng không bị xóa**
  (xem mục 8); xóa tay thư mục đó nếu muốn sạch hoàn toàn.
- Cuối cài đặt, bộ cài cảnh báo nếu chưa có Edge WebView2 runtime (tải Evergreen runtime từ trang WebView2 của Microsoft).

## 8. Dữ liệu và cấu hình trên máy cài

Bản cài **không ghi vào thư mục cài**. Mọi thứ người dùng đổi nằm ở `%LOCALAPPDATA%\RobotDiag`:

| Đường dẫn | Nội dung |
|---|---|
| `targets.yaml` | cấu hình board (sao từ bản đi kèm ở lần chạy đầu, sau đó không ghi đè) |
| `sessions\` | các phiên ghi, `flash_log.jsonl`, `settings.json` |
| `sessions\chats\` | các cuộc trò chuyện đã lưu (kèm ảnh/file đính kèm) |
| `logs\robot_diag.log` | log của ứng dụng (exe không có console) |
| `%LOCALAPPDATA%\robot_diag_ui\webview` | hồ sơ WebView (theme, ngôn ngữ, danh sách Live Expressions) |

Sao lưu: chép thư mục `%LOCALAPPDATA%\RobotDiag`. Khi chạy từ mã nguồn thì các thứ này nằm trong chính repo (`sessions\` bị git bỏ qua).

## 9. Triển khai lên máy mới (danh sách kiểm tra)

1. Cài **driver ST-LINK** (STSW-LINK009) và **STM32CubeProgrammer 2.20.0** (nếu cần nạp). Cắm board.
2. Chạy bộ cài `RobotDiag-Setup-*.exe`; mở Robot Diag.
3. Vào **Cài đặt > Môi trường và công cụ** và bấm quét: STM32_Programmer_CLI phải báo *Sẵn sàng*, driver ST-LINK báo *Sẵn sàng* và liệt kê từng probe
   cùng serial; Claude báo *Sẵn sàng*, nếu chưa thì bấm nút `claude auth login` và đăng nhập trong trình duyệt.
4. **Serial probe**: `targets.yaml` mang serial ST-LINK của bộ board hiện tại. Máy/board khác thì sửa `%LOCALAPPDATA%\RobotDiag\targets.yaml`
   (`probe_serial`) theo serial hiện ở bước 3. Chưa có giao diện sửa mục này.
5. **File ELF**: máy không có các repo firmware cạnh nhau nên đường dẫn trong `targets.yaml` không tồn tại. Vào **Cài đặt > File ELF**, thêm ELF của
   từng board (bản Debug có DWARF cho biến, và ELF Release cho image nếu board chạy bản Release) rồi chọn.
6. **File để nạp**: **Cài đặt > File firmware để nạp**, đăng ký `.elf`/`.hex`/`.bin` cho từng board (`.bin` cần địa chỉ). Khung "Nạp firmware" chỉ nhận
   các file đã đăng ký.
7. Thử đọc: bấm "Bắt đầu đọc" ở Bảng điều khiển; trạng thái từng board và việc firmware khớp ELF hiện ở đầu trang.
8. Trước khi nạp robot: bánh phải được kê khỏi mặt đất, có người ở cạnh sẵn sàng tắt nguồn (nguồn motor là nguồn của board).

## 10. Quy trình phát hành

1. Cập nhật mã, chạy `.\scripts\check.ps1` (phải xanh).
2. Nếu đổi biến hiển thị hoặc `rdt\reference.py`: `python -I scripts\gen_reference.py`.
3. Tăng phiên bản ở `rdt\__init__.py` và `pyproject.toml`.
4. `.\scripts\build_exe.ps1` (smoke test phải qua).
5. **Cài thử bộ cài trên một máy sạch** (không Python, không repo firmware): cài, mở, chạy bước 3 đến 7 của mục 9, gỡ, cài lại (nâng cấp) và kiểm tra dữ
   liệu còn nguyên.
6. Ghi vào `handoff\latest.md` (đã kiểm chứng gì, chưa gì) và, nếu đổi kiến trúc, thêm file trong `decisions\`.
7. Commit, gắn tag phiên bản, lưu `RobotDiag-Setup-<phiên bản>.exe` ở nơi phát hành (file này không nằm trong git).

Bộ cài **chưa ký số**: Windows SmartScreen sẽ cảnh báo lần chạy đầu trên máy khác ("Run anyway"). Muốn tránh, ký bằng chứng chỉ code signing sau
khi build, ví dụ `signtool sign /fd SHA256 /tr <timestamp-url> /td SHA256 /a dist\installer\RobotDiag-Setup-<phiên bản>.exe` (và ký luôn
`RobotDiag.exe` trước khi dựng bộ cài). Việc này chưa được làm.

## 11. Cập nhật thư viện đã ghim

1. Đổi phiên bản trong `pyproject.toml` và `scripts\toolchain.psd1` (một test kiểm tra chúng khớp với tài liệu này).
2. `.venv\Scripts\python -m pip install -e .[...]`, chạy `check.ps1`, rồi build lại và chạy smoke test: PyInstaller dễ hỏng khi gói đổi cách nạp plugin hay dữ liệu
   (pyOCD nạp probe bằng entry point, Agent SDK kèm `claude.exe`, pywebview cần pythonnet).
3. Ghi lý do trong `decisions\`.

## 12. Xử lý sự cố

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| `Access denied (insufficient permissions)` khi đọc | probe đang bị chương trình khác giữ (CubeIDE debug, một daemon khác) | đóng phiên debug, đóng daemon thừa, rút cắm ST-LINK |
| Trang Frames, Live Expressions trống sau khi cập nhật | daemon cũ còn chạy với mã cũ | đóng cửa sổ rồi chạy lại `start.ps1` (tự khởi động lại daemon cũ) |
| Cửa sổ không mở / chậm lần đầu | WebView2 chưa có, hoặc lần đầu unpack chậm | cài WebView2 Evergreen; chờ vài giây; xem `logs\robot_diag.log` |
| "Không thấy file ELF" khi bấm Bắt đầu đọc | `targets.yaml` trỏ tới đường dẫn không có trên máy này | chọn ELF ở Cài đặt > File ELF |
| `FIRMWARE MISMATCH` | board chạy bản khác với ELF đang chọn | chọn đúng ELF (hoặc nạp lại); giá trị đọc được lúc này không đáng tin |
| Chat báo chưa đăng nhập | Claude Code đi kèm chưa đăng nhập | Cài đặt > nút `claude auth login` |
| `pip install` hoặc `pytest` báo "Invalid statement (at line 1, column 1)" | `pyproject.toml` bị ghi lại có BOM | lưu lại dạng UTF-8 không BOM (đừng dùng `Set-Content -Encoding utf8` của PowerShell 5.1) |
| `build_exe.ps1` dừng ngay ở PyInstaller với `NativeCommandError` | PowerShell 5.1 coi stderr là lỗi | script đã bọc bằng `Invoke-Tool`; nếu tự gọi lệnh, đặt `$ErrorActionPreference = "Continue"` quanh lệnh |
| Exe thoát ngay (mã 1), không có log | lỗi import lúc khởi động | chạy `RobotDiag.exe serve --port 8899` rồi xem `%LOCALAPPDATA%\RobotDiag\logs\robot_diag.log`; kiểm tra cảnh báo `build\pyinstaller\robot_diag\warn-robot_diag.txt` |
| Smoke test báo SDK không đi kèm | gói `claude_agent_sdk` không được thu thập | kiểm tra `collect_all("claude_agent_sdk")` trong `robot_diag.spec` |
| pytest treo khi liệt kê USB | CubeIDE đang mở phiên | test dùng probe chỉ chạy khi đặt `RDT_HW_TESTS=1`; đóng CubeIDE debug |
| SmartScreen cảnh báo bộ cài | bộ cài chưa ký | chọn "More info" > "Run anyway", hoặc ký số (mục 10) |

## 13. Bảo mật và an toàn khi vận hành

- Daemon chỉ nghe `127.0.0.1` và từ chối Host/Origin không phải cục bộ.
- Mặc định **chỉ đọc**: không halt, không reset, không ghi bộ nhớ target. Việc duy nhất ghi vào board là nạp firmware qua khung "Nạp firmware" (cụm
  xác nhận, DEV_ID, vùng flash, file đã đăng ký, `motors_safe` cho robot). Claude chỉ có công cụ đọc và hiển thị.
- Không mở VCP USART3 của robot (dùng chung với đường nhận của module E22).
- Thanh ghi ngoại vi chỉ đọc được khi bật "cho phép đọc thanh ghi ngoại vi" ở Cài đặt (đọc có thể xóa cờ hoặc lấy byte khỏi FIFO).
- Mọi thứ đính kèm trong chat được gửi lên Anthropic như một tin nhắn chat bình thường.

## 14. Bảng lệnh nhanh

| Việc | Lệnh |
|---|---|
| Cài môi trường | `python -m venv .venv; .venv\Scripts\python -m pip install -e .[dev,daemon,probe,chat,app]` |
| Build giao diện | `cd ui; npm install; npm run build` |
| Chạy | `.\scripts\start.ps1` |
| Kiểm tra | `.\scripts\check.ps1` |
| Build + bộ cài | `.\scripts\build_exe.ps1` |
| Chỉ build thư mục | `.\scripts\build_exe.ps1 -NoInstaller` |
| Dựng lại bộ cài từ bản build có sẵn | `.\scripts\build_exe.ps1 -SkipBuild -NoSmoke` |
| Cài im lặng | `RobotDiag-Setup-<v>.exe /VERYSILENT /NORESTART` |
| Gỡ im lặng | `%LOCALAPPDATA%\Programs\RobotDiag\unins000.exe /VERYSILENT` |
| Sinh lại tài liệu tham khảo | `.venv\Scripts\python -I scripts\gen_reference.py` |
