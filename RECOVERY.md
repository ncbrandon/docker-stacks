# WWTP Docker Server Recovery Notes

This document explains how to recover or rebuild the Docker-based WWTP / Water Resources server setup.

It covers:

- SQL Server container
- WWTP database backups
- NAS backup verification
- Restore testing
- Well Readings web app
- Cloudflare Tunnel
- Portainer
- Watchtower
- New Ubuntu VM recovery order

> **Important:** Do not commit real passwords, tokens, or the real `.env` file to GitHub. Commit `.env.example` only.

---

## Main Server Folders

```text
/home/brandon/docker-stacks
/home/brandon/sql-backups
/home/brandon/.config/rclone
```

### Folder Purposes

```text
/home/brandon/docker-stacks
```

Holds Docker Compose stack folders and documentation.

```text
/home/brandon/sql-backups
```

Stores local SQL Server `.bak` backup files and backup logs.

```text
/home/brandon/.config/rclone
```

Stores rclone configuration used by the backup container to copy backups to the NAS.

---

## Main Containers

```text
wwtp-sql
well-readings
cloudflared
portainer
watchtower
sql-backup
```

### Container Purposes

| Container | Purpose |
|---|---|
| `wwtp-sql` | Microsoft SQL Server container for the WWTP database |
| `well-readings` | ASP.NET Well Readings web app |
| `cloudflared` | Cloudflare Tunnel container |
| `portainer` | Docker/Portainer management UI |
| `watchtower` | Container update automation |
| `sql-backup` | One-shot backup container that creates SQL `.bak` files and copies them to backup destinations |

---

## Recommended Docker Stack Folder Layout

```text
docker-stacks/
├── .env
├── .env.example
├── .gitignore
├── README.md
├── RECOVERY.md
├── wwtp-sql/
│   └── docker-compose.yml
├── well-readings/
│   └── docker-compose.yml
├── cloudflared/
│   └── docker-compose.yml
├── sql-backup/
│   ├── docker-compose.yml
│   ├── Dockerfile
│   └── backup-wwtp-sql.sh
└── nc-dww-scraper/
    └── docker-compose.yml
```

---

## GitHub Safety

Do **not** commit the real `.env` file.

Use `.gitignore`:

```gitignore
.env
*.bak
*.backup
*.tar
*.tar.gz
*.log
```

Commit `.env.example` instead.

Example `.env.example`:

```env
# SQL backup
SQL_CONTAINER_NAME=wwtp-sql
SQL_BACKUP_DATABASE=WWTP
SQL_BACKUP_PASSWORD=change-me

# Backup destinations
ONEDRIVE_REMOTE=
NAS_REMOTE=nas:West Jefferson/WWTP SQL Backups

# Well Readings app
WELL_READINGS_CONNECTION_STRING=Server=wwtp-sql;Database=WWTP;User Id=sa;Password=change-me;TrustServerCertificate=True;
```

---

# SQL Server

## SQL Container

```text
wwtp-sql
```

## Main Database

```text
WWTP
```

## SQL Backup Container

```text
sql-backup
```

The backup container is a one-shot container. It runs, creates a backup, copies it to configured remote destinations, and exits.

Manual backup command:

```bash
docker start -a sql-backup
```

---

## SQL Backup Paths

### Host Backup Folder

```text
/home/brandon/sql-backups
```

### SQL Container Backup Folder

```text
/var/opt/mssql/backups
```

The SQL stack should mount the host folder into the SQL container, similar to:

```yaml
volumes:
  - ms_sql_server_sql_data:/var/opt/mssql
  - /home/brandon/sql-backups:/var/opt/mssql/backups
```

---

## SQL Backup Stack Environment Variables

The `sql-backup` container needs these values passed into it:

```yaml
environment:
  SQL_CONTAINER_NAME: wwtp-sql
  SQL_BACKUP_DATABASE: ${SQL_BACKUP_DATABASE}
  SQL_BACKUP_PASSWORD: ${SQL_BACKUP_PASSWORD}
  ONEDRIVE_REMOTE: ${ONEDRIVE_REMOTE}
  NAS_REMOTE: ${NAS_REMOTE}
```

If `NAS_REMOTE` is not included in `docker-compose.yml`, the container will not copy backups to the NAS even if `.env` contains a NAS value.

---

## Current NAS Backup Destination

```text
nas:West Jefferson/WWTP SQL Backups
```

The `.env` value should be:

```env
NAS_REMOTE=nas:West Jefferson/WWTP SQL Backups
```

If OneDrive is not being used, leave it blank:

```env
ONEDRIVE_REMOTE=
```

---

## Rebuild/Recreate SQL Backup Container

