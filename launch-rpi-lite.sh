#!/bin/bash
# Raspberry Pi OS Lite에서 Weston DRM kiosk와 팬던트를 함께 실행한다.

set -eu

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
PYTHON="${HOME}/pyside-env/bin/python"
WAYLAND_SOCKET="wayland-pendant"
WESTON_LOG="/tmp/pendant-weston.log"

export XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}"
install -d -m 700 "$XDG_RUNTIME_DIR"

cleanup() {
    if [ -n "${WESTON_PID:-}" ] && kill -0 "$WESTON_PID" 2>/dev/null; then
        kill "$WESTON_PID" 2>/dev/null || true
        wait "$WESTON_PID" 2>/dev/null || true
    fi
}
trap cleanup EXIT INT TERM

weston \
    --backend=drm-backend.so \
    --shell=kiosk-shell.so \
    --socket="$WAYLAND_SOCKET" \
    --idle-time=0 \
    --config="$PROJECT_DIR/weston-rpi.ini" \
    --log="$WESTON_LOG" &
WESTON_PID=$!

for _ in $(seq 1 20); do
    [ -S "$XDG_RUNTIME_DIR/$WAYLAND_SOCKET" ] && break
    kill -0 "$WESTON_PID" 2>/dev/null || {
        tail -n 80 "$WESTON_LOG" >&2
        exit 1
    }
    sleep 0.25
done

[ -S "$XDG_RUNTIME_DIR/$WAYLAND_SOCKET" ] || {
    echo "Weston Wayland socket was not created" >&2
    tail -n 80 "$WESTON_LOG" >&2
    exit 1
}

cd "$PROJECT_DIR"
exec env \
    WAYLAND_DISPLAY="$WAYLAND_SOCKET" \
    QT_QPA_PLATFORM=wayland \
    QT_AUTO_SCREEN_SCALE_FACTOR=0 \
    QT_SCALE_FACTOR=1 \
    PENDANT_GPIO_ESTOP=0 \
    PYTHONUNBUFFERED=1 \
    "$PYTHON" main.py
