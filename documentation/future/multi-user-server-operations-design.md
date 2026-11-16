# Multi-user server: operations (Phase 6 design)

Status: draft (built on branch claude/multi-user-phase-6-operations-f5081b, not merged)
Date: 2026-11-16

Implements "Phase 6 - Operations" of `multi-user-server-plan.md`. All new code is in new files
(`src/funnel_guard.py`, `src/gateway/backup_crypto.py`, `backup_dest.py`, `backup_store.py`, `health.py`,
`logs.py`, `power.py`, `migrate_all.py`, `ops.py`); the edits to existing files are small wiring changes in
`src/gateway/server.py` and `src/gateway/app.py`. The operator steps are in
`multi-user-server-operations-runbook.md`; the open measurements in `multi-user-server-operations-measurements.md`.

## Backup format and key handling

**Primitive.** The standard library has no authenticated cipher. `cryptography` was already installed on the
dev machine (it was not in `requirements.txt`, which lists only what the app imports), so this phase adds
`cryptography>=42,<46` to `requirements.txt` and uses `AESGCM` and `HKDF`. Hand-built HMAC-over-stream ciphers
were rejected: the library is widely reviewed and the dependency is pure wheels on Windows.

**Archive** (`<UTC stamp>.rpbak`, one file per set):

```
"RPBK" | version 1 | key id (8 bytes) | salt (16) | nonce prefix (4) | chunk size u32
then repeated: ciphertext length u32 | AES-256-GCM ciphertext of one chunk
```

* The per-archive data key is `HKDF-SHA256(master key, salt)`, so no two archives share a key.
* Each chunk's nonce is the 4-byte prefix plus the chunk counter; its authenticated data is the header, the
  counter and a "final chunk" flag. A reordered, dropped, duplicated, flipped or truncated chunk fails
  authentication, and an archive without a final chunk is "truncated".
* The plaintext is a tar stream written straight into the encryptor, so no plaintext copy of any plan ever
  reaches the disk. Each SQLite file is copied with the backup API into memory (consistent while a worker is
  writing), then added to the tar.
* Members: `users/<id>/plan.rpx`, `users/<id>/app.db`, `gateway.db`, `manifest.json` (last).
* After writing, the archive is read back and fully verified before it is renamed from `.partial`, so a set that
  cannot be restored is never reported as a success.
* Errors are typed: `WrongKeyError` (header key id differs: wrong or missing key) and `CorruptBackupError`
  (damage or tampering). Restore refuses on either and changes nothing.

**Key.** A 32-byte random key in a file (`backup.key`, base64 text) created by `ops backup-key create`, which
refuses to overwrite and refuses a location inside the backup destination, the data root, the install folder or
a synced folder. The key is never in the backup folder, the gateway config, the database or a log. In per-account
mode the key file is locked to the gateway account. **The owner must copy the key offline** (the runbook says
where): without it every archive is unreadable, and a backup folder copied elsewhere is useless to a thief.
Key rotation: create a new key, run a backup, keep the old key for as long as old archives are retained.

**Destination.** `--backup-dir` (default `%ProgramData%\RetirementPlannerGateway\backups`) is a server-side path
set only in the service config file, which only a Windows administrator can write; there is no web route that
sets it, so "admin-only" holds by construction. `validate_backup_destination` is the same confinement review as
other stored paths: absolute, no `..`, no UNC share, not a drive root, symlinks and junctions resolved, and refused
when inside the data root, the install folder, any user profile folder, or a OneDrive, Dropbox, Google Drive,
iCloud or Box tree (environment roots and folder-name markers). It runs at gateway start (refused with exit 2) and
in `ops`. Backups are enabled by giving `--backup-key-file`; `--backup-dir` alone is refused (no unencrypted
backups from the gateway).

**Retention.** `--backup-keep N` complete sets (default 14). Per-user snapshots taken before a deletion or a
migration (`<stamp>.user<ID>.rpbak`) are kept at most N per user.

**Restore.** `ops restore --archive A --user ID` verifies the whole archive, extracts only the allow-listed names
for that user into a staging folder on the same volume, moves the user's current files aside
(`*.before-restore-<stamp>`), and swaps the restored ones in. Other users' files are never opened for writing.
It refuses while that user's worker is running. `gateway.db` is restored to a new file (`--gateway-db-out`), never
over the live one: swap it with the service stopped.

## Health endpoint access rule

`GET /api/auth/admin/health`: **signed-in gateway admin only** (the existing admin gate, which also requires
the second factor). Loopback-only was rejected because Funnel delivers every internet request from 127.0.0.1 and
every worker, which belongs to a mutually untrusted user, can also reach 127.0.0.1; "from loopback" proves
nothing. Unauthenticated is out. The payload carries status, uptime, schema version, running worker count, build
queue (running, waiting), free space and total on the data and backup volumes, the last backup result (time,
users, errors, newest archive age) and a `warnings` list (low disk, stale or failed backup, no backups
configured). It names no paths other than volume labels and carries no user data. For monitoring without a
browser, `ops health` prints the same disk and backup figures from the server.

## Migrate-all flow (offline)

`ops migrate-all --data-root D --gateway-db G --backup-dir B --key-file K` (gateway service stopped):

1. For every user folder: refuse that user if a live worker owns it; write a per-user encrypted snapshot
   (`premigrate`). A failed snapshot skips the user's migration and reports it.
2. Run the migration in a child process with the workspace pinned in the environment (`src/remote_worker`'s
   pinning; the workspace is cached at import so a fresh process per user is required): open the plan file (schema
   migration) and run `migrate_plan_data_at_rest`, whose error dict is reported instead of swallowed.
3. Report per user (`ok`, `failed`, `skipped`, details, snapshot name) to the console and a JSON report file;
   exit 1 if any user failed. Failure of one user never stops the others.
4. `gateway.db` migrates when `GatewayStore` opens it; the command does that and reports the schema version.

**Rollback:** stop the service, `ops restore --archive <premigrate snapshot> --user ID` for each affected user,
check out the previous release, start the service. Tested with a fixture user (migrate, damage, restore, bytes
equal to the snapshot).

## Other pieces

* **Funnel guard** (`src/funnel_guard.py`): parses `tailscale serve status --json` properly (not a regex) and
  enforces a whitelist: external 8443 or 10000 may target only the gateway's Funnel port; external 443 only the
  reporter's remote port 5058; nothing may target 5057, the gateway's local port or any worker port. The reporter's
  `check_funnel_target` and its tests are unchanged; the shared module is additive. `ops funnel apply` prints
  the exact command and runs it only with `--yes`; it never runs `tailscale funnel reset` (that would remove the
  reporter's 443 entry).
* **Service wrapper**: confirmed in `service.py`: failure actions restart the service three times, 10 s apart,
  with the failure counter reset after 24 h; start type automatic; the gateway log rotates at 5 MB x 5.
* **No-sleep policy** (`power.py`): `ops power show|apply --yes|revert`; sets AC standby and hibernate timeouts
  to never, remembers the previous values in a file so `revert` restores them. Applied only on the owner's yes.
* **Log rotation**: the gateway log and the worker's `app.log` already rotate; the worker console log is replaced
  at each worker start but can grow inside one long run, so the gateway truncates an idle user's oversized console
  log and removes stale rotated copies (`logs.py`, hourly, never touching a running worker's open file).
* **Mandatory TOTP**: built in Phase 2; verified by the existing gateway functional tests and by the end-to-end
  run recorded in the measurements note (no rebuild here).
