"""Bilingual reference data: what rdt monitors, what pyOCD and STM32_Programmer_CLI commands mean.

Single source for the UI "Reference" page (GET /api/reference) and the generated docs
(`scripts/gen_reference.py` -> docs/REFERENCE.en.md, docs/REFERENCE.vi.md). Every variable the dashboard reads
(`ui/src/panels.js`) must have an entry in MONITORED (tests/test_reference.py checks it).

`safety` of a command: read (reads only) | control (halts, resets or resumes the core) | write (changes flash, memory or
option bytes) | danger (can erase the chip or remove protection). rdt itself only runs `read` commands; flashing goes
through the gated Flash panel.
"""
from __future__ import annotations


def _v(path, target, panel, en, vi, kind="counter"):
    return {"name": path, "target": target, "panel": panel, "kind": kind, "en": en, "vi": vi}


MONITORED = [
    # --- remote (F446, robot_rc_rtos) ---
    _v("s_app_input.data.controls.drive_ud", "remote", "signal", "Drive up/down stick value the remote application reads from the operator.",
       "Giá trị cần lái tiến/lùi mà ứng dụng remote đọc từ người điều khiển.", "value"),
    _v("s_app_input.data.alive_tick", "remote", "signal", "Counter the input task increments each cycle; stops when the input task hangs.",
       "Bộ đếm task đầu vào tăng mỗi chu kỳ; đứng yên nghĩa là task đầu vào treo."),
    _v("s_tx.out.source", "remote", "signal", "Which input source the arbiter selected for the frame being sent.",
       "Nguồn đầu vào mà arbiter chọn cho frame đang gửi.", "value"),
    _v("s_tx.arbiter.armed", "remote", "signal,flags", "Arbiter armed state: the remote is allowed to send drive commands.",
       "Trạng thái armed của arbiter: remote được phép gửi lệnh lái.", "flag"),
    _v("s_tx.out.sent.drive_ud", "remote", "signal", "drive_ud value inside the last CONTROL frame the remote sent.",
       "Giá trị drive_ud nằm trong frame CONTROL cuối cùng remote gửi.", "value"),
    _v("s_tx.out.control_frames", "remote", "signal,link", "Count of CONTROL frames sent. A drop means the remote restarted.",
       "Số frame CONTROL đã gửi. Giảm nghĩa là remote khởi động lại."),
    _v("s_tx.out.tx_failures", "remote", "link", "Count of failed sends to the radio module (E22) or UART.",
       "Số lần gửi thất bại xuống module radio (E22) hoặc UART."),
    _v("s_tx.out.input_valid", "remote", "flags", "True when the remote has a valid operator input to send.",
       "Đúng khi remote có đầu vào người điều khiển hợp lệ để gửi.", "flag"),
    _v("s_tx.out.sent.estop", "remote", "flags", "ESTOP flag in the last CONTROL frame; set means the remote is asking the robot to stop.",
       "Cờ ESTOP trong frame CONTROL cuối; đang bật nghĩa là remote yêu cầu robot dừng khẩn cấp.", "flag"),
    _v("s_tx.out.sweep_step", "remote", "sweep", "Current step of the Phase 0 sweep build (send-rate test).",
       "Bước hiện tại của bản sweep Phase 0 (thử tốc độ gửi).", "value"),
    _v("s_tx.out.sweep_gap_ms", "remote", "sweep", "Gap between frames (ms) at the current sweep step.",
       "Khoảng cách giữa các frame (ms) ở bước sweep hiện tại.", "value"),
    _v("s_link.link_up", "remote", "flags", "Remote's own view that the link to the robot is up (telemetry received). Meaningful on SFF/MFF builds.",
       "Remote tự đánh giá link tới robot đang tốt (nhận được telemetry). Chỉ có ý nghĩa với bản SFF/MFF.", "flag"),
    _v("s_link.frames_ok", "remote", "link", "Telemetry frames from the robot received correctly.",
       "Số frame telemetry từ robot nhận đúng."),
    _v("s_link.frames_bad", "remote", "link", "Telemetry frames from the robot received corrupted.",
       "Số frame telemetry từ robot bị hỏng."),
    _v("s_link.frames_lost", "remote", "link", "Telemetry frames from the robot detected as missing (sequence gaps).",
       "Số frame telemetry từ robot bị mất (nhảy số thứ tự)."),
    # --- robot (H755, robot_s_rtos) ---
    _v("s_lora_rx.parser.stats.frames", "robot", "signal,link", "Frames the robot's LoRa parser decoded.",
       "Số frame parser LoRa của robot giải mã được."),
    _v("s_lora_rx.parser.stats.crc_errors", "robot", "link", "Frames dropped for a bad CRC (noise, wrong baud, remote not speaking RCL v1).",
       "Số frame bị bỏ vì sai CRC (nhiễu, sai baud, remote không nói RCL v1)."),
    _v("s_lora_rx.parser.stats.truncated", "robot", "link", "Frames cut short (remote sending slower than 500 ms or weak signal).",
       "Số frame bị cắt (remote gửi thưa hơn 500 ms hoặc sóng yếu)."),
    _v("s_lora_rx.filter.stats.accepted", "robot", "signal,sweep", "Frames the filter accepted (right link ID, in sequence).",
       "Số frame bộ lọc chấp nhận (đúng LINK_ID, đúng thứ tự)."),
    _v("s_lora_rx.filter.stats.lost", "robot", "link", "Frames missing by sequence number. A jump of 200 or more is a remote restart, not real loss.",
       "Số frame mất theo số thứ tự. Nhảy từ 200 trở lên là remote khởi động lại, không phải mất gói thật."),
    _v("s_lora_rx.filter.stats.duplicates", "robot", "link", "Frames repeating an already seen sequence number.",
       "Số frame lặp số thứ tự đã nhận."),
    _v("s_lora_rx.filter.stats.err_link_id", "robot", "analyzers", "Frames rejected because their LINK_ID differs from the one the robot locked.",
       "Số frame bị loại vì LINK_ID khác với LINK_ID robot đã chốt. Tăng nghĩa là cần reset robot."),
    _v("s_lora_rx.input.drive_ud", "robot", "signal", "drive_ud the robot's input stage holds after the filter.",
       "Giá trị drive_ud mà tầng input của robot đang giữ sau bộ lọc.", "value"),
    _v("s_lora_rx.control_frames", "robot", "signal", "Count of CONTROL frames delivered to the robot's input stage.",
       "Số frame CONTROL đã chuyển tới tầng input của robot."),
    _v("s_lora_rx.connected", "robot", "flags,analyzers", "Robot considers the remote connected (fresh valid frames).",
       "Robot coi remote đang kết nối (có frame hợp lệ mới).", "flag"),
    _v("s_lora_rx.input.connected", "robot", "flags", "Connected flag as seen at the robot's input stage.",
       "Cờ connected ở tầng input của robot.", "flag"),
    _v("s_lora_rx.input.button_emergency", "robot", "flags", "Emergency stop requested; set is a problem state.",
       "Yêu cầu dừng khẩn cấp; đang bật là trạng thái có vấn đề.", "flag"),
]

