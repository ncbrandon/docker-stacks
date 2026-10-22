# Work MeshCentral backup and Proxmox recovery

This is a **reproducible backup procedure**, not proof a live backup was made. See [05 MeshCentral work](05-meshcentral-work.md) for the installed Portainer Compose.

## Instructions

1. Copy [backup-meshcentral-work.sh](../../scripts/backup-meshcentral-work.sh) to `/home/brandon/backup-meshcentral-work.sh` on the old **work** Docker VM. Set executable bit: `chmod 700 /home/brandon/backup-meshcentral-work.sh`.
2. **Run one attended test**: `/home/brandon/backup-meshcentral-work.sh`. This briefly stops `meshcentral-work`, archives all **four actual named Docker volumes**, then restarts it if previously running.
3. Check output; verify directory and hashes: `ls -ld /home/brandon/meshcentral-backups/*/` then `cd /home/brandon/meshcentral-backups/DATE-FOLDER && sha256sum -c SHA256SUMS`.
4. Check `docker ps --filter name=meshcentral-work`, log in at `https://remote.wjwater.org`, and test an existing agent after the script returns.
5. **Only after success**, add `30 3 * * * /home/brandon/backup-meshcentral-work.sh >> /home/brandon/meshcentral-backups/backup.log 2>&1` to the work user's crontab via `crontab -e`. This is after the existing 03:00 SQL backup and 03:15 manhole backup.
6. Back up the entire `/home/brandon/meshcentral-backups` directory to an **encrypted off-host destination** (existing `nas:` rclone remote is a possible target, but first verify destination, encryption and credentials). Local archives alone **will not protect against host/disk failure**. Keep at least one restore-tested off-host copy.

### Cautions
- This script stops remote access briefly: schedule outside business hours.
- The automatic local retention removes old dated backup directories after more than 30 days; this is **not** a verified retention policy on the remote backup.
- This is for the named-volume embedded DB setup shown in current Compose. If an external SQL/MongoDB service is added later, a database-native consistent backup becomes necessary.
- Archives contain **MeshCentral private keys, certificates, MFA-related account database**. Store encrypted off-host; keep host backup directory private; never upload raw archives to GitHub.
- Backup script uses a small temporary Alpine container (`alpine:3.20`). Ensure Docker can pull its image first; script is intentionally not configured to pull secrets.
- Crash consistency is obtained by stopping MeshCentral before tar; original server restarted immediately after volume archive creation. The backup directory name uses the date/time.
- Treat first backup as **pending** until the script is run and hashes pass. Treat restoration as **pending** until tested.

## Restore to new work Proxmox Docker VM
1. Keep the old server safely offline/isolated during recovery testing to avoid duplicate agents/tunnels. Restore from a clean, trusted, encrypted backup.
2. Install supported Docker/Compose and Portainer; create network `tunnel`, then deploy the **same** MeshCentral Compose (initially without making the restored hostname public).
3. Stop `meshcentral-work` on destination. Identify the **actual** four volume names from Docker inspect.
4. Restore each archive into its corresponding **empty** destination volume, preserving ownership, permissions, and keys. Example of a single archive restore (adapt volume and file path):
```bash
docker run --rm --network none \
  -v ACTUAL_DATA_VOLUME_NAME:/target \
  -v /path/to/backup-folder:/backup:ro \
  alpine:3.20 tar -xzf /backup/meshcentral-data.tar.gz -C /target
```
Repeat for `meshcentral-files`, `meshcentral-backups`, `meshcentral-web`. **Never extract a backup over unknown pre-existing live data**.
5. Make sure `config.json` still advertises `remote.wjwater.org`, and Cloudflare tunnel routing points to `https://meshcentral-work:443` through the work tunnel network. Configure trusted origin TLS instead of relying on `No TLS Verify` indefinitely.
6. Start container and test login, MFA, user-to-device authorization and existing installed agents through the hostname **before declaring recovery successful**.

## Current status
**Observed 2026-10-22:** Script installed and run manually on work VM. It archived all four named volumes, all four SHA256 checks passed, and printed `SUCCESS: /home/brandon/meshcentral-backups/20261022-124305`. User crontab verified to contain `30 3 * * * /home/brandon/backup-meshcentral-work.sh >> /home/brandon/meshcentral-backups/backup.log 2>&1`. **Still unverified:** service restarted and agents reconnected after script, next cron execution, encrypted off-host transfer, and independent restore drill.
