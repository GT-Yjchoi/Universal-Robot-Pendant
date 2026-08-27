(*
  Panasonic FP0H - pendant communication watchdog.

  Connect w_Heartbeat to DT200. Combine b_CommunicationOK with the physical
  E-stop and machine interlocks before feeding FB_PendantMailbox.b_InterlockOK.
  b_WatchdogStop is a one-scan pulse suitable for the servo stop request path.
*)
FUNCTION_BLOCK FB_PendantWatchdog
VAR_INPUT
    w_Heartbeat       : WORD;
    t_Timeout         : TIME := T#1500MS;
END_VAR
VAR_OUTPUT
    b_CommunicationOK : BOOL;
    b_WatchdogStop    : BOOL;
END_VAR
VAR
    w_Previous        : WORD;
    b_Changed          : BOOL;
    b_TimeoutPrevious : BOOL;
    fb_Timeout        : TON;
END_VAR

b_Changed := w_Heartbeat <> w_Previous;
IF b_Changed THEN
    w_Previous := w_Heartbeat;
END_IF;

(* A changed heartbeat resets TON for one scan. *)
fb_Timeout(IN := NOT b_Changed, PT := t_Timeout);
b_CommunicationOK := NOT fb_Timeout.Q;
b_WatchdogStop := fb_Timeout.Q AND NOT b_TimeoutPrevious;
b_TimeoutPrevious := fb_Timeout.Q;

END_FUNCTION_BLOCK
