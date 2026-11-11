# robot_diag: tool có UI, khung chat Claude Code và trực quan hóa (làm bằng ST-LINK trước)

Nháp, 2026-11-11. Chưa có decision. Bổ sung cho `flash_diag_tool_plan.md` (2026-11-03): bản đó đã
có kiến trúc daemon + MCP, phương án có dây / ESP32, an toàn và các spike S1-S3. Bản này chốt
phạm vi **có dây trước** và thêm hai thứ bản cũ để sau: **khung chat Claude Code nằm trong UI**
và **trực quan hóa**. Task Jira tương ứng: 111 / 169.

## 1. Ý tưởng một câu

Một cửa sổ duy nhất: bên trái là dữ liệu sống của hai board (remote và robot) qua hai ST-LINK,
bên phải là Claude Code đang xem **cùng dữ liệu đó**. Bạn hỏi "vì sao robot rơi vào failsafe?",
Claude tự đọc biến, log, frame, rồi **chỉ lên đồ thị** chỗ nó nghĩ là nguyên nhân.

Khác với phiên làm việc hiện tại: bây giờ mỗi phép đo là một lệnh `STM32_Programmer_CLI` do tôi
gõ (mỗi lần mở kết nối, ~1 lần/s) và bạn không nhìn thấy gì cho tới khi tôi báo lại. Tool này
cho bạn nhìn trực tiếp, và Claude không còn phải đoán offset (`+0x6C`).

## 2. Dữ liệu lấy được qua hai ST-LINK

| Kênh | Remote (F446, USART2 VCP) | Robot (H755 CM7) |
|---|---|---|
| Log VCP | Có: `[lora]`, `[tx]`, `[in]`, `[io]`, `[sweep]`, banner (115200) | **Không dùng được**: USART3 PD8/PD9 là VCP chung với đường nhận E22, mở COM sẽ chặn byte tới robot |
| Đọc biến qua SWD khi đang chạy | Có (blackboard `rc_state`, bộ đếm supervisor) | Có: `s_lora_rx`, `s_stats`, `s_remote_input`, FDCAN PSR... |
| Log runtime từ firmware | Có | **Chưa có** (debug_guide §10 mục 5) |
| Thanh ghi ngoại vi | Có | Có (ví dụ FDCAN PSR/ECR) |
| Nạp code, reset | Có | Có (CM7/CM4 qua STM32_Programmer_CLI) |

Hệ quả thiết kế: phía robot **không có log**, mọi thứ đi qua đọc biến SWD. Vì vậy:

1. Đọc theo **tên biến** (địa chỉ, kiểu, offset lấy từ DWARF của đúng file ELF đã nạp), không
   hard-code offset.
2. Nên thêm `diag_block_t` ở robot (một struct counter ổn định, có magic + version), để tool đọc
   một lần ~100 B và không vỡ khi đổi tên biến nội bộ. Cần decision ở `robot_att`.
3. Ứng viên thay log: SWO/ITM của ST-LINK V3 (không tốn UART). Đánh giá ở spike S4.

Hai probe chạy song song, chọn bằng serial: H755 `0030004A3235510837333439`, F446
`0670FF514988525067182431` (cắm "robot S02" và "remote S02" thì thêm vào `targets.yaml`; xem
câu hỏi 1).

## 3. Kiến trúc

```text
 Cửa sổ tool (web local 127.0.0.1, bọc thành app sau)
 +----------------------+----------------------+
 | Dashboard / đồ thị   |  Chat Claude Code    |
 +-----------+----------+----------+-----------+
             | WebSocket           | WebSocket
        +----v---------------------v-----------+
        |  rdt daemon (Python, FastAPI)        |
        |  targets | symbols(ELF) | decoders   |
        |  recorder | analyzers | safety gate  |
        |  claude bridge (Agent SDK)  <------- Claude Code (CLI, đăng nhập sẵn)
        +----+---------------+-----------------+      ^ tool MCP: đọc, vẽ, chú thích
             |               |                         |
        ST-LINK robot   ST-LINK remote + VCP      (cùng bộ tool cũng xuất ra
        (SWD)           (SWD + COM log)            MCP stdio cho phiên Claude khác)
```

- Một daemon giữ phần cứng; UI và Claude đều là client, nên thấy cùng một phiên đo.
- Backend probe: pyOCD (exclusive, đọc nhanh) hoặc STM32CubeProgrammer API; CubeIDE đang debug
  thì chuyển sang shared. Chọn ở spike S1. Nạp code vẫn dùng STM32_Programmer_CLI đã ghim.
- Ngôn ngữ: Python 3.12 (đã có trên máy). UI: Vite + Svelte + uPlot (đồ thị thời gian thực).
- Repo riêng `robot_diag` (dùng chung cho robot_att, robot_rc_rtos, robot_link).

## 4. Khung chat Claude Code trong UI

### 4.1 Nhúng bằng cách nào

