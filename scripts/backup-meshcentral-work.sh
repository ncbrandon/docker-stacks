#!/usr/bin/env bash
# MeshCentral work: consistent full-volume backup; run as the Docker-capable user.
# IMPORTANT: Backups contain server identity/private keys and account database.
set -Eeuo pipefail
umask 077
CONTAINER="meshcentral-work"
DEST="${MESH_BACKUP_DIR:-/home/brandon/meshcentral-backups}"
RETENTION_DAYS="${MESH_BACKUP_RETENTION_DAYS:-30}"
LOCK="/tmp/meshcentral-work-backup.lock"
mkdir -p "$DEST"
exec 9>"$LOCK"
flock -n 9 || { echo "Backup already running"; exit 1; }
command -v docker >/dev/null
command -v python3 >/dev/null
command -v tar >/dev/null
command -v sha256sum >/dev/null
stamp="$(date +%Y%m%d-%H%M%S)"
tmp="$(mktemp -d "$DEST/.incomplete-$stamp-XXXX")"
was_running=false
restarted=false
finish() {
  status=$?
  if [[ "$was_running" == true && "$restarted" == false ]]; then
    docker start "$CONTAINER" >/dev/null || echo "CRITICAL: failed to restart $CONTAINER" >&2
  fi
  if [[ -d "$tmp" ]]; then
    echo "Incomplete backup kept at: $tmp" >&2
  fi
  exit "$status"
}
trap finish EXIT INT TERM
docker inspect "$CONTAINER" >/dev/null
mounts="$(docker inspect -f '{{json .Mounts}}' "$CONTAINER")"
mapfile -t volumes < <(printf '%s' "$mounts" | python3 -c '
import json,sys
mounts=json.load(sys.stdin)
paths=["meshcentral-data","meshcentral-files","meshcentral-backups","meshcentral-web"]
for path in paths:
    target="/opt/meshcentral/"+path
    found=[m for m in mounts if m.get("Destination")==target and m.get("Type")=="volume"]
    if len(found)!=1: sys.exit("Required named volume missing or ambiguous: "+target)
    print(found[0]["Name"])
')
if [[ "${#volumes[@]}" -ne 4 ]]; then echo "Unable to identify four named volumes"; exit 1; fi
if [[ "$(docker inspect -f '{{.State.Running}}' "$CONTAINER")" == true ]]; then
  was_running=true
  echo "Stopping $CONTAINER to get consistent database and certificate backup..."
  docker stop --time 45 "$CONTAINER" >/dev/null
fi
for i in 0 1 2 3; do
  label=(meshcentral-data meshcentral-files meshcentral-backups meshcentral-web)
  echo "Backing up ${label[$i]} from Docker volume ${volumes[$i]}"
  docker run --rm --network none \
    --mount "type=volume,src=${volumes[$i]},dst=/source,readonly" \
    --mount "type=bind,src=$tmp,dst=/backup" \
    alpine:3.20 \
    tar -czf "/backup/${label[$i]}.tar.gz" -C /source .
done
if [[ "$was_running" == true ]]; then
  docker start "$CONTAINER" >/dev/null
  restarted=true
fi
(
  cd "$tmp"
  sha256sum ./*.tar.gz > SHA256SUMS
  sha256sum -c SHA256SUMS
)
cat > "$tmp/README.txt" <<EOF
MeshCentral work consistent Docker volume backup
Captured: $stamp
Container: $CONTAINER
Public hostname: remote.wjwater.org
Volume mapping:
meshcentral-data: ${volumes[0]}
meshcentral-files: ${volumes[1]}
meshcentral-backups: ${volumes[2]}
meshcentral-web: ${volumes[3]}
SECURITY: This archive contains account database and server private keys.
EOF
mv "$tmp" "$DEST/$stamp"
echo "SUCCESS: $DEST/$stamp"
find "$DEST" -mindepth 1 -maxdepth 1 -type d -name '20????????-??????' -mtime +"$RETENTION_DAYS" -print0 | xargs -0 -r rm -rf --
echo "Local retention applied; REMOTE/OFF-HOST BACKUP IS NOT CONFIGURED."