After editing `.env`, `docker-compose.yml`, `Dockerfile`, or `backup-wwtp-sql.sh`, recreate the backup container:

```bash
cd /home/brandon/docker-stacks/sql-backup

docker rm -f sql-backup

docker compose --env-file /home/brandon/docker-stacks/.env up -d --build --force-recreate
```

Check that the environment variables loaded correctly:

```bash
docker inspect sql-backup --format '{{range .Config.Env}}{{println .}}{{end}}' | grep -E "ONEDRIVE|NAS|SQL"
```

Expected example:

```text
SQL_CONTAINER_NAME=wwtp-sql
SQL_BACKUP_DATABASE=WWTP
SQL_BACKUP_PASSWORD=SECRET
ONEDRIVE_REMOTE=
NAS_REMOTE=nas:West Jefferson/WWTP SQL Backups
```

---

# Backup Logs and Verification

## View Backup Log

```bash
tail -100 /home/brandon/sql-backups/backup.log
```

Successful backup log should include something like:

```text
Starting backup at ...
Database: WWTP
Backup file: WWTP_YYYY-MM-DD_HH-MM-SS.bak
Backup created:
Copying to NAS remote: nas:West Jefferson/WWTP SQL Backups
Removing local backups older than 14 days...
Backup completed successfully at ...
```

## List Local Backups

```bash
ls -lht /home/brandon/sql-backups/*.bak | head
```

## Verify NAS Backup Files

```bash
docker run --rm -it \
  -v /home/brandon/.config/rclone:/config/rclone \
  rclone/rclone:latest lsf "nas:West Jefferson/WWTP SQL Backups"
```

---

# Daily Backup Schedule

Backups are scheduled with the `brandon` user's crontab.

Check cron:

```bash
crontab -l
```

Expected cron line:

```cron
0 2 * * * docker start -a sql-backup >> /home/brandon/sql-backups/cron.log 2>&1
```

This runs the SQL backup container every day at **2:00 AM**.

View cron log:

```bash
tail -100 /home/brandon/sql-backups/cron.log
```

If cron is not running:

```bash
sudo systemctl status cron
sudo systemctl enable cron
sudo systemctl start cron
```

---

# SQL Restore Test Process

This process verifies that a backup file is actually restorable.

The test restore uses a temporary database named:

```text
WWTP_RestoreTest
```

It does **not** overwrite the live `WWTP` database.

---

## 1. Pick Latest Backup

```bash
LATEST_BAK=$(ls -t /home/brandon/sql-backups/*.bak | head -1)
BASENAME=$(basename "$LATEST_BAK")
echo "$BASENAME"
```

Example:

```text
WWTP_2026-05-15_11-58-38.bak
```

---

## 2. Enter SQL Password

```bash
read -s SQL_PASSWORD
```

Paste the SQL `sa` password and press `Enter`.

---

## 3. Check Backup Logical File Names

```bash
docker exec -it wwtp-sql /opt/mssql-tools18/bin/sqlcmd \
  -S localhost \
  -U sa \
  -P "$SQL_PASSWORD" \
  -C \
  -Q "RESTORE FILELISTONLY FROM DISK = N'/var/opt/mssql/backups/$BASENAME'"
```

Expected logical file names are usually:

```text
WWTP
WWTP_log
```

If the logical names are different, update the `MOVE` names in the restore command.

---

## 4. Drop Old Restore Test Database If It Exists

```bash
docker exec -it wwtp-sql /opt/mssql-tools18/bin/sqlcmd \
  -S localhost \
  -U sa \
  -P "$SQL_PASSWORD" \
  -C \
  -Q "IF DB_ID(N'WWTP_RestoreTest') IS NOT NULL
      BEGIN
          ALTER DATABASE [WWTP_RestoreTest] SET SINGLE_USER WITH ROLLBACK IMMEDIATE;
          DROP DATABASE [WWTP_RestoreTest];
      END"
```

---

## 5. Restore Backup as WWTP_RestoreTest

```bash
docker exec -it wwtp-sql /opt/mssql-tools18/bin/sqlcmd \
  -S localhost \
  -U sa \
  -P "$SQL_PASSWORD" \
  -C \
  -Q "RESTORE DATABASE [WWTP_RestoreTest]
      FROM DISK = N'/var/opt/mssql/backups/$BASENAME'
      WITH
          MOVE N'WWTP' TO N'/var/opt/mssql/data/WWTP_RestoreTest.mdf',
          MOVE N'WWTP_log' TO N'/var/opt/mssql/data/WWTP_RestoreTest_log.ldf',
          REPLACE,
          RECOVERY,
          STATS = 10"
```

Expected output includes progress such as:

```text
10 percent processed.
20 percent processed.
...
RESTORE DATABASE successfully processed ...
```

---

