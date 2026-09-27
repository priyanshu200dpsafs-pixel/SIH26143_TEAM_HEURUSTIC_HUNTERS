# AIS Provider Configuration & Integration Guide
**System**: Autonomous Maritime Oil Spill Intelligence Platform  
**Problem Statement 26143**: *“Leveraging satellite imagery to determine Oil spills at sea along with AIS data correlations to identify vessel responsible for the spill.”*

---

## 1. Overview
The platform supports pluggable, provider-agnostic maritime AIS ingestion. Under **Phase 5B**, the system is fully engineered to connect to legitimate live AIS transponder feeds without scraping, hacking, or fabricating positions.

When no credentials are provided, the system honestly reports:
```text
STATUS: NOT_CONFIGURED
Reason: no AIS provider credentials configured
```
Replay benchmark mode (`data_status=SIMULATED`, `mode=REPLAY`) remains operational for training, benchmarking, and demonstration.

---

## 2. Supported Legitimate Providers

### Option A: AISStream.io (Recommended for Real-Time Open Feeds)
- **Website**: [https://aisstream.io](https://aisstream.io)
- **Description**: Real-time terrestrial AIS stream offering free developer API keys.
- **Protocol**: WebSocket / REST proxy
- **Environment Configuration**:
  ```bash
  export AIS_PROVIDER="aisstream"
  export AIS_API_URL="wss://stream.aisstream.io/v0/stream"
  export AIS_API_KEY="<YOUR_AISSTREAM_API_KEY>"
  ```

### Option B: BarentsWatch / Norwegian Coastal Administration (Kystverket)
- **Website**: [https://barentswatch.no](https://barentswatch.no)
- **Description**: Open government AIS service for European and Arctic waters.
- **Protocol**: REST OAuth2 Bearer Token
- **Environment Configuration**:
  ```bash
  export AIS_PROVIDER="barentswatch"
  export AIS_API_URL="https://live.ais.barentswatch.no/v1/latest/combined"
  export AIS_API_KEY="<YOUR_OAUTH_TOKEN>"
  ```

### Option C: Spire Maritime 2.0 (Commercial Satellite AIS)
- **Website**: [https://spire.com/maritime/](https://spire.com/maritime/)
- **Description**: Global satellite + terrestrial satellite constellation coverage.
- **Protocol**: REST API
- **Environment Configuration**:
  ```bash
  export AIS_PROVIDER="spire"
  export AIS_API_URL="https://api.spire.com/v2/vessels"
  export AIS_API_KEY="<YOUR_SPIRE_TOKEN>"
  ```

### Option D: Generic REST Maritime Transponder Proxy
- **Description**: Standard JSON REST endpoint returning vessel arrays with coordinates, speeds, and timestamps.
- **Environment Configuration**:
  ```bash
  export AIS_PROVIDER="generic_rest"
  export AIS_API_URL="https://your-maritime-proxy.org/api/v1/positions"
  export AIS_API_KEY="<YOUR_API_KEY>"
  ```

---

## 3. Configuration File (`config/ais.yaml`)

Edit [`config/ais.yaml`](file:///Users/priyanshu/Desktop/oil-spill-attribution/config/ais.yaml) to switch operating modes:

```yaml
provider:
  mode: live  # Set to 'live' for real feeds, or 'replay' for controlled benchmarks

replay:
  enabled: true
  benchmark_dir: "data/ais/synthetic/benchmarks"
  default_scenario: 1

live:
  enabled: true
  provider: "generic_rest"  # or aisstream / spire / barentswatch
  endpoint: "https://your-maritime-proxy.org/api/v1/positions"
  api_key_env: "AIS_API_KEY"
  timeout_seconds: 15

buffer:
  hours: 48
  minimum_track_points: 3
  maximum_gap_minutes: 30

query:
  max_vessel_distance_km: 100
  lookback_hours: 72
  temporal_buffer_hours: 4.0
  spatial_buffer_deg: 0.5
```

---

## 4. Testing Connectivity

Run the standalone operator verification command:

```bash
PYTHONPATH=. .venv/bin/python scripts/check_ais_live.py
```

The script audits:
1. Provider connection and authentication
2. Spatial bounding box querying
3. Schema normalization into canonical `AISObservation`
4. Generation of data quality report at `data/results/ais/live_quality_report.json`
