# FP0H pendant command mailbox

The Raspberry Pi owns recipe control flow. FP0H executes one idempotent hardware
command at a time. All values are little-endian DT words.

## Request DT300..DT342

| Address | Meaning |
|---|---|
| DT300 | command: 1 output, 2 pulse, 3 all outputs off, 10 absolute move, 11 home, 12 stop, 13 reset |
| DT301 | signal group: 0 system I/O, 1 valve I/O |
| DT302 | signal index 0..15 |
| DT303 | value |
| DT304..305 | pulse duration in ms (DINT) |
| DT306 | axis enable mask |
| DT307 | motion flags: bit0=acknowledge after move acceptance (simultaneous transition) |
| DT308..323 | target positions, 8 signed DINT values in 0.001 mm |
| DT324..331 | axis speeds |
| DT332 | acceleration |
| DT333 | deceleration |
| DT334..341 | reserved; write zero |
| DT342 | request sequence/commit word (1..65535) |

DT342 is written in the same block as the payload but is placed last. The PLC
must ignore a sequence already acknowledged. Retrying a TCP response therefore
cannot execute a motion twice.

## Status DT350..DT354

| Address | Meaning |
|---|---|
| DT350 | acknowledged request sequence |
| DT351 | state: 0 idle, 1 busy, 2 done, 3 error |
| DT352 | error code |
| DT353 | echoed command |
| DT354 | command-specific detail |

## Safety rules

- Emergency stop, servo limits, physical interlocks and output conflicts are
  checked in PLC logic before accepting a command.
- A pulse is timed completely in the PLC. Pi never sends separate ON/OFF TCP
  packets for a precise pulse.
- Loss of the independent heartbeat forces motion stop and the configured safe
  output mask.
- STOP is handled before normal command state processing.
