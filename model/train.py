import torch
from torch.utils.data import Dataset, DataLoader
from transformers import DistilBertTokenizer, DistilBertForMaskedLM, get_linear_schedule_with_warmup
from tqdm import tqdm
import pandas as pd
import os
from log_dataloader import *

CSV_FILE = "./teamm3ow-waf-dataset/nginx_access_parsed.csv"
EPOCHS = 30
BATCH_SIZE = 16
LR = 5e-5
MAX_LENGTH = 256
MODEL_PATH = "distilbert/distilbert-base-cased"
SAVE_PATH = "/content/drive/MyDrive/distilbert_http_mlm"
VAL_SPLIT = 0.1
PATIENCE = 3
device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
print("Using device:", device)

def collate_fn(batch):
    encodings = tokenizer(
        batch,
        padding=True,
        truncation=True,
        max_length=MAX_LENGTH,
        return_tensors='pt'
    )
    return encodings

tokenizer = DistilBertTokenizer.from_pretrained(MODEL_PATH)
model = DistilBertForMaskedLM.from_pretrained(MODEL_PATH)
model.to(device)
dataset = HTTPLogsDataset(CSV_FILE, max_length=MAX_LENGTH)
train_size = int((1 - VAL_SPLIT) * len(dataset))
val_size = len(dataset) - train_size
train_dataset, val_dataset = torch.utils.data.random_split(dataset, [train_size, val_size])

special_tokens = {
'additional_special_tokens': [
    '<body_bytes>', '</body_bytes>',
    '<request_method>', '</request_method>',
    '<request_path>', '</request_path>',
    '<request_protocol>', '</request_protocol>',
    '<request_body>', '</request_body>'
]
}

tokenizer.add_special_tokens(special_tokens)
model.resize_token_embeddings(len(tokenizer))

train_dataloader = DataLoader(train_dataset, batch_size=BATCH_SIZE, shuffle=True, collate_fn=collate_fn)
val_dataloader = DataLoader(val_dataset, batch_size=BATCH_SIZE, shuffle=False, collate_fn=collate_fn)

optimizer = torch.optim.AdamW(model.parameters(), lr=LR, weight_decay=0.01)
total_steps = len(train_dataloader) * EPOCHS
scheduler = get_linear_schedule_with_warmup(
    optimizer,
    num_warmup_steps=int(0.1 * total_steps),
    num_training_steps=total_steps
)

def mask_tokens_for_mlm(input_ids, tokenizer, mask_prob=0.15):
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
    labels[~masked_indices] = -100
    indices_replaced = torch.bernoulli(torch.full(labels.shape, 0.8, device=device)).bool() & masked_indices
    input_ids[indices_replaced] = tokenizer.mask_token_id
    indices_random = torch.bernoulli(torch.full(labels.shape, 0.5, device=device)).bool() & masked_indices & ~indices_replaced
    random_words = torch.randint(len(tokenizer), labels.shape, dtype=torch.long, device=device)
    input_ids[indices_random] = random_words[indices_random]
    return input_ids, labels

def validate(model, dataloader):
    model.eval()
    total_loss = 0.0
    num_batches = 0
    with torch.no_grad():
        for batch in dataloader:
            input_ids = batch["input_ids"].to(device)
            attention_mask = batch["attention_mask"].to(device)

            masked_input_ids, labels = mask_tokens_for_mlm(input_ids, tokenizer)
            masked_input_ids = masked_input_ids.to(device)
            labels = labels.to(device)

            outputs = model(
                input_ids=masked_input_ids,
                attention_mask=attention_mask,
                labels=labels
            )

            if not torch.isnan(outputs.loss):
                total_loss += outputs.loss.item()
                num_batches += 1

    model.train()
    return total_loss / num_batches if num_batches > 0 else float('inf')

best_val_loss = float('inf')
patience_counter = 0
train_losses = []
val_losses = []

model.train()
for epoch in range(EPOCHS):
    loop = tqdm(train_dataloader, desc=f"Epoch {epoch+1}/{EPOCHS}")
    total_loss = 0.0
    num_batches = 0

    for batch in loop:
        input_ids = batch["input_ids"].to(device)
        attention_mask = batch["attention_mask"].to(device)

        masked_input_ids, labels = mask_tokens_for_mlm(input_ids, tokenizer)
        masked_input_ids = masked_input_ids.to(device)
        labels = labels.to(device)

        outputs = model(
            input_ids=masked_input_ids,
            attention_mask=attention_mask,
            labels=labels
        )
        
        loss = outputs.loss

        if torch.isnan(loss):
            print("Warning: NaN loss detected, skipping batch")
            continue

        optimizer.zero_grad()
        loss.backward()
        torch.nn.utils.clip_grad_norm_(model.parameters(), max_norm=1.0)
        optimizer.step()
        scheduler.step()

        total_loss += loss.item()
        num_batches += 1
        loop.set_postfix(loss=loss.item(), lr=scheduler.get_last_lr()[0])

    avg_train_loss = total_loss / num_batches if num_batches > 0 else 0
    train_losses.append(avg_train_loss)
    avg_val_loss = validate(model, val_dataloader)
    val_losses.append(avg_val_loss)

    print(f"Epoch {epoch+1} | Train Loss: {avg_train_loss:.4f} | Val Loss: {avg_val_loss:.4f}")
    if avg_val_loss < best_val_loss:
        best_val_loss = avg_val_loss
        patience_counter = 0
        best_model_path = f"{SAVE_PATH}_best"
        os.makedirs(best_model_path, exist_ok=True)
        model.save_pretrained(best_model_path)
        tokenizer.save_pretrained(best_model_path)
        print(f"✓ New best model saved! Val Loss: {best_val_loss:.4f}")
    else:
        patience_counter += 1
        print(f"No improvement for {patience_counter} epoch(s)")

        if patience_counter >= PATIENCE:
            print(f"Early stopping triggered after {epoch+1} epochs")
            break
    if (epoch + 1) % 2 == 0:
        checkpoint_path = f"{SAVE_PATH}_epoch{epoch+1}"
        os.makedirs(checkpoint_path, exist_ok=True)
        model.save_pretrained(checkpoint_path)
        tokenizer.save_pretrained(checkpoint_path)
        print(f"Checkpoint saved to {checkpoint_path}")

os.makedirs(SAVE_PATH, exist_ok=True)
model.save_pretrained(SAVE_PATH)
tokenizer.save_pretrained(SAVE_PATH)
print(f"Final model saved to {SAVE_PATH}")
