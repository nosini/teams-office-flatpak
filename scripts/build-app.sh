#!/usr/bin/env bash
# Run from the teams-office module's source root inside flatpak-builder.
set -euo pipefail

source_root=$PWD
app_directory=$source_root
if [[ -f scripts/prepare-app.js ]]; then
  node scripts/prepare-app.js
  app_directory=$source_root/build/teams-office
fi
# Older source tags have the app directly at the source root. Keeping this
# path lets existing releases build while the next tag adopts the submodule.

# Install scripts would download Electron and test browsers. Both Electron
# and the native-module headers are already supplied by generated-sources.json.
ln -s "$XDG_CACHE_HOME/node-gyp" "$HOME/.electron-gyp"
# shellcheck source=/dev/null
source "$source_root/flatpak-node/electron-builder-arch-args.sh"
cd "$app_directory"
npm ci --ignore-scripts
# The generated value contains separate flags, e.g. --x64 or --arm64.
# shellcheck disable=SC2086
./node_modules/.bin/electron-builder --linux --dir $ELECTRON_BUILDER_ARCH_ARGS --publish never \
  -c.electronDist="$XDG_CACHE_HOME/electron"
cp -a dist/linux*unpacked "${FLATPAK_DEST}/teams-office"
patch-electron-desktop-filename "${FLATPAK_DEST}/teams-office/resources/app.asar"
install -Dm644 app/assets/icons/icon-256x256.png \
  "${FLATPAK_DEST}/share/icons/hicolor/256x256/apps/${FLATPAK_ID}.png"
