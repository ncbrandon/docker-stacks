# 03 — Fresh work Proxmox and Docker rebuild

## Architecture
Dedicated **municipal work** Proxmox host and Docker VM; never reuse home Proxmox or home MeshCentral for municipal services. A simple starting architecture: Proxmox host -> one supported Ubuntu Server LTS VM -> Docker Engine + Compose plugin -> Portainer CE -> app stacks. Choose CPU/RAM/storage according to actual SQL database size, load and backup windows and record final values.

## Before installation
- Save physical server BIOS/UEFI, NIC MAC addresses, disks/RAID/ZFS design, Proxmox subscription/repo choice, VLAN/firewall, DHCP reservation/static IP, admin/2FA credentials and out-of-band recovery.
- Decide Proxmox management IP, storage pool, VM disks, backup target and restore location. Proxmox storage itself is **not** a sufficient off-host backup.
- Inventory live Docker VM volumes, host binds, cron and Cloudflare routes. Copy encrypted recovery material and database backups.

## Build order
1. Install Proxmox VE from official installation media; update and secure management access, set NTP/time, stable network bridge, storage and off-host backup job.
2. Create Ubuntu Server LTS VM with static or reserved address; enable Proxmox guest agent and autostart; patch OS.
3. Install supported Docker Engine and Compose plugin using official Docker APT repository (not an undocumented one-line curl install). Verify `docker version` and `docker compose version`.
4. Install Portainer CE following official supported procedure; persist Portainer data, restrict its administrative port to LAN/VPN, then import prior backup.
5. Recreate external networks used by existing stack definitions:
```bash
docker network inspect wwtp-net >/dev/null 2>&1 || docker network create wwtp-net
docker network inspect tunnel >/dev/null 2>&1 || docker network create tunnel
```
6. Verify external SQL data volume is **restored** before starting SQL, or create empty SQL volume deliberately and perform a real SQL `.bak` restore. Never start fresh SQL over an unrecovered existing deployment.
7. Deploy SQL Server from `../../wwtp-sql/docker-compose.yml`. SQL host backup path is `/home/brandon/sql-backups`; adapt the new VM's user/path and permissions safely.
8. Restore databases, validate logins and data, then deploy `../../well-readings/docker-compose.yml` and `../../well-depth-grapher/docker-compose.yml`.
9. Recover `nc-dww-scraper`, rainfall-flow and fire-flow dashboards, manhole-survey image/source and SQLite data, scripts, cron jobs and Watchtower config from **audited live definitions**. Avoid guessing Docker image names/ports.
10. Configure `../../cloudflared/docker-compose.yml` with correct work tunnel token and verified origin mappings; test DNS/Cloudflare Access and WebSockets (where needed).
11. Set up planned separate work MeshCentral only after stable TLS/hostname, agent routing and MFA. Restrict operators by groups and privileges; do not put plant control systems on general unattended remote access without documented authorization.
12. Validate all services, run backup restore drills, freeze source VM as rollback target, then decommission only after approval.

## Known Compose environment variable names
| Stack | Variables |
|---|---|
| SQL | `MSSQL_SA_PASSWORD` |
| Well Readings | `WELL_READINGS_CONNECTION_STRING` |
| Cloudflared | `CLOUDFLARE_TUNNEL_TOKEN` |
| Well-depth grapher | `DB_SERVER`, `DB_PORT`, `DB_NAME`, `DB_USER`, `DB_PASSWORD` |

Keep values outside GitHub in Portainer secure environment or a password manager. Restrict SQL 1433 exposure and Portainer management ports. Commit a **sanitized** `.env.example` only.

## URLs and checkpoints
- `well-readings` Compose uses port `8080:8080`.
- Well-depth grapher Compose uses `8502:8501`.
- SQL host mapping `1433:1433` is recorded but should be firewall-restricted.
- Exact public hostnames, Docker/Portainer source versions, and new work VM IP must be gathered from live environment.

## Repeatable test matrix
- SQL application user can read/write intended WWTP tables, and database report counts match.
- Well Readings `/Scada`, `/DailyEntry`, `/Maintenance`, `/MonthlyReport`, `/ExcelImport`, `/ScadaEntry`; investigate known report mismatches before certifying equality.
- DWW scraper runs once successfully without duplicate ingestion.
- Rain/flow and fire-flow imports, interactive date ranges, template downloads, exports, notes, SQL persistence.
- Manhole survey record status (yellow -> green), measurements, upload persistence, supplier PDF, cron ZIP backup and retention.
- Cloudflare Access email OTP/user policy and external access.
- Restore a complete VM + DB + attachments backup in an isolated lab.
