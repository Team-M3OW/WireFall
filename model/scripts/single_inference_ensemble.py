import argparse
import json

import joblib
import numpy as np
import torch
from transformers import DistilBertForMaskedLM, DistilBertTokenizer

MAX_LENGTH = 256
device = torch.device("cuda" if torch.cuda.is_available() else "cpu")


def build_sequence(log_data):
    """Build sequence - handles both flat and nested JSON structures"""
    body_bytes = log_data.get("body_bytes_sent", "") or log_data.get("body_bytes", "")
    method = log_data.get("method", "") or log_data.get("request.method", "")
    path = log_data.get("path", "") or log_data.get("request.path", "")
    protocol = log_data.get("protocol", "") or log_data.get("request.protocol", "")
    body = log_data.get("request_body", "") or log_data.get("body", "")

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
        rand_idx = torch.randint(1, labels.shape[1] - 1, (1,), device=device)
        masked_indices[0, rand_idx] = True

    labels[~masked_indices] = -100
    indices_replaced = torch.bernoulli(torch.full(labels.shape, 0.8, device=device)).bool() & masked_indices
    input_ids[indices_replaced] = tokenizer.mask_token_id
    indices_random = (
        torch.bernoulli(torch.full(labels.shape, 0.5, device=device)).bool() & masked_indices & ~indices_replaced
    )
    random_words = torch.randint(len(tokenizer), labels.shape, dtype=torch.long, device=device)
    input_ids[indices_random] = random_words[indices_random]

    return input_ids, labels


def load_training_statistics(train_features_path):
    """Load training statistics"""
    train_data = np.load(train_features_path, allow_pickle=True).item()
    train_errors = train_data["errors"]

    mean_error = train_errors.mean()
    std_error = train_errors.std()
    threshold_percentile = np.percentile(train_errors, 95)

    return {"mean_error": mean_error, "std_error": std_error, "threshold_percentile": threshold_percentile}


def extract_features(log_text, tokenizer, model, num_runs=5):
    """Run multiple times and average to reduce variance - MATCHES BATCH INFERENCE"""
    errors = []
    cls_embeddings = []
    perplexities = []

    model.eval()
    for i in range(num_runs):
        encoding = tokenizer(log_text, padding=True, truncation=True, max_length=MAX_LENGTH, return_tensors="pt").to(
            device
        )

        input_ids = encoding["input_ids"]
        attention_mask = encoding["attention_mask"]

        with torch.no_grad():
            masked_input, labels = mask_tokens(input_ids.clone(), tokenizer)
            outputs = model(
                input_ids=masked_input, attention_mask=attention_mask, labels=labels, output_hidden_states=True
            )

        loss_val = outputs.loss
        if loss_val.ndim == 0:
            error = loss_val.item()
        else:
            error = loss_val.mean().item()

        errors.append(error)
        cls_embeddings.append(outputs.hidden_states[-1][0, 0, :].cpu().numpy())
        perplexities.append(np.exp(error))

    # Average to stabilize
    return np.mean(errors), np.mean(cls_embeddings, axis=0), np.mean(perplexities)


def predict_anomaly(reconstruction_error, cls_embedding, perplexity, scaler, iforest, train_stats):
    """
    ENSEMBLE VOTING METHOD:
    Combines Isolation Forest, Statistical (z-score), and Percentile methods
    via MAJORITY VOTE (2 out of 3 anomaly votes → ANOMALY)
    """
    # Prepare features (same as batch)
    features = np.column_stack(
        [
            np.array([reconstruction_error]).reshape(-1, 1),
            np.array([perplexity]).reshape(-1, 1),
            cls_embedding.reshape(1, -1),
        ]
    )

    features_scaled = scaler.transform(features)

    # Method 1: Isolation Forest
    if_prediction = iforest.predict(features_scaled)[0]
    if_score = iforest.score_samples(features_scaled)[0]
    if_anomaly = if_prediction == -1

    # Method 2: Statistical (z-score > 3)
    z_score = np.abs((reconstruction_error - train_stats["mean_error"]) / train_stats["std_error"])
    statistical_anomaly = z_score > 7

    # Method 3: Percentile (95th)
    percentile_anomaly = reconstruction_error > train_stats["threshold_percentile"]

    # === MAJORITY VOTING ===
    votes = [if_anomaly, statistical_anomaly, percentile_anomaly]
    vote_count = sum(votes)
    ensemble_prediction = vote_count >= 2  # 2 or more votes → ANOMALY

    # Combined score (same as batch)
    combined_score = (
        0.4 * (-if_score) + 0.3 * z_score + 0.3 * (reconstruction_error / train_stats["threshold_percentile"])
    )

    return int(ensemble_prediction), {
        "combined_score": float(combined_score),
        "if_prediction": int(if_anomaly),
        "if_score": float(-if_score),
        "statistical_anomaly": int(statistical_anomaly),
        "z_score": float(z_score),
        "percentile_anomaly": int(percentile_anomaly),
        "reconstruction_error": float(reconstruction_error),
        "perplexity": float(perplexity),
        "votes": {
            "iforest": int(if_anomaly),
            "statistical": int(statistical_anomaly),
            "percentile": int(percentile_anomaly),
            "total_votes": int(vote_count),
        },
    }


