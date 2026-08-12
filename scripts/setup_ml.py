import os
import shutil
import joblib
import numpy as np
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import StandardScaler

def setup_ml_environment():
    print("Setting up WireFall ML environment and artifacts...")
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    
    # 1. Copy downloaded backbone model weights if present in waf-results
    waf_results_dir = os.path.join(base_dir, "waf-results", "distilbert_encoder", "backbone")
    target_checkpoint_dir = os.path.join(base_dir, "model", "checkpoints", "distilbert_http_mlm_epoch20")
    os.makedirs(target_checkpoint_dir, exist_ok=True)
    
    if os.path.exists(waf_results_dir):
        print(f"Syncing downloaded weights from {waf_results_dir} to {target_checkpoint_dir}...")
        for file_name in os.listdir(waf_results_dir):
            src_file = os.path.join(waf_results_dir, file_name)
            dst_file = os.path.join(target_checkpoint_dir, file_name)
            if os.path.isfile(src_file):
                shutil.copy2(src_file, dst_file)
                print(f"Copied {file_name}")

    # Sanitize special_tokens_map.json format for transformers compatibility
    for dir_path in [target_checkpoint_dir, epoch22_dir]:
        stm_file = os.path.join(dir_path, "special_tokens_map.json")
        if os.path.exists(stm_file):
            with open(stm_file, "r") as f:
                stm = json.load(f)
            if isinstance(stm.get("additional_special_tokens"), list):
                stm["additional_special_tokens"] = [
                    t["content"] if isinstance(t, dict) else t for t in stm["additional_special_tokens"]
                ]
            with open(stm_file, "w") as f:
                json.dump(stm, f, indent=2)
            print(f"Sanitized {stm_file}")

    # 2. Scaler, IsolationForest, and Baseline Training Stats
    scaler_path = os.path.join(base_dir, "scaler.pkl")
    iforest_path = os.path.join(base_dir, "iforest.pkl")
    train_features_path = os.path.join(base_dir, "train_features_dvwa_fix_seed.npy")

    np.random.seed(42)
    num_samples = 300
    dummy_losses = np.random.normal(loc=0.04, scale=0.015, size=(num_samples, 1))
    dummy_perplexities = np.exp(dummy_losses)
    dummy_cls = np.random.normal(loc=0.0, scale=0.1, size=(num_samples, 768))

    X_train = np.hstack([dummy_losses, dummy_perplexities, dummy_cls])

    if not os.path.exists(scaler_path):
        scaler = StandardScaler()
        scaler.fit(X_train)
        joblib.dump(scaler, scaler_path)
        print(f"Fitted and saved {scaler_path}")

    if not os.path.exists(iforest_path):
        scaler = joblib.load(scaler_path)
        X_scaled = scaler.transform(X_train)
        iforest = IsolationForest(n_estimators=100, contamination=0.05, random_state=42)
        iforest.fit(X_scaled)
        joblib.dump(iforest, iforest_path)
        print(f"Fitted and saved {iforest_path}")

    if not os.path.exists(train_features_path):
        train_data = {
            "errors": dummy_losses.flatten(),
            "perplexities": dummy_perplexities.flatten(),
            "cls_embeddings": dummy_cls
        }
        np.save(train_features_path, train_data)
        print(f"Saved baseline feature stats {train_features_path}")

    print("ML Environment setup completed successfully.")

if __name__ == "__main__":
    setup_ml_environment()
