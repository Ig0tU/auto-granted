#!/usr/bin/env python3
"""Decode base64 pipeline modules. Run from repo root: python scripts/decode_pipeline.py"""
from pathlib import Path
import base64
root = Path(__file__).resolve().parent.parent
pairs = [
    ("pipeline/helpers_a.py.b64", "pipeline/helpers_a.py"),
    ("pipeline/helpers_b.py.b64", "pipeline/helpers_b.py"),
    ("pipeline/ui.py.b64", "pipeline/ui.py"),
]
for src, dst in pairs:
    data = base64.b64decode((root / src).read_text().strip())
    out = root / dst
    out.write_bytes(data)
    print(f"wrote {dst} ({len(data)} bytes)")
print("Done. Then: python app.py")
