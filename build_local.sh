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
"$PYINSTALLER" backend/backend.spec --distpath dist-backend --noconfirm

SIDECAR_OUT="frontend/src-tauri/binaries/backend-$TARGET"
echo "→ Copying sidecar to $SIDECAR_OUT"
mkdir -p frontend/src-tauri/binaries
cp dist-backend/backend "$SIDECAR_OUT"
chmod +x "$SIDECAR_OUT"

# ── Step 2: Build Tauri app ──────────────────────────────────────────────────
echo "→ Building Tauri app..."
cd frontend
npm run tauri build

# ── Done ─────────────────────────────────────────────────────────────────────
DMG=$(find src-tauri/target/release/bundle/dmg -name "*.dmg" 2>/dev/null | head -1)
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
