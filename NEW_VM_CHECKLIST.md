# New Ubuntu VM Checklist

This checklist is for rebuilding the WWTP Docker server on a new Ubuntu Server VM.

It assumes the Docker stack repo is:

```text
/home/brandon/docker-stacks
```

It also assumes the main services are:

```text
wwtp-sql
well-readings
cloudflared
watchtower
sql-backup
portainer
```

> Do not commit real passwords, tunnel tokens, or connection strings to GitHub. Keep real values only in `.env` on the server.

---

## 1. Install Ubuntu Server

Install Ubuntu Server on the new VM.

Recommended:

- Use a static IP or DHCP reservation.
- Enable OpenSSH during install if available.
- Use the same username if possible:

```text
brandon
```

---

## 2. Update Ubuntu

```bash
sudo apt update
sudo apt upgrade -y
sudo reboot
```

Reconnect after reboot.

---

## 3. Install Docker

```bash
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker brandon
```

Log out and back in so the Docker group change applies.

Verify:

```bash
docker --version
docker compose version
```

Enable Docker on boot:

```bash
sudo systemctl enable docker
sudo systemctl enable containerd
```

---

## 4. Create required folders

```bash
mkdir -p /home/brandon/docker-stacks
mkdir -p /home/brandon/sql-backups
mkdir -p /home/brandon/.config/rclone
```

---

## 5. Create Docker network

The stacks use a shared external Docker network.

```bash
docker network create wwtp-net
```

If it already exists, that is okay.

Verify:

```bash
docker network ls | grep wwtp-net
```

---

## 6. Create SQL Server volume

The SQL Server stack uses an external Docker volume.

```bash
docker volume create ms_sql_server_sql_data
```

Verify:

```bash
docker volume ls | grep ms_sql_server_sql_data
```

---

## 7. Restore or clone Docker stacks

Preferred method:

```bash
git clone git@github.com:ncbrandon/docker-stacks.git /home/brandon/docker-stacks
```

If SSH is not configured yet, use HTTPS instead:

```bash
git clone https://github.com/ncbrandon/docker-stacks.git /home/brandon/docker-stacks
```

Alternative: restore from the NAS tar backup.

Example:

```bash
cd /home/brandon
tar xzf docker-stacks-backup-YYYY-MM-DD_HH-MM-SS.tar.gz
```

---

## 8. Create the real `.env` file

Start from the example file:

```bash
cd /home/brandon/docker-stacks
cp .env.example .env
nano .env
```

Fill in the real values.

Example structure:

```env
# SQL Server
MSSQL_SA_PASSWORD=change-this
ACCEPT_EULA=Y

# Well Readings app
WELL_READINGS_CONNECTION_STRING=Server=wwtp-sql;Database=WWTP;User Id=sa;Password=change-this;TrustServerCertificate=True;

# SQL backup
SQL_CONTAINER_NAME=wwtp-sql
SQL_BACKUP_DATABASE=WWTP
SQL_BACKUP_PASSWORD=change-this

# Optional OneDrive backup destination. Leave blank to disable.
ONEDRIVE_REMOTE=

# NAS backup destination
NAS_REMOTE=nas:West Jefferson/WWTP SQL Backups
```

Make sure `.env` is ignored by Git:

```bash
git status
```

The real `.env` file should not be staged or committed.

---

## 9. Restore rclone config

Restore the rclone config folder to:

```text
/home/brandon/.config/rclone
```

If restoring from tar backup:

```bash
cd /home/brandon
tar xzf rclone-config-backup-YYYY-MM-DD_HH-MM-SS.tar.gz
```

Fix ownership and permissions:

```bash
sudo chown -R brandon:brandon /home/brandon/.config/rclone
chmod 700 /home/brandon/.config/rclone
chmod 600 /home/brandon/.config/rclone/rclone.conf
```

Verify the NAS remote:

```bash
docker run --rm -it \
  -v /home/brandon/.config/rclone:/config/rclone \
  rclone/rclone:latest lsd nas:
```

Verify the SQL backup folder on NAS:

```bash
docker run --rm -it \
  -v /home/brandon/.config/rclone:/config/rclone \
  rclone/rclone:latest lsf "nas:West Jefferson/WWTP SQL Backups"
```

---

## 10. Copy latest SQL backup to the new server

Copy the latest `WWTP_*.bak` file from the old server or from NAS to:

```text
/home/brandon/sql-backups
```

Verify:

```bash
ls -lht /home/brandon/sql-backups/*.bak | head
```

---

## 11. Deploy SQL Server stack

```bash
cd /home/brandon/docker-stacks/wwtp-sql

docker compose --env-file /home/brandon/docker-stacks/.env up -d
```

Check logs:

```bash
docker logs --tail=100 wwtp-sql
```

Wait until SQL Server is ready.

---

## 12. Restore the WWTP database

Set the latest backup filename:

```bash
LATEST_BAK=$(ls -t /home/brandon/sql-backups/*.bak | head -1)
BASENAME=$(basename "$LATEST_BAK")
echo "$BASENAME"
```

Enter SQL password:

```bash
read -s SQL_PASSWORD
```

Check backup logical file names:

```bash
docker exec -it wwtp-sql /opt/mssql-tools18/bin/sqlcmd \
  -S localhost \
  -U sa \
  -P "$SQL_PASSWORD" \
  -C \
  -Q "RESTORE FILELISTONLY FROM DISK = N'/var/opt/mssql/backups/$BASENAME'"
```

Expected logical names are usually:

```text
WWTP
WWTP_log
```

Restore the database:

```bash
docker exec -it wwtp-sql /opt/mssql-tools18/bin/sqlcmd \
  -S localhost \
  -U sa \
  -P "$SQL_PASSWORD" \
  -C \
  -Q "RESTORE DATABASE [WWTP]
      FROM DISK = N'/var/opt/mssql/backups/$BASENAME'
      WITH
          MOVE N'WWTP' TO N'/var/opt/mssql/data/WWTP.mdf',
          MOVE N'WWTP_log' TO N'/var/opt/mssql/data/WWTP_log.ldf',
          REPLACE,
          RECOVERY,
          STATS = 10"
```

Verify database is online:

```bash
docker exec -it wwtp-sql /opt/mssql-tools18/bin/sqlcmd \
  -S localhost \
  -U sa \
  -P "$SQL_PASSWORD" \
  -C \
  -Q "SELECT name, state_desc FROM sys.databases WHERE name LIKE 'WWTP%';"
```

Verify important row counts:

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

Last verified restore test on May 15, 2026 showed:

```text
ScadaHistoryPoints            48300
DailyEntries                      0
WellReadings                      0
FiltrationPlantReadings           0
Wells                            10
ValidMeterLocations              12
```

Counts may be higher if newer data has been added.

---

## 13. Deploy Well Readings app

```bash
cd /home/brandon/docker-stacks/well-readings

docker compose --env-file /home/brandon/docker-stacks/.env up -d
```

Check logs:

```bash
docker logs --tail=100 well-readings
```

Test locally from the server:

```bash
curl -I http://localhost:8080
```

---

## 14. Deploy Cloudflare Tunnel

```bash
cd /home/brandon/docker-stacks/cloudflared

docker compose --env-file /home/brandon/docker-stacks/.env up -d
```

Check logs:

```bash
docker logs --tail=100 cloudflared
```

Verify the public site loads through the Cloudflare hostname.

---

## 15. Deploy Watchtower

```bash
cd /home/brandon/docker-stacks/watchtower

docker compose --env-file /home/brandon/docker-stacks/.env up -d
```

Check:

```bash
docker logs --tail=100 watchtower
```

Recommended: exclude SQL Server from automatic updates with this label in the SQL compose file:

```yaml
labels:
  - "com.centurylinklabs.watchtower.enable=false"
```

---

## 16. Deploy SQL backup container

```bash
cd /home/brandon/docker-stacks/sql-backup

docker compose --env-file /home/brandon/docker-stacks/.env up -d --build
```

Confirm it has the correct environment variables:

```bash
docker inspect sql-backup --format '{{range .Config.Env}}{{println .}}{{end}}' | grep -E "ONEDRIVE|NAS|SQL"
```

Expected:

```text
SQL_CONTAINER_NAME=wwtp-sql
SQL_BACKUP_DATABASE=WWTP
SQL_BACKUP_PASSWORD=REDACTED
ONEDRIVE_REMOTE=
NAS_REMOTE=nas:West Jefferson/WWTP SQL Backups
```

---

## 17. Test SQL backup on the new VM

Run a manual backup:

```bash
docker start -a sql-backup
```

Check local backup:

```bash
ls -lht /home/brandon/sql-backups/*.bak | head
```

Check backup log:

```bash
tail -100 /home/brandon/sql-backups/backup.log
```

Verify NAS backup:

```bash
docker run --rm -it \
  -v /home/brandon/.config/rclone:/config/rclone \
  rclone/rclone:latest lsf "nas:West Jefferson/WWTP SQL Backups"
```

---

## 18. Add daily SQL backup cron job

```bash
crontab -e
```

Add:

```cron
0 2 * * * docker start -a sql-backup >> /home/brandon/sql-backups/cron.log 2>&1
```

Verify:

```bash
crontab -l
```

Check cron log after it runs:

```bash
tail -100 /home/brandon/sql-backups/cron.log
```

---

## 19. Verify all containers

```bash
docker ps --format "table {{.Names}}\t{{.Image}}\t{{.Status}}\t{{.Ports}}"
```

Expected important containers:

```text
wwtp-sql
well-readings
cloudflared
watchtower
sql-backup
portainer
```

Note: `sql-backup` may be stopped after running. That is normal.

---

## 20. Final application tests

Test these before shutting down the old VM:

- Well Readings app loads locally.
- Well Readings app loads through Cloudflare Tunnel.
- App can connect to SQL Server.
- A new database entry can be saved, if appropriate.
- SQL backup runs manually.
- SQL backup appears locally.
- SQL backup appears on NAS.
- Cron is scheduled.
- Portainer is reachable.
- Docker containers restart correctly after reboot.

Reboot test:

```bash
sudo reboot
```

After reboot:

```bash
docker ps
```

Then test the website again.

---

## 21. Keep the old VM temporarily

Do not delete the old VM immediately.

Recommended:

- Shut down the old VM after the new one is verified.
- Keep it available for several days.
- Do not run both production instances at the same time against the same public hostname unless intentionally switching traffic.

---

## Quick recovery commands

Show running containers:

```bash
docker ps --format "table {{.Names}}\t{{.Image}}\t{{.Ports}}"
```

Check SQL logs:

```bash
docker logs --tail=100 wwtp-sql
```

Check web app logs:

```bash
docker logs --tail=100 well-readings
```

Check Cloudflare logs:

```bash
docker logs --tail=100 cloudflared
```

Run backup:

```bash
docker start -a sql-backup
```

List local backups:

```bash
ls -lht /home/brandon/sql-backups/*.bak | head
```

List NAS backups:

```bash
docker run --rm -it \
  -v /home/brandon/.config/rclone:/config/rclone \
  rclone/rclone:latest lsf "nas:West Jefferson/WWTP SQL Backups"
```