ANALYZERS = [
    ("remote_restart", "warn", "Remote's control_frames dropped: it reset (sequence back to 0).", "control_frames của remote giảm: remote reset (số thứ tự về 0)."),
    ("lost_jump", "info", "One step of `lost` of 200+: a remote restart, excluded from the loss rate.", "`lost` nhảy từ 200 trở lên trong một mẫu: remote khởi động lại, đã loại khỏi tỉ lệ mất."),
    ("link_loss", "info/warn/error", "Real loss percentage from `lost` against frames received (under 1 % info, under 5 % warn).", "Tỉ lệ mất gói thật theo `lost` so với số frame nhận (dưới 1 % info, dưới 5 % warn)."),
    ("robot_not_receiving", "error", "Remote keeps sending but the robot's parser frames stand still.", "Remote vẫn gửi nhưng frames của parser robot đứng yên."),
    ("remote_not_sending", "warn", "Neither the remote's counter nor the robot's frames move.", "Cả bộ đếm của remote lẫn frames của robot đều đứng."),
    ("crc_errors", "warn", "CRC errors counted by the robot.", "Robot đếm được lỗi CRC."),
    ("truncated", "info", "Truncated frames at the robot.", "Frame bị cắt ở robot."),
    ("remote_tx_failures", "warn", "Remote failed to send.", "Remote gửi thất bại."),
    ("remote_rx_bad", "info", "Remote received corrupted telemetry.", "Remote nhận telemetry hỏng."),
    ("connected_flap", "warn", "`connected` toggles repeatedly.", "`connected` bật/tắt liên tục."),
    ("frames_not_connected", "error", "Frames arrive but `connected` stays false (often a different LINK_ID was locked).", "Có frame nhưng `connected` vẫn false (thường robot đã chốt LINK_ID khác)."),
    ("remote_estop", "info", "Remote is sending the ESTOP flag.", "Remote đang gửi cờ ESTOP."),
    ("remote_link_down", "warn", "Remote reports link_up = false.", "Remote báo link_up = false."),
    ("sample_gap", "info", "A gap in samples (SWD read delayed): data around it needs care.", "Thiếu mẫu (đọc SWD bị trễ): số liệu quanh đó cần đọc cẩn thận."),
    ("log_watchdog / log_fault / log_stack", "warn", "A remote VCP log line mentions watchdog, a fault or a stack problem (quoted as data).", "Một dòng log VCP của remote nhắc tới watchdog, fault hoặc stack (trích như dữ liệu)."),
]


