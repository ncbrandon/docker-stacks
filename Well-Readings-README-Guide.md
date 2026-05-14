# Well Readings Website, SQL Server, Docker, GitHub, and Migration Guide

This README documents the setup and workflow used for the **Well Readings** website, SQL Server database, Docker/Portainer deployment, GitHub image publishing, Cloudflare Tunnel access, backups, and migration to a new Ubuntu Server VM.

It is written as a practical guide so the system can be rebuilt, moved, or troubleshot later.

---

## 1. Project Overview

The system is built around a local web application used for municipal water operations.

### Main pieces

| Piece | Purpose |
|---|---|
| **Well Readings web app** | ASP.NET Core web app for well readings, SCADA entry, filtration plant readings, reports, and related water system workflows |
| **SQL Server container** | Stores application data in the `WWTP` database |
| **Docker / Portainer** | Runs and manages the SQL Server, web app, Cloudflare Tunnel, Watchtower, and supporting containers |
| **GitHub / GHCR** | Stores the source code and publishes Docker images |
| **Cloudflare Tunnel** | Provides secure access to the locally hosted web app without exposing the server directly to the public internet |
| **Rclone / NAS backup** | Used or planned for SQL backups and off-server backup copies |
| **NC DWW Scraper** | Separate Python/Streamlit scraper project for NC Drinking Water Watch data |

---

## 2. Main Names and Values Used

### Server and host context

- Docker host: **Ubuntu Server VM**
- VM runs inside **VirtualBox** on a Windows machine
- Docker is managed with **Portainer**
- Existing app files path used on VM: `/opt/well-readings`
- SQL Server should stay private and should **not** be exposed to the internet

### Containers

| Container | Image | Purpose |
|---|---|---|
| `wwtp-sql` | `mcr.microsoft.com/mssql/server:2022-latest` | SQL Server database |
| `well-readings` | `ghcr.io/ncbrandon/well-readings-app:latest` | ASP.NET Core web app |
| `cloudflared` | `cloudflare/cloudflared:latest` | Cloudflare Tunnel |
| `watchtower` | `containrrr/watchtower:latest` | Optional automatic image update checker |
| `portainer` | `portainer/portainer-ce:latest` | Docker management UI |
| `nc-dww-scraper` | local/custom Streamlit image | NC Drinking Water Watch scraper |

### Docker volumes

| Volume | Purpose |
|---|---|
| `ms_sql_server_sql_data` | SQL Server database files |
| `portainer_data` | Portainer settings |
| `well-readings` | App-related persistent files, if used by the stack |

### Database

- Primary database name: `WWTP`
- SQL Server container: `wwtp-sql`
- SQL Server port internally: `1433`
- SQL login is used instead of Windows authentication
- SQL Server should remain private, for example only reachable from the LAN/VM network or Docker network

---

## 3. Website Project

The main website project is the **Well Readings** ASP.NET Core application.

Known project/repo names and paths:

- Repo/project name: `Well-Readings-App`
- Project folder/name: `Well Readings`
- Example Windows project path:

```text
C:\Users\wwtp\OneDrive - Town of West Jefferson\wjwater\Well Entry Website\Well-Readings-App\Well Readings
```

- Example project file:

```text
Well Readings.csproj
```

- Publish output:

```text
bin\Release\net8.0\publish\
```

When manually publishing to the Linux server, copy the **contents** of the publish folder into:

```text
/opt/well-readings
```

The publish folder should contain files such as:

```text
WellReadings.dll
appsettings.json
wwwroot/
```

---

## 4. Important Website Pages and Features

### Main pages worked on

| Page | Purpose |
|---|---|
| `/ScadaEntry` | Manual SCADA/well entry page |
| `/MonthlyReport` | Monthly reporting workflow |
| `/DistributionPoints` | Distribution sample location setup/entry |
| NC DWW scraper pages | Attempted .NET integration, later removed in favor of separate Python/Streamlit app |

### `/ScadaEntry`

The `/ScadaEntry` page was adjusted so that well tiles display in **2 columns on mobile** instead of one.

The page includes client-side behavior that:

- Fetches readings by date
- Submits manual readings
- Saves local draft data to browser `localStorage`
- Uses API routes like:

```text
/api/scada/manual-entry
/api/scada/entry-by-date?date=...
```

### Distribution point naming

A naming issue was fixed for distribution sample locations.

Known example:

- Display/entry needed to use:

```text
1 S. Jefferson Avenue
```

instead of:

```text
S Jefferson Avenue
001 - S. Jefferson Avenue
```

