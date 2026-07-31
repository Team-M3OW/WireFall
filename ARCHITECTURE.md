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
[ 3. AGENTIC WORKERS (Self-Learning Loop) ]

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
```

---

## 2. Module Breakdown

### Module 1: The Edge Layer (OpenResty & Lua)
**The Goal:** Act as an ultra-fast, zero-latency shield that drops known attacks before they ever reach the Python backend.

**Deep Dive:**
OpenResty is a customized version of Nginx that embeds the LuaJIT (Just-In-Time) compiler. Nginx is fundamentally built on an asynchronous, event-driven architecture. By embedding Lua directly into this event loop, we execute code at the C-level speed of Nginx. 

When an HTTP request arrives, the Lua script intercepts the connection. It connects to Redis (using a non-blocking TCP socket) to pull the active WAF blocklist. If the payload matches any of the auto-generated regex rules, Lua immediately executes `ngx.exit(ngx.HTTP_FORBIDDEN)`, instantly terminating the connection. The heavy Python PyTorch backend never even knows the attacker existed, saving massive amounts of CPU and GPU compute.

**Limitations & Scaling:** Network latency from Nginx to Redis can add up. To scale this to massive enterprise levels, you would implement an in-memory local cache directly inside the Nginx worker (using Lua shared dictionaries) to avoid the TCP jump to Redis entirely.

### Module 2: The Core Backend (FastAPI)
**The Goal:** Orchestrate the heavy lifting, manage traffic control, and serve as the traffic cop for unknown payloads.

**Deep Dive:**
When a payload bypasses the Lua edge layer, it hits the asynchronous FastAPI backend. Here is the strict sequence of defensive LLD operations it executes:
1. **DDoS Protection (Rate Limiting):** It executes a single, atomic Redis pipeline transaction to run a Sliding Window Log algorithm, ensuring malicious bots cannot brute-force the ML model.
2. **Caching ($O(1)$ Bypass):** It runs a SHA-256 hash on the payload. If we analyzed this exact payload 5 seconds ago and deemed it safe, we serve the cached result and skip the ML model.
3. **Bounded Concurrency:** It enters an `asyncio.Semaphore(50)`. PyTorch is notorious for causing Out-Of-Memory (OOM) crashes under concurrent load. The semaphore ensures that no matter how much traffic hits the API, only 50 requests will ever execute ML inference simultaneously. 
4. **Fault Tolerance (Graceful Degradation):** It utilizes a Circuit Breaker State Machine. If the ML inference throws repeated exceptions, the circuit "trips," and the API safely fails-open, allowing traffic through so the customer's production site doesn't go offline.

### Module 3: The ML Inference Engine (PyTorch)
**The Goal:** Detect zero-day attacks that evade traditional static Regex rules using unsupervised machine learning.

**Deep Dive:**
1. **The Singleton Pattern:** The multi-gigabyte DistilBERT transformer model is heavily memory-bound. It is instantiated via the Singleton Pattern exactly once at startup so all concurrent HTTP requests can share a single footprint in RAM.
2. **Reconstruction Loss:** The payload is tokenized, and 15% of the tokens are deliberately masked. DistilBERT attempts to guess the missing tokens based on context. If the payload contains chaotic SQL injection syntax (`' OR 1=1--`), the model fails to reconstruct it. This failure is mathematically quantified as "Reconstruction Loss" and "Perplexity".
3. **Ensemble Voting:** Raw loss isn't enough. We pass these metrics into a secondary layer: an Isolation Forest and a Z-Score statistical model. These models act as a voting committee to determine if the loss is severe enough to definitively classify the payload as an anomaly.

### Module 4: Agentic Rule Generator (RabbitMQ & LangGraph)
**The Goal:** Automate the job of a Cybersecurity Engineer by writing protective Regex rules on the fly without blocking web traffic.

**Deep Dive:**
If the PyTorch model flags a payload as a novel attack, we must write a rule for it. Generating rules using an LLM takes ~10 seconds. We cannot make the HTTP request wait 10 seconds.
1. **Producer-Consumer Architecture:** FastAPI (The Producer) publishes a JSON message containing the attack payload to a **RabbitMQ** queue and instantly returns an HTTP response to the user.
2. **Agentic Sandboxing:** In the background, a Python Worker (The Consumer) picks up the message. It uses **LangGraph** to orchestrate a local `Qwen-7B` model. The LLM acts as an agent, writing a candidate regex rule and generating fake malicious/benign payloads to test its own rule against. If the rule accidentally blocks benign traffic (a False Positive), the agent self-corrects and rewrites the rule until it passes the sandbox.
3. **Dead Letter Queues (DLQ):** If the LLM crashes, the worker uses **Exponential Backoff** to sleep and retry. After 3 failures, it routes the message to a DLQ so engineers can debug it later, ensuring no attacks are forgotten.

### Module 5: The Data Layer (Polyglot Persistence)
**The Goal:** Store ephemeral state for high-speed edge lookups and persistent state for long-term historical auditing.

**Deep Dive:**
WireFall utilizes **Polyglot Persistence**—choosing different databases for specific computer science problems.
* **Redis (In-Memory Key-Value):** Stores the active WAF blocklist, the Rate Limiter sorted sets, and the cache. Running entirely in RAM on a single-threaded event loop guarantees sub-millisecond read/write speeds, making it the perfect nervous system for the Lua Edge layer.
* **MongoDB (Document Store):** Stores the historical audit logs. Because HTTP payloads vary wildly in size and structure, SQL tables would be too rigid. MongoDB's BSON document structure accommodates this schema-less, heavy write-throughput logging requirement. Logging is offloaded to a **Background Thread Pool** to prevent network I/O from slowing down the FastAPI response.

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
Visualized as JSON to illustrate structural intent.

**1. The Active WAF Rules (Redis `SET`)**
```json
{
  "Key": "waf:customer_a:rules:regex",
  "Type": "Set",
  "TTL": "Infinite",
  "Value": [
    "(?i)union.*select.*",
    "<script\\b[^<]*(?:(?!<\\/script>)<[^<]*)*<\\/script>"
  ]
}
```

**2. The Sliding Window Rate Limiter (Redis `ZSET`)**
```json
{
  "Key": "waf:ratelimit:customer_a:198.51.100.23",
  "Type": "Sorted Set",
  "TTL": "60 seconds",
  "Value": [
    { "Score": 1692800000.123, "Member": "1692800000.123" },
    { "Score": 1692800000.456, "Member": "1692800000.456" }
  ]
}
```

**3. The Request Cache (Redis `STRING`)**
```json
{
  "Key": "waf:customer_a:cache:e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
  "Type": "String",
  "TTL": "300 seconds",
  "Value": "1" 
}
```