def _c(name, syntax, safety, en, vi, used=False):
    return {"name": name, "syntax": syntax, "safety": safety, "en": en, "vi": vi, "used_by_rdt": used}


PYOCD_API = [
    _c("ConnectHelper.session_with_chosen_probe", "session_with_chosen_probe(unique_id=<serial>, connect_mode='attach', halt_on_connect=False, resume_on_disconnect=False, options={'frequency': 4000000, 'target_override': 'cortex_m'})", "read",
       "Opens a debug session to one probe by serial. rdt uses attach mode (no halt, no reset) and the generic cortex_m target because pyOCD has no H755 pack.",
       "Mở phiên debug tới một probe theo serial. rdt dùng chế độ attach (không halt, không reset) và target cortex_m chung vì pyOCD không có pack H755.", True),
    _c("session.open() / close()", "session.open(); session.close()", "read",
       "Starts and releases the SWD connection. Releasing matters: an unclosed session blocks the next user of the probe.",
       "Mở và nhả kết nối SWD. Phải nhả: phiên không đóng sẽ chặn người dùng probe kế tiếp.", True),
    _c("target.read_memory_block8", "target.read_memory_block8(address, size) -> list[int]", "read",
       "Reads `size` bytes from target memory without stopping the core. This is how every monitored variable is sampled.",
       "Đọc `size` byte bộ nhớ target mà không dừng core. Mọi biến theo dõi được lấy mẫu bằng lệnh này.", True),
    _c("target.read32", "target.read32(address) -> int", "read",
       "Reads one 32-bit word (used by the spike scripts for debug registers).",
       "Đọc một từ 32 bit (script spike dùng để đọc thanh ghi debug).", False),
    _c("DebugProbeAggregator.get_all_connected_probes", "get_all_connected_probes(unique_id=None)", "read",
       "Lists attached probes; rdt matches the serials from targets.yaml.",
       "Liệt kê các probe đang cắm; rdt đối chiếu serial trong targets.yaml.", True),
    _c("target.write32 / write8", "target.write32(address, value)", "write",
       "Writes target memory or registers. Not used by the daemon; only spike S4's opt-in loopback wrote ITM/TPIU debug registers (restored afterwards).",
       "Ghi bộ nhớ hoặc thanh ghi target. Daemon không dùng; chỉ loopback S4 (tùy chọn) từng ghi thanh ghi debug ITM/TPIU rồi khôi phục.", False),
    _c("probe.swo_start / swo_read / swo_stop", "probe.swo_start(baud); probe.swo_read(); probe.swo_stop()", "read",
       "Captures SWO trace bytes through the ST-LINK. Spike S4 only; on the robot it returned no bytes (decision 0004).",
       "Bắt byte SWO qua ST-LINK. Chỉ trong spike S4; trên robot chưa nhận được byte nào (decision 0004).", False),
]

