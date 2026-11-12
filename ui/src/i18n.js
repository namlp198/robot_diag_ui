// Theme (dark default, light) and language (vi/en) stores, persisted in localStorage; `t` is the translate function store.
import { writable, derived, get } from 'svelte/store';

const read = (k, ok, dflt) => { try { const v = localStorage.getItem(k); return ok.includes(v) ? v : dflt; } catch { return dflt; } };
const save = (k, v) => { try { localStorage.setItem(k, v); } catch { /* private mode: not persisted */ } };

export const theme = writable(read('rdt.theme', ['dark', 'light'], 'dark'));
export const lang = writable(read('rdt.lang', ['vi', 'en'], 'vi'));

theme.subscribe((v) => { document.documentElement.dataset.theme = v; save('rdt.theme', v); });
lang.subscribe((v) => { document.documentElement.lang = v; save('rdt.lang', v); });
export const toggleTheme = () => theme.update((v) => (v === 'dark' ? 'light' : 'dark'));
export const toggleLang = () => lang.update((v) => (v === 'vi' ? 'en' : 'vi'));

const D = {
  vi: {
    'conn.live': 'daemon nối', 'conn.replay': 'xem lại {name}', 'conn.offline': 'daemon chưa chạy (rdt serve)',
    'target.reads': '{n} đọc', 'target.fail': ', {n} lỗi', 'target.idle': 'không theo dõi',
    'hdr.vcp': 'log remote', 'hdr.vcpTip': 'VCP của remote; robot không có VCP dùng được',
    'hdr.start': 'Bắt đầu đọc', 'hdr.stop': 'Dừng', 'hdr.rec': '● Ghi phiên', 'hdr.recording': '■ Ghi {name}', 'hdr.live': 'Về trực tiếp',
    'hdr.sessions': 'phiên đã ghi…', 'hdr.open': 'Mở', 'hdr.themeTip': 'Đổi giao diện sáng/tối', 'hdr.langTip': 'Language: English / Tiếng Việt',
    'nav.dashboard': 'Bảng điều khiển', 'nav.cli': 'Programmer CLI', 'nav.reference': 'Tham khảo',
    'sig.title': '1. Đường đi tín hiệu', 'sig.moving': 'đang đổi', 'sig.stuck': 'đứng {s} s', 'sig.armed': 'armed', 'sig.disarmed': 'disarmed',
    'sig.note': 'Đỏ: bộ đếm của chặng không đổi quá {s} s. Xám: chặng chưa có biến để đọc.',
    'stage.app': 'Remote: ứng dụng/đầu vào', 'stage.arb': 'Remote: arbiter', 'stage.out': 'Remote: CONTROL gửi đi', 'stage.air': 'Không trung (LoRa)',
    'stage.par': 'Robot: parser', 'stage.flt': 'Robot: filter', 'stage.inp': 'Robot: input', 'stage.can': 'Kinematics → CAN rpm',
    'stage.noVar': 'không có biến', 'stage.noVarYet': 'chưa có biến',
    'link.title': '2. Link LoRa (sự kiện / giây)', 'link.robot': 'Robot (H755): nhận', 'link.remote': 'Remote (F446): gửi và nhận',
    'link.note': 'Hai board không chung đồng hồ: trục thời gian là đồng hồ máy tính lúc nhận mẫu, sai số bằng chu kỳ poll.',
    'flags.title': '3. Cờ và trạng thái', 'flag.sentEstop': 'remote ESTOP gửi',
    'find.title': 'Chẩn đoán tự động', 'find.mark': 'Đánh dấu trên đồ thị', 'find.ask': 'Hỏi Claude',
    'find.none': 'Chưa có phát hiện nào. Quy tắc lấy từ bảng triệu chứng của debug_guide và task_history; biến thiếu thì quy tắc bị bỏ qua, không đoán.',
    'find.askText': 'Giải thích phát hiện "{title}" ({target}, t={t0}–{t1} s) và kiểm tra bằng số liệu.',
    'cc.title': 'Đồ thị Claude vẽ', 'cc.chart': 'đồ thị', 'cc.band': 'vùng {t0}–{t1} s {label}',
    'sweep.title': 'Sweep Phase 0 (mất gói theo tốc độ gửi)', 'sweep.calc': 'Tính từ {src}', 'sweep.live': 'dữ liệu trực tiếp', 'sweep.replay': 'phiên đang xem',
    'sweep.csv': 'Tải CSV', 'sweep.hint': 'Remote phải chạy bản sweep và được reset sau khi bắt đầu đọc. rdt chỉ quan sát, không điều khiển remote.',
    'sweep.cols': 'gap ms|giây|gửi|robot rx|accepted|lost|loss %|crc', 'sweep.restart': ' (−{n} restart)',
    'sweep.src': 'Ranh giới bước lấy từ {src} theo đồng hồ máy tính: sai số một chu kỳ poll.', 'sweep.srcVcp': 'log VCP', 'sweep.srcVar': 'biến sweep_step',
    'tl.title': '5. Dòng thời gian', 'tl.count': '{n} mục (log VCP remote, đổi cờ, lỗi đọc)', 'tl.none': 'chưa có sự kiện',
    'flash.title': 'Nạp firmware (có chốt an toàn)', 'flash.warn': 'Ghi vào board thật. Chỉ nhận file .elf khớp danh sách cho phép của board, kiểm DEV_ID, và cần gõ đúng cụm xác nhận. Claude không có công cụ nạp.',
    'flash.dry': 'Kiểm tra (không ghi)', 'flash.stopFirst': 'Dừng đọc trước: nạp cần dùng riêng probe.', 'flash.already': 'Board đang chạy đúng image này; nạp lại là không đổi gì.',
    'flash.safe': 'Bánh đã kê khỏi mặt đất, tôi đứng cạnh robot và sẵn sàng tắt nguồn ngay', 'flash.typeExactly': 'Gõ đúng:', 'flash.go': 'Nạp',
    'flash.rejected': 'Kế hoạch bị từ chối: sửa các mục ✕ rồi kiểm tra lại.', 'flash.done': 'Đã nạp', 'flash.failed': 'Nạp lỗi',
    'flash.after': '(mã {rc}); so lại flash với ELF: {v}', 'flash.vNone': 'không chạy', 'flash.vOk': 'khớp', 'flash.vBad': 'KHÔNG khớp',
    'chat.title': 'Chat Claude', 'chat.noModel': 'chưa kết nối', 'chat.new': 'Mới', 'chat.newTip': 'Cuộc trò chuyện mới',
    'chat.login': 'Chat dùng bản Claude Code đi kèm SDK, chưa đăng nhập. Chạy một lần trong terminal rồi hỏi lại:',
    'chat.empty': 'Hỏi về dữ liệu đang xem, ví dụ: "link có mất gói không?". Claude chỉ có tool đọc và hiển thị; không ghi, không reset, không nạp.',
    'chat.placeholder': 'Hỏi Claude… (Enter gửi)', 'chat.send': 'Gửi', 'chat.stop': 'Dừng',
    'cli.title': 'STM32_Programmer_CLI (chỉ đọc)', 'cli.intro': 'Chạy các lệnh CLI chỉ đọc qua whitelist; kết nối HOTPLUG (không halt, không reset). Nạp firmware vẫn ở khung "Nạp firmware" trên Bảng điều khiển.',
    'cli.stopFirst': 'Dừng đọc trước: CLI cần dùng riêng probe.', 'cli.command': 'Lệnh', 'cli.target': 'Board', 'cli.address': 'Địa chỉ', 'cli.size': 'Số byte',
    'cli.preview': 'Xem lệnh', 'cli.run': 'Chạy', 'cli.exact': 'Dòng lệnh sẽ chạy:', 'cli.output': 'Kết quả (rc {rc}):',
    'cli.c.list': 'Liệt kê probe ST-LINK', 'cli.c.info': 'Thông tin thiết bị (chỉ kết nối)', 'cli.c.read32': 'Đọc bộ nhớ (-r32)', 'cli.c.ob_display': 'Hiện option byte',
    'cli.hint.list': 'Liệt kê các ST-LINK đang cắm kèm serial.', 'cli.hint.info': 'Kết nối HOTPLUG và in thông tin thiết bị/core.',
    'cli.hint.read32': 'Đọc trong flash hoặc SRAM, căn 4 byte, tối đa 4096 byte. Không đọc vùng ngoại vi.', 'cli.hint.ob_display': 'Hiện option byte (RDP, boot, watchdog...). Chỉ đọc.',
    'ref.title': 'Tham khảo', 'ref.search': 'Tìm…', 'ref.docs': 'Bản Markdown: docs/REFERENCE.vi.md', 'ref.used': 'rdt dùng', 'ref.cols.var': 'Biến',
    'ref.safety': 'An toàn', 'ref.board': 'Board', 'ref.shown': 'Hiển thị ở', 'ref.copy': 'Chép', 'ref.noMatch': 'Không có mục khớp.', 'ref.loadFail': 'Không tải được tham khảo: {e}',
    'ref.safety.all': 'mọi mức',
    'tl.kind.all': 'tất cả', 'tl.kind.log': 'log', 'tl.kind.flag': 'cờ', 'tl.kind.finding': 'chẩn đoán', 'tl.kind.note': 'ghi chú', 'tl.kind.error': 'lỗi',
    'err.stopFirst': 'Hãy dừng đọc trước: thao tác này cần dùng riêng probe.', 'err.alreadyRunning': 'Đang đọc rồi; hãy dừng trước.', 'err.notRunning': 'Chưa bắt đầu đọc.',
    'err.flashBusy': 'Đang nạp firmware.', 'err.local': 'Chỉ cho phép truy cập từ máy này.', 'err.fw': 'FIRMWARE KHÔNG KHỚP: {a}/{b} đoạn flash khác với ELF. Bạn đang xem biến theo ELF không phải là firmware đang chạy.',
    'err.noSdk': 'Chat cần claude-agent-sdk (pip install -e .[chat]).',
    'flash.check.image_allowed_for_target': 'File nằm trong danh sách cho phép', 'flash.check.image_inside_flash_range': 'Image nằm trong vùng flash của board',
    'flash.check.probe_attached': 'Probe đã cắm', 'flash.check.board_dev_id': 'DEV_ID của board đúng',
    'nav.frames': 'Gói tin', 'nav.expr': 'Live Expressions', 'nav.settings': 'Cài đặt',
    'chat.ready': 'sẵn sàng', 'chat.needLogin': 'chưa đăng nhập', 'chat.noSdk': 'thiếu SDK', 'chat.unknown': 'chưa rõ trạng thái',
    'chat.loginTip': 'Chạy một lần: .venv\\Lib\\site-packages\\claude_agent_sdk\\_bundled\\claude.exe auth login',
    'fr.title': 'Gói tin RCL (frame đầy đủ)', 'fr.src.remote_tx': 'Remote gửi → robot', 'fr.src.robot_rx': 'Robot nhận', 'fr.src.remote_rx': 'Remote nhận (từ robot)',
    'fr.none': 'chưa thấy frame', 'fr.needWatch': 'Bấm "Bắt đầu đọc": các bộ đệm frame được đọc cùng với các biến khác.',
    'fr.match': 'Remote gửi tới SEQ {tx}, robot nhận tới SEQ {rx}: chênh {d} frame (có thể do chu kỳ đọc).', 'fr.noMatch': 'Chưa có đủ dữ liệu hai phía để so SEQ.',
    'fr.history': 'Lịch sử frame', 'fr.filter': 'Nguồn', 'fr.all': 'tất cả', 'fr.inspect': 'Chi tiết frame', 'fr.pickRow': 'Chọn một frame ở bảng lịch sử hoặc một thẻ phía trên.',
    'fr.cols': 'thời gian (s)|nguồn|loại|SEQ|LINK_ID|byte|CRC', 'fr.crcOk': 'CRC đúng', 'fr.crcBad': 'CRC sai', 'fr.copyHex': 'Chép hex', 'fr.copied': 'Đã chép',
    'fr.note': 'Frame được lấy mẫu từ bộ đệm của board (bộ đệm gửi của remote, bộ đệm parser của robot và của remote), không phải bắt toàn bộ đường truyền: nếu tần số đọc thấp hơn tần số gửi thì có frame không được thấy (nhìn khoảng nhảy SEQ). Frame sai CRC không được hiển thị. Robot không có bộ đệm cho telemetry gửi đi nên chiều robot → remote chỉ xem ở phía remote nhận.',
    'fr.payload': 'Nội dung', 'fr.field': 'Trường', 'fr.flags': 'Cờ', 'fr.slots': 'Slot', 'fr.records': 'Bản ghi telemetry', 'fr.tlv': 'TLV',
    'ex.title': 'Live Expressions', 'ex.intro': 'Theo dõi biến theo tên hoặc địa chỉ bất kỳ, chỉ đọc (không ghi). Cần đang "Bắt đầu đọc"; giá trị cập nhật theo chu kỳ đọc.',
    'ex.needWatch': 'Chưa đọc: bấm "Bắt đầu đọc" để thấy giá trị.', 'ex.target': 'Board', 'ex.expr': 'Biến hoặc địa chỉ', 'ex.exprPh': 's_lora_rx.filter.stats.lost hoặc 0xE000ED28',
    'ex.type': 'Kiểu (địa chỉ)', 'ex.count': 'Số phần tử', 'ex.add': 'Thêm', 'ex.core': 'Thanh ghi lõi…', 'ex.format': 'Hiển thị', 'ex.fmt.auto': 'tự động', 'ex.fmt.dec': 'thập phân', 'ex.fmt.hex': 'hex', 'ex.fmt.bin': 'nhị phân',
    'ex.cols': 'Board|Biểu thức|Địa chỉ|Kiểu|Giá trị|Đổi cách đây', 'ex.expand': 'Mở rộng', 'ex.remove': 'Xóa', 'ex.clear': 'Xóa tất cả', 'ex.empty': 'Chưa có biểu thức nào. Thêm một biến hoặc địa chỉ ở trên.',
    'ex.periph': 'Đọc thanh ghi ngoại vi đang tắt (Cài đặt): đọc có thể xóa cờ hoặc lấy byte khỏi FIFO.', 'ex.readOnly': 'Chỉ đọc: Flash, SRAM và thanh ghi lõi Cortex-M luôn đọc được; thanh ghi ngoại vi cần bật trong Cài đặt.',
    'ex.ago': '{s} s', 'ex.never': '—', 'ex.bits': 'bit',
    'set.title': 'Cài đặt', 'set.chat': 'Chat Claude', 'set.model': 'Model', 'set.modelCustom': 'Model khác (nhập id)…', 'set.effort': 'Mức suy luận (effort)', 'set.effortDefault': 'mặc định của model',
    'set.budget': 'Giới hạn chi phí mỗi cuộc trò chuyện (USD)', 'set.save': 'Lưu', 'set.saved': 'Đã lưu. Cuộc trò chuyện mới sẽ dùng cài đặt này.', 'set.savedRestart': 'Đã lưu và đã bắt đầu cuộc trò chuyện mới.',
    'set.status': 'Trạng thái chat', 'set.statusReady': 'sẵn sàng (đã đăng nhập)', 'set.statusLogin': 'chưa đăng nhập: chạy lệnh auth login một lần', 'set.statusNoSdk': 'thiếu claude-agent-sdk', 'set.statusUnknown': 'chưa rõ',
    'set.engineNote': 'Công cụ chat là Claude Agent SDK (chỉ có công cụ đọc và hiển thị của rdt; không ghi, reset hay nạp). Model và effort áp dụng từ cuộc trò chuyện kế tiếp.',
    'set.reading': 'Đọc dữ liệu', 'set.periph': 'Cho phép Live Expressions đọc thanh ghi ngoại vi (0x4000_0000..0x5FFF_FFFF)', 'set.periphWarn': 'Đọc một thanh ghi trạng thái hoặc dữ liệu có thể xóa cờ hoặc lấy byte khỏi FIFO và làm firmware chạy khác đi. Mặc định tắt.',
    'set.appearance': 'Giao diện', 'set.theme': 'Theme', 'set.themeDark': 'tối', 'set.themeLight': 'sáng', 'set.lang': 'Ngôn ngữ',
  },
  en: {
    'conn.live': 'daemon connected', 'conn.replay': 'replaying {name}', 'conn.offline': 'daemon not running (rdt serve)',
    'target.reads': '{n} reads', 'target.fail': ', {n} errors', 'target.idle': 'not watching',
    'hdr.vcp': 'remote log', 'hdr.vcpTip': 'Remote VCP log; the robot has no usable VCP',
    'hdr.start': 'Start reading', 'hdr.stop': 'Stop', 'hdr.rec': '● Record session', 'hdr.recording': '■ Recording {name}', 'hdr.live': 'Back to live',
    'hdr.sessions': 'recorded sessions…', 'hdr.open': 'Open', 'hdr.themeTip': 'Switch light/dark theme', 'hdr.langTip': 'Ngôn ngữ: English / Tiếng Việt',
    'nav.dashboard': 'Dashboard', 'nav.cli': 'Programmer CLI', 'nav.reference': 'Reference',
    'sig.title': '1. Signal path', 'sig.moving': 'changing', 'sig.stuck': 'stuck {s} s', 'sig.armed': 'armed', 'sig.disarmed': 'disarmed',
    'sig.note': 'Red: the stage counter has not changed for more than {s} s. Grey: no variable to read for that stage.',
    'stage.app': 'Remote: app/input', 'stage.arb': 'Remote: arbiter', 'stage.out': 'Remote: CONTROL sent', 'stage.air': 'Air (LoRa)',
    'stage.par': 'Robot: parser', 'stage.flt': 'Robot: filter', 'stage.inp': 'Robot: input', 'stage.can': 'Kinematics → CAN rpm',
    'stage.noVar': 'no variable', 'stage.noVarYet': 'no variable yet',
    'link.title': '2. LoRa link (events / second)', 'link.robot': 'Robot (H755): receive', 'link.remote': 'Remote (F446): send and receive',
    'link.note': 'The two boards share no clock: the time axis is the PC clock when each sample arrived, accurate to one poll period.',
    'flags.title': '3. Flags and state', 'flag.sentEstop': 'remote ESTOP sent',
    'find.title': 'Automatic diagnosis', 'find.mark': 'Mark on chart', 'find.ask': 'Ask Claude',
    'find.none': 'No findings yet. Rules come from the symptom tables of debug_guide and task_history; a rule whose variables are missing is skipped, not guessed.',
    'find.askText': 'Explain the finding "{title}" ({target}, t={t0}–{t1} s) and check it against the data.',
    'cc.title': 'Charts Claude drew', 'cc.chart': 'chart', 'cc.band': 'band {t0}–{t1} s {label}',
    'sweep.title': 'Phase 0 sweep (loss vs send rate)', 'sweep.calc': 'Compute from {src}', 'sweep.live': 'live data', 'sweep.replay': 'the session being viewed',
    'sweep.csv': 'Download CSV', 'sweep.hint': 'The remote must run the sweep build and be reset after reading starts. rdt only observes; it does not control the remote.',
    'sweep.cols': 'gap ms|seconds|sent|robot rx|accepted|lost|loss %|crc', 'sweep.restart': ' (−{n} restart)',
    'sweep.src': 'Step boundaries come from {src} on the PC clock: accurate to one poll period.', 'sweep.srcVcp': 'the VCP log', 'sweep.srcVar': 'the sweep_step variable',
    'tl.title': '5. Timeline', 'tl.count': '{n} items (remote VCP log, flag changes, read errors)', 'tl.none': 'no events yet',
    'flash.title': 'Flash firmware (safety gated)', 'flash.warn': 'Writes to the real board. Accepts only .elf files on the board\'s allow-list, checks DEV_ID, and needs the exact confirmation phrase. Claude has no flash tool.',
    'flash.dry': 'Check (no write)', 'flash.stopFirst': 'Stop reading first: flashing needs the probe exclusively.', 'flash.already': 'The board already runs this image; flashing again changes nothing.',
    'flash.safe': 'The wheels are off the ground, I am at the robot and ready to cut power at once', 'flash.typeExactly': 'Type exactly:', 'flash.go': 'Flash',
    'flash.rejected': 'Plan rejected: fix the ✕ items and check again.', 'flash.done': 'Flashed', 'flash.failed': 'Flash failed',
    'flash.after': '(code {rc}); flash compared with the ELF: {v}', 'flash.vNone': 'not run', 'flash.vOk': 'match', 'flash.vBad': 'MISMATCH',
    'chat.title': 'Claude chat', 'chat.noModel': 'not connected', 'chat.new': 'New', 'chat.newTip': 'New conversation',
    'chat.login': 'The chat uses the Claude Code bundled with the SDK, which is not logged in. Run this once in a terminal, then ask again:',
    'chat.empty': 'Ask about the data you are looking at, for example: "is the link losing packets?". Claude only has read and display tools: no write, no reset, no flashing.',
    'chat.placeholder': 'Ask Claude… (Enter to send)', 'chat.send': 'Send', 'chat.stop': 'Stop',
    'cli.title': 'STM32_Programmer_CLI (read-only)', 'cli.intro': 'Runs read-only CLI commands from a whitelist over a HOTPLUG connection (no halt, no reset). Flashing stays in the "Flash firmware" panel of the Dashboard.',
    'cli.stopFirst': 'Stop reading first: the CLI needs the probe exclusively.', 'cli.command': 'Command', 'cli.target': 'Board', 'cli.address': 'Address', 'cli.size': 'Bytes',
    'cli.preview': 'Preview', 'cli.run': 'Run', 'cli.exact': 'Command line to run:', 'cli.output': 'Output (rc {rc}):',
    'cli.c.list': 'List ST-LINK probes', 'cli.c.info': 'Device info (connect only)', 'cli.c.read32': 'Read memory (-r32)', 'cli.c.ob_display': 'Display option bytes',
    'cli.hint.list': 'Lists attached ST-LINK probes with serial numbers.', 'cli.hint.info': 'Connects in HOTPLUG mode and prints device and core info.',
    'cli.hint.read32': 'Reads flash or SRAM, 4-byte aligned, up to 4096 bytes. Peripheral areas are not allowed.', 'cli.hint.ob_display': 'Shows option bytes (RDP, boot, watchdog...). Read-only.',
    'ref.title': 'Reference', 'ref.search': 'Search…', 'ref.docs': 'Markdown copy: docs/REFERENCE.en.md', 'ref.used': 'used by rdt', 'ref.cols.var': 'Variable',
    'ref.safety': 'Safety', 'ref.board': 'Board', 'ref.shown': 'Shown in', 'ref.copy': 'Copy', 'ref.noMatch': 'No matching entries.', 'ref.loadFail': 'Could not load the reference: {e}',
    'ref.safety.all': 'all levels',
    'tl.kind.all': 'all', 'tl.kind.log': 'log', 'tl.kind.flag': 'flag', 'tl.kind.finding': 'finding', 'tl.kind.note': 'note', 'tl.kind.error': 'error',
    'err.stopFirst': 'Stop reading first: this needs the probe exclusively.', 'err.alreadyRunning': 'Already reading; stop first.', 'err.notRunning': 'Not reading yet.',
    'err.flashBusy': 'A flash is in progress.', 'err.local': 'Local access only.', 'err.fw': 'FIRMWARE MISMATCH: {a}/{b} flash chunks differ from the ELF. The variables you see follow the ELF, not the firmware that is running.',
    'err.noSdk': 'The chat needs claude-agent-sdk (pip install -e .[chat]).',
    'flash.check.image_allowed_for_target': 'Image is on the allow-list', 'flash.check.image_inside_flash_range': 'Image is inside the board flash',
    'flash.check.probe_attached': 'Probe attached', 'flash.check.board_dev_id': 'Board DEV_ID matches',
    'nav.frames': 'Frames', 'nav.expr': 'Live Expressions', 'nav.settings': 'Settings',
    'chat.ready': 'ready', 'chat.needLogin': 'not logged in', 'chat.noSdk': 'SDK missing', 'chat.unknown': 'status unknown',
    'chat.loginTip': 'Run once: .venv\\Lib\\site-packages\\claude_agent_sdk\\_bundled\\claude.exe auth login',
    'fr.title': 'RCL frames (full frame)', 'fr.src.remote_tx': 'Remote sends → robot', 'fr.src.robot_rx': 'Robot receives', 'fr.src.remote_rx': 'Remote receives (from robot)',
    'fr.none': 'no frame seen yet', 'fr.needWatch': 'Press "Start reading": the frame buffers are read together with the other variables.',
    'fr.match': 'Remote sent up to SEQ {tx}, robot received up to SEQ {rx}: {d} frame(s) apart (may be the poll period).', 'fr.noMatch': 'Not enough data from both sides to compare SEQ.',
    'fr.history': 'Frame history', 'fr.filter': 'Source', 'fr.all': 'all', 'fr.inspect': 'Frame detail', 'fr.pickRow': 'Pick a frame from the history table or one of the cards above.',
    'fr.cols': 'time (s)|source|type|SEQ|LINK_ID|bytes|CRC', 'fr.crcOk': 'CRC ok', 'fr.crcBad': 'CRC bad', 'fr.copyHex': 'Copy hex', 'fr.copied': 'Copied',
    'fr.note': "Frames are sampled from the boards' buffers (the remote's send buffer and the parser buffers of the robot and the remote); this is not a capture of the whole line. If the poll rate is below the send rate some frames are never seen (look at SEQ jumps). Frames with a bad CRC are not shown. The robot keeps no buffer for the telemetry it sends, so the robot → remote direction is visible only on the remote's receive side.",
    'fr.payload': 'Payload', 'fr.field': 'Field', 'fr.flags': 'Flags', 'fr.slots': 'Slots', 'fr.records': 'Telemetry records', 'fr.tlv': 'TLV',
    'ex.title': 'Live Expressions', 'ex.intro': 'Watch variables by name or any address, read-only (never writes). Needs "Start reading"; values refresh at the read rate.',
    'ex.needWatch': 'Not reading: press "Start reading" to see values.', 'ex.target': 'Board', 'ex.expr': 'Variable or address', 'ex.exprPh': 's_lora_rx.filter.stats.lost or 0xE000ED28',
    'ex.type': 'Type (address)', 'ex.count': 'Elements', 'ex.add': 'Add', 'ex.core': 'Core register…', 'ex.format': 'Format', 'ex.fmt.auto': 'auto', 'ex.fmt.dec': 'decimal', 'ex.fmt.hex': 'hex', 'ex.fmt.bin': 'binary',
    'ex.cols': 'Board|Expression|Address|Type|Value|Changed ago', 'ex.expand': 'Expand', 'ex.remove': 'Remove', 'ex.clear': 'Clear all', 'ex.empty': 'No expressions yet. Add a variable or an address above.',
    'ex.periph': 'Reading peripheral registers is off (Settings): a read can clear a flag or take a byte out of a FIFO.', 'ex.readOnly': 'Read-only: flash, SRAM and the Cortex-M core registers are always readable; peripheral registers need to be enabled in Settings.',
    'ex.ago': '{s} s', 'ex.never': '—', 'ex.bits': 'bits',
    'set.title': 'Settings', 'set.chat': 'Claude chat', 'set.model': 'Model', 'set.modelCustom': 'Other model (enter id)…', 'set.effort': 'Reasoning effort', 'set.effortDefault': "the model's default",
    'set.budget': 'Cost cap per conversation (USD)', 'set.save': 'Save', 'set.saved': 'Saved. A new conversation will use these settings.', 'set.savedRestart': 'Saved, and a new conversation was started.',
    'set.status': 'Chat status', 'set.statusReady': 'ready (logged in)', 'set.statusLogin': 'not logged in: run the auth login command once', 'set.statusNoSdk': 'claude-agent-sdk is missing', 'set.statusUnknown': 'unknown',
    'set.engineNote': "The chat engine is the Claude Agent SDK (only rdt's read and display tools: no write, reset or flash). Model and effort apply from the next conversation.",
    'set.reading': 'Reading data', 'set.periph': 'Let Live Expressions read peripheral registers (0x4000_0000..0x5FFF_FFFF)', 'set.periphWarn': 'Reading a status or data register can clear a flag or take a byte out of a FIFO and change how the firmware behaves. Off by default.',
    'set.appearance': 'Appearance', 'set.theme': 'Theme', 'set.themeDark': 'dark', 'set.themeLight': 'light', 'set.lang': 'Language',
  },
};

