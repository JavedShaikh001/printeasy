#!/usr/bin/env bash
# Build PrintEasy.app and wrap it in a drag-to-Applications .dmg.   Run on a Mac:
#   bash packaging/macos/build_dmg.sh
# Optional signing/notarisation (removes the "unidentified developer" warning):
#   export MAC_SIGN_ID="Developer ID Application: Your Name (TEAMID)"
#   export MAC_NOTARY_PROFILE="printeasy-notary"   # made with: xcrun notarytool store-credentials
set -euo pipefail
cd "$(dirname "$0")/../.."

VERSION=1.0.0
ARCH=$(uname -m)
python3 -m pip install -r requirements.txt pyinstaller pillow
python3 packaging/make_icons.py
rm -rf build dist/PrintEasy dist/PrintEasy.app
pyinstaller --noconfirm printeasy.spec

APP=dist/PrintEasy.app
if [[ -n "${MAC_SIGN_ID:-}" ]]; then
  codesign --deep --force --options runtime --timestamp --sign "$MAC_SIGN_ID" "$APP"
fi

mkdir -p dist/installers
STAGE=$(mktemp -d)
cp -R "$APP" "$STAGE/"
ln -s /Applications "$STAGE/Applications"
DMG="dist/installers/PrintEasy-$VERSION-macOS-$ARCH.dmg"
rm -f "$DMG"
hdiutil create -volname "PrintEasy" -srcfolder "$STAGE" -ov -format UDZO "$DMG"
rm -rf "$STAGE"

if [[ -n "${MAC_SIGN_ID:-}" ]]; then
  codesign --force --sign "$MAC_SIGN_ID" "$DMG"
fi
if [[ -n "${MAC_NOTARY_PROFILE:-}" ]]; then
  xcrun notarytool submit "$DMG" --keychain-profile "$MAC_NOTARY_PROFILE" --wait
  xcrun stapler staple "$DMG"
fi
echo "Built $DMG"
