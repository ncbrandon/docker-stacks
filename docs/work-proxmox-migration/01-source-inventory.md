# 01 — Source-system inventory and evidence checklist

**Status:** initial read-only inventory received October 22, 2026; full application/backup validation still pending. Do not assume the GitHub copy matches Portainer. This document is intended to be filled in before any migration, after reviewing the output privately.

## Repositories discovered in GitHub
The account currently exposes: `SmartThingsPublic`, `Keith`, `wjwater`, `ai_website`, `Well-Readings-App`, `nc-dww-scraper`, `docker-stacks`, `tools`, `Home`. Likely work sources are `Well-Readings-App`, `nc-dww-scraper`, `docker-stacks`, and public site `wjwater`. `Keith` is a separate consulting website; do not migrate it onto the municipal VM without a conscious decision. Verify other repositories' roles rather than assume.

## Capture from the running Ubuntu work Docker VM
Paste output into a **private** encrypted migration record. These commands may expose infrastructure details; never post raw inspect results or tokens in public GitHub.

```bash
hostnamectl
timedatectl
ip -br address
lsblk -f
df -hT
docker version
docker compose version
docker ps -a --format 'table {{.Names}}\t{{.Image}}\t{{.Status}}\t{{.Ports}}'
docker volume ls
docker network ls
docker images --digests
crontab -l
sudo crontab -l
sudo systemctl list-timers --all
sudo systemctl list-unit-files --type=service
```

For each running container, additionally collect `docker inspect CONTAINER` in the **private record**. Inspect actual Portainer stack editor/variables, bind mounts, volume data, labels and Docker image digest. Find all custom code or Dockerfiles currently built **only** on the VM.

## Evidence matrix
| System | GitHub verified | Live data needed | Action |
|---|---|---|---|
| `wwtp-sql` | Compose in `wwtp-sql/` | SQL backups and logins, named volume `ms_sql_server_sql_data` | prove full restore |
| `well-readings` | Compose in `well-readings/` | exact image digest, connection string, file dependencies | regression tests |
| `cloudflared` | Compose in `cloudflared/` | hostname/Access policy export, tunnel token secure escrow | test after DNS cutover |
| `well-depth-grapher` | Compose and workflow in `well-depth-grapher/` | database role/connection, digest | dashboard test |
| `nc-dww-scraper` | separate repo exists | runtime deploy definition, schedule, output | one successful scrape |
| Rain/flow dashboard | app reported in prior setup | source/Compose, SQL tables, uploaded Excel files | functionality/data validation |
| Fire-flow dashboard | app reported in prior setup | source/Compose, SQL tables/templates | functionality/data validation |
| Manhole survey | separate standalone Docker app | local code, SQLite, storage, cron, Access policy | restore + PDF test |
| SQL/rclone backup | configured historically | scripts, remote, encryption, rotations, alerting | off-host restore test |
| Portainer/Watchtower | managed historically | Portainer backup, Watchtower policy | administrative restore |

## High-risk dependency findings
1. Current SQL Compose uses external volume `ms_sql_server_sql_data`, external network `wwtp-net`, and host backup bind `/home/brandon/sql-backups`. The Compose file alone does **not** contain database contents or restore SQL users.
2. Well Readings requires `WELL_READINGS_CONNECTION_STRING` and networks `wwtp-net` and `tunnel`.
3. Cloudflared requires `CLOUDFLARE_TUNNEL_TOKEN` and configured Cloudflare public hostnames/Access policies, which cannot be recreated from the Compose file alone.
4. Well-depth grapher requires `DB_SERVER`, `DB_PORT`, `DB_NAME`, `DB_USER`, `DB_PASSWORD` and connects to `wwtp-net`.
5. Any app hosted only in a locally built Docker image **must have its source and Dockerfile archived**; `docker save` alone is not a maintainable source recovery plan.

## Never treat as validated until measured
Private IPs, VM IDs, live DNS routes, exact versions/digests, running cron lines, database row counts, current volumes, retention periods, user account identities, backup destinations and password recovery information.

## Actual work VM inventory — captured 2026-10-22 07:27 EDT

This section is based on actual read-only command output provided by the operator. **It does not include live stack editor definitions, complete source code, backup inspection, or a restore test.**

- Host: `docker`; Ubuntu **24.04.4 LTS**, kernel `6.8.0-142-generic`, x86-64 under **VirtualBox**.
- Timezone `America/New_York`, synchronized clock, active NTP.
- Docker Engine **29.5.2**, Docker Compose **v5.1.4**.
- Root filesystem `/dev/sda2`, ext4, **79 GB total**, **42 GB used**, **34 GB free** at collection.
- **13 containers** (12 running, 1 normally stopped), **6 named volumes**, **11 Docker networks**.

### Exact container inventory

