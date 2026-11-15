import os

# Testele nu depind de Ollama. Se setează înainte ca app.config să fie importat.
os.environ.setdefault("LLM_ENABLED", "0")
# Aplicația pornește implicit pe Jezero; testele rămân pe situl sintetic (ca înainte).
os.environ.setdefault("MARSWALK_SITE", "synthetic")
# Testele (e2e, scena demo) se bazează pe evenimentele programate ale scenariului demo.
os.environ.setdefault("MARSWALK_DEMO_EVENTS", "1")
