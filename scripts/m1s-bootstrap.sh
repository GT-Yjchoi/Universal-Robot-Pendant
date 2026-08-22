#!/bin/bash
# M1S Pendant bootstrap — Ubuntu 24.04 server clean install 에서 한방에
# g24p0 mali blob + DSI VU8s overlay + weston + PySide6 (HW 가속 검증) 까지.
#
# 사용법:
#   bash scripts/m1s-bootstrap.sh
#   (sudo 비밀번호 한 번 물어보고 나머지는 자동)
#
# 멱등 (idempotent): 다시 돌려도 안전. 이미 적용된 단계는 skip.
# 끝에서 verify 단계가 PASS/FAIL 로 보고.
#
# 처음 적용 후에는 reboot 필수 (DSI overlay 가 boot 시 적용됨).

set -euo pipefail

# -----------------------------------------------------------------------------
# 상수 / 설정
# -----------------------------------------------------------------------------
MALI_DEB_URL="https://github.com/tsukumijima/libmali-rockchip/releases/download/v1.9-1-20260312-bd33ee2/libmali-bifrost-g52-g24p0-wayland-gbm_1.9-1_arm64.deb"
MALI_DEB_SHA256_HINT=""  # 검증 안 함 — release 가 GitHub Actions 빌드라 해시 가변
MALI_SO_DST="/usr/lib/aarch64-linux-gnu/libmali.so.1.9.0"
MALI_SO_MIN_SIZE_MB=40   # 진짜 binary 는 54MB, stub 은 21KB
EXPECTED_BUILD_TAG="g24p0-00eac0"

CONFIG_INI="/boot/config.ini"
OVERLAY_NAME="display_vu8s"

OVERRIDE_DIR="/etc/systemd/system/libmali-setup.service.d"
OVERRIDE_FILE="$OVERRIDE_DIR/override.conf"

VENV_DIR="/home/odroid/pyside-env"

# 색
C_RED=$'\033[31m'; C_GRN=$'\033[32m'; C_YLW=$'\033[33m'; C_CYN=$'\033[36m'; C_RST=$'\033[0m'

step() { echo; echo "${C_CYN}== $* ==${C_RST}"; }
ok()   { echo "${C_GRN}  OK${C_RST}   $*"; }
skip() { echo "${C_YLW}  skip${C_RST} $*"; }
fail() { echo "${C_RED}  FAIL${C_RST} $*"; exit 1; }
info() { echo "         $*"; }

# -----------------------------------------------------------------------------
# Sanity
# -----------------------------------------------------------------------------
step "Sanity check"

[ "$(id -u)" -ne 0 ] || fail "root 로 직접 돌리지 마. 'bash $0' 로 실행 — 필요할 때 sudo 만 호출."

# sudo 한 번 prime (cache 가 valid 하면 prompt 안 뜸)
if ! sudo -n true 2>/dev/null; then
    info "sudo 비밀번호 필요 — 한 번만 물어봄"
    sudo true || fail "sudo 권한 거부됨"
fi
# keepalive: 50초마다 cache 갱신해서 script 중간에 안 만료되게
( while true; do sudo -n true 2>/dev/null || exit; sleep 50; done ) &
SUDO_KEEPALIVE=$!
trap 'kill $SUDO_KEEPALIVE 2>/dev/null || true' EXIT

. /etc/os-release
case "$VERSION_ID" in
    24.04) ok "Ubuntu $VERSION_ID ($VERSION_CODENAME)" ;;
    *) fail "Ubuntu 24.04 전용 (이 시스템: $PRETTY_NAME)" ;;
esac

GPUINFO=$(find /sys/devices/platform -name gpuinfo 2>/dev/null | head -1)
if [ -n "$GPUINFO" ] && grep -q 'Mali-G52' "$GPUINFO"; then
    ok "$(cat $GPUINFO)"
else
    fail "Mali-G52 GPU 감지 안 됨 (M1S 가 맞는지 확인)"
fi

# -----------------------------------------------------------------------------
# apt lock 풀릴 때까지 대기 (unattended-upgrades 가 boot 직후 자주 잡고있음)
# -----------------------------------------------------------------------------
step "apt lock 대기"
TIMEOUT_S=900   # 최대 15분
ELAPSED=0
while sudo lsof /var/lib/dpkg/lock-frontend /var/lib/dpkg/lock >/dev/null 2>&1; do
    if [ $ELAPSED -ge $TIMEOUT_S ]; then
        fail "apt lock 이 15분 후에도 안 풀림. unattended-upgrades 확인 필요."
    fi
    if [ $ELAPSED -eq 0 ]; then
        info "다른 프로세스가 apt 잡고있어 대기 (보통 unattended-upgrades, 5-10분)"
    fi
    sleep 5
    ELAPSED=$((ELAPSED + 5))