// Server-made finding text is Vietnamese; for English the UI rebuilds it from the finding id and its evidence.
const F = {
  remote_restart: { title: 'Remote restarted', detail: () => "The remote's control_frames counter dropped: the remote reset (sequence back to 0). The robot's `lost` jumping to ~255 after it is not real loss.", checks: ['Remote VCP log: banner / reset reason', 'task_history 122: IWDG if the reset repeats every ~500 ms'] },
  lost_jump: { title: (f) => `\`lost\` jumped ${Math.round(f.evidence?.jump ?? 0)} in one sample`, detail: () => 'One big jump is a remote restart (task 147), not packet loss; it is excluded from the loss rate.', checks: ["Is there a 'Remote restarted' finding at the same time?"] },
  link_loss: { title: (f) => `Real packet loss about ${f.evidence?.loss_pct ?? '?'}%`, detail: (f) => `${Math.round(f.evidence?.lost ?? 0)} lost vs ${Math.round(f.evidence?.received ?? 0)} received, ${f.evidence?.bursts ?? '?'} burst(s).`, checks: ['crc_errors, truncated', 'remote tx_failures', 'Weak signal or remote sending slower than 500 ms (debug_guide 5.5)'] },
  robot_not_receiving: { title: 'Remote is sending but the robot receives no frames', detail: (f) => `parser.frames stood still ${f.evidence?.seconds ?? '?'} s while the remote sent ${Math.round(f.evidence?.remote_sent ?? 0)} more frames.`, checks: ['s_stats.rx_bytes, huart3.ErrorCode', 'crc_errors, dropped_bytes', 'Old remote firmware (not RCL v1), wrong baud, VCP pin conflict'] },
  remote_not_sending: { title: 'Remote is not sending frames', detail: (f) => `The remote's control_frames stood still ${f.evidence?.seconds ?? '?'} s and the robot received nothing new either.`, checks: ['Remote reset or hung? Check the VCP log and remote power'] },
  crc_errors: { title: 'Robot reports CRC errors', detail: (f) => `${Math.round(f.evidence?.count ?? 0)} frames with a bad CRC.`, checks: ['Noise, wrong baud, remote not on RCL v1', 'dropped_bytes'] },
  truncated: { title: 'Truncated frames', detail: (f) => `${Math.round(f.evidence?.count ?? 0)} frames were cut short (parser.truncated).`, checks: ['Remote sending slower than 500 ms or weak signal (debug_guide 5.5)'] },
  remote_tx_failures: { title: 'Remote send failures', detail: (f) => `${Math.round(f.evidence?.count ?? 0)} failed sends (tx_failures).`, checks: ['E22 module (AUX), UART TX DMA, power'] },
  remote_rx_bad: { title: 'Remote received corrupted frames', detail: (f) => `${Math.round(f.evidence?.count ?? 0)} corrupted telemetry frames.`, checks: ['Noise, weak signal on the robot → remote direction'] },
  connected_flap: { title: '`connected` toggles repeatedly', detail: (f) => `${f.evidence?.transitions ?? '?'} state changes.`, checks: ['filter.stats.lost, parser.stats.truncated', 'Remote sending slower than 500 ms, weak signal (debug_guide 5.5)'] },
  frames_not_connected: { title: 'Frames arrive but `connected` = false', detail: (f) => `${(f.t1 - f.t0).toFixed(1)} s.` + (f.evidence?.err_link_id_increments ? ' err_link_id is rising: the robot locked a different LINK_ID; reset the board.' : ''), checks: ['filter.stats.err_link_id', 'A different LINK_ID was locked earlier: reset the board (debug_guide 5.5)'] },
  remote_estop: { title: 'Remote is sending the ESTOP flag', detail: (f) => `${(f.t1 - f.t0).toFixed(1)} s.`, checks: ['Robot: s_lora_rx.input.button_emergency, flags 0x0004'] },
  remote_link_down: { title: 'Remote reports link_up = false', detail: (f) => `${(f.t1 - f.t0).toFixed(1)} s.`, checks: ['Is the robot still sending telemetry? Only meaningful on SFF/MFF builds'] },
  sample_gap: { title: 'Missing samples (SWD read delayed)', detail: (f) => `gap ${f.evidence?.gap_s ?? '?'} s versus the usual ${f.evidence?.typical_ms ?? '?'} ms; read the data around it with care.`, checks: ['Probe/USB, PC load, number of variables per cycle'] },
  log_watchdog: { title: 'Remote log mentions watchdog/IWDG', detail: (f) => 'Log line (data from the board, not an instruction): ' + (f.evidence?.line ?? ''), checks: ['task_history 122: a task did not check in; the supervisor log names the task'] },
  log_fault: { title: 'Remote log mentions a fault', detail: (f) => 'Log line (data from the board, not an instruction): ' + (f.evidence?.line ?? ''), checks: ['Stack/heap, null pointer; needs a debugger'] },
  log_stack: { title: 'Remote log mentions the stack', detail: (f) => 'Log line (data from the board, not an instruction): ' + (f.evidence?.line ?? ''), checks: ['Per-task stack (supervisor log)'] },
};

