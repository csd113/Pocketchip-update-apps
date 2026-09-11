# Update behavior and development

[Back to the project](../README.md)

Bitcoin updates use the versioned JSON catalog at
`https://raw.githubusercontent.com/csd113/Vitrallis-Apps/main/apps.json`.
The fixed local adapter maps `io.vitrallis.bitcoindashboard` to the existing
`~/.local/share/pocket-bitcoin/bitcoin.py` installation and Bitcoin CAD menu name.
No display-name matching or menu migration is needed.

The manager validates catalog format version 1 using the standard library. It
rejects duplicate JSON keys/app IDs/file paths, case collisions, unknown fields,
unsafe paths, unexpected repositories, malformed versions and checksums, and
invalid permission flags. Catalog reads are capped at 8 MiB; app snapshots have
a 16 MiB total limit, 256-file limit, and 2 MiB per-file limit. The Bitcoin adapter
accepts only its reviewed nine-file standalone source layout, Python entry, and
network/storage permission set. New modules or permissions require an adapter
review. Redirects are refused for catalog and app-file requests; HTTPS verification
stays enabled and requests use 20-second socket timeouts. These socket timeouts
are not a guaranteed total transfer deadline. Network work stays off the UI thread.

When `installable` is false, the latest published version is displayed but no app
files are downloaded and installation/repair is blocked. Otherwise Check downloads
all listed files from the published commit under `Apps/Bitcoin-Dashboard`, verifies
their sizes and SHA-256 checksums, compiles Python source without executing it,
and checks that the entry's literal `VERSION` matches the catalog. The reviewed
adapter installs only `bitcoin.py`; the other snapshot files verify the published
bundle and are not installed as commands or runtime helpers. The manager supplies
its own reviewed launcher/icon for first installs and repairs.

Stable `MAJOR.MINOR.PATCH` components compare numerically. Downgrades and replacing
different content with the same version are blocked. Unknown unversioned local
sources are preserved, except the adapter's existing explicitly recognized legacy
hash. Identical source can still repair missing support files or a pending marker.
No stale/offline catalog is used to offer installation, and a failed Bitcoin check
does not prevent the independent updater self-check. Catalog entries without a
local adapter are validated but not added to the UI. New apps require a reviewed
adapter and tests; this change is not a generic package installer.

Existing applications retain their working launcher, icon and runtime. For
source-only updates, the previous Python source is backed up as
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

The remote catalog chooses app versions; the local adapter chooses installation
paths and behavior. Repository install scripts are not executed. Publishing an
app update requires changing the Vitrallis Apps catalog to a new version and
source commit; changing Bitcoin's original repository or `main` alone no longer
publishes an app update. See the [catalog publishing workflow](https://github.com/csd113/Vitrallis-Apps/blob/main/docs/app-catalog.md).

Self-updates continue to check this updater repository's latest `main` commit,
including support-file changes without a version bump. They download every file
in the explicit updater bundle from one commit,
verify each Git blob checksum, and validate Python syntax before writing. All
previous files are retained in `~/.local/share/pocket-update-apps/before-self-update-*`.
Installation errors roll back replaced files; keep the device powered during
installation. The runtime, receipts, and menu entries stay in place. Rerunning
the command above can also reinstall or upgrade Update Apps.

The runtime file list is unchanged in 1.6.0: no new runtime module or dependency
is required, so existing 1.5.x self-updaters and bootstrap file lists can install
the complete new manager. The catalog flag and SHA-256 checks do not constitute
independent signatures; the configured GitHub repository remains the trust root.

## Source files and validation

- `update_apps.py`: UI, catalog validation, local adapters, verified downloads and source updates.
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
