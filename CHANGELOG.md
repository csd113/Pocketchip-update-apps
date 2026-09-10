# Changelog

Changes are listed newest first. Dates use America/Vancouver time.
Versions 1.1.0–1.3.0 were distributed through `main`; they did not have separate
GitHub Releases when this history was added.

## 1.5.2 — 2026-09-10

### Fixed

- Bring the PocketCHIP's local installation-recovery fixes into the shared app.
  Interrupted app/shortcut installs keep a pending marker, and Bitcoin CAD can
  repair missing launchers/icons or a non-executable launcher even when its
  source is already up to date.
- Preserve working custom launchers and icons during repair, and retain the
  PocketHome configuration's existing permissions.
- Bound configuration reads, validate document structure and filenames, and
  reject hardlinked files and unsafe marker paths before installation writes.
- Recheck file contents and permissions before replacement; rollback preserves
  files edited after the installer wrote them.
- Keep the lock-regression timeout focused on the critical operation while
  allowing slower Python/Tk startup on ARM devices.

Normal self-updates remain available in the shared app. The device-specific
manual-update restriction is not part of this release.

## 1.5.1 — 2026-09-10

### Fixed

- Wait until the running-app confirmation dialog is visible before focusing
  Cancel. This prevents the Linux window manager from losing the initial button
  focus and was verified with the full keypad interaction check on PocketCHIP.

## 1.5.0 — 2026-09-10

### Added

- Keypad and keyboard navigation across app rows, Check for updates, Install
  selected, and Home. Up/Down continue from the list to the buttons; Left/Right
  and Tab/Shift+Tab move between controls and skip disabled buttons.
- Enter, keypad Enter, and Space toggle the focused checkbox or activate the
  focused button. Numeric keypad arrows work with Num Lock off.
- A visible row highlight and button focus outline, with the first app focused
  at launch. Moving focus does not check an app for installation.
- Keyboard navigation in the running-app confirmation, starting on Cancel.
  Arrows or Tab choose a button; Enter/Space activate it; Escape/Home cancel.
- Regression tests for navigation, activation, disabled controls, busy operations,
  modal focus, and self-update focus, plus a desktop `--windowed` layout check.

### Changed

- Restore usable keyboard focus when an operation finishes or the updater is
  brought forward, retaining confirmation-dialog focus while a prompt is open.
- Focus Home after a successful self-update so the keypad can close the updater.

## 1.4.1 — 2026-09-09

### Changed

- Added 12 pixels of spacing between checkboxes and app names while keeping
  the table within the 480 × 272 display.

## 1.4.0 — 2026-09-09

### Added

- Per-app checkboxes with touch-row and keyboard selection. Nothing is checked
  automatically; check one app to install or update it independently.
- **Install selected** acts only on checked apps with available changes, including
  the updater itself. Unchecked apps are neither closed nor installed.
- Selection is frozen while an operation is running, and the install button stays
  disabled when no checked app needs an update.

## 1.3.1 — 2026-09-09

### Fixed

- Removed queue operations from the signal handler used to bring an existing
  updater window forward. A simple flag is now handled by the UI event loop,
  avoiding a possible deadlock when tapping the Home-menu icon again.
- Added a regression test that requests the window while the event queue is locked.

[Implementation](https://github.com/csd113/Pocketchip-update-apps/commit/8cf08ea)

## 1.3.0 — 2026-09-09

### Added

- A touchscreen **Cancel / Close and update** prompt for running apps.
- Confirmed apps receive a termination request; installation waits up to eight
  seconds for them to stop. An app that does not stop is skipped, and updated
  apps are not reopened automatically.
- Process matching checks the user, Python script path, and process start time
  before sending the termination request.

### Changed

- Renamed the updater's list entry to **App Updater (self)**.
- Clarified that self-updates use code already loaded in memory; tap Home when
  finished and manually launch the updater when needed.

### Fixed

- Removed cached Python bytecode during self-updates so a same-size source
  replacement within one second cannot load stale code on the next launch.

[Implementation](https://github.com/csd113/Pocketchip-update-apps/commit/1bb7330)

## 1.2.0 — 2026-09-09

### Added

- Update Apps itself appears in the app list and can check for and install updates.
- Self-updates fetch the full explicit bundle from one GitHub commit, verify each
  file's Git blob checksum, and validate Python syntax before replacing files.
- Backups of the previous updater files and rollback on installation errors.
- Further checks and installs are disabled after a successful self-update until
  the updater is closed and launched again.

[Implementation](https://github.com/csd113/Pocketchip-update-apps/commit/ec00348)

## 1.1.0 — 2026-09-09

### Added

- Installation of missing Bitcoin CAD apps through the same update button,
  including a launcher, icon, PocketHome entry, and desktop shortcuts.
- A single-command GitHub installer for Update Apps, repeatable for upgrades
  without duplicate menu entries.
- An independent copy of the existing app-local Python/Tk runtime, or installation
  of system Tk through apt when no usable runtime is available.
- Validation and rollback for app files and shortcuts, plus menu backups.

### Changed

- Renamed the install button to **Install / update** and show missing apps as
  **not installed**.

[Implementation](https://github.com/csd113/Pocketchip-update-apps/commit/27fc9c6)

## 1.0.0 — 2026-09-09

### Added

- Initial 480 × 272 Python/Tkinter updater with a Bitcoin CAD catalog entry,
  installed/latest version columns, and Check and Install buttons.
- Commit-pinned GitHub downloads, Git blob checksum verification, Python syntax
  checks, atomic source replacement, and an original-source backup.
- Semantic version detection, revision fallback, content-keyed receipts, and
  checks for locally changed or running apps before updating.
- Background work, single-instance locking, Home/Escape exit, C/I shortcuts,
  an app-local runtime launcher, and PocketHome installation.

[Implementation](https://github.com/csd113/Pocketchip-update-apps/commit/dda21fb)