PYOCD_CLI = [
    _c("pyocd list", "pyocd list [--targets] [--probes]", "read", "Lists connected probes (with their unique IDs) or the supported targets.", "Liệt kê probe đang cắm (kèm unique ID) hoặc các target được hỗ trợ."),
    _c("pyocd commander", "pyocd commander -u <serial> -t cortex_m --connect attach [-c \"<cmd>\"]", "read",
       "Interactive or one-shot debug shell (alias `pyocd cmd`). `-u` selects the probe, `-t` the target type, `--connect attach` avoids halting the core.",
       "Shell debug tương tác hoặc chạy một lệnh (bí danh `pyocd cmd`). `-u` chọn probe, `-t` loại target, `--connect attach` để không dừng core."),
    _c("commander: status", "status", "read", "Shows whether the core is running or halted.", "Hiện core đang chạy hay đang halt."),
    _c("commander: read32 / read8", "read32 <addr> [<count>]", "read", "Reads 32-bit (or 8-bit) words from memory; the same access as rdt's sampling.", "Đọc từ 32 bit (hoặc 8 bit) từ bộ nhớ; cùng kiểu truy cập với lấy mẫu của rdt."),
    _c("commander: reg", "reg [<name>]", "read", "Shows core registers. Reads registers, so on a running core the values are a snapshot that may need a halt.", "Hiện thanh ghi core. Trên core đang chạy giá trị chỉ là ảnh chụp, có thể cần halt."),
    _c("commander: show map", "show map", "read", "Shows the target memory map pyOCD uses.", "Hiện bản đồ bộ nhớ target mà pyOCD dùng."),
    _c("commander: halt / go / step / reset", "halt | go | step | reset [halt]", "control", "Stops the core, resumes it, single-steps, or resets. On a robot with live motors these are unsafe; rdt never issues them.", "Dừng core, chạy tiếp, chạy từng lệnh, hoặc reset. Với robot đang có động cơ thì không an toàn; rdt không bao giờ gọi."),
    _c("commander: write32 / write8", "write32 <addr> <value>", "write", "Writes memory or registers. rdt's rule: never write target memory.", "Ghi bộ nhớ hoặc thanh ghi. Quy tắc của rdt: không bao giờ ghi bộ nhớ target."),
    _c("pyocd flash / load", "pyocd flash -t <target> <file.elf|hex|bin>", "write", "Programs flash with pyOCD. rdt flashes with STM32_Programmer_CLI instead (gated Flash panel).", "Nạp flash bằng pyOCD. rdt nạp bằng STM32_Programmer_CLI (khung Nạp firmware có chốt an toàn)."),
    _c("pyocd gdbserver", "pyocd gdbserver -u <serial>", "control", "Starts a GDB server on the probe (holds the probe exclusively; stop rdt first).", "Chạy GDB server trên probe (chiếm riêng probe; phải dừng rdt trước)."),
]

