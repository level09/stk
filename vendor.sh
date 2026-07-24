#!/usr/bin/env bash
# Refresh vendored frontend assets. stk has no build step, so these files are
# committed. Bump a version here, run this, then run `uv run quart smoke`.
set -euo pipefail

VUE_VERSION="3.5.40"
VUETIFY_VERSION="3.12.11"
AXIOS_VERSION="1.18.1"
TABLER_VERSION="3.45.0"

cd "$(dirname "$0")"
STATIC="stk/static"
CDN="https://cdn.jsdelivr.net/npm"

fetch() {
  echo "  $2"
  curl -fsSL "$1" -o "$2"
}

echo "vue $VUE_VERSION"
fetch "$CDN/vue@$VUE_VERSION/dist/vue.global.prod.js" "$STATIC/js/vue.min.js"

echo "vuetify $VUETIFY_VERSION"
fetch "$CDN/vuetify@$VUETIFY_VERSION/dist/vuetify.min.js" "$STATIC/js/vuetify.min.js"
fetch "$CDN/vuetify@$VUETIFY_VERSION/dist/vuetify.min.css" "$STATIC/css/vuetify.min.css"

echo "axios $AXIOS_VERSION"
fetch "$CDN/axios@$AXIOS_VERSION/dist/axios.min.js" "$STATIC/js/axios.min.js"

echo "tabler icons $TABLER_VERSION"
mkdir -p "$STATIC/icons/fonts"
fetch "$CDN/@tabler/icons-webfont@$TABLER_VERSION/dist/tabler-icons.min.css" "$STATIC/icons/tabler-icons.min.css"
fetch "$CDN/@tabler/icons-webfont@$TABLER_VERSION/dist/fonts/tabler-icons.woff2" "$STATIC/icons/fonts/tabler-icons.woff2"

# Keep woff2 only; the published stylesheet also lists woff and ttf fallbacks
# that we do not vendor, and a missing font file fails `quart smoke`.
python3 - "$STATIC/icons/tabler-icons.min.css" <<'PY'
import re
import sys

path = sys.argv[1]
css = open(path).read()
css, count = re.subn(
    r'src:url\("\./fonts/tabler-icons\.woff2[^}]*?format\("truetype"\)',
    'src:url("./fonts/tabler-icons.woff2") format("woff2")',
    css,
    count=1,
)
if count != 1:
    raise SystemExit(f"tabler css @font-face changed shape, adjust {path}")
open(path, "w").write(css)
PY

cat > "$STATIC/VERSIONS.txt" <<EOF
vue $VUE_VERSION
vuetify $VUETIFY_VERSION
axios $AXIOS_VERSION
@tabler/icons-webfont $TABLER_VERSION
EOF

echo
echo "Vendored:"
cat "$STATIC/VERSIONS.txt"
echo
echo "Next: uv run quart smoke"