The remaining issue noted was that the **New Entry** section of `/DistributionPoints` still showed the older dropdown value:

```text
001 - S. Jefferson Avenue
```

---

## 5. SQL Server Setup

SQL Server runs as a Docker container.

### Container name

```text
wwtp-sql
```

### Image

```text
mcr.microsoft.com/mssql/server:2022-latest
```

### Database

```text
WWTP
```

### SQL Server port

SQL Server listens on port `1433`.

During testing, it was exposed like this:

```text
0.0.0.0:1433->1433/tcp
```

For the final/secure setup, the recommended approach is:

- Keep SQL Server private
- Do **not** expose port `1433` to the public internet
- Prefer Docker internal networking between the web app and SQL Server
- Only expose SQL to the host/LAN if absolutely needed for management

---

## 6. SQL Server Stack Example

A clean Docker Compose pattern for SQL Server is:

```yaml
services:
  wwtp-sql:
    image: mcr.microsoft.com/mssql/server:2022-latest
    container_name: wwtp-sql
    restart: unless-stopped
    environment:
      ACCEPT_EULA: "Y"
      MSSQL_PID: "Express"
      SA_PASSWORD: "${SA_PASSWORD}"
    volumes:
      - ms_sql_server_sql_data:/var/opt/mssql
      - ./backups:/var/opt/mssql/backup
    networks:
      - wwtp-net
    # For better security, avoid publishing this unless needed:
    # ports:
    #   - "1433:1433"

volumes:
  ms_sql_server_sql_data:
    external: true

networks:
  wwtp-net:
    external: true
```

Create the shared network first if it does not already exist:

```bash
docker network create wwtp-net
```

Create the SQL volume first if it does not already exist:

```bash
docker volume create ms_sql_server_sql_data
```

---

## 7. Web App Stack Example

The web app uses the image published to GitHub Container Registry:

```text
ghcr.io/ncbrandon/well-readings-app:latest
```

Example Compose stack:

```yaml
services:
  well-readings:
    image: ghcr.io/ncbrandon/well-readings-app:latest
    container_name: well-readings
    restart: unless-stopped
    environment:
      ASPNETCORE_ENVIRONMENT: "Production"
      ASPNETCORE_URLS: "http://+:8080"
      ConnectionStrings__DefaultConnection: "Server=wwtp-sql,1433;Database=WWTP;User Id=sa;Password=${SA_PASSWORD};TrustServerCertificate=True;"
    ports:
      - "8080:8080"
    networks:
      - wwtp-net
      - tunnel
    depends_on:
      - wwtp-sql

networks:
  wwtp-net:
    external: true
  tunnel:
    external: true
```

Notes:

- The app connects to SQL Server using the Docker container name `wwtp-sql`.
- `ConnectionStrings__DefaultConnection` overrides the appsettings connection string inside the container.
- The app listens on port `8080`.
- Cloudflare Tunnel should route to:

```text
http://well-readings:8080
```

when `cloudflared` and `well-readings` share the same Docker network.

---

## 8. GitHub and Container Registry Workflow

The app was moved toward a GitHub-based workflow where the source code lives in GitHub and the deployed Docker image is pulled from GitHub Container Registry.

### Image name

```text
ghcr.io/ncbrandon/well-readings-app:latest
```

### General workflow

1. Make code changes locally.
2. Commit changes to Git.
3. Push to GitHub.
4. GitHub builds/publishes a new Docker image.
5. The server pulls the latest image.
6. Portainer redeploys the stack.

Typical Git commands:

```bash
git status
git add .
git commit -m "Describe the change"
git push
```

On the server, update the running app by pulling the new image and recreating the container.

From a Compose folder:

```bash
docker compose pull well-readings
docker compose up -d well-readings
```

In Portainer, the equivalent is generally:

- Go to the stack
- Pull/re-pull latest image
- Redeploy the stack

---

## 9. Pull and Redeploy vs Re-pull Image and Redeploy

These two phrases are similar but slightly different depending on the Portainer screen.

### Pull and redeploy

This means:

1. Download the latest version of the image from the registry.
2. Recreate the container using that new image.

This is what you usually want after pushing a new app image to GitHub Container Registry.

### Re-pull image and redeploy

This means essentially the same thing in Portainer wording:

1. Force Portainer/Docker to check the registry again.
2. Pull the latest image.
3. Recreate the container.

### Redeploy without pulling

This only recreates the container using the image already present on the server.

That will **not** pick up new GitHub image changes unless the new image has already been pulled.

---

## 10. Watchtower

Watchtower can automatically check for updated container images.

Container:

```text
watchtower
```

Image:

```text
containrrr/watchtower:latest
```

### Once-per-day Watchtower schedule

Watchtower uses a cron-style schedule.

Example: check once per day at 3:00 AM:

```yaml
services:
  watchtower:
    image: containrrr/watchtower:latest
    container_name: watchtower
    restart: unless-stopped
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock
    environment:
      WATCHTOWER_SCHEDULE: "0 0 3 * * *"
      WATCHTOWER_CLEANUP: "true"
```

### Updating immediately when Watchtower only checks once per day

If you make a change and want it live immediately, manually pull and redeploy:

```bash
docker compose pull well-readings
docker compose up -d well-readings
```

Or use Portainer’s pull/redeploy option.

---

## 11. Cloudflare Tunnel

Cloudflare Tunnel is used to expose the local web app securely without opening inbound firewall ports.

Container:

```text
cloudflared
```

Image:

```text
cloudflare/cloudflared:latest
```

Preferred access model:

- Host the app locally
- Expose it through Cloudflare Tunnel
- Use Cloudflare Access with one-time PIN login
- Avoid exposing SQL Server

### Docker network requirement

The `cloudflared` container must be on the same Docker network as the web app container.

Example network:

```text
tunnel
```

Create it if needed:

```bash
docker network create tunnel
```

Then both `cloudflared` and `well-readings` should be attached to `tunnel`.

Cloudflare public hostname should point to:

```text
http://well-readings:8080
```

For the Streamlit scraper, Cloudflare should point to:

```text
http://nc-dww-scraper:8501
```

---

## 12. NC Drinking Water Watch Scraper

A separate Python/Streamlit app was created for NC Drinking Water Watch sample scraping.

### Purpose

The scraper pulls Non-TCR sample data from NC Drinking Water Watch and can filter to detects only.

### Main container

```text
nc-dww-scraper
```

### Streamlit port

```text
8501
```

### Typical URL target through Docker network

```text
http://nc-dww-scraper:8501
```

### Known water system

West Jefferson:

```text
WEST JEFFERSON, TOWN OF
NC0105010
tinwsys_is_number=22040
tinwsys_st_code=NC
```

### CSV data file inside container

```text
/app/water_systems.csv
```

Example fields:

```text
key,name,tinwsys_is_number,tinwsys_st_code,wsnumber
```

Example entry:

```text
west-jefferson,"West Jefferson, Town Of",22040,NC,NC0105010
```

### Detect filter logic

The Streamlit app included a “Detects only” option.

General logic:

- Exclude results where the sample value contains `<`
- Or use the `less_than_indicator` field where available

### Typical Docker Compose pattern

```yaml
services:
  nc-dww-scraper:
    build: .
    container_name: nc-dww-scraper
    restart: unless-stopped
    ports:
      - "8501:8501"
    volumes:
      - ./output:/app/output
    networks:
      - tunnel

networks:
  tunnel:
    external: true
```

---

## 13. Database Tables and Schema Notes

Observed/known tables include:

```text
__EFMigrationsHistory
DailyEntries
FiltrationPlantReadings
WellReadings
ScadaHistoryPoints
ValidMeterLocations
Wells
```

Important observed row counts from earlier troubleshooting:

| Table | Approx/observed rows |
|---|---:|
| `dbo.ScadaHistoryPoints` | 47840 |
| `dbo.__EFMigrationsHistory` | 12 |
| `dbo.ValidMeterLocations` | 12 |
| `dbo.Wells` | 10 |
| `dbo.DailyEntries` | 0 |
| `dbo.FiltrationPlantReadings` | 0 |
| `dbo.WellReadings` | 0 |

### `DailyEntries`

Known fields:

```text
Id uniqueidentifier
EntryDate date
EntryTime time
CreatedAt datetime2
```

### `FiltrationPlantReadings`

Known fields include:

```text
Id uniqueidentifier
DailyEntryId uniqueidentifier
FilterPlantMeterReading decimal
MtJeffersonMeterReading decimal
Chlorine decimal nullable
Phosphate decimal nullable
Ph decimal nullable
Temperature decimal nullable
```

### SCADA history

The app uses `ScadaHistoryPoints` for imported/historical SCADA values.

The CT reporting script also queries:

```text
dbo.ScadaHistoryPoints
```

---

## 14. Entity Framework and App Startup

The ASP.NET Core app uses Entity Framework Core.

Observed project namespaces/classes included:

```text
Well_Readings.Data
Well_Readings.DTOs
Well_Readings.Models
DailyEntryService.cs
AppDbContext
```

EF Core runs database checks/migrations at startup.

