import torch
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from transformers import DistilBertTokenizer, DistilBertForMaskedLM
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import confusion_matrix, ConfusionMatrixDisplay
from scipy import stats

MODEL_PATH = "/content/drive/MyDrive/distilbert_http_mlm_epoch22"
MAX_LENGTH = 256
CSV_FILE = "./teamm3ow-waf-dataset/nginx_access_parsed.csv"
TRAIN_CSV = "./teamm3ow-waf-dataset/nginx_access_parsed.csv"
TEST_CSV = "/content/teamm3ow-waf-dataset/test-data-set.csv"
device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

tokenizer = DistilBertTokenizer.from_pretrained(MODEL_PATH)
model = DistilBertForMaskedLM.from_pretrained(MODEL_PATH)
model.to(device)
model.eval()

def build_sequence(row):
    seq = (
        f"[CLS] "
        f"<body_bytes> {row['body_bytes_sent']} </body_bytes> [SEP] "
        f"<request_method> {row['request.method']} </request_method> [SEP] "
        f"<request_path> {row['request.path']} </request_path> [SEP] "
        f"<request_protocol> {row['request.protocol']} </request_protocol> [SEP] "
        f"<request_body> {row['request_body']} </request_body> [SEP]"
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


from tqdm import tqdm

def extract_features(logs, batch_size=64):
    reconstruction_errors = []
    cls_embeddings = []
    perplexities = []

    model.eval()
    with torch.no_grad():
        for i in tqdm(range(0, len(logs), batch_size), desc="Extracting features", ncols=100):
            batch_logs = logs[i:i+batch_size]
            encodings = tokenizer(
                batch_logs,
                padding=True,
                truncation=True,
                max_length=MAX_LENGTH,
                return_tensors='pt'
            ).to(device)

            input_ids = encodings["input_ids"]
            attention_mask = encodings["attention_mask"]

            # Mask tokens batchwise
            masked_input, labels = mask_tokens(input_ids.clone(), tokenizer)

            outputs = model(
                input_ids=masked_input,
                attention_mask=attention_mask,
                labels=labels,
                output_hidden_states=True
            )

            # Handle batched loss safely
            loss_val = outputs.loss
            if loss_val.ndim == 0:
                loss_val = loss_val.repeat(len(batch_logs))
            losses = loss_val.detach().cpu().numpy()

            # Collect features for each sample in batch
            for j in range(len(batch_logs)):
                reconstruction_errors.append(losses[j])
                cls_embeddings.append(outputs.hidden_states[-1][j, 0, :].cpu().numpy())
                perplexities.append(np.exp(losses[j]))

    reconstruction_errors = np.array(reconstruction_errors)
    cls_embeddings = np.vstack(cls_embeddings)
    perplexities = np.array(perplexities)

    return reconstruction_errors, cls_embeddings, perplexities



class AdvancedAnomalyDetector:
    def __init__(self):
        self.isolation_forest = IsolationForest(contamination=0.1, random_state=42)
        self.scaler = StandardScaler()
        self.threshold_percentile = None
        self.mean_error = None
        self.std_error = None

    def fit(self, reconstruction_errors, cls_embeddings, perplexities):
        features = np.column_stack([
            reconstruction_errors.reshape(-1, 1),
            perplexities.reshape(-1, 1),
            cls_embeddings
        ])

        features_scaled = self.scaler.fit_transform(features)
        self.isolation_forest.fit(features_scaled)

        self.mean_error = reconstruction_errors.mean()
        self.std_error = reconstruction_errors.std()
        self.threshold_percentile = np.percentile(reconstruction_errors, 95)

        print(f"Fitted detector:")
        print(f"  Mean error: {self.mean_error:.4f}")
        print(f"  Std error: {self.std_error:.4f}")
        print(f"  95th percentile: {self.threshold_percentile:.4f}")

    def predict(self, reconstruction_errors, cls_embeddings, perplexities):
        features = np.column_stack([
            reconstruction_errors.reshape(-1, 1),
            perplexities.reshape(-1, 1),
            cls_embeddings
        ])

        features_scaled = self.scaler.transform(features)

        if_predictions = self.isolation_forest.predict(features_scaled)
        if_scores = self.isolation_forest.score_samples(features_scaled)

        z_scores = np.abs((reconstruction_errors - self.mean_error) / self.std_error)
        statistical_anomalies = z_scores > 3

        percentile_anomalies = reconstruction_errors > self.threshold_percentile

        combined_scores = (
            0.4 * (-if_scores) +
            0.3 * z_scores +
            0.3 * (reconstruction_errors / self.threshold_percentile)
        )

        ensemble_predictions = (if_predictions == -1) | statistical_anomalies | percentile_anomalies

        return {
            'predictions': ensemble_predictions,
            'scores': combined_scores,
            'if_predictions': if_predictions == -1,
            'statistical_anomalies': statistical_anomalies,
            'percentile_anomalies': percentile_anomalies,
            'reconstruction_errors': reconstruction_errors,
            'z_scores': z_scores
        }

if __name__ == "__main__":
    train_df = pd.read_csv(TRAIN_CSV)
    test_df = pd.read_csv(TEST_CSV)

    train_df = train_df.fillna('').astype(str)
    test_df = test_df.fillna('').astype(str)

    train_logs = [build_sequence(row) for _, row in train_df.iterrows()]
    test_logs = [build_sequence(row) for _, row in test_df.iterrows()]

    print("Extracting features from training data...")
    train_errors, train_cls, train_perp = extract_features(train_logs)

    print("\nFitting detector...")
    detector = AdvancedAnomalyDetector()
    detector.fit(train_errors, train_cls, train_perp)

    print("\nExtracting features from test data...")
    test_errors, test_cls, test_perp = extract_features(test_logs)
    from tqdm import tqdm

    print("\nDetecting anomalies...")
    results = detector.predict(test_errors, test_cls, test_perp)

    n_anomalies = results['predictions'].sum()
    print(f"\nDetected {n_anomalies} anomalies ({n_anomalies/len(test_logs)*100:.2f}%)")
    print(f"  Isolation Forest: {results['if_predictions'].sum()}")
    print(f"  Statistical (z>3): {results['statistical_anomalies'].sum()}")
    print(f"  Percentile (95th): {results['percentile_anomalies'].sum()}")

    plt.figure(figsize=(18, 12))

    plt.subplot(3, 3, 1)
    plt.hist(test_errors[~results['predictions']], bins=50, alpha=0.7, label='Normal', color='green')
    plt.hist(test_errors[results['predictions']], bins=50, alpha=0.7, label='Anomaly', color='red')
    plt.xlabel('Reconstruction Error')
    plt.ylabel('Count')
    plt.title('Reconstruction Error Distribution')
    plt.legend()

    plt.subplot(3, 3, 2)
    plt.plot(test_errors, alpha=0.6, linewidth=0.5)
    plt.scatter(np.where(results['predictions'])[0], test_errors[results['predictions']],
                color='red', s=30, alpha=0.8, label='Anomalies', zorder=5)
    plt.axhline(detector.threshold_percentile, color='orange', linestyle='--', label='95th percentile')
    plt.xlabel('Sample Index')
    plt.ylabel('Reconstruction Error')
    plt.title('Reconstruction Error Over Time')
    plt.legend()

    plt.subplot(3, 3, 3)
    plt.scatter(test_errors, results['scores'], c=results['predictions'], cmap='RdYlGn_r', alpha=0.6)
    plt.xlabel('Reconstruction Error')
    plt.ylabel('Combined Anomaly Score')
    plt.title('Reconstruction vs Combined Score')
    plt.colorbar(label='Anomaly')

    plt.subplot(3, 3, 4)
    plt.hist(results['z_scores'][~results['predictions']], bins=50, alpha=0.7, label='Normal', color='green')
    plt.hist(results['z_scores'][results['predictions']], bins=50, alpha=0.7, label='Anomaly', color='red')
    plt.axvline(3, color='black', linestyle='--', label='z=3')
    plt.xlabel('Z-Score')
    plt.ylabel('Count')
    plt.title('Z-Score Distribution')
    plt.legend()

    plt.subplot(3, 3, 5)
    from sklearn.decomposition import PCA
    pca = PCA(n_components=2)
    test_cls_2d = pca.fit_transform(test_cls)
    plt.scatter(test_cls_2d[~results['predictions'], 0], test_cls_2d[~results['predictions'], 1],
                alpha=0.5, s=20, label='Normal', color='green')
    plt.scatter(test_cls_2d[results['predictions'], 0], test_cls_2d[results['predictions'], 1],
                alpha=0.8, s=40, label='Anomaly', color='red', marker='x')
    plt.xlabel('PCA Component 1')
    plt.ylabel('PCA Component 2')
    plt.title('[CLS] Embedding Space')
    plt.legend()

    plt.subplot(3, 3, 6)
    methods = ['Isolation\nForest', 'Statistical\n(z>3)', 'Percentile\n(95th)', 'Ensemble']
    counts = [
        results['if_predictions'].sum(),
        results['statistical_anomalies'].sum(),
        results['percentile_anomalies'].sum(),
        results['predictions'].sum()
    ]
    plt.bar(methods, counts, color=['steelblue', 'orange', 'purple', 'red'])
    plt.ylabel('Number of Anomalies')
    plt.title('Anomalies by Method')
    plt.xticks(rotation=0)

    plt.subplot(3, 3, 7)
    plt.hist(test_perp[~results['predictions']], bins=50, alpha=0.7, label='Normal', color='green')
    plt.hist(test_perp[results['predictions']], bins=50, alpha=0.7, label='Anomaly', color='red')
    plt.xlabel('Perplexity')
    plt.ylabel('Count')
    plt.title('Perplexity Distribution')
    plt.legend()

    plt.subplot(3, 3, 8)
    normal_errors = test_errors[~results['predictions']]
    anomaly_errors = test_errors[results['predictions']]
    plt.boxplot([normal_errors, anomaly_errors], labels=['Normal', 'Anomaly'])
    plt.ylabel('Reconstruction Error')
    plt.title('Error Distribution by Class')
    plt.grid(axis='y', alpha=0.3)

    plt.subplot(3, 3, 9)
    plt.plot(results['scores'], alpha=0.6, linewidth=0.5)
    plt.scatter(np.where(results['predictions'])[0], results['scores'][results['predictions']],
                color='red', s=30, alpha=0.8, label='Anomalies')
    plt.xlabel('Sample Index')
    plt.ylabel('Combined Score')
    plt.title('Combined Anomaly Scores')
    plt.legend()

    plt.tight_layout()
    plt.savefig('advanced_mlm_results.png', dpi=150)
    print("\nSaved plot to advanced_mlm_results.png")
    plt.show()
    print("\nTop 15 Anomalies (by combined score):")
    top_indices = np.argsort(results['scores'])[-15:][::-1]
    for rank, idx in enumerate(top_indices, 1):
        print(f"\n[{rank}] Combined Score: {results['scores'][idx]:.4f}")
        print(f"    Reconstruction Error: {test_errors[idx]:.4f}")
        print(f"    Z-Score: {results['z_scores'][idx]:.2f}")
        print(f"    IF: {'✓' if results['if_predictions'][idx] else '✗'} | "
              f"Stat: {'✓' if results['statistical_anomalies'][idx] else '✗'} | "
              f"Perc: {'✓' if results['percentile_anomalies'][idx] else '✗'}")
        print(f"    {test_logs[idx][:100]}...")
    y_true = np.zeros(len(test_logs), dtype=int)
    y_true[1300:] = 1  # first 0–1300 normal, rest anomalies

    # Predictions from your detector (True=anomaly)
    y_pred = results['predictions'].astype(int)
    cm = confusion_matrix(y_true, y_pred)
    disp = ConfusionMatrixDisplay(confusion_matrix=cm, display_labels=['Normal', 'Anomaly'])
    disp.plot(cmap='Blues', values_format='d')
    plt.title("Confusion Matrix – MLM + Isolation Forest Ensemble")
    plt.savefig('confusion_matrix.png', dpi=150)
    plt.show()

    print("\nConfusion Matrix:")
    print(cm)
    wrong_indices = np.where(y_true != y_pred)[0]
    with open("wrong_predictions.txt", "w") as f:
        for idx in wrong_indices:
            f.write(f"Index: {idx}\n")
            f.write(f"True Label: {'Anomaly' if y_true[idx] else 'Normal'}\n")
            f.write(f"Predicted: {'Anomaly' if y_pred[idx] else 'Normal'}\n")
            f.write(f"Combined Score: {results['scores'][idx]:.4f}\n")
            f.write(f"Reconstruction Error: {results['reconstruction_errors'][idx]:.4f}\n")
            f.write(f"Z-Score: {results['z_scores'][idx]:.2f}\n")
            f.write(f"Snippet: {test_logs[idx][:150]}...\n")
            f.write("="*80 + "\n")

    print(f"\nSaved wrong predictions ({len(wrong_indices)}) to wrong_predictions.txt")
    np.save("/content/drive/MyDrive/train_features.npy", {
        'errors': train_errors,
        'cls_embeddings': train_cls,
        'perplexities': train_perp
    })
    np.save("test_features.npy", {
        'errors': test_errors,
        'cls_embeddings': test_cls,
        'perplexities': test_perp
    })

    print("\nSaved extracted features to train_features.npy and test_features.npy")
