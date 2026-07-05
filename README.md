<div align="center">

# 🛡️ WireFall

**Self-Learning Web Application Firewall**  
Powered by Transformer-based Anomaly Detection with Ensemble Voting

[![CI](https://github.com/Team-M3OW/WireFall/actions/workflows/ci.yml/badge.svg)](https://github.com/Team-M3OW/WireFall/actions)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue)](https://www.python.org/downloads/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.104-009688)](https://fastapi.tiangolo.com/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)

</div>

---

## Overview

WireFall is a **self-learning Web Application Firewall (WAF)** that uses a **DistilBERT-based Masked Language Model (MLM)** combined with an **ensemble anomaly detector** to inspect HTTP requests in real time and block malicious traffic — without relying on static rule databases.

Unlike traditional WAFs (ModSecurity, AWS WAF, Cloudflare), WireFall **learns what normal traffic looks like** and flags deviations. It also **auto-generates regex rules** from novel attacks, creating a fast-path blocklist that improves over time.

### How It Works

```
Client ──▶ OpenResty ──▶ Stage 1: Redis Regex Rules ──▶ Stage 2: ML Model ──▶ Backend App
                │                                            │
                │                                     ┌──────┴──────┐
                │                                     │  Ensemble   │
                │                                     │  Detector   │
                │                                     └──────┬──────┘
                │                                      ┌──────┴──────┐
                │                                      │  auto-rule  │
                │                                      │  generation │
                │                                      └─────────────┘
```

The WAF operates in two stages:
1. **Stage 1 (Fast Path)** — Checks every request against Redis-stored regex rules. Known attacks are blocked in microseconds.
2. **Stage 2 (Deep Path)** — For unknown requests, the ML model runs 5 masked-language-modeling passes through DistilBERT, extracts feature vectors, and votes via a 3-method ensemble.

---

## Features

- **Transformer-based detection** — DistilBERT MLM trained on HTTP traffic logs
- **Ensemble anomaly detector** — Isolation Forest + z-score threshold + 95th percentile majority vote
- **Self-learning** — Automatically generates regex rules from novel malicious payloads using distilgpt2
- **Real-time monitoring** — WebSocket-powered live dashboard with Chart.js visualizations
- **Dual dashboards** — Static HTML dashboard + React/Vite dashboard
- **Two-stage architecture** — Fast regex path + deep ML path for optimal throughput
- **WAF modes** — `off`, `fast` (regex only), `full` (regex + ML)
- **Whitelist support** — Bypass blocked requests with one click
- **OpenResty integration** — Lua script hooks into nginx request lifecycle
- **Separate logs service** — Lightweight CRUD microservice for analysis logs

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        WireFall System                          │
├───────────────────────┬─────────────────────────────────────────┤
│   OpenResty (port 80)  │   FastAPI Backend (port 8001)          │
│   ┌─────────────────┐  │   ┌───────────────────────────────┐   │
│   │  waf_chain.lua  │  │   │  /analyze  /health  /logs     │   │
│   │  Stage 1: Redis │──┼──▶│  /rules   /set-mode  /ws/logs │   │
│   │  Stage 2: HTTP  │  │   │  ┌───────────┬────────────┐   │   │
│   └─────────────────┘  │   │  │ DistilBERT│  Ensemble  │   │   │
│                        │   │  │   MLM     │  Detector  │   │   │
│   Backend App          │   │  └───────────┴────────────┘   │   │
│   (port 3000)          │   └───────────────────────────────┘   │
├───────────────────────┼─────────────────────────────────────────┤
│   Logs Service         │   Infrastructure                       │
│   (port 8002)          │   ┌──────────┐  ┌──────────┐         │
│   ┌─────────────────┐  │   │  Redis   │  │ MongoDB  │         │
│   │  CRUD for logs  │  │   │ (state,  │  │ (persist │         │
│   └─────────────────┘  │   │  rules)  │  │  logs)   │         │
│                        │   └──────────┘  └──────────┘         │
└───────────────────────┴─────────────────────────────────────────┘
```

### Components

| Component | Tech | Purpose |
|---|---|---|
| **OpenResty** | nginx + Lua | Reverse proxy with embedded WAF Lua hook |
| **WAF Backend** | FastAPI (Python) | ML inference, rule management, real-time WebSocket |
| **Logs Service** | FastAPI (Python) | Lightweight CRUD for analysis logs |
| **Inference Engine** | PyTorch + scikit-learn | DistilBERT MLM + Isolation Forest ensemble |
| **Rule Generator** | distilgpt2 (HuggingFace) | Auto-generates regex rules from malicious payloads |
| **Redis** | In-memory DB | WAF mode, regex rules, whitelist |
| **MongoDB** | Document DB | Persistent analysis logs |
| **Dashboard (Static)** | HTML + JS + Chart.js | Real-time monitoring UI |
| **Dashboard (React)** | React 18 + Vite + Chart.js | Modern reactive dashboard |

---

## Getting Started

### Prerequisites

- Python 3.10+
- Redis 7+
- MongoDB 7+
- OpenResty (optional, for nginx integration)
- NVIDIA GPU (optional, for accelerated inference)

### Installation

```bash
# Clone
git clone https://github.com/Team-M3OW/WireFall.git
cd WireFall

# Install dependencies
pip install -e .

# Or with dev dependencies
pip install -e ".[dev]"

# Configure
cp .env.example .env
# Edit .env with your Redis/MongoDB URIs
```

### Running

**Start the WAF backend:**

```bash
make run-api
# or: uvicorn api.main:app --host 0.0.0.0 --port 8001 --reload
```

**Start the logs service:**

```bash
make run-logs
# or: uvicorn api.logs_service:app --host 0.0.0.0 --port 8002 --reload
```

**Start with Docker:**

```bash
make docker-up
# or: docker compose -f infrastructure/docker-compose.yml up -d
```

### Verification

```bash
# Health check
curl http://localhost:8001/health

# Analyze a request
curl -X POST http://localhost:8001/analyze \
  -H "Content-Type: application/json" \
  -d '{"method":"GET","path":"/","protocol":"HTTP/1.1","request_body":""}'
```

---

## API Reference

### Core Endpoints

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/analyze` | Analyze an HTTP request for anomalies |
| `GET` | `/health` | Service health check |
| `GET` | `/logs` | Paginated analysis logs |
| `POST` | `/set-mode/{mode}` | Set WAF mode (`off`, `fast`, `full`) |
| `POST` | `/pass-request` | Whitelist a blocked request |
| `GET` | `/rules` | List all regex rules |
| `POST` | `/rules` | Add a regex rule |
| `DELETE` | `/rules` | Delete a regex rule |
| `WS` | `/ws/logs` | Real-time log stream via WebSocket |

### Logs Service (port 8002)

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/logs` | Paginated logs with total count |
| `GET` | `/logs/stats` | Aggregate statistics |
| `GET` | `/logs/recent` | Most recent N logs |
| `GET` | `/logs/{id}` | Single log by ID |
| `DELETE` | `/logs` | Clear all logs |
| `DELETE` | `/logs/{id}` | Delete specific log |

### Request Schema

```json
{
  "method": "GET",
  "path": "/api/login",
  "protocol": "HTTP/1.1",
  "request_body": "username=admin&password=test"
}
```

### Response Schema

```json
{
  "allow": true,
  "reason": "Passed transformer model analysis."
}
```

---

## Dashboards

### Static Dashboard
Open `dashboard/static/index.html` in your browser for a real-time monitoring dashboard with Chart.js visualizations.

### React Dashboard
```bash
cd dashboard/react
npm install
npm run dev
```
Opens at `http://localhost:5173` — a modern reactive dashboard with the same monitoring capabilities.

---

## ML Pipeline

### Training

The DistilBERT model is fine-tuned with Masked Language Modeling on HTTP access logs:

```bash
python model/scripts/train.py \
  --model distilbert-base-uncased \
  --data ./data/nginx_access_parsed.csv \
  --epochs 30 \
  --batch-size 32
```

### Inference

The inference pipeline (`inference/`) performs:

1. **Sequence building** — Formats the HTTP request into a structured text sequence with special tokens
2. **Masked inference** — Runs DistilBERT with random token masking (15% of tokens), repeated 5 times for stability
3. **Feature extraction** — Collects reconstruction loss, [CLS] embeddings, and perplexity
4. **Ensemble voting** — 3 methods vote:
   - **Isolation Forest** — Unsupervised anomaly detection
   - **Z-score** — Statistical deviation > 7σ
   - **Percentile** — Reconstruction loss > 95th training percentile

   ≥ 2 votes = malicious → blocked. Auto-rule generated via distilgpt2.

---

## Project Structure

```
WireFall/
├── api/                    # FastAPI backend
│   ├── main.py             # App entry point, startup/shutdown
│   ├── logs_service.py     # Standalone logs microservice
│   ├── config.py           # Pydantic settings (env-based config)
│   ├── models/             # Pydantic schemas
│   ├── routes/             # Route handlers (analyze, health, logs, rules, modes, ws)
│   └── services/           # Service layer (Redis, MongoDB, WebSocket)
├── inference/              # ML inference pipeline
│   ├── model.py            # Model loading and device management
│   ├── features.py         # Sequence building, masking, feature extraction
│   ├── ensemble.py         # Ensemble anomaly detector
│   └── rule_generator.py   # LLM-based regex rule generation
├── model/                  # Training artifacts
│   ├── scripts/            # Training and evaluation scripts
│   ├── checkpoints/        # Trained model checkpoints
│   └── samples/            # Sample inputs and outputs
├── dashboard/              # User interfaces
│   ├── static/             # Static HTML + vanilla JS dashboard
│   └── react/              # React + Vite dashboard
├── lua/                    # OpenResty Lua WAF scripts
├── infrastructure/         # Deployment configs
│   ├── nginx/              # Nginx/OpenResty config
│   ├── docker/             # Dockerfiles
│   ├── docker-compose.yml  # Multi-service orchestration
│   └── k8s/                # Kubernetes manifests
├── tests/                  # Test suite
├── docs/                   # Documentation
├── scripts/                # Utility scripts
├── pyproject.toml          # Project metadata and dependencies
├── Makefile                # Common task runner
└── README.md
```

---

## Development

```bash
# Install dev dependencies
make dev

# Lint and format
make lint
make format

# Type check
make typecheck

# Run tests
make test

# Clean up
make clean
```

### Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing`)
3. Install pre-commit hooks (`pre-commit install`)
4. Make your changes
5. Run linting and tests
6. Submit a pull request

---

## License

MIT License — see [LICENSE](LICENSE) for details.

---

<div align="center">
Built with ❤️ by <a href="https://github.com/Team-M3OW">Team M3OW</a>
</div>
