# WireFall: Architectural Deep Dive

WireFall is an autonomous, self-learning Web Application Firewall (WAF) designed to detect and mitigate zero-day web attacks in real-time. It leverages an ultra-fast edge caching layer, an asynchronous Python core, Unsupervised Machine Learning, and Agentic Large Language Models (LLMs) to automatically generate protective regex rules on the fly.

This document breaks down the end-to-end flow of the system and highlights the Low-Level Design (LLD) and Computer Science fundamentals implemented across the architecture.

---

## 1. System Request Lifecycle

```text
                                +---------------------------+
                                |      Attacker / User      |
                                +-------------+-------------+
                                              |
                                              v (HTTP Request)
=======================================================================================
[ 1. EDGE LAYER (The Fast Path) ]

                                +---------------------------+
                                |  OpenResty (Nginx + Lua)  |
                                +-------------+-------------+
                                              |
                          +-------------------+-------------------+
                          |                                       |
                          v                                       v
             +-------------------------+            +---------------------------+
             | Redis (Regex Cache)     | --Match--> |      DROP CONNECTION      |
             +-------------------------+            +---------------------------+
                          |
                          v (No Match / Unknown Payload)
=======================================================================================
[ 2. CORE BACKEND (The Slow Path) ]

                                +---------------------------+
                                |      FastAPI Server       |
                                |     (POST /analyze)       |
                                +-------------+-------------+
                                              |
                          +-------------------+-------------------+
                          |                                       |
                          v                                       v
             +-------------------------+            +---------------------------+
             | Bounded Concurrency     |            | Background Thread Pool    |
             | (asyncio.Semaphore)     |            +-------------+-------------+
             +------------+------------+                          |
                          |                                       v
                          v                             +-------------------+
             +-------------------------+                |  MongoDB Logging  |
             |  PyTorch ML Inference   |                +-------------------+
             | (DistilBERT / Ensemble) |
             +------------+------------+
                          |
                          v (Novel Attack Detected)
=======================================================================================
[ 3. AGENTIC WORKERS & CONTINUAL LEARNING ]

                                +---------------------------+
                                |  RabbitMQ Message Queue   |
                                +-------------+-------------+
                                              |
                                              v
                                +---------------------------+
                                |    Python Rule Worker     |
                                +-------------+-------------+
                                              |
                                              v
                                +---------------------------+
                                | LangGraph & Qwen-7B LLM   |
                                | (Sandboxed Validation)    |
                                +-------------+-------------+
                                              |
                                              v (Regex Generated)
                                +---------------------------+
                                | Deploy to Redis Edge Node |
                                +---------------------------+
                                
=======================================================================================
[ 4. OFFLINE CONTINUAL LEARNING (LoRA) ]

             +-------------------------+            +---------------------------+
             | MongoDB (Audit Logs)    | ---------> | LoRA Fine-Tuning Pipeline |
             +-------------------------+            +---------------------------+
                                                                  |
                                                                  v
                                                    +---------------------------+
                                                    | Update DistilBERT Weights |
                                                    +---------------------------+
```

---

## 2. Module Breakdown

### Module 1: The Edge Layer (OpenResty & Lua)
**The Goal:** Act as an ultra-fast, zero-latency shield that drops known attacks before they ever reach the Python backend.

**Deep Dive:**
OpenResty is a customized version of Nginx that embeds the LuaJIT (Just-In-Time) compiler. When an HTTP request arrives, the Lua script intercepts the connection. It connects to Redis to pull the active WAF blocklist. If the payload matches any of the auto-generated regex rules, Lua immediately drops the connection. The Python backend never even knows the attacker existed.

### Module 2: The Core Backend (FastAPI)
**The Goal:** Orchestrate the heavy lifting, manage traffic control, and serve as the traffic cop for unknown payloads.

**Deep Dive:**
When a payload bypasses the Lua edge layer, it hits the asynchronous FastAPI backend. It executes:
1. **DDoS Protection:** Runs a Sliding Window Log algorithm via Redis.
2. **Caching:** Runs a SHA-256 hash on the payload to serve known-safe requests in $O(1)$ time.
3. **Bounded Concurrency:** Uses an `asyncio.Semaphore(50)` to prevent PyTorch from causing Out-Of-Memory (OOM) crashes under concurrent load.
4. **Fault Tolerance:** Utilizes a Circuit Breaker State Machine to Fail-Open if the ML inference throws exceptions, guaranteeing customer uptime.

