# Changelog

Changes are listed newest first. Dates use America/Vancouver time.
Versions 1.1.0–1.3.0 were distributed through `main`; they did not have separate
GitHub Releases when this history was added.

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
