# Universal Robot Pendant — 산업용 서보 제어 HMI

Raspberry Pi 5와 Raspberry Pi OS Lite 64-bit 기반 PySide6 풀스크린 HMI 앱.
파나소닉 PLC(FPWIN Pro)와 TCP(MEWTOCOL-style) 통신으로 8축 서보 시스템을 제어하고 시퀀스·포인트를 관리합니다.

---

## 실행 환경

| 항목 | 값 |
|---|---|
| 플랫폼 | Raspberry Pi 5 (aarch64) |
| OS | Raspberry Pi OS Lite 64-bit — 데스크톱 환경 없음 |
| Python | `/home/yjchoi/pyside-env/bin/python` + PySide6 venv |
| 프로젝트 경로 | `/home/yjchoi/Universal-Robot-Pendant/` |
| 가상환경 | `/home/yjchoi/pyside-env` |
| Qt 플랫폼 | **Wayland on Weston DRM kiosk** (`QT_QPA_PLATFORM=wayland`) |
| 디스플레이 | Raspberry Pi DSI 패널 (`weston-rpi.ini`에서 출력/회전 관리) |
| 터치 입력 | weston/libinput 입력 처리 |
| 자동 실행 | `pendant-rpi-lite.service` → `launch-rpi-lite.sh` → Weston kiosk + `main.py` |
| WiFi 스캔 권한 | polkit 규칙 `/etc/polkit-1/rules.d/50-netdev-wifi.rules` + `netdev` 그룹 |
| 유선 이더넷 | NM 프로파일에 `ipv4.never-default=yes` — PLC 전용 LAN 이 디폴트 라우트로 승격되는 것 차단 |

Qt의 EGLFS 플러그인은 현재 PySide6 ARM64 wheel에서 의존 라이브러리가 빠져 실행되지 않아,
검증된 구성은 Raspberry Pi의 Mesa/V3D 위에 최소 Weston DRM compositor만 띄우는 방식이다.
Raspberry Pi OS Desktop은 필요하지 않다.

### 통신 드라이버

- `drivers.plc.PLCClient`: 기존 PLC 통신 공개 API. 현재 팬던트의 기본 백엔드로 유지한다.
- `drivers.fastech_ezi_io.EziIOClient`: FASTECH Ezi-IO Plus-E UDP 드라이버.
  Linux에서 제조사 Windows DLL 없이 UDP 3001 프로토콜을 직접 사용한다.
- Ezi-IO 출력 쓰기는 기본 잠금 상태이며 `allow_writes=True`를 명시해야 한다.
- `scripts/ezi_io_probe.py <IP>`: 장치 정보와 입출력 상태만 읽는 안전한 연결 시험.
- `scripts/ezi_io_output_test.py <IP>`: 부하가 없는 I8O8 모듈의 8개 출력과 하드웨어 트리거 시험.

현재 검증 장치는 `Ezi-IO-EN-I8O8N-T` (`192.168.0.5`)이다. Raspberry Pi의
`eth0`는 게이트웨이 없는 `192.168.0.10/24` DIO 전용망으로 구성하고, 원격 관리용
Wi-Fi 기본 경로와 분리한다. 프로토콜의 16/32비트 필드는 little-endian을 사용한다.
I8O8의 논리 출력 0~7은 통합 프로토콜 비트맵의 bit 8~15에 대응하므로 클라이언트를
`output_offset=8, output_count=8`로 생성한다.

---

## 프로젝트 구조

```
Pendant/
├── main.py                        # 진입점 (QApplication, PLCClient, MainWindow) + 스크린샷 핫키(F12) / 우상단 3초 롱프레스
├── main.spec                      # PyInstaller 빌드 스펙
├── pendant-rpi-lite.service       # Raspberry Pi OS Lite 자동 실행 서비스
├── launch-rpi-lite.sh             # Weston DRM kiosk + 앱 실행기
├── weston-rpi.ini                 # DSI 출력과 화면 회전 설정
├── settings.json                  # 사용자 설정 (PLC IP/Port, 밸브, IO 이름, 축 등)
├── style.qss                      # 전역 스타일시트 (Fusion 기반)
├── new_plc_fb.st                  # PLC 펑션블록 (현재 사용, 3-instance + 콜스택 + 파렛타이징 통합)
├── fb_WriteMotionTable.st         # RTEX 모션 테이블 일괄 쓰기 FB (포인트 60개 분량)
├── fb_MainAxis.st                 # 메인 축 제어 FB
├── fb_RTEX_Amp_Param.st           # RTEX 앰프 파라미터 FB
├── fb_Packing.st                  # [deprecated] 파렛타이징 독립 FB (현재 new_plc_fb 에 통합됨, 참고용)
├── fb_Packing_README.md           # 파렛타이징 PLC 통합 가이드 (DT 맵, FB 수정 내역)
├── new_plc_fb_README.md           # new_plc_fb.st 상세 문서
├── plc_Readme.md                  # PLC 공통 노트 (TON 배열 패턴, 메모리 맵 등)
├── alarm_history.json             # 알람 발생 이력 (최근 30일, .gitignore 대상)
├── op_history.json                # 사용자 조작 이력 (최근 7일, .gitignore 대상)
│
├── ui/                            # UI 레이어
│   ├── main_window.py             # 메인 윈도우 (페이지 스택, 네비게이션, 알람 오버레이)
│   ├── top_bar.py                 # 상단 바 (통신·모드·알람 상태, JOG 버튼)
│   ├── theme.py                   # 전역 테마
│   ├── overlays/
│   │   ├── alarm_overlay.py       # 축/E-STOP/시퀀스 알람 오버레이
│   │   └── alarm_history_overlay.py  # 이력 팝업 (알람 30일 / 조작 7일 탭)
│   ├── pages/
│   │   ├── page_manual.py         # 수동 운전 페이지 (밸브 수동 제어)
│   │   ├── page_auto.py           # 자동 운전 페이지 (시퀀스 실행, 확인운전, 전체속도 조절)
│   │   ├── page_mode.py           # 모드 설정 페이지 (40개 모드 On/Off)
│   │   ├── page_position.py       # 포인트 관리 + 시퀀스 미리보기 + 자동 중 미세조정
│   │   ├── page_timer.py          # 타이머 설정 페이지 (TMR 스텝 시간 편집)
│   │   ├── page_packing.py        # 패킹(팔레타이징) 페이지 — X/Y/Z축 설정, 사용 토글, 스택 순서, 시뮬레이션
│   │   ├── page_data.py           # 레시피 관리 (저장/로드/새로만들기/삭제)
│   │   └── page_settings.py       # 설정 페이지 (PLC/IO/축/밸브/알람/네트워크)
│   ├── dialogs/
│   │   ├── jog_control_dialog.py  # 조그 제어 팝업 (축별 수동 이동 + 밸브)
│   │   ├── sequence_editor_dialog.py  # 시퀀스 편집기 (스텝 추가/수정/삭제)
│   │   ├── sequence_step_ui.py    # 스텝 UI 위젯 (POS/OUT/IN/TMR/JMP/CALL/END/COMMENT)
│   │   ├── sequence_utils.py      # 공용 오버레이 (CardList, Rename, NumericKeypad 등)
│   │   └── timer_edit_dialog.py   # 타이머 값 편집 팝업
│   └── widgets/
│       ├── axis_position_panel.py # 축 위치 표시 패널
│       ├── valve_tile.py          # 밸브 타일 (Y 출력 실시간 동기화, 자동중 조작 차단 오버레이)
│       └── custom_inputs.py       # 커스텀 입력 위젯
│
├── utils/                         # 비즈니스 로직
│   ├── plc_client.py              # 파나소닉 PLC TCP 통신 클라이언트
│   ├── io_manager.py              # IO 이름 관리 (싱글톤)
│   ├── mode_manager.py            # 모드 이름 관리 (싱글톤)
│   ├── languages.py               # 다국어 지원 (한/영)
│   ├── gpio_estop.py              # GPIO 기반 하드 비상정지 입력
│   ├── wifi_manager.py            # WiFi / 유선 네트워크 nmcli 래퍼
│   ├── json_utils.py              # JSON 읽기/쓰기 공통 유틸
│   ├── paths.py                   # 리소스 경로 유틸 (PyInstaller 호환)
│   ├── alarm_history.py           # 알람 이력 기록 (30일)
│   ├── op_history.py              # 조작 이력 기록 (7일)
│   ├── axis_limits.py             # 축 스트로크 한계 조회·클램프
│   └── internal_bit_names.py      # 내부비트 M00~M31 사용자 정의 이름
│
├── widgets/                       # 공용 재사용 위젯
│   ├── nav_button.py              # 하단 네비게이션 버튼
│   ├── glass_card.py              # 글래스 카드 컨테이너
│   ├── io_panel.py                # IO 상태 패널
│   ├── square_toggle_tile.py      # 정사각형 토글 타일
│   ├── touch_keyboard.py          # 터치 소프트 키보드 (한/영 + 특수문자 _ . )
│   └── touch_number_keyboard.py   # 터치 숫자 키패드
│
├── assets/                        # 정적 리소스
│   └── fonts/                     # Pretendard 한글 폰트 번들
│
└── recipes/                       # 레시피 파일 (런타임 생성)
    └── *.json                     # 시퀀스·포인트·모드·전체속도 통합 저장
```

