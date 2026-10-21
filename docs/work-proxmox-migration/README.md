# Town of West Jefferson — Work Proxmox Disaster Recovery

**Audit status (2026-10-21): IN PROGRESS — NOT YET VERIFIED RECOVERABLE.** This documentation is grounded in the GitHub stacks inspected and previous setup conversations. A complete disaster-recovery guarantee requires export of the *running* Portainer environment, off-host backup inspection and successful restore rehearsals.

## Read these in order
1. [Inventory existing work VM and gaps](01-source-inventory.md)
2. [Backups and disaster recovery testing](02-backup-restore.md)
3. [Fresh Proxmox/Docker reinstall sequence](03-proxmox-rebuild.md)

## Existing GitHub source of truth
- [Work SQL Server Compose](../../wwtp-sql/docker-compose.yml)
- [Well Readings Compose](../../well-readings/docker-compose.yml)
- [Work Cloudflare Compose](../../cloudflared/docker-compose.yml)
- [Well Depth Grapher Compose](../../well-depth-grapher/docker-compose.yml)
- [Well Depth Grapher image workflow](../../.github/workflows/well-depth-grapher-publish.yml)

Other likely work repositories: [Well-Readings-App](https://github.com/ncbrandon/Well-Readings-App), [nc-dww-scraper](https://github.com/ncbrandon/nc-dww-scraper), [wjwater](https://github.com/ncbrandon/wjwater). All repository references must be cross-checked with the actual running services before relying on them.

## What is not yet proven
- Exact running container/image versions, Portainer stacks and environment mappings.
- SQL and SQLite backups tested on a separate machine.
- Portainer settings, volumes, file uploads and host-only app code exported.
- Cron jobs, rclone credentials/destination and backup monitoring.
- Cloudflare tunnel hostnames, Access policies and recovery keys restored.
- Proxmox host/VM storage, off-host backup target and successful disaster-recovery drill.
- Recovery of dashboards, scraper and manhole app from *only* documented files.

**Keep home systems separate from municipal systems. Do not add secrets, database dumps or personal data to GitHub.**

## Migration readiness decision
Do **not** decommission the original VM until every acceptance check in [backup/restore](02-backup-restore.md) and [rebuild](03-proxmox-rebuild.md) is completed and recorded.
