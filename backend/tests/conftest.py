import os

# Testele nu depind de Ollama. Se setează înainte ca app.config să fie importat.
os.environ.setdefault("LLM_ENABLED", "0")
