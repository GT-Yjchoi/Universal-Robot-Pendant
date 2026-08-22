(*
  Panasonic FP0H - single pendant hardware command executor.
  Recipe steps, TMR, JMP, CALL, DAT and internal bits remain on Raspberry Pi.

  Bind request/status variables to DT300..DT354 in FPWIN global variables.
  Bind w_SystemOutput/w_ValveOutput to the application's physical output words.
  The existing servo driver consumes the motion request interface below.
*)
FUNCTION_BLOCK FB_PendantMailbox
VAR_INPUT
    w_RequestSeq       : WORD;
    w_Command          : WORD;
    w_Group            : WORD;
    w_Index            : WORD;
    w_Value            : WORD;
    di_DurationMs      : DINT;
    w_AxisMask         : WORD;
    w_MotionFlags      : WORD;
    adi_Target         : ARRAY[0..7] OF DINT;
    aw_Speed           : ARRAY[0..7] OF WORD;
    w_Acceleration     : WORD;
    w_Deceleration     : WORD;
    b_InterlockOK      : BOOL;
    b_MotionDone       : BOOL;
    b_MotionError      : BOOL;
    w_MotionErrorCode  : WORD;
END_VAR
VAR_IN_OUT
    w_SystemOutput     : WORD;
    w_ValveOutput      : WORD;
END_VAR
VAR_OUTPUT
    w_AckSeq           : WORD;
    w_State            : WORD;
    w_Error            : WORD;
    w_EchoCommand      : WORD;
    w_Detail           : WORD;
    b_MoveRequest      : BOOL;
    b_HomeRequest      : BOOL;
    b_StopRequest      : BOOL;
    b_ResetRequest     : BOOL;
    w_MoveAxisMask     : WORD;
    aw_MoveSpeed       : ARRAY[0..7] OF WORD;
    adi_MoveTarget     : ARRAY[0..7] OF DINT;
    w_MoveAcceleration : WORD;
    w_MoveDeceleration : WORD;
END_VAR
VAR
    i                   : INT;
    w_Mask              : WORD;
    w_ActiveCommand     : WORD;
    w_ActiveSeq         : WORD;
    fb_Pulse            : TON;
    b_PulseActive       : BOOL;
    w_PulseGroup        : WORD;
    w_PulseMask         : WORD;
END_VAR

b_MoveRequest := FALSE;
b_HomeRequest := FALSE;
b_StopRequest := FALSE;
b_ResetRequest := FALSE;

(* PLC-timed pulse completion *)
fb_Pulse(IN := b_PulseActive, PT := DINT_TO_TIME(di_DurationMs));
IF b_PulseActive AND fb_Pulse.Q THEN
    IF w_PulseGroup = 0 THEN
        w_SystemOutput := w_SystemOutput AND NOT w_PulseMask;
    ELSE
        w_ValveOutput := w_ValveOutput AND NOT w_PulseMask;
    END_IF;
    b_PulseActive := FALSE;
    w_State := 2;
    w_AckSeq := w_ActiveSeq;
END_IF;

(* STOP bypasses the normal busy state. *)
IF (w_RequestSeq <> w_AckSeq) AND (w_Command = 12) THEN
    b_StopRequest := TRUE;
    b_PulseActive := FALSE;
    w_SystemOutput := 0;
    w_ValveOutput := 0;
    w_EchoCommand := w_Command;
    w_Error := 0;
    w_State := 2;
    w_AckSeq := w_RequestSeq;

ELSIF (w_RequestSeq <> w_AckSeq) AND (w_State <> 1) THEN
    w_ActiveSeq := w_RequestSeq;
    w_ActiveCommand := w_Command;
    w_EchoCommand := w_Command;
    w_Error := 0;
    w_Detail := 0;

    IF NOT b_InterlockOK THEN
        w_Error := 1;
        w_State := 3;
        w_AckSeq := w_RequestSeq;
    ELSE
        CASE w_Command OF
            1: (* output set *)
                IF w_Index > 15 THEN
                    w_Error := 2; w_State := 3;
                ELSE
                    w_Mask := SHL(WORD#1, WORD_TO_INT(w_Index));
                    IF w_Group = 0 THEN
                        IF w_Value <> 0 THEN w_SystemOutput := w_SystemOutput OR w_Mask;
                        ELSE w_SystemOutput := w_SystemOutput AND NOT w_Mask; END_IF;
                    ELSIF w_Group = 1 THEN
                        IF w_Value <> 0 THEN w_ValveOutput := w_ValveOutput OR w_Mask;
                        ELSE w_ValveOutput := w_ValveOutput AND NOT w_Mask; END_IF;
                    ELSE
                        w_Error := 3; w_State := 3;
                    END_IF;
                    IF w_Error = 0 THEN w_State := 2; END_IF;
                END_IF;
                w_AckSeq := w_RequestSeq;

            2: (* PLC-timed positive pulse *)
                IF (w_Index > 15) OR (di_DurationMs <= 0) THEN
                    w_Error := 4; w_State := 3; w_AckSeq := w_RequestSeq;
                ELSE
                    w_PulseMask := SHL(WORD#1, WORD_TO_INT(w_Index));
                    w_PulseGroup := w_Group;
                    IF w_Group = 0 THEN w_SystemOutput := w_SystemOutput OR w_PulseMask;
                    ELSIF w_Group = 1 THEN w_ValveOutput := w_ValveOutput OR w_PulseMask;
                    ELSE w_Error := 3; w_State := 3; w_AckSeq := w_RequestSeq; END_IF;
                    IF w_Error = 0 THEN b_PulseActive := TRUE; w_State := 1; END_IF;
                END_IF;

            3: (* all outputs off *)
                w_SystemOutput := 0; w_ValveOutput := 0;
                b_PulseActive := FALSE; w_State := 2; w_AckSeq := w_RequestSeq;

            10: (* absolute servo move *)
                FOR i := 0 TO 7 DO
                    adi_MoveTarget[i] := adi_Target[i];
                    aw_MoveSpeed[i] := aw_Speed[i];
                END_FOR;
                w_MoveAxisMask := w_AxisMask;
                w_MoveAcceleration := w_Acceleration;
                w_MoveDeceleration := w_Deceleration;
                b_MoveRequest := TRUE;
                (* motion flag bit0: acknowledge after command acceptance so the
                   pendant can execute the next step while motion continues. *)
                IF (w_MotionFlags AND WORD#1) <> 0 THEN
                    w_State := 2;
                    w_AckSeq := w_RequestSeq;
                ELSE
                    w_State := 1;
                END_IF;

            11: b_HomeRequest := TRUE; w_State := 1;
            13: b_ResetRequest := TRUE; w_State := 2; w_AckSeq := w_RequestSeq;
        ELSE
            w_Error := 5; w_State := 3; w_AckSeq := w_RequestSeq;
        END_CASE;
    END_IF;
END_IF;

IF w_State = 1 THEN
    IF b_MotionError THEN
        w_Error := w_MotionErrorCode; w_State := 3; w_AckSeq := w_ActiveSeq;
    ELSIF b_MotionDone AND ((w_ActiveCommand = 10) OR (w_ActiveCommand = 11)) THEN
        w_State := 2; w_AckSeq := w_ActiveSeq;
    END_IF;
END_IF;
END_FUNCTION_BLOCK
