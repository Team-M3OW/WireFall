import re

from transformers import pipeline

_llm_pipe = None
_llm_loaded = False


def _load_llm():
    global _llm_pipe, _llm_loaded
    try:
        _llm_pipe = pipeline("text-generation", model="distilgpt2", device=-1)
        _llm_loaded = True
    except Exception:
        _llm_loaded = False


def generate_rule_from_payload(payload: str) -> str | None:
    if not payload:
        return None
    if not _llm_loaded:
        _load_llm()

    if _llm_pipe is None:
        return f"(?i){re.escape(payload[:100])}"

    try:
        prompt = (
            f"Generate a regex pattern for a WAF to detect this malicious payload. "
            f"Output ONLY the regex pattern, nothing else:\n\n"
            f"Payload: {payload[:200]}\n\nRegex pattern:"
        )
        outputs = _llm_pipe(prompt, max_new_tokens=50, pad_token_id=50256)
        regex_part = outputs[0]["generated_text"].replace(prompt, "").strip().split("\n")[0].strip("'\"")
        re.compile(regex_part)
        return regex_part
    except Exception:
        return f"(?i){re.escape(payload[:100])}"
