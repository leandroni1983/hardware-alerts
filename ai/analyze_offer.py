"""AI classifier wrapper calling local Ollama to classify an offer.

The AI is only used to label a candidate as REAL / NORMAL / HUMO based
on the provided context. Calculations are performed in Python, not by the model.
"""

import json
from typing import Dict

import requests

OLLAMA_URL = "http://127.0.0.1:11434/api/generate"
MODEL = "qwen2.5:3b-instruct"


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
    try:
        resp = requests.post(OLLAMA_URL, json=payload, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            # Ollama returns text under 'text' or 'response' depending on version
            text = data.get("text") or data.get("response") or json.dumps(data)
            # Extract first token (REAL/NORMAL/HUMO)
            first = text.strip().split()[0].upper()
            label = first if first in ("REAL", "NORMAL", "HUMO") else "NORMAL"
            return {"label": label, "raw": text}
        return {"label": "NORMAL", "raw": f"ollama_error:{resp.status_code}"}
    except Exception as e:
        return {"label": "NORMAL", "raw": f"exception:{e}"}


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
