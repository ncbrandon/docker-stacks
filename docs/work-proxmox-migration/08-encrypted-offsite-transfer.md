# Encrypted off-host transfer (work)
Status: **Script committed, not yet installed or run**. Script: [scripts/offsite-work-backups.sh](../../scripts/offsite-work-backups.sh).

Existing local cron remains unchanged (SQL 03:00, Manhole 03:15, MeshCentral 03:30). Once tested, add **separate** off-host cron job at **04:00 Eastern**:
```
0 4 * * * /home/brandon/offsite-work-backups.sh >> /home/brandon/backup-logs/offsite-work-backups.log 2>&1
```
It only uploads backups generated on the current local calendar day; it refuses stale data, checks MeshCentral SHA256 manifest, copies to `nas-crypt:manhole-survey/` and `nas-crypt:meshcentral/`, and checks remote decrypted content by downloading and comparing bytes. It does not change the SQL backup or local jobs.

**Before use:** `nas-crypt:` must be verified as type `crypt` wrapping `nas:NetBackup/wj-encrypted-backups` with data encryption enabled. The rclone config and credentials are secrets, **not** GitHub files. Verify the raw SMB folder contains encrypted/obfuscated filenames and file contents. Existing successful test: user uploaded a harmless test file via `nas-crypt:` and read back original plaintext via same remote on 2026-10-22.

Installation, after reviewing the script:
```bash
curl -fL https://raw.githubusercontent.com/ncbrandon/docker-stacks/main/scripts/offsite-work-backups.sh -o /home/brandon/offsite-work-backups.sh
chmod 700 /home/brandon/offsite-work-backups.sh
/home/brandon/offsite-work-backups.sh
```
The script mounts the existing host rclone config read-only into the `rclone/rclone:latest` container (no host rclone package needed), along with the two source folders as read-only mounts. It uses `rclone check --download` to avoid crypt backend hash limitations and does not delete remote data.

IMPORTANT: Remote 30-day cleanup is **not enabled**, pending recovery validation and safe deletion scope review. Preserve a recovery-tested historical snapshot. Verify source ZIP includes all manhole database/uploads and application source separately. Confirm MeshCentral starts and agents reconnect after local backup. Back up encryption credentials securely outside the same host and NAS.

NOTE: Script expects the last scheduled daily MeshCentral folder and daily manhole ZIP. Run on same day after both completed. On manual test Oct 22 MeshCentral has folder `20261022-124305` and manhole has `manhole-backup-2026-10-22_03-15-01.zip`. `--download` verification can consume network bandwidth.

## First verified production off-host transfer — 2026-10-22
User executed `/home/brandon/offsite-work-backups.sh` on work VM. Output confirmed `SHA256SUMS` successful for four MeshCentral tarballs, encrypted remote upload of `manhole-backup-2026-10-22_03-15-01.zip` and MeshCentral directory `20261022-124305`, followed by `rclone check --download`: **Manhole Survey 1 matching file, zero differences; MeshCentral 6 matching files, zero differences**. Script reported SUCCESS.

The 04:00 cron entry **has not yet been confirmed installed**. Remote retention and independent Proxmox restore test still pending. Verify encryption backend configuration/credentials stored securely outside server.
