#!/bin/bash
# Raspberry Pi OS Desktop용 실행기.
# 기존 launch.sh는 ODROID-M1S에서 Weston DRM을 직접 띄우는 용도다.

set -eu

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
PYTHON="${HOME}/pyside-env/bin/python"

export XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}"
export WAYLAND_DISPLAY="${WAYLAND_DISPLAY:-wayland-0}"
export QT_QPA_PLATFORM="${QT_QPA_PLATFORM:-wayland}"
export PENDANT_GPIO_ESTOP="${PENDANT_GPIO_ESTOP:-0}"
export PYTHONUNBUFFERED=1

cd "$PROJECT_DIR"
exec "$PYTHON" main.py
