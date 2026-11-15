"""OpenRouter chat client: model fallback chain, 429 skip, defensive parsing."""
import logging
import os
import re
import time

import requests

from config import cfg, model_chain

log = logging.getLogger("agent.llm")

API_URL = "https://openrouter.ai/api/v1/chat/completions"


def _extract_text(data):
    """Pull final text out of an OpenRouter response, whatever shape it has.

    Handles: choices[0].message.content (may be None), message.reasoning
    (reasoning models), and inline <think>...</think> blocks leaking into
    content.
    """
    try:
        msg = data["choices"][0]["message"]
    except (KeyError, IndexError, TypeError):
        return ""
    text = msg.get("content") or msg.get("reasoning") or ""
    # Strip <think>...</think> blocks (nemotron leaks thinking into content)
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)
    return text.strip()


def chat(prompt, system=None, max_retries_per_model=3, timeout=60,
         temperature=0.2, max_tokens=400):
    """One chat completion, trying each model in OPENROUTER_MODELS in order.

    Returns the final text, or None if every model failed.
    """
    api_key = cfg("OPENROUTER_API_KEY")
    if not api_key:
        log.error("OPENROUTER_API_KEY missing")
        return None

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    for model in model_chain():
        attempt_tokens = max_tokens
        for attempt in range(max_retries_per_model):
            body = {
                "model": model,
                "messages": messages,
                "max_tokens": attempt_tokens,
                "temperature": temperature,
            }
            try:
                resp = requests.post(API_URL, headers=headers, json=body, timeout=timeout)
            except requests.RequestException as exc:
                log.warning("model=%s network error: %s", model, exc)
                break  # next model
            if resp.status_code == 429:
                log.warning("model=%s rate-limited (429), attempt %d", model, attempt + 1)
                time.sleep(3 * (attempt + 1))
                continue
            if resp.status_code >= 400:
                log.warning("model=%s HTTP %d: %s", model, resp.status_code, resp.text[:200])
                break  # next model
            try:
                data = resp.json()
            except ValueError:
                log.warning("model=%s non-JSON response", model)
                break
            try:
                msg = data["choices"][0]["message"]
                finish = data["choices"][0].get("finish_reason")
            except (KeyError, IndexError, TypeError):
                log.warning("model=%s unexpected response shape", model)
                break
            content = _extract_text({"choices": [{"message": msg}]}) if msg.get("content") else ""
            reasoning = _extract_text({"choices": [{"message": {"content": msg.get("reasoning")}}]}) if msg.get("reasoning") else ""
            if content:
                return content
            if reasoning and finish == "length":
                # Reasoning model ran out of tokens mid-think — retry with a
                # bigger budget instead of returning raw thinking as the answer
                log.warning("model=%s reasoning-only (length), retrying with 2x tokens", model)
                attempt_tokens *= 2
                continue
            if reasoning:
                # Some models emit the final answer in `reasoning` with finish=stop
                return reasoning
            log.warning("model=%s empty content, trying next", model)
            break
    log.error("all models failed")
    return None