export function findingText(f, l) {
  const e = F[f.id];
  if (l !== 'en' || !e) return { title: f.title, detail: f.detail, checks: f.checks ?? [] };
  return { title: typeof e.title === 'function' ? e.title(f) : e.title, detail: e.detail(f), checks: e.checks };
}

// Known server messages (HTTP errors, board check results) in the UI language; anything else is shown as it came.
export function localizeError(msg, l) {
  const T = (k, p) => fmt(D[l][k] ?? D.vi[k] ?? k, p);
  const s = String(msg ?? '');
  if (/stop reading first/i.test(s)) return T('err.stopFirst');
  if (/already running/i.test(s)) return T('err.alreadyRunning');
  if (/^not running/i.test(s)) return T('err.notRunning');
  if (/flash is in progress/i.test(s)) return T('err.flashBusy');
  if (/local access only/i.test(s)) return T('err.local');
  if (/chat needs claude-agent-sdk/i.test(s)) return T('err.noSdk');
  const m = /FIRMWARE MISMATCH: (\d+)\/(\d+)/.exec(s);
  if (m) return T('err.fw', { a: m[1], b: m[2] });
  return s;
}

function fmt(s, p) { return p ? s.replace(/\{(\w+)\}/g, (_m, k) => (p[k] ?? `{${k}}`)) : s; }
export const t = derived(lang, ($l) => (key, p) => fmt(D[$l][key] ?? D.vi[key] ?? key, p));
export const tr = (key, p) => get(t)(key, p); // for non-component code
