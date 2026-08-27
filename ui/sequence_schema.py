"""Recipe sequence normalization shared by non-visual backends."""

MONITOR_SEQ_KEY = "Monitor"


def normalize_step(step, timer_library=None):
    kind = step.get("type")
    if kind == "TMR" and step.get("tmr_mode") == "hold":
        # Legacy held-signal timers are now represented by an IN time-up step.
        timer_ref = step.pop("timer_ref", "")
        step["type"] = "IN"
        step["timeup_enabled"] = True
        step["timeup_time"] = float(step.pop("time", 0.0))
        if timer_ref:
            step["timeup_timer_ref"] = timer_ref
        step.pop("tmr_mode", None)
        kind = "IN"
    if kind in ("POS", "WPOS"):
        axes = step.get("active_axes", step.get("axes"))
        if not isinstance(axes, list):
            axes = [True] * 8 if kind == "WPOS" else [False] * 8
        step["active_axes"] = (list(axes) + [False] * 8)[:8]
        if kind == "WPOS":
            step["position_tolerance"] = max(
                0.0, float(step.get("position_tolerance", 0.1))
            )
            step["timeout"] = max(0.001, float(step.get("timeout", 5.0)))
    elif kind == "IN":
        if "in_type" not in step:
            port = step.get("port", 0)
            step["in_type"] = 3 if port >= 200 else 2 if port >= 100 else 1 if port >= 32 else 0
        if step.get("timeup_enabled", False):
            ref = step.get("timeup_timer_ref", "")
            if ref and timer_library and ref in timer_library:
                step["timeup_time"] = float(timer_library[ref])
        if step.get("timeout_enabled", False):
            ref = step.get("timeout_timer_ref", "")
            if ref and timer_library and ref in timer_library:
                step["timeout"] = float(timer_library[ref])
            else:
                step["timeout"] = max(0.0, float(step.get("timeout", 5.0)))
    elif kind == "TMR":
        ref = step.get("timer_ref", "")
        if ref and timer_library and ref in timer_library:
            step["time"] = float(timer_library[ref])
    elif kind == "OUT" and step.get("delay_enable", False):
        ref = step.get("delay_timer_ref", "")
        if ref and timer_library and ref in timer_library:
            step["delay_time"] = float(timer_library[ref])
    elif kind == "JMP" and str(step.get("cond_type", "")).upper() in (
            "POSITION", "POINT", "AXISPOS"):
        axes = step.get("cond_position_axes")
        if not isinstance(axes, list):
            axes = [True] * 8
        step["cond_type"] = "POSITION"
        step["cond_position_axes"] = (list(axes) + [False] * 8)[:8]
        step["cond_position_tolerance"] = max(
            0.0, float(step.get("cond_position_tolerance", 0.1))
        )


def normalize_all_sequences(sequences, timer_library=None):
    if not isinstance(sequences, dict):
        return
    for steps in sequences.values():
        if isinstance(steps, list):
            for step in steps:
                if isinstance(step, dict):
                    normalize_step(step, timer_library)
