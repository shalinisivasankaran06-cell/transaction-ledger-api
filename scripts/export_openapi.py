import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from app.main import app  # noqa: E402

out_path = os.path.join(ROOT, "docs", "openapi.json")
os.makedirs(os.path.dirname(out_path), exist_ok=True)
with open(out_path, "w") as f:
    json.dump(app.openapi(), f, indent=2)
print(f"wrote {out_path}")
