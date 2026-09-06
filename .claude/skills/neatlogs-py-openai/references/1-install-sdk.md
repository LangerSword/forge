# Step 1: Install the Neatlogs SDK

## Action

1. Call the `detect_package_manager` tool to get the install command.
2. Install the LATEST `neatlogs`. ALWAYS pull the newest published version (use the upgrade flag so an already-installed older version is upgraded):
   - pip: `pip install --upgrade neatlogs`
   - uv: `uv add --upgrade neatlogs`  (or `uv pip install --upgrade neatlogs`)
   - poetry: `poetry add neatlogs@latest`
3. Extras are only needed for providers that use the global auto-instrumentor (Path B in SKILL.md — Groq, Cohere, Bedrock, Mistral, Together, LiteLLM). For the wrap() path (OpenAI/Anthropic/Google GenAI) no extras bracket is required. If the project uses a Path-B provider, add its extra:
   - Groq: `neatlogs[groq]`, Cohere: `neatlogs[cohere]`, Bedrock: `neatlogs[bedrock]`, Mistral: `neatlogs[mistralai]`, Together: `neatlogs[together]`, LiteLLM: `neatlogs[litellm]`
   - Multiple: combine with commas, e.g. `neatlogs[groq,cohere]`
4. Start installation as a background task. Do not wait for it.

## Verification

The package will be available by the time we need it. Proceed immediately.
