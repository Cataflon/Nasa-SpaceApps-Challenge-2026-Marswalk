import os

# Testele nu depind de Ollama. Se setează înainte ca app.config să fie importat.
os.environ.setdefault("LLM_ENABLED", "0")
# Aplicația pornește implicit pe Jezero; testele rămân pe situl sintetic (ca înainte).
os.environ.setdefault("MARSWALK_SITE", "synthetic")