Observed EF query pattern:

```sql
SELECT OBJECT_ID(N'[__EFMigrationsHistory]');
```

A prior issue happened where app startup failed because it could not connect to SQL Server.

Things to check if the app fails at startup:

1. Is `wwtp-sql` running?
2. Is the `WWTP` database present?
3. Is the connection string correct?
4. Are both containers on the same Docker network?
5. Is SQL Server ready before the app starts?
6. Does the SQL login have access to `WWTP`?
7. Are migrations valid for the current database?

---

## 15. SQL Backup Commands

Before changing SQL stacks, restoring databases, or moving servers, create a `.bak` backup.

### Create backup folder inside container

```bash
docker exec -it wwtp-sql mkdir -p /var/opt/mssql/backup
```

### Run SQL backup

Replace the password placeholder with the real SQL password.

```bash
docker exec -it wwtp-sql /opt/mssql-tools18/bin/sqlcmd \
  -S localhost \
  -U sa \
  -P '<SA_PASSWORD>' \
  -C \
  -Q "BACKUP DATABASE [WWTP] TO DISK = N'/var/opt/mssql/backup/WWTP.bak' WITH INIT, COMPRESSION, STATS = 10;"
```

### Copy backup from container to host

```bash
docker cp wwtp-sql:/var/opt/mssql/backup/WWTP.bak ./WWTP.bak
```

### Safer dated backup name

```bash
BACKUP_NAME="WWTP_$(date +%Y-%m-%d_%H-%M-%S).bak"

docker exec -it wwtp-sql /opt/mssql-tools18/bin/sqlcmd \
  -S localhost \
  -U sa \
  -P '<SA_PASSWORD>' \
  -C \
  -Q "BACKUP DATABASE [WWTP] TO DISK = N'/var/opt/mssql/backup/$BACKUP_NAME' WITH INIT, COMPRESSION, STATS = 10;"

docker cp "wwtp-sql:/var/opt/mssql/backup/$BACKUP_NAME" "./$BACKUP_NAME"
```

---

## 16. SQL Restore Commands

Copy the backup into the SQL Server container:

```bash
docker cp ./WWTP.bak wwtp-sql:/var/opt/mssql/backup/WWTP.bak
```

Check logical file names:

```bash
docker exec -it wwtp-sql /opt/mssql-tools18/bin/sqlcmd \
  -S localhost \
  -U sa \
  -P '<SA_PASSWORD>' \
  -C \
  -Q "RESTORE FILELISTONLY FROM DISK = N'/var/opt/mssql/backup/WWTP.bak';"
```

Observed logical name:

```text
WWTP
```

A restore command pattern:

```bash
docker exec -it wwtp-sql /opt/mssql-tools18/bin/sqlcmd \
  -S localhost \
  -U sa \
  -P '<SA_PASSWORD>' \
  -C \
  -Q "RESTORE DATABASE [WWTP] FROM DISK = N'/var/opt/mssql/backup/WWTP.bak' WITH REPLACE, MOVE N'WWTP' TO N'/var/opt/mssql/data/WWTP.mdf', MOVE N'WWTP_log' TO N'/var/opt/mssql/data/WWTP_log.ldf', STATS = 10;"
```

If the logical log file name is not `WWTP_log`, use the name returned by `RESTORE FILELISTONLY`.

---

## 17. SQL Troubleshooting

### Error 4060

Error:

```text
Cannot open database "WWTP" requested by the login.
Login failed for user 'sa'.
```

Likely causes:

- The `WWTP` database does not exist
- The restore did not complete
- The app connection string points to the wrong database
- SQL Server is using a different volume than expected
- The database is offline/recovering
- SQL login does not have the expected permissions

Check databases:

```bash
docker exec -it wwtp-sql /opt/mssql-tools18/bin/sqlcmd \
  -S localhost \
  -U sa \
  -P '<SA_PASSWORD>' \
  -C \
  -Q "SELECT name FROM sys.databases;"
```

### Backup restore access denied

Error example:

```text
Operating system error 5(Access is denied.)
```

Common causes:

- Backup file is not inside the container
- SQL Server process cannot read the file path
- File copied to wrong folder
- Host path was used instead of container path

Safer approach:

1. Copy the `.bak` into the container.
2. Use a path under:

```text
/var/opt/mssql/backup/
```

3. Run restore from that path.

---

## 18. Docker Volume Backup and Restore

### Back up a Docker volume

Example for SQL volume:

```bash
docker run --rm \
  -v ms_sql_server_sql_data:/volume \
  -v "$PWD":/backup \
  alpine \
  tar czf /backup/ms_sql_server_sql_data.tar.gz -C /volume .
```