---

## 핵심 설계

### PLC 통신 (`utils/plc_client.py`)

- **대상 PLC**: 파나소닉 FP 시리즈 (FPWIN Pro, ST 프로그래밍)
- **프로토콜**: TCP, `DEST_UNIT=0x01`, 12바이트 헤더 프레임
- **모니터링**: DT100~DT163 (64 Words) 를 50ms 주기로 폴링
- **하트비트**: 통신 성공마다 DT214에 0~100 순환값 전송
- **자동 재연결**: 통신 끊김 시 5초 간격으로 재연결 시도

#### PLC 메모리 맵

| 영역 | 주소 | 내용 |
|---|---|---|
| **모니터링 (PLC→HMI)** | DT100~115 | 8축 현재 위치 (DINT×8, 0.001mm 단위) |
| | DT116~119 | 입력(X) 상태 (WORD×4, 64점) |
| | DT120~123 | 출력(Y) 상태 (WORD×4). 이 PLC 는 `DT120=Y00~Y0F`, `DT121=Y20~Y2F` 매핑 |
| | DT124~125 | 밸브 동작 상태 (32개 밸브 비트) |
| | DT126 | 병렬 워커2 실행 슬롯 (FB_Worker2.i_CurrentSlot, 0=idle) |
| | DT127 | 병렬 워커2 실행 스텝 (FB_Worker2.i_CurrentStep) |
| | DT128 | 미사용 |
| | DT129 | 운전 상태 (op_status: 0=정지, 1=자동, 2=확인운전) |
| | DT130 | 확인운전 상태 (check_run_status) |
| | DT131 | 현재 실행 스텝 (FB.i_CurrentStep, 스택 top 기준) |
| | DT132 | 현재 실행 슬롯 (FB.i_CurrentSlot: Main=0, 서브=1~N) |
| | DT133 | 콜 스택 깊이 (FB.i_StackDepth, 0~3) |
| | DT134 | 병렬 워커1 실행 슬롯 (FB_Sub.i_CurrentSlot, 0=idle) |
| | DT135 | 병렬 워커1 실행 스텝 (FB_Sub.i_CurrentStep) |
| | DT136~137 | 총 취출 횟수 (DINT) |
| | DT138~139 | 현재 성형 시간 (DINT, 0.1초 단위) |
| | DT140~141 | 현재 취출 시간 (DINT, 0.1초 단위) |
| | DT142 | 축 알람 비트맵 (bit0~7=1~8축, bit8=비상정지) |
| | DT143~158 | 축별 에러코드 (DINT×8축) |
| | DT159 | 사용자 알람 (`w_UserAlarm`, IN 스텝 P3=1/2 발동, 핸드셰이크: HMI 수신 후 0으로 클리어) |
| | DT160 | 스텝 알람 ID (`i_StepAlarmID`, 0=정상, 21/22/50/93~99) |
| | DT161~163 | **파렛타이징 현재 인덱스** (`gi_PackIdxX/Y/Z`, INT×3, 0-based, HMI 양방향 R/W) |
| **제어 (HMI→PLC)** | DT200 | 운전 제어 (0=정지, 1=자동, 2=확인운전) |
| | DT201 | 조작압 선택 (0=제품압, 1=티칭압) |
| | DT202 | 확인운전 제어 (상승엣지로 1스텝 진행) |
| | DT204~205 | 밸브 수동 제어 (2 Words, 32비트) |
| | DT205 | 조그 제어 (비트별 축) |
| | DT206~208 | 모드 설정 (40개 모드 비트팩, 3 Words) |
| | DT211 | 조그 속도 |
| | DT212 | 알람 리셋 상승펄스 → `b_AlarmReset` 으로 배선 |
| | DT213 | 소프트 비상정지 (0=정상, 1=비상정지) |
| | DT214 | 하트비트 (0~100 순환) |
| | DT215 | 수동조작 모드 (0=앱솔루트, 1=JOG) |
| | DT216 | 전체 속도 배율 (`gi_SpeedOverride`, 1~10 단계, 자동/확인운전 공통) |
| **파렛타이징 설정** | DT217 | 패킹 마스터 ON/OFF (`gw_PackEnable`, 0=미사용, 1=사용) — **commit pattern**: 설정 변경 시 가장 나중에 씀 |
| | DT218~223 | X/Y/Z 피치 (`gdi_PitchX/Y/Z`, DINT×3, 0.001mm 단위) |
| | DT224~226 | X/Y/Z 방향 (`gi_DirX/Y/Z`, INT×3, +1 정방향 / −1 역방향. Z 는 기본 −1 = 위로 쌓기) |
| | DT227~229 | X/Y/Z 적층 횟수 (`gi_CountX/Y/Z`, INT×3) |
| | DT230 | 적층 순서 (`gi_StackOrder`, 0~5: XYZ/XZY/YXZ/YZX/ZXY/ZYX) |
| **축 파라미터** | DT15000~15049 | 8축 공통 설정 블록 (50 Words) |
| | DT15000 | 축 사용 비트마스크 (bit0~7 = 1~8축) → FB 의 `w_AxisEnable` |
| | DT15001~15008 | 8축 운전 방향 (0=정방향, 1=역방향) |
| | DT15009~15024 | 8축 스트로크 한계 (DINT×8, mm × 1000) |
| | DT15025~15032 | 8축 가감속 시간 (WORD×8) |
| | DT15033 | 축 데이터셋 전송 트리거 (버튼 누름 시 축 비트 ON) |
| | DT15034~15049 | 8축 PPR — 서보 1회전당 지령펄스수 (DINT×8) |
| **포인트 데이터** | DT16000~DT17919 | 포인트당 32 Words × **최대 60 포인트** (`g_Dut_Point[0..59]`) |
| **시퀀스 데이터** | DT20000~ | 슬롯당 1000 Words (100스텝 × 10Words) × 최대 40슬롯 (DT20000~DT59999) |

