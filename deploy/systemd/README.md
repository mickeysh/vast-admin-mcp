# Run VAST Admin MCP with systemd

This guide shows how to run **VAST Admin MCP** as a Linux systemd service using `systemctl`.

Use this when you want the MCP server always available over **HTTP** (or HTTPS) on a host, for remote AI clients or shared team access.

> **Note:** systemd is for **HTTP transport**. Desktop apps that talk over stdio (Cursor, Claude Desktop, etc.) do not use this service — they start the MCP process themselves.

---

## Prerequisites

- Linux host with `systemd` (RHEL/CentOS, Ubuntu, Debian, Rocky, Alma, etc.)
- Python 3.10+ and `pip`
- Network access from the host to your VAST cluster(s)
- `jq` installed (required by vast-admin-mcp)

```bash
# RHEL / CentOS / Rocky / Alma
sudo yum install jq

# Ubuntu / Debian
sudo apt-get install jq
```

---

## 1. Install vast-admin-mcp

Install as root (or the service user) so the binary is available system-wide:

```bash
sudo pip install 'vast-admin-mcp[http]'
```

Confirm the binary path (needed in the unit file):

```bash
which vast-admin-mcp
# Typical results:
#   /usr/local/bin/vast-admin-mcp
#   /usr/bin/vast-admin-mcp
```

---

## 2. Configure VAST clusters

Run setup once (as the same user the service will run as — see step 3):

```bash
vast-admin-mcp setup
```

This creates:

| Path | Purpose |
|------|---------|
| `~/.vast-admin-mcp/config.json` | Cluster credentials and optional HTTP settings |
| `~/.vast-admin-mcp/vast_admin_mcp.log` | Application log |

Verify clusters are reachable:

```bash
vast-admin-mcp list clusters
```

---

## 3. Choose a service user

**Recommended:** run as a dedicated non-root user.

```bash
sudo useradd --system --create-home --home-dir /var/lib/vast-admin-mcp --shell /sbin/nologin vastmcp
```

Then install and configure for that user:

```bash
sudo -u vastmcp -H pip install --user 'vast-admin-mcp[http]'
sudo -u vastmcp -H bash -lc 'vast-admin-mcp setup'
```

Find the binary for that user:

```bash
sudo -u vastmcp -H bash -lc 'which vast-admin-mcp || echo $HOME/.local/bin/vast-admin-mcp'
```

**Simpler option:** run as `root` and use the system-wide install from step 1. Prefer a dedicated user in production.

---

## 4. (Recommended) Set an auth token

Generate a token and store it for the service:

```bash
# Generate a token
TOKEN="vamt_$(openssl rand -base64 32 | tr -d '=+/')"
echo "$TOKEN"

# Persist for systemd (root example)
sudo mkdir -p /etc/vast-admin-mcp
echo "VAST_ADMIN_MCP_AUTH_TOKEN=$TOKEN" | sudo tee /etc/vast-admin-mcp/environment
sudo chmod 600 /etc/vast-admin-mcp/environment
```

Clients must send:

```http
Authorization: Bearer <your-token>
```

---

## 5. Install the systemd unit

Copy the sample unit (or create the file below):

```bash
sudo cp deploy/systemd/vast-admin-mcp.service /etc/systemd/system/vast-admin-mcp.service
```

Or create it manually:

```bash
sudo tee /etc/systemd/system/vast-admin-mcp.service >/dev/null <<'EOF'
[Unit]
Description=VAST Admin MCP Server (HTTP)
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=vastmcp
Group=vastmcp
WorkingDirectory=/var/lib/vast-admin-mcp
EnvironmentFile=-/etc/vast-admin-mcp/environment
# Adjust ExecStart path if `which vast-admin-mcp` differs
ExecStart=/var/lib/vast-admin-mcp/.local/bin/vast-admin-mcp mcp --transport http --host 0.0.0.0 --port 8000
Restart=on-failure
RestartSec=5
# Optional hardening
NoNewPrivileges=true
PrivateTmp=true

[Install]
WantedBy=multi-user.target
EOF
```

### Adjust these values

