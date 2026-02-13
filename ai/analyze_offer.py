"""AI classifier wrapper calling local Ollama to classify an offer.

The AI is only used to label a candidate as REAL / NORMAL / HUMO based
on the provided context. Calculations are performed in Python, not by the model.
"""

import json
import os
import re
import time
from typing import Dict

import requests

# Configurable via environment
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://192.168.0.234:11434/api/generate")
MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5:3b-instruct")
OLLAMA_TIMEOUT = float(os.getenv("OLLAMA_TIMEOUT", "15"))
OLLAMA_RETRIES = int(os.getenv("OLLAMA_RETRIES", "3"))
OLLAMA_BACKOFF = float(os.getenv("OLLAMA_BACKOFF", "1.5"))


def _build_prompt(context: Dict) -> str:
    # Context includes: title, price, avg30, avg7, shop, url, notes
    prompt = (
        "Eres un asistente que clasifica ofertas de hardware en Argentina. "
        "Recibirás datos estructurados: título, precio actual (ARS), promedio 30d, promedio 7d, tienda, URL. "
        "Responde con una sola palabra: REAL, NORMAL o HUMO, y luego una breve justificación de 1-2 líneas.\n\n"
    )
    prompt += "Context:\n"
    for k, v in context.items():
        prompt += f"- {k}: {v}\n"
    prompt += "\nClasificación:"
    return prompt


def analyze(context: Dict) -> Dict:
    prompt = _build_prompt(context)
    payload = {
        "model": MODEL,
        "prompt": prompt,
        "max_tokens": 256,
        "temperature": 0.0,
    }
    last_exc = None
    for attempt in range(1, OLLAMA_RETRIES + 1):
        try:
            resp = requests.post(OLLAMA_URL, json=payload, timeout=OLLAMA_TIMEOUT)
            if resp.status_code == 200:
                # Try to handle streaming newline-delimited JSON (Ollama may stream tokens)
                text = ""
                content_type = resp.headers.get("Content-Type", "")
                try:
                    # If streaming, iterate lines
                    if resp.encoding is None:
                        resp.encoding = "utf-8"
                    if "text/event-stream" in content_type or "application/json" in content_type or True:
                        # Use iter_lines to safely iterate without blocking
                        for raw in resp.iter_lines(decode_unicode=True):
                            if not raw:
                                continue
                            # raw may be a JSON object per line or plain text fragments
                            line = raw.strip()
                            try:
                                j = json.loads(line)
                                # common keys: 'text', 'response', or nested 'results'
                                if isinstance(j, dict):
                                    part = j.get("text") or j.get("response")
                                    if not part and "results" in j and isinstance(j["results"], list) and j["results"]:
                                        # try to extract textual parts from results
                                        for r in j["results"]:
                                            if isinstance(r, dict):
                                                # try common shapes
                                                cont = r.get("content") or r
                                                if isinstance(cont, dict):
                                                    t = cont.get("text") or cont.get("response")
                                                    if t:
                                                        part = (part or "") + str(t)
                                    if part:
                                        text += str(part)
                                    else:
                                        # append any string fields as fallback
                                        for v in j.values():
                                            if isinstance(v, str):
                                                text += v
                            except json.JSONDecodeError:
                                # not JSON, append raw line
                                text += line
                except Exception:
                    # Fallback: try to parse full JSON body
                    try:
                        data = resp.json()
                        text = data.get("text") or data.get("response") or resp.text or json.dumps(data)
                    except Exception:
                        text = resp.text
                # Prefer explicit label tokens anywhere in the returned text (take last occurrence)
                found = re.findall(r"\b(REAL|NORMAL|HUMO)\b", text, flags=re.IGNORECASE)
                if found:
                    label = found[-1].upper()
                else:
                    first = text.strip().split()[0].upper() if text else "NORMAL"
                    label = first if first in ("REAL", "NORMAL", "HUMO") else "NORMAL"
                return {"label": label, "raw": text}

            # non-200 status
            last_exc = Exception(f"status={resp.status_code}")
        except Exception as e:
            last_exc = e
            # backoff before retrying
            if attempt < OLLAMA_RETRIES:
                try:
                    time.sleep(OLLAMA_BACKOFF * attempt)
                except Exception:
                    pass
            continue

    # If we reach here, all attempts failed
    return {"label": "NORMAL", "raw": f"exception:{last_exc}"}


if __name__ == "__main__":
    ctx = {
        "title": "RTX 3060 12GB XYZ",
        "price": 900000,
        "avg30": 1100000,
        "avg7": 1080000,
        "shop": "compra_gamer",
        "url": "https://...",
    }
    print(analyze(ctx))