Example for Portainer:

```bash
docker run --rm \
  -v portainer_data:/volume \
  -v "$PWD":/backup \
  alpine \
  tar czf /backup/portainer_data.tar.gz -C /volume .
```

Example for well-readings volume:

```bash
docker run --rm \
  -v well-readings:/volume \
  -v "$PWD":/backup \
  alpine \
  tar czf /backup/well-readings.tar.gz -C /volume .
```

### Restore a Docker volume

Create the volume first:

```bash
docker volume create ms_sql_server_sql_data
```

Restore:

```bash
docker run --rm \
  -v ms_sql_server_sql_data:/volume \
  -v "$PWD":/backup \
  alpine \
  sh -c "cd /volume && tar xzf /backup/ms_sql_server_sql_data.tar.gz"
```

---

## 19. Moving to a New Ubuntu Server VM

Copying Portainer stacks alone is **not enough**.

You also need:

- Docker installed
- Portainer installed
- Portainer data restored if keeping existing Portainer setup
- Docker named volumes copied/restored
- SQL `.bak` backup copied/restored
- Stack YAML files copied
- `.env` files copied
- Secrets/passwords copied securely
- Bind-mounted folders copied
- Docker networks recreated
- Cloudflare Tunnel token/config copied or recreated
- Rclone config copied if using OneDrive backup
- NAS mount config copied if using NAS backup
- Cron jobs/systemd timers copied if backup scripts rely on them
- App image access to GHCR confirmed

### Recommended migration sequence

1. Build/install the new Ubuntu Server VM.
2. Install Docker.
3. Install Portainer.
4. Create required Docker networks:

```bash
docker network create wwtp-net
docker network create tunnel
```

5. Create/restore Docker volumes:

```bash
docker volume create ms_sql_server_sql_data
docker volume create portainer_data
docker volume create well-readings
```

6. Restore `portainer_data` if migrating Portainer itself.
7. Deploy SQL Server stack.
8. Restore `WWTP.bak` into SQL Server.
9. Confirm database exists:

```sql
SELECT name FROM sys.databases;
```

10. Deploy web app stack.
11. Confirm web app can connect to SQL.
12. Deploy or reconnect Cloudflare Tunnel.
13. Test the website through local IP and Cloudflare URL.
14. Reconfigure Watchtower if desired.
15. Restore backup scripts/rclone/NAS mount.
16. Run a test backup.
17. Keep the old VM untouched until the new VM is fully verified.

---

## 20. Fresh Docker and Portainer Install

On a fresh Ubuntu Server VM:

```bash
sudo apt update
sudo apt install -y ca-certificates curl gnupg
```

Install Docker using Docker’s official convenience script:

```bash
curl -fsSL https://get.docker.com | sudo sh
```

Add your user to the Docker group:

```bash
sudo usermod -aG docker $USER
```

Log out and back in, then test:

```bash
docker version
docker ps
```

Create Portainer volume:

```bash
docker volume create portainer_data
```

Run Portainer:

```bash
docker run -d \
  --name portainer \
  --restart=unless-stopped \
  -p 8000:8000 \
  -p 9443:9443 \
  -v /var/run/docker.sock:/var/run/docker.sock \
  -v portainer_data:/data \
  portainer/portainer-ce:latest
```

Open Portainer:

```text
https://SERVER-IP:9443
```

---

## 21. Backups to NAS and OneDrive

The goal was to back up SQL Server to:

1. NAS
2. OneDrive

### NAS context

NAS IP:

```text
192.168.0.125
```

Attempted mount:

```bash
sudo mount -t cifs //192.168.0.125/volume1 /mnt/wwtp-nas-backups \
  -o credentials=/etc/samba/wwtp-nas.credentials,iocharset=utf8,vers=3.0
```

Known issue:

```text
mount error(13): Permission denied
```

Things to check:

- NAS username/password
- Share name
- Whether `volume1` is a share or only a Synology volume path
- SMB permissions on the NAS
- Whether the NAS user has read/write access
- Correct CIFS version
- Credentials file permissions

Recommended credentials file permissions:

```bash
sudo chmod 600 /etc/samba/wwtp-nas.credentials
```

### Rclone / OneDrive

Rclone was used to access OneDrive.

Example test command:

```bash
docker run --rm -it \
  -v /home/brandon/.config/rclone:/config/rclone \
  rclone/rclone:latest lsd onedrive:
```

Known OneDrive folders included:

```text
Attachments
Desktop
Documents
Personal Vault
Pictures
Pump Station Sheets
```