## 6. Confirm Restored Database Exists

```bash
docker exec -it wwtp-sql /opt/mssql-tools18/bin/sqlcmd \
  -S localhost \
  -U sa \
  -P "$SQL_PASSWORD" \
  -C \
  -Q "SELECT name, state_desc FROM sys.databases WHERE name IN ('WWTP', 'WWTP_RestoreTest');"
```

Expected:

```text
WWTP              ONLINE
WWTP_RestoreTest  ONLINE
```

---

## 7. Check Restored Table Counts

```bash
docker exec -it wwtp-sql /opt/mssql-tools18/bin/sqlcmd \
  -S localhost \
  -U sa \
  -P "$SQL_PASSWORD" \
  -C \
  -d WWTP_RestoreTest \
  -Q "SELECT 'ScadaHistoryPoints' AS TableName, COUNT(*) AS RowsFound FROM dbo.ScadaHistoryPoints
      UNION ALL
      SELECT 'DailyEntries', COUNT(*) FROM dbo.DailyEntries
      UNION ALL
      SELECT 'WellReadings', COUNT(*) FROM dbo.WellReadings
      UNION ALL
      SELECT 'FiltrationPlantReadings', COUNT(*) FROM dbo.FiltrationPlantReadings
      UNION ALL
      SELECT 'Wells', COUNT(*) FROM dbo.Wells
      UNION ALL
      SELECT 'ValidMeterLocations', COUNT(*) FROM dbo.ValidMeterLocations;"
```

---

## 8. Compare With Live WWTP Database

```bash
docker exec -it wwtp-sql /opt/mssql-tools18/bin/sqlcmd \
  -S localhost \
  -U sa \
  -P "$SQL_PASSWORD" \
  -C \
  -d WWTP \
  -Q "SELECT 'ScadaHistoryPoints' AS TableName, COUNT(*) AS RowsFound FROM dbo.ScadaHistoryPoints
      UNION ALL
      SELECT 'DailyEntries', COUNT(*) FROM dbo.DailyEntries
      UNION ALL
      SELECT 'WellReadings', COUNT(*) FROM dbo.WellReadings
      UNION ALL
      SELECT 'FiltrationPlantReadings', COUNT(*) FROM dbo.FiltrationPlantReadings
      UNION ALL
      SELECT 'Wells', COUNT(*) FROM dbo.Wells
      UNION ALL
      SELECT 'ValidMeterLocations', COUNT(*) FROM dbo.ValidMeterLocations;"
```

The restored counts should match the live database counts at the time the backup was created.

---

## 9. Drop Restore Test Database

After confirming the restore worked:

```bash
docker exec -it wwtp-sql /opt/mssql-tools18/bin/sqlcmd \
  -S localhost \
  -U sa \
  -P "$SQL_PASSWORD" \
  -C \
  -Q "ALTER DATABASE [WWTP_RestoreTest] SET SINGLE_USER WITH ROLLBACK IMMEDIATE;
      DROP DATABASE [WWTP_RestoreTest];"
```

Confirm only the live database remains:

```bash
docker exec -it wwtp-sql /opt/mssql-tools18/bin/sqlcmd \
  -S localhost \
  -U sa \
  -P "$SQL_PASSWORD" \
  -C \
  -Q "SELECT name, state_desc FROM sys.databases WHERE name LIKE 'WWTP%';"
```

Expected:

```text
WWTP    ONLINE
```

---

# Last Verified Restore Test

Date:

```text
May 15, 2026
```

Result:

```text
Backup restored to WWTP_RestoreTest successfully.
Restored row counts matched live WWTP.
WWTP_RestoreTest was deleted afterward.
Live WWTP remained ONLINE.
```

Verified row counts:

```text
TableName               RowsFound
----------------------- -----------
ScadaHistoryPoints            48300
DailyEntries                      0
WellReadings                      0
FiltrationPlantReadings           0
Wells                            10
ValidMeterLocations              12
```

---

# Basic Health Checks

## Show Running Containers

```bash
docker ps --format "table {{.Names}}\t{{.Image}}\t{{.Ports}}"
```

## SQL Logs

```bash
docker logs --tail=100 wwtp-sql
```

## Web App Logs

```bash
docker logs --tail=100 well-readings
```

## Cloudflare Tunnel Logs

```bash
docker logs --tail=100 cloudflared
```

## Backup Logs

```bash
tail -100 /home/brandon/sql-backups/backup.log
```

## Cron Logs

```bash
tail -100 /home/brandon/sql-backups/cron.log
```

## Run Manual Backup

```bash
docker start -a sql-backup
```

## Verify Latest Local Backup

```bash
ls -lht /home/brandon/sql-backups/*.bak | head
```