| Cách | Mô tả | Đánh giá |
|---|---|---|
| **A. Claude Agent SDK (Python), khuyến nghị** | Daemon chạy Claude Code (cùng CLI, cùng đăng nhập) như thư viện: nhận luồng sự kiện có cấu trúc, gắn tool in-process, có callback duyệt quyền, resume phiên | Hiển thị được tool call, kế hoạch, tiến độ như Claude Code desktop; tool của ta là hàm Python gọi thẳng daemon |
| B. Chạy `claude -p --output-format stream-json` làm tiến trình con | Cùng luồng sự kiện, dùng cờ CLI (`--mcp-config`, `--resume`, `--permission-prompt-tool`) | Ít phụ thuộc hơn, nhưng tự lo nhiều việc hơn A |
| C. Nhúng terminal (xterm.js + ConPTY) chạy `claude` tương tác | Giống hệt CLI | Không có trạng thái có cấu trúc để vẽ UI; chỉ làm tab phụ |

Làm A; B là phương án dự phòng; C là tab "Terminal" tùy chọn. Tên API chính xác kiểm ở spike S3.

### 4.2 Hiển thị trạng thái giống Claude Code desktop

Từ luồng sự kiện hiển thị: tin nhắn Claude (stream từng chữ), thẻ tool call (tên, tham số, kết
quả, thời gian), **danh sách kế hoạch** (khi Claude cập nhật task list), thanh trạng thái (model,
chế độ quyền, token/chi phí/ngữ cảnh), nút dừng, lịch sử phiên và resume.

### 4.3 Claude điều khiển được UI (khác biệt chính so với chat thường)

Ngoài tool đọc dữ liệu (xem plan cũ §2.3), có nhóm tool **hiển thị**: `show_chart(series, window)`,
`annotate(time, text)`, `highlight_range`, `open_watch(names)`, `bookmark`. Câu trả lời kèm
đồ thị thật ở đúng khoảng thời gian, thay vì một đoạn số dài. Chiều ngược lại: nút "Hỏi Claude về
đoạn này" trên đồ thị gửi `view_context` (cửa sổ thời gian, chuỗi đang xem, thống kê) dưới dạng
tool `get_view_context`, không dán cả bảng số vào prompt.

### 4.4 Quyền và hồ sơ

- Hồ sơ **Phân tích** (mặc định): chỉ tool đọc/hiển thị của `robot-diag`, không sửa file, không Bash.
- Hồ sơ **Phát triển**: thêm Edit/Bash trong thư mục repo để Claude sửa firmware sau khi tìm ra lỗi.
- Tool ghi (`flash`, `reset`, `write_symbol`, lệnh vận tốc) luôn hiện **thẻ xác nhận trong UI**; bấm
  trong chat thôi chưa đủ. Daemon còn chặn thêm theo §6, kể cả khi đã duyệt.
- Dữ liệu từ board (dòng log, chuỗi banner) và file là **dữ liệu**, không phải lệnh: bộ phân tích
  chỉ đưa số và chuỗi đã escape vào ngữ cảnh.

## 5. Trực quan hóa

Bố cục màn hình chính:

```text
+--------------------------------------------------------------+----------------+
| [Remote S02: ●nối]  [Robot S02: ●nối]  phiên 14:02  ● ghi    | Chat           |
+------------------------------+-------------------------------+ (Claude Code)  |
| 1. Đường đi tín hiệu         | 2. Link LoRa                  |                |
| ADC→arbiter→CONTROL→[không   | frames/s, CRC, lost, dup,     | tin nhắn,      |
| trung]→ring→parser→input→    | truncated, uart_errors        | thẻ tool call, |
| kinematics→CAN rpm           | (tỉ lệ theo thời gian)        | kế hoạch       |
| mỗi chặng: giá trị + tuổi    |                               |                |
+------------------------------+-------------------------------+                |
| 3. Cờ & trạng thái           | 4. Sức khỏe RTOS / CAN        |                |
| connected failsafe ESTOP     | heap, stack từng task,        |                |
| armed(R4) INPUT_VALID        | FDCAN PSR/TEC/REC đã giải     |                |
+------------------------------+-------------------------------+                |
| 5. Dòng thời gian: log + frame RCL giải mã + chú thích        | [ô nhập] [Dừng]|
+--------------------------------------------------------------+----------------+
```

1. **Đường đi tín hiệu** (làm đầu tiên): chính là Flow 1 của `debug_guide` (§5) thành sơ đồ sống.
   Chặng nào ngừng cập nhật thì tô đỏ. Trả lời nhanh câu "dừng ở đâu".
2. **Link LoRa**: tỉ lệ theo thời gian của bộ đếm parser/filter/driver. Lost do remote khởi động lại
   (nhảy tới 255) được đánh dấu riêng, không lẫn với mất gói thật.
3. **Cờ và trạng thái** của cả hai phía, cạnh nhau.
4. **RTOS / CAN**: heap, stack, supervisor; PSR/ECR của FDCAN giải sẵn (LEC, error passive).
5. **Dòng thời gian** chung: log remote, frame `[tx]` giải mã bằng `rcl.py`, chú thích của
   analyzer và của Claude, bấm vào một điểm thì chat được gợi ý sẵn câu hỏi.