done
ok "apt lock 해방됨 (대기 ${ELAPSED}s)"

# -----------------------------------------------------------------------------
# Phase A: /boot/config.ini 에 display_vu8s overlay 추가
# -----------------------------------------------------------------------------
step "Phase A — DSI VU8s overlay (/boot/config.ini)"

if grep -qE "^overlays=.*\b${OVERLAY_NAME}\b" "$CONFIG_INI"; then
    skip "이미 ${OVERLAY_NAME} 적용됨"
else
    TS=$(date +%Y%m%d-%H%M%S)
    sudo cp "$CONFIG_INI" "${CONFIG_INI}.bak-${TS}"
    info "백업: ${CONFIG_INI}.bak-${TS}"
    sudo sed -i -E "/^\[generic\]/,/^\[/{
        s|^overlays=\"([^\"]*)\"|overlays=\"\1 ${OVERLAY_NAME}\"|
    }" "$CONFIG_INI"
    if grep -qE "^overlays=.*\b${OVERLAY_NAME}\b" "$CONFIG_INI"; then
        ok "[generic] overlays 에 ${OVERLAY_NAME} 추가됨"
    else
        fail "config.ini 패치 실패 — 수동 수정 필요"
    fi
fi

# -----------------------------------------------------------------------------
# Phase B: apt 패키지 설치
# -----------------------------------------------------------------------------
step "Phase B — apt 패키지"

# linuxfactory PPA 의 g24p0 wayland-gbm 은 현재 빈 stub 이지만 (2026-05 기준)
# Provides: libmali 메타 자리 잡으라고 같이 설치. 진짜 .so 는 Phase C 에서.
APT_PACKAGES=(
    # mali 머신러리
    libmali-setup
    libmali-bifrost-g52-g24p0-wayland-gbm

    # bind 대상 (Mesa stubs — libmali-setup 가 이 위에 bind-mount)
    libegl1 libgles2 libgbm1 libwayland-egl1

    # 도구
    binutils

    # Weston (kiosk + drm-backend)
    weston

    # PySide6 venv
    python3-pip python3.12-venv

    # Qt6 의 system 의존 (libGL 셰임, XCB, X11 보조)
    libgl1
    libxcb-cursor0 libxkbcommon-x11-0
    libxcb-icccm4 libxcb-image0 libxcb-keysyms1
    libxcb-render-util0 libxcb-shape0
    libsm6 libice6
)

sudo DEBIAN_FRONTEND=noninteractive apt-get update -qq
info "apt-get install 진행 (5~10분 걸릴 수 있음)…"
sudo DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends "${APT_PACKAGES[@]}" >/tmp/m1s-apt.log 2>&1 \
    || { tail -30 /tmp/m1s-apt.log; fail "apt install 실패 (전체 로그: /tmp/m1s-apt.log)"; }
ok "apt 패키지 ${#APT_PACKAGES[@]}개 설치/확인"

# -----------------------------------------------------------------------------
# Phase C: 진짜 g24p0 .so 배치 (tsukumijima GitHub)
# -----------------------------------------------------------------------------
step "Phase C — g24p0 mali blob (tsukumijima)"

need_download=true
if [ -f "$MALI_SO_DST" ]; then
    sz_mb=$(($(stat -c%s "$MALI_SO_DST") / 1024 / 1024))
    tag=$(grep -aoE 'g[0-9]+p0-[0-9a-z]+' "$MALI_SO_DST" 2>/dev/null | sort -u | head -1)
    if [ "$sz_mb" -ge "$MALI_SO_MIN_SIZE_MB" ] && [ "$tag" = "$EXPECTED_BUILD_TAG" ]; then
        skip "${MALI_SO_DST} 이미 진짜 g24p0 (${sz_mb}MB, ${tag})"
        need_download=false
    else
        info "기존 ${MALI_SO_DST} (${sz_mb}MB, tag=${tag:-none}) — 진짜 binary 로 교체"
    fi
fi

