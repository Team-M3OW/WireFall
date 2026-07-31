import sys
import logging

logging.basicConfig(level=logging.INFO)

from inference.rule_generator import app

def test():
    payload = "1' OR '1'='1' -- -"
    print(f"--- Running inference for payload: {payload} ---")
    
    final_state = app.invoke({
        "payload": payload, 
        "prompt": "", 
        "retries": 0, 
        "regex_pattern": None,
        "test_malicious": None,
        "test_benign": None,
        "error": None
    })
    
    print("\n--- Inference Complete ---")
    print("\n[+] Generated Similar Malicious Payloads:")
    for m in final_state.get("test_malicious", []):
        print(f"  - {m}")
        
    print("\n[+] Generated Benign Payloads (Safe Traffic):")
    for b in final_state.get("test_benign", []):
        print(f"  - {b}")
        
    print(f"\n[+] Final Regex Pattern Generated: {final_state.get('regex_pattern')}")
    print(f"[+] Validation Errors (if any remaining): {final_state.get('error')}")
    print(f"[+] Retry loops taken: {final_state.get('retries')}")

if __name__ == "__main__":
    test()
