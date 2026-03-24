#!/usr/bin/env python3
"""Generate 4 cover art images for 准时的飞蛾 (Punctual Moth)."""

import requests
import base64
import json
import os
import time
from pathlib import Path

def load_env():
    env_file = Path(__file__).resolve().parent.parent / "suno-api" / ".env"
    if not env_file.exists():
        env_file = Path(__file__).resolve().parent / ".env"
    if not env_file.exists():
        return
    with open(env_file) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                key, value = line.split("=", 1)
                os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))

load_env()

OUTPUT_DIR = "/Users/xuejin/Documents/claude/输出文件/2026-03-10/cover/准时的飞蛾-S1ent"

# --- Doubao (ARK) Config ---
ARK_API_KEY = os.environ["ARK_API_KEY"]
ARK_ENDPOINT = "https://ark.cn-beijing.volces.com/api/v3/images/generations"
ARK_MODEL = "doubao-seedream-3-0-t2i-250415"

# --- Gemini Config ---
GEMINI_API_KEY = os.environ["GEMINI_API_KEY"]
GEMINI_ENDPOINT = f"https://generativelanguage.googleapis.com/v1beta/models/imagen-4.0-generate-001:predict?key={GEMINI_API_KEY}"
_proxy = os.environ.get("HTTPS_PROXY") or os.environ.get("HTTP_PROXY")
GEMINI_PROXY = {"http": _proxy, "https": _proxy} if _proxy else None

# --- Prompts ---
DOUBAO_PROMPTS = {
    "cover_温暖重逢_doubao.png": "温暖的咖啡厅角落，一杯珍珠奶茶放在木桌上，旁边有一件叠好的灰色帽衫卫衣，窗外是三月初春的街道，暖黄色调，画面干净唯美，无任何文字水印logo，高清摄影风，小红书调性",
    "cover_奶茶与飞蛾_doubao.png": "一只小飞蛾停在发光的奶茶杯盖上，暖黄色光晕，背景模糊的城市夜景，温馨可爱风格，微距摄影感，画面干净唯美，无任何文字水印logo，高清摄影风，小红书调性",
}

GEMINI_PROMPTS = {
    "cover_温暖重逢_nb.png": "A cozy cafe corner with a bubble milk tea on a wooden table, a neatly folded gray hoodie beside it, early spring street visible through the window, warm golden tones, soft dreamy lighting, aesthetic photography style, NO text NO people NO watermark NO letters NO logos",
    "cover_奶茶与飞蛾_nb.png": "A tiny cute moth resting on a glowing milk tea cup lid, warm golden light halo, blurred city lights in background, whimsical and cozy style, macro photography feel, aesthetic and dreamy, NO text NO people NO watermark NO letters NO logos",
}


def generate_doubao(filename, prompt):
    """Generate image using Doubao/ARK API."""
    print(f"\n[Doubao] Generating: {filename}")
    print(f"  Prompt: {prompt[:60]}...")

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {ARK_API_KEY}",
    }
    payload = {
        "model": ARK_MODEL,
        "prompt": prompt,
        "width": 1024,
        "height": 1024,
    }

    resp = requests.post(ARK_ENDPOINT, headers=headers, json=payload, timeout=120)
    print(f"  Status: {resp.status_code}")

    if resp.status_code != 200:
        print(f"  Error: {resp.text[:500]}")
        return False

    data = resp.json()
    # ARK returns base64 image in data[0].b64_json or url
    if "data" in data and len(data["data"]) > 0:
        item = data["data"][0]
        if "b64_json" in item:
            img_bytes = base64.b64decode(item["b64_json"])
            filepath = os.path.join(OUTPUT_DIR, filename)
            with open(filepath, "wb") as f:
                f.write(img_bytes)
            print(f"  Saved: {filepath} ({len(img_bytes)} bytes)")
            return True
        elif "url" in item:
            img_resp = requests.get(item["url"], timeout=60)
            filepath = os.path.join(OUTPUT_DIR, filename)
            with open(filepath, "wb") as f:
                f.write(img_resp.content)
            print(f"  Saved: {filepath} ({len(img_resp.content)} bytes)")
            return True

    print(f"  Unexpected response: {json.dumps(data, ensure_ascii=False)[:500]}")
    return False


def generate_gemini(filename, prompt):
    """Generate image using Gemini Imagen API."""
    print(f"\n[Gemini] Generating: {filename}")
    print(f"  Prompt: {prompt[:60]}...")

    headers = {"Content-Type": "application/json"}
    payload = {
        "instances": [{"prompt": prompt}],
        "parameters": {"sampleCount": 1, "aspectRatio": "1:1"},
    }

    resp = requests.post(
        GEMINI_ENDPOINT,
        headers=headers,
        json=payload,
        proxies=GEMINI_PROXY,
        timeout=120,
    )
    print(f"  Status: {resp.status_code}")

    if resp.status_code != 200:
        print(f"  Error: {resp.text[:500]}")
        return False

    data = resp.json()
    if "predictions" in data and len(data["predictions"]) > 0:
        b64_data = data["predictions"][0].get("bytesBase64Encoded") or data["predictions"][0].get("bytesContent")
        if b64_data:
            img_bytes = base64.b64decode(b64_data)
            filepath = os.path.join(OUTPUT_DIR, filename)
            with open(filepath, "wb") as f:
                f.write(img_bytes)
            print(f"  Saved: {filepath} ({len(img_bytes)} bytes)")
            return True

    print(f"  Unexpected response: {json.dumps(data, ensure_ascii=False)[:500]}")
    return False


def main():
    results = {}

    # Generate Doubao images
    for fname, prompt in DOUBAO_PROMPTS.items():
        ok = generate_doubao(fname, prompt)
        results[fname] = ok
        time.sleep(1)

    # Generate Gemini images
    for fname, prompt in GEMINI_PROMPTS.items():
        ok = generate_gemini(fname, prompt)
        results[fname] = ok
        time.sleep(1)

    # Summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    for fname, ok in results.items():
        status = "OK" if ok else "FAILED"
        print(f"  [{status}] {fname}")

    success = sum(1 for v in results.values() if v)
    print(f"\n  {success}/{len(results)} images generated successfully.")


if __name__ == "__main__":
    main()