Rclone config path:

```text
/home/brandon/.config/rclone
```

When migrating servers, copy:

```text
~/.config/rclone/rclone.conf
```

---

## 22. Backup Script Checklist

A good SQL backup script should:

1. Generate a dated backup filename.
2. Run `BACKUP DATABASE [WWTP]`.
3. Copy the `.bak` from the container to the host.
4. Copy the backup to NAS.
5. Copy the backup to OneDrive using rclone.
6. Log success/failure.
7. Delete old local backups after a retention period.
8. Be run by cron or a systemd timer.

Example filename pattern:

```text
WWTP_YYYY-MM-DD_HH-MM-SS.bak
```

Important: after setting up automated backups, test that more than the first backup is created. A previous issue was that automatic backups appeared to create only the initial backup and then no more.

---

## 23. Monthly CT Calculation / Spreadsheet Workflow

There is a related reporting workflow for filling CT calculation spreadsheets.

Known folder/template context:

```text
Filter Plant Script and Reports
Blank CT Calculations.xlsx
EMOR FILES
```

Known script:

```text
fill_ct_calculations.py
fill_ct_calculations_fixed.py
```

Known CLI flags included:

```text
--year
--month
--sql-server
--sql-database
--sql-username
--sql-password
```

Example pattern:

```bash
py fill_ct_calculations.py --year 2026 --month 4
```

The script queries SQL Server and uses SCADA data to populate the CT workbook.

Important note:

- The `Flow` cell is in MGD.
- It is derived from the `Filter Plant Meter Reading` gallons value converted to MGD.

Common Windows issue:

When passing Windows paths to Python, avoid unescaped backslashes.

Use raw strings in Python:

```python
r"C:\Users\wwtp\OneDrive - Town of West Jefferson\..."
```

Or use forward slashes:

```text
C:/Users/wwtp/OneDrive - Town of West Jefferson/...
```

---

## 24. SCADA Location and Metric Notes

Known SCADA locations included:

```text
Filter Plant
Filter 1
Filter 2
Park Well
Park Well A
Park Well B
Park Well Site
Beaver Creek Generator
Beaver Creek Pump 1
Beaver Creek Pump 2
Dogget Pump 1
Dogget Pump 2
Greenfield Generator
Greenfield Pump 1
Greenfield Pump 2
Helen Blevins Pump 1
Helen Blevins Pump 2
Oakwood
New
Ray
Reeves Well
Reeves Well A
Reeves Well Site
Woods
Catawissa
```

Known metric types included:

```text
Chlorine
Feed Flow
Feed Pressure
Filtrate Flow
Filtrate Pressure
Generator Status
Meter Reading
pH
Phosphate
Pressure Decay
Pump Status
Temperature
TMP
Total Filter Run Time
Total Filtration Flow Yesterday
```

Example source columns:

```text
Cl-F
pH-F
PO4-F
Filter Plant
```

---

## 25. Common Build and Code Issues Encountered

### EF Core / DTO type mismatches

Errors were seen in `DailyEntryService.cs` such as:

```text
Argument 1: cannot convert from 'System.Guid' to 'int'
Cannot implicitly convert type 'HashSet<System.Guid>' to 'HashSet<int>'
'WellReading' does not contain a definition for 'Value'
'WellReadingDto' does not contain a definition for 'Value'
```

This means the service code, DTOs, and entity models were not aligned.

The key lesson:

- Check whether IDs are `Guid` or `int`
- Check whether reading values are named `Value` or something more specific
- Keep DTO property names aligned with entity property names

### NC DWW .NET integration issues

An attempted .NET scraper integration caused several issues, including:

- Missing `ConfigurePrimaryHttpMessageHandler`
- Missing `_logger`
- Bracket/EOF issues
- Package/project path confusion
- NC DWW HTTP 403 responses

The .NET integration was later removed/reverted, and the Python/Streamlit scraper became the cleaner path.

---

## 26. Docker and Command Troubleshooting Notes

### `docker cp` from remote Linux host to Windows path

A previous issue happened when trying to copy between Docker/Linux and a Windows path from the wrong place.

Rule:

- `docker cp` runs from the machine where Docker is running.
- If Docker is on the Ubuntu VM, copy to a Linux path first.
- Then transfer the file from Linux to Windows separately if needed.

### Cloudflared container does not include `wget`

A test like this failed because `wget` was not inside the `cloudflared` image:

```bash
docker exec -it cloudflared wget -qO- http://nc-dww-scraper:8501
```

Use another container for network testing:

```bash
docker run --rm --network tunnel curlimages/curl http://nc-dww-scraper:8501
```

