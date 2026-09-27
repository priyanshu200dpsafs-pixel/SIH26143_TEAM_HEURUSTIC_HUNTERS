# AEGIS-SAR Production Deployment & Administration Guide

**Autonomous Maritime Oil Spill Intelligence & Vessel Attribution Platform**  
*Smart India Hackathon (SIH) Problem Statement 26143*

---

## 1. Architecture Overview

AEGIS-SAR is built for mission-critical maritime surveillance operations. It integrates:
- **FastAPI Core Engine**: High-throughput asynchronous backend servicing REST APIs, WebSocket telemetry, and long-running physics/deep learning jobs.
- **Scientific Physics & Neural Engines**: U-Net 4-Class SAR segmentation (PyTorch), Runge-Kutta 4th Order Lagrangian trajectory hindcasting, and MarineCadastre/AIS kinematics correlation.
- **MapLibre GL Tactical Interface**: Single-page application compiled to static production assets served with immutable cache headers.
- **Append-Only Audit & Forensic Sealer**: Cryptographic SHA-256 ledger integrity sealing for prosecutorial dossiers (UNCLOS & MARPOL 73/78 Annex I compliance).

---

## 2. Target System Requirements

### Hardware Specifications
- **CPU**: 4+ Cores (x86_64 or ARM64 / Apple Silicon).
- **RAM**: 8 GB minimum (16 GB recommended for high-resolution Sentinel-1 GRD TIFF processing).
- **Storage**: 50 GB+ SSD recommended for SAR imagery cache, ERA5/OSCAR environmental grids, and report archives.
- **OS**: Ubuntu 22.04 / 24.04 LTS, Debian 12, or macOS 14+ (Darwin).

### Required System Packages
```bash
sudo apt-get update && sudo apt-get install -y \
    build-essential \
    libgdal-dev \
    gdal-bin \
    libproj-dev \
    python3-dev \
    python3-venv \
    nodejs \
    npm \
    nginx \
    certbot \
    python3-certbot-nginx
```

---

## 3. Deployment Methods

### Method A: Native Host Deployment (Production Service)

#### Step 1: Clone Repository & Set Permissions
```bash
git clone https://github.com/organization/oil-spill-attribution.git /opt/aegis-sar
cd /opt/aegis-sar
chown -R www-data:www-data /opt/aegis-sar
```

#### Step 2: Virtual Environment & Python Dependencies
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip setuptools wheel
pip install -r requirements.txt
```

#### Step 3: Compile Frontend Production Bundle
```bash
cd frontend
npm ci
npm run build
cd ..
```
*Verify that `frontend/dist/` contains `index.html` and static assets.*

#### Step 4: Configure Environment & Secrets
Create `/opt/aegis-sar/.env` with strict permissions (`chmod 600 .env`):
```ini
# Copernicus CDSE Sentinel-1 Ingestion Credentials
COPERNICUS_CLIENT_ID=your_cdse_client_id_here
COPERNICUS_CLIENT_SECRET=your_cdse_client_secret_here

# Live AIS Feed Authentication (Optional - Leave blank for Replay/Benchmark mode)
AISSTREAM_API_KEY=

# Platform Operations
PORT=8000
HOST=127.0.0.1
ENVIRONMENT=production
```

#### Step 5: Systemd Service Configuration
Create `/etc/systemd/system/aegis.service`:
```ini
[Unit]
Description=AEGIS-SAR Maritime Spill Intelligence & Vessel Attribution Platform
After=network.target

[Service]
Type=simple
User=www-data
Group=www-data
WorkingDirectory=/opt/aegis-sar
EnvironmentFile=/opt/aegis-sar/.env
ExecStart=/opt/aegis-sar/.venv/bin/python -m uvicorn src.api.main:app --host 127.0.0.1 --port 8000 --workers 4
Restart=always
RestartSec=5
LimitNOFILE=65536

[Install]
WantedBy=multi-user.target
```

Enable and start the service:
```bash
sudo systemctl daemon-reload
sudo systemctl enable aegis.service
sudo systemctl start aegis.service
sudo systemctl status aegis.service
```

---

### Method B: Docker & Docker Compose Deployment

#### Step 1: Build & Launch Multi-Stage Containers
```bash
docker compose build --no-cache
docker compose up -d
```

#### Step 2: Verify Container Health
```bash
docker compose ps
docker compose logs -f backend
```

---

## 4. Nginx Reverse Proxy with WebSocket Support & SSL

Create `/etc/nginx/sites-available/aegis.conf`:
```nginx
map $http_upgrade $connection_upgrade {
    default upgrade;
    '' close;
}

server {
    listen 80;
    server_name surveillance.maritime.domain;

    client_max_body_size 500M;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;

        # WebSocket Upgrade Headers
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection $connection_upgrade;

        # Standard Proxy Headers
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # Timeouts for long-running Lagrangian simulations
        proxy_read_timeout 300s;
        proxy_send_timeout 300s;
    }
}
```

Enable site and acquire Let's Encrypt SSL certificate:
```bash
sudo ln -s /etc/nginx/sites-available/aegis.conf /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx
sudo certbot --nginx -d surveillance.maritime.domain
```

---

## 5. Automated Backup & Disaster Recovery

AEGIS-SAR includes cryptographic backup and restore scripts ensuring non-repudiation and complete state recovery.

### Running an Automated Backup
```bash
./scripts/backup_data.sh
```
This archives:
- Incident registries and GeoJSON layers (`data/results/incidents/`)
- Ingestion ledger tracking Sentinel-1 scenes (`data/ledger/ingestion_ledger.json`)
- Compiled forensic dossiers & briefs (`data/reports/`)
- Append-only tamper-evident audit logs (`data/audit/audit_log.jsonl`)
- Platform configuration profiles (`config/`)
- Computes SHA-256 hash stored alongside archive (`aegis_backup_<TIMESTAMP>.tar.gz.sha256`).

### Automated Nightly Cron Job
Add to root crontab (`sudo crontab -e`):
```cron
0 2 * * * /opt/aegis-sar/scripts/backup_data.sh >> /var/log/aegis_backup.log 2>&1
```

### Performing Disaster Recovery Restore
To recover from an archive:
```bash
./scripts/restore_data.sh backups/aegis_backup_20260915_000000Z.tar.gz
```
The script validates the SHA-256 checksum before extracting into an isolated staging buffer and atomically restoring data.

---

## 6. System Observability & Metrics

AEGIS-SAR provides a dedicated system diagnostics endpoint for Prometheus or automated monitoring agents:

- **Health Check Endpoint**: `GET /api/system/health`
  - Returns `{"status": "READY", "mode": "REPLAY", "uptime": "..."}`
- **Operational Metrics Endpoint**: `GET /api/system/metrics`
  - Returns process memory (MB), CPU thread usage, persistent incident counts, ledger tracking stats, live AIS buffer observations, and background jobs.
- **Audit Log Verification**: `GET /api/system/audit?limit=50`
  - Returns immutable operator actions.
