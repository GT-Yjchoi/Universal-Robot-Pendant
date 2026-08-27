# FP0H pendant command mailbox

The Raspberry Pi owns recipe control flow. FP0H executes one idempotent hardware
command at a time. All values are little-endian DT words.

Bind `aw_OutputRequest[0..3]` to DT210..DT213. The four words represent the
four output-group slots configured on the pendant. The PLC program packs the
selected physical Y group into the matching slot (for example, slot 2 may be
Y10..Y1F or Y20..Y2F).
Physical output feedback is reported separately at DT144..DT147.

Normal OUT ON/OFF steps write the corresponding DT210..DT213 request bit
directly and do not wait for a mailbox acknowledgement. Command 2 is reserved
for a precise PLC-timed pulse. Motion, homing and reset also use the mailbox
because the pendant must receive completion or error status.

## Request DT300..DT342

| Address | Meaning |
|---|---|
| DT300 | command: 1 output, 2 pulse, 3 all outputs off, 10 absolute move, 11 home, 12 stop, 13 reset |
| DT301 | physical output group slot: 0..3 |
| DT302 | signal index 0..15 |
| DT303 | value |
| DT304..305 | pulse duration in ms (DINT) |
| DT306 | axis enable mask |
| DT307 | motion flags: bit0=acknowledge after move acceptance (simultaneous transition) |
| DT308..323 | target positions, 8 signed DINT values in 0.001 mm |
| DT324..331 | axis speeds |
| DT332..341 | reserved; write zero |
| DT342 | request sequence/commit word (1..65535) |

Acceleration and deceleration are deliberately not part of the mailbox. Bind
the PLC system parameters directly to the MoveAbsolute block.

DT342 is written in the same block as the payload but is placed last. The PLC
must ignore a sequence already acknowledged. Retrying a TCP response therefore
cannot execute a motion twice.

## Status DT400..DT404

| Address | Meaning |
|---|---|
| DT400 | acknowledged request sequence |
| DT401 | state: 0 idle, 1 busy, 2 done, 3 error |
| DT402 | error code |
| DT403 | echoed command |
| DT404 | command-specific detail |

DT343..DT399 and DT405..DT499 are reserved for future step-command processing.

## Safety rules

- Emergency stop, servo limits, physical interlocks and output conflicts are
  checked in PLC logic before accepting a command.
- A pulse is timed completely in the PLC. Pi never sends separate ON/OFF TCP
  packets for a precise pulse.
- Loss of the independent heartbeat forces motion stop and the configured safe
  output mask.
- STOP is handled before normal command state processing.

## PLC wiring checklist

1. Map `aw_OutputRequest[0..3]` to DT210..DT213. Apply the machine output
   interlocks before copying these request words to physical Y outputs.
2. Map the request inputs in declaration order to DT300..DT331 and
   `w_RequestSeq` to DT342. DT332..DT341 are always zero.
3. Map `w_AckSeq`, `w_State`, `w_Error`, `w_EchoCommand` and `w_Detail` to
   DT400..DT404.
4. Connect `FB_PendantWatchdog.w_Heartbeat` to DT200. Combine its
   `b_CommunicationOK` with the physical E-stop and machine interlocks for
   `FB_PendantMailbox.b_InterlockOK`.
5. OR `FB_PendantWatchdog.b_WatchdogStop`, DT223 and
   `FB_PendantMailbox.b_StopRequest` into the normal servo-stop request path.
6. Connect the axis-specific system acceleration/deceleration parameters
   directly to the MoveAbsolute blocks. They are intentionally absent from
   the mailbox.

The software interlock and watchdog are not safety-rated. The physical
emergency-stop circuit must stop hazardous motion independently of Raspberry
Pi, Ethernet and PLC application code.

## Error codes

| Code | Meaning |
|---:|---|
| 0 | No error |
| 1 | Interlock not satisfied or dropped during processing |
| 2 | Output bit index is outside 0..15 |
| 3 | Output bank is outside 0..3 |
| 4 | Invalid pulse index or duration |
| 5 | Unsupported command |
| Other | Motion block error code passed through by the PLC |
