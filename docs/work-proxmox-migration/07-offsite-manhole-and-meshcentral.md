# 07 — Off-host backup plan: Manhole Survey and MeshCentral

Status: **pending rclone remote encryption verification and live path audit**. This document records the plan; do not claim that NAS copies exist until remote copies and recovery are tested.

## Existing work schedules (confirmed from user crontab)
- 03:00 Eastern: `docker start -a sql-backup` with logs in `/home/brandon/sql-backups/cron.log`.
- 03:15 Eastern: `/usr/bin/python3 /home/brandon/backup_manhole.py`, logs in `/home/brandon/manhole-backup.log`.
- 03:30 Eastern: `/home/brandon/backup-meshcentral-work.sh`, logs in `/home/brandon/meshcentral-backups/backup.log`.

Do **not** replace these jobs or add a second manhole backup without checking the existing script and its destinations.

## Required recovery data
### Manhole Survey
- Live SQLite and uploads: `/home/brandon/manhole-survey/storage` -> Docker `/app/storage`.
- Complete current application source, Dockerfile, Compose, image provenance, PDF/export templates, GIS imports; running image recorded as `manhole-survey:1.3`.
- Existing backup script `/home/brandon/backup_manhole.py`; verify whether its ZIP captures SQLite **consistently** and includes attachments, and determine its actual output path and retention before relying on it.
- Cloudflare Access route and policy; cron, secrets/credentials kept outside GitHub.

### MeshCentral
- Four Docker volumes, verified manually archived and checksummed 2026-10-22; see [MeshCentral backup guide](06-meshcentral-backup-restore.md).
- Preserve CA/server identity private keys, database/accounts and MFA material in encrypted remote storage.

## Off-host backup requirements
1. Existing `nas:` rclone remote was used previously for SQL backup. **Do not assume `nas:` is encrypted.** `rclone listremotes` shows aliases but does not prove backend type or encryption.
2. Use an existing verified rclone **crypt** remote over NAS, or set up a new `crypt` remote which points to a separate folder on `nas:`. Never commit or paste crypt passwords, salt, tokens, or rclone configuration into GitHub.
3. Once the crypt remote is verified, send *complete successful* MeshCentral backup folders, including archives and `SHA256SUMS`, and complete manhole backup ZIPs; include application source backups separately.
4. Use a durable synchronization method with logging and failure reporting; do **not** delete remote copies before confirming the new backup uploaded and passed checks.
5. Verify transfer using `rclone check` against source and remote where supported. Test download to a separate location and archive checksums. For manhole ZIP also test `unzip -t` and inspect SQLite integrity after a controlled restore.
6. Retention goal: 30 days. Implement remote retention with a **narrow, dedicated backup prefix**, after proving the rules cannot delete SQL or unrelated data. Retain a known-good recovery snapshot in an independent location.
7. Since SQL starts at 03:00, manhole at 03:15, MeshCentral at 03:30, any copy process must run **after successful local backups** and should not interfere with database consistency; don't assume fixed duration.
8. Backups remain **not disaster-recovery verified** until complete Proxmox restore tests succeed.

## Next safe source-machine checks
Run and share **only these summaries**, not rclone config secrets:
```bash
rclone listremotes
ls -ld /home/brandon/manhole-survey/storage /home/brandon/meshcentral-backups /home/brandon/.config/rclone
find /home/brandon -maxdepth 5 -type f \( -iname '*manhole*.zip' -o -iname '*manhole*.bak' \) -printf '%TY-%Tm-%Td %TH:%TM %s %p\n' 2>/dev/null | sort -r | head -20
grep -nE 'backup|zip|retention|destination|output|days' /home/brandon/backup_manhole.py | head -60
```
Review results before writing any NAS-transfer cron jobs. The `grep` may display destination paths but should not be used if the script contains hard-coded secrets.
