from pathlib import Path
import types
_pkg = Path(__file__).parent
_code = (_pkg / "helpers_a.py").read_text() + (_pkg / "helpers_b.py").read_text()
_mod = types.ModuleType("pipeline.helpers_impl")
exec(compile(_code, "pipeline/helpers_impl", "exec"), _mod.__dict__)
globals().update({k: v for k, v in _mod.__dict__.items() if not k.startswith("_")})
