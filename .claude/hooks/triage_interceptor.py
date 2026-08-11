#!/usr/bin/env python3
import sys
import json
import re

COMPLEXITY_KEYWORDS = [
    r"\brefactor\b", r"\barchitect\b", r"\bmigrate\b", r"\brewrite\b", 
    r"\bmulti-file\b", r"\boverhaul\b", r"\bdesign pattern\b"
]
WORD_COUNT_THRESHOLD = 40

def is_complex_prompt(prompt_text):
    for pattern in COMPLEXITY_KEYWORDS:
        if re.search(pattern, prompt_text, re.IGNORECASE):
            return True
    
    words = prompt_text.split()
    if len(words) > WORD_COUNT_THRESHOLD:
        return True
        
    return False

def main():
    try:
        data = json.load(sys.stdin)
        user_prompt = data.get("prompt", "")
    except Exception:
        sys.exit(0)

    if is_complex_prompt(user_prompt):
        triage_prefix = (
            "[SYSTEM DIRECTIVE: AUTOMATED TRIAGE ENFORCED]\n"
            "This request has been flagged as high-complexity.\n"
            "Delegate the initial assessment pass to the `@triage-evaluator` subagent before writing or editing code.\n\n"
            "USER PROMPT:\n"
        )
        
        output = {
            "hookSpecificOutput": {
                "hookEventName": "UserPromptSubmit",
                "updatedInput": {
                    "prompt": triage_prefix + user_prompt
                }
            }
        }
        print(json.dumps(output))
    
    sys.exit(0)

if __name__ == "__main__":
    main()