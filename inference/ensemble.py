import numpy as np

from inference.model import model_instance


def predict_anomaly(reconstruction_error, cls_embedding, perplexity, payload=""):
    features = np.column_stack(
        [
            np.array([reconstruction_error, perplexity]).reshape(1, -1),
            cls_embedding.reshape(1, -1),
        ]
    )
    features_scaled = model_instance.scaler.transform(features)

    if_anomaly = model_instance.iforest.predict(features_scaled)[0] == -1

    payload_lower = payload.lower() if isinstance(payload, str) else ""
    attack_keywords = [
        "union select", "select ", "drop table", "insert into", "delete from",
        "<script", "javascript:", "onerror=", "onload=", "fetch(",
        "../", "..\\", "/etc/passwd", "c:\\windows",
        "cat /", "; cat", "| nc ", "| bash", "chmod +x", "wget http", "curl http",
        "' or '1'='1", "1=1", "' union"
    ]
    has_attack_pattern = any(kw in payload_lower for kw in attack_keywords)
    high_loss_anomaly = reconstruction_error > 15.0

    is_anomaly = has_attack_pattern or (if_anomaly and high_loss_anomaly)
    votes = sum([has_attack_pattern, if_anomaly, high_loss_anomaly])

    return int(is_anomaly), {
        "if_anomaly": bool(if_anomaly),
        "has_attack_pattern": bool(has_attack_pattern),
        "high_loss_anomaly": bool(high_loss_anomaly),
        "votes": int(votes),
        "reconstruction_error": float(reconstruction_error),
        "perplexity": float(perplexity),
    }

