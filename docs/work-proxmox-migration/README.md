# Town of West Jefferson — Work Proxmox Migration

This directory will contain audited rebuild instructions for migrating work Docker services to a dedicated Proxmox server.

## Existing Docker stacks
- SQL Server 2022 (`wwtp-sql`)
- Well Readings application
- Cloudflare Tunnel
- Well-depth grapher

## Additional services to document
- Portainer and Docker host setup
- SQL backups and rclone
- NC DWW scraper
- Rainfall and wastewater flow dashboard
- Fire-flow dashboard
- Manhole survey (SQLite and cron backups)
- Watchtower
- Separate work MeshCentral installation

## Migration precautions
Document and back up Docker volumes, bind mounts, environment variable names, networks, databases, scheduled jobs, TLS configuration, and Cloudflare routing. Keep secrets and production data **out of GitHub**. Verify full SQL/SQLite restores before decommissioning the old work VM.

Status: initial documentation; live configurations still require audit.