def main():
    parser = argparse.ArgumentParser(description="HTTP Log Anomaly Detection - Ensemble (Matches Batch Inference)")
    parser.add_argument("--model", required=True, help="Model directory path")
    parser.add_argument("--train-features", required=True, help="Path to train_features.npy")
    parser.add_argument("--scaler", required=True, help="Path to scaler.pkl")
    parser.add_argument("--iforest", required=True, help="Path to iforest.pkl")
    parser.add_argument("--input", required=True, help="Input JSON file path")
    parser.add_argument("--output", required=True, help="Output JSON file path")
    parser.add_argument("--num-runs", type=int, default=5, help="Number of masking runs to average")

    args = parser.parse_args()

    # Set seed for reproducibility (IMPORTANT - matches batch)
    torch.manual_seed(42)
    np.random.seed(42)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(42)

    print(f"Loading model from: {args.model}")
    tokenizer = DistilBertTokenizer.from_pretrained(args.model)
    model = DistilBertForMaskedLM.from_pretrained(args.model)
    model.to(device)
    model.eval()

    print(f"Loading training statistics from: {args.train_features}")
    train_stats = load_training_statistics(args.train_features)

    print(f"Loading scaler from: {args.scaler}")
    scaler = joblib.load(args.scaler)

    print(f"Loading isolation forest from: {args.iforest}")
    iforest = joblib.load(args.iforest)

    print("\nTraining Statistics:")
    print(f"  Mean: {train_stats['mean_error']:.4f}")
    print(f"  Std: {train_stats['std_error']:.4f}")
    print(f"  95th percentile: {train_stats['threshold_percentile']:.4f}")

    with open(args.input) as f:
        log_data = json.load(f)

    formatted_log = build_sequence(log_data)
    print(f"\n{formatted_log}")

    reconstruction_error, cls_embedding, perplexity = extract_features(
        formatted_log, tokenizer, model, num_runs=args.num_runs
    )

    category, details = predict_anomaly(reconstruction_error, cls_embedding, perplexity, scaler, iforest, train_stats)

    result = {
        "request": log_data,
        "category": category,
        "reconstruction_loss": float(reconstruction_error),
        "details": details,
    }

    with open(args.output, "w") as f:
        json.dump(result, f, indent=2)

    print(f"\n{'=' * 60}")
    print(f"RESULT: {'ANOMALY' if category == 1 else 'SAFE'}")
    print(f"{'=' * 60}")
    print(f"Reconstruction Loss: {reconstruction_error:.4f}")
    print(f"Combined Score: {details['combined_score']:.4f}")
    print("\nEnsemble Breakdown:")
    print(f"  [{'✓' if details['if_prediction'] else '✗'}] Isolation Forest (score: {details['if_score']:.4f})")
    print(
        f"  [{'✓' if details['statistical_anomaly'] else '✗'}] Statistical (z-score: {details['z_score']:.2f} {'> 3' if details['statistical_anomaly'] else '< 3'})"
    )
    print(
        f"  [{'✓' if details['percentile_anomaly'] else '✗'}] Percentile (loss: {reconstruction_error:.4f} {'>' if details['percentile_anomaly'] else '<'} {train_stats['threshold_percentile']:.4f})"
    )
    print(f"\nOutput saved to: {args.output}")


if __name__ == "__main__":
    main()