> 포인트 인덱스 `i` 의 시작 주소 = `DT16000 + i × 32`
> 슬롯 `s` 의 스텝 `k` 시작 주소 = `DT20000 + s × 1000 + k × 10`

#### RTEX 모션 테이블 할당 정책 (64개)

하드웨어 한계로 RTEX 테이블은 64개. 이 중 **파렛타이징 전용 스크래치** 1개를 예약:

| 인덱스 | RTEX 테이블 번호 | 용도 |
|---|---|---|
| 0..59 | 10026~10085 | **일반 포인트 (60개)** — `fb_WriteMotionTable` 이 전체 사이클 완료 시 갱신 |
| 60..62 | 10086~10088 | 예비 (미래 확장용) |
| 63 | **10089** | **파렛타이징 스크래치** (`pack_base` 스텝 실행 시 `new_plc_fb.st` 가 좌표 계산·기록) |

> HMI 의 포인트 추가 제한도 60개. 61개 이상 추가 시 UI 경고 + PLC 전송 시 스킵.

#### 포인트 데이터 레이아웃 (32 Words/포인트)

| 오프셋 | 내용 |
|---|---|
| +0 | 유효 플래그 (0xFF = 사용) |
| +1 | 전체 속도 (%) |
| +2~17 | 8축 좌표 (DINT×8, 0.001mm) |
| +18~25 | 8축 속도 (WORD×8, %) |

#### 시퀀스 스텝 명령 코드 (10 Words/스텝)

스텝 레이아웃: `[iCommand, wOption, P1_L, P1_H, P2_L, P2_H, P3_L, P3_H, P4_L, P4_H]`

| CMD | 타입 | 설명 |
|---|---|---|
| 10 | POS | 포인트 이동 (OPT = 사용축 비트마스크 bit0~7 + **bit8 = pack_base 플래그**, P1 = 포인트 인덱스 0..59) |
| 20 | OUT | 출력/밸브 On/Off (P3>0 → 타이머 기동후출력) |
| 21 | IN | 입력 대기 (P2 = 타임아웃, P3 = 동작, P4 = 알람번호) |
| 30 | TMR | 타이머 대기 또는 신호유지 (0.01초 단위) |
| 40 | JMP | 점프 (OPT=0 무조건, OPT=1 조건부) |
| 50 | CALL | 서브 시퀀스 호출 (OPT=0 동기, OPT=1 병렬) |
| 99 | END | 시퀀스 종료 (최상위 → `b_Step_End` 펄스 + pack_idx 증가 트리거) |

##### wOption 비트 구조 (POS 스텝)

```
bit 0 : 1축 (X)      bit 4 : 5축 (Z2)    bit 8 : pack_base ★
bit 1 : 2축 (Y)      bit 5 : 6축 (θ)     bit 9~15 : 예약
bit 2 : 3축 (Z)      bit 6 : 7축 (R1)
bit 3 : 4축 (Y2)     bit 7 : 8축 (R2)
```

**`pack_base` 비트가 1** 이면 `new_plc_fb.st` state 11 에서:
- `gw_PackEnable <> 0` 이고 `NOT b_NoSubCall` (Monitor 아님) 일 때만 작동
- `g_Dut_Point[P1]` 좌표 + `gi_PackIdx × gdi_Pitch × gi_Dir` 오프셋을 계산
- 결과를 RTEX 테이블 63 (10089) 에 기록 후 그 테이블로 이동
- 조건 미충족 시 일반 POS (`10026 + P1`) 로 이동 = **안전 폴백**

> **주의**: 코멘트 스텝은 PLC 전송 시 제외되므로, PLC 관점의 스텝 번호와 HMI 리스트 행 번호가 다를 수 있습니다. `page_position._highlight_step` 에서 PLC step 인덱스를 UI 행으로 매핑합니다.

#### OUT 스텝 파라미터 상세

| 파라미터 | 내용 |
|---|---|
| OPT | 출력 상태 (1=ON, 0=OFF) |
| P1 | 비트 인덱스 (포트) |
| P2 | 출력 구분 (0=시스템출력, 1=밸브출력, 2=내부비트) |
| P3 | 딜레이 시간 (0=즉시출력, >0=타이머 기동후출력, 0.01초 단위) |

**타이머 기동후출력 동작:**
- P3 > 0 이면 타이머만 기동하고 즉시 다음 스텝으로 진행
- 타이머 만료 시 지정된 출력(P1, P2, OPT)을 실행
- 최대 **5개** 동시 기동 가능 (슬롯 0~4)
- 5개 초과 시 `i_StepAlarmID = 98` 에러로 시퀀스 정지

#### IN 스텝 포트 매핑

| 포트 범위 | 의미 |
|---|---|
| 0~63 | 시스템/밸브 입력 X00~X3F |
| 100~131 | 내부 비트 M00~M31 (DT300~301) |

---

### PLC 펑션블록 (`new_plc_fb.st`) — 3-instance + 내부 콜 스택

시퀀스 실행 FB 는 **3개 인스턴스**로 배선. 동기 CALL 은 FB 내부 콜 스택(4레벨)으로 처리하고, 병렬 CALL 은 워커 2개 중 빈 워커로 외부 기동합니다.

```
FB_Main    (slot 0 고정, 모든 동기 CALL 처리, 내부 스택 최대 4레벨)
   ↓ b_ParallelStart1 / i_ParallelSlot1 (병렬 CALL 워커1)
   ↓ b_ParallelStart2 / i_ParallelSlot2 (병렬 CALL 워커2)
FB_Sub     (병렬 워커1, b_NoSubCall=TRUE)
FB_Worker2 (병렬 워커2, b_NoSubCall=TRUE)
```

#### VAR_INPUT (주요)

