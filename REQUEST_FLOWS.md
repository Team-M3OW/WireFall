# WireFall: Request Flows & Edge Cases

This document maps out the exact lifecycle of an HTTP request as it traverses the WireFall architecture under every possible condition. 

By understanding these 9 cases, you can demonstrate exactly how the system behaves across the Edge Layer, the ML Engine, and the Agentic Background Workers.

## Case 1: The Known Attack (The Fast Path)
**Scenario:** An attacker sends a classic SQL injection (`' OR 1=1--`) that WireFall has previously learned about.
1. The request hits the OpenResty (Nginx) Edge Node.
2. The Lua script intercepts the request and checks the Redis `waf:tenant_id:rules:regex` Set.
3. The payload matches an active regex rule.
4. Nginx executes `ngx.exit(403)` and instantly drops the TCP connection.
**Result:** Blocked in < 1 millisecond. The Python backend is completely unaware of the event.

## Case 2: The Volumetric DDoS Attack
**Scenario:** A botnet tries to flood the server with 10,000 seemingly benign requests per second.
1. The requests bypass the Nginx Lua Regex check (as the payload structure looks benign).
2. The requests hit the FastAPI `/analyze` endpoint.
3. FastAPI immediately executes the Redis Sliding Window Rate Limiter.
4. The Redis pipeline counts > 1,000 requests in the last 60 seconds for this IP.
5. FastAPI instantly throws a `429 Too Many Requests` HTTP exception.
**Result:** Blocked in ~2 milliseconds. The heavy ML model is never invoked, saving the GPU from an Out-Of-Memory (OOM) crash.

## Case 3: The Highly Repetitive Safe Request
**Scenario:** A legitimate user reloads the homepage multiple times, sending the exact same safe JSON payload.
1. The request hits FastAPI.
2. The Rate Limiter allows the request.
3. FastAPI computes a SHA-256 hash of the payload and checks Redis.
4. It finds the hash in the `waf:tenant_id:cache` keyspace.
5. FastAPI instantly returns `{"allow": true}`.
**Result:** Allowed in ~2 milliseconds. The ML inference is bypassed, ensuring $O(1)$ response times for heavy, legitimate traffic.

## Case 4: The Novel Safe Request (The Slow Path)
**Scenario:** A legitimate user submits a long, complex, but safe form submission that hasn't been cached yet.
1. The request bypasses the Lua Edge, the Rate Limiter, and the Redis Cache.
2. The request enters the `asyncio.Semaphore(50)`. If there are 50 active requests currently being processed, it waits gracefully in an async queue.
3. The DistilBERT PyTorch model tokenizes the payload and masks 15% of the tokens.
4. The model reconstructs the payload successfully (yielding a Low Reconstruction Loss).
5. The Ensemble models (Isolation Forest/Z-Score) vote that the loss is within normal bounds.
6. FastAPI returns `{"allow": true}` and saves the payload hash to the Redis Cache for 5 minutes.
7. A Background Task is fired to log the event to MongoDB.
**Result:** Allowed in ~50-150 milliseconds. Future identical requests will now fall into Case 3.

## Case 5: The Zero-Day Attack (Self-Learning Triggered)
**Scenario:** An attacker exploits a brand new, highly obfuscated vulnerability that has no existing Regex rule.
1. The request bypasses Lua, Rate Limits, and Cache.
2. DistilBERT attempts to reconstruct the chaotic, obfuscated payload and fails spectacularly (yielding a High Reconstruction Loss).
3. The Ensemble models flag the request as a definitive anomaly.
4. FastAPI instantly returns `{"allow": false}` and drops the connection.
5. FastAPI (The Producer) publishes the payload to RabbitMQ and logs the event to MongoDB.
6. In the background, the Python Worker (The Consumer) picks up the message from RabbitMQ.
7. The LangGraph Agent boots up the local Qwen-7B LLM to generate a regex rule to catch this obfuscation.
8. The Agent sandboxes its own rule against fake benign payloads to ensure no False Positives.
9. The Worker deploys the final Regex rule to the Redis Edge layer.
**Result:** Blocked in ~150 milliseconds. ~10 seconds later, the system autonomously immunizes itself at the edge layer. Future identical attacks will now fall into Case 1.

## Case 6: Catastrophic Hardware Failure (Graceful Degradation)
**Scenario:** The GPU runs out of memory, or the PyTorch inference throws a critical runtime exception.
1. The request reaches FastAPI and begins ML evaluation.
2. PyTorch throws an exception (e.g., `CUDA Out of Memory`).
3. The Circuit Breaker state machine trips to `OPEN`.
4. FastAPI catches the exception and intentionally returns `{"allow": true, "reason": "WAF Degraded"}`.
**Result:** Allowed. The WAF explicitly prioritizes the customer's uptime over security. This architectural decision (Failing Open) guarantees that an internal WAF hardware failure will never accidentally take down the customer's production web application.

## Case 7: The Agentic Hallucination (Sandboxed Self-Correction)
**Scenario:** The LLM hallucinates and generates a dangerously broad regex rule like `.*` that would accidentally block all traffic.
1. The RabbitMQ Worker receives the zero-day attack payload.
2. The LangGraph LLM loop generates the candidate regex `.*`.
3. Before deploying, the Worker enters the **Agentic Sandbox**. It generates 5 benign JSON payloads and tests `.*` against them.
4. The regex matches the benign payloads (producing False Positives).
5. The Worker rejects the rule and loops back to the LLM with the error: *"Your rule blocked benign traffic. Try again and be more specific."*
6. The LLM self-corrects and generates a tighter, safer rule.
7. It passes the sandbox and is deployed to Redis.
**Result:** The customer's production traffic is saved from a self-inflicted Denial of Service (DoS) caused by AI hallucination.

## Case 8: The Redis Outage (Database Resiliency)
**Scenario:** The primary Redis cluster crashes, taking the Cache and Rate Limiter offline.
1. A request hits FastAPI.
2. The Sliding Window Rate Limiter attempts a pipeline transaction against Redis.
3. The connection throws a `TimeoutError` or `ConnectionRefusedError`.
4. The Rate Limiter catches the exception and intentionally returns `True` (Failing Open).
5. The request proceeds to the PyTorch ML engine for full evaluation.
**Result:** The WAF continues to protect the customer from attacks, albeit slightly slower due to the lack of caching. A database outage does not cause a hard system crash.

## Case 9: The Multi-Tenant Boundary (B2B SaaS Data Isolation)
**Scenario:** Customer A is attacked by a novel SQL injection. Customer B receives the exact same payload a second later.
1. Customer A's zero-day attack triggers the PyTorch model and the LangGraph worker.
2. The worker generates a new regex rule and saves it specifically to `waf:customer_a:rules:regex`.
3. Customer B receives the same attack payload.
4. The Nginx Lua edge script for Customer B checks `waf:customer_b:rules:regex`.
5. Because the rule was isolated to Customer A's namespace, Customer B's edge layer misses it.
6. The payload passes to FastAPI, where PyTorch detects it and triggers a separate rule generation process for Customer B.
**Result:** Strict data isolation. Customer A's custom security rules can never accidentally block or interfere with Customer B's legitimate web traffic, proving enterprise-grade multi-tenancy.