CUBE_CLI = [
    _c("-l st-link", "STM32_Programmer_CLI -l st-link", "read", "Lists ST-LINK probes with serial numbers and firmware versions. UI: Programmer CLI > List probes.", "Liệt kê probe ST-LINK kèm số serial và phiên bản firmware. UI: Programmer CLI > List probes.", True),
    _c("-c port=SWD", "-c port=SWD sn=<serial> mode=HOTPLUG [freq=<kHz>] [ap=<n>] [reset=<SWrst|HWrst|Crst>]", "read",
       "Connects to the target over SWD. `sn` picks the probe. `mode`: HOTPLUG attaches to the running target without halting or resetting (rdt's reads); NORMAL (default) connects and may halt or reset the core (used for flashing); UR connects under reset. `ap` picks the access port (core).",
       "Kết nối target qua SWD. `sn` chọn probe. `mode`: HOTPLUG gắn vào target đang chạy, không halt hay reset (dùng cho các lệnh đọc của rdt); NORMAL (mặc định) kết nối và có thể halt hoặc reset core (dùng khi nạp); UR kết nối trong lúc reset. `ap` chọn access port (core).", True),
    _c("-r32", "-r32 <addr> <size>", "read", "Reads `size` bytes starting at `addr` and prints 32-bit words. rdt limits it to flash and SRAM, 4-byte aligned, at most 4 KiB.", "Đọc `size` byte từ `addr` và in dưới dạng từ 32 bit. rdt giới hạn trong flash và SRAM, căn 4 byte, tối đa 4 KiB.", True),
    _c("-ob displ", "-ob displ", "read", "Displays the option bytes (read protection level, boot addresses, watchdog and bank settings).", "Hiện option byte (mức bảo vệ đọc, địa chỉ boot, watchdog, cấu hình bank).", True),
    _c("-w", "-w <file.elf|hex|bin> [<addr>]", "write", "Programs the file into flash (alias `-d`). .bin needs an address. rdt uses it only in the gated Flash panel, with .elf images.", "Nạp file vào flash (bí danh `-d`). .bin cần địa chỉ. rdt chỉ dùng trong khung Nạp firmware có chốt an toàn, với file .elf.", True),
    _c("-v", "-v", "read", "Verifies flash content against the file after programming.", "Kiểm tra nội dung flash với file sau khi nạp.", True),
    _c("-rst", "-rst", "control", "Resets the core after the other commands finish. rdt adds it to the flash command so the new firmware starts.", "Reset core sau khi các lệnh khác xong. rdt thêm vào lệnh nạp để firmware mới chạy.", True),
    _c("-hardRst", "-hardRst", "control", "Hardware reset through the NRST line. Not used by rdt.", "Reset cứng qua chân NRST. rdt không dùng."),
    _c("-halt / -run", "-halt | -run", "control", "Halts the core / starts execution. Not used by rdt (read-only policy).", "Dừng core / cho chạy. rdt không dùng (chính sách chỉ đọc)."),
    _c("-e", "-e all | -e <sector,...>", "danger", "Erases the whole flash or the listed sectors. Not exposed by rdt; flashing erases only what the programmed segments need.", "Xóa toàn bộ flash hoặc các sector chỉ định. rdt không cung cấp; lệnh nạp chỉ xóa phần cần cho các segment được nạp."),
    _c("-ob <option>=<value>", "-ob RDP=0xAA | -ob BOR_LEV=...", "danger", "Writes option bytes. Setting RDP back to level 0 mass-erases the flash. Never run from rdt.", "Ghi option byte. Đặt RDP về level 0 sẽ xóa sạch flash. rdt không bao giờ chạy."),
    _c("-vb / -log", "-vb <1|2|3> | -log <file>", "read", "Verbosity of the output / writes the output to a log file.", "Mức chi tiết của output / ghi output ra file log."),
]

