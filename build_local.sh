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

# ── Step 1: Build Python sidecar with PyInstaller ───────────────────────────
echo "→ Building Python sidecar (this takes a few minutes)..."
rm -rf dist-backend build/backend
"$PYINSTALLER" backend/backend.spec --distpath dist-backend --noconfirm --clean

SIDECAR_RESOURCES="frontend/src-tauri/resources/backend"
echo "→ Copying onedir bundle to $SIDECAR_RESOURCES"
rm -rf "$SIDECAR_RESOURCES"
mkdir -p frontend/src-tauri/resources
cp -r dist-backend/backend "$SIDECAR_RESOURCES"

# ── Step 2: Build Tauri app ──────────────────────────────────────────────────
echo "→ Building Tauri app..."
cd frontend
npm run tauri build || true  # DMG creation may fail on macOS 26 — handled below

# ── Re-sign .app (fixes SIGKILL for unsigned dylibs from pyannote/speechbrain) ──
APP=$(find src-tauri/target/release/bundle/macos -name "*.app" 2>/dev/null | head -1)
if [[ -n "$APP" ]]; then
  echo "→ Ad-hoc re-signing $APP ..."
  codesign --force --deep --sign - "$APP" 2>&1
  echo "✓ Re-signed"
fi

# ── Done ─────────────────────────────────────────────────────────────────────
DMG=$(find src-tauri/target/release/bundle/dmg -name "*.dmg" 2>/dev/null | head -1)
if [[ -z "$DMG" ]] && [[ -n "$APP" ]]; then
  # Tauri's bundle_dmg.sh failed (known issue with macOS 26 / large bundles).
  # Create the DMG manually with hdiutil.
  echo "→ Tauri DMG failed — creating DMG manually with hdiutil..."
  APP_NAME=$(basename "$APP" .app)
  DMG_DIR="src-tauri/target/release/bundle/dmg"
  mkdir -p "$DMG_DIR"
  DMG_OUT="$DMG_DIR/${APP_NAME}_2.0.0_aarch64.dmg"
  # Create a temporary staging folder with the .app and an Applications symlink
  STAGING=$(mktemp -d)
  cp -r "$APP" "$STAGING/"
  ln -s /Applications "$STAGING/Applications"
  hdiutil create -volname "$APP_NAME" -srcfolder "$STAGING" -ov -format UDZO "$DMG_OUT"
  rm -rf "$STAGING"
  DMG="$DMG_OUT"
  echo "✓ DMG created: $DMG_OUT"
fi

if [[ -n "$DMG" ]]; then
  echo ""
  echo "✓ Build complete!"
  echo "  .dmg → $SCRIPT_DIR/frontend/$DMG"
  echo ""
  echo "  Install: open frontend/$DMG"
else
  echo ""
  echo "✓ Tauri build complete (no .dmg found — check src-tauri/target/release/bundle/)"
fi
