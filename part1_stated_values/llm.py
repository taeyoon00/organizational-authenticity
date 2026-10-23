"""
Thin wrapper around the LLM used by the Part 1 coding steps.

Backend (DECISIONS.md, D-011): by default a local open-weight model served
by Ollama (no cost, no data leaves the machine, model version pinned), so
the whole pipeline can be rerun by anyone with a consumer GPU. The Claude
API is kept as an alternative backend: set LLM_BACKEND=anthropic.

Common to both backends:
* Structured output: every call passes a JSON schema, so the answer is
  guaranteed to parse into the expected fields.
* Deterministic decoding where the backend allows it (temperature 0, seed).
* Caching on disk: each answer is saved under
  data/intermediate/llm_cache/<task>/<model>/<key>.json together with a
  fingerprint of its exact input, and reused only for that same input, so
  runs are resumable, re-running is free, and a changed page is re-coded.
* Usage log: token counts (and cost, for the paid backend) per call in
  data/intermediate/llm_usage.csv.
"""
import csv
import hashlib
import json
import os
import re
import time

import requests

from common import PROCESSED

BACKEND = os.environ.get("LLM_BACKEND", "ollama")

# local backend
OLLAMA_URL = "http://localhost:11434/api/chat"
OLLAMA_MODEL = "qwen2.5:7b-instruct"     # Apache-2.0, ~4.7 GB, fits a 6 GB GPU
CONTEXT_TIERS = (8192, 16384, 32768)     # 32768 = native context of Qwen2.5-7B
MAX_CONTEXT = CONTEXT_TIERS[-1]
MAX_ANSWER_TOKENS = 1500

# paid backend (optional)
CLAUDE_MODEL = "claude-opus-5-5"
CLAUDE_PRICE_IN, CLAUDE_PRICE_OUT = 4.00, 20.00   # USD per million tokens

MODEL = OLLAMA_MODEL if BACKEND == "ollama" else CLAUDE_MODEL
CACHE = PROCESSED / "llm_cache"
USAGE_CSV = PROCESSED / "llm_usage.csv"


def _slug(s):
    return re.sub(r"[^A-Za-z0-9.-]+", "_", s)


def _cache_file(task, key):
    return CACHE / task / _slug(MODEL) / f"{key}.json"


def input_sha(system, user, schema):
    """Fingerprint of everything sent to the model. Stored with each cached
    answer, so an answer is reused only for exactly the same input: if a
    company-year's page text changes upstream, it is coded again."""
    blob = json.dumps([system, user, schema], sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]


def cached(task, key, sha=None):
    """The cached answer, or None. With `sha`, an answer stored for a
    different input does not count."""
    f = _cache_file(task, key)
    if not f.exists():
        return None
    stored = json.loads(f.read_text(encoding="utf-8"))
    if sha is not None and stored.get("_input_sha") != sha:
        return None
    return {k: v for k, v in stored.items() if k != "_input_sha"}


def approx_tokens(text):
    return len(text) / 3.5          # rough; English web text


def estimate_cost(chars_in, n_calls, out_tokens_per_call=1500):
    """Pre-run cost estimate in USD (zero for the local backend)."""
    if BACKEND == "ollama":
        return 0.0
    return (chars_in / 4) / 1e6 * CLAUDE_PRICE_IN + n_calls * out_tokens_per_call / 1e6 * CLAUDE_PRICE_OUT


def context_tier(system, user):
    """Smallest fixed context size that fits the request. Ollama reloads the
    model whenever num_ctx changes, so sizes come from a few fixed tiers and
    callers process requests grouped by tier."""
    need = approx_tokens(system + user) + MAX_ANSWER_TOKENS
    for tier in CONTEXT_TIERS:
        if need <= tier:
            return tier
    raise ValueError(f"input too long for {MODEL} (~{int(need)} tokens > {CONTEXT_TIERS[-1]})")


def _call_ollama(system, user, schema):
    num_ctx = context_tier(system, user)
    payload = {
        "model": OLLAMA_MODEL,
        "messages": [{"role": "system", "content": system},
                     {"role": "user", "content": user}],
        "format": schema,
        "stream": False,
        # num_predict caps the answer; repeat_penalty discourages the loops a
        # 7B model can fall into when filling long JSON arrays
        "options": {"temperature": 0, "seed": 0, "num_ctx": num_ctx,
                    "num_predict": MAX_ANSWER_TOKENS, "repeat_penalty": 1.1},
    }
    for attempt in range(2):          # a crashed model runner restarts on the next request
        r = requests.post(OLLAMA_URL, timeout=900, json=payload)
        if r.status_code == 200:
            break
        time.sleep(10)
    else:
        raise RuntimeError(f"Ollama HTTP {r.status_code} (num_ctx={num_ctx}): {r.text[:300]}")
    body = r.json()
    return body["message"]["content"], body.get("prompt_eval_count", 0), body.get("eval_count", 0), 0.0


def _call_claude(system, user, schema):
    import anthropic          # imported lazily: the local backend needs no key
    response = anthropic.Anthropic().beta.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=16000,
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
        output_config={"effort": "medium",
                       "format": {"type": "json_schema", "schema": schema}},
        system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
        messages=[{"role": "user", "content": user}],
    )
    if response.stop_reason in ("refusal", "max_tokens"):
        raise RuntimeError(f"stopped: {response.stop_reason}")
    u = response.usage
    cost = ((u.input_tokens + (u.cache_creation_input_tokens or 0) * 1.25
             + (u.cache_read_input_tokens or 0) * 0.1) / 1e6 * CLAUDE_PRICE_IN
            + u.output_tokens / 1e6 * CLAUDE_PRICE_OUT)
    text = next(b.text for b in response.content if b.type == "text")
    return text, u.input_tokens, u.output_tokens, cost


def call_json(task, key, system, user, schema):
    """Return the parsed JSON answer for (task, key), calling the model only once."""
    sha = input_sha(system, user, schema)
    hit = cached(task, key, sha)
    if hit is not None:
        return hit
    started = time.time()
    call = _call_ollama if BACKEND == "ollama" else _call_claude
    text, tok_in, tok_out, cost = call(system, user, schema)
    answer = json.loads(text)

    out = _cache_file(task, key)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({**answer, "_input_sha": sha}, ensure_ascii=False, indent=1),
                   encoding="utf-8")

    new_file = not USAGE_CSV.exists()
    with USAGE_CSV.open("a", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        if new_file:
            w.writerow(["time", "task", "key", "backend", "model", "input_tokens",
                        "output_tokens", "seconds", "cost_usd"])
        w.writerow([time.strftime("%Y-%m-%d %H:%M:%S"), task, key, BACKEND, MODEL,
                    tok_in, tok_out, round(time.time() - started, 1), round(cost, 5)])
    return answer
