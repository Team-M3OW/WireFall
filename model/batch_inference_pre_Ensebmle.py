import torch
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from transformers import DistilBertTokenizer, DistilBertForMaskedLM
from sklearn.preprocessing import StandardScaler
from sklearn.ensemble import IsolationForest
from sklearn.metrics import confusion_matrix, ConfusionMatrixDisplay
from tqdm import tqdm
import joblib, json, random
from scipy import stats

# ==============================
# CONFIG
# ==============================
MODEL_PATH = "./distilbert_http_mlm_epoch22"
TRAIN_FEATURES = "./train_features_dvwa_fix_seed.npy"
SCALER_PATH = "./scaler.pkl"
IFOREST_PATH = "./iforest.pkl"
TEST_CSV = "./teamm3ow-waf-dataset/test-data-set.csv"
MAX_LENGTH = 256
BATCH_SIZE = 64
device = torch.device("cuda" if torch.cuda.is_available() else "cpu")


# ==============================
# REPRODUCIBILITY
# ==============================
def set_seed(seed=42):
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)
set_seed(42)


# ==============================
# UTILITIES
# ==============================
def build_sequence(row):
    """Build sequence - handles both flat and nested JSON structures"""
    body_bytes = row.get('body_bytes_sent', '') or row.get('body_bytes', '')
    method = row.get('method', '') or row.get('request.method', '')
    path = row.get('path', '') or row.get('request.path', '')
    protocol = row.get('protocol', '') or row.get('request.protocol', '')
    body = row.get('request_body', '') or row.get('body', '')
    
    seq = (
        f"[CLS] "
        f"<body_bytes> {body_bytes} </body_bytes> [SEP] "
        f"<request_method> {method} </request_method> [SEP] "
        f"<request_path> {path} </request_path> [SEP] "
        f"<request_protocol> {protocol} </request_protocol> [SEP] "
        f"<request_body> {body} </request_body> [SEP]"
    )
    return seq


def mask_tokens(input_ids, tokenizer, mask_prob=0.15):
    device = input_ids.device
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


def load_training_statistics(train_features_path):
    train_data = np.load(train_features_path, allow_pickle=True).item()
    train_errors = train_data['errors']
    return {
        'mean_error': train_errors.mean(),
        'std_error': train_errors.std(),
        'threshold_percentile': np.percentile(train_errors, 95)
    }


# ==============================
# MODEL & TOKENIZER
# ==============================
print(f"Loading model from {MODEL_PATH}")
tokenizer = DistilBertTokenizer.from_pretrained(MODEL_PATH)
model = DistilBertForMaskedLM.from_pretrained(MODEL_PATH).to(device)
model.eval()


# ==============================
# FEATURE EXTRACTION (BATCH)
# ==============================
def extract_features(log_texts, tokenizer, model, num_runs=3):
    all_errors, all_cls, all_perp = [], [], []

    for i in range(num_runs):
        encodings = tokenizer(
            log_texts,
            padding=True,
            truncation=True,
            max_length=MAX_LENGTH,
            return_tensors='pt'
        ).to(device)

        input_ids = encodings["input_ids"]
        attention_mask = encodings["attention_mask"]
        with torch.no_grad():
            masked_input, labels = mask_tokens(input_ids.clone(), tokenizer)
            outputs = model(input_ids=masked_input, attention_mask=attention_mask, labels=labels, output_hidden_states=True)
        
        loss_vals = outputs.loss
        if loss_vals.ndim == 0:
            loss_vals = loss_vals.repeat(len(log_texts))
        errors = loss_vals.detach().cpu().numpy()
        cls_embeddings = outputs.hidden_states[-1][:, 0, :].cpu().numpy()
        perplexities = np.exp(errors)

        all_errors.append(errors)
        all_cls.append(cls_embeddings)
        all_perp.append(perplexities)
    
    return np.mean(all_errors, axis=0), np.mean(all_cls, axis=0), np.mean(all_perp, axis=0)


# ==============================
# ENSEMBLE VOTING (EXACTLY SAME)
# ==============================
def predict_anomaly(reconstruction_error, cls_embedding, perplexity, scaler, iforest, train_stats):
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
    vote_count = sum(votes)
    ensemble_prediction = (vote_count >= 2)

    combined_score = (
        0.4 * (-if_score) +
        0.3 * z_score +
        0.3 * (reconstruction_error / train_stats['threshold_percentile'])
    )

    return int(ensemble_prediction), combined_score, z_score, if_score, votes


# ==============================
# BATCH INFERENCE
# ==============================
def batch_inference(df, tokenizer, model, scaler, iforest, train_stats, batch_size=64):
    preds, scores, errors, zscores = [], [], [], []
    logs = [build_sequence(row) for _, row in df.iterrows()]
    
    for i in tqdm(range(0, len(logs), batch_size), desc="Batch inference", ncols=100):
        batch_logs = logs[i:i+batch_size]
        err, cls, perp = extract_features(batch_logs, tokenizer, model)
        
        for j in range(len(batch_logs)):
            category, combined, z, if_score, _ = predict_anomaly(
                err[j], cls[j], perp[j], scaler, iforest, train_stats
            )
            preds.append(category)
            scores.append(combined)
            errors.append(err[j])
            zscores.append(z)
    
    return np.array(preds), np.array(scores), np.array(errors), np.array(zscores)


# ==============================
# MAIN EXECUTION
# ==============================
if __name__ == "__main__":
    print("Loading scaler and iforest...")
    scaler = joblib.load(SCALER_PATH)
    iforest = joblib.load(IFOREST_PATH)
    train_stats = load_training_statistics(TRAIN_FEATURES)

    print(f"Training Stats → mean={train_stats['mean_error']:.4f}, std={train_stats['std_error']:.4f}, 95th={train_stats['threshold_percentile']:.4f}")

    test_df = pd.read_csv(TEST_CSV).fillna("").astype(str)
    preds, scores, errors, zscores = batch_inference(test_df, tokenizer, model, scaler, iforest, train_stats, batch_size=BATCH_SIZE)

    # True labels (0: normal, 1: anomaly)
    y_true = np.zeros(len(test_df))
    y_true[1300:] = 1
    y_pred = preds

    # Confusion matrix
    cm = confusion_matrix(y_true, y_pred)
    disp = ConfusionMatrixDisplay(confusion_matrix=cm, display_labels=['Normal', 'Anomaly'])
    disp.plot(cmap='Blues', values_format='d')
    plt.title("Confusion Matrix (Ensemble Voting)")
    plt.savefig("ensemble_confusion_matrix.png", dpi=150)
    plt.show()

    print(f"\nConfusion Matrix:\n{cm}")
    print(f"Detected {(y_pred.sum()/len(y_pred))*100:.2f}% anomalies")

    # Wrong predictions
    wrong_idx = np.where(y_true != y_pred)[0]
    with open("wrong_predictions.txt", "w") as f:
        for idx in wrong_idx:
            f.write(f"Index: {idx}\nTrue: {y_true[idx]} Pred: {y_pred[idx]}\nError: {errors[idx]:.4f} Z: {zscores[idx]:.2f} Score: {scores[idx]:.4f}\n{'='*80}\n")
    print(f"Saved {len(wrong_idx)} wrong predictions → wrong_predictions.txt")

    np.save("test_features.npy", {"errors": errors, "scores": scores, "z_scores": zscores})
