import argparse
import json

import numpy as np
import torch
from transformers import DistilBertForMaskedLM, DistilBertTokenizer

MAX_LENGTH = 256
device = torch.device("cuda" if torch.cuda.is_available() else "cpu")


def build_sequence(log_data):
    """Build sequence from JSON log data"""
    body_bytes = log_data.get("body_bytes_sent", "")
    method = (
        log_data.get("request", {}).get("method", "")
        if isinstance(log_data.get("request"), dict)
        else log_data.get("request.method", "")
    )
    path = (
        log_data.get("request", {}).get("path", "")
        if isinstance(log_data.get("request"), dict)
        else log_data.get("request.path", "")
    )
    protocol = (
        log_data.get("request", {}).get("protocol", "")
        if isinstance(log_data.get("request"), dict)
        else log_data.get("request.protocol", "")
    )
    body = log_data.get("request_body", "")

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


def extract_features_multiple_runs(log_text, tokenizer, model, num_runs=10):
    """Run feature extraction multiple times to check variance"""
    reconstruction_errors = []

    model.eval()
    for run in range(num_runs):
        # Set different seed for each run to see variance
        torch.manual_seed(42 + run)
        np.random.seed(42 + run)

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
            reconstruction_error = loss_val.item()
        else:
            reconstruction_error = loss_val.mean().item()

        reconstruction_errors.append(reconstruction_error)

    return reconstruction_errors


def main():
    parser = argparse.ArgumentParser(description="Debug Distribution Mismatch")
    parser.add_argument("--model", required=True, help="Model directory path")
    parser.add_argument("--train_features", required=True, help="Train features .npy file")
    parser.add_argument("--input", required=True, help="Input JSON file")
    parser.add_argument("--runs", type=int, default=10, help="Number of runs to check variance")

    args = parser.parse_args()

    print("=" * 80)
    print("DISTRIBUTION MISMATCH DEBUGGER")
    print("=" * 80)

    # Load training statistics
    print(f"\n1. Loading training features from: {args.train_features}")
    train_data = np.load(args.train_features, allow_pickle=True).item()
    train_errors = train_data["errors"]

    print("\nTraining Data Statistics:")
    print(f"  Number of samples: {len(train_errors)}")
    print(f"  Mean error: {train_errors.mean():.4f}")
    print(f"  Std error: {train_errors.std():.4f}")
    print(f"  Min error: {train_errors.min():.4f}")
    print(f"  Max error: {train_errors.max():.4f}")
    print(f"  Median error: {np.median(train_errors):.4f}")
    print(f"  95th percentile: {np.percentile(train_errors, 95):.4f}")
    print(f"  99th percentile: {np.percentile(train_errors, 99):.4f}")

    # Load model
    print(f"\n2. Loading model from: {args.model}")
    tokenizer = DistilBertTokenizer.from_pretrained(args.model)
    model = DistilBertForMaskedLM.from_pretrained(args.model)
    model.to(device)
    model.eval()

    # Load and format test log
    print(f"\n3. Loading test log from: {args.input}")
    with open(args.input) as f:
        log_data = json.load(f)

    formatted_log = build_sequence(log_data)
    print("\nFormatted log (first 200 chars):")
    print(f"  {formatted_log[:200]}...")
    print(f"  Length: {len(formatted_log)} characters")

    # Tokenize and check
    encoding = tokenizer(formatted_log, padding=True, truncation=True, max_length=MAX_LENGTH, return_tensors="pt")
    print("\nTokenization info:")
    print(f"  Number of tokens: {encoding['input_ids'].shape[1]}")
    print(f"  Tokens: {tokenizer.convert_ids_to_tokens(encoding['input_ids'][0])[:20]}...")

    # Run multiple times to check variance
    print(f"\n4. Running feature extraction {args.runs} times...")
    reconstruction_errors = extract_features_multiple_runs(formatted_log, tokenizer, model, args.runs)

    print(f"\nTest Sample Statistics (over {args.runs} runs):")
    print(f"  Mean error: {np.mean(reconstruction_errors):.4f}")
    print(f"  Std error: {np.std(reconstruction_errors):.4f}")
    print(f"  Min error: {np.min(reconstruction_errors):.4f}")
    print(f"  Max error: {np.max(reconstruction_errors):.4f}")
    print(f"  All errors: {[f'{e:.4f}' for e in reconstruction_errors]}")

    # Compare distributions
    print("\n5. Distribution Comparison:")
    mean_test_error = np.mean(reconstruction_errors)
    train_mean = train_errors.mean()
    train_std = train_errors.std()

    z_score = abs(mean_test_error - train_mean) / train_std
    percentile_rank = (train_errors < mean_test_error).sum() / len(train_errors) * 100

    print(f"  Test error is {mean_test_error - train_mean:.4f} away from training mean")
    print(f"  Z-score: {z_score:.2f} standard deviations")
    print(f"  Percentile rank: {percentile_rank:.1f}% (in training data)")

    if z_score > 3:
        print(f"\n⚠️  WARNING: Test sample is {z_score:.1f}σ away from training mean!")
        print("    This indicates a distribution mismatch.")

    # Recommendations
    print("\n6. Analysis & Recommendations:")

    if z_score > 10:
        print("  ❌ SEVERE MISMATCH DETECTED!")
        print("     Possible causes:")
        print("     - Training data format differs from inference data")
        print("     - Model was trained on different preprocessing")
        print("     - Input JSON structure doesn't match training CSV")
        print("\n     Action: Check that build_sequence() matches training preprocessing")
    elif z_score > 3:
        print("  ⚠️  MODERATE MISMATCH")
        print("     The test sample is unusual but may be valid")
        print("     Consider adjusting detection thresholds")
    else:
        print("  ✅ Distribution looks reasonable")

    # Check if training data seems realistic
    if train_mean < 0.1:
        print("\n  ⚠️  Training mean error is very low (<0.1)")
        print("     This might indicate overfitting or data leakage during training")

    print("\n" + "=" * 80)


if __name__ == "__main__":
    main()
