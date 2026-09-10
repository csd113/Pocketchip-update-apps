# Update behavior and development

[Back to the project](../README.md)

The updater checks the latest `main` commit even if the version was not bumped.
It downloads the pinned Python source, verifies its Git blob checksum and checks
Python syntax before installing. Existing applications retain their working
launcher, icon and runtime. For source-only updates, the previous Python source is backed up as
`bitcoin.py.before-update`. A receipt keyed by content records unversioned builds.
New installs validate the Home configuration and file paths before writing,
back up the menu, and roll back files and shortcuts if installation fails.
Menu backups use `~/.pocket-home/config.json.before-app-install-*`.

App and shortcut installations write `.installation-pending` in the app directory
before replacing files and remove it only after all writes succeed. Bitcoin CAD
shows `incomplete / repair` while this marker exists, or when its launcher or icon
is missing or its launcher is not executable. Check for updates and install the
selected app to repair it, including when the Python source is already current.
Repair preserves existing working launchers and icons. Failed installations keep
the marker so an interrupted or partially rolled-back install stays visible.

PocketHome configuration reads are capped at 1 MiB and its document structure is
validated before writing. The installer rejects unsafe paths, hardlinked files,
invalid labels and unsafe marker files, and preserves the menu's existing file
permissions. Each target's contents and permissions are rechecked before replacement.
Rollback restores only files that still match what this installation wrote,
preserving later edits instead of overwriting them.

The catalog is explicit: repositories are not automatically discovered and
repository install scripts are not executed. Bitcoin is currently a standalone
Python/Tk app; future applications or new dependencies require a corresponding
catalog and installation recipe. Self-updates download every file in the explicit updater bundle from one commit,
verify each Git blob checksum, and validate Python syntax before writing. All
previous files are retained in `~/.local/share/pocket-update-apps/before-self-update-*`.
Installation errors roll back replaced files; keep the device powered during
installation. The runtime, receipts, and menu entries stay in place. Rerunning
the command above can also reinstall or upgrade Update Apps.

## Source files and validation

- `update_apps.py`: UI, catalog, verified downloads and source updates.
- `deployment.py`: app and shortcut installation with rollback.
- `install.sh`, `install.py`: GitHub bootstrap and repeatable updater installer.
- `launch`, `bitcoin-launch`: runtime-aware launchers.
- `update-apps.png`, `bitcoin.png`: Home icons.
- `test_update_apps.py`, `test_deployment.py`, `test_self_update.py`: navigation, update, and install failure tests.
- `check_layout.py`: widget bounds and touch/keyboard/keypad interaction checks.

```sh
python3 -m unittest discover -s . -v
python3 -m py_compile update_apps.py deployment.py install.py test_update_apps.py test_deployment.py test_self_update.py check_layout.py
sh -n install.sh launch bitcoin-launch
DISPLAY=:0 python3 check_layout.py
```

For tests on devices using app-local Tk libraries, export the environment shown
in `launch` first.

On a desktop, use `python3 check_layout.py --windowed` to test a 480 × 272 window
without entering fullscreen. The interaction checks simulate button presses and
confirmation choices without downloading, installing, or closing applications.
On macOS, Tk cannot synthesize keypad-arrow events, so this check verifies those
bindings and exercises ordinary arrow events; unit tests cover the keypad
callbacks. Run the fullscreen check on PocketCHIP for device verification.

## Making changes

Keep the 480 × 272 interface usable on PocketCHIP and preserve existing app
paths and PocketHome entries. The download and install lists in `update_apps.py`,
`install.py`, and `install.sh` must stay compatible. Test update failures, backups,
and self-updates when changing installation behavior.

For a release, update `VERSION` and the changelog, run the checks above, and
verify the interface on the device. GitHub release tags use `vMAJOR.MINOR.PATCH`.

The shared app retains normal self-updates. Earlier device-specific builds that
display `App Updater (manual)` disabled them to protect local fixes. Those builds
need a manual reinstall to return to the shared app; v1.5.2 includes the recovery
and validation fixes that previously required that local patch.
