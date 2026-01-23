import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

print("[conftest] inserted ROOT into sys.path:", ROOT)
print("[conftest] sys.path[0]:", sys.path[0])