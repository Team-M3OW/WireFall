import numpy as np

from inference.model import model_instance


def predict_anomaly(reconstruction_error, cls_embedding, perplexity):
    features = np.column_stack(
        [
            np.array([reconstruction_error, perplexity]).reshape(1, -1),
            cls_embedding.reshape(1, -1),
        ]
    )
    features_scaled = model_instance.scaler.transform(features)

    if_anomaly = model_instance.iforest.predict(features_scaled)[0] == -1
    z_score = np.abs(
        (reconstruction_error - model_instance.train_stats["mean_error"]) / model_instance.train_stats["std_error"]
    )
    statistical_anomaly = z_score > 7
    percentile_anomaly = reconstruction_error > model_instance.train_stats["threshold_percentile"]

    votes = sum([if_anomaly, statistical_anomaly, percentile_anomaly])
    return int(votes >= 2), {
        "if_anomaly": bool(if_anomaly),
        "z_score": float(z_score),
        "percentile_anomaly": bool(percentile_anomaly),
        "votes": int(votes),
        "reconstruction_error": float(reconstruction_error),
        "perplexity": float(perplexity),
    }
