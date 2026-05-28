#!/usr/bin/env bash
# Re-derive the 10 trivia illustrations from the PDF source.
# Run from repo root: bash scripts/extract_trivia_images.sh
#
# Requires: pdftoppm (poppler-utils) + either ImageMagick OR Python 3 with Pillow
#
# Output goes to campaigns/themes/futboleros/assets/trivia/ (the tracked source
# directory). The runtime copy at /themes/ is gitignored and populated by
# themes_setup.py / the setup_default_theme management command.
set -euo pipefail

PDF="${PDF:-/home/elgran/Downloads/NUBE BLANCA ROSAL PROMO MUNDIAL.pdf}"
OUT="campaigns/themes/futboleros/assets/trivia"
TMP="$(mktemp -d)"
trap "rm -rf $TMP" EXIT

mkdir -p "$OUT"

# Render slides 30-37 at 200 DPI.
pdftoppm -png -r 200 -f 30 -l 37 "$PDF" "$TMP/slide"

# The illustration tile sits inside the white card on the right of each slide.
# At 200 DPI the page is 2000x1125 px (measured). The tile is roughly:
#   x=1278  y=578  w=224  h=160  (right edge at x=1502, bottom at y=738)
# These coordinates were verified against slides 30-37; all share the layout.

crop_tile() {
  local src="$1" dst="$2"
  if command -v convert &>/dev/null; then
    # ImageMagick path
    convert "$src" -crop "224x160+1278+578" +repage "$dst"
  else
    # Python/Pillow fallback
    python3 - "$src" "$dst" <<'PYEOF'
import sys
from PIL import Image
img = Image.open(sys.argv[1])
tile = img.crop((1278, 578, 1502, 738))
tile.save(sys.argv[2])
PYEOF
  fi
}

for n in 30 31 32 33 34 35 36 37; do
  crop_tile "$TMP/slide-${n}.png" "$TMP/tile-${n}.png"
done

# Map slide -> question number (some slides serve two questions).
cp "$TMP/tile-31.png" "$OUT/q1.png"    # USA map
cp "$TMP/tile-30.png" "$OUT/q2.png"    # crowd / fans
cp "$TMP/tile-31.png" "$OUT/q3.png"    # USA map (reused)
cp "$TMP/tile-32.png" "$OUT/q4.png"    # Obelisco Buenos Aires
cp "$TMP/tile-34.png" "$OUT/q5.png"    # stadium seats
cp "$TMP/tile-31.png" "$OUT/q6.png"    # USA map (reused)
cp "$TMP/tile-35.png" "$OUT/q7.png"    # player + ball
cp "$TMP/tile-32.png" "$OUT/q8.png"    # Obelisco Buenos Aires (reused)
cp "$TMP/tile-33.png" "$OUT/q9.png"    # Angel de la Independencia (Mexico City)
cp "$TMP/tile-36.png" "$OUT/q10.png"   # team photo (blue shirts)

# Fallback: q2 (crowd) is the most generic; reuse it.
cp "$OUT/q2.png" "$OUT/fallback.png"

echo "Wrote $(ls "$OUT" | wc -l) files into $OUT"
