import re
import os
import json
from typing import TypedDict, Annotated, Sequence
import operator

from langchain_huggingface import HuggingFacePipeline
from transformers import pipeline
from langgraph.graph import StateGraph, END

class AgentState(TypedDict):
    payload: str
    prompt: str
    regex_pattern: str | None
    test_malicious: list[str]
    test_benign: list[str]
    error: str | None
    retries: int

llm = None

def _get_llm():
    global llm
    if llm is None:
        # Use Qwen2.5 7B Instruct as it is a highly capable local model.
        # It's much better at generating JSON and following instructions.
        pipe = pipeline(
            "text-generation", 
            model="Qwen/Qwen2.5-7B-Instruct", 
            max_new_tokens=256,
            device_map="auto" # Automatically uses GPU if available
        )
        llm = HuggingFacePipeline(pipeline=pipe)
    return llm

def generate_test_cases(state: AgentState):
    """
    Agent generates similar payloads of the same family (malicious) 
    and similar-looking benign payloads to validate against.
    """
    payload = state["payload"]
    if state.get("test_malicious") is not None:
        return {} # already generated
        
    prompt = f"""<|im_start|>user
Given the following malicious payload:
{payload[:200]}

Generate 3 similar malicious payloads (same family of attack) and 3 benign payloads that look similar but are completely safe/normal traffic.
Return ONLY valid JSON in the following format:
{{
  "malicious": ["payload1", "payload2", "payload3"],
  "benign": ["payload1", "payload2", "payload3"]
}}
Do not include markdown blocks or any other text.<|im_end|>
<|im_start|>assistant
"""
    try:
        response = _get_llm().invoke(prompt)
        # Extract the assistant's reply
        output_text = response.split("<|im_start|>assistant")[-1].strip()
        
        content = output_text.strip('`')
        if content.startswith("json"):
            content = content[4:].strip()
        data = json.loads(content)
        return {
            "test_malicious": data.get("malicious", []),
            "test_benign": data.get("benign", [])
        }
    except Exception:
        # Fallback to empty lists if parsing fails
        return {
            "test_malicious": [],
            "test_benign": []
        }

def generate_node(state: AgentState):
    """
    Agent generates the regex based on the original payload and handles validation feedback.
    """
    payload = state["payload"]
    current_prompt = state.get("prompt", "")
    
    if not current_prompt:
        # Initial prompt
        prompt = (
            f"<|im_start|>user\n"
            f"Generate a regex pattern for a WAF to detect this malicious payload and its family of attacks.\n"
            f"Output ONLY the regex pattern, nothing else. Do not wrap in markdown or quotes.\n\n"
            f"Payload: {payload[:200]}<|im_end|>\n"
            f"<|im_start|>assistant\n"
        )
    else:
        # We have an error, construct a correction prompt
        error = state.get("error")
        prompt = current_prompt + f"\n<|im_start|>user\nThe generated regex failed validation with error: {error}\n\nPlease provide a corrected regex pattern. Output ONLY the regex pattern, nothing else.<|im_end|>\n<|im_start|>assistant\n"
        
    response = _get_llm().invoke(prompt)
    output_text = response.split("<|im_start|>assistant")[-1].strip()
    
    # Extract the regex
    regex_part = output_text.strip().strip("'\"").strip("`")
    if regex_part.startswith("regex"):
        regex_part = regex_part[5:].strip()
    
    return {
        "prompt": prompt + output_text,
        "regex_pattern": regex_part,
        "retries": state.get("retries", 0) + 1
    }

def validate_node(state: AgentState):
    """
    Sandboxed validation against the generated similar malicious and benign payloads.
    """
    regex_pattern = state.get("regex_pattern")
    malicious = [state["payload"]] + state.get("test_malicious", [])
    benign = state.get("test_benign", [])
    
    try:
        if not regex_pattern:
            return {"error": "Empty regex pattern"}
            
        compiled = re.compile(regex_pattern)
        
        # Test malicious (should match)
        for p in malicious:
            if not compiled.search(p):
                return {"error": f"Regex failed to match malicious payload: {p}"}
                
        # Test benign (should NOT match)
        for p in benign:
            if compiled.search(p):
                return {"error": f"Regex incorrectly matched benign payload: {p}"}
                
        return {"error": None}
    except Exception as e:
        return {"error": f"Regex compilation error: {str(e)}"}

def route_validation(state: AgentState):
    if state.get("error") is None:
        return "end"
    if state.get("retries", 0) >= 3:
        return "end"
    return "generate"

# Build graph
workflow = StateGraph(AgentState)
workflow.add_node("generate_test_cases", generate_test_cases)
workflow.add_node("generate", generate_node)
workflow.add_node("validate", validate_node)

workflow.set_entry_point("generate_test_cases")
workflow.add_edge("generate_test_cases", "generate")
workflow.add_edge("generate", "validate")
workflow.add_conditional_edges("validate", route_validation, {"end": END, "generate": "generate"})

app = workflow.compile()

def generate_rule_from_payload(payload: str) -> str | None:
    if not payload:
        return None
    
    try:
        final_state = app.invoke({
            "payload": payload, 
            "prompt": "", 
            "retries": 0, 
            "regex_pattern": None,
            "test_malicious": None,
            "test_benign": None,
            "error": None
        })
        
        if final_state.get("error") is None and final_state.get("regex_pattern"):
            return final_state["regex_pattern"]
        else:
            # Fallback if we exceeded retries without success
            return f"(?i){re.escape(payload[:100])}"
    except Exception as e:
        return f"(?i){re.escape(payload[:100])}"
