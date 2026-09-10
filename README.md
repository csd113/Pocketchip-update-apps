# Update Apps for PocketCHIP

Version 1.3.1. Install missing apps and update installed apps from a simple
480 × 272 touchscreen interface. The catalog includes **App Updater (self)** and **Bitcoin CAD**
from [PocketChip-Bitcoin-Display](https://github.com/csd113/PocketChip-Bitcoin-Display).

## Install with one command

Paste this into the PocketCHIP terminal as your normal user (usually `chip`):

```sh
sh -c 'set -e; f=$(mktemp); trap '\''rm -f "$f"'\'' EXIT; curl -fsSL https://raw.githubusercontent.com/csd113/Pocketchip-update-apps/main/install.sh -o "$f"; sh "$f"'
```

Requires internet, `curl`, Python 3.7+ and PocketHome with an Apps page.
The installer downloads files from one pinned GitHub revision. It reuses an
existing app-local Python/Tk runtime, keeping an independent copy for Update
Apps, or installs `python3-tk` through apt (sudo may ask for your password).
On older Debian installations, configured apt repositories must still work.
Run without `sudo` so shortcuts and files belong to your user. Repeating the
command upgrades Update Apps without duplicating its menu entry.

Restart PocketHome (or reboot) after installing to reload its menu. **Update
Apps** is added to PocketHome, `~/Desktop`, and the desktop application menu.

## Use

Open **Update Apps**, tap **Check for updates**, then **Install / update**.
Missing apps appear as **not installed** and are installed by the same button.
New Bitcoin installations include the launcher, icon, and Home/desktop shortcuts.
App Updater (self) identifies the updater in the list and uses the same buttons.
Self-updates run using code already loaded in memory while replacing the files
on disk. Tap Home when finished; the next manual launch loads the new version.
Checking and installing are disabled after a successful self-update.
Restart PocketHome to see newly added Home icons. If an app is running, a touch-friendly prompt offers **Cancel** or **Close and
update**. Confirming sends a termination request and waits up to eight seconds
for the app to stop before installation. Unsaved work may be lost. If it does
not stop, the update is skipped. Apps are never reopened automatically.
Home or Escape exits; C checks and I installs. Internet access is required.

![Update Apps on PocketCHIP (1.0 interface)](docs/update-apps.png)

The updater checks the latest `main` commit even if the version was not bumped.
It downloads the pinned Python source, verifies its Git blob checksum and checks
Python syntax before installing. Existing applications retain their launcher,
icon and runtime. The previous Python source is backed up as
`bitcoin.py.before-update`. A receipt keyed by content records unversioned builds.
New installs validate the Home configuration and file paths before writing,
back up the menu, and roll back files and shortcuts if installation fails.
Menu backups use `~/.pocket-home/config.json.before-app-install-*`.

The catalog is explicit: repositories are not automatically discovered and
repository install scripts are not executed. Bitcoin is currently a standalone
Python/Tk app; future applications or new dependencies require a corresponding
catalog and installation recipe. Self-updates download every file in the explicit updater bundle from one commit,
verify each Git blob checksum, and validate Python syntax before writing. All
previous files are retained in `~/.local/share/pocket-update-apps/before-self-update-*`.
Installation errors roll back replaced files; keep the device powered during
installation. The runtime, receipts, and menu entries stay in place. Rerunning
the command above can also reinstall or upgrade Update Apps.

## Files and validation

- `update_apps.py`: UI, catalog, verified downloads and source updates.
- `deployment.py`: app and shortcut installation with rollback.
- `install.sh`, `install.py`: GitHub bootstrap and repeatable updater installer.
- `launch`, `bitcoin-launch`: runtime-aware launchers.
- `update-apps.png`, `bitcoin.png`: Home icons.
- `test_update_apps.py`, `test_deployment.py`, `test_self_update.py`: update and install failure tests.
- `check_layout.py`: on-device widget bounds checks.

```sh
python3 -m unittest discover -s . -v
python3 -m py_compile update_apps.py deployment.py install.py test_update_apps.py test_deployment.py test_self_update.py
sh -n install.sh launch bitcoin-launch
DISPLAY=:0 python3 check_layout.py
```

For tests on devices using app-local Tk libraries, export the environment shown
in `launch` first.