if [ "$need_download" = "true" ]; then
    TMPDIR=$(mktemp -d)
    info "다운로드: $(basename $MALI_DEB_URL)"
    wget -q "$MALI_DEB_URL" -O "$TMPDIR/mali.deb" || fail "다운로드 실패"
    dpkg-deb -x "$TMPDIR/mali.deb" "$TMPDIR/ex"
    SRC_SO=$(find "$TMPDIR/ex" -name 'libmali.so*' -type f | head -1)
    [ -n "$SRC_SO" ] || fail "추출된 .deb 안에 libmali.so 없음"
    src_tag=$(grep -aoE 'g[0-9]+p0-[0-9a-z]+' "$SRC_SO" | sort -u | head -1)
    [ "$src_tag" = "$EXPECTED_BUILD_TAG" ] || fail "추출본 build tag = ${src_tag}, 기대값 ${EXPECTED_BUILD_TAG} 와 불일치"
    sudo /usr/sbin/libmali-setup --disable 2>/dev/null || true
    sudo cp "$SRC_SO" "$MALI_SO_DST"
    sudo chmod 644 "$MALI_SO_DST"
    sudo ldconfig
    rm -rf "$TMPDIR"
    ok "${MALI_SO_DST} 배치 ($(($(stat -c%s $MALI_SO_DST)/1024/1024))MB, tag=${src_tag})"
fi

# -----------------------------------------------------------------------------
# Phase D: libmali-setup systemd override + apt-mark
# -----------------------------------------------------------------------------
step "Phase D — systemd 안전장치 + apt-mark"

if [ -f "$OVERRIDE_FILE" ] && grep -q 'bind count' "$OVERRIDE_FILE"; then
    skip "override.conf 이미 적용됨"
else
    sudo mkdir -p "$OVERRIDE_DIR"
    sudo tee "$OVERRIDE_FILE" >/dev/null <<'EOF'
# m1s-bootstrap.sh 가 배치 — 손대지 마.
# 원본 libmali-setup 스크립트가 /mali/libEGL.so.1 (없는 경로) 에도 bind 시도하다 exit 1 로 끝남.
# 그래도 핵심 bind 4개 (libEGL/libGLESv2/libgbm/libwayland-egl) 가 잡혔으면 진짜 성공.
# 이 wrapper 가 mount 개수를 세서 4개 이상이면 SUCCESS 로 변환.
[Service]
Type=oneshot
RemainAfterExit=yes
ExecStart=
ExecStart=/bin/sh -c '/usr/sbin/libmali-setup; n=$(mount | grep -cE "/usr/lib/aarch64-linux-gnu/(libEGL|libGLESv2|libgbm|libwayland-egl)\\.so"); if [ "$n" -ge 4 ]; then exit 0; else echo "libmali-setup bind count $n < 4"; exit 1; fi'
EOF
    sudo systemctl daemon-reload
    ok "override.conf 작성 + daemon-reload"
fi

sudo systemctl restart libmali-setup.service
if systemctl is-active --quiet libmali-setup.service; then
    ok "libmali-setup.service active"
else
    fail "libmali-setup.service 시작 실패 (journalctl -u libmali-setup 확인)"
fi

# autoremove 보호 / 빈 stub 자동 업그레이드 방지
sudo apt-mark manual libmali-setup >/dev/null
sudo apt-mark hold libmali-bifrost-g52-g24p0-wayland-gbm >/dev/null
ok "apt-mark: libmali-setup=manual, libmali-bifrost-g52-g24p0-wayland-gbm=hold"

# -----------------------------------------------------------------------------
# Phase E: PySide6 venv
# -----------------------------------------------------------------------------
step "Phase E — PySide6 venv"

if [ -x "$VENV_DIR/bin/python" ]; then
    info "venv 이미 존재 — pip install PySide6 (upgrade if needed)"
else
    python3 -m venv "$VENV_DIR"
    info "venv 생성: $VENV_DIR"
fi

"$VENV_DIR/bin/pip" install --upgrade -q pip >/tmp/m1s-pip.log 2>&1 \
    || { tail -20 /tmp/m1s-pip.log; fail "pip upgrade 실패"; }
"$VENV_DIR/bin/pip" install -q PySide6 >>/tmp/m1s-pip.log 2>&1 \
    || { tail -20 /tmp/m1s-pip.log; fail "PySide6 설치 실패 (/tmp/m1s-pip.log)"; }
PYSIDE_VER=$("$VENV_DIR/bin/python" -c 'import PySide6; print(PySide6.__version__)' 2>&1)
ok "PySide6 ${PYSIDE_VER} (venv: $VENV_DIR)"

# -----------------------------------------------------------------------------
# Phase F: 검증 & 리포트
# -----------------------------------------------------------------------------
step "Phase F — 검증"

PASS=0; FAIL_COUNT=0
check() {
    local name="$1"; local expected="$2"; local actual="$3"
    if [ "$actual" = "$expected" ]; then
        ok   "$name = $actual"
        PASS=$((PASS+1))
    else
        echo "${C_RED}  FAIL${C_RST} $name : got '$actual', want '$expected'"
        FAIL_COUNT=$((FAIL_COUNT+1))
    fi
}
check_min() {
    local name="$1"; local min="$2"; local actual="$3"
    if [ "$actual" -ge "$min" ] 2>/dev/null; then
        ok   "$name = $actual (≥ $min)"
        PASS=$((PASS+1))
    else
        echo "${C_RED}  FAIL${C_RST} $name : got '$actual', want ≥ $min"
        FAIL_COUNT=$((FAIL_COUNT+1))
    fi
}

