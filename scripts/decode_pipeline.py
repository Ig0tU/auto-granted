#!/usr/bin/env python3
"""Materialize pipeline UI sources from embedded payloads. Run from repo root."""
from pathlib import Path
import base64
import importlib.util

root = Path(__file__).resolve().parent.parent

def load_const(mod_path: Path, name: str) -> str:
    spec = importlib.util.spec_from_file_location(mod_path.stem, mod_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return getattr(mod, name)

HA = load_const(root / "pipeline" / "_ha.py", "HA")
HB = load_const(root / "pipeline" / "_hb.py", "HB")
HU = load_const(root / "pipeline" / "_hu.py", "HU")

for rel, b64 in [
    ("pipeline/helpers_a.py", HA),
    ("pipeline/helpers_b.py", HB),
    ("pipeline/ui.py", HU),
]:
    data = base64.b64decode(b64)
    path = root / rel
    path.write_bytes(data)
    print(f"wrote {rel} ({len(data)} bytes)")
print("Done. Run: python app.py")
