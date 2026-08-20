"""
Ollama Cloud client for AutoGrantED
===================================
Docs: https://docs.ollama.com/cloud
Auth: https://docs.ollama.com/api/authentication
Keys: https://ollama.com/settings/keys

Two modes (do not mix model name suffixes):
  1) Direct cloud API  host=https://ollama.com
     - Authorization: Bearer <OLLAMA_API_KEY>
     - Model names WITHOUT the -cloud suffix  e.g. gpt-oss:120b

  2) Local Ollama proxying cloud  host=http://localhost:11434
     - ollama signin (no Bearer key on the request)
     - Model names WITH the -cloud suffix  e.g. gpt-oss:120b-cloud

This module implements mode (1) for the Gradio UI (user pastes API key).
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional, Tuple

OLLAMA_CLOUD_HOST = "https://ollama.com"
KEYS_URL = "https://ollama.com/settings/keys"
CLOUD_DOCS_URL = "https://docs.ollama.com/cloud"
CLOUD_LIBRARY_URL = "https://ollama.com/search?c=cloud"
TAGS_URL = f"{OLLAMA_CLOUD_HOST}/api/tags"
CHAT_URL = f"{OLLAMA_CLOUD_HOST}/api/chat"

# Curated defaults for grant / long-form structured writing (direct API names — no -cloud).
# Sourced from live https://ollama.com/api/tags + cloud library, filtered for task fit.
GRANT_TASK_PREFERRED = [
    "gpt-oss:120b",
    "gpt-oss:20b",
    "nemotron-3-super",
    "nemotron-3-nano:30b",
    "glm-5.2",
    "glm-5.1",
    "minimax-m3",
    "minimax-m2.7",
    "deepseek-v4-flash:0731",
    "deepseek-v4-pro:0813",
    "gemma4:31b",
    "qwen3.5:397b",
    "kimi-k2.6",
    "mistral-large-3:675b",
]


def _request(
    url: str,
    *,
    method: str = "GET",
    api_key: Optional[str] = None,
    body: Optional[Dict[str, Any]] = None,
    timeout: int = 120,
) -> Dict[str, Any]:
    data = None
    headers = {"Content-Type": "application/json", "User-Agent": "AutoGrantED/2.3"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key.strip()}"
    if body is not None:
        data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Ollama Cloud HTTP {e.code}: {err_body[:500]}") from e
    except urllib.error.URLError as e:
        raise RuntimeError(f"Ollama Cloud network error: {e}") from e


def list_cloud_models(api_key: Optional[str] = None) -> List[str]:
    payload = _request(TAGS_URL, api_key=api_key, timeout=30)
    models = payload.get("models") or []
    names: List[str] = []
    for m in models:
        name = m.get("name") or m.get("model")
        if name:
            if name.endswith("-cloud"):
                name = name[: -len("-cloud")]
            names.append(name)
    return sorted(set(names))


def models_for_grant_task(api_key: Optional[str] = None) -> Tuple[List[str], str]:
    try:
        available = list_cloud_models(api_key=api_key)
    except Exception as e:
        return list(GRANT_TASK_PREFERRED), f"Live tags unavailable ({e}); showing curated defaults."

    available_set = set(available)
    ordered: List[str] = []
    for pref in GRANT_TASK_PREFERRED:
        if pref in available_set:
            ordered.append(pref)
    for name in available:
        if name not in ordered:
            ordered.append(name)

    note = f"Loaded {len(available)} cloud models from ollama.com/api/tags (no -cloud suffix)."
    return ordered, note


def chat(
    api_key: str,
    model: str,
    messages: List[Dict[str, str]],
    *,
    stream: bool = False,
    temperature: float = 0.4,
) -> str:
    if not api_key or not api_key.strip():
        raise ValueError(
            "Ollama Cloud API key required. Create one at https://ollama.com/settings/keys"
        )

    model = model.strip()
    if model.endswith("-cloud"):
        model = model[: -len("-cloud")]

    body = {
        "model": model,
        "messages": messages,
        "stream": stream,
        "options": {"temperature": temperature},
    }
    result = _request(CHAT_URL, method="POST", api_key=api_key, body=body, timeout=300)
    msg = result.get("message") or {}
    content = msg.get("content") or result.get("response") or ""
    if not content:
        raise RuntimeError(f"Empty response from Ollama Cloud: {json.dumps(result)[:400]}")
    return content.strip()


def generate_proposal_sections(
    api_key: str,
    model: str,
    *,
    agency: str,
    opp_number: str,
    opp_title: str,
    deadline: str,
    project_capability: str = "SignalMesh zero-token multi-agent orchestration",
) -> Dict[str, str]:
    system = (
        "You are an expert federal grant proposal writer for NSF, DARPA, and DOE. "
        "Write concrete, specific, non-hype technical prose. Use clear section structure. "
        "Do not invent fake prior awards or fake citations. "
        "Respond ONLY with valid JSON keys: "
        "overview, intellectual_merit, broader_impacts, narrative, dmp, project_title."
    )
    user = (
        f"Write proposal sections for this opportunity:\n"
        f"Agency: {agency}\n"
        f"Solicitation: {opp_number}\n"
        f"Title: {opp_title}\n"
        f"Deadline: {deadline}\n"
        f"Our capability focus: {project_capability}\n\n"
        f"Requirements:\n"
        f"- overview: 2-4 sentences (Project Summary overview)\n"
        f"- intellectual_merit: 1 short paragraph on technical novelty and rigor\n"
        f"- broader_impacts: 1 short paragraph on societal / community impact\n"
        f"- narrative: multi-paragraph Project Description with Technical Approach, "
        f"Work Packages (WP1-WP5), and Results from Prior Support placeholder\n"
        f"- dmp: short FAIR Data Management Plan paragraph\n"
        f"- project_title: a tight proposal title aligned to the solicitation\n"
    )
    raw = chat(
        api_key,
        model,
        [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        temperature=0.35,
    )
    text = raw.strip()
    if "```" in text:
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            text = text[start : end + 1]
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        data = {
            "project_title": opp_title,
            "overview": raw[:600],
            "intellectual_merit": "",
            "broader_impacts": "",
            "narrative": raw,
            "dmp": "All code and datasets will be published under FAIR principles.",
        }
    return {
        "project_title": str(data.get("project_title") or opp_title),
        "overview": str(data.get("overview") or ""),
        "intellectual_merit": str(data.get("intellectual_merit") or ""),
        "broader_impacts": str(data.get("broader_impacts") or ""),
        "narrative": str(data.get("narrative") or ""),
        "dmp": str(data.get("dmp") or ""),
    }


def validate_key(api_key: str) -> Tuple[bool, str]:
    if not api_key or not api_key.strip():
        return False, "Paste an API key from https://ollama.com/settings/keys"
    try:
        models = list_cloud_models(api_key=api_key.strip())
        return True, f"Key OK — {len(models)} models visible on ollama.com"
    except Exception as e:
        return False, str(e)
