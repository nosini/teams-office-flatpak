#!/usr/bin/env bash
# Regenerate generated-sources.json, the npm packages and Electron downloads
# of the teams-office module, from the package-lock.json of the commit the
# manifest pins. Run it after changing that commit.
#
# LOCKFILE=path/to/package-lock.json uses a local lockfile instead, for a
# commit that hasn't been pushed yet.
set -euo pipefail
cd "$(dirname "$0")/.."

manifest=eu.nosini.TeamsOffice.yml
output=generated-sources.json
venv=.cache/node-generator
tools=$(bash scripts/builder-tools.sh)

# flatpak-node-generator from the pinned flatpak-builder-tools, in its own
# virtual environment. It needs aiohttp and PyYAML.
if [[ ! -x "$venv/bin/flatpak-node-generator" || "$(cat "$venv/tools-commit" 2>/dev/null)" != "$(git -C "$tools" rev-parse HEAD)" ]]; then
  rm -rf "$venv"
  python3 -m venv "$venv"
  "$venv/bin/pip" install --quiet "$tools/node"
  git -C "$tools" rev-parse HEAD > "$venv/tools-commit"
fi

work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT

if [[ -n "${LOCKFILE:-}" ]]; then
  cp "$LOCKFILE" "$work/package-lock.json"
else
  read -r url commit < <("$venv/bin/python" - "$manifest" <<'EOF'
import sys, yaml
manifest = yaml.safe_load(open(sys.argv[1]))
module = next(m for m in manifest["modules"] if m["name"] == "teams-office")
source = module["sources"][0]
print(source["url"], source["commit"])
EOF
  )
  git init -q "$work/source"
  git -C "$work/source" fetch -q --depth=1 "$url" "$commit"
  git -C "$work/source" show FETCH_HEAD:package-lock.json > "$work/package-lock.json"
fi

# Electron's headers let electron-builder compile native modules offline.
"$venv/bin/flatpak-node-generator" npm --electron-node-headers \
  "$work/package-lock.json" -o "$work/$output"

# The lockfile includes Playwright for upstream's end-to-end tests. Its
# browsers are only downloaded by install scripts, which the build skips, so
# leave out the several hundred megabytes of browser archives.
"$venv/bin/python" - "$work/$output" "$output" <<'EOF'
import json, sys
sources = json.load(open(sys.argv[1]))
kept = [s for s in sources
        if not s.get("dest", "").startswith("flatpak-node/cache/ms-playwright/")]
with open(sys.argv[2], "w") as f:
    json.dump(kept, f, indent=4)
    f.write("\n")
print(f"Wrote {len(kept)} sources to {sys.argv[2]}, "
      f"leaving out {len(sources) - len(kept)} Playwright browser downloads.")
EOF
