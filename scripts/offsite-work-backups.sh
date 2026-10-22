#!/usr/bin/env bash
# Off-host encrypted backup transfer for work Manhole Survey & MeshCentral
# Schedule AFTER both local jobs; does not alter either local backup script.
set -Eeuo pipefail
umask 077
export TZ=America/New_York
SRC_MANHOLE="/home/brandon/manhole-backups"
SRC_MESH="/home/brandon/meshcentral-backups"
CONFIG="/home/brandon/.config/rclone"
DEST="nas-crypt:"
RUN_DATE="$(date +%Y-%m-%d)"
LOCK="/tmp/wj-encrypted-offsite.lock"
mkdir -p /home/brandon/backup-logs
exec 9>"$LOCK"
flock -n 9 || { echo "Offsite transfer already active"; exit 1; }
[[ -f "$CONFIG/rclone.conf" ]] || { echo "Missing rclone.conf"; exit 1; }
[[ -d "$SRC_MANHOLE" && -d "$SRC_MESH" ]] || { echo "Missing backup source directory"; exit 1; }
rclone() {
  docker run --rm --network bridge \
    --mount "type=bind,src=$CONFIG,dst=/config/rclone,readonly" \
    --mount "type=bind,src=$SRC_MANHOLE,dst=/input/manhole,readonly" \
    --mount "type=bind,src=$SRC_MESH,dst=/input/mesh,readonly" \
    rclone/rclone:latest "$@"
}
# Crypt configuration sanity check, without printing credentials
backend="$(rclone config show nas-crypt | sed -n 's/^type = //p' | head -1)"
[[ "$backend" == "crypt" ]] || { echo "ERROR: nas-crypt is not type crypt"; exit 1; }
# Require today's successful manhole archive, not stale data.
mapfile -t manhole < <(find "$SRC_MANHOLE" -maxdepth 1 -type f -name "manhole-backup-${RUN_DATE}_*.zip" -printf '%f\n' | sort)
[[ "${#manhole[@]}" -gt 0 ]] || { echo "ERROR: no manhole backup made today"; exit 1; }
latest_manhole="${manhole[-1]}"
# Require a completed MeshCentral backup from today (YYYYMMDD), with checksum manifest
mesh_date="$(date +%Y%m%d)"
mapfile -t mesh < <(find "$SRC_MESH" -mindepth 1 -maxdepth 1 -type d -name "${mesh_date}-*" -printf '%f\n' | sort)
[[ "${#mesh[@]}" -gt 0 ]] || { echo "ERROR: no MeshCentral backup made today"; exit 1; }
latest_mesh="${mesh[-1]}"
[[ -f "$SRC_MESH/$latest_mesh/SHA256SUMS" ]] || { echo "ERROR: MeshCentral backup has no checksum manifest"; exit 1; }
(cd "$SRC_MESH/$latest_mesh" && sha256sum -c SHA256SUMS)
echo "Uploading Manhole ZIP: $latest_manhole"
rclone copyto "/input/manhole/$latest_manhole" "$DEST/manhole-survey/$latest_manhole" --retries 3
echo "Uploading MeshCentral complete backup directory: $latest_mesh"
rclone copy "/input/mesh/$latest_mesh" "$DEST/meshcentral/$latest_mesh" --retries 3
# Verify byte-for-byte readback of decrypted encrypted remote.
echo "Verifying Manhole ZIP by downloaded-byte comparison"
rclone check "/input/manhole/$latest_manhole" "$DEST/manhole-survey/$latest_manhole" --download --one-way
echo "Verifying MeshCentral archives by downloaded-byte comparison"
rclone check "/input/mesh/$latest_mesh" "$DEST/meshcentral/$latest_mesh" --download --one-way
echo "SUCCESS: Both today's backups are stored and verified through nas-crypt:"
echo "Remote retention has NOT been enabled until a full restore test."
