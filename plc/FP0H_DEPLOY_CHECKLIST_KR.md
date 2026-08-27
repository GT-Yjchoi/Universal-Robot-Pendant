# FP0H 팬던트 브리지 적용 체크리스트

대상 PLC는 Panasonic FP0H-C32ET이며, 레시피와 스텝 실행 흐름은 Raspberry Pi가
담당한다. PLC는 물리 I/O, 서보 명령, 인터록, 비상정지 및 통신 Watchdog만 담당한다.

## 1. 먼저 추가할 FB

1. `FB_PendantWatchdog.st`
2. `FB_PendantMailbox.st`

가감속은 메일박스에 연결하지 않는다. 시스템 파라미터 DT15025..DT15032를 기존
MoveAbsolute 블록의 축별 가감속 입력에 직접 연결한다.

## 2. Watchdog 배선

- `FB_PendantWatchdog.w_Heartbeat` → DT200
- `FB_PendantWatchdog.t_Timeout` → `T#1500MS`
- `b_PendantInterlockOK` → 물리 안전조건 AND 서보 인터록 AND
  `FB_PendantWatchdog.b_CommunicationOK`
- `FB_PendantWatchdog.b_WatchdogStop` → 서보 정지 요청에 OR 연결
- `b_PendantInterlockOK` → `FB_PendantMailbox.b_InterlockOK`

물리 비상정지는 반드시 Raspberry Pi, Ethernet 및 PLC 프로그램과 독립적으로
위험 동작을 차단해야 한다.

## 3. 즉시 제어 영역

| 주소 | 연결 |
|---|---|
| DT200 | 통신 하트비트 |
| DT201 | 팬던트 운전상태 |
| DT210..DT213 | Y00/Y10/Y20/Y30 출력 요청 WORD |
| DT220 | 축별 JOG: bit 2n=+, bit 2n+1=- |
| DT221 | JOG 속도 |
| DT222 | 전체 속도 배율 |
| DT223 | 팬던트 축 정지 요청 |

DT223과 Watchdog 정지, 메일박스 `b_StopRequest`를 기존 서보 정지 경로에 OR로
연결한다. DT210..DT213은 인터록을 적용한 후 실제 Y 출력으로 전달한다.

## 4. 명령 요청 메일박스

| 주소 | FB 입력 |
|---|---|
| DT300 | `w_Command` |
| DT301 | `w_Group` |
| DT302 | `w_Index` |
| DT303 | `w_Value` |
| DT304..DT305 | `di_DurationMs` |
| DT306 | `w_AxisMask` |
| DT307 | `w_MotionFlags` |
| DT308..DT323 | `adi_Target[0..7]` |
| DT324..DT331 | `aw_Speed[0..7]` |
| DT332..DT341 | 예약, 항상 0 |
| DT342 | `w_RequestSeq`/Commit |

`aw_OutputRequest[0..3]`은 DT210..DT213에 연결한다. 메일박스 출력 그룹은
0=Y00, 1=Y10, 2=Y20, 3=Y30이다.

## 5. 처리 결과 메일박스

| 주소 | FB 출력 |
|---|---|
| DT400 | `w_AckSeq` |
| DT401 | `w_State` |
| DT402 | `w_Error` |
| DT403 | `w_EchoCommand` |
| DT404 | `w_Detail` |

`w_State`: 0=Idle, 1=Busy, 2=Done, 3=Error.

## 6. PLC 모니터 영역

`DT_ADDRESS_MAP.md`의 DT100..DT167 표를 그대로 사용한다. 특히 다음 주소를
과거 맵과 혼동하지 않는다.

- 축 알람/비상정지: DT116
- 원점완료 비트맵: DT117
- 실제 입력: DT140..DT143
- 실제 출력: DT144..DT147
- 생산/목표/사이클 정보: DT160..DT167

## 7. 무부하 시운전 순서

1. 서보 기동과 실제 출력 전달을 차단한 상태로 PLC 프로그램을 다운로드한다.
2. DT200이 약 500ms마다 변하는지 확인한다.
3. Ethernet을 분리하고 1.5초 안에 Watchdog 정지가 발생하는지 확인한다.
4. 인터록 OFF에서 메일박스 명령이 Error 1로 거절되는지 확인한다.
5. 출력 명령 1과 전체 출력 OFF 명령 3을 무부하로 확인한다.
6. 펄스 명령 2가 PLC 타이머로 정확히 OFF되는지 확인한다.
7. 정지 명령 12와 DT223의 우선정지를 확인한다.
8. 원점복귀 명령 11을 확인한다.
9. 마지막으로 저속·단축 조건에서 절대위치 이동 명령 10을 확인한다.

