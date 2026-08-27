# Pendant ↔ FP0H DT address map

This is the canonical map for the pendant-side sequence architecture. Reserved
words must not be read as state or written by the application.

## PLC → pendant: DT100 range

| Address | Meaning |
|---|---|
| DT100..115 | Eight current axis positions (signed DINT, 0.001 mm) |
| DT116 | Axis-alarm/E-stop bitmap (bits 0..7 = axes 1..8, bit 8 = E-stop) |
| DT117 | Eight-axis homing-complete bitmap (bits 0..7 = axes 1..8) |
| DT118..119 | Reserved |
| DT120..121 | Axis 1 error code (DINT) |
| DT122..123 | Axis 2 error code (DINT) |
| DT124..125 | Axis 3 error code (DINT) |
| DT126..127 | Axis 4 error code (DINT) |
| DT128..129 | Axis 5 error code (DINT) |
| DT130..131 | Axis 6 error code (DINT) |
| DT132..133 | Axis 7 error code (DINT) |
| DT134..135 | Axis 8 error code (DINT) |
| DT136..139 | Reserved |
| DT140..143 | Physical inputs X00..X3F, one word per hexadecimal group |
| DT144..147 | Physical outputs Y00..Y3F, one word per hexadecimal group |
| DT148..149 | Reserved |
| DT150 | PLC operation-mode status |
| DT151..159 | Reserved |
| DT160..161 | Production/take-out count (DINT) |
| DT162..163 | Target count (DINT) |
| DT164..165 | Take-out cycle time (DINT, 0.1 s) |
| DT166..167 | Molding cycle time (DINT, 0.1 s) |

DT129 is the high word of the axis 5 error-code DINT. The operation state is
owned by the pendant and written to DT201.

## Pendant → PLC: DT200 range

| Address | Meaning |
|---|---|
| DT200 | Communication heartbeat |
| DT201 | Current operation state owned by the pendant |
| DT202..209 | Reserved |
| DT210..213 | Configured output group requests, one 16-bit word per group slot |
| DT214..219 | Reserved |
| DT220 | Axis JOG command bits (axis n: bit 2n = +, bit 2n+1 = -) |
| DT221 | JOG speed |
| DT222 | Global speed override |
| DT223 | Axis-stop request from the pendant |
| DT224..299 | Reserved |

`DT210.0` is the request for group 1 bit 0. With the default group-1 start
address this is Y00, and its physical feedback is `DT144.0`. Group slots
2..4 use DT211..DT213 regardless of whether their configured PLC labels start
at Y10, Y20, or another 16-point boundary. The PLC program must pack the same
physical groups into the corresponding words. Output feedback slots 2..4 use
DT145..DT147.

Alarm reset, motion, homing and precise output pulses use the request mailbox
at DT300..DT342 and the result mailbox at DT400..DT404 rather than consuming
additional DT200-range words.

Ordinary OUT ON/OFF steps write DT210..DT213 directly and do not wait for
DT400 acknowledgement. Step delays and control flow remain on the pendant.

Acceleration and deceleration are not mailbox fields. The PLC system
parameters at DT15025..DT15032 are wired directly to the MoveAbsolute blocks.

## Motion command mailbox

| Address | Meaning |
|---|---|
| DT300 | Command: 1 output, 2 pulse, 3 all outputs off, 10 absolute move, 11 home, 12 stop, 13 reset |
| DT301 | Configured physical output group slot, 0..3 |
| DT302 | Signal index, 0..15 |
| DT303 | Command value |
| DT304..305 | Pulse duration in ms (DINT) |
| DT306 | Axis-enable bitmap |
| DT307 | Motion flags |
| DT308..323 | Eight target positions (signed DINT, 0.001 mm) |
| DT324..331 | Eight axis speeds |
| DT332..341 | Reserved; the pendant writes zero |
| DT342 | Request sequence and commit word |
| DT343..399 | Reserved |
| DT400 | Acknowledged request sequence |
| DT401 | State: 0 idle, 1 busy, 2 done, 3 error |
| DT402 | Error code |
| DT403 | Echoed command |
| DT404 | Command-specific detail |
| DT405..499 | Reserved |

## Pendant variable export mirror

The pendant remains the sole owner of these values.  The PLC block is a
read-only mirror for other devices; PLC writes must not be fed back into the
pendant variables.

| Address | Meaning |
|---|---|
| DT500 | Export schema version (currently 2) |
| DT501 | Completed snapshot sequence number |
| DT502 | Status: bit0 valid, bit1 running, bit2 paused, bit3 error |
| DT503 | Reserved |
| DT504..511 | Up to 128 published named internal bits |
| DT512..711 | User-assigned published named data values (signed DINT each) |
| DT712..719 | Reserved |

Internal data has no PLC address by default. When `PLC publish` is enabled, the
operator explicitly selects an even DINT start address from DT512, DT514, ...,
DT710. Duplicate assignments are rejected. Renaming does not change the chosen
address. Disabling publication, deleting a published value, or changing its
address clears the old PLC DINT to zero.
Payload words are written first and DT500..DT503 are committed last.

## Axis system parameters

| Address | Meaning |
|---|---|
| DT15000 | Enabled-axis bitmap |
| DT15001..15008 | Eight axis directions |
| DT15009..15024 | Eight stroke limits (signed DINT, 0.001 mm) |
| DT15025..15032 | Eight acceleration/deceleration settings |
| DT15033 | Axis dataset trigger bitmap |
| DT15034..15049 | Eight PPR values (DINT) |

The absolute/incremental encoder classification is stored in the pendant's
`settings.json`; it has no PLC DT allocation.

## Pendant-local addresses

These names are evaluated only by the pendant step executor. They are not PLC
memory and are reset when the pendant application restarts.

| Address | Meaning |
|---|---|
| Named internal bits | Up to 128 BOOL values |
| Named data registers | Up to 100 signed 32-bit values |

Old recipes containing M00..M31 or virtual DT60000..DT60099 fields are
migrated automatically to stable named-variable IDs when loaded. Those legacy
labels are compatibility fields, not PLC memory.

## Legacy PLC storage ranges

The following constants remain in the compatibility library, but the current
pendant-side sequence runtime does not upload recipes or points to these PLC
ranges.

| Address | Legacy meaning | Current state |
|---|---|---|
| DT16000..17919 | Position-point table | Unused; points are stored in pendant recipe files |
| DT20000..59999 | PLC sequence slots | Unused; steps execute on the pendant |
