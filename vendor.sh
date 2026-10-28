#!/usr/bin/env bash
# Refresh vendored frontend assets. stk has no build step, so these files are
# committed. Bump a version here, run this, then run `uv run quart smoke`.
set -euo pipefail

VUE_VERSION="3.5.44"
VUETIFY_VERSION="4.3.1"
AXIOS_VERSION="1.21.0"
TABLER_VERSION="3.50.0"

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
rm -rf "$STATIC/icons/fonts" && mkdir -p "$STATIC/icons/fonts"
fetch "$CDN/@tabler/icons-webfont@$TABLER_VERSION/dist/tabler-icons.min.css" "$STATIC/icons/tabler-icons.min.css"
# Since 3.50 the font ships as unicode-range subsets; fetch every file the
# stylesheet references so a missing font cannot fail `stk smoke`.
for font in $(grep -o '\./fonts/[^"?)]*' "$STATIC/icons/tabler-icons.min.css" | sort -u); do
  fetch "$CDN/@tabler/icons-webfont@$TABLER_VERSION/dist/${font#./}" "$STATIC/icons/${font#./}"
done

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
