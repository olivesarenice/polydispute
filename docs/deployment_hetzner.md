# Hetzner Cloud VPS Deployment Guide

Step-by-step runbook for deploying Polydispute to a Hetzner Cloud VPS instance using Docker Compose and Caddy (automatic HTTPS).

---

## 1. Recommended Instance Sizing

| Provider | Plan | vCPU | RAM | Disk | Cost | Purpose |
|---|---|---|---|---|---|---|
| Hetzner Cloud | **CX22** | 2 | 4 GB | 40 GB NVMe | ~€3.79 / mo | Production Web Dashboard (FastAPI + React SPA) |
| Hetzner Cloud | **CPX31** | 4 | 8 GB | 160 GB NVMe | ~€13.60 / mo | Production Web Dashboard + Continuous Data Pipeline Ingestion |

* **OS**: Ubuntu 24.04 LTS (x86_64)
* **Location**: Nuremberg (nbg1) or Falkenstein (fsn1)

---

## 2. Server Bootstrap & Docker Engine Setup

SSH into your fresh Hetzner VPS:

```bash
ssh root@<YOUR_SERVER_IP>
```

### 2.1 Update System & Install Essentials
```bash
apt update && apt upgrade -y
apt install -y curl git ufw jq htop ca-certificates gnupg
```

### 2.2 Configure Firewall (UFW)
```bash
ufw default deny incoming
ufw default allow outgoing
ufw allow 22/tcp     # SSH
ufw allow 80/tcp     # HTTP (Caddy / Let's Encrypt challenge)
ufw allow 443/tcp    # HTTPS
ufw enable
```

### 2.3 Install Docker Engine & Docker Compose Plugin
```bash
# Add Docker's official GPG key
install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
chmod a+r /etc/apt/keyrings/docker.asc

# Add the repository to Apt sources
echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu \
  $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | \
  tee /etc/apt/sources.list.d/docker.list > /dev/null

apt update
apt install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

# Verify installation
docker --version
docker compose version
```

---

## 3. Clone Repository & Configure Secrets

### 3.1 Clone the Project
```bash
git clone https://github.com/<your-org>/polydispute.git /opt/polydispute
cd /opt/polydispute
```

### 3.2 Configure Environment Variables
Create the production `.env` file:

```bash
cp .env.example .env
nano .env
```

Ensure the following production credentials are set:
```bash
PIPELINE_ENV=prod
MOTHERDUCK_TOKEN="ey..."
MOTHERDUCK_DATABASE=polydispute_prod
LOG_LEVEL=INFO
```

*(Optional: If you use Doppler on the VPS)*:
```bash
# Install Doppler CLI
(curl -Ls --tlsv1.2 --proto "=https" --retry 3 https://cli.doppler.com/install.sh || wget -t 3 -qO- https://cli.doppler.com/install.sh) | sudo sh

# Configure project & service token
doppler setup --no-interactive --token "<DOPPLER_SERVICE_TOKEN>"
doppler secrets download --no-file --format env > .env
```

---

## 4. Launch Polydispute Container

Build the multi-stage Docker image and start the daemon.

> [!NOTE]
> The web container is decoupled from `pipeline/`. It packages only the compiled React SPA (`frontend/dist`) and analytical API (`backend/`), locking down dependencies via the root `pyproject.toml` and `uv.lock` for a lightweight ~220 MB image footprint.

```bash
docker compose up -d --build
```

### 4.1 Verify Container State
```bash
docker compose ps
```
Output:
```
NAME              IMAGE                 COMMAND                  SERVICE       CREATED         STATUS                   PORTS
polydispute-app   polydispute-app       "uvicorn backend.src…"   polydispute   5 seconds ago   Up 4 seconds (healthy)   0.0.0.0:8000->8000/tcp
```

### 4.2 Test Endpoint from VPS Localhost
```bash
# Test API Health
curl -s http://localhost:8000/api/health | jq .

# Test Frontend SPA Delivery
curl -I http://localhost:8000/
# Expected: HTTP/1.1 200 OK, Content-Type: text/html; charset=utf-8
```

---

## 5. Domain & Automated HTTPS Setup (Caddy)

Caddy provides zero-configuration automated SSL certificates via Let's Encrypt.

### 5.1 Install Caddy on Ubuntu
```bash
apt install -y debian-keyring debian-archive-keyring apt-transport-https curl
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' | tee /etc/apt/sources.list.d/caddy-stable.list
apt update
apt install -y caddy
```

### 5.2 Configure Caddyfile
Edit `/etc/caddy/Caddyfile`:

```bash
nano /etc/caddy/Caddyfile
```

Replace the contents with:
```caddy
polydispute.yourdomain.com {
    reverse_proxy 127.0.0.1:8000 {
        header_up Host {host}
        header_up X-Real-IP {remote_host}
        header_up X-Forwarded-For {remote_host}
        header_up X-Forwarded-Proto {scheme}
    }
}
```

### 5.3 Restart Caddy
```bash
systemctl restart caddy
systemctl status caddy
```

Point your DNS `A` record (`polydispute.yourdomain.com`) to `<YOUR_SERVER_IP>`. Caddy will automatically issue and renew TLS certificates.

---

## 6. Maintenance & Operational Commands

### View Application Logs
```bash
docker compose logs -f --tail=100
```

### Pull Updates & Redeploy
```bash
cd /opt/polydispute
git pull origin main
docker compose up -d --build
```

### Container Restart & Stop
```bash
docker compose restart
docker compose down
```
