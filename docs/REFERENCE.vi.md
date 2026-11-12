# Tham khảo rdt: dữ liệu theo dõi và danh sách lệnh

Sinh tự động từ `rdt/reference.py` bằng `scripts/gen_reference.py`. Không sửa tay.

## Dữ liệu đang theo dõi

Các biến được đọc qua SWD mà không dừng core. Tên biến được giải từ file ELF đã nạp (không gán cứng offset).

| Biến | Board | Hiển thị ở | Ý nghĩa |
|---|---|---|---|
| `s_app_input.data.controls.drive_ud` | remote | signal | Giá trị cần lái tiến/lùi mà ứng dụng remote đọc từ người điều khiển. |
| `s_app_input.data.alive_tick` | remote | signal | Bộ đếm task đầu vào tăng mỗi chu kỳ; đứng yên nghĩa là task đầu vào treo. |
| `s_tx.out.source` | remote | signal | Nguồn đầu vào mà arbiter chọn cho frame đang gửi. |
| `s_tx.arbiter.armed` | remote | signal,flags | Trạng thái armed của arbiter: remote được phép gửi lệnh lái. |
| `s_tx.out.sent.drive_ud` | remote | signal | Giá trị drive_ud nằm trong frame CONTROL cuối cùng remote gửi. |
| `s_tx.out.control_frames` | remote | signal,link | Số frame CONTROL đã gửi. Giảm nghĩa là remote khởi động lại. |
| `s_tx.out.tx_failures` | remote | link | Số lần gửi thất bại xuống module radio (E22) hoặc UART. |
| `s_tx.out.input_valid` | remote | flags | Đúng khi remote có đầu vào người điều khiển hợp lệ để gửi. |
| `s_tx.out.sent.estop` | remote | flags | Cờ ESTOP trong frame CONTROL cuối; đang bật nghĩa là remote yêu cầu robot dừng khẩn cấp. |
| `s_tx.out.sweep_step` | remote | sweep | Bước hiện tại của bản sweep Phase 0 (thử tốc độ gửi). |
| `s_tx.out.sweep_gap_ms` | remote | sweep | Khoảng cách giữa các frame (ms) ở bước sweep hiện tại. |
| `s_link.link_up` | remote | flags | Remote tự đánh giá link tới robot đang tốt (nhận được telemetry). Chỉ có ý nghĩa với bản SFF/MFF. |
| `s_link.frames_ok` | remote | link | Số frame telemetry từ robot nhận đúng. |
| `s_link.frames_bad` | remote | link | Số frame telemetry từ robot bị hỏng. |
| `s_link.frames_lost` | remote | link | Số frame telemetry từ robot bị mất (nhảy số thứ tự). |
| `s_tx.out.frame` | remote | frames | Frame RCL cuối cùng remote đã dựng để gửi (bộ đệm 58 byte; `frame_len` cho biết frame dài bao nhiêu byte). |
| `s_tx.out.frame_len` | remote | frames | Độ dài (byte) của frame trong `s_tx.out.frame`. |
| `s_rx.parser.buf` | remote | frames | Bộ đệm byte của parser nhận ở remote; giữ frame telemetry cuối cùng từ robot cho tới khi frame sau ghi đè. |
| `s_lora_rx.parser.buf` | robot | frames | Bộ đệm byte của parser nhận ở robot; giữ frame CONTROL cuối cùng từ remote cho tới khi frame sau ghi đè. |
| `s_lora_rx.parser.stats.frames` | robot | signal,link | Số frame parser LoRa của robot giải mã được. |
| `s_lora_rx.parser.stats.crc_errors` | robot | link | Số frame bị bỏ vì sai CRC (nhiễu, sai baud, remote không nói RCL v1). |
| `s_lora_rx.parser.stats.truncated` | robot | link | Số frame bị cắt (remote gửi thưa hơn 500 ms hoặc sóng yếu). |
| `s_lora_rx.filter.stats.accepted` | robot | signal,sweep | Số frame bộ lọc chấp nhận (đúng LINK_ID, đúng thứ tự). |
| `s_lora_rx.filter.stats.lost` | robot | link | Số frame mất theo số thứ tự. Nhảy từ 200 trở lên là remote khởi động lại, không phải mất gói thật. |
| `s_lora_rx.filter.stats.duplicates` | robot | link | Số frame lặp số thứ tự đã nhận. |
| `s_lora_rx.filter.stats.err_link_id` | robot | analyzers | Số frame bị loại vì LINK_ID khác với LINK_ID robot đã chốt. Tăng nghĩa là cần reset robot. |
| `s_lora_rx.input.drive_ud` | robot | signal | Giá trị drive_ud mà tầng input của robot đang giữ sau bộ lọc. |
| `s_lora_rx.control_frames` | robot | signal | Số frame CONTROL đã chuyển tới tầng input của robot. |
| `s_lora_rx.connected` | robot | flags,analyzers | Robot coi remote đang kết nối (có frame hợp lệ mới). |
| `s_lora_rx.input.connected` | robot | flags | Cờ connected ở tầng input của robot. |
| `s_lora_rx.input.button_emergency` | robot | flags | Yêu cầu dừng khẩn cấp; đang bật là trạng thái có vấn đề. |

