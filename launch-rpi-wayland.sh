#!/bin/bash
# Raspberry Pi OS Desktop의 기존 Wayland 세션에서 실행하는 개발용 실행기.

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