SECTIONS = [
    {"id": "monitored", "title": {"en": "Monitored data", "vi": "Dữ liệu đang theo dõi"},
     "intro": {"en": "Variables read over SWD without stopping the cores. Names are resolved from the flashed ELF (never hard-coded offsets).",
               "vi": "Các biến được đọc qua SWD mà không dừng core. Tên biến được giải từ file ELF đã nạp (không gán cứng offset)."}},
    {"id": "analyzers", "title": {"en": "Automatic diagnosis rules", "vi": "Luật chẩn đoán tự động"},
     "intro": {"en": "Findings state evidence and what to check next; they do not claim a cause as fact.",
               "vi": "Phát hiện nêu bằng chứng và việc cần kiểm tra tiếp; không khẳng định nguyên nhân."}},
    {"id": "pyocd_api", "title": {"en": "pyOCD functions rdt uses", "vi": "Hàm pyOCD mà rdt dùng"},
     "intro": {"en": "Python API (pyOCD 0.46.1).", "vi": "API Python (pyOCD 0.46.1)."}},
    {"id": "pyocd_cli", "title": {"en": "pyOCD command line", "vi": "Dòng lệnh pyOCD"},
     "intro": {"en": "For manual debugging; stop rdt first because one probe serves one session. rdt itself only reads.",
               "vi": "Để debug thủ công; phải dừng rdt trước vì một probe chỉ phục vụ một phiên. Bản thân rdt chỉ đọc."}},
    {"id": "cube_cli", "title": {"en": "STM32_Programmer_CLI", "vi": "STM32_Programmer_CLI"},
     "intro": {"en": "STM32CubeProgrammer command line (2.20.0). The Programmer CLI page runs only the read commands; flashing is in the gated Flash panel.",
               "vi": "Dòng lệnh STM32CubeProgrammer (2.20.0). Trang Programmer CLI chỉ chạy các lệnh đọc; nạp firmware nằm ở khung Nạp có chốt an toàn."}},
]

SAFETY = {
    "read": {"en": "read-only", "vi": "chỉ đọc"},
    "control": {"en": "controls the core (halt/reset/run)", "vi": "điều khiển core (halt/reset/chạy)"},
    "write": {"en": "writes the target", "vi": "ghi vào target"},
    "danger": {"en": "dangerous (erase / protection)", "vi": "nguy hiểm (xóa / bảo vệ)"},
}

def to_markdown(lang: str) -> str:
    """The docs/REFERENCE.<lang>.md text (generated; do not edit the files by hand)."""
    en = lang == "en"
    head = ("# rdt reference: monitored data and command lists" if en else "# Tham khảo rdt: dữ liệu theo dõi và danh sách lệnh")
    note = ("Generated from `rdt/reference.py` by `scripts/gen_reference.py`. Do not edit by hand." if en
            else "Sinh tự động từ `rdt/reference.py` bằng `scripts/gen_reference.py`. Không sửa tay.")
    out = [head, "", note, ""]
    for sec in SECTIONS:
        out += [f"## {sec['title'][lang]}", "", sec["intro"][lang], ""]
        key = sec["id"]
        if key == "monitored":
            out += ["| " + " | ".join(["Variable", "Board", "Shown in", "Meaning"] if en else ["Biến", "Board", "Hiển thị ở", "Ý nghĩa"]) + " |",
                    "|---|---|---|---|"]
            out += [f"| `{m['name']}` | {m['target']} | {m['panel']} | {m[lang]} |" for m in MONITORED]
        elif key == "analyzers":
            out += ["| " + " | ".join(["Rule", "Severity", "Meaning"] if en else ["Luật", "Mức", "Ý nghĩa"]) + " |", "|---|---|---|"]
            out += [f"| `{i}` | {s} | {e if en else v} |" for i, s, e, v in ANALYZERS]
        else:
            items = REFERENCE[key]
            out += ["| " + " | ".join(["Command", "Syntax", "Safety", "Meaning", "rdt uses it"] if en else ["Lệnh", "Cú pháp", "An toàn", "Ý nghĩa", "rdt dùng"]) + " |",
                    "|---|---|---|---|---|"]
            for c in items:
                used = ("yes" if en else "có") if c["used_by_rdt"] else ("no" if en else "không")
                out.append(f"| `{c['name']}` | `{c['syntax'].replace('|', '\\|')}` | {SAFETY[c['safety']][lang]} | {c[lang]} | {used} |")
        out.append("")
    return "\n".join(out)


REFERENCE = {
    "sections": SECTIONS,
    "safety": SAFETY,
    "monitored": MONITORED,
    "analyzers": [{"id": i, "severity": s, "en": e, "vi": v} for i, s, e, v in ANALYZERS],
    "pyocd_api": PYOCD_API,
    "pyocd_cli": PYOCD_CLI,
    "cube_cli": CUBE_CLI,
}
