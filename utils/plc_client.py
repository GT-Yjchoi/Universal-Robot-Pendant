import socket
import struct
import threading
import time
import queue
import itertools
import os
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
        self._command_queue = queue.PriorityQueue()
        self._command_sequence = itertools.count()
        self._next_monitor_at = 0.0
        self._last_monitor_at = 0.0
        self._command_thread = threading.Thread(
            target=self._command_loop, name="plc-communication-core", daemon=True
        )
        self.sig_async_done.connect(self._deliver_async_result)
        self._command_thread.start()

        # --- PLC 통신 설정 ---
        self.USE_HEADER = True      
        self.DEST_UNIT_NO = 0x01    
        
        # ===== 메모리 맵 =====

        # 1. 실시간 모니터링 블록 (PLC → HMI): DT100~
        self.MONITOR_ADDR  = 100
        self.MONITOR_COUNT = 68  # DT100~167
        # 2. 팬던트 → PLC 상태/수동 명령 블록 (확정 DT 맵)
        self.HEARTBEAT_ADDR       = 200  # 통신 하트비트
        self.ADDR_OPERATION_STATE = 201  # 현재 운전상태 (팬던트가 기록)
        self.ADDR_OUTPUT_BASE     = 210  # DT210~213: 설정된 출력 그룹 1~4 요청
        self.ADDR_JOG_CTRL        = 220  # 축 JOG 명령 비트
        self.ADDR_JOG_SPEED       = 221  # JOG 속도
        self.ADDR_SPEED_OVR       = 222  # 전체 속도 배율
        self.ADDR_AXIS_STOP       = 223  # 축 정지 요청
        self._operation_state = 0
        self._axis_jog_bits = 0
        self._axis_jog_lock = threading.Lock()
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

        # 5. 축 설정 블록: DT15000~ (50 Words)
        self.AXIS_PARAM_ADDR   = 15000
        self.ADDR_AXIS_DATASET = self.AXIS_PARAM_ADDR + 33  # 데이터셋 트리거

    def submit(self, func, *args, callback=None, priority=10):
        """Run a PLC operation in the single ordered backend queue.

        The optional callback is delivered on the Qt/UI thread as
        ``callback(result, error)``.  UI code never needs to wait for TCP.
        """
        self._command_queue.put(
            (int(priority), next(self._command_sequence), func, args, callback)
        )

    def _command_loop(self):
        self._pin_communication_thread()
        while True:
            now = time.monotonic()
            timeout = 0.05
            if self._monitor_running and self.is_connected:
                timeout = max(0.0, min(0.02, self._next_monitor_at - now))
            try:
                _, _, func, args, callback = self._command_queue.get(
                    timeout=timeout
                )
            except queue.Empty:
                func = None
            if func is not None:
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

            now = time.monotonic()
            monitor_due = (
                self._monitor_running and self.is_connected
                and now >= self._next_monitor_at
            )
            monitor_forced = now - self._last_monitor_at >= 0.06
            if monitor_due and (self._command_queue.empty() or monitor_forced):
                self._poll_monitor_once()
                now = time.monotonic()
                self._last_monitor_at = now
                self._next_monitor_at = now + 0.02

    @staticmethod
    def _pin_communication_thread():
        """Best-effort Linux CPU affinity for the PLC worker only.

        ``auto`` selects the last available CPU when at least two CPUs exist.
        Set ``PENDANT_PLC_CPU=off`` to disable or provide an explicit CPU index.
        No real-time scheduler policy is requested, so a communication fault
        cannot starve the QML render or operating-system threads.
        """
        if not hasattr(os, "sched_getaffinity"):
            return
        value = os.environ.get("PENDANT_PLC_CPU", "auto").strip().lower()
        if value in {"", "off", "false", "none", "-1"}:
            return
        try:
            available = sorted(os.sched_getaffinity(0))
            if len(available) < 2:
                return
            cpu = available[-1] if value == "auto" else int(value)
            if cpu not in available:
                raise ValueError(
                    f"CPU {cpu} is not available; choices are {available}"
                )
            os.sched_setaffinity(0, {cpu})
            print(f"[PLC] 통신 스레드 CPU{cpu} 고정")
        except (OSError, ValueError) as exc:
            print(f"[PLC] 통신 스레드 CPU 고정 생략: {exc}")

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
        하트비트 값을 +1 증가시키고 DT200에 전송
        - 0~100 범위를 순환
        - 100 다음에는 0으로 리셋
        - 무한루프 방지: _heartbeat_skip 플래그 사용
        """
        # 하트비트 값 증가
        self.heartbeat_value += 1
        if self.heartbeat_value > 100:
            self.heartbeat_value = 0
        
        # DT200에 하트비트 값 쓰기 (무한루프 방지)
        if not self._heartbeat_skip:
            self._heartbeat_skip = True  # 플래그 설정으로 재귀 방지
            try:
                # send_packet을 직접 호출하지 않고 저수준으로 전송
                body = struct.pack('<BBBHH', 0x80, 0x50, 0x09, self.HEARTBEAT_ADDR, 1)
                data_part = struct.pack('<H', self.heartbeat_value)
                self._send_packet_raw(body + data_part)
                # print(f"[하트비트] DT200 = {self.heartbeat_value}")  # 필요시 주석 해제
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
    # 팬던트 상태/수동 명령 (팬던트 → PLC)
    # =========================================================
    
    def send_operation_state(self, state):
        """DT201: 팬던트가 관리하는 현재 운전상태를 PLC에 알린다."""
        state = max(0, min(3, int(state)))
        self._operation_state = state
        print(f"[PLC] 현재 운전상태 → DT{self.ADDR_OPERATION_STATE} = {state}")
        return self.write_words(0x09, self.ADDR_OPERATION_STATE, [state])

    def send_control_command(self, mode):
        """Compatibility alias: execution is local; only the state is reported."""
        return self.send_operation_state(mode)
    
    def send_jog_command(self, jog_value):
        """Legacy pressure-selection command; no DT is assigned in the new map."""
        print("[PLC] 조작압 선택은 팬던트 내부 설정으로 변경됨")
        return True
    
    def send_check_run_command(self, state):
        """Check-run stepping is owned by the pendant in the new map."""
        return True
    
    def write_jog_bits(self, bit_mask):
        """Write the four configured 16-bit output groups at DT210..DT213."""
        words = [(int(bit_mask) >> (16 * i)) & 0xFFFF for i in range(4)]
        return bool(self.write_words(0x09, self.ADDR_OUTPUT_BASE, words))

    def write_jog_bit(self, bit_pos, is_on):
        """Write one configured output in compact group order."""
        bit_pos = max(0, min(63, int(bit_pos)))
        addr = self.ADDR_OUTPUT_BASE + bit_pos // 16
        bit_index = bit_pos % 16
        return self.write_bit(0x09, addr, bit_index, is_on)
    
    def send_jog_control(self, jog_bit):
        """DT220: 축별 JOG 방향 명령 비트."""
        with self._axis_jog_lock:
            self._axis_jog_bits = int(jog_bit) & 0xFFFF
            value = self._axis_jog_bits
        return self.write_words(0x09, self.ADDR_JOG_CTRL, [value])

    def write_axis_jog_bit(self, bit_pos, is_on):
        """Update pendant-owned DT220 locally and send it with one TCP write."""
        bit_pos = int(bit_pos)
        if not 0 <= bit_pos < 16:
            raise ValueError(f"axis JOG bit out of range: {bit_pos}")
        with self._axis_jog_lock:
            if is_on:
                # Never permit + and - for the same axis at the same time.
                self._axis_jog_bits &= ~(1 << (bit_pos ^ 1))
                self._axis_jog_bits |= 1 << bit_pos
            else:
                self._axis_jog_bits &= ~(1 << bit_pos)
            value = self._axis_jog_bits
        return self.write_words(0x09, self.ADDR_JOG_CTRL, [value])

    def reset_axis_jog(self):
        """Clear every DT220 JOG direction bit after startup/reconnect/close."""
        return self.send_jog_control(0)
    
    def send_mode_settings(self, mode_data):
        """User modes are evaluated on the pendant; retained as a no-op API."""
        return True

    def read_mode_settings(self):
        return None

    def send_axis_stop(self, active):
        """DT223: pendant-requested axis stop (not a safety-rated E-stop)."""
        val = 1 if active else 0
        print(f"[PLC] 축 정지 요청 → DT{self.ADDR_AXIS_STOP} = {val}")
        return self.write_words(0x09, self.ADDR_AXIS_STOP, [val])

    def send_soft_estop(self, active):
        return self.send_axis_stop(active)

    def send_jog_mode(self, mode):
        """Manual motion selection is owned by the pendant."""
        return True

    def send_speed_override(self, level):
        """
        DT222: 전체 속도 배율 (1~10 단계)
        - 자동/확인운전 시 전체 속도에 곱해지는 배율
        """
        level = max(1, min(10, int(level)))
        print(f"[PLC] 전체 속도 배율 → DT{self.ADDR_SPEED_OVR} = {level}")
        return self.write_words(0x09, self.ADDR_SPEED_OVR, [level])

    def send_packing_config(self, cfg):
        """
        Compatibility no-op. Packing configuration and indices are now owned
        entirely by the pendant; DT217~230 are reserved.
        """
        return True

    def write_pack_idx(self, axis, value):
        """Compatibility no-op; packing indices are stored by the pendant."""
        return False

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
        """Enable cyclic reads on the dedicated communication core."""
        if self._monitor_running:
            return
        self._monitor_running = True
        self._next_monitor_at = 0.0
        self._last_monitor_at = time.monotonic()
        print("[PLC] 전용 통신 코어 시작 (명령 우선, 모니터 약 33Hz)")

    def _poll_monitor_once(self):
        raw = self.read_words(0x09, self.MONITOR_ADDR, self.MONITOR_COUNT)
        if raw and len(raw) >= self.MONITOR_COUNT:
            try:
                result = self._parse_monitor_data(raw)
                self._last_monitor_data = result
                self.sig_monitor_data.emit(result)
            except Exception as exc:
                print(f"[PLC] 모니터링 파싱 에러: {exc}")
        now = time.monotonic()
        if now - self._last_heartbeat_at >= 0.5:
            self._last_heartbeat_at = now
            self._update_heartbeat()

    def _parse_monitor_data(self, raw):
        """
        모니터링 데이터 파싱
        raw: DT100~DT167의 Word 배열 (68개)
        """
        res = {}

        def dint(offset, *, signed=False):
            value = raw[offset] | (raw[offset + 1] << 16)
            if signed and value >= 0x80000000:
                value -= 0x100000000
            return value
        
        # ===== 1. 8축 현재 위치 (DT100~115) =====
        # DINT * 8 = 16 Words
        res['axis_pos'] = []
        for i in range(0, 16, 2):
            v = dint(i, signed=True)
            # 0.001mm 단위 → mm 변환
            res['axis_pos'].append(v / 1000.0)

        # ===== 2. 축 알람/비상정지 (DT116) =====
        # bit0~7=1~8축 알람, bit8=비상정지
        res['axis_alarms'] = []
        alarm_word = raw[16]
        for i in range(8):
            if alarm_word & (1 << i):
                res['axis_alarms'].append(i + 1)
        if alarm_word & (1 << 8):
            res['axis_alarms'].append(9)

        # ===== 3. 8축 원점완료 비트맵 (DT117) =====
        res['axis_home_bits'] = raw[17] & 0x00FF
        # 활성 축 판단 전에도 사용할 수 있는 보수적인 호환값이다.
        res['home_done'] = res['axis_home_bits'] == 0x00FF

        # DT118~119: 예약

        # ===== 4. 8축 에러코드 (DT120~135, DINT×8) =====
        res['axis_error_codes'] = [dint(20 + i * 2) for i in range(8)]

        # DT136~139: 예약

        # ===== 5. 실제 입출력 상태 =====
        # 4 WORD = X/Y 00~3F, 한 워드가 16점인 비압축 매핑
        res['inputs'] = raw[40:44]    # DT140~143
        res['outputs'] = raw[44:48]   # DT144~147

        # DT148~149: 예약

        # ===== 6. PLC 운전모드 상태 (DT150) =====
        # 팬던트가 DT201에 쓰는 현재 운전상태와 구분한다.
        res['operation_mode_status'] = raw[50]

        # DT151~159: 예약

        # ===== 7. 생산 정보 (DT160~167, DINT×4) =====
        production_count = dint(60)
        target_count = dint(62)
        takeout_cycle_raw = dint(64)
        molding_cycle_raw = dint(66)

        res['production_count'] = production_count
        res['total_count'] = production_count
        res['stack_count'] = production_count
        res['target_count'] = target_count
        res['setting_count'] = target_count
        res['takeout_cycle_time'] = takeout_cycle_raw / 10.0
        res['takeout_time'] = res['takeout_cycle_time']
        res['molding_cycle_time'] = molding_cycle_raw / 10.0
        res['mold_time'] = res['molding_cycle_time']

        return res

    # =========================================================
    # 유틸리티
    # =========================================================

    def current_op_status(self):
        """Pendant-owned operation state mirrored to DT201."""
        return int(self._operation_state)

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
            # Legacy encoder only: current execution uses the DT300 mailbox.
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