## Luật chẩn đoán tự động

Phát hiện nêu bằng chứng và việc cần kiểm tra tiếp; không khẳng định nguyên nhân.

| Luật | Mức | Ý nghĩa |
|---|---|---|
| `remote_restart` | warn | control_frames của remote giảm: remote reset (số thứ tự về 0). |
| `lost_jump` | info | `lost` nhảy từ 200 trở lên trong một mẫu: remote khởi động lại, đã loại khỏi tỉ lệ mất. |
| `link_loss` | info/warn/error | Tỉ lệ mất gói thật theo `lost` so với số frame nhận (dưới 1 % info, dưới 5 % warn). |
| `robot_not_receiving` | error | Remote vẫn gửi nhưng frames của parser robot đứng yên. |
| `remote_not_sending` | warn | Cả bộ đếm của remote lẫn frames của robot đều đứng. |
| `crc_errors` | warn | Robot đếm được lỗi CRC. |
| `truncated` | info | Frame bị cắt ở robot. |
| `remote_tx_failures` | warn | Remote gửi thất bại. |
| `remote_rx_bad` | info | Remote nhận telemetry hỏng. |
| `connected_flap` | warn | `connected` bật/tắt liên tục. |
| `frames_not_connected` | error | Có frame nhưng `connected` vẫn false (thường robot đã chốt LINK_ID khác). |
| `remote_estop` | info | Remote đang gửi cờ ESTOP. |
| `remote_link_down` | warn | Remote báo link_up = false. |
| `sample_gap` | info | Thiếu mẫu (đọc SWD bị trễ): số liệu quanh đó cần đọc cẩn thận. |
| `log_watchdog / log_fault / log_stack` | warn | Một dòng log VCP của remote nhắc tới watchdog, fault hoặc stack (trích như dữ liệu). |

## Hàm pyOCD mà rdt dùng

API Python (pyOCD 0.46.1).

| Lệnh | Cú pháp | An toàn | Ý nghĩa | rdt dùng |
|---|---|---|---|---|
| `ConnectHelper.session_with_chosen_probe` | `session_with_chosen_probe(unique_id=<serial>, connect_mode='attach', halt_on_connect=False, resume_on_disconnect=False, options={'frequency': 4000000, 'target_override': 'cortex_m'})` | chỉ đọc | Mở phiên debug tới một probe theo serial. rdt dùng chế độ attach (không halt, không reset) và target cortex_m chung vì pyOCD không có pack H755. | có |
| `session.open() / close()` | `session.open(); session.close()` | chỉ đọc | Mở và nhả kết nối SWD. Phải nhả: phiên không đóng sẽ chặn người dùng probe kế tiếp. | có |
| `target.read_memory_block8` | `target.read_memory_block8(address, size) -> list[int]` | chỉ đọc | Đọc `size` byte bộ nhớ target mà không dừng core. Mọi biến theo dõi được lấy mẫu bằng lệnh này. | có |
| `target.read32` | `target.read32(address) -> int` | chỉ đọc | Đọc một từ 32 bit (script spike dùng để đọc thanh ghi debug). | không |
| `DebugProbeAggregator.get_all_connected_probes` | `get_all_connected_probes(unique_id=None)` | chỉ đọc | Liệt kê các probe đang cắm; rdt đối chiếu serial trong targets.yaml. | có |
| `target.write32 / write8` | `target.write32(address, value)` | ghi vào target | Ghi bộ nhớ hoặc thanh ghi target. Daemon không dùng; chỉ loopback S4 (tùy chọn) từng ghi thanh ghi debug ITM/TPIU rồi khôi phục. | không |
| `probe.swo_start / swo_read / swo_stop` | `probe.swo_start(baud); probe.swo_read(); probe.swo_stop()` | chỉ đọc | Bắt byte SWO qua ST-LINK. Chỉ trong spike S4; trên robot chưa nhận được byte nào (decision 0004). | không |

## Dòng lệnh pyOCD

Để debug thủ công; phải dừng rdt trước vì một probe chỉ phục vụ một phiên. Bản thân rdt chỉ đọc.

