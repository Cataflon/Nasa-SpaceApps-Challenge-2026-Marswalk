import sys
from pathlib import Path

# Scripturile din pipeline/ se importă direct (nu e pachet).
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
