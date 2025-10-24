import torch
import json
import argparse
import numpy as np
from transformers import DistilBertTokenizer, DistilBertForMaskedLM

MAX_LENGTH = 256
device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

def build_sequence(log_data):
    """Build sequence - handles both flat and nested JSON structures"""
    body_bytes = log_data.get('body_bytes_sent', '') or log_data.get('body_bytes', '')
    method = log_data.get('method', '') or log_data.get('request.method', '')
    path = log_data.get('path', '') or log_data.get('request.path', '')
    protocol = log_data.get('protocol', '') or log_data.get('request.protocol', '')
    body = log_data.get('request_body', '') or log_data.get('body', '')
    
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
    """Load training statistics to compute threshold"""
    train_data = np.load(train_features_path, allow_pickle=True).item()
    train_errors = train_data['errors']
    
    mean_error = train_errors.mean()
    std_error = train_errors.std()
    threshold_percentile = np.percentile(train_errors, 95)
    
    return {
        'mean_error': mean_error,
        'std_error': std_error,
        'threshold_percentile': threshold_percentile
    }

def extract_features(log_text, tokenizer, model, num_runs=5):
    """Run multiple times and average to reduce variance from random masking"""
    errors = []
    
    model.eval()
    for i in range(num_runs):
        encoding = tokenizer(
            log_text,
            padding=True,
            truncation=True,
            max_length=MAX_LENGTH,
            return_tensors='pt'
        ).to(device)
        
        input_ids = encoding["input_ids"]
        attention_mask = encoding["attention_mask"]
        
        with torch.no_grad():
            masked_input, labels = mask_tokens(input_ids.clone(), tokenizer)
            outputs = model(
                input_ids=masked_input,
                attention_mask=attention_mask,
                labels=labels
            )
        
        # Handle both scalar and batched loss
        loss_val = outputs.loss
        if loss_val.ndim == 0:
            error = loss_val.item()
        else:
            error = loss_val.mean().item()
        
        errors.append(error)
    
    # Return average and individual runs
    return np.mean(errors), errors

def predict_anomaly(reconstruction_error, train_stats):
    """Predict using 95th percentile threshold from training data"""
    threshold = train_stats['threshold_percentile']
    is_anomaly = reconstruction_error > threshold
    
    # Also compute z-score for additional info
    z_score = abs(reconstruction_error - train_stats['mean_error']) / train_stats['std_error']
    
    return int(is_anomaly), {
        'threshold': float(threshold),
        'z_score': float(z_score),
        'mean_error': float(train_stats['mean_error']),
        'std_error': float(train_stats['std_error'])
    }

def main():
    parser = argparse.ArgumentParser(description='HTTP Log Anomaly Detection - Using Training Threshold')
    parser.add_argument('--model', required=True, help='Model directory path')
    parser.add_argument('--train-features', required=True, help='Path to train_features.npy')
    parser.add_argument('--input', required=True, help='Input JSON file path')
    parser.add_argument('--output', required=True, help='Output JSON file path')
    parser.add_argument('--num-runs', type=int, default=5, help='Number of masking runs to average')
    
    args = parser.parse_args()
    
    # Set seed for reproducibility
    torch.manual_seed(42)
    np.random.seed(42)
    
    print(f"Loading model from: {args.model}")
    tokenizer = DistilBertTokenizer.from_pretrained(args.model)
    model = DistilBertForMaskedLM.from_pretrained(args.model)
    model.to(device)
    model.eval()
    
    print(f"Loading training statistics from: {args.train_features}")
    train_stats = load_training_statistics(args.train_features)
    print(f"Training mean: {train_stats['mean_error']:.4f}")
    print(f"Training std: {train_stats['std_error']:.4f}")
    print(f"95th percentile threshold: {train_stats['threshold_percentile']:.4f}")
    
    with open(args.input, 'r') as f:
        log_data = json.load(f)
    
    formatted_log = build_sequence(log_data)
    print(f"\n{formatted_log}")
    
    reconstruction_error, error_runs = extract_features(
        formatted_log, tokenizer, model, num_runs=args.num_runs
    )
    
    category, details = predict_anomaly(reconstruction_error, train_stats)
    
    result = {
        "request": log_data,
        "category": category,
        "reconstruction_loss": float(reconstruction_error),
        "details": details
    }
    
    with open(args.output, 'w') as f:
        json.dump(result, f, indent=2)
    
    print(f"\nCategory: {'ANOMALY' if category == 1 else 'SAFE'}")
    print(f"Reconstruction Loss: {reconstruction_error:.4f}")
    print(f"Threshold (95th percentile): {details['threshold']:.4f}")
    print(f"Z-score: {details['z_score']:.2f}")
    print(f"Output saved to: {args.output}")

if __name__ == "__main__":
    main()