| Lệnh | Cú pháp | An toàn | Ý nghĩa | rdt dùng |
|---|---|---|---|---|
| `pyocd list` | `pyocd list [--targets] [--probes]` | chỉ đọc | Liệt kê probe đang cắm (kèm unique ID) hoặc các target được hỗ trợ. | không |
| `pyocd commander` | `pyocd commander -u <serial> -t cortex_m --connect attach [-c "<cmd>"]` | chỉ đọc | Shell debug tương tác hoặc chạy một lệnh (bí danh `pyocd cmd`). `-u` chọn probe, `-t` loại target, `--connect attach` để không dừng core. | không |
| `commander: status` | `status` | chỉ đọc | Hiện core đang chạy hay đang halt. | không |
| `commander: read32 / read8` | `read32 <addr> [<count>]` | chỉ đọc | Đọc từ 32 bit (hoặc 8 bit) từ bộ nhớ; cùng kiểu truy cập với lấy mẫu của rdt. | không |
| `commander: reg` | `reg [<name>]` | chỉ đọc | Hiện thanh ghi core. Trên core đang chạy giá trị chỉ là ảnh chụp, có thể cần halt. | không |
| `commander: show map` | `show map` | chỉ đọc | Hiện bản đồ bộ nhớ target mà pyOCD dùng. | không |
| `commander: halt / go / step / reset` | `halt \| go \| step \| reset [halt]` | điều khiển core (halt/reset/chạy) | Dừng core, chạy tiếp, chạy từng lệnh, hoặc reset. Với robot đang có động cơ thì không an toàn; rdt không bao giờ gọi. | không |
| `commander: write32 / write8` | `write32 <addr> <value>` | ghi vào target | Ghi bộ nhớ hoặc thanh ghi. Quy tắc của rdt: không bao giờ ghi bộ nhớ target. | không |
| `pyocd flash / load` | `pyocd flash -t <target> <file.elf\|hex\|bin>` | ghi vào target | Nạp flash bằng pyOCD. rdt nạp bằng STM32_Programmer_CLI (khung Nạp firmware có chốt an toàn). | không |
| `pyocd gdbserver` | `pyocd gdbserver -u <serial>` | điều khiển core (halt/reset/chạy) | Chạy GDB server trên probe (chiếm riêng probe; phải dừng rdt trước). | không |

## STM32_Programmer_CLI

Dòng lệnh STM32CubeProgrammer (2.20.0). Trang Programmer CLI chỉ chạy các lệnh đọc; nạp firmware nằm ở khung Nạp có chốt an toàn.

| Lệnh | Cú pháp | An toàn | Ý nghĩa | rdt dùng |
|---|---|---|---|---|
| `-l st-link` | `STM32_Programmer_CLI -l st-link` | chỉ đọc | Liệt kê probe ST-LINK kèm số serial và phiên bản firmware. UI: Programmer CLI > List probes. | có |
| `-c port=SWD` | `-c port=SWD sn=<serial> mode=HOTPLUG [freq=<kHz>] [ap=<n>] [reset=<SWrst\|HWrst\|Crst>]` | chỉ đọc | Kết nối target qua SWD. `sn` chọn probe. `mode`: HOTPLUG gắn vào target đang chạy, không halt hay reset (dùng cho các lệnh đọc của rdt); NORMAL (mặc định) kết nối và có thể halt hoặc reset core (dùng khi nạp); UR kết nối trong lúc reset. `ap` chọn access port (core). | có |
| `-r32` | `-r32 <addr> <size>` | chỉ đọc | Đọc `size` byte từ `addr` và in dưới dạng từ 32 bit. rdt giới hạn trong flash và SRAM, căn 4 byte, tối đa 4 KiB. | có |
| `-ob displ` | `-ob displ` | chỉ đọc | Hiện option byte (mức bảo vệ đọc, địa chỉ boot, watchdog, cấu hình bank). | có |
| `-w` | `-w <file.elf\|hex\|bin> [<addr>]` | ghi vào target | Nạp file vào flash (bí danh `-d`). .bin cần địa chỉ. rdt chỉ dùng trong khung Nạp firmware có chốt an toàn, với file .elf. | có |
| `-v` | `-v` | chỉ đọc | Kiểm tra nội dung flash với file sau khi nạp. | có |
| `-rst` | `-rst` | điều khiển core (halt/reset/chạy) | Reset core sau khi các lệnh khác xong. rdt thêm vào lệnh nạp để firmware mới chạy. | có |
| `-hardRst` | `-hardRst` | điều khiển core (halt/reset/chạy) | Reset cứng qua chân NRST. rdt không dùng. | không |
| `-halt / -run` | `-halt \| -run` | điều khiển core (halt/reset/chạy) | Dừng core / cho chạy. rdt không dùng (chính sách chỉ đọc). | không |
| `-e` | `-e all \| -e <sector,...>` | nguy hiểm (xóa / bảo vệ) | Xóa toàn bộ flash hoặc các sector chỉ định. rdt không cung cấp; lệnh nạp chỉ xóa phần cần cho các segment được nạp. | không |
| `-ob <option>=<value>` | `-ob RDP=0xAA \| -ob BOR_LEV=...` | nguy hiểm (xóa / bảo vệ) | Ghi option byte. Đặt RDP về level 0 sẽ xóa sạch flash. rdt không bao giờ chạy. | không |
| `-vb / -log` | `-vb <1\|2\|3> \| -log <file>` | chỉ đọc | Mức chi tiết của output / ghi output ra file log. | không |
