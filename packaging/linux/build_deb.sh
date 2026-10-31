#!/usr/bin/env bash
# Build a .deb for Ubuntu, Debian, Linux Mint, Pop!_OS, Zorin ...   Run on Linux:
#   bash packaging/linux/build_deb.sh
# Double-clicking the .deb opens the Software app with an Install button.
set -euo pipefail
cd "$(dirname "$0")/../.."

VERSION=1.0.0
ARCH=$(dpkg --print-architecture)
if [[ "${SKIP_PIP:-0}" != "1" ]]; then
  python3 -m pip install -r requirements.txt pyinstaller pillow
fi
python3 packaging/make_icons.py
rm -rf build dist/PrintEasy
pyinstaller --noconfirm printeasy.spec

PKG=$(mktemp -d)/printeasy_${VERSION}_${ARCH}
mkdir -p "$PKG/DEBIAN" "$PKG/opt/printeasy" "$PKG/usr/bin" "$PKG/usr/share/applications" \
         "$PKG/usr/share/icons/hicolor/256x256/apps" "$PKG/usr/share/icons/hicolor/1024x1024/apps"
cp -a dist/PrintEasy/. "$PKG/opt/printeasy/"
ln -s /opt/printeasy/PrintEasy "$PKG/usr/bin/printeasy"
cp packaging/assets/printeasy-256.png "$PKG/usr/share/icons/hicolor/256x256/apps/printeasy.png"
cp packaging/assets/printeasy.png "$PKG/usr/share/icons/hicolor/1024x1024/apps/printeasy.png"
cp packaging/linux/printeasy.desktop "$PKG/usr/share/applications/printeasy.desktop"

SIZE=$(du -sk "$PKG" | cut -f1)
cat > "$PKG/DEBIAN/control" <<EOF
Package: printeasy
Version: $VERSION
Section: utils
Priority: optional
Architecture: $ARCH
Installed-Size: $SIZE
Depends: cups-client, libxkbcommon-x11-0, libxcb-cursor0, libegl1
Recommends: cups, cups-filters, avahi-daemon, network-manager, xdotool, policykit-1 | polkitd
Maintainer: PrintEasy <support@printeasy.invalid>
Description: Connect any printer without the headache
 PrintEasy finds printers on your Wi-Fi or USB, connects them in one click,
 helps new printers join Wi-Fi, keeps printer addresses from changing, and
 lets you choose which printer each program uses.
EOF
cat > "$PKG/DEBIAN/postinst" <<'EOF'
#!/bin/sh
set -e
# Let the person who installed PrintEasy add printers without typing a password each time.
WHO="${SUDO_USER:-}"
if [ -z "$WHO" ] && [ -n "${PKEXEC_UID:-}" ]; then WHO=$(getent passwd "$PKEXEC_UID" | cut -d: -f1); fi
if [ -n "$WHO" ] && [ "$WHO" != "root" ] && getent group lpadmin >/dev/null; then
  usermod -aG lpadmin "$WHO" || true
fi
command -v update-desktop-database >/dev/null && update-desktop-database -q || true
command -v gtk-update-icon-cache >/dev/null && gtk-update-icon-cache -q /usr/share/icons/hicolor || true
exit 0
EOF
chmod 755 "$PKG/DEBIAN/postinst"

mkdir -p dist/installers
OUT="dist/installers/PrintEasy-$VERSION-Linux-$ARCH.deb"
dpkg-deb --root-owner-group --build "$PKG" "$OUT"
echo "Built $OUT"
