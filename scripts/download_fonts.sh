#!/usr/bin/env bash
# scripts/download_fonts.sh
# Downloads OFL-licensed Google Fonts for the poster renderer.
# Run this during Docker build or Railway/Render pre-deploy step.
set -e

FONTS_DIR="$(dirname "$0")/../fonts"
mkdir -p "$FONTS_DIR"

BASE="https://github.com/google/fonts/raw/main/ofl"

download_font() {
  local url="$1"
  local dest="$2"
  if [ ! -f "$dest" ]; then
    echo "⬇️  Downloading $(basename $dest)..."
    curl -fsSL "$url" -o "$dest"
  else
    echo "✅  $(basename $dest) already exists"
  fi
}

download_font "$BASE/poppins/Poppins-Regular.ttf"   "$FONTS_DIR/Poppins-Regular.ttf"
download_font "$BASE/poppins/Poppins-SemiBold.ttf"  "$FONTS_DIR/Poppins-SemiBold.ttf"
download_font "$BASE/poppins/Poppins-Bold.ttf"      "$FONTS_DIR/Poppins-Bold.ttf"
download_font "$BASE/inter/Inter-Regular.ttf"       "$FONTS_DIR/Inter-Regular.ttf"
download_font "$BASE/inter/Inter-SemiBold.ttf"      "$FONTS_DIR/Inter-SemiBold.ttf"

echo "✅  All fonts ready in $FONTS_DIR"
