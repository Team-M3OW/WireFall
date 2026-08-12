import logging
import re
from transformers import pipeline

_llm_pipe = None
_llm_loaded = False
_model_name = "Qwen/Qwen2.5-0.5B-Instruct"


def _load_llm():
    global _llm_pipe, _llm_loaded, _model_name
    try:
        logging.info(f"Loading primary LLM rule generator: {_model_name}...")
        _llm_pipe = pipeline("text-generation", model=_model_name, device=-1)
        _llm_loaded = True
        logging.info("Qwen2.5 rule generator loaded successfully.")
    except Exception as e:
        logging.warning(f"Failed to load {_model_name}: {e}. Falling back to distilgpt2...")
        try:
            _model_name = "distilgpt2"
            _llm_pipe = pipeline("text-generation", model=_model_name, device=-1)
            _llm_loaded = True
            logging.info("DistilGPT2 fallback rule generator loaded.")
        except Exception as err:
            logging.error(f"Failed to load fallback LLM: {err}")
            _llm_loaded = False


def generate_rule_from_payload(payload: str) -> str | None:
    if not payload:
        return None
    if not _llm_loaded:
        _load_llm()

    if _llm_pipe is None:
        return f"(?i){re.escape(payload[:100])}"

    try:
        if "Qwen" in _model_name:
            prompt = (
                f"<|im_start|>system\n"
                f"You are a WAF security engine. Generate a precise Python regex block rule for the given attack payload. "
                f"Output ONLY the raw regex pattern string starting with (?i). Do not output markdown, quotes, or explanations.<|im_end|>\n"
                f"<|im_start|>user\nPayload: {payload[:200]}<|im_end|>\n"
                f"<|im_start|>assistant\n"
            )
            outputs = _llm_pipe(prompt, max_new_tokens=40, return_full_text=False)
            regex_part = outputs[0]["generated_text"].strip().split("\n")[0].strip("'`\"")
        else:
            prompt = (
                f"Generate a regex pattern for a WAF to detect this malicious payload. "
                f"Output ONLY the regex pattern:\n\nPayload: {payload[:200]}\n\nRegex pattern:"
            )
            outputs = _llm_pipe(prompt, max_new_tokens=40)
            regex_part = outputs[0]["generated_text"].replace(prompt, "").strip().split("\n")[0].strip("'`\"")

        re.compile(regex_part)
        return regex_part
    except Exception:
        return f"(?i){re.escape(payload[:100])}"
