#!/usr/bin/env bash
# ==========================================================
# IPTV Ultra Pro - Standalone APK / IPK Builder
# ==========================================================
# This script builds both .apk and .ipk packages without
# needing the full OpenWrt SDK. Use for quick testing.
#
# Usage:
#   chmod +x build-standalone.sh
#   ./build-standalone.sh
#
# Output: ./dist/luci-app-iptv-ultra_*.apk
#         ./dist/luci-app-iptv-ultra_*.ipk
# ==========================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$SCRIPT_DIR"
DIST_DIR="$PROJECT_ROOT/dist"
VERSION="2.0.0"
PKG_NAME="luci-app-iptv-ultra"
ARCH="all"

# Clean
rm -rf "$DIST_DIR"
mkdir -p "$DIST_DIR"

echo "============================================"
echo " IPTV Ultra Pro v${VERSION} Package Builder"
echo "============================================"

# --------------------------------------------------
# 1. Build APK package (for OpenWrt 24+)
# --------------------------------------------------
echo ""
echo "[1/2] Building APK package..."

APK_DIR=$(mktemp -d)
mkdir -p "$APK_DIR/usr/bin"
mkdir -p "$APK_DIR/etc/config"
mkdir -p "$APK_DIR/etc/init.d"
mkdir -p "$APK_DIR/usr/lib/lua/luci/controller"
mkdir -p "$APK_DIR/usr/lib/lua/luci/model/cbi/iptv-ultra"
mkdir -p "$APK_DIR/www/iptv"

# Copy files
cp "$PROJECT_ROOT/files/usr/bin/iptv-ultra" "$APK_DIR/usr/bin/"
cp "$PROJECT_ROOT/files/usr/bin/iptv-probe.py" "$APK_DIR/usr/bin/"
cp "$PROJECT_ROOT/files/etc/config/iptv-ultra" "$APK_DIR/etc/config/"
cp "$PROJECT_ROOT/files/etc/init.d/iptv-ultra" "$APK_DIR/etc/init.d/"
cp "$PROJECT_ROOT/files/usr/lib/lua/luci/controller/iptv-ultra.lua" \
   "$APK_DIR/usr/lib/lua/luci/controller/"
cp "$PROJECT_ROOT/files/usr/lib/lua/luci/model/cbi/iptv-ultra/settings.lua" \
   "$APK_DIR/usr/lib/lua/luci/model/cbi/iptv-ultra/"

chmod 755 "$APK_DIR/usr/bin/iptv-ultra"
chmod 755 "$APK_DIR/usr/bin/iptv-probe.py"
chmod 755 "$APK_DIR/etc/init.d/iptv-ultra"

# Create APK (tar.gz named .apk)
APK_FILE="${PKG_NAME}_${VERSION}_${ARCH}.apk"
cd "$APK_DIR"
tar -czf "$DIST_DIR/$APK_FILE" .
echo "  ✓ Created: $DIST_DIR/$APK_FILE ($(wc -c < "$DIST_DIR/$APK_FILE") bytes)"
cd "$PROJECT_ROOT"
rm -rf "$APK_DIR"

# --------------------------------------------------
# 2. Build IPK package (for opkg - legacy)
# --------------------------------------------------
echo ""
echo "[2/2] Building IPK package..."

IPK_DIR=$(mktemp -d)
IPK_CONTROL="$IPK_DIR/DEBIAN"
mkdir -p "$IPK_CONTROL"

# Control file
cat > "$IPK_CONTROL/control" << EOF
Package: $PKG_NAME
Version: $VERSION-1
Depends: python3-light, python3-urllib, ffmpeg, ffprobe, luci-base, luci-compat
Conflicts:
Maintainer: IPTV Ultra Team
Architecture: $ARCH
Installed-Size: $(du -sk "$PROJECT_ROOT/files" | cut -f1)
Description: IPTV Ultra Pro - Smart IPTV source optimizer
 Automatic IPTV source fetching, FFmpeg-based quality testing,
 intelligent aggregation, and optimized playlist generation.
 Supports TVBox / 影视仓 subscription.
EOF

# Conffiles
echo "/etc/config/iptv-ultra" > "$IPK_CONTROL/conffiles"

# Post-install script
cat > "$IPK_CONTROL/postinst" << 'POSTINST'
#!/bin/sh
# IPTV Ultra Pro post-install
if command -v uci >/dev/null 2>&1; then
    uci commit iptv-ultra 2>/dev/null || true
fi
# Enable and start service
/etc/init.d/iptv-ultra enable 2>/dev/null || true
/etc/init.d/iptv-ultra start 2>/dev/null || true
echo ""
echo "======================================"
echo " IPTV Ultra Pro installed!"
echo "======================================"
echo " Access LuCI: Services -> IPTV Ultra Pro"
echo " Subscribe:   http://<router-ip>/iptv/best.m3u"
echo "======================================"
exit 0
POSTINST

chmod 755 "$IPK_CONTROL/postinst"

# Copy data files
cp -r "$PROJECT_ROOT/files/usr" "$IPK_DIR/"
cp -r "$PROJECT_ROOT/files/etc" "$IPK_DIR/"
mkdir -p "$IPK_DIR/www"
cp -r "$PROJECT_ROOT/files/www" "$IPK_DIR/"

# Build IPK (ar archive)
IPK_FILE="${PKG_NAME}_${VERSION}-1_${ARCH}.ipk"
cd "$IPK_DIR"

# Create control.tar.gz (without ./DEBIAN in paths)
tar -czf control.tar.gz -C "$IPK_CONTROL" . 2>/dev/null || true
# Create data.tar.gz
tar -czf data.tar.gz usr/ etc/ www/ 2>/dev/null
# Create debian-binary
echo "2.0" > debian-binary

# Pack with ar
ar -rc "$DIST_DIR/$IPK_FILE" debian-binary control.tar.gz data.tar.gz

echo "  ✓ Created: $DIST_DIR/$IPK_FILE ($(wc -c < "$DIST_DIR/$IPK_FILE") bytes)"
cd "$PROJECT_ROOT"
rm -rf "$IPK_DIR"

# --------------------------------------------------
# Summary
# --------------------------------------------------
echo ""
echo "============================================"
echo " Build Complete!"
echo "============================================"
echo ""
echo "Output files:"
ls -lh "$DIST_DIR/"
echo ""
echo "Installation:"
echo "  APK (OpenWrt 24+):  apk add ${DIST_DIR}/${APK_FILE}"
echo "  IPK (legacy):       opkg install ${DIST_DIR}/${IPK_FILE}"
echo ""
echo "============================================"