## Verify Latest NAS Backup

```bash
docker run --rm -it \
  -v /home/brandon/.config/rclone:/config/rclone \
  rclone/rclone:latest lsf "nas:West Jefferson/WWTP SQL Backups"
```

---

# SQL Server Exposure Recommendation

If the web app talks to SQL Server over a Docker network, SQL Server does not need to be publicly exposed.

Prefer using Docker networking:

```text
Server=wwtp-sql;Database=WWTP;User Id=...;Password=...;TrustServerCertificate=True;
```

Avoid exposing this unless needed:

```yaml
ports:
  - "1433:1433"
```

If remote SQL access from a Windows machine is required, restrict it to the LAN or use a safer access method.

---

# Watchtower Recommendation

Use Watchtower carefully.

Recommended:

- Allow Watchtower to update the web app if desired.
- Consider excluding SQL Server from automatic updates.
- Run a SQL backup before updating SQL Server.

Example label to exclude SQL Server:

```yaml
labels:
  - "com.centurylinklabs.watchtower.enable=false"
```

---

# New Ubuntu Server VM Recovery Order

Use this order if rebuilding or migrating to a new Ubuntu Server VM.

1. Install Ubuntu Server.
2. Install Docker.
3. Install Portainer.
4. Copy `/home/brandon/docker-stacks` to the new VM.
5. Copy `/home/brandon/.config/rclone` to the new VM.
6. Copy or restore `/home/brandon/sql-backups`.
7. Create any required Docker networks.
8. Deploy the SQL Server stack.
9. Restore latest `WWTP` `.bak` file.
10. Deploy the Well Readings web app stack.
11. Deploy Cloudflare Tunnel.
12. Deploy Watchtower.
13. Deploy the SQL backup stack.
14. Test the website.
15. Run a manual backup:

```bash
docker start -a sql-backup
```

16. Verify the backup appears on the NAS.
17. Confirm the daily cron schedule:

```bash
crontab -l
```

---

# New Server Pre-Migration Checklist

Before moving from the old VM to a new VM:

## 1. Run a Fresh Backup

```bash
docker start -a sql-backup
```

## 2. Verify Local Backup

```bash
ls -lht /home/brandon/sql-backups/*.bak | head
```

## 3. Verify NAS Backup

```bash
docker run --rm -it \
  -v /home/brandon/.config/rclone:/config/rclone \
  rclone/rclone:latest lsf "nas:West Jefferson/WWTP SQL Backups"
```

## 4. Save Container List

```bash
docker ps --format "table {{.Names}}\t{{.Image}}\t{{.Ports}}" > /home/brandon/docker-stacks/container-list.txt
```

## 5. Save SQL Mounts

```bash
docker inspect wwtp-sql --format '{{range .Mounts}}{{println .Source "->" .Destination}}{{end}}' > /home/brandon/docker-stacks/wwtp-sql-mounts.txt
```

## 6. Save Web App Mounts

```bash
docker inspect well-readings --format '{{range .Mounts}}{{println .Source "->" .Destination}}{{end}}' > /home/brandon/docker-stacks/well-readings-mounts.txt
```

---

# After Reboot Checklist

After rebooting the Ubuntu VM or Windows host:

```bash
docker ps
```

Check main services:

```bash
docker logs --tail=50 wwtp-sql
docker logs --tail=50 well-readings
docker logs --tail=50 cloudflared
```

Run backup test:

```bash
docker start -a sql-backup
```

Verify NAS:

```bash
docker run --rm -it \
  -v /home/brandon/.config/rclone:/config/rclone \
  rclone/rclone:latest lsf "nas:West Jefferson/WWTP SQL Backups"
```

---

# Quick Status Commands

```bash
# Containers
docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Image}}\t{{.Ports}}"

# Backup files
ls -lht /home/brandon/sql-backups/*.bak | head

# Backup log
tail -80 /home/brandon/sql-backups/backup.log

# Cron log
tail -80 /home/brandon/sql-backups/cron.log

# Backup container environment
docker inspect sql-backup --format '{{range .Config.Env}}{{println .}}{{end}}' | grep -E "ONEDRIVE|NAS|SQL"

# NAS backup listing
docker run --rm -it \
  -v /home/brandon/.config/rclone:/config/rclone \
  rclone/rclone:latest lsf "nas:West Jefferson/WWTP SQL Backups"
```

---

# Recovery Confidence Notes

As of the last verified test:

- SQL backups are being created.
- NAS backup destination is configured.
- A backup was restored to `WWTP_RestoreTest`.
- Restored row counts matched the live `WWTP` database.
- The test restore database was deleted after verification.
- The live `WWTP` database remained online.

This means the backup process has been verified beyond file creation; it has been confirmed restorable.