# 1. config.ini overlay
if grep -qE "^overlays=.*\b${OVERLAY_NAME}\b" "$CONFIG_INI"; then
    ok "config.ini overlay = ${OVERLAY_NAME}"
    PASS=$((PASS+1))
else
    echo "${C_RED}  FAIL${C_RST} config.ini overlay"
    FAIL_COUNT=$((FAIL_COUNT+1))
fi

# 2. libmali blob
sz_mb=$(($(stat -c%s "$MALI_SO_DST") / 1024 / 1024))
check_min "libmali.so.1.9.0 size (MB)" $MALI_SO_MIN_SIZE_MB "$sz_mb"
tag=$(grep -aoE 'g[0-9]+p0-[0-9a-z]+' "$MALI_SO_DST" | sort -u | head -1)
check "libmali build tag" "$EXPECTED_BUILD_TAG" "$tag"

# 3. systemd
state=$(systemctl is-active libmali-setup.service)
check "libmali-setup.service state" "active" "$state"

# 4. bind mount 개수
binds=$(mount | grep -cE '/usr/lib/aarch64-linux-gnu/(libEGL|libGLESv2|libgbm|libwayland-egl)\.so')
check_min "bind mounts" 4 "$binds"

# 5. 라이브 libEGL 의 EGL 1.5 entry
egl_tag=$(grep -aoE 'g[0-9]+p0-[0-9a-z]+' /usr/lib/aarch64-linux-gnu/libEGL.so.1 | sort -u | head -1)
check "live libEGL.so.1 build tag" "$EXPECTED_BUILD_TAG" "$egl_tag"
egl15=$(nm -D /usr/lib/aarch64-linux-gnu/libEGL.so.1 2>/dev/null | grep -cE 'T eglGetPlatformDisplay$|T eglCreatePlatformWindowSurface$')
check_min "EGL 1.5 core symbols" 2 "$egl15"

# 6. PySide6 import + Qt 버전
qt_ver=$("$VENV_DIR/bin/python" -c 'from PySide6.QtCore import qVersion; print(qVersion())' 2>/dev/null) || qt_ver="(import 실패)"
if [ -n "$qt_ver" ] && [ "$qt_ver" != "(import 실패)" ]; then
    ok "PySide6 / Qt = $qt_ver"
    PASS=$((PASS+1))
else
    echo "${C_RED}  FAIL${C_RST} PySide6 import"
    FAIL_COUNT=$((FAIL_COUNT+1))
fi

# 7. DRM (DSI 는 부팅 후에만 보임 — HDMI 상태도 OK)
drm_status=$(for s in /sys/class/drm/card*-*/status; do [ -f "$s" ] && cat "$s"; done | sort -u | grep -vw unknown | head -1)
if [ -n "$drm_status" ]; then
    info "DRM 1개 이상 connected ($(ls /sys/class/drm/card0-*/status 2>/dev/null | xargs -I{} sh -c 'echo "{}: $(cat {})"' | grep -v unknown | head -1))"
fi

# -----------------------------------------------------------------------------
# 결산
# -----------------------------------------------------------------------------
echo
echo "${C_CYN}==================== 결과 ====================${C_RST}"
echo "  PASS: $PASS"
echo "  FAIL: $FAIL_COUNT"
echo

if [ $FAIL_COUNT -eq 0 ]; then
    echo "${C_GRN}모든 검증 통과.${C_RST}"
    echo
    echo "다음 단계:"
    echo "  1. ${C_YLW}HDMI 케이블 빼고 DSI VU8s 패널 연결${C_RST} (overlay 가 HDMI 끄고 DSI 만 활성화)"
    echo "  2. ${C_YLW}sudo reboot${C_RST}"
    echo "  3. 부팅 후 DSI 화면에 텍스트 콘솔이 떠야 정상"
    echo "  4. (선택) tty 에서 weston + PySide6 hello world 검증:"
    echo "     - Universal-Robot-Pendant/scripts/m1s-verify-gui.sh 가 있으면 그걸 실행"
    echo "     - 또는 weston 직접 + venv 의 PySide6 import 확인"
    exit 0
else
    echo "${C_RED}일부 검증 실패.${C_RST} 위 'FAIL' 라인 확인."
    echo "  로그: /tmp/m1s-apt.log, /tmp/m1s-pip.log, journalctl -u libmali-setup"
    exit 1
fi