or:

```bash
docker run --rm --network tunnel curlimages/curl http://well-readings:8080
```

---

## 27. VirtualBox / Windows Host Notes

The Ubuntu Docker server runs as a VirtualBox VM on Windows.

Issues encountered:

- `VBoxManage setproperty autostartdbpath C:\VirtualBoxAutostart` returned `VERR_NOT_SUPPORTED`
- NSSM was explored to run the VM at boot
- Windows service logon problems occurred
- PIN vs password issues came up when using a Microsoft account
- Temporary password testing allowed service startup progress

Key point:

If relying on the Windows host, make sure the Ubuntu VM starts automatically after reboot, otherwise the website, SQL Server, Cloudflare Tunnel, and backups will all stay offline.

---

## 28. Security Notes

### Do not commit secrets

Do not commit these to GitHub:

```text
SA_PASSWORD
ConnectionStrings with real passwords
Cloudflare Tunnel token
rclone.conf
NAS credentials
appsettings.Production.json with secrets
```

Use one of these instead:

- Portainer environment variables
- `.env` files kept off GitHub
- GitHub Actions secrets
- Docker secrets where appropriate

### SQL Server

SQL Server should stay private.

Avoid exposing this publicly:

```text
1433
```

Preferred app-to-SQL connection:

```text
Server=wwtp-sql,1433;Database=WWTP;User Id=sa;Password=...;TrustServerCertificate=True;
```

### Cloudflare

Only the web app should be public through Cloudflare Tunnel.

Do not expose:

- SQL Server
- Portainer
- SSH
- Backup shares

unless intentionally protected.

---

## 29. Recommended Repo Structure

A clean repo structure could look like this:

```text
Well-Readings-App/
├── Well Readings/
│   ├── Pages/
│   ├── Models/
│   ├── DTOs/
│   ├── Data/
│   ├── Services/
│   ├── wwwroot/
│   ├── appsettings.json
│   ├── Program.cs
│   └── Well Readings.csproj
├── docker/
│   ├── docker-compose.web.yml
│   ├── docker-compose.sql.yml
│   └── docker-compose.scraper.yml
├── scripts/
│   ├── backup_wwtp_sql.sh
│   ├── restore_wwtp_sql.sh
│   └── fill_ct_calculations.py
├── docs/
│   └── migration-guide.md
├── .github/
│   └── workflows/
│       └── docker-publish.yml
├── .gitignore
└── README.md
```

---

## 30. Recommended `.gitignore`

Use a `.gitignore` that excludes secrets, build output, local database files, and generated backups:

```gitignore
# Build output
bin/
obj/
.vs/
.vscode/

# User/local settings
*.user
*.suo

# Secrets
.env
.env.*
appsettings.Production.json
appsettings.Local.json
rclone.conf
*.credentials

# SQL backups
*.bak
*.trn
*.mdf
*.ldf

# Logs
*.log
logs/

# Python
__pycache__/
*.pyc
.venv/
venv/

# Excel temp files
~$*.xlsx
```

---

## 31. Deployment Checklist

Use this checklist after pushing a website change.

### On local development machine

```bash
git status
git add .
git commit -m "Update well readings app"
git push
```

### Confirm GitHub action/image build succeeds

Check GitHub Actions for the repository.

Expected image:

```text
ghcr.io/ncbrandon/well-readings-app:latest
```

### On server / Portainer

Either use Portainer pull/redeploy, or run:

```bash
docker compose pull well-readings
docker compose up -d well-readings
```

### Confirm container status

```bash
docker ps
```

### Check logs

```bash
docker logs --tail=100 well-readings
```

### Test locally

```bash
curl http://localhost:8080
```

or from the Docker network:

```bash
docker run --rm --network tunnel curlimages/curl http://well-readings:8080
```

### Test through Cloudflare

Open the public Cloudflare Tunnel URL and verify:

- Site loads
- Login/access works
- `/ScadaEntry` works
- SQL-backed pages load
- New entries save correctly

---

## 32. Full Rebuild Checklist

Use this if the server is lost or you are rebuilding from scratch.

1. Install Ubuntu Server.
2. Install Docker.
3. Install Portainer.
4. Create Docker networks:

```bash
docker network create wwtp-net
docker network create tunnel
```

5. Create Docker volumes:

```bash
docker volume create ms_sql_server_sql_data
docker volume create portainer_data
docker volume create well-readings
```

6. Deploy SQL Server stack.
7. Restore the latest `WWTP.bak`.
8. Confirm the `WWTP` database exists.
9. Deploy web app stack using:

