"""Validation of what the LLM returns. We never trust model output: shapes, types, sizes and
file names are checked here before anything downstream uses them."""
from __future__ import annotations

from .client import LLMFormatError as LLMError

MAX_EDITS = 3
MAX_TEST_CHARS = 20000
MAX_EDIT_CHARS = 8000


def _s(v, name: str, required: bool = True, limit: int = 4000) -> str:
    if v is None or v == "":
        if required:
            raise LLMError(f"Model output is missing '{name}'.")
        return ""
    if not isinstance(v, str):
        raise LLMError(f"Model output field '{name}' must be a string.")
    return v[:limit] if name not in {"search", "replace", "test_code"} else v


def parse_diagnosis(obj: dict, known_files: set[str]) -> dict:
    summary = _s(obj.get("summary"), "summary")
    root = _s(obj.get("root_cause"), "root_cause")
    conf = str(obj.get("confidence", "low")).lower()
    if conf not in {"low", "medium", "high"}:
        conf = "low"
    raw = obj.get("suspects")
    if not isinstance(raw, list) or not raw:
        raise LLMError("Model output has no 'suspects'.")
    suspects = []
    for s in raw[:3]:
        if not isinstance(s, dict):
            continue
        path = str(s.get("file", "")).strip()
        while path.startswith("./"):
            path = path[2:]
        suspects.append({
            "file": path,
            "symbol": str(s.get("symbol", ""))[:200],
            "reason": str(s.get("reason", ""))[:1000],
            "chunk_ids": [str(c) for c in s.get("chunk_ids", []) if isinstance(c, str)][:6],
            # Grounding check: did the model name a file that really exists in this repository?
            "verified": path in known_files,
        })
    if not suspects:
        raise LLMError("Model output has no usable 'suspects'.")
    return {"summary": summary, "root_cause": root, "confidence": conf, "suspects": suspects}


def parse_fix(obj: dict) -> dict:
    explanation = _s(obj.get("explanation"), "explanation")
    raw_edits = obj.get("edits")
    if not isinstance(raw_edits, list) or not raw_edits:
        raise LLMError("The model proposed no edits.")
    if len(raw_edits) > MAX_EDITS:
        raise LLMError(f"The model proposed {len(raw_edits)} edits; at most {MAX_EDITS} are allowed.")
    edits = []
    for e in raw_edits:
        if not isinstance(e, dict):
            raise LLMError("An edit has the wrong shape.")
        file = _s(e.get("file"), "file", limit=500).strip()
        search = _s(e.get("search"), "search")
        replace = e.get("replace")
        if not isinstance(replace, str):
            raise LLMError("An edit is missing 'replace'.")
        if len(search) > MAX_EDIT_CHARS or len(replace) > MAX_EDIT_CHARS:
            raise LLMError("An edit is too large; propose a smaller, targeted change.")
        edits.append({"file": file, "search": search, "replace": replace})
    test_code = _s(obj.get("test_code"), "test_code")
    if len(test_code) > MAX_TEST_CHARS:
        raise LLMError("The generated test is too large.")
    if "def test_" not in test_code and "class Test" not in test_code:
        raise LLMError("The generated test file contains no tests.")
    return {
        "explanation": explanation,
        "edits": edits,
        "test_code": test_code,
        "test_rationale": _s(obj.get("test_rationale"), "test_rationale", required=False),
    }
