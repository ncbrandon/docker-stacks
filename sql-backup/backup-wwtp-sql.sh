#!/usr/bin/env bash
set -euo pipefail

CONTAINER_NAME="${SQL_CONTAINER_NAME:-wwtp-sql}"
DATABASE_NAME="${SQL_BACKUP_DATABASE:-WWTP}"
SQL_USER="${SQL_USER:-sa}"
SQL_PASSWORD="${SQL_BACKUP_PASSWORD:?SQL_BACKUP_PASSWORD is required}"

HOST_BACKUP_DIR="/backups"
CONTAINER_BACKUP_DIR="/var/opt/mssql/backups"

ONEDRIVE_REMOTE="${ONEDRIVE_REMOTE:-}"
NAS_REMOTE="${NAS_REMOTE:-}"

TIMESTAMP="$(date +'%Y-%m-%d_%H-%M-%S')"
BACKUP_FILE="${DATABASE_NAME}_${TIMESTAMP}.bak"
CONTAINER_BACKUP_PATH="${CONTAINER_BACKUP_DIR}/${BACKUP_FILE}"
HOST_BACKUP_PATH="${HOST_BACKUP_DIR}/${BACKUP_FILE}"

LOG_FILE="${HOST_BACKUP_DIR}/backup.log"

mkdir -p "$HOST_BACKUP_DIR"

echo "==================================================" | tee -a "$LOG_FILE"
echo "Starting backup at $(date)" | tee -a "$LOG_FILE"
echo "Database: $DATABASE_NAME" | tee -a "$LOG_FILE"
echo "Backup file: $BACKUP_FILE" | tee -a "$LOG_FILE"

docker exec "$CONTAINER_NAME" /opt/mssql-tools18/bin/sqlcmd \
  -S localhost \
  -U "$SQL_USER" \
  -P "$SQL_PASSWORD" \
  -C \
  -Q "BACKUP DATABASE [${DATABASE_NAME}] TO DISK = N'${CONTAINER_BACKUP_PATH}' WITH INIT, COMPRESSION, STATS = 10"

if [ ! -f "$HOST_BACKUP_PATH" ]; then
  echo "ERROR: Backup file was not found on host/container-mounted path: $HOST_BACKUP_PATH" | tee -a "$LOG_FILE"
  exit 1
fi

echo "Backup created:" | tee -a "$LOG_FILE"
ls -lh "$HOST_BACKUP_PATH" | tee -a "$LOG_FILE"

if [ -n "$ONEDRIVE_REMOTE" ]; then
  echo "Copying to OneDrive remote: $ONEDRIVE_REMOTE" | tee -a "$LOG_FILE"
  rclone copy "$HOST_BACKUP_PATH" "$ONEDRIVE_REMOTE" --progress
fi

if [ -n "$NAS_REMOTE" ]; then
  echo "Copying to NAS remote: $NAS_REMOTE" | tee -a "$LOG_FILE"
  rclone copy "$HOST_BACKUP_PATH" "$NAS_REMOTE" --progress
fi

echo "Removing local backups older than 14 days..." | tee -a "$LOG_FILE"
find "$HOST_BACKUP_DIR" -name "${DATABASE_NAME}_*.bak" -type f -mtime +14 -delete

echo "Backup completed successfully at $(date)" | tee -a "$LOG_FILE"