```text
ghcr.io/ncbrandon/well-readings-app:latest
```

10. Set the correct environment variables.
11. Deploy Cloudflare Tunnel.
12. Confirm Cloudflare routes to:

```text
http://well-readings:8080
```

13. Restore rclone config if needed.
14. Restore NAS mount config if needed.
15. Restore backup scripts.
16. Set up cron/systemd backup schedule.
17. Run a test backup.
18. Test the website.
19. Keep the old server/backup until the new system is verified.

---

## 33. Useful Commands

### Show running containers

```bash
docker ps --format "table {{.ID}}\t{{.Names}}\t{{.Image}}\t{{.Ports}}"
```

### Show Docker volumes

```bash
docker volume ls
```

### Show Docker networks

```bash
docker network ls
```

### Inspect app logs

```bash
docker logs --tail=100 well-readings
```

### Inspect SQL logs

```bash
docker logs --tail=100 wwtp-sql
```

### Open shell in SQL container

```bash
docker exec -it wwtp-sql bash
```

### Query SQL databases

```bash
docker exec -it wwtp-sql /opt/mssql-tools18/bin/sqlcmd \
  -S localhost \
  -U sa \
  -P '<SA_PASSWORD>' \
  -C \
  -Q "SELECT name FROM sys.databases;"
```

### Restart web app

```bash
docker restart well-readings
```

### Restart SQL

```bash
docker restart wwtp-sql
```

### Check app image

```bash
docker images | grep well-readings
```

### Pull latest app image

```bash
docker pull ghcr.io/ncbrandon/well-readings-app:latest
```

---

## 34. Things to Verify Periodically

- SQL backups are still running daily
- Backups are actually reaching NAS
- Backups are actually reaching OneDrive
- Cloudflare Tunnel is still connected
- Watchtower is not updating something unexpectedly
- GitHub Actions image builds are still passing
- The server reboots and the Ubuntu VM starts automatically
- Docker containers restart after VM reboot
- SQL database can be restored from the latest backup
- Portainer stack files are exported or stored somewhere safe
- Secrets are not committed to GitHub

---

## 35. Current Recommended Architecture

The clean target architecture is:

```text
Windows Host
└── VirtualBox Ubuntu Server VM
    ├── Docker
    │   ├── Portainer
    │   ├── SQL Server container: wwtp-sql
    │   │   └── Database: WWTP
    │   ├── Web app container: well-readings
    │   │   └── Image: ghcr.io/ncbrandon/well-readings-app:latest
    │   ├── Cloudflare Tunnel container: cloudflared
    │   ├── Watchtower container
    │   └── Optional Streamlit scraper: nc-dww-scraper
    ├── SQL backups
    ├── rclone config for OneDrive
    └── NAS mount/config for local backup
```

Public access should flow like this:

```text
User browser
→ Cloudflare Access / Tunnel
→ cloudflared container
→ well-readings container
→ wwtp-sql container
```

SQL Server should not be exposed directly to the public internet.

---

## 36. Notes for Future Work

Potential future improvements:

- Store all stack YAML files in the GitHub repo under `docker/`
- Add a dedicated `docs/` folder for migration and backup guides
- Add a tested `backup_wwtp_sql.sh` script
- Add a tested `restore_wwtp_sql.sh` script
- Add health checks to Docker Compose
- Add a SQL readiness wait to the web app stack
- Move recurring backup scheduling to a systemd timer
- Add Cloudflare Access policies for specific users/emails
- Keep the NC DWW scraper separate from the ASP.NET app unless there is a strong reason to integrate it
- Regularly test restoring `WWTP.bak` into a temporary SQL Server container

---

## 37. Minimal Emergency Recovery

If the system is down and needs to be recovered quickly, the minimum required pieces are:

1. A working Docker host
2. SQL Server container
3. Latest `WWTP.bak`
4. Web app image:

```text
ghcr.io/ncbrandon/well-readings-app:latest
```

5. Correct connection string
6. Cloudflare Tunnel or local network access

Fast recovery order:

```text
Install Docker
→ Start SQL Server
→ Restore WWTP.bak
→ Start well-readings app
→ Point Cloudflare Tunnel to well-readings:8080
→ Test site
```

---

## 38. Important Reminder

Portainer stacks define how containers should run, but they do **not** automatically include everything needed to rebuild the system.

Always separately preserve:

- SQL database backups
- Docker volumes
- Environment variables
- Secrets
- Stack YAML files
- Cloudflare Tunnel config/token
- Rclone config
- NAS credentials
- Backup scripts
- Any bind-mounted folders
