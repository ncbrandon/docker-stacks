# 05 — MeshCentral work installation (observed October 22, 2026)

## Current installation
- Source host: existing Town work Ubuntu Docker VM, LAN IP recorded as `192.168.0.95`.
- Docker container: `meshcentral-work`; image `ghcr.io/ylianst/meshcentral:1.3.0`.
- Public hostname: `remote.wjwater.org` through existing work Cloudflare Tunnel.
- LAN URL: `https://192.168.0.95:8443` (may no longer match advertised hostname; use public hostname for normal login).
- Port mapping: host TCP 8443 -> container 443.
- Networks: Compose default plus existing external `tunnel` network shared with `cloudflared`.
- Dynamic configuration disabled; configuration is maintained inside persistent data volume.
- Cloudflare route: `https://meshcentral-work:443`. Cloudflare's **No TLS Verify** was temporarily enabled to pass the self-signed origin certificate; **replace with trusted origin CA/certificate validation before signoff**.
- MeshCentral administrator web login reached through permanent hostname after updating certificate hostname and allowed origin. **No unattended agent functionality verified yet.**

## Current Portainer Compose (provided by operator)
```yaml
services:
  meshcentral:
    image: ghcr.io/ylianst/meshcentral:1.3.0
    container_name: meshcentral-work
    restart: unless-stopped
    networks:
      - default
      - tunnel
    environment:
      NODE_ENV: production
      DYNAMIC_CONFIG: "false"
    ports:
      - "8443:443"
    volumes:
      - meshcentral-work-data:/opt/meshcentral/meshcentral-data
      - meshcentral-work-files:/opt/meshcentral/meshcentral-files
      - meshcentral-work-backups:/opt/meshcentral/meshcentral-backups
      - meshcentral-work-web:/opt/meshcentral/meshcentral-web
networks:
  tunnel:
    external: true
volumes:
  meshcentral-work-data:
  meshcentral-work-files:
  meshcentral-work-backups:
  meshcentral-work-web:
```

**Warning:** Docker Compose normally project-prefixes these volume keys (likely `meshcentral-work_meshcentral-work-data`, etc.). Verify actual names with `docker inspect meshcentral-work` and `docker volume ls`; do not assume the keys above equal Docker's real volume names.

## Persistent MeshCentral configuration
The operator adjusted `/opt/meshcentral/meshcentral-data/config.json` to advertise:
- `settings.cert = "remote.wjwater.org"`
- `settings.port = 443`
- `settings.aliasPort = 443`
- `domains[""].certUrl = "https://remote.wjwater.org"`
- `domains[""].allowedOrigin = ["remote.wjwater.org"]`

Settings were written in the data volume with a prior copy named `config.json.before-remote-hostname`. Back up the **entire** data volume (including generated MeshCentral CA, agent-server keys and database) rather than only this JSON. Do not publish private keys, certificates containing secret private keys, account databases, password/session material, or signed agent installers.

**Caution:** The `certUrl` value is not proof that agent certificate pinning works through Cloudflare. Before enrolling users or critical devices, inspect the public endpoint's actual TLS certificate and test a single agent from outside LAN, its WebSocket channel, persistence after restart, and agent reconnect. Depending on Cloudflare's certificate and MeshCentral reverse-proxy configuration, adjust certificate handling using the upstream MeshCentral guide. Cloudflare Access one-time PIN is not automatically compatible with unattended agents.

## Migration procedure
1. Keep work and home MeshCentral **entirely separate**. Restrict work admin access and enable MFA before production agents.
2. Back up all four **actual** Docker volumes, preserving permissions and timestamps; keep an encrypted copy away from the source VM. Include Portainer Compose and Cloudflare mapping/policies separately.
3. Restore same volume contents to target work Proxmox Docker VM, preserving all MeshCentral identity keys and database. Do **not** launch a fresh server that generates different keys and expect old agents to reconnect.
4. Create external `tunnel` network on new Docker VM (or adapt the Compose and tunnel design). Validate HTTPS origin and DNS routing, then move Cloudflare tunnel connection after isolating old and new servers.
5. Verify admin login, device groups/permissions and a pre-enrolled test agent connecting after the hostname points to the new VM. Test remote desktop, reconnect after reboot and restore a backup.
6. Review use of host port 8443; avoid unnecessary LAN exposure once tunnel access is proven. Enforce MFA and least-privileged per-device access, especially on municipal systems.

## Remaining acceptance items
- [ ] Confirm actual named-volume identities, sizes and encrypted off-host backup.
- [ ] Confirm agent connectivity from outside LAN.
- [ ] Verify origin certificate trust; remove No TLS Verify workaround.
- [ ] Enable MFA and confirm enrollment and per-user access policies.
- [ ] Restore complete instance on isolated test Docker VM.
- [ ] Preserve original agent identity through simulated Proxmox migration.
- [ ] Review and approve access to any SCADA/OT devices separately.
