#!/usr/bin/env sh
set -eu
repository_root=$(CDPATH= cd -- "$(dirname -- "$0")/../../.." && pwd)
plugin_path=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
python -m pip install -e "$repository_root"
codex plugin install --dev "$plugin_path"
