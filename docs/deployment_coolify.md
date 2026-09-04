# Coolify Deployment Runbook

Guide for deploying the Polydispute unified web application (FastAPI + React SPA) on Hetzner using **Coolify** and Docker Compose.

---

## Architecture in Coolify

```
Internet (HTTPS)
      │
      ▼
Coolify Traefik Reverse Proxy (Automated Let's Encrypt SSL)
      │
      ▼ Internal Port 8000
Container: polydispute-app
  ├── entrypoint.sh (Transparent Doppler secret injector)
  ├── FastAPI Analytical Engine (/api/*)
  └── Static Pre-compiled React SPA (/*, /assets/*)
      │
      ▼ SQL queries over TLS
MotherDuck Cloud Data Warehouse (md:polydispute_prod)
```

---

## 1. Quick Deploy Steps in Coolify

### Step 1: Add New Project in Coolify
1. Open your Coolify dashboard (e.g. `https://coolify.yourdomain.com`).
2. Navigate to **Projects** $\rightarrow$ select or create your project.
3. Click **+ New Resource** $\rightarrow$ select **Docker Compose** or **GitHub / Git Repository**.

### Step 2: Configure Repository Source
* **Repository URL**: `https://github.com/<your-org>/polydispute`
* **Branch**: `main`
* **Build Pack**: `Docker Compose`
* **Base Directory**: `/`
* **Docker Compose Location**: `/docker-compose.yml`

### Step 3: Configure Environment Variables
In Coolify's **Environment Variables** tab for the resource (or at the Project Shared Variables level), configure **only**:

```env
DOPPLER_TOKEN=dp.st.prod.XXXXX...
DOPPLER_CONFIG=prd
```

> **Zero Duplicate Keys**: `docker-compose.yml` does not declare individual keys (`MOTHERDUCK_TOKEN`, `SENTRY_DSN`, etc.). The image's `ENTRYPOINT ["doppler", "run", "--"]` fetches and injects all project secrets into memory directly from Doppler upon startup, exactly like `pipeline/Dockerfile.worker`.

### Step 4: Configure Domain & Routing
1. In the service settings, set your **Domains**:
   ```
   https://polydispute.yourdomain.com
   ```
2. Ensure the container port is set to **`8000`** (Coolify routes traffic from your public domain to container port 8000).
3. Traefik will automatically provision and renew Let's Encrypt SSL certificates.

### Step 5: Deploy
Click **Deploy** in the top right corner.
Coolify will:
1. Clone the repository.
2. Build Stage 1 (compiling React 18 frontend with Node 20).
3. Build Stage 2 (installing Python 3.12 dependencies with `uv sync`).
4. Start the container with healthcheck monitoring (`/api/health`).
5. Wire Traefik routing once healthy.

---

## 2. Verification & Health Monitoring

### Healthcheck Configuration
Coolify monitors container health via the built-in Docker healthcheck in `docker-compose.yml`:
```yaml
healthcheck:
  test: ["CMD", "curl", "-f", "http://localhost:8000/api/health"]
  interval: 20s
  timeout: 5s
  retries: 3
  start_period: 15s
```

### Checking Logs in Coolify
* Click on **Logs** inside the Coolify resource view to see real-time Uvicorn access and application logs.
* Healthy startup will log:
  ```
  [Polydispute] Starting Polydispute API on 0.0.0.0:8000
  INFO: Uvicorn running on http://0.0.0.0:8000
  ```

---

## 3. Auto-Deployments via Webhooks

To trigger redeployments on every `git push`:
1. In Coolify, go to the **Webhooks** tab of the Polydispute resource.
2. Copy the **Deploy Webhook URL**.
3. In GitHub, navigate to **Settings** $\rightarrow$ **Webhooks** $\rightarrow$ **Add webhook**.
4. Paste the URL, set content type to `application/json`, and trigger on `push` events.
