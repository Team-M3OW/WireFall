import numpy as np
import torch

from api.config import settings
from inference.model import model_instance


def build_sequence(log_data: dict) -> str:
    return (
        f"[CLS] <body_bytes> {log_data.get('body_bytes_sent', '')} </body_bytes> [SEP] "
        f"<request_method> {log_data.get('method', '')} </request_method> [SEP] "
        f"<request_path> {log_data.get('path', '')} </request_path> [SEP] "
        f"<request_protocol> {log_data.get('protocol', '')} </request_protocol> [SEP] "
        f"<request_body> {log_data.get('request_body', '')} </request_body> [SEP]"
    )


def mask_tokens(input_ids, mask_prob=None):
    if mask_prob is None:
        mask_prob = settings.mask_prob
    labels = input_ids.clone()
    device = input_ids.device
    probability_matrix = torch.full(labels.shape, mask_prob, device=device)
    special_tokens_mask = torch.tensor(
        [[val in model_instance.tokenizer.all_special_ids for val in row] for row in labels.tolist()],
        dtype=torch.bool,
        device=device,
    )
    probability_matrix.masked_fill_(special_tokens_mask, value=0.0)
    masked_indices = torch.bernoulli(probability_matrix).bool()

    if masked_indices.sum() == 0:
        rand_idx = torch.randint(1, labels.shape[1] - 1, (1,), device=device)
        masked_indices[0, rand_idx] = True

    labels[~masked_indices] = -100
    indices_replaced = torch.bernoulli(torch.full(labels.shape, 0.8, device=device)).bool() & masked_indices
    input_ids[indices_replaced] = model_instance.tokenizer.mask_token_id
    indices_random = (
        torch.bernoulli(torch.full(labels.shape, 0.5, device=device)).bool() & masked_indices & ~indices_replaced
    )
    random_words = torch.randint(len(model_instance.tokenizer), labels.shape, dtype=torch.long, device=device)
    input_ids[indices_random] = random_words[indices_random]
    return input_ids, labels


def extract_features(log_text: str, num_runs=None):
    if num_runs is None:
        num_runs = settings.num_inference_runs
    errors, cls_embeddings, perplexities = [], [], []

    for _ in range(num_runs):
        encoding = model_instance.tokenizer(
            log_text,
            padding=True,
            truncation=True,
            max_length=settings.max_length,
            return_tensors="pt",
        ).to(model_instance.device)

        with torch.no_grad():
            masked_input, labels = mask_tokens(encoding["input_ids"].clone())
            outputs = model_instance.model(
                input_ids=masked_input,
                attention_mask=encoding["attention_mask"],
                labels=labels,
                output_hidden_states=True,
            )

        loss_val = outputs.loss.item() if outputs.loss.ndim == 0 else outputs.loss.mean().item()
        errors.append(loss_val)
        cls_embeddings.append(outputs.hidden_states[-1][0, 0, :].cpu().numpy())
        perplexities.append(np.exp(loss_val))

    return np.mean(errors), np.mean(cls_embeddings, axis=0), np.mean(perplexities)
