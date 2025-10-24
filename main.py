import os
import re
import traceback
from datetime import datetime
from typing import Dict, Any, List
import joblib
import numpy as np
import redis
import torch
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from transformers import pipeline, DistilBertTokenizer, DistilBertForMaskedLM
from pymongo import MongoClient
from bson import ObjectId
from dotenv import load_dotenv
import json


# ===================================================================
# --- 0. INITIAL SETUP & ENVIRONMENT VARIABLES ---
# ===================================================================
load_dotenv()  # Load environment variables from .env file


def log_debug(message: str, level: str = "INFO"):
    """Custom logging with timestamps."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] [{level}] {message}")


# ===================================================================
# --- 1. SERVICE CONNECTIONS (Redis & MongoDB) ---
# ===================================================================
app = FastAPI()


# Add CORS middleware for React frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://localhost:3000",
        "http://localhost:8080",
        "http://127.0.0.1:8080"
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


log_debug("🚀 Starting FastAPI WAF Application...")


# --- Redis Connection ---
try:
    redis_url = os.environ.get("REDIS_URL") or "redis://localhost:6379"
    r = redis.from_url(redis_url, decode_responses=True)
    r.ping()
    log_debug("✅ Successfully connected to Redis.", "SUCCESS")
except Exception as e:
    log_debug(f"❌ ERROR: Could not connect to Redis: {e}", "ERROR")
    r = None


# --- MongoDB Connection ---
try:
    mongo_uri = os.getenv("MONGO_URI")
    if not mongo_uri:
        raise ValueError("MONGO_URI environment variable not set!")
    
    mongo_client = MongoClient(mongo_uri)
    db = mongo_client.get_database("waf_db")
    analysis_collection = db.get_collection("analysis_logs")
    mongo_client.admin.command('ping')
    log_debug("✅ Successfully connected to MongoDB.", "SUCCESS")
except Exception as e:
    log_debug(f"❌ ERROR: Could not connect to MongoDB: {e}", "ERROR")
    mongo_client = None
    analysis_collection = None


# ===================================================================
# --- 2. ANOMALY DETECTION MODEL SETUP ---
# ===================================================================
log_debug("🧠 Loading Anomaly Detection Models...")
try:
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    MAX_LENGTH = 256
    MODEL_PATH, SCALER_PATH, IFOREST_PATH, TRAIN_FEATURES_PATH = (
        './distilbert_http_mlm_epoch22', 
        'scaler.pkl', 
        'iforest.pkl', 
        'train_features_dvwa_fix_seed.npy'
    )
    tokenizer = DistilBertTokenizer.from_pretrained(MODEL_PATH)
    model = DistilBertForMaskedLM.from_pretrained(MODEL_PATH)
    model.to(device)
    model.eval()
    scaler = joblib.load(SCALER_PATH)
    iforest = joblib.load(IFOREST_PATH)
    train_data = np.load(TRAIN_FEATURES_PATH, allow_pickle=True).item()
    train_stats = {
        'mean_error': train_data['errors'].mean(), 
        'std_error': train_data['errors'].std(), 
        'threshold_percentile': np.percentile(train_data['errors'], 95)
    }
    torch.manual_seed(42)
    np.random.seed(42)
    anomaly_model_loaded = True
    log_debug("✅ Anomaly Detection Models loaded successfully.", "SUCCESS")
except Exception as e:
    log_debug(f"❌ CRITICAL ERROR: Failed to load Anomaly Detection models: {e}", "ERROR")
    anomaly_model_loaded = False


# ===================================================================
# --- 3. HELPER FUNCTIONS (Anomaly Detection & Rule Generation) ---
# ===================================================================
def build_sequence(log_data: dict) -> str:
    return (
        f"[CLS] <body_bytes> {log_data.get('body_bytes_sent', '')} </body_bytes> [SEP] "
        f"<request_method> {log_data.get('method', '')} </request_method> [SEP] "
        f"<request_path> {log_data.get('path', '')} </request_path> [SEP] "
        f"<request_protocol> {log_data.get('protocol', '')} </request_protocol> [SEP] "
        f"<request_body> {log_data.get('request_body', '')} </request_body> [SEP]"
    )


def mask_tokens(input_ids, tokenizer, mask_prob=0.15):
    labels = input_ids.clone()
    probability_matrix = torch.full(labels.shape, mask_prob, device=device)
    special_tokens_mask = torch.tensor(
        [[val in tokenizer.all_special_ids for val in row] for row in labels.tolist()], 
        dtype=torch.bool, 
        device=device
    )
    probability_matrix.masked_fill_(special_tokens_mask, value=0.0)
    masked_indices = torch.bernoulli(probability_matrix).bool()
    
    if masked_indices.sum() == 0:
        rand_idx = torch.randint(1, labels.shape[1] - 1, (1,), device=device)
        masked_indices[0, rand_idx] = True
    
    labels[~masked_indices] = -100
    indices_replaced = torch.bernoulli(torch.full(labels.shape, 0.8, device=device)).bool() & masked_indices
    input_ids[indices_replaced] = tokenizer.mask_token_id
    indices_random = torch.bernoulli(torch.full(labels.shape, 0.5, device=device)).bool() & masked_indices & ~indices_replaced
    random_words = torch.randint(len(tokenizer), labels.shape, dtype=torch.long, device=device)
    input_ids[indices_random] = random_words[indices_random]
    
    return input_ids, labels


def extract_features(log_text: str, tokenizer_inst, model_inst, num_runs=5):
    errors, cls_embeddings, perplexities = [], [], []
    
    for _ in range(num_runs):
        encoding = tokenizer_inst(
            log_text, 
            padding=True, 
            truncation=True, 
            max_length=MAX_LENGTH, 
            return_tensors='pt'
        ).to(device)
        
        with torch.no_grad():
            masked_input, labels = mask_tokens(encoding["input_ids"].clone(), tokenizer_inst)
            outputs = model_inst(
                input_ids=masked_input, 
                attention_mask=encoding["attention_mask"], 
                labels=labels, 
                output_hidden_states=True
            )
        
        loss_val = outputs.loss.item() if outputs.loss.ndim == 0 else outputs.loss.mean().item()
        errors.append(loss_val)
        cls_embeddings.append(outputs.hidden_states[-1][0, 0, :].cpu().numpy())
        perplexities.append(np.exp(loss_val))
    
    return np.mean(errors), np.mean(cls_embeddings, axis=0), np.mean(perplexities)


def predict_anomaly(reconstruction_error, cls_embedding, perplexity, scaler_inst, iforest_inst, stats):
    features = np.column_stack([
        np.array([reconstruction_error, perplexity]).reshape(1, -1), 
        cls_embedding.reshape(1, -1)
    ])
    features_scaled = scaler_inst.transform(features)
    if_anomaly = (iforest_inst.predict(features_scaled)[0] == -1)
    z_score = np.abs((reconstruction_error - stats['mean_error']) / stats['std_error'])
    statistical_anomaly = z_score > 7
    percentile_anomaly = reconstruction_error > stats['threshold_percentile']
    
    return int(sum([if_anomaly, statistical_anomaly, percentile_anomaly]) >= 2)


# LLM for rule generation
log_debug("✍️ Loading LLM model for rule generation...")
try:
    llm_pipe = pipeline("text-generation", model="distilgpt2", device=-1)
    llm_loaded = True
except Exception:
    llm_pipe = None
    llm_loaded = False


def generate_rule_from_payload(payload: str) -> str | None:
    if not payload or llm_pipe is None:
        return f"(?i){re.escape(payload[:100])}"
    
    try:
        prompt = (
            f"Generate a regex pattern for a WAF to detect this malicious payload. "
            f"Output ONLY the regex pattern, nothing else:\n\n"
            f"Payload: {payload[:200]}\n\nRegex pattern:"
        )
        outputs = llm_pipe(prompt, max_new_tokens=50, pad_token_id=50256)
        regex_part = outputs[0]['generated_text'].replace(prompt, "").strip().split('\n')[0].strip('\'"')
        re.compile(regex_part)
        return regex_part
    except Exception:
        return f"(?i){re.escape(payload[:100])}"


# ===================================================================
# --- WebSocket Connection Manager ---
# ===================================================================
class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        log_debug(f"🔌 WebSocket client connected. Total connections: {len(self.active_connections)}")

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
        log_debug(f"🔌 WebSocket client disconnected. Total connections: {len(self.active_connections)}")

    async def broadcast(self, message: dict):
        """Broadcast a message to all connected WebSocket clients."""
        disconnected = []
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception as e:
                log_debug(f"❌ Error sending to WebSocket client: {e}", "ERROR")
                disconnected.append(connection)
        
        # Clean up disconnected clients
        for conn in disconnected:
            if conn in self.active_connections:
                self.active_connections.remove(conn)


manager = ConnectionManager()


# ===================================================================
# --- 4. PYDANTIC MODELS & API ENDPOINTS ---
# ===================================================================
class RequestData(BaseModel):
    method: str
    path: str
    protocol: str
    request_body: str


@app.post("/analyze")
async def analyze(request_data: RequestData):
    """
    Analyzes request, blocks if malicious, and logs the result to MongoDB.
    """
    if not anomaly_model_loaded:
        raise HTTPException(status_code=503, detail="Anomaly detection service unavailable")

    try:
        # --- STEP 1: Transformer Model Analysis ---
        formatted_log = build_sequence(request_data.dict())
        rec_error, cls_emb, perplexity = extract_features(formatted_log, tokenizer, model)
        category = predict_anomaly(rec_error, cls_emb, perplexity, scaler, iforest, train_stats)
        is_malicious = bool(category)
        
        # --- STEP 2: Logic for response and logging ---
        response, new_rule = None, None
        
        if is_malicious:
            log_debug(f"🚨 MALICIOUS request detected! Loss: {rec_error:.4f}", "ALERT")
            payload = request_data.request_body or request_data.path
            new_rule = generate_rule_from_payload(payload)
            if new_rule and r:
                r.sadd("waf:rules:regex", new_rule)
            response = {
                "allow": False, 
                "reason": f"Blocked by transformer model (loss: {rec_error:.4f})", 
                "auto_learned_rule": new_rule
            }
        else:
            log_debug(f"✅ BENIGN request classified. Loss: {rec_error:.4f}")
            response = {"allow": True, "reason": "Passed transformer model analysis."}
            
        # --- STEP 3: Save to MongoDB ---
        if analysis_collection is not None:
            log_document = {
                "timestamp": datetime.utcnow(),
                "request": request_data.dict(),
                "analysis": {
                    "is_malicious": is_malicious,
                    "reconstruction_loss": rec_error,
                    "perplexity": perplexity,
                },
                "action_taken": "BLOCK" if is_malicious else "ALLOW",
                "auto_learned_rule": new_rule
            }
            result = analysis_collection.insert_one(log_document)
            log_document["_id"] = str(result.inserted_id)
            log_debug("📝 Analysis result logged to MongoDB.")
            
            # Broadcast to WebSocket clients
            broadcast_data = {
                "_id": log_document["_id"],
                "timestamp": log_document["timestamp"].isoformat(),
                "method": request_data.method,
                "path": request_data.path,
                "request_body": request_data.request_body,
                "action_taken": log_document["action_taken"],
                "is_malicious": is_malicious,
                "reconstruction_loss": rec_error,
                "perplexity": perplexity,
                "auto_learned_rule": new_rule
            }
            await manager.broadcast(broadcast_data)

        return response
            
    except Exception as e:
        log_debug(f"❌ CRITICAL ERROR in /analyze: {e}", "ERROR")
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@app.get("/health")
async def health_check():
    return {
        "status": "healthy" if r and anomaly_model_loaded and (mongo_client is not None) else "degraded",
        "redis_connected": bool(r),
        "mongodb_connected": (mongo_client is not None),
        "anomaly_model_loaded": anomaly_model_loaded,
    }


# ===================================================================
# --- ✅ NEW: HISTORICAL LOGS ENDPOINT ---
# ===================================================================
@app.get("/logs")
async def get_logs(limit: int = 20):
    """
    Get recent analysis logs from MongoDB.
    Returns the most recent logs sorted by timestamp (newest first).
    """
    if analysis_collection is None:
        raise HTTPException(status_code=503, detail="MongoDB service unavailable")
    
    try:
        # Fetch logs sorted by timestamp (newest first)
        logs = list(analysis_collection.find()
                   .sort("timestamp", -1)
                   .limit(limit))
        
        # Convert ObjectId to string and timestamp to ISO format
        for log in logs:
            log["_id"] = str(log["_id"])
            if "timestamp" in log:
                log["timestamp"] = log["timestamp"].isoformat()
        
        log_debug(f"📚 Fetched {len(logs)} historical logs", "INFO")
        return {"logs": logs, "count": len(logs)}
        
    except Exception as e:
        log_debug(f"❌ Error fetching logs: {e}", "ERROR")
        raise HTTPException(status_code=500, detail=f"Error fetching logs: {str(e)}")


# ===================================================================
# --- DASHBOARD API ENDPOINTS ---
# ===================================================================
@app.post("/set-mode/{mode_name}")
async def set_waf_mode(mode_name: str):
    """
    Set the WAF operational mode: 'off', 'fast', or 'full'.
    Stores the mode in Redis under the key 'waf:mode'.
    """
    valid_modes = ['off', 'fast', 'full']
    if mode_name not in valid_modes:
        raise HTTPException(status_code=400, detail=f"Invalid mode. Must be one of: {valid_modes}")
    
    if not r:
        raise HTTPException(status_code=503, detail="Redis service unavailable")
    
    try:
        r.set("waf:mode", mode_name)
        log_debug(f"🔧 WAF mode set to: {mode_name}", "INFO")
        return {"status": "success", "mode": mode_name, "message": f"WAF mode set to {mode_name}"}
    except Exception as e:
        log_debug(f"❌ Error setting WAF mode: {e}", "ERROR")
        raise HTTPException(status_code=500, detail=f"Error setting WAF mode: {str(e)}")


class PassRequestBody(BaseModel):
    mongo_id: str


@app.post("/pass-request")
async def pass_request(body: PassRequestBody):
    """
    Whitelist a blocked request by adding its request_body to Redis whitelist.
    Retrieves the original request from MongoDB using the provided _id.
    """
    if not r:
        raise HTTPException(status_code=503, detail="Redis service unavailable")
    
    if analysis_collection is None:
        raise HTTPException(status_code=503, detail="MongoDB service unavailable")
    
    try:
        # Retrieve the request from MongoDB
        document = analysis_collection.find_one({"_id": ObjectId(body.mongo_id)})
        
        if not document:
            raise HTTPException(status_code=404, detail="Request not found in database")
        
        # Extract the request_body to whitelist
        request_body = document.get("request", {}).get("request_body", "")
        
        if not request_body:
            raise HTTPException(status_code=400, detail="Request body is empty, cannot whitelist")
        
        # Add to Redis whitelist
        r.sadd("waf:whitelist", request_body)
        log_debug(f"✅ Request whitelisted: {body.mongo_id}", "INFO")
        
        return {
            "status": "success", 
            "message": "Request added to whitelist",
            "mongo_id": body.mongo_id,
            "whitelisted_data": request_body[:100]
        }
        
    except Exception as e:
        log_debug(f"❌ Error whitelisting request: {e}", "ERROR")
        raise HTTPException(status_code=500, detail=f"Error whitelisting request: {str(e)}")


@app.websocket("/ws/logs")
async def websocket_logs(websocket: WebSocket):
    """
    WebSocket endpoint for real-time log streaming.
    Clients connect here to receive live analysis results.
    """
    await manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)
        log_debug("🔌 WebSocket client disconnected normally")
    except Exception as e:
        log_debug(f"❌ WebSocket error: {e}", "ERROR")
        manager.disconnect(websocket)


# ===================================================================
# --- RULES MANAGEMENT ENDPOINTS ---
# ===================================================================
@app.get("/rules")
async def get_rules():
    """Get all regex rules from Redis."""
    if not r:
        raise HTTPException(status_code=503, detail="Redis service unavailable")
    
    try:
        rules = list(r.smembers("waf:rules:regex"))
        return {"rules": rules, "count": len(rules)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching rules: {str(e)}")


class RuleBody(BaseModel):
    rule: str


@app.post("/rules")
async def add_rule(body: RuleBody):
    """Manually add a regex rule."""
    if not r:
        raise HTTPException(status_code=503, detail="Redis service unavailable")
    
    try:
        # Validate regex
        re.compile(body.rule)
        r.sadd("waf:rules:regex", body.rule)
        log_debug(f"➕ Manual rule added: {body.rule}", "INFO")
        return {"status": "success", "message": "Rule added", "rule": body.rule}
    except re.error as e:
        raise HTTPException(status_code=400, detail=f"Invalid regex pattern: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error adding rule: {str(e)}")


@app.delete("/rules")
async def delete_rule(body: RuleBody):
    """Delete a specific rule."""
    if not r:
        raise HTTPException(status_code=503, detail="Redis service unavailable")
    
    try:
        removed = r.srem("waf:rules:regex", body.rule)
        if removed:
            log_debug(f"➖ Rule deleted: {body.rule}", "INFO")
            return {"status": "success", "message": "Rule deleted", "rule": body.rule}
        else:
            raise HTTPException(status_code=404, detail="Rule not found")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error deleting rule: {str(e)}")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