### Module 3: The ML Inference Engine (PyTorch)
**The Goal:** Detect zero-day attacks using unsupervised machine learning.

**Deep Dive:**
1. **The Singleton Pattern:** The DistilBERT model is instantiated via the Singleton Pattern exactly once at startup.
2. **Reconstruction Loss:** The payload is tokenized and 15% of the tokens are masked. DistilBERT attempts to guess the missing tokens. If the payload contains chaotic SQL injection syntax, it fails, yielding high "Reconstruction Loss".
3. **Ensemble Voting:** An Isolation Forest and Z-Score statistical model act as a voting committee to determine if the loss is severe enough to definitively classify the payload as an anomaly.

### Module 4: Agentic Rule Generator (RabbitMQ & LangGraph)
**The Goal:** Automate the job of a Cybersecurity Engineer by writing protective Regex rules on the fly.

**Deep Dive:**
1. **Producer-Consumer Architecture:** FastAPI publishes a JSON message containing the attack payload to a **RabbitMQ** queue and instantly returns an HTTP response.
2. **Agentic Sandboxing:** In the background, a Python Worker uses **LangGraph** to orchestrate a `Qwen-7B` model. The LLM acts as an agent, writing a candidate regex rule and testing it against fake benign payloads. If it accidentally blocks benign traffic, the agent self-corrects.
3. **Dead Letter Queues (DLQ):** If the LLM crashes, the worker uses **Exponential Backoff**. After 3 failures, it routes the message to a DLQ so engineers can debug it later.

### Module 5: Offline Continual Learning (LoRA)
**The Goal:** Evolve the core Machine Learning models without the massive computational expense of retraining from scratch.

**Deep Dive:**
Machine learning models suffer from "Concept Drift"—as hackers invent new attack syntaxes, the original DistilBERT model becomes outdated. However, retraining a massive neural network from scratch daily is computationally impossible.

To solve this, WireFall implements **Continual Learning via LoRA (Low-Rank Adaptation)**.
1. **The Feedback Loop:** Every night, a scheduled pipeline pulls the latest False Positives and novel Zero-Day attacks from the MongoDB Audit Logs.
2. **Low-Rank Adaptation:** Instead of updating all 66 million parameters of DistilBERT, LoRA freezes the original model weights and injects small, trainable "rank decomposition matrices" into the transformer layers.
3. **The Result:** We can continually fine-tune the model on the latest hacker trends in minutes on a single GPU. The newly adapted LoRA weights are then swapped into the live FastAPI instance, ensuring the WAF gets smarter every single day with minimal compute costs.

### Module 6: The Data Layer (Polyglot Persistence)
**The Goal:** Store ephemeral state for high-speed edge lookups and persistent state for historical auditing.

**Deep Dive:**
* **Redis:** Stores the active WAF blocklist, Rate Limiter, and cache for sub-millisecond read/write speeds.
* **MongoDB:** Stores the historical audit logs. Logging is offloaded to a **Background Thread Pool** to prevent network I/O from slowing down the FastAPI response.

---

## 3. Database Schemas

### MongoDB Schema (Audit Logging & Analytics)
```json
{
  "_id": "ObjectId('64e2a...')",         
  "tenant_id": "String",                  
  "timestamp": "ISODate",                 
  
  "request": {                            
    "method": "String",                   
    "path": "String",                     
    "protocol": "String",                 
    "request_body": "String"              
  },
  
  "analysis": {                           
    "is_malicious": "Boolean",            
    "reconstruction_loss": "Float",       
    "perplexity": "Float",                
    "details": "String"                   
  },
  
  "action_taken": "String",               
  "auto_learned_rule": "String"           
}
```

### Redis Schema (Real-Time Edge Caching)
**1. The Active WAF Rules (Redis `SET`)**
```json
{
  "Key": "waf:customer_a:rules:regex",
  "Type": "Set",
  "Value": ["(?i)union.*select.*"]
}
```

**2. The Sliding Window Rate Limiter (Redis `ZSET`)**
```json
{
  "Key": "waf:ratelimit:customer_a:198.51.100.23",
  "Type": "Sorted Set",
  "Value": [{ "Score": 1692800000.123, "Member": "1692800000.123" }]
}
```

**3. The Request Cache (Redis `STRING`)**
```json
{
  "Key": "waf:customer_a:cache:e3b0c442...",
  "Type": "String",
  "Value": "1" 
}
```