| 이름 | 용도 |
|---|---|
| `i_SlotNo` | 시작 슬롯 (Main=0) |
| `b_Run` | 외부 자동운전 명령 |
| `b_Reset` | **운전정지 상승펄스** — 스택/타이머/SystemOutput/내부비트 초기화 (에러/Valve 유지) |
| `b_AlarmReset` | **알람 리셋 상승펄스 (DT212)** — UserAlarm/StepAlarm 모두 클리어 + state 900 트랩 탈출 |
| `b_NoSubCall` | TRUE면 이 인스턴스는 CALL 불가 (병렬 워커 용) |
| `t_WaitTime` | state 21 BUSY 감지 타임아웃 (PROGRAM에서 T#500MS 이상 배선 필수) |
| `w_AxisEnable` | DT15000 축 사용 비트마스크 — POS 스텝 자동 마스킹 (3축/5축 공용 레시피 지원) |

#### VAR_IN_OUT (공유 변수, 모든 시퀀스 FB 같은 전역변수 배선)

| 이름 | 매핑 | 용도 |
|---|---|---|
| `i_ControlCmd` | DT200 | 운전 명령 |
| `i_CheckRunState` | — | 확인운전 상태 |
| `w_system_Output` | DT203 | 시스템 출력 (b_Reset 시 초기화) |
| `w_Valve_Output` | DT204 | 밸브 출력 (b_Reset 시 유지 — 척/진공 보호) |
| `w_internal_Bit0` | DT300 | 내부비트 M00~M15 (b_Reset 시 초기화) |
| `w_internal_Bit1` | DT301 | 내부비트 M16~M31 (b_Reset 시 초기화) |
| `w_UserAlarm` | DT159 | IN 스텝 P3=1/2 발동 사용자 알람 |
| `b_StepAlarm` | — | 스텝 진행 에러 플래그 (PROGRAM 자동정지 트리거) |
| `i_StepAlarmID` | DT160 | 스텝 진행 에러 코드 |

#### VAR_OUTPUT

- `b_StepDone` — 스텝 완료 펄스
- `b_Step_End` — 최상위 END 도달 펄스 (카운터 증가 등에 사용)
- `b_IsBusy` — FB 실행 중 (i_SeqState <> 0 또는 스택 깊이 > 0)
- `i_CurrentStep`, `i_CurrentSlot`, `i_StackDepth` — HMI 모니터링용
- `i_ParallelSlot1`, `b_ParallelStart1` — Main → 병렬 워커1 기동
- `i_ParallelSlot2`, `b_ParallelStart2` — Main → 병렬 워커2 기동
- `i_ParallelSlot`, `b_ParallelStart` — 워커1 호환용 alias

#### 스텝 알람 ID (`i_StepAlarmID`)

| ID | 의미 |
|---|---|
| 21 | POS 축 이동 확인 실패 (BUSY 상승 미감지) — 타임아웃 후 INP 체크 백업까지 실패한 경우 |
| 22 | **파렛타이징 베이스 인덱스 범위 오류** — `pack_base` 스텝의 `point_index` 가 0~59 를 벗어남 |
| 50 | 병렬 CALL 실패 — 병렬 워커 2개 모두 실행중 |
| 93 | 동기 CALL 스택 오버플로 (4레벨 초과) |
| 94 | CALL 사용 불가 — 이 인스턴스는 `b_NoSubCall=TRUE` (병렬 워커 등) |
| 95 | JMP 타겟 스텝 번호 범위 초과 (0~99) |
| 96 | CALL 슬롯 번호 범위 초과 (0~39) |
| 97 | 실행 슬롯 번호 범위 초과 (0~39) |
| 98 | OUT 지연 타이머 슬롯 없음 (5개 모두 사용중) |
| 99 | 알 수 없는 커맨드 |

#### 리셋 경로 분리

| 경로 | 트리거 | 초기화 대상 | 보존 대상 |
|---|---|---|---|
| `b_Reset` | 자동정지 DF 펄스 | 콜 스택, 시퀀스 상태, 타이머, SystemOutput, 내부비트 | **b_StepAlarm/i_StepAlarmID/w_UserAlarm (알람 유지), Valve_Output (물림 상태)** |
| `b_AlarmReset` | DT212 상승펄스 | b_StepAlarm, i_StepAlarmID, w_UserAlarm, state 900 | — |

이 분리 덕분에 에러 발생 시 **정지 → 알람 표시 → 작업자 확인 후 리셋** 흐름이 가능하며, 공작물을 물고 있는 밸브는 정지로 자동 해제되지 않습니다.

#### POS 스텝 상세 (state 11~30)

1. **state 11**: `w_EffOpt := w_StepOpt AND w_AxisEnable` 로 미연결 축 마스킹 → F151_WRT 로 활성 축에만 테이블 번호 쓰기
2. **state 12**: RTEX 전파 대기 (50ms 고정)
3. **state 20**: 활성 축 기동 신호 ON
4. **state 21**: BUSY 상승 래치 (어느 축이든 BUSY=TRUE 감지하면 통과). `t_WaitTime` 내 BUSY 미감지 시 **INP 백업 체크** — 모든 활성 축 INP=TRUE 면 "이미 제자리" 로 간주해 정상 통과, 아니면 에러 21
5. **state 30**: 모든 활성 축 BUSY=FALSE 대기 → state 99 (다음 스텝)

---

### 파렛타이징 (Palletizing)

베이스 포인트에서 X/Y/Z 오프셋을 자동으로 더해 팔레트 적재 위치로 이동시키는 기능. 로직은 **PLC (new_plc_fb.st) 안에 통합** 되어 있으며, HMI 는 설정 UI + pack_idx 관리만 담당.

#### 시퀀스 스텝에서 pack_base 지정

시퀀스 편집기의 POS 스텝 편집 패널에 **"파렛타이징 베이스 (X/Y/Z 스택 가감산)"** 체크박스. 체크된 스텝의 `wOption` bit 8 이 켜져 PLC 로 전달됨.

- 같은 포인트를 **여러 스텝에서 다르게** 쓸 수 있음 — 어떤 스텝은 pack_base, 어떤 스텝은 일반 POS
- `pack_base` 플래그는 **스텝 단위** (포인트 단위가 아님) → JMP 분기로 패킹/비패킹 경로 분리 가능

#### 좌표 계산 (state 11)

```
target_X = g_Dut_Point[i].diPosX + (gi_PackIdxX × gdi_PitchX × gi_DirX)
target_Y = g_Dut_Point[i].diPosY + (gi_PackIdxY × gdi_PitchY × gi_DirY)
target_Z = g_Dut_Point[i].diPosZ + (gi_PackIdxZ × gdi_PitchZ × gi_DirZ)
(Y2, Z2 는 원본 그대로)
```

계산된 좌표는 **RTEX 테이블 63(10089)** 에 기록되고 그 테이블로 이동. **원본 포인트 데이터는 절대 변경되지 않음** → HMI 의 기억 좌표 유지.

#### pack_idx 증가 로직 (state 10 CMD=99)

최상위 END 도달 시 (사이클 완료), `gi_StackOrder` (0~5) 에 따라 6 케이스 오도미터 방식으로 `gi_PackIdxX/Y/Z` 증가:

| stack_order | 증가 순서 | 예 (X=3,Y=2,Z=2) |
|---|---|---|
| 0 | X → Y → Z | (0,0,0)→(1,0,0)→(2,0,0)→(0,1,0)→... |
| 1 | X → Z → Y | X 내부, Z 중간, Y 외부 |
| 2 | Y → X → Z | Y 내부 |
| 3 | Y → Z → X | |
| 4 | Z → X → Y | 높이부터 |
| 5 | Z → Y → X | 기둥 먼저 |

`gw_PackEnable=0` 이거나 `b_NoSubCall=TRUE` (Monitor) 또는 `gi_Count*` 중 하나가 0 이면 증가 안 함.

#### HMI 측 기능 (`page_packing.py`)

- **X 축 패널 상단 "● 패킹 사용" 토글** — DT217 을 ON/OFF
- 축별 **현재위치(No.)·설정횟수·설정피치·방향** 편집 (Z 는 기본 −방향 = 위로 쌓기)
- "X→Y→Z" 토글 버튼 — 6 순서 순환
- 왼쪽 **시뮬레이션 뷰** (실시간 미리보기, 300ms 주기 애니메이션)
- 현재위치 버튼 클릭 → 사용자 임의 인덱스 설정 (DT161~163 덮어쓰기)
- 설정은 **레시피 JSON** 에 `packing_config` 키로 저장

#### PLC 연결 시 전체 재전송

HMI 가 PLC 에 새로 연결되거나 레시피가 교체될 때 **백그라운드 스레드** 로:
1. 모드/전체속도/패킹설정 (즉시)
2. 포인트 테이블 60개 (1,920 Words)
3. 시퀀스 40 슬롯 (40,000 Words)

모두 재송신 → PLC 휘발성 메모리여도 항상 최신 상태. UI 블로킹 없음.

#### commit pattern (packing_config 전송 순서)

`plc_client.send_packing_config()` 는 중간 통신 끊김 시 부분 활성화 상태를 방지:
1. DT217 = 0 (먼저 비활성화)
2. DT218~230 데이터 쓰기
3. DT217 = 1 (활성화)

→ 중간에 끊겨도 PLC 는 "비활성" 상태라 카운터 증가 안 함. 안전.

---

### 알람 & 조작 이력

| 유형 | 파일 | 보존 | 위치 |
|---|---|---|---|
| 알람 발생 이력 | `alarm_history.json` | 30일 (하드캡 5000건) | `utils/alarm_history.py` |
| 조작 이력 | `op_history.json` | 7일 (하드캡 10000건) | `utils/op_history.py` |

**TopBar 의 `알람: 없음` 을 클릭** 하면 탭 전환 팝업 (`AlarmHistoryOverlay`) 이 열려 양쪽을 조회할 수 있습니다.

#### 알람 카테고리 (`category` 필드)

| 카테고리 | 발생 시점 |
|---|---|
| `ESTOP` | DT142 bit8 또는 GPIO E-STOP 활성화 |
| `AXIS` | 축 서보 알람 (DT142 bit0~7) |
| `STEP` | `i_StepAlarmID` ≠ 0 |
| `USER` | IN 스텝 P3=1/2 에서 발동한 사용자 정의 알람 |
| `COMM` | PLC TCP 통신 끊김 |

#### 조작 카테고리

| 카테고리 | 예시 메시지 |
|---|---|
| `RUN` | 자동 운전 시작 / 확인 운전 시작 / 정지 버튼 |
| `VALVE` | 흡착 1 ON / (JOG) 척 1 OFF / 포스쳐 반전 모멘터리 ON |
| `POS` | M0665 X축 기억위치 변경 → 150.000 mm / (자동중) 미세조정 +0.1 |
| `SPEED` | 전체속도 8 → 10 / M0665 Y축 속도 80 → 100 % |
| `TIMER` | 타이머 'CycleStart' 1.00s → 1.50s |
| `MODE` | 척1 배타 ON |
| `RECIPE` | 레시피 로드: M0665 |
| `ALARM_RESET` | 알람 리셋 버튼 |

자동 정리는 `load_history()` / `record()` 호출마다 **시간 기반 + 하드캡 이중 필터**. 사용자 개입 없이 파일 크기가 안전 범위로 유지됩니다.

---

### 레시피 파일 형식 (`recipes/*.json`)

```json
{
    "version": 1.5,
    "saved_at": "2026-04-23 13:45:00",
    "sequence": {
        "Main": [
            {"type": "POS", "name": "이동_1", "point_name": "Home",
             "active_axes": [true,true,true,false,false,false,false,false]},
            {"type": "POS", "name": "제품개방", "point_name": "제품개방위치",
             "active_axes": [true,true,true,false,false,false,false,false],
             "pack_base": true}
        ],
        "Sub1": [...]
    },
    "position_points": {
        "Home":    {"coords": [0,0,0,0,0,0,0,0], "speeds": [100]*8, "visible_mode": []},
        "제품개방위치": {"coords": [100.5, 200.0, 150.0, ...], "speeds": [...]}
    },
    "timer_library": {"CycleStart": 1.0, "취출전진대기": 0.5},
    "mode": [false, true, false, ...],
    "view_order": ["Home", "제품개방위치", ...],
    "speed_level": 10,
    "packing_config": {
        "enabled": true,
        "x_count": 3, "x_pitch": 50.0, "x_dir": 1,
        "y_count": 2, "y_pitch": 40.0, "y_dir": 1,
        "z_count": 2, "z_pitch": 10.0, "z_dir": -1,
        "stack_order": 0
    },
    "user_modes": {...}
}
```

앱 시작 시 `settings.json` 의 `last_recipe` 값으로 자동 로드되며, `page_data` 에서 선택 로드 시 `sig_file_loaded` 시그널이 발생해 각 페이지 UI/PLC 가 동기화됩니다.

---

### settings.json 주요 구조

```json
{
    "plc_ip": "192.168.0.60",
    "plc_port": "60001",
    "last_recipe": "M0665",

    "axis_uses":    [true, true, true, false, false, false, false, false],
    "axis_strokes": [500.0, 400.0, 300.0, 0, 0, 0, 0, 0],

    "valve_config": [
        {"index": 0, "name": "척 1", "mode": "toggle",    "enabled": true, "jog_valve": true},
        {"index": 8, "name": "포스쳐 반전", "mode": "momentary", "enabled": true}
    ],

    "io_names": {
        "inputs":  ["X00 비상정지", "X01", ...],
        "outputs": ["Y00", ..., "Y0D 서보온", ...]
    },

    "sequence_alarms": {
        "1": "입력 대기 타임아웃",
        "2": "도어 열림"
    },

    "internal_bit_names": {
        "M00": "감지비트",
        "M05": "초기화완료"
    },

    "point_visibility": {"Home": []}
}
```

---

## 주요 기능

### 자동 운전 페이지 (`page_auto`)

- AUTO / CHECK / STOP 버튼
- **전체속도 (1~10 단계)**: 계단형 그래프 UI, `±1 ±0.1` 대신 +/- 버튼. 값은 DT216으로 전송되고 레시피 JSON 에 저장 (`speed_level`)
- IO 패널 (X/Y 실시간)
- 축 위치 패널
- 생산 정보 (취출횟수, 예약알람, 성형시간, 취출시간)

### 위치설정 페이지 (`page_position`)

- 포인트 선택 (콤보 or 네임카드 오버레이)
- 축별 [축 / 현재위치 / 기억위치 / 속도%] 그리드
- **기억위치 스트로크 한계 검증**: `axis_strokes` 참조, 벗어나면 팝업 후 입력 거부
- **자동/확인운전 중 기억위치 수정**: 값 셀 클릭 시 키패드 대신 **미세조정 오버레이** (`-1 / -0.1 / +0.1 / +1` 버튼) 표시, 즉시 PLC 반영
- 동작순서 미리보기 — 스텝 타입별 파라미터 요약 표시 (예: `출력제어_1 (Y24: 흡착 1 ON)`, `타이머_1 (취출전진대기)`, `JMP (점프할 스텝명)`)
- 티치 버튼 — 현재 축 위치를 기억위치로 기록

### 수동 운전 페이지 & 위치 설정 우측 밸브 패널

- `valve_tile.ValvePanel` 공용 컴포넌트
- **출력 상태 실시간 동기화**: DT120/DT121 기반으로 토글 버튼 상태가 실제 Y 출력과 항상 일치
- **자동/확인운전 중 조작 차단**: 반투명 오버레이 + "자동 중에는 사용할 수 없습니다" 안내
- Toggle / Momentary 모드 지원 (`settings.json` → `valve_config.mode`)

### 시퀀스 편집기 (`sequence_editor_dialog`)

- 시퀀스 카드 목록 — **단순 클릭 선택** (길게 눌러 이름 변경 제거, 스크롤 중 오발동 방지)
- 시퀀스 네비게이션 바: `[이름변경] [+] [삭제]` (Main/Monitor 는 이름변경/삭제 비활성)
- **이름 변경 시 모든 CALL 스텝의 `target_seq` 자동 갱신** (끊김 없음)
- 스텝 라벨에 주요 파라미터 표시:
  - POS: `위치이동_1 (원점)`
  - OUT/IN: `출력제어_1 (Y24: 흡착 1 ON)`
  - JMP: `점프_1 (출력제어_1)`
  - TMR: `타이머_1 (취출전진대기)`
  - CALL: `호출_1 (취출동작)`
  - COMMENT: `// 텍스트` (노란색)
- **내부비트 선택 시 ✎ 아이콘으로 이름 지정** — `settings.json` `internal_bit_names` 에 저장되어 `M00 \n 감지비트` 두 줄로 표시
- **POS 스텝 편집 패널에 "파렛타이징 베이스 (X/Y/Z 스택 가감산)" 체크박스** — 체크 시 step JSON 에 `"pack_base": true` 저장, PLC 전송 시 wOption bit 8 로 인코딩
- **포인트 이름 변경 시** 모든 스텝의 `point_name` + `name` 필드 동기 갱신 → 시퀀스 재전송 시 인덱스 자동 재계산 (`sorted()` 기반)
- **포인트 개수 60개 제한 가드** — 61번째 추가 시도 시 경고 팝업

### 타이머 페이지 (`page_timer`)

- 타이머 카드 그리드, 클릭 시 시간 편집
- 현재 실행 중인 TMR 카드 **초록색 점멸 하이라이트** (최소 500ms 유지 + 큐잉 방식으로 연속 타이머도 놓치지 않음)
- 순서 변경 버튼은 **우측 하단**에 배치 (카드 영역을 최대한 위로 확보)

### 스크린샷 (사용설명서 캡처용)

- **F12** 키 또는 화면 **우상단 100×100 영역 3초 롱프레스** → `~/screenshots/pendant_YYYYMMDD_HHMMSS.png` 저장 + 하단 토스트 알림
- 저장 함수는 `QWidget.grab()` 기반이라 weston kiosk 환경에서도 풀스크린 캡처 가능
- 원격 SSH 로 가져오려면: `scp yjchoi@192.168.1.190:/home/yjchoi/screenshots/* .`

### UI 터치 최적화 (2026-04)

- **TouchComboBox**: 드롭다운이 press 가 아닌 **release 에서 열림** — 손가락이 화면에서 떨어진 뒤 팝업이 나타나므로 터치 위치에 hover 하이라이트가 잘못 걸리던 문제 해결
- **ValvePanel 자동 중 잠금 오버레이**: 메시지를 2줄(`자동 중에는\n사용할 수 없습니다`)로 word-wrap + 18px 로 축소 → 좁은 위치설정 페이지에서도 잘리지 않음
- **패킹 페이지**: `● 패킹 사용/미사용` 토글을 X 패널 프레임 밖(위)으로 분리. Y/Z 도 동일 구조(상단 68px 투명 영역 + 프레임) 로 통일해 타이틀 정렬 유지. 시뮬레이션 타이머 300→500ms 로 완화, HEAD 타일 색상 시안 → 따뜻한 베이지(`#E8D5A9`), 축 타이틀은 모두 흰색
- **위치설정 페이지**: 자동/확인운전 중 `현재 위치 기억 (TEACH)` 버튼 **비활성 + 흑백 처리** (`QGraphicsColorizeEffect`). 시퀀스 드롭다운 리스트는 글씨·항목 높이 확대(20px / 42px) + hover 하이라이트 제거해 "선택된 항목만" 파란색으로 표시
- **순서 변경 다이얼로그** (`PositionOrderDialog`): 리스트에 `QScroller` 제스처 추가 — 드래그로 부드러운 터치 스크롤

### TopBar

- 통신: `통신: 정상 / 오류`
- 모드: `모드: 자동운전 / 확인운전 / 정지`
- 알람: `알람: 없음` (클릭 → 이력 팝업) / `[!] 알람 (N축)` / `[!] 비상정지`
- 데이터: 현재 레시피 이름 (하단 메뉴의 "데이터" 탭에서 변경)
- JOG 버튼 (정지 상태에서만 활성)

---

## PLC 펑션블록 와이어링 (PROGRAM 예시)

```st
(* 전역 변수 *)
VAR_GLOBAL
    g_UserAlarm    : WORD;  (* DT159 매핑 *)
    g_StepAlarm    : BOOL;
    g_StepAlarmID  : INT;   (* DT160 매핑 *)
END_VAR

(* FB_Main *)
FB_Main.i_SlotNo       := 0;
FB_Main.b_NoSubCall    := FALSE;
FB_Main.b_Run          := <외부 운전 명령>;
FB_Main.b_Reset        := b_AutoStopRising;    (* 자동정지 DF 펄스 *)
FB_Main.b_AlarmReset   := b_DT212_Rising;      (* DT212 상승펄스 *)
FB_Main.t_WaitTime     := T#500MS;
FB_Main.w_AxisEnable   := DT15000;
FB_Main.i_ControlCmd   := DT200;
FB_Main.w_UserAlarm    := g_UserAlarm;
FB_Main.b_StepAlarm    := g_StepAlarm;
FB_Main.i_StepAlarmID  := g_StepAlarmID;
(* ... 서보/입력/모드 변수 연결 ... *)

FB_Main.b_ParallelBusy1 := FB_Sub.b_IsBusy;
FB_Main.b_ParallelBusy2 := FB_Worker2.b_IsBusy;

(* FB_Sub: 병렬 워커1 *)
FB_Sub.i_SlotNo     := FB_Main.i_ParallelSlot1;
FB_Sub.b_Run        := FB_Main.b_ParallelStart1;
FB_Sub.b_NoSubCall  := TRUE;
FB_Sub.b_Reset      := b_AutoStopRising;
FB_Sub.b_AlarmReset := b_DT212_Rising;
FB_Sub.t_WaitTime   := T#500MS;
FB_Sub.w_AxisEnable := DT15000;
FB_Sub.i_ControlCmd := DT200;
FB_Sub.w_UserAlarm  := g_UserAlarm;
FB_Sub.b_StepAlarm  := g_StepAlarm;
FB_Sub.i_StepAlarmID:= g_StepAlarmID;

(* FB_Worker2: 병렬 워커2 *)
FB_Worker2.i_SlotNo     := FB_Main.i_ParallelSlot2;
FB_Worker2.b_Run        := FB_Main.b_ParallelStart2;
FB_Worker2.b_NoSubCall  := TRUE;
FB_Worker2.b_Reset      := b_AutoStopRising;
FB_Worker2.b_AlarmReset := b_DT212_Rising;
FB_Worker2.t_WaitTime   := T#500MS;
FB_Worker2.w_AxisEnable := DT15000;
FB_Worker2.i_ControlCmd := DT200;
FB_Worker2.w_UserAlarm  := g_UserAlarm;
FB_Worker2.b_StepAlarm  := g_StepAlarm;
FB_Worker2.i_StepAlarmID:= g_StepAlarmID;
(* 동일한 I/O 변수 공유 *)

(* HMI 모니터링 *)
DT131 := FB_Main.i_CurrentStep;
DT132 := FB_Main.i_CurrentSlot;
DT133 := FB_Main.i_StackDepth;
DT134 := FB_Sub.i_CurrentSlot;
DT135 := FB_Sub.i_CurrentStep;
DT126 := FB_Worker2.i_CurrentSlot;
DT127 := FB_Worker2.i_CurrentStep;
DT160 := INT_TO_WORD(g_StepAlarmID);

(* 자동정지 트리거 - 에러 발생 시 *)
IF g_StepAlarm AND NOT g_StepAlarmPrev THEN
    DT200 := 0;   (* i_ControlCmd := 0 → 자동정지 DF → b_Reset *)
END_IF;
g_StepAlarmPrev := g_StepAlarm;
```

---

## Raspberry Pi OS Lite 초기 세팅

```bash
git clone git@github.com:GT-Yjchoi/Universal-Robot-Pendant.git
cd Universal-Robot-Pendant
sudo apt update
sudo apt install -y python3-venv python3-lgpio weston libqt6waylandclient6
python3 -m venv ~/pyside-env
~/pyside-env/bin/pip install --upgrade pip PySide6
sudo install -m 0644 pendant-rpi-lite.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now pendant-rpi-lite.service
```

서비스 파일의 `User`, `Group`, 홈 경로와 UID(기본 1000)는 실제 설치 계정에 맞춰야 한다.
DSI 커넥터 이름과 회전 방향은 `weston-rpi.ini`에서 조정한다. GPIO 비상정지는 기본적으로
비활성화되어 있으며, 실제 line 번호와 배선을 확인한 뒤 환경변수로 활성화한다.

SSH 키 미등록 시:
```bash
ssh-keygen -t ed25519 -C "<email>"
cat ~/.ssh/id_ed25519.pub   # GitHub → Settings → SSH keys 에 등록
```

## 서비스 관리

```bash
sudo systemctl start pendant-rpi-lite       # 시작
sudo systemctl stop pendant-rpi-lite        # 정지
sudo systemctl restart pendant-rpi-lite     # 재시작 (코드 변경 후)
journalctl -u pendant-rpi-lite -f           # 실시간 로그
```

---

## 빌드 방법 (PyInstaller)

```bash
cd /home/yjchoi/Universal-Robot-Pendant
source /home/yjchoi/pyside-env/bin/activate
pyinstaller --clean -y main.spec
```

> `main.spec` 의 `datas` 에 `assets/fonts` 가 포함되어 있어 번들 폰트가 실행파일에 포함됩니다.

---

## 개발 실행 (서비스 안 거치고 포그라운드 실행)

```bash
sudo systemctl stop pendant-rpi-lite   # tty1 점유 해제
cd /home/yjchoi/Universal-Robot-Pendant
./launch-rpi-lite.sh
```

> `launch-rpi-lite.sh`는 Weston kiosk를 띄운 뒤 같은 Wayland 소켓에서 `main.py`를 실행한다. 보통은 `journalctl -u pendant-rpi-lite -f`와 `/tmp/pendant-weston.log`를 보면서 작업하는 것이 편하다.

---

## 번들 폰트 (한글 렌더)

시스템에 한글 폰트를 설치하지 않아도 되도록 프로젝트에 Pretendard(OFL) 를 포함.

- 위치: `assets/fonts/Pretendard-Regular.ttf`, `assets/fonts/Pretendard-Bold.ttf` (총 ~5MB)
- 로드: `main.py` 의 `_load_bundled_fonts()` 가 `QFontDatabase.addApplicationFont()` 로 등록 후 앱 기본 폰트로 설정
- 스타일시트: `ui/theme.py` 의 `QWidget { font-family: "Pretendard", "Segoe UI"; }` 로 우선순위 지정

---

## 문제 해결

### HDMI 연결이 끊기면 앱이 종료됨
`linuxfb` 플랫폼 플러그인은 부팅 시 `/dev/fb0` 를 잡은 상태로 고정.
HDMI 핫플러그로 `vc4-kms-v3d` 드라이버가 프레임버퍼를 재구성하면 Qt 가 따라가지 못하고 크래시.
재연결 후에는 프레임버퍼 상태가 달라져 터치 좌표 매핑이 어긋나거나 evdev 가 꼬인다.

**증상 연쇄**:
1. HDMI 끊김 → 앱 크래시 종료
2. 재연결 후 tty1 은 여전히 **텍스트 모드** 상태로 남아있어 커서가 FB 에 찍힘
3. 앱을 다시 실행해도 Qt 가 `KDSETMODE KD_GRAPHICS` ioctl 로 tty 모드 전환에 실패 → 커서와 앱이 겹쳐 보임
4. USB/evdev 레이어도 half-init 상태라 Qt 가 터치 디바이스 exclusive grab 실패 → 터치 안 됨

**복구 방법**:
- 1차 (거의 항상 필요): **재부팅**. `sudo dd if=/dev/zero of=/dev/fb0`, `chvt 2 && chvt 1`, `systemctl restart getty@tty1` 등은 대부분 효과 없음.
- 근본 예방: `/boot/firmware/cmdline.txt` 끝에 `video=HDMI-A-1:1024x600M@60D` 추가 — `D` 플래그가 HDMI 핫플러그 무시하고 출력 강제 유지. 그리고 systemd 로 앱 자동 재시작 서비스 등록.

### 앱 좌상단에 tty1 커서가 깜빡이거나 콘솔 텍스트가 비침
linuxfb 는 `/dev/fb0` 를 직접 그리지만 커널 프레임버퍼 콘솔(`fbcon`)도 같은 FB 를 공유하므로
기본 상태에선 tty1 의 커서·텍스트가 앱 뒤로 겹쳐 보인다.

**해결**: `/boot/firmware/cmdline.txt` 에 아래 플래그 추가 후 재부팅.
```
vt.global_cursor_default=0 consoleblank=0 fbcon=map:2 logo.nologo
```
- `vt.global_cursor_default=0` — 콘솔 커서 깜빡임 제거
- `consoleblank=0` — 화면 자동 꺼짐 방지
- `fbcon=map:2` — fbcon 을 존재하지 않는 FB 로 돌려 FB0 점유 해제 (핵심)
- `logo.nologo` — 부팅 로고 제거

> 재부팅 없이 임시로만 끄려면: `sudo sh -c 'echo 0 > /sys/class/vtconsole/vtcon1/bind'`

### 앱 종료 & tty 복귀
- tty1 에서 실행 중이면 해당 터미널에서 `Ctrl+C` — Qt 앱이 SIGINT 받고 종료, 셸 프롬프트 복귀.
- 화면에 잔상이 남으면 `sudo dd if=/dev/zero of=/dev/fb0` 또는 `chvt 2 && chvt 1`.
- 다른 tty 로 전환: `Ctrl+Alt+F2` (돌아올 때 `Ctrl+Alt+F1`). SSH 로 접속해 `pkill -f "python main.py"` 로 강제 종료도 가능.

### 0초 타이머가 HMI 에 표시 안 됨
HMI 폴링 주기(50ms)가 PLC 스캔(1~5ms)보다 느려 0초 TMR 스텝이 `i_CurrentStep` 에 1스캔만 나타나 HMI 가 놓칠 수 있습니다.
현재는 **관측된 경우**에만 최소 500ms 하이라이트 + 큐잉으로 보정합니다. 완벽한 감지가 필요하면 PLC 에 TMR 진입 이벤트 래치 + 핸드셰이크 레지스터를 추가해야 합니다 (미구현).

### 시퀀스 편집기 — 클릭 안 한 스텝이 옛 필드로 PLC 에 전송됨 (해결)
HMI 업데이트로 스텝 데이터 스키마가 바뀐 뒤 (예: POS `axes` → `active_axes`, IN `in_type` 신설, TMR/OUT 의 `timer_ref`/`delay_timer_ref` 라이브러리 동기화) 마이그레이션 변환이 `_load_data_to_ui` 안에서만 수행됐습니다. 즉, 사용자가 편집기에서 **그 스텝을 한 번이라도 클릭해야** 새 필드가 채워졌고, 미클릭 스텝은 옛 필드 그대로 PLC 에 송신됐습니다.

- 증상: 편집기 열어 저장·닫기로 송신해도 PLC 가 의도와 다르게 동작 (예: POS 가 모든 축을 움직이거나, IN 이 잘못된 영역을 감시). 해당 스텝을 클릭한 뒤 다시 저장·닫기하면 정상.
- 원인: PLC 인코더(`utils/plc_client.py`)가 `active_axes` 가 없으면 `[True]*8` 로 폴백해 전 축 이동, `in_type` 누락 시 영역 추론 불일치.
- 수정: `ui/dialogs/sequence_editor_dialog.py` 에 `normalize_step` / `normalize_all_sequences` 모듈 함수 추가. **송신 직전** 클릭 여부와 무관하게 전 스텝을 in-place 정규화. 편집기의 "저장 후 닫기" (`_send_all_sequences_to_plc`) 와 PLC 재연결 시 자동 재전송 (`main_window._send_full_recipe_to_plc`) 양쪽에서 호출.

### 시퀀스 편집기 — JMP 스텝 라벨의 `(타겟이름)` 이 실제 설정과 어긋남 (해결)
JMP 스텝의 `target_idx` 는 콤보 인덱스 = **원본 리스트 인덱스 (COMMENT 포함)** 로 저장됩니다 (`_on_jmp_value_changed`, `_fix_jmp_targets`, `plc_idx_map[orig_idx]→plc_step` 모두 동일 규약). 그런데 스텝 목록 라벨의 `(target_name)` 표시 함수 `_get_jmp_target_name` 만 `target_idx` 를 **비-COMMENT 카운트** 로 잘못 해석해 COMMENT 가 끼어 있으면 다른 스텝 이름(또는 `스텝N` 플레이스홀더) 이 표시됐습니다.

- 영향 범위: **표시값만** 어긋남. 콤보 선택 / 저장 / PLC 전송 / `_fix_jmp_targets` 는 처음부터 일관된 orig-idx 규약이라 실제 점프 동작은 정상이었음.
- 마이그레이션: 저장된 데이터는 그대로 유효 — 별도 변환 불필요.
- 수정: `_get_jmp_target_name` 이 `current_list[target_idx]` 를 직접 인덱싱하도록 변경 (COMMENT 도 `// text` 로 표시).

---

## 네트워크 탭 (설정 > 네트워크)

`ui/pages/page_settings.py` 의 마지막 탭. NetworkManager(`nmcli`) 래퍼는 `utils/wifi_manager.py`.

- **무선**: 현재 SSID/IP/신호 표시, 스캔/암호 입력(터치 키보드)/연결 해제. 탭이 보이는 동안 15초마다 자동 스캔.
- **유선**: 인터페이스/상태/IP/게이트웨이/방식(DHCP/고정) 표시, DHCP 적용 · 고정 IP 설정(IP/prefix/GW/DNS).
- WiFi 스캔은 polkit 인증이 필요할 수 있으므로 배포 시 실행 사용자의 `netdev` 권한을 확인한다.

> 핸드폰 핫스팟이 안 잡힐 때: iOS 는 핫스팟 설정 화면을 열어둔 상태에서만 5GHz 비콘을 활발히 송출. 2.4GHz 로 설정하면 안정적.

---

## 자주 수정하는 부분

| 목적 | 파일 |
|---|---|
| PLC IP/Port 기본값 | `ui/main_window.py` → `_try_auto_connect` |
| 사용자 알람 메시지 (IN 스텝) | 설정 페이지 > 알람 탭 (또는 `settings.json` `sequence_alarms`) |
| 밸브 이름·모드·JOG 노출 | 설정 페이지 > 밸브 탭 (또는 `settings.json` `valve_config`) |
| IO 이름 변경 | 설정 페이지 > IO 탭 (또는 `settings.json` `io_names`) |
| 축 설정 (사용여부·스트로크·가감속·PPR) | 설정 페이지 > 축 파라미터 (또는 `settings.json` `axis_uses`·`axis_strokes`) |
| 내부비트 이름 | 시퀀스 편집기 OUT/IN 스텝 → 내부비트 카드 ✎ 아이콘 |
| 모니터링 주기 변경 | `utils/plc_client.py` → `_mon_loop` (`time.sleep`) |
| PLC 주소 상수 | `utils/plc_client.py` → `__init__` 상단 |
| 시퀀스 FB 로직 | `new_plc_fb.st` |
| 페이지 추가 | `ui/pages/` 생성 후 `ui/main_window.py` 에 등록 |
| 네비게이션 버튼 순서 | `ui/main_window.py` → `add_nav(...)` 호출 순서 |
| 이력 보존 기간 | `utils/alarm_history.py` (RETENTION_DAYS=30) / `utils/op_history.py` (=7) |
| 이력 팝업 페이지 크기 | `ui/overlays/alarm_history_overlay.py` → `PAGE_SIZE` (기본 100) |
| 포인트 최대 개수 | `utils/plc_client.py` → `MAX_POINTS` (기본 60) + `fb_WriteMotionTable.st` + `new_plc_fb.st` |
| 파렛타이징 DT 주소 | `utils/plc_client.py` → `ADDR_PACK_IDX` (DT161) / `ADDR_PACK_CFG` (DT217) |
| 파렛타이징 알람 메시지 | `ui/overlays/alarm_overlay.py` → `STEP_ALARM_DESCRIPTIONS[22]` |
| 스타일 변경 | `ui/theme.py` / 각 위젯 setStyleSheet |
