import torch
import joblib
import numpy as np
from transformers import DistilBertTokenizer, DistilBertForMaskedLM
from api.config import settings


class AnomalyModel:
    def __init__(self):
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self.tokenizer = None
        self.model = None
        self.scaler = None
        self.iforest = None
        self.train_stats = None
        self.loaded = False

    def load(self):
        try:
            self.tokenizer = DistilBertTokenizer.from_pretrained(settings.model_path)
            self.model = DistilBertForMaskedLM.from_pretrained(settings.model_path)
            self.model.to(self.device)
            self.model.eval()

            self.scaler = joblib.load(settings.scaler_path)
            self.iforest = joblib.load(settings.iforest_path)
            train_data = np.load(settings.train_features_path, allow_pickle=True).item()
            self.train_stats = {
                "mean_error": train_data["errors"].mean(),
                "std_error": train_data["errors"].std(),
                "threshold_percentile": np.percentile(train_data["errors"], 95),
            }
            self.loaded = True
            return True
        except Exception:
            self.loaded = False
            return False

    def to_device(self, tensor):
        return tensor.to(self.device)


model_instance = AnomalyModel()