| Container | Image shown by `docker ps -a` | Host exposure/status |
|---|---|---|
| `weewx-web` | `nginx:alpine` | up; `80/tcp` only (not published) |
| `manhole-survey` | `manhole-survey:1.3` | up; `8088:8080` |
| `weewx` | `weewx-weewx` | up; no published port |
| `cloudflared` | `cloudflare/cloudflared:latest` | up |
| `fire-flow-dashboard` | `fire-flow-dashboard-fire-flow-dashboard` | up; `8504:8501` |
| `well-readings` | `ghcr.io/ncbrandon/well-readings-app:latest` | up; `8080:8080` |
| `rainfall-flow-dashboard` | `rainfall-flow-dashboard-rainfall-flow-dashboard` | up; `8503:8501` |
| `well-depth-grapher` | `ghcr.io/ncbrandon/well-depth-grapher:latest` | up; `8502:8501` |
| `sql-backup` | `sql-backup-sql-backup` | `Exited (0)` ~4h before audit; cron-driven |
| `watchtower` | `containrrr/watchtower:latest` | up; healthy |
| `wwtp-sql` | `mcr.microsoft.com/mssql/server:2022-latest` | up; `1433:1433` |
| `nc-dww-scraper` | `nc-dww-scraper-nc-dww-scraper` | up; `8501/tcp` only |
| `portainer` | `portainer/portainer-ce:latest` | up; `8000:8000`, `9443:9443` |

Local-only images include `manhole-survey:1.0`, `:1.1`, `:1.2` and currently running **`:1.3`**; `weewx-weewx`; rainfall/fire-flow dashboards; `sql-backup-sql-backup`; and `nc-dww-scraper-nc-dww-scraper`. Preserve **source + Dockerfiles + build instructions**, not just image tar files. The old `well-depth-grapher-well-depth-grapher` image also remains on host but is not current container image.

### Named volumes

- `ms_sql_server_sql_data` **critical** SQL data
- `nc-dww-scraper_nc_dww_data` -> `/app/data`
- `nc-dww-scraper_nc_dww_output` -> `/app/output`
- `portainer_data` -> `/data`
- `well-readings` — appears not to be mounted by any of the listed current containers; confirm unused before any deletion
- `homeassistant_homeassistant_config` — appears not currently mounted; determine if historical/home residue and do **not** delete based on that assumption

### Important bind mounts

| Container | Source | Inside container |
|---|---|---|
| `weewx` | `/home/brandon/docker-stacks/weewx/data` | `/data` |
| `weewx-web` | `/home/brandon/docker-stacks/weewx/data/public_html` | `/usr/share/nginx/html` |
| `manhole-survey` | `/home/brandon/manhole-survey/storage` | `/app/storage` |
| `wwtp-sql` | `/home/brandon/sql-backups` | `/var/opt/mssql/backups` |
| `sql-backup` | `/home/brandon/sql-backups` | `/backups` |
| `sql-backup` | `/home/brandon/.config/rclone` | `/config/rclone` |
| `sql-backup`, `watchtower`, `portainer` | `/var/run/docker.sock` | `/var/run/docker.sock` |

The `weewx` source directory is under `docker-stacks/weewx/data`, but this does **not** mean it is committed to Git; check ignored files and copy the real files off-host. Several dashboards have no mounts and therefore any important local state inside their writable layers may be lost on recreation.

### Networks seen
`app-network`, `bridge`, `host`, `manhole-survey_default`, `none`, `sql-backup_default`, `tunnel`, `tunnel-net`, `watchtower_default`, `weather-internal`, `wwtp-net`.

**Do not simply re-create all networks blindly**: inspect per-container memberships, aliases, firewall and isolation policies. Existing GitHub stacks explicitly depend on external `tunnel` and `wwtp-net`.

### Scheduled jobs — actual user crontab
```cron
0 3 * * * docker start -a sql-backup >> /home/brandon/sql-backups/cron.log 2>&1
15 3 * * * /usr/bin/python3 /home/brandon/backup_manhole.py >> /home/brandon/manhole-backup.log 2>&1
```
The normal exit code of `sql-backup` indicates successful process completion only, **not that off-site files or restores were checked**. Archive both script and rclone config (private/encrypted); check cron logs, backup age and restoreability. Existing observations cannot confirm whether the manhole script's retention limit is actually enforced.

### Newly recognized critical service: WeeWX
The VM runs both `weewx` and `weewx-web`, with a host bind of `/home/brandon/docker-stacks/weewx/data`. Add WeeWX driver/hardware mapping, configuration, database/history, template/assets, Nginx content, weather devices, logs and associated private tunnel hostname to recovery plan. Validate on restored server.

### Priority corrections to historical notes
- Manhole survey is **v1.3**, not v1.0; preserve the v1.3 code/Dockerfile and current SQLite storage.
- Backup jobs are scheduled for **03:00** and **03:15 America/New_York**.
- WeeWX was omitted from earlier recovery lists and is now a tracked service.
- The **source** VM uses ~42 GB; budget headroom for SQL growth, image rebuilds and snapshots on Proxmox, not just 42 GB.
- The inventory lists 13 **containers**; an installed image or named volume is not proof of a running service.

### Next evidence to request privately
1. Per-container image digest, network memberships, restart policy and stack-origin labels, without secret values.
2. Safe directory listing, source/code backup and file-size inventories for `/home/brandon/docker-stacks/`, `/home/brandon/manhole-survey/`, WeeWX, local dashboard source directories, and `/home/brandon/backup_manhole.py`.
3. Check `.bak` file times/sizes, backup job logs, rclone remote **names** and remote reachability, and SQLite backup manifests; never paste credentials.
4. Export Portainer backup and full per-stack YAML **securely**, sanitizing secrets before committing docs.
5. Test independent SQL/SQLite restoration and recovered WeeWX archive before any retirement of the source VM.
