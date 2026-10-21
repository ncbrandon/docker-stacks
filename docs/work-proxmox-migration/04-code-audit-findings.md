# 04 — GitHub source review: concrete findings and actions

**Review date:** 2026-10-21. Findings below refer to files actually fetched from the user's GitHub repositories. They do **not** demonstrate that the same version is deployed on the production VM.

## Confirmed source facts
| Component | Inspected file | Finding | Recovery/security action |
|---|---|---|---|
| Well Readings publish | [workflow](https://github.com/ncbrandon/Well-Readings-App/blob/main/.github/workflows/docker-publish.yml) | Workflow builds using `./Well Readings/Dockerfile` (not root `Dockerfile`) and publishes mutable tag `ghcr.io/ncbrandon/well-readings-app:latest`. | Record the last known-good image digest and its source commit, confirm GitHub Actions completed and ensure old image can be recovered. |
| NC DWW scraper | [Dockerfile](https://github.com/ncbrandon/nc-dww-scraper/blob/main/Dockerfile) | Python 3.12 slim image; Streamlit port 8501; first-run copy of `water_systems.csv` to `/app/data/water_systems.csv`; output under `/app/output`; launch flags explicitly set `--server.enableCORS=false` and `--server.enableXsrfProtection=false`. | Ensure `/app/data` and `/app/output` persistence if needed, document the actual Compose bindings. **Review disabling both CORS/XSRF protections; restrict the application behind trusted access controls.** |
| Well-depth grapher | [Dockerfile](../../well-depth-grapher/Dockerfile) | Python 3.12 slim, Streamlit 8501; Python packages installed from `requirements.txt`. | Preserve source files and test build against the current SQL backend. |
| Well-depth grapher dependencies | [requirements](../../well-depth-grapher/requirements.txt) | `streamlit`, `pandas`, `plotly`, `pymssql`, `openpyxl`, `reportlab`, `matplotlib` **have no pinned versions**. | Pin/test dependency versions and build from locked packages or known-good image digest before disaster-recovery certification. |
| SQL Server | [compose](../../wwtp-sql/docker-compose.yml) | Mutable `2022-latest` tag, exposes host port 1433, external data volume. | Preserve data separately; test a pinned version and restrict SQL port to trusted hosts. |
| Cloudflared | [compose](../../cloudflared/docker-compose.yml) | Runs with token-based tunnel; external networks required. | Save routing/Access policies and escrow token securely; do not put it in Git. |
| Well Readings | [compose](../../well-readings/docker-compose.yml) | GHCR `latest` plus Watchtower opt-in label; SQL connection supplied by variable. | Disable untested rolling updates during cutover; capture actual secret securely and image digest. |

## Specific concerns
1. **Reproducibility:** `latest` tags and unpinned Python dependencies can change a fresh install unexpectedly. Create a tested deployment manifest with commit SHAs and image digests.
2. **NC DWW scraper security:** Launching Streamlit with XSRF protection disabled merits explicit review. Do not forward publicly without an authenticated upstream and appropriate CSRF/CORS threat assessment.
3. **Source path assumptions:** The Well Readings Dockerfile is under `Well Readings/`; a nonexistent root Dockerfile is not an error in the repository if its workflow uses the correct nested path.
4. **Persistence:** `/app/data`, `/app/output`, SQL volumes, uploaded files, SQLite and cron-managed backups must be verified from running container mounts. Source repository alone cannot demonstrate persistence.
5. **Not verified:** Full inventories of every file in all nine repositories, actual running app versions, current database health, security configuration of Cloudflare/Portainer, and full end-to-end restore.

## Next audit evidence required
Obtain **sanitized** Portainer stack exports, volume/host mount inventory, cron entries, tested database backup manifests and Proxmox backup settings from the old production environment. Never commit unredacted `docker inspect`, `.env`, TLS keys, credentials or live customer data into this public repository.
