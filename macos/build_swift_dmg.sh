#!/usr/bin/env bash
set -euo pipefail

# Build 100% native macOS SwiftUI + AppKit Lingo.app Universal DMG on a real Mac (macOS 13+ / Xcode CLT)
ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
STAGE_DIR="$(mktemp -d)"
APP="$STAGE_DIR/Lingo.app"
DMG_OUT="$ROOT_DIR/releases/Lingo-macOS.dmg"
trap 'rm -rf "$STAGE_DIR"' EXIT

echo "[1/5] Building production frontend..."
(cd "$ROOT_DIR/frontend" && npm run build)

echo "[2/5] Running Swift XCTests..."
(cd "$ROOT_DIR/macos/native-app" && swift test --verbose)

echo "[3/5] Compiling Universal SwiftUI + AppKit binary (arm64 + x86_64)..."
(cd "$ROOT_DIR/macos/native-app" && swift build -c release --arch arm64 --arch x86_64)
BIN_DIR="$(cd "$ROOT_DIR/macos/native-app" && swift build -c release --arch arm64 --arch x86_64 --show-bin-path)"
BINARY="$BIN_DIR/LingoReelApp"
lipo -info "$BINARY"

echo "[4/5] Generating transparent Apple HIG Squircle AppIcon.icns & assembling Lingo.app..."
mkdir -p "$STAGE_DIR/AppIcon.iconset"
SRC="$ROOT_DIR/macos/LingoAppIcon.png"
for sz in 16 32 128 256 512; do
  sips -s format png -z "$sz" "$sz" "$SRC" --out "$STAGE_DIR/AppIcon.iconset/icon_${sz}x${sz}.png" >/dev/null
  sz2=$((sz * 2))
  sips -s format png -z "$sz2" "$sz2" "$SRC" --out "$STAGE_DIR/AppIcon.iconset/icon_${sz}x${sz}@2x.png" >/dev/null
done
iconutil -c icns "$STAGE_DIR/AppIcon.iconset" -o "$STAGE_DIR/AppIcon.icns"

mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources/app/backend" "$APP/Contents/Resources/app/frontend/dist"
cp "$ROOT_DIR/macos/Info.plist" "$APP/Contents/Info.plist"
plutil -replace LSUIElement -bool false "$APP/Contents/Info.plist"
printf 'APPL????' > "$APP/Contents/PkgInfo"
cp "$BINARY" "$APP/Contents/MacOS/LingoReelApp"
chmod +x "$APP/Contents/MacOS/LingoReelApp"
cp "$STAGE_DIR/AppIcon.icns" "$APP/Contents/Resources/AppIcon.icns"
cp "$ROOT_DIR/macos/native-app/Sources/LingoReelApp/Resources/lingo-logo.png" "$APP/Contents/Resources/lingo-logo.png"
for b in "$BIN_DIR"/*.bundle; do
  if [ -d "$b" ]; then
    cp -R "$b" "$APP/Contents/Resources/"
  fi
done
rsync -a --exclude='.venv' --exclude='data' --exclude='__pycache__' --exclude='*.pyc' --exclude='.DS_Store' \
  "$ROOT_DIR/backend/" "$APP/Contents/Resources/app/backend/"
rsync -a --exclude='.DS_Store' "$ROOT_DIR/frontend/dist/" "$APP/Contents/Resources/app/frontend/dist/"
cp "$ROOT_DIR/README.md" "$APP/Contents/Resources/app/README.md"

codesign --force --deep --sign - "$APP"
codesign --verify --deep --strict "$APP"
"$APP/Contents/MacOS/LingoReelApp" --self-test --verify-bundle

echo "[5/5] Creating genuine Apple UDZO DMG -> $DMG_OUT..."
mkdir -p "$STAGE_DIR/dmg_root" "$ROOT_DIR/releases"
cp -R "$APP" "$STAGE_DIR/dmg_root/"
ln -s /Applications "$STAGE_DIR/dmg_root/Applications"
cp "$ROOT_DIR/macOS安装说明.txt" "$STAGE_DIR/dmg_root/安装说明.txt"
hdiutil create -volname "Lingo" -srcfolder "$STAGE_DIR/dmg_root" -ov -format UDZO "$DMG_OUT"
ls -lh "$DMG_OUT"
echo "[✓] Built 100% Native SwiftUI Universal DMG: $DMG_OUT"
