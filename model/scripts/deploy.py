from fastapi import FastAPI
from pydantic import BaseModel
import torch
import random
import numpy as np
import joblib
from transformers import DistilBertTokenizer, DistilBertForMaskedLM

app = FastAPI()

# Load everything once at startup
device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
MAX_LENGTH = 256

tokenizer = DistilBertTokenizer.from_pretrained('./distilbert_http_mlm_epoch22')
model = DistilBertForMaskedLM.from_pretrained('./distilbert_http_mlm_epoch22')
model.to(device)
model.eval()

scaler = joblib.load('scaler.pkl')
iforest = joblib.load('iforest.pkl')
train_data = np.load('train_features_dvwa_fix_seed.npy', allow_pickle=True).item()
train_stats = {
    'mean_error': train_data['errors'].mean(),
    'std_error': train_data['errors'].std(),
    'threshold_percentile': np.percentile(train_data['errors'], 95)
}

torch.manual_seed(42)
np.random.seed(42)

class LogInput(BaseModel):
    body_bytes_sent: str = ""
    method: str = ""
    path: str = ""
    protocol: str = ""
    request_body: str = ""

class PredictionOutput(BaseModel):
    request: dict
    formatted_log: str
    category: int
    reconstruction_loss: float
    combined_score: float
    is_anomaly: bool

def build_sequence(log_data):
    return (
        f"[CLS] "
        f"<body_bytes> {log_data.get('body_bytes_sent', '')} </body_bytes> [SEP] "
        f"<request_method> {log_data.get('method', '')} </request_method> [SEP] "
        f"<request_path> {log_data.get('path', '')} </request_path> [SEP] "
        f"<request_protocol> {log_data.get('protocol', '')} </request_protocol> [SEP] "
        f"<request_body> {log_data.get('request_body', '')} </request_body> [SEP]"
    )

def mask_tokens(input_ids, mask_prob=0.15):
    labels = input_ids.clone()
    probability_matrix = torch.full(labels.shape, mask_prob, device=device)
    special_tokens_mask = torch.zeros_like(labels, dtype=torch.bool, device=device)
    
    for i, ids in enumerate(input_ids):
        tokens = tokenizer.convert_ids_to_tokens(ids.cpu())
        for j, token in enumerate(tokens):
            if token in [tokenizer.cls_token, tokenizer.sep_token, tokenizer.pad_token]:
                special_tokens_mask[i, j] = True
    
    probability_matrix.masked_fill_(special_tokens_mask, value=0.0)
    masked_indices = torch.bernoulli(probability_matrix).bool()
    
    if masked_indices.sum() == 0:
        rand_idx = torch.randint(1, labels.shape[1]-1, (1,), device=device)
        masked_indices[0, rand_idx] = True
    
    labels[~masked_indices] = -100
    indices_replaced = torch.bernoulli(torch.full(labels.shape, 0.8, device=device)).bool() & masked_indices
    input_ids[indices_replaced] = tokenizer.mask_token_id
    indices_random = torch.bernoulli(torch.full(labels.shape, 0.5, device=device)).bool() & masked_indices & ~indices_replaced
    random_words = torch.randint(len(tokenizer), labels.shape, dtype=torch.long, device=device)
    input_ids[indices_random] = random_words[indices_random]
    
    return input_ids, labels

def extract_features(log_text, num_runs=5):
    errors = []
    cls_embeddings = []
    perplexities = []
    
    for _ in range(num_runs):
        encoding = tokenizer(log_text, padding=True, truncation=True, max_length=MAX_LENGTH, return_tensors='pt').to(device)
        input_ids = encoding["input_ids"]
        attention_mask = encoding["attention_mask"]
        
        with torch.no_grad():
            masked_input, labels = mask_tokens(input_ids.clone())
            outputs = model(input_ids=masked_input, attention_mask=attention_mask, labels=labels, output_hidden_states=True)
        
        loss_val = outputs.loss.item() if outputs.loss.ndim == 0 else outputs.loss.mean().item()
        errors.append(loss_val)
        cls_embeddings.append(outputs.hidden_states[-1][0, 0, :].cpu().numpy())
        perplexities.append(np.exp(loss_val))
    
    return np.mean(errors), np.mean(cls_embeddings, axis=0), np.mean(perplexities)

def predict_anomaly(reconstruction_error, cls_embedding, perplexity):
    features = np.column_stack([
        np.array([reconstruction_error]).reshape(-1, 1),
        np.array([perplexity]).reshape(-1, 1),
        cls_embedding.reshape(1, -1)
    ])
    
    features_scaled = scaler.transform(features)
    
    if_prediction = iforest.predict(features_scaled)[0]
    if_score = iforest.score_samples(features_scaled)[0]
    if_anomaly = (if_prediction == -1)
    
    z_score = np.abs((reconstruction_error - train_stats['mean_error']) / train_stats['std_error'])
    statistical_anomaly = z_score > 7
    
    percentile_anomaly = reconstruction_error > train_stats['threshold_percentile']
    
    votes = [if_anomaly, statistical_anomaly, percentile_anomaly]
    ensemble_prediction = sum(votes) >= 2
    
    combined_score = (
        0.4 * (-if_score) +
        0.3 * z_score +
        0.3 * (reconstruction_error / train_stats['threshold_percentile'])
    )
    
    return int(ensemble_prediction), float(combined_score)

@app.post("/predict", response_model=PredictionOutput)
def predict(data: LogInput):
    torch.manual_seed(42)
    np.random.seed(42)
    random.seed(42)
    log_dict = data.dict()
    formatted_log = build_sequence(log_dict)
    reconstruction_error, cls_embedding, perplexity = extract_features(formatted_log)
    category, combined_score = predict_anomaly(reconstruction_error, cls_embedding, perplexity)
    
    return {
        "category": category,
        "request": log_dict,
        "formatted_log": formatted_log,
        "reconstruction_loss": float(reconstruction_error),
        "combined_score": combined_score,
        "is_anomaly": bool(category)
    }

# Run with: uvicorn main:app --host 0.0.0.0 --port 8000