Hai phía **không chung đồng hồ**. Thời gian gắn ở máy tính khi nhận mẫu; độ trễ end-to-end suy ra
từ cạnh sự kiện (bấm e-stop trên remote tới khi cờ robot đổi) với sai số bằng chu kỳ poll cộng
trễ VCP. Giữ ghi chú sai số này ngay trên đồ thị. Ghi/replay: mỗi phiên một thư mục (mẫu, log,
hash ELF, git hash) để phân tích lại offline và cho Claude đọc sau.

## 6. An toàn (tóm tắt, chi tiết ở plan cũ §6)

- Giai đoạn đầu **chỉ đọc**. Không halt, không reset, không ghi bộ nhớ khi robot có thể chạy motor.
- Nạp code: so DEV_ID với ELF, so cấu hình sản phẩm (không nạp `SFF_*` lên remote đi cặp với
  robot_att), verify sau nạp, nạp theo cặp kiểm `RCL_VERSION`.
- Chưa xác nhận: khi H755 bị halt/reset, phanh driver (PC10) và DMKE về trạng thái an toàn chưa
  (debug_guide §2, §10 mục 6). Không cho reset từ xa trước khi kiểm.
- Cáp USB nối trực tiếp vào robot đang chạy motor: dùng hub có nguồn và nên cách ly USB.

## 7. Kế hoạch (có dây trước)

| Giai đoạn | Nội dung | Kiểm được khi | Ước lượng |
|---|---|---|---|
| **S. Spike** | S1: hai probe cùng lúc theo serial, đo số lần đọc/s của pyOCD và CubeProgrammer API trên F446 và H755. S2: pyelftools giải `s_lora_rx.lost` từ ELF robot_att, đối chiếu với offset đã biết. S3: Agent SDK: luồng sự kiện, tool in-process, callback duyệt quyền, resume, dùng lại đăng nhập. S4: SWO/ITM trên H755 | 4 con số/kết luận, chọn backend | 3-5 ngày |
| **D1. Lõi** | daemon, `targets.yaml`, symbol, watch, log VCP, recorder, CLI `rdt` | `rdt watch robot s_lora_rx.lost` chạy; ghi và đọc lại một phiên | 1-1,5 tuần |
| **D2. UI + đồ thị** | khung UI, mục 1-3 và 5 của §5, ghi/replay | Làm lại phiên đo Phase 0 từ UI, không cần PowerShell | 1,5-2 tuần |
| **D3. Chat + tool** | claude bridge, tool đọc/hiển thị, thẻ tool call, kế hoạch, thanh trạng thái, quyền, hồ sơ | Hỏi "link có mất gói không" ra đáp án kèm đồ thị Claude tự vẽ | 1,5-2 tuần |
| **D4. Analyzer + diag block** | luật chẩn đoán từ `task_history` (bảng triệu chứng); `diag_block_t` ở hai firmware (spec + C + Python cùng lúc); mục 4 của §5 | Analyzer tự gắn nhãn trên log cũ ("remote restart", "CAN ACK error") | 1-2 tuần |
| **D5. Kịch bản + nạp** | port `link_sweep.ps1`, nạp có cổng an toàn, nạp cặp | Sweep chạy từ UI ra bảng; nạp đúng build đúng board | 1-1,5 tuần |

Giá trị đến sớm: sau D1 + D2 đã thay `link_sweep.ps1` và việc đọc `s_lora_rx` bằng tay; sau D3 có
chat. Ước lượng thô, chỉnh lại sau spike.

## 8. Rủi ro chính

- Tốc độ đọc SWD đủ cho đồ thị ~20-50 Hz không (S1). Nếu không: giảm số biến, gom khối, hoặc dùng
  `diag_block_t`.
- H755 hai core: chắc chắn đọc được vùng SRAM của CM7 khi CM4 chạy, nhưng pyOCD có hỗ trợ H755 sẵn
  không là điều phải kiểm (S1); nếu không, dùng CubeProgrammer API.
- Agent SDK / CLI thay đổi nhanh: ghim phiên bản, ghi trong `toolchain.psd1`.
- Hai thứ tranh một probe: CubeIDE debug và tool. Quy ước: một lúc một bên, hoặc shared mode.
- Nội dung do Claude sinh ra điều khiển phần cứng: nên đã tách tool ghi, thẻ xác nhận ở UI, cổng
  an toàn ở daemon.

## 9. Câu hỏi cần quyết

1. "Robot S02" và "remote S02" là bo nào (MCU, ELF có symbol không)? Mỗi cái là một ST-LINK
   NUCLEO hay ST-LINK rời nối header SWD?
2. Chạy là web local trong browser/Claude desktop (khuyến nghị), hay cần cửa sổ app riêng (bọc
   Tauri/pywebview sau)?
3. Chat dùng Agent SDK (khuyến nghị) hay chỉ cần mở terminal Claude Code trong UI?
4. Chấp nhận thêm `diag_block_t` vào firmware robot (cần decision trong `robot_att`)?
5. Repo riêng `robot_diag` hay để trong `robot_link`?