| Setting | What to change |
|---------|----------------|
| `User` / `Group` | Service account (`vastmcp` or `root`) |
| `WorkingDirectory` / home | Must match that user’s home so `~/.vast-admin-mcp` resolves |
| `ExecStart` | Full path from `which vast-admin-mcp` |
| `--host` | `0.0.0.0` for network access; `127.0.0.1` for localhost only |
| `--port` | Default `8000` |
| `--read-write` | Add only if create/update tools are required |

**Read-write example** (use only when needed):

```ini
ExecStart=/usr/local/bin/vast-admin-mcp mcp --transport http --host 0.0.0.0 --port 8000 --read-write
```

**HTTPS example** (after generating certs):

```bash
# As the service user
vast-admin-mcp gencert --cn mcp.example.com --san mcp.example.com
```

```ini
ExecStart=/usr/local/bin/vast-admin-mcp mcp --transport http --host 0.0.0.0 --port 8000 \
  --ssl-cert /var/lib/vast-admin-mcp/.vast-admin-mcp/ssl/cert.pem \
  --ssl-key /var/lib/vast-admin-mcp/.vast-admin-mcp/ssl/key.pem
```

---

## 6. Enable and start with systemctl

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now vast-admin-mcp
```

---

## 7. Verify

```bash
# Service state
sudo systemctl status vast-admin-mcp

# Follow logs
sudo journalctl -u vast-admin-mcp -f

# Health check (HTTP)
curl -sS http://127.0.0.1:8000/health

# Health check with bearer token (if configured)
curl -sS -H "Authorization: Bearer $TOKEN" http://127.0.0.1:8000/health
```

Endpoints:

| Endpoint | URL |
|----------|-----|
| MCP | `http://<hostname>:8000/mcp/` |
| Health | `http://<hostname>:8000/health` |

---

## Everyday systemctl commands

```bash
# Start / stop / restart
sudo systemctl start vast-admin-mcp
sudo systemctl stop vast-admin-mcp
sudo systemctl restart vast-admin-mcp

# Enable / disable start on boot
sudo systemctl enable vast-admin-mcp
sudo systemctl disable vast-admin-mcp

# Status and recent logs
sudo systemctl status vast-admin-mcp
sudo journalctl -u vast-admin-mcp -n 100 --no-pager
```

After editing the unit file:

```bash
sudo systemctl daemon-reload
sudo systemctl restart vast-admin-mcp
```

---

## Firewall (if needed)

```bash
# firewalld (RHEL family)
sudo firewall-cmd --permanent --add-port=8000/tcp
sudo firewall-cmd --reload

# ufw (Ubuntu)
sudo ufw allow 8000/tcp
```

---

## Connect an MCP client

Point the client at the HTTP MCP URL, for example:

```
http://mcp.example.com:8000/mcp/
```

If `VAST_ADMIN_MCP_AUTH_TOKEN` is set, configure the same bearer token in the client.

---

## Troubleshooting

| Symptom | What to check |
|---------|----------------|
| `Failed to start` | `sudo journalctl -u vast-admin-mcp -xe` |
| `vast-admin-mcp: not found` | Fix `ExecStart` path; run `which vast-admin-mcp` as the service user |
| `config file ... not found` | Run `vast-admin-mcp setup` as the **same** user in the unit file |
| Port already in use | Change `--port` or stop the conflicting process |
| Clients get 401 | Confirm `VAST_ADMIN_MCP_AUTH_TOKEN` in `/etc/vast-admin-mcp/environment` matches the client |
| Cannot reach VAST clusters | Check network/DNS/proxy from the host; verify with `vast-admin-mcp list clusters` as the service user |

Application log (in addition to journald):

```bash
# Path depends on the service user home
sudo -u vastmcp tail -f /var/lib/vast-admin-mcp/.vast-admin-mcp/vast_admin_mcp.log
```

---

## Uninstall

```bash
sudo systemctl disable --now vast-admin-mcp
sudo rm -f /etc/systemd/system/vast-admin-mcp.service
sudo systemctl daemon-reload
# Optional: remove config / user / token file
# sudo rm -rf /etc/vast-admin-mcp /var/lib/vast-admin-mcp
# sudo userdel vastmcp
```
