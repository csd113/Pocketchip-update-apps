#!/bin/sh
# Run as the normal PocketCHIP user, not with sudo.
set -eu
if [ "$(id -u)" = 0 ]; then
    echo 'Run this installer as your normal PocketCHIP user, without sudo.' >&2
    exit 1
fi
command -v python3 >/dev/null
command -v curl >/dev/null
STAGE=$(mktemp -d)
trap 'rm -rf "$STAGE"' EXIT HUP INT TERM
BASE=https://raw.githubusercontent.com/csd113/Pocketchip-update-apps
curl -fsSL --retry 3 https://api.github.com/repos/csd113/Pocketchip-update-apps/commits/main -o "$STAGE/commit.json"
REV=$(python3 -c 'import json,re,sys; s=json.load(open(sys.argv[1]))["sha"]; assert re.fullmatch("[0-9a-f]{40}",s); print(s)' "$STAGE/commit.json")
for FILE in update_apps.py deployment.py launch update-apps.png bitcoin-launch bitcoin.png install.py test_update_apps.py test_deployment.py check_layout.py README.md; do
    curl -fsSL --retry 3 "$BASE/$REV/$FILE" -o "$STAGE/$FILE"
done
for RUNTIME in "$HOME/.local/share/pocket-update-apps/runtime/usr" "$HOME/.local/share/pocket-bitcoin/runtime/usr"; do
    if [ -d "$RUNTIME" ]; then
        export LD_LIBRARY_PATH="$RUNTIME/lib/arm-linux-gnueabihf"
        export PYTHONPATH="$RUNTIME/lib/python3.13:$RUNTIME/lib/python3.13/lib-dynload"
        export TCL_LIBRARY="$RUNTIME/share/tcltk/tcl8.6"
        export TK_LIBRARY="$RUNTIME/share/tcltk/tk8.6"
        break
    fi
done
if ! python3 -c 'import tkinter' 2>/dev/null; then
    echo 'Installing the Python Tk dependency (sudo may ask for your password).'
    sudo apt-get update
    sudo apt-get install -y python3-tk
fi
python3 -c 'import tkinter'
python3 "$STAGE/install.py"
