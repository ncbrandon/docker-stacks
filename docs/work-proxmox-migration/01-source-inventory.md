# 01 — Source-system inventory and evidence checklist

**Status:** requires a read-only audit of the running **work** Docker VM. Do not assume the GitHub copy matches Portainer. This document is intended to be filled in before any migration, after reviewing the output privately.

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
