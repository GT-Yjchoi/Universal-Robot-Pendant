import socket
import struct
import threading
import time
import queue
from PySide6.QtCore import QObject, Signal, Slot

class PLCClient(QObject):
    sig_connected = Signal(bool)
    sig_monitor_data = Signal(dict)  # 모니터링 데이터 (PLC → HMI)
    sig_error = Signal(str)
    sig_async_done = Signal(object, object, object)

    def __init__(self):
        super().__init__()
        self.sock = None
        self.is_connected = False
        self._monitor_running = False
        self._monitor_thread = None
        # Re-entrant so compound operations (read-modify-write bit updates)
        # can hold the socket lock across both packets without deadlocking.
        self.lock = threading.RLock()
        self._last_ip = None
        self._last_port = None
        self._reconnect_running = False
        # 사용자가 "연결끊기"를 눌렀는지 구분.
        # True 인 동안에는 재연결 루프를 자동으로 띄우지 않음(사용자 의도 존중).
        self._manual_disconnect = False
        self._last_monitor_data = {}
        self._recipe_transfer_active = False
        self._command_queue = queue.Queue()
        self._command_thread = threading.Thread(
            target=self._command_loop, name="plc-ui-command-queue", daemon=True
        )
        self.sig_async_done.connect(self._deliver_async_result)
        self._command_thread.start()

        # --- PLC 통신 설정 ---
        self.USE_HEADER = True      
        self.DEST_UNIT_NO = 0x01    
        
        # ===== 메모리 맵 =====

        # 1. 실시간 모니터링 블록 (PLC → HMI): DT100~
        self.MONITOR_ADDR  = 100
        self.MONITOR_COUNT = 66
        self.ADDR_USER_ALARM = 159   # DT159: 사용자 알람 (IN 스텝에서 발동, w_UserAlarm)

        # 2. 제어 명령 블록 (HMI → PLC): DT200~
        self.ADDR_CTRL_CMD    = 200  # 운전 제어 명령
        self.ADDR_JOG_PRESS   = 201  # 조작압 선택
        self.ADDR_CHECK_RUN   = 202  # 확인운전 제어
        self.ADDR_VALVE_OUT   = 204  # 밸브 수동출력 (204~205, 2 Words)
        self.ADDR_JOG_CTRL    = 205  # 조그 제어
        self.ADDR_MODE        = 206  # 모드 설정 (206~208, 3 Words)
        self.ADDR_JOG_SPEED   = 211  # 조그 속도
        self.ADDR_ALARM_RESET = 212  # 알람 리셋
        self.ADDR_SOFT_ESTOP  = 213  # 소프트 비상정지 (0=정상, 1=비상정지)
        self.HEARTBEAT_ADDR   = 214  # 하트비트
        self.ADDR_JOG_MODE    = 215  # 수동조작 모드 선택 (0=앱솔루트기동, 1=JOG기동)
        self.ADDR_SPEED_OVR   = 216  # 전체 속도 배율 (1~10 단계)
        self.heartbeat_value  = 0
        self._heartbeat_skip  = False
        self._last_heartbeat_at = 0.0

        # 3. 시퀀스 데이터 블록: DT20000~ (40슬롯 × 1000 = DT20000~DT59999)
        self.SEQ_BASE_ADDR = 20000
        self.SLOT_SIZE     = 1000   # 100스텝 × 10워드
        self.MAX_SLOTS     = 40

        # 4. 포인트 데이터 블록: DT16000~ (60개 × 32 = DT16000~DT17919)
        # RTEX 하드웨어 테이블 64개 중 60 일반/3 예약/1 패킹 스크래치(idx=63)로 배정
        self.POINT_BASE_ADDR = 16000
        self.POINT_SIZE      = 32
        self.MAX_POINTS      = 60

        # 파렛타이징
        self.ADDR_PACK_IDX = 161     # DT161~163 (pack_idx 공유, HMI·PLC 모두 R/W)
        self.ADDR_PACK_CFG = 217     # DT217~230 (패킹 설정 HMI→PLC)

        # 5. 축 설정 블록: DT15000~ (50 Words)
        self.AXIS_PARAM_ADDR   = 15000
        self.ADDR_AXIS_DATASET = self.AXIS_PARAM_ADDR + 33  # 데이터셋 트리거

    def submit(self, func, *args, callback=None):
        """Run a PLC operation in the single ordered backend queue.

        The optional callback is delivered on the Qt/UI thread as
        ``callback(result, error)``.  UI code never needs to wait for TCP.
        """
        self._command_queue.put((func, args, callback))

    def _command_loop(self):
        while True:
            func, args, callback = self._command_queue.get()
            result = None
            error = None
            try:
                result = func(*args)
            except Exception as exc:
                error = exc
            if callback is not None:
                self.sig_async_done.emit(callback, result, error)
            elif error is not None:
                print(f"[PLC async command] {error}")
            self._command_queue.task_done()

    @Slot(object, object, object)
    def _deliver_async_result(self, callback, result, error):
        try:
            callback(result, error)
        except Exception as exc:
            print(f"[PLC async callback] {exc}")

    def connect_to_plc(self, ip, port):
        """PLC 연결 요청 — 비차단(즉시 반환).
        실제 소켓 연결은 백그라운드 재연결 루프가 수행. 성공/실패는 sig_connected 로 통지.
        실패 시 주기적으로 계속 재시도 (disconnect_plc() 로 수동 중지 가능)."""
        self._last_ip = ip
        self._last_port = port
        self._manual_disconnect = False
        if self.is_connected:
            return True, "이미 연결됨"
        self._start_reconnect(immediate=True)
        return True, "연결 시도 중..."

    def disconnect_plc(self):
        """PLC 연결 해제 — 사용자가 명시적으로 요청한 수동 끊기."""
        self._manual_disconnect = True
        self._monitor_running = False
        self._reconnect_running = False
        self.is_connected = True  # 재연결 루프 while 조건(not is_connected) 즉시 탈출
        if self.sock:
            try:
                self.sock.close()
            except OSError:
                pass
        self.sock = None
        self.is_connected = False
        # 모니터링 스레드가 완전히 종료될 때까지 대기 (최대 200ms)
        # → 스레드가 소멸된 Qt 객체에 시그널을 emit해 segfault 발생하는 것을 방지
        if self._monitor_thread and self._monitor_thread.is_alive():
            self._monitor_thread.join(timeout=0.2)
        self._monitor_thread = None
        self.sig_connected.emit(False)
        print("[PLC] 연결 해제")

    def _update_heartbeat(self):
        """
        하트비트 값을 +1 증가시키고 DT214에 전송
        - 0~100 범위를 순환
        - 100 다음에는 0으로 리셋
        - 무한루프 방지: _heartbeat_skip 플래그 사용
        """
        # 하트비트 값 증가
        self.heartbeat_value += 1
        if self.heartbeat_value > 100:
            self.heartbeat_value = 0
        
        # DT214에 하트비트 값 쓰기 (무한루프 방지)
        if not self._heartbeat_skip:
            self._heartbeat_skip = True  # 플래그 설정으로 재귀 방지
            try:
                # send_packet을 직접 호출하지 않고 저수준으로 전송
                body = struct.pack('<BBBHH', 0x80, 0x50, 0x09, self.HEARTBEAT_ADDR, 1)
                data_part = struct.pack('<H', self.heartbeat_value)
                self._send_packet_raw(body + data_part)
                # print(f"[하트비트] DT214 = {self.heartbeat_value}")  # 필요시 주석 해제
            except OSError:
                pass  # 하트비트 전송 실패는 무시
            finally:
                self._heartbeat_skip = False  # 플래그 해제

    def _send_packet_raw(self, body):
        """
        패킷 전송 (하트비트 전용, _update_heartbeat 호출 안함)
        """
        if not self.sock or not self.is_connected: 
            return None
        try:
            with self.lock:
                length = len(body)
                prefix = b'\x10\x00' + struct.pack('<H', length) + b'\x02\x00\x02\x00\x00\x00'
                suffix = bytes([0x01, self.DEST_UNIT_NO])
                packet = prefix + suffix + body
                self.sock.sendall(packet)
                response = self.sock.recv(4096)
            if len(response) > 12:
                return response[12:]
            return response
        except OSError:
            return None

    def send_packet(self, body):
        """패킷 전송 (헤더 포함).
        주의: _start_reconnect() 는 self.lock 을 다시 잡으므로 lock 해제 후에 호출해야 함(데드락 방지)."""
        if not self.sock or not self.is_connected:
            return None
        result = None
        error_happened = False
        with self.lock:
            try:
                length = len(body)
                # LS PLC 프레임 헤더
                prefix = b'\x10\x00' + struct.pack('<H', length) + b'\x02\x00\x02\x00\x00\x00'
                suffix = bytes([0x01, self.DEST_UNIT_NO])
                packet = prefix + suffix + body

                t_start = time.time()
                self.sock.sendall(packet)
                response = self.sock.recv(4096)
                elapsed = (time.time() - t_start) * 1000  # ms

                if elapsed > 30:
                    print(f"[PLC] [!] 응답 지연: {elapsed:.1f}ms")

                # 헤더 제거하고 데이터 반환
                if len(response) > 12:
                    result = response[12:]
                else:
                    result = response
            except Exception as e:
                print(f"[PLC] 통신 에러: {e}")
                self.is_connected = False
                self.sig_connected.emit(False)
                error_happened = True
        if error_happened:
            self._start_reconnect()
        return result

    def read_words(self, area_code, start_addr, count):
        """Word 읽기"""
        body = struct.pack('<BBBHH', 0x80, 0x51, area_code, start_addr, count)
        resp = self.send_packet(body)
        if resp and len(resp) > 3:
            data = resp[3:]
            words = [struct.unpack('<H', data[i:i+2])[0] for i in range(0, len(data), 2)]
            return words
        return None

    def write_words(self, area_code, start_addr, values):
        """Word 쓰기"""
        if not isinstance(values, list):
            values = [values]
        
        # 값 검증
        clean_values = []
        for val in values:
            try:
                clean_values.append(int(val) & 0xFFFF)
            except (TypeError, ValueError):
                clean_values.append(0)
        
        header_part = struct.pack('<BBBHH', 0x80, 0x50, area_code, start_addr, len(clean_values))
        data_part = b''.join([struct.pack('<H', v) for v in clean_values])
        result = self.send_packet(header_part + data_part)
        
        if result:
            print(f"[PLC] O Write DT{start_addr} = {len(clean_values)} Words")
        else:
            print(f"[PLC] X Write FAILED DT{start_addr}")
        
        return result

    def write_bit(self, area_code, addr, bit_pos, on_off):
        """Atomic word read-modify-write for one bit."""
        with self.lock:
            curr = self.read_words(area_code, addr, 1)
            if not curr:
                return False
            val = int(curr[0])
            if on_off:
                val |= 1 << int(bit_pos)
            else:
                val &= ~(1 << int(bit_pos))
            return bool(self.write_words(area_code, addr, [val]))

    def write_dint(self, area_code, addr, value):
        """DINT(32비트) 쓰기"""
        v = int(value)
        low = v & 0xFFFF
        high = (v >> 16) & 0xFFFF
        return self.write_words(area_code, addr, [low, high])

    def patch_tmr_step_time(self, slot_id, step_idx, time_sec):
        """TMR 스텝의 diParam1(시간값)만 PLC에 직접 패치 (슬롯 전체 재전송 없이)"""
        if not self.is_connected:
            return False
        if not (0 <= slot_id < self.MAX_SLOTS) or not (0 <= step_idx < 100):
            return False
        # Word 오프셋: 스텝당 10Words, diParam1 = +2~3
        addr = self.SEQ_BASE_ADDR + slot_id * self.SLOT_SIZE + step_idx * 10 + 2
        value = int(round(time_sec * 100))
        result = self.write_dint(0x09, addr, value)
        print(f"[PLC] TMR 패치 Slot={slot_id} Step={step_idx} DT{addr} = {value} ({time_sec}s)")
        return result

    def patch_out_delay_step_time(self, slot_id, step_idx, time_sec):
        """OUT 스텝의 diParam3(타이머 기동후출력 시간)만 PLC에 직접 패치"""
        if not self.is_connected:
            return False
        if not (0 <= slot_id < self.MAX_SLOTS) or not (0 <= step_idx < 100):
            return False
        # Word 오프셋: 스텝당 10Words, diParam3 = +6~7
        addr = self.SEQ_BASE_ADDR + slot_id * self.SLOT_SIZE + step_idx * 10 + 6
        value = int(round(time_sec * 100))
        result = self.write_dint(0x09, addr, value)
        print(f"[PLC] OUT 지연 패치 Slot={slot_id} Step={step_idx} DT{addr} = {value} ({time_sec}s)")
        return result

    def patch_sequence_step(self, slot_id, step_idx, step_data):
        """단일 시퀀스 스텝(10 Words)을 전체 전송과 같은 인코더로 재생성해 패치."""
        if not self.is_connected:
            return False
        if not (0 <= slot_id < self.MAX_SLOTS) or not (0 <= step_idx < 100):
            return False

        words = self._convert_json_step_to_10words(step_data)
        addr = self.SEQ_BASE_ADDR + slot_id * self.SLOT_SIZE + step_idx * 10
        result = self.write_words(0x09, addr, words)
        print(f"[PLC] STEP 패치 Slot={slot_id} Step={step_idx} DT{addr}~{addr+9} ({step_data.get('type', 'NOP')})")
        return result

    # =========================================================
    # 제어 명령 (HMI → PLC) - DT200~208
    # =========================================================
    
    def send_control_command(self, mode):
        """
        DT200: 운전 제어 명령
        - 0: 정지
        - 1: 자동 (AUTO RUN)
        - 2: 확인운전 (CHECK RUN)
        """
        if int(mode) in (1, 2) and self.is_recipe_transfer_active():
            print("[PLC] X 레시피/시퀀스 전송 중이라 운전 시작 차단")
            return False
        print(f"[PLC] 운전 제어 명령 → DT{self.ADDR_CTRL_CMD} = {mode}")
        return self.write_words(0x09, self.ADDR_CTRL_CMD, [mode])
    
    def send_jog_command(self, jog_value):
        """
        DT201: 조작 압 선택
        - 0: 제품압
        - 1: 티칭압
        """
        print(f"[PLC] 조작 압 선택 → DT{self.ADDR_JOG_PRESS} = {jog_value}")
        return self.write_words(0x09, self.ADDR_JOG_PRESS, [jog_value])
    
    def send_check_run_command(self, state):
        """
        DT202: 확인운전 제어
        - 확인운전 시작/중지 명령
        """
        if int(state) == 1 and self.is_recipe_transfer_active():
            print("[PLC] X 레시피/시퀀스 전송 중이라 확인운전 진행 차단")
            return False
        print(f"[PLC] 확인운전 제어 → DT{self.ADDR_CHECK_RUN} = {state}")
        return self.write_words(0x09, self.ADDR_CHECK_RUN, [state])
    
    def write_jog_bits(self, bit_mask):
        """
        DT204~205: 밸브 수동 제어 (Bit 단위)
        - 32개 밸브를 Bit로 제어 (2 Words)
        """
        low = bit_mask & 0xFFFF
        high = (bit_mask >> 16) & 0xFFFF
        return self.write_words(0x09, self.ADDR_VALVE_OUT, [low, high])

    def write_jog_bit(self, bit_pos, is_on):
        """
        DT204~205: 특정 밸브 On/Off
        bit_pos: 0~31 (밸브 번호)
        """
        addr = self.ADDR_VALVE_OUT if bit_pos < 16 else self.ADDR_VALVE_OUT + 1
        bit_index = bit_pos % 16
        self.write_bit(0x09, addr, bit_index, is_on)
    
    def send_jog_control(self, jog_bit):
        """
        DT205: 조그 제어 명령 (Bit 단위)
        - 즉별 조그 이동 신호
        """
        return self.write_words(0x09, self.ADDR_JOG_CTRL, [jog_bit])
    
    def send_mode_settings(self, mode_data):
        """
        DT206~208: 모드 설정 변경 (3 Words = 40개 모드)
        mode_data: 길이 40의 boolean 리스트
        """
        if len(mode_data) < 40:
            mode_data = mode_data + [False] * (40 - len(mode_data))
        
        # 40개 모드를 3 Words로 압축
        words = [0, 0, 0]
        for i in range(40):
            word_idx = i // 16
            bit_idx = i % 16
            if mode_data[i]:
                words[word_idx] |= (1 << bit_idx)
        
        print(f"[PLC] 모드 설정 → DT{self.ADDR_MODE}~{self.ADDR_MODE+2} = {words}")
        return self.write_words(0x09, self.ADDR_MODE, words)

    def read_mode_settings(self):
        """
        DT206~208에서 현재 모드 설정 읽기
        반환: 길이 44의 boolean 리스트 (모드 0~43)
        """
        words = self.read_words(0x09, self.ADDR_MODE, 3)
        if not words or len(words) < 3:
            return None
        result = []
        for i in range(44):
            word_idx = i // 16
            bit_idx = i % 16
            result.append(bool(words[word_idx] & (1 << bit_idx)))
        return result

    def send_soft_estop(self, active):
        """
        DT213: 소프트 비상정지
        - True  / 1 : 비상정지 발동
        - False / 0 : 비상정지 해제
        """
        val = 1 if active else 0
        print(f"[PLC] 소프트 비상정지 → DT{self.ADDR_SOFT_ESTOP} = {val}")
        return self.write_words(0x09, self.ADDR_SOFT_ESTOP, [val])

    def send_jog_mode(self, mode):
        """
        DT215: 수동조작 모드 선택
        - 0: 앱솔루트기동 (위치결정 수동조작)
        - 1: JOG기동 (JOG 수동조작)
        """
        print(f"[PLC] 수동조작 모드 → DT{self.ADDR_JOG_MODE} = {mode} ({'JOG' if mode else 'ABS'})")
        return self.write_words(0x09, self.ADDR_JOG_MODE, [mode])

    def send_speed_override(self, level):
        """
        DT216: 전체 속도 배율 (1~10 단계)
        - 자동/확인운전 시 전체 속도에 곱해지는 배율
        """
        level = max(1, min(10, int(level)))
        print(f"[PLC] 전체 속도 배율 → DT{self.ADDR_SPEED_OVR} = {level}")
        return self.write_words(0x09, self.ADDR_SPEED_OVR, [level])

    def send_packing_config(self, cfg):
        """
        DT217~230 에 패킹 설정 전송 (HMI → PLC).

        Commit pattern (중간 통신 끊김 시 부분 활성화 방지):
          1) DT217 = 0  (먼저 비활성화 → PLC 가 부분 설정 상태에서 동작 안 함)
          2) DT218~230 데이터 쓰기 (pitch/dir/count/order)
          3) DT217 = 1  (최종 활성화)

        cfg["enabled"] 가 False 면 DT217 = 0 으로 끝내고 나머지는 건드리지 않음.
        pitch 는 float mm → int32 (0.001mm) 로 스케일.
        """
        if not self.is_connected:
            return False
        cfg = cfg or {}
        if "enabled" in cfg:
            enable = 1 if cfg.get("enabled") else 0
        else:
            enable = 1 if cfg else 0

        def _s16(v):
            return int(v) & 0xFFFF

        # ── 1) 먼저 비활성화 ─────────────────────────────────────────
        # 이 시점부터 다음 commit 완료 전까지 PLC 는 pack 카운터를 증가시키지 않음.
        self.write_words(0x09, self.ADDR_PACK_CFG, [0])

        if not enable:
            print(f"[PLC] 패킹 미사용 → DT{self.ADDR_PACK_CFG} = 0")
            return True

        # ── 2) 나머지 설정 먼저 쓰기 ──────────────────────────────────
        # DT218~223: pitches (DINT, ×1000)
        for i, key in enumerate(("x_pitch", "y_pitch", "z_pitch")):
            pitch_int = int(round(float(cfg.get(key, 0.0)) * 1000))
            self.write_dint(0x09, self.ADDR_PACK_CFG + 1 + i * 2, pitch_int)

        # DT224~226: directions (Z 는 기본 -1 = 위로 쌓기)
        self.write_words(0x09, self.ADDR_PACK_CFG + 7, [
            _s16(cfg.get("x_dir", 1)),
            _s16(cfg.get("y_dir", 1)),
            _s16(cfg.get("z_dir", -1)),
        ])

        # DT227~229: counts
        self.write_words(0x09, self.ADDR_PACK_CFG + 10, [
            max(1, int(cfg.get("x_count", 1))),
            max(1, int(cfg.get("y_count", 1))),
            max(1, int(cfg.get("z_count", 1))),
        ])

        # DT230: stack_order (0~5)
        order = int(cfg.get("stack_order", 0)) % 6
        self.write_words(0x09, self.ADDR_PACK_CFG + 13, [order])

        # ── 3) 마지막으로 활성화 (commit) ────────────────────────────
        self.write_words(0x09, self.ADDR_PACK_CFG, [1])

        print(f"[PLC] 패킹 설정 전송 완료 (order={order}, cfg={cfg})")
        return True

    def write_pack_idx(self, axis, value):
        """
        사용자 수동 변경용: 특정 축의 현재 스택 인덱스(DT161~163)를 덮어씀.
        axis: 'x' | 'y' | 'z'
        value: 0-based index (0 = 첫 번째 칸)
        """
        if not self.is_connected:
            return False
        offsets = {"x": 0, "y": 1, "z": 2}
        off = offsets.get(str(axis).lower())
        if off is None:
            return False
        addr = self.ADDR_PACK_IDX + off
        v = max(0, int(value)) & 0xFFFF
        self.write_words(0x09, addr, [v])
        print(f"[PLC] pack_idx {axis.upper()} 수동설정 → DT{addr} = {v}")
        return True

    # =========================================================
    # 모니터링 (PLC → HMI) - DT100~141
    # =========================================================
    
    def _start_reconnect(self, immediate: bool = False):
        """자동 재연결 시작 (이미 실행 중이면 무시).
        immediate=True: 첫 시도를 대기 없이 즉시 수행.
        사용자가 수동 끊기를 했다면 재연결 안 함."""
        with self.lock:
            if self._manual_disconnect:
                return
            if self._reconnect_running or not self._last_ip:
                return
            self._reconnect_running = True
        threading.Thread(target=self._reconnect_loop, args=(immediate,), daemon=True).start()

    def _reconnect_loop(self, immediate: bool = False):
        """기본 5초 간격 재연결 시도. 수동 끊기(_manual_disconnect) 발생 시 즉시 종료."""
        interval = 5
        first = True
        try:
            while not self.is_connected and not self._manual_disconnect:
                if not (first and immediate):
                    print(f"[PLC] {interval}초 후 재연결 시도... ({self._last_ip}:{self._last_port})")
                    time.sleep(interval)
                first = False
                if self.is_connected or self._manual_disconnect:
                    break
                try:
                    if self.sock:
                        try:
                            self.sock.close()
                        except OSError:
                            pass
                    self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    self.sock.settimeout(3.0)  # 전송/수신 기본 3초 — 실제 PLC 전송은 수십 ms 수준
                    # TCP keepalive — 랜선 단절을 OS 레벨에서 4~5초 내 감지
                    self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
                    try:
                        self.sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPIDLE, 2)
                        self.sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPINTVL, 1)
                        self.sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPCNT, 3)
                    except (AttributeError, OSError):
                        pass  # 플랫폼이 TCP_KEEPIDLE 등을 지원 안 하면 기본값 사용
                    print(f"[PLC] 연결 시도: {self._last_ip}:{self._last_port}")
                    self.sock.connect((self._last_ip, int(self._last_port)))
                    self.is_connected = True
                    self.sig_connected.emit(True)
                    print("[PLC] 연결 성공!")
                    self.start_monitoring()
                except Exception as e:
                    print(f"[PLC] 연결 실패: {e}")
        finally:
            # 예외가 루프를 끊어도 반드시 플래그 해제 → 다음 에러 이벤트에서 재시작 가능
            with self.lock:
                self._reconnect_running = False

    def start_monitoring(self):
        """실시간 모니터링 시작"""
        if self._monitor_running:
            return
        self._monitor_running = True
        print("[PLC] 모니터링 시작 (DT100~DT160, 0.05초 주기)")
        t = threading.Thread(target=self._mon_loop, daemon=True)
        self._monitor_thread = t
        t.start()

    def _mon_loop(self):
        """모니터링 루프 (0.1초 주기)"""
        while self._monitor_running and self.is_connected:
            raw = self.read_words(0x09, self.MONITOR_ADDR, self.MONITOR_COUNT)

            if raw and len(raw) >= 40:  # 최소 40개 이상
                try:
                    res = self._parse_monitor_data(raw)
                    self._last_monitor_data = res
                    self.sig_monitor_data.emit(res)
                except Exception as e:
                    print(f"[PLC] 모니터링 파싱 에러: {e}")

            # Heartbeat is independent from normal request/response traffic.
            # Updating it after every packet doubled the 10 ms FP0H Ethernet
            # transaction cost and also made command latency unpredictable.
            now = time.monotonic()
            if now - self._last_heartbeat_at >= 0.5:
                self._last_heartbeat_at = now
                self._update_heartbeat()

            time.sleep(0.02)  # response ~10ms + 20ms rest: about 33Hz UI source
        self._monitor_running = False  # 루프 종료 시 플래그 리셋 (재연결 후 재시작 가능하도록)

    def _parse_monitor_data(self, raw):
        """
        모니터링 데이터 파싱
        raw: DT100~DT162의 Word 배열 (63개)
        """
        res = {}
        
        # ===== 1. 8축 현재 위치 (DT100~115) =====
        # DINT * 8 = 16 Words
        res['axis_pos'] = []
        for i in range(0, 16, 2):
            v = raw[i] | (raw[i+1] << 16)
            if v >= 0x80000000:  # 음수 처리
                v -= 0x100000000
            # 0.001mm 단위 → mm 변환
            res['axis_pos'].append(v / 1000.0)
        
        # ===== 2. 입력(X) 상태 (DT116~119) =====
        # WORD * 4 = X0~X3F (64점 모니터링)
        res['inputs'] = raw[16:20]  # DT116, 117, 118, 119
        
        # ===== 3. 출력(Y) 상태 (DT120~123) =====
        # WORD * 4 = Y0~Y3F (64점 모니터링)
        res['outputs'] = raw[20:24]  # DT120, 121, 122, 123

        # DT126~127: 병렬 워커2 실행 상태 (워커1은 DT134~135)
        res['parallel2_slot'] = raw[26] if len(raw) > 26 else 0
        res['parallel2_step'] = raw[27] if len(raw) > 27 else 0
        
        # ===== 4. 밸브 동작 상태 (DT124~125) =====
        # WORD * 2 = 32개 밸브 On/Off
        res['valve_status'] = raw[24:26]  # DT124, 125
        
        # ===== 6. 현재 운전 상태 (DT129) =====
        # INT: 1=수동, 2=자동, 0=정지, 3=일정지(확인운전)
        res['op_status'] = raw[29]  # DT129
        
        # ===== 7. 확인운전 상태 (DT130) =====
        # INT: 현재 확인운전 진행 상태
        res['check_run_status'] = raw[30] if len(raw) > 30 else 0  # DT130
        
        # ===== 8. 현재 시퀀스 단계 (DT131) =====
        # INT: 현재 실행 중인 스텝 번호
        res['current_step'] = raw[31] if len(raw) > 31 else 0  # DT131
        
        # ===== 9. 현재 실행 슬롯 + 콜 스택 깊이 (DT132~133) =====
        # DT132: 현재 실행 중 슬롯 번호 (FB.i_CurrentSlot) - 스택 top이 가리키는 슬롯
        #        Main=0, 서브시퀀스=1~N(이름 정렬)
        # DT133: 동기 CALL 스택 깊이 (FB.i_StackDepth) - 0~3
        #        0=Main만 실행, 1=Main→Sub, 2=Main→Sub→SubSub, 3=최대 중첩
        # ※ 키명 sub_seq_idx/sub_step은 구버전 호환 유지. 실제 의미는 위 주석 기준.
        res['sub_seq_idx']  = raw[32] if len(raw) > 32 else 0  # DT132 = 현재 슬롯
        res['sub_step']     = raw[33] if len(raw) > 33 else 0  # DT133 = 스택 깊이

        # ===== 10. 병렬 워커1 실행 상태 (DT134~135) =====
        # DT134: FB_Sub.i_CurrentSlot (병렬 워커1이 실행 중인 슬롯, 0=idle)
        # DT135: FB_Sub.i_CurrentStep (병렬 워커1이 실행 중인 스텝)
        # 키명 monitor_slot/monitor_step은 구버전 호환 유지.
        res['monitor_slot'] = raw[34] if len(raw) > 34 else 0  # DT134
        res['monitor_step'] = raw[35] if len(raw) > 35 else 0  # DT135

        # ===== 11. 자동운전 생산 정보 (DINT) =====
        # DT136~137: 스택수량, DT138~139: 포장수량, DT140~141: 예약수량
        if len(raw) > 37:
            res['total_count'] = raw[36] | (raw[37] << 16)  # DT136-137
            res['stack_count'] = res['total_count']
        else:
            res['total_count'] = 0
            res['stack_count'] = 0

        if len(raw) > 39:
            v = raw[38] | (raw[39] << 16)
            res['pack_count'] = v
            res['mold_time'] = v / 10.0  # 0.1초 → 초 변환
        else:
            res['pack_count'] = 0
            res['mold_time'] = 0.0

        if len(raw) > 41:
            v = raw[40] | (raw[41] << 16)
            res['reserve_count'] = v
            res['setting_count'] = v
            res['takeout_time'] = v / 10.0  # 0.1초 → 초 변환
        else:
            res['reserve_count'] = 0
            res['setting_count'] = 0
            res['takeout_time'] = 0.0

        # ===== 14. 축 알람 상태 (DT142) + 축별 에러코드 (DT143~DT158) =====
        # DT142: 비트0=1축, 비트1=2축, ... 비트7=8축, 비트8=비상정지
        # DT143~158: 축별 에러코드 (DINT, 2워드씩)
        res['axis_alarms'] = []
        res['axis_error_codes'] = [0] * 8  # 8축 에러코드
        if len(raw) > 42:
            alarm_word = raw[42]
            for i in range(8):
                if alarm_word & (1 << i):
                    res['axis_alarms'].append(i + 1)  # 축 번호 (1~8)
            if alarm_word & (1 << 8):  # 비상정지 (9번째 비트)
                res['axis_alarms'].append(9)
        for i in range(8):
            idx = 43 + i * 2  # DT143=index43, DT145=index45, ...
            if len(raw) > idx + 1:
                res['axis_error_codes'][i] = raw[idx] | (raw[idx + 1] << 16)

        # ===== 15. 사용자 알람 (DT159) =====
        # new_plc_fb.st의 w_UserAlarm - IN 스텝 P3=1/2 에서 세팅
        # 0=없음, N=알람번호, N+1000=알람+진행
        res['user_alarm'] = raw[59] if len(raw) > 59 else 0

        # ===== 16. 스텝 알람 ID (DT160) =====
        # new_plc_fb.st의 i_StepAlarmID (VAR_IN_OUT, 공유 변수 → g_StepAlarmID)
        # 0=없음, 21/50/93~99=스텝 진행 에러
        res['step_alarm_id'] = raw[60] if len(raw) > 60 else 0

        # ===== 17. 패킹 스택 인덱스 (DT161~163) =====
        # PLC FB가 사이클 완료 시 증가시키는 x/y/z 현재 적층 위치 (0-based)
        res['pack_idx'] = [
            raw[61] if len(raw) > 61 else 0,
            raw[62] if len(raw) > 62 else 0,
            raw[63] if len(raw) > 63 else 0,
        ]
        res['home_request'] = raw[64] if len(raw) > 64 else 0
        res['home_done'] = bool(raw[65]) if len(raw) > 65 else False

        return res

    # =========================================================
    # 유틸리티
    # =========================================================

    def current_op_status(self):
        """마지막 모니터링값 기준 운전 상태. 0=정지, 1=자동, 2=확인운전."""
        try:
            return int(self._last_monitor_data.get("op_status", 0))
        except (TypeError, ValueError):
            return 0

    def is_sequence_running(self):
        return self.current_op_status() in (1, 2)

    def begin_recipe_transfer(self):
        """시퀀스/포인트 전체 전송 시작. 운전 중이면 DT 영역 갱신을 금지한다."""
        if self.is_sequence_running():
            print(f"[PLC] X 운전 중(op_status={self.current_op_status()})이라 시퀀스/포인트 전송 차단")
            return False
        self._recipe_transfer_active = True
        return True

    def end_recipe_transfer(self):
        self._recipe_transfer_active = False

    def is_recipe_transfer_active(self):
        return self._recipe_transfer_active
    
    def read_dint(self, area_code, addr):
        """DINT(32비트) 읽기"""
        words = self.read_words(area_code, addr, 2)
        if words and len(words) == 2:
            v = words[0] | (words[1] << 16)
            if v >= 0x80000000:
                v -= 0x100000000
            return v
        return 0
    
    # =========================================================
    # 시퀀스 데이터 전송 (HMI → PLC)
    # =========================================================
    
    def _split_32bit(self, value):
        """32비트 값을 Low/High Word로 분리"""
        v = int(value)
        if v < 0:
            v += 0x100000000
        low = v & 0xFFFF
        high = (v >> 16) & 0xFFFF
        return low, high
    
    def _convert_active_axes_to_word(self, active_axes):
        """
        사용축 배열을 1개 Word로 변환 (비트 패킹)
        
        active_axes: [True, False, True, ...] (8개 축)
        반환: 0x0000 ~ 0x00FF (비트 0~7)
        
        예시:
        - [True, False, False, ...] → 0x0001 (X축만)
        - [True, True, False, ...] → 0x0003 (X, Y축)
        - [True, True, True, ...] → 0x0007 (X, Y, Z축)
        """
        if not active_axes or not isinstance(active_axes, list):
            return 0x00FF  # 기본값: 전축 사용
        
        word_value = 0
        for i in range(min(8, len(active_axes))):
            if active_axes[i]:
                word_value |= (1 << i)
        
        return word_value
    
    def _convert_json_step_to_10words(self, step_data):
        """
        JSON 스텝 데이터를 10 Words로 변환
        
        step_data: {
            "type": "POS" | "OUT" | "IN" | "TMR" | "JMP" | "CALL" | "END",
            "active_axes": [True, True, False, ...],  # POS 스텝용
            ...
        }
        
        반환: [cmd, opt, p1_low, p1_high, p2_low, p2_high, p3_low, p3_high, p4_low, p4_high]
        """
        cmd, opt, p1, p2, p3, p4 = 0, 0, 0, 0, 0, 0
        step_type = step_data.get("type", "NOP")
        
        if step_type == "POS":
            cmd = 10
            p1 = int(step_data.get("point_index", 0))
            # [D-1 방어] point_index 범위 검증 (0..59). 범위 밖이면 0 으로 강제 + 경고.
            # 포인트 rename/삭제 후 점인덱스 재계산 누락 시 잘못된 위치로 이동 방지.
            if p1 < 0 or p1 > 59:
                print(f"    [!] POS point_index={p1} 범위 밖 (0..59). "
                      f"point_name='{step_data.get('point_name', '')}' → 0 으로 fallback")
                p1 = 0

            # ★ 사용축 비트를 opt에 저장 (bit 0~7)
            active_axes = step_data.get("active_axes", [True] * 8)
            opt = self._convert_active_axes_to_word(active_axes)

            # ★ 파렛타이징 베이스 플래그 (bit 8 = 0x0100)
            if step_data.get("pack_base"):
                opt |= 0x0100

            # ★ 이행 모드 (diParam2): 0=완료 후 이행(기본), 1=동시 이행
            #   wait_completion 키 누락 시 True(완료 후 이행)로 간주 → 기존 레시피 하위호환
            wait_completion = step_data.get("wait_completion", True)
            p2 = 0 if wait_completion else 1

            # 디버그 출력
            axes_str = "".join(["X" if active_axes[0] else "-",
                               "Y" if active_axes[1] else "-",
                               "Z" if active_axes[2] else "-",
                               "Y2" if active_axes[3] else "-",
                               "Z2" if active_axes[4] else "-",
                               "θ" if active_axes[5] else "-",
                               "R1" if active_axes[6] else "-",
                               "R2" if active_axes[7] else "-"])
            pb = " [PB]" if step_data.get("pack_base") else ""
            ex = "완료후" if wait_completion else "동시"
            print(f"    → 사용축: {axes_str} (0x{opt:04X}){pb} 이행={ex}(p2={p2})")
            
        elif step_type == "OUT":
            cmd = 20
            on_value = step_data.get("on", step_data.get("on_off", False))
            opt = 1 if on_value else 0
            port = int(step_data.get("port", step_data.get("io_index", 0)))
            # out_type: 0=시스템출력(DT203), 1=밸브출력(DT204), 2=내부비트(DT300~301)
            out_type = int(step_data.get("out_type", 0))
            p1 = port
            p2 = out_type
            # p3: 딜레이 시간 (0=즉시, >0=타이머 기동후출력, 단위 0.01초)
            if step_data.get("delay_enable", False):
                delay_time = float(step_data.get("delay_time", 0.0))
                p3 = int(delay_time * 100)
            print(f"[DEBUG OUT] out_type={out_type}, bit={port}, on={on_value}, delay_p3={p3}")
            
        elif step_type == "IN":
            cmd = 21
            # ★ "on" 키 지원
            on_value = step_data.get("on", step_data.get("on_off", True))
            opt = 1 if on_value else 0
            # ★ "port" 키 지원
            port = int(step_data.get("port", step_data.get("io_index", 0)))
            
            print(f"[DEBUG IN] step_data: {step_data}")
            print(f"[DEBUG IN] port={port}, on={on_value}")
            
            # ★ 포트 종류별 처리
            if 100 <= port <= 131:
                p1 = port  # 내부 비트 M00~M31
                print(f"[DEBUG IN] 내부비트 M{port-100:02d} → P1={p1}")
            else:
                p1 = port  # 시스템/밸브 입력 X
                print(f"[DEBUG IN] 입력 X{port:02X} → P1={p1}")
            
            # ★ P2: 타임아웃 (1초 = 100 단위, 미사용 시 0)
            timeout_enabled = step_data.get("timeout_enabled", True)
            timeout_sec = float(step_data.get("timeout", 5.0))
            p2 = int(timeout_sec * 100) if timeout_enabled else 0
            
            # ★ P3: 타임아웃 동작 (0:계속대기, 1:알람+정지, 2:알람+진행)
            action = step_data.get("timeout_action", "continue")
            if action == "ask":
                p3 = 1
            elif action == "alarm_go":
                p3 = 2
            else:  # "continue"
                p3 = 0

            # ★ P4: 알람 번호 (알람 동작일 때 사용)
            p4 = int(step_data.get("timeout_alarm_no", 1))

            print(f"[DEBUG IN] timeout={timeout_sec}s({p2}units), action={action}({p3}), alarm_no={p4}")
            
        elif step_type == "TMR":
            cmd = 30
            # 1초 = 100 단위 (page_timer와 동일 기준)
            if "time" in step_data:
                p1 = int(float(step_data["time"]) * 100)
            elif "value" in step_data:
                p1 = int(step_data["value"])
            else:
                p1 = 100

            if step_data.get("tmr_mode") == "hold":
                # 신호 유지 모드: p2=포트, p3=1(모드플래그), opt=ON(1)/OFF(0)
                p2 = int(step_data.get("port", 0))
                p3 = 1
                opt = 1 if step_data.get("on", True) else 0
                print(f"[DEBUG TMR-HOLD] port={p2}, on={bool(opt)}, hold_time={p1}")
            # else: 단순 대기 - p2=p3=0, opt=0 그대로
                
        elif step_type == "JMP":
            cmd = 40

            is_conditional = step_data.get("condition", False)

            if is_conditional:
                p1 = int(step_data.get("target_step", 0))
                cond_type = step_data.get("cond_type", "PORT")

                if cond_type == "DTCMP":
                    # ── 조건부·데이터값 비교 점프 (opt=2) [신규] ──────────────
                    # PLC 계약: cmd==40 && opt==2 이면
                    #   DT[p2] 값을 p3 연산자로 p4(상수)와 비교, 참이면 p1 스텝으로 점프.
                    #   연산자(p3): 0:==  1:≠  2:>  3:≥  4:<  5:≤
                    # ⚠ PLC 펌웨어가 opt==2 분기를 구현해야 동작. 미구현 시 무동작.
                    #   실장비 검증 전 라이브 레시피 투입 금지.
                    opt = 2
                    p2 = int(step_data.get("cmp_dt_addr", 0))
                    p3 = int(step_data.get("cmp_op", 0))
                    p4 = int(step_data.get("cmp_const", 0))
                    print(f"[DEBUG JMP DT비교] target={p1}, DT{p2} (op={p3}) const={p4} (opt=2)")
                else:
                    # 조건부·비트 점프 (opt=1)
                    opt = 1
                    if cond_type == "MODE":
                        p2 = 1
                    elif cond_type == "STATE":
                        p2 = 2
                    else:
                        p2 = 0
                    p3 = int(step_data.get("cond_value", 0))
                    p4 = 1 if step_data.get("cond_on", True) else 0

                    print(f"[DEBUG JMP 조건부] target={p1}, type={cond_type}({p2}), value={p3}, on={p4}")

            else:
                # 무조건 점프 (opt=0)
                opt = 0
                p1 = int(step_data.get("target_step", 0))
                print(f"[DEBUG JMP 무조건] target={p1}")
            
        elif step_type == "CALL":
            cmd = 50
            p1 = int(step_data.get("sequence_id", 0))
            
            # ★ 실행 모드: 0=대기, 1=동시실행
            is_parallel = step_data.get("parallel", False)
            opt = 1 if is_parallel else 0
            
            print(f"[DEBUG CALL] seq_id={p1}, parallel={is_parallel}({opt})")
            
        elif step_type == "DAT":
            # ── 데이터연산 (cmd 60): g_DTPool(DT60000~60099) 상수 대입/가산/감산 ──
            #   p1 = 대상 DT 절대주소(60000~60099), p2 = 연산자(0:대입 1:가산 2:감산), p3 = 상수
            #   ⚠ PLC FB 가 cmd 60 / state 100 을 구현해야 동작. 빌드·다운로드 전 라이브 투입 금지.
            cmd = 60
            p1 = int(step_data.get("dat_dt_addr", 60000))
            p2 = int(step_data.get("dat_op", 0))      # 0:대입 1:가산 2:감산
            p3 = int(step_data.get("dat_const", 0))   # 16비트 부호 상수
            _opname = {0: "대입", 1: "가산", 2: "감산"}.get(p2, "?")
            print(f"[DEBUG DAT] DT{p1} {_opname}(op={p2}) const={p3}")

        elif step_type == "END":
            cmd = 99

        # 32비트 값을 Low/High Word로 분리
        p1_l, p1_h = self._split_32bit(p1)
        p2_l, p2_h = self._split_32bit(p2)
        p3_l, p3_h = self._split_32bit(p3)
        p4_l, p4_h = self._split_32bit(p4)
        
        return [cmd, opt, p1_l, p1_h, p2_l, p2_h, p3_l, p3_h, p4_l, p4_h]
    
    def send_sequence_to_slot(self, slot_id, json_steps):
        """
        시퀀스 데이터를 PLC 슬롯에 전송 (분할 전송)
        
        slot_id: 0~39 (0=Main, 1~39=서브 시퀀스)
        json_steps: 스텝 딕셔너리 리스트
        
        반환: True=성공, False=실패
        """
        if self.is_sequence_running():
            print(f"[PLC] X 운전 중(op_status={self.current_op_status()})이라 Slot {slot_id} 시퀀스 전송 차단")
            return False
        if not (0 <= slot_id < self.MAX_SLOTS):
            print(f"[PLC] X 잘못된 슬롯 번호: {slot_id}")
            return False
        
        # ★ 자동으로 END 스텝 추가 (마지막에 END가 없으면)
        steps_with_end = list(json_steps)  # 복사
        if not steps_with_end or steps_with_end[-1].get("type") != "END":
            steps_with_end.append({"type": "END", "name": "시퀀스 종료"})
            print(f"[PLC] i  END 스텝 자동 추가됨")
        
        print(f"[PLC] → Slot {slot_id} 시퀀스 변환 시작 ({len(steps_with_end)}개 스텝)")
        
        # JSON 스텝을 10 Words씩 변환
        flat_data = []
        for idx, step in enumerate(steps_with_end):
            if step.get("type") == "POS":
                active_axes = step.get("active_axes", step.get("axes", []))
                if self._convert_active_axes_to_word(active_axes) == 0:
                    print(f"  X Step {idx}: POS 사용축이 0개라 전송 중단")
                    return False
            try:
                words = self._convert_json_step_to_10words(step)
                flat_data.extend(words)
                print(f"  Step {idx}: {step.get('type', 'NOP')} → CMD={words[0]}, OPT=0x{words[1]:04X}, P1={words[2]|words[3]<<16}")
            except Exception as e:
                print(f"  X Step {idx} 변환 실패: {e}")
                flat_data.extend([0] * 10)
        
        # 100개 스텝 = 1000 Words로 패딩
        total_len = 100 * 10
        if len(flat_data) < total_len:
            flat_data.extend([0] * (total_len - len(flat_data)))

        # ★★★ 한 번에 전송 (1000 Words = 1000 Words 제한, 분할 전송) ★★★
        addr = self.SEQ_BASE_ADDR + (slot_id * self.SLOT_SIZE)
        print(f"[PLC] → DT{addr}에 {len(flat_data)} Words 전송 중...")
        
        result = self.write_words(0x09, addr, flat_data)
        
        if result:
            print(f"[PLC] O Slot {slot_id} 전송 성공")
            return True
        else:
            print(f"[PLC] X Slot {slot_id} 전송 실패")
            return False
    
    def send_all_points(self, points_dict, ordered_names):
        """
        모든 포인트 데이터를 PLC에 전송 (분할 전송)
        
        points_dict: {"Point_1": {"coords": [...], "speeds": [...]}, ...}
        ordered_names: ["Point_1", "Point_2", ...]
        
        반환: True=성공, False=실패
        """
        if self.is_sequence_running():
            print(f"[PLC] X 운전 중(op_status={self.current_op_status()})이라 포인트 테이블 전송 차단")
            return False
        print(f"[PLC] → 포인트 테이블 전송 시작 ({len(ordered_names)}개 포인트)")
        
        # 100개 포인트 × 32 Words = 3200 Words 버퍼 생성
        total_buffer = [0] * (self.MAX_POINTS * self.POINT_SIZE)
        
        for i, name in enumerate(ordered_names):
            if i >= self.MAX_POINTS:
                print(f"  [!] 최대 포인트 수({self.MAX_POINTS}) 초과, {name} 스킵")
                break
            
            if name not in points_dict:
                print(f"  [!] 포인트 '{name}' 데이터 없음")
                continue
            
            try:
                p_data = points_dict[name]
                coords = p_data.get("coords", [0.0] * 8)
                speeds = p_data.get("speeds", [100.0] * 8)
                
                # 포인트 데이터 생성 (32 Words)
                chunk = [0] * self.POINT_SIZE
                chunk[0] = 0xFF      # 유효 플래그
                chunk[1] = 100       # 전체 속도
                
                # 8축 좌표 (0.001mm 단위로 변환)
                for axis in range(8):
                    val_int = int(float(coords[axis]) * 1000)
                    low, high = self._split_32bit(val_int)
                    chunk[2 + axis*2] = low
                    chunk[3 + axis*2] = high
                
                # 8축 속도 (%)
                for axis in range(8):
                    chunk[18 + axis] = int(float(speeds[axis]))
                
                # 버퍼에 복사
                start_idx = i * self.POINT_SIZE
                total_buffer[start_idx : start_idx + self.POINT_SIZE] = chunk
                
                print(f"  Point {i}: {name} → X={coords[0]:.3f}, Y={coords[1]:.3f}")
                
            except Exception as e:
                print(f"  X 포인트 '{name}' 변환 실패: {e}")
        
        # ★★★ 분할 전송 (500 Words = 1000 Bytes씩, 안정성 우선) ★★★
        print(f"[PLC] → DT{self.POINT_BASE_ADDR}에 분할 전송 중...")
        chunk_size = 500  # 500 Words씩 전송 (안정성 확보)
        total_chunks = (len(total_buffer) + chunk_size - 1) // chunk_size
        
        for i in range(0, len(total_buffer), chunk_size):
            chunk_num = i // chunk_size + 1
            chunk = total_buffer[i:i+chunk_size]
            addr = self.POINT_BASE_ADDR + i
            
            print(f"  → Chunk {chunk_num}/{total_chunks}: DT{addr} ({len(chunk)} Words)")
            result = self.write_words(0x09, addr, chunk)
            
            if not result:
                print(f"[PLC] X 포인트 Chunk {chunk_num}/{total_chunks} 전송 실패 (DT{addr})")
                return False
            
            # 진행 상황 표시
            progress = (chunk_num * 100) // total_chunks
            print(f"  O 완료: {progress}%")
            
            # 짧은 대기 (안정성)
            time.sleep(0.05)  # 50ms (여유 확보)
        
        print(f"[PLC] O 포인트 테이블 전송 성공 ({total_chunks}개 청크)")
        return True
