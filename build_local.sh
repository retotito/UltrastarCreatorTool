#!/usr/bin/env zsh
# build_local.sh — Full local release build (sidecar + Tauri .dmg)
# Usage: ./build_local.sh
set -e

SCRIPT_DIR="${0:a:h}"
cd "$SCRIPT_DIR"

# ── Detect target triple ─────────────────────────────────────────────────────
ARCH=$(uname -m)
if [[ "$ARCH" == "arm64" ]]; then
  TARGET="aarch64-apple-darwin"
else
  TARGET="x86_64-apple-darwin"
fi
echo "→ Target: $TARGET"

# ── Resolve venv paths ───────────────────────────────────────────────────────
PYINSTALLER="$SCRIPT_DIR/.venv/bin/pyinstaller"
if [[ ! -x "$PYINSTALLER" ]]; then
  echo "ERROR: pyinstaller not found at $PYINSTALLER"
  echo "Run: source .venv/bin/activate && pip install pyinstaller"
  exit 1
fi

# ── Ensure ffmpeg is available for bundling ──────────────────────────────────
if ! command -v ffmpeg &>/dev/null && [[ ! -f /opt/homebrew/bin/ffmpeg ]] && [[ ! -f /usr/local/bin/ffmpeg ]]; then
  echo "→ ffmpeg not found — downloading static binary for bundling..."
  FFMPEG_TMP="$SCRIPT_DIR/.ffmpeg_build"
  mkdir -p "$FFMPEG_TMP"
  if [[ "$ARCH" == "arm64" ]]; then
    FFMPEG_URL="https://evermeet.cx/ffmpeg/getrelease/ffmpeg/zip"
  else
    FFMPEG_URL="https://evermeet.cx/ffmpeg/getrelease/ffmpeg/zip"
  fi
  curl -L "$FFMPEG_URL" -o "$FFMPEG_TMP/ffmpeg.zip"
  unzip -o "$FFMPEG_TMP/ffmpeg.zip" -d "$FFMPEG_TMP"
  chmod +x "$FFMPEG_TMP/ffmpeg"
  export PATH="$FFMPEG_TMP:$PATH"
  echo "→ ffmpeg ready at $FFMPEG_TMP/ffmpeg"
fi

# ── Step 1: Build Python sidecar with PyInstaller ───────────────────────────
echo "→ Building Python sidecar (this takes a few minutes)..."
rm -rf dist-backend build/backend
"$PYINSTALLER" backend/backend.spec --distpath dist-backend --noconfirm --clean

SIDECAR_RESOURCES="frontend/src-tauri/resources/backend"
echo "→ Copying onedir bundle to $SIDECAR_RESOURCES"
rm -rf "$SIDECAR_RESOURCES"
mkdir -p frontend/src-tauri/resources
cp -r dist-backend/backend "$SIDECAR_RESOURCES"

# ── Step 2: Build the Tauri app (.app only) ─────────────────────────────────
# The .dmg is made below from the re-signed .app: Tauri's own .dmg step removes the .app afterwards, so the
# re-signing never ran and the .dmg held an app with only the linker's signature (strict check failed).
echo "→ Building Tauri app..."
cd frontend
npm run tauri build -- --bundles app

# ── Re-sign .app (fixes SIGKILL for unsigned dylibs from pyannote/speechbrain) ──
APP=$(find src-tauri/target/release/bundle/macos -name "*.app" 2>/dev/null | head -1)
if [[ -z "$APP" ]]; then
  echo "ERROR: no .app was built"
  exit 1
fi
echo "→ Ad-hoc re-signing $APP ..."
codesign --force --deep --sign - "$APP" 2>&1
codesign --verify --deep --strict "$APP"
echo "✓ Re-signed and verified"

# ── .dmg from the signed .app ────────────────────────────────────────────────
APP_NAME=$(basename "$APP" .app)
VERSION=$(sed -n 's/.*"version": *"\([^"]*\)".*/\1/p' src-tauri/tauri.conf.json | head -1)
DMG_DIR="src-tauri/target/release/bundle/dmg"
mkdir -p "$DMG_DIR"
DMG="$DMG_DIR/${APP_NAME}_${VERSION}_${ARCH/arm64/aarch64}.dmg"
STAGING=$(mktemp -d)
ditto "$APP" "$STAGING/$(basename "$APP")"
ln -s /Applications "$STAGING/Applications"
hdiutil create -volname "$APP_NAME" -srcfolder "$STAGING" -ov -format UDZO "$DMG"
rm -rf "$STAGING"

echo ""
echo "✓ Build complete!"
echo "  .dmg → $SCRIPT_DIR/frontend/$DMG"
echo ""
echo "  Install: open frontend/$DMG"
