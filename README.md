# Update Apps for PocketCHIP

A 480 × 272 Python/Tkinter app, version 1.0.0. Open **Update Apps** on PocketHome,
tap **Check for updates**, then **Install updates** when an update is available.
Close Bitcoin CAD before installing. Home or Escape exits. C checks; I installs.
The device needs internet access (normally Wi-Fi) to reach GitHub.

![Update Apps on PocketCHIP](docs/update-apps.png)

The initial catalog contains Bitcoin CAD from
https://github.com/csd113/PocketChip-Bitcoin-Display, tracking `main`.
Versions are read from the literal `VERSION` constant in the app source
(e.g. `v1.0.0`), with eight-character Git revision IDs for older unversioned builds.
The latest `main` commit is checked even if a publisher forgets to bump the version. Updates fetch the latest commit, download its pinned `bitcoin.py`,
verify the Git blob checksum, and check Python syntax before installation.
An unknown or locally edited installation is labelled `local / unknown`.
Installing replaces that source after retaining a backup.

Only the standalone application source is updated. The existing Bitcoin
launcher, icon, runtime, tests, and other files stay in place. A future version
that introduces additional required files or dependencies needs an updater
catalog/installer change; this updater does not execute repository install scripts.
Add future compatible single-file apps explicitly in `APPS` in `update_apps.py`.

Updates run in a background thread. The complete executable is replaced by one
atomic rename, after writing and syncing a backup to
`~/.local/share/pocket-bitcoin/bitcoin.py.before-update`. A content-keyed version
receipt prevents an interrupted install from showing an incorrect version.
A process lock prevents concurrent updater instances. No service, polling job,
pip package, or new runtime is installed. The launcher reuses the existing
Bitcoin app's Python/Tcl/Tk library environment.

## Files

- `update_apps.py`: interface, catalog, verified download and atomic installation.
- `launch`: launcher using the device's existing runtime.
- `update-apps.png`: home menu icon.
- `install.py`: initial on-device installation; backs up the PocketHome menu and
  refuses to overwrite an existing updater directory.
- `test_update_apps.py`: twelve update and failure-path tests.
- `check_layout.py`: on-device 480 × 272 widget bounds and button-state checks.

## Validation

```
python3 -m unittest discover -s . -v
python3 -m py_compile update_apps.py install.py test_update_apps.py
sh -n launch
DISPLAY=:0 python3 check_layout.py
```

On a device with app-local Tk libraries, use the environment exported in `launch`
when running these commands. To install from a copied source directory, run
`python3 install.py` in that same environment, then restart PocketHome so it
reloads its configuration. No reboot is needed.

Validated on PocketCHIP: all 12 updater tests and the layout smoke check passed.
The on-device Check and Install buttons upgraded Bitcoin from its unversioned
build to v1.0.0, with matching source hashes and a verified original-file backup.
The running-app guard and returning to an existing updater window were checked.
