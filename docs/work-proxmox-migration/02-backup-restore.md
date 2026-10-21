# 02 — Disaster-recovery checklist (work systems)

This runbook documents **required checks**, not a claim that all backups exist. Protect all backups and secrets outside public GitHub.

## Required independent recovery layers
1. **Proxmox VM backup**: regular VM image backup to a *different physical device/host* with retention and periodic verification. Record Proxmox version, storage IDs, host network bridge/VLAN, VM ID, cores, memory, virtual disks, BIOS type, boot order, guest agent, autostart and backup schedule.
2. **SQL Server application backup**: full `.bak` for WWTP and every other database; copy to a second system and run `RESTORE VERIFYONLY` **plus a real test restore**. Document TDE/certificates if used, logins, jobs, linked servers, database owner and application accounts.
3. **Manhole survey**: consistent SQLite backup *and* its related files/uploads/GIS assets; `PRAGMA integrity_check`; test actual app and supplier PDF after recovery.
4. **Configuration and scripts**: Portainer stack compose, `.env` templates (no values in GitHub), host crontabs, systemd units, rclone config/credentials (encrypted), SQL scripts, registry authentication, Cloudflare DNS/Access/tunnel settings and recovery codes.
5. **Business logic verification**: compare reports/records before vs after restore, not merely a green Docker status indicator.

## Initial on-source audit
```bash
docker ps -a --format 'table {{.Names}}\t{{.Image}}\t{{.Status}}\t{{.Ports}}'
docker volume ls
docker network ls
crontab -l
sudo crontab -l
sudo systemctl list-timers --all
```

Record each container's read/write mounts, exact image digest, networks, restart policies, user IDs, and environment variable **names**, as well as all storage located outside Docker volumes. Keep any `docker inspect` dumps private because secrets may be included.

## SQL Server source facts to verify
- Compose file: `../../wwtp-sql/docker-compose.yml`.
- Image `mcr.microsoft.com/mssql/server:2022-latest` (mutable; pin exact tested version for migration).
- Named volume `ms_sql_server_sql_data` is `external: true`.
- Backup bind path `/home/brandon/sql-backups:/var/opt/mssql/backups`.
- External Docker network `wwtp-net`.
- Port 1433 exposed to host in current Compose. Restrict it via host firewall/LAN/VPN.

Historical database check had `WWTP`, `WWTP_RestoreTest`; `ScadaHistoryPoints` approximately 48,300, `Wells` 10, `ValidMeterLocations` 12. These are **historical samples**, not recovery targets. Record current live counts before migration.

## Restore sequence
1. Create isolated destination VM/network; never run duplicate production scrapers or Cloudflare tunnels during testing.
2. Restore data via SQL `.bak` to a compatible 2022 instance; recreate permissions/logins, verify job owners and collations. Do **not** just create an empty `ms_sql_server_sql_data` volume and assume data recovered.
3. Recover SQLite and uploads, then attach bind mounts and permissions.
4. Create required external networks `wwtp-net` and `tunnel`; Portainer must preserve its own data volume.
5. Deploy database first, then apps/dashboard/scrapers, then access layer and scheduled backups, then auto-update only after testing.
6. Verify internal database reachability, core UI routes, reports, exports, user access, MFA, external hostnames and cloud policies.
7. Do an actual off-site recoverability drill **before** removing the source VM.

## Recovery acceptance checks
- [ ] latest encrypted off-host VM backup can restore
- [ ] complete SQL backup can restore with login/application access
- [ ] manhole records, photos, GIS and PDF export survive
- [ ] schedules trigger and backups **rotate** with defined retention
- [ ] remote Cloudflare/tunnel configuration works on cellular
- [ ] service credentials/recovery keys are escrowed securely
- [ ] GitHub repositories, scripts and built image artifacts can rebuild
- [ ] all source-only assets copied before retiring old machine

## Policy
Until the above is proven, describe the migration as **NOT DISASTER-RECOVERY VERIFIED**.
