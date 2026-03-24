import os
import sys
import requests
import base64
import time
import threading
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

# Config
ARK_KEY = os.environ["ARK_API_KEY"]
GEMINI_KEY = os.environ["GEMINI_API_KEY"]
OUT_DIR = "/Users/xuejin/Documents/claude/输出文件/2026-03-12/cover/成品曲-晴日西多士-春芽-植树节"

# Prompts
themes = {
    "泥土发芽": {
        "doubao": "一颗嫩绿的小芽从龟裂的泥土中破土而出，柔和的清晨阳光照射，微距特写镜头，小叶片上挂着晶莹的露珠，温暖的大地色调搭配清新的绿色点缀，高品质摄影风格，细节丰富，唯美自然",
        "gemini": "A tender green sprout pushing through cracked earth, soft morning light, close-up macro shot, dewdrops on the tiny leaf, warm earthy tones with fresh green accent, high quality photography, rich details, beautiful nature, album cover art style"
    },
    "山坡小树": {
        "doubao": "一棵小树苗种在阳光明媚的山坡上，旁边放着一个浇水壶，欢快的春天氛围，明亮鲜艳的色彩，微风轻拂，背景柔和虚化，高品质摄影风格，温馨治愈，充满希望",
        "gemini": "A small sapling on a sunny hillside, a watering can nearby, cheerful spring atmosphere, bright colors, gentle breeze, soft bokeh background, high quality photography, warm and healing, full of hope, album cover art style"
    }
}

results = {}
errors = {}

def gen_doubao(theme_name, prompt):
    """Generate image using Doubao Seedream API"""
    try:
        print(f"[doubao/{theme_name}] Starting generation...")
        r = requests.post(
            "https://ark.cn-beijing.volces.com/api/v3/images/generations",
            headers={"Authorization": f"Bearer {ARK_KEY}", "Content-Type": "application/json"},
            json={
                "model": "doubao-seedream-3-0-t2i-250415",
                "prompt": prompt,
                "width": 1024,
                "height": 1024,
                "n": 1
            },
            timeout=300
        )
        r.raise_for_status()
        data = r.json()
        b64 = data["data"][0]["b64_json"]
        out_path = os.path.join(OUT_DIR, f"cover_{theme_name}_doubao.png")
        with open(out_path, "wb") as f:
            f.write(base64.b64decode(b64))
        print(f"[doubao/{theme_name}] Saved to {out_path}")
        results[f"doubao_{theme_name}"] = out_path
    except Exception as e:
        print(f"[doubao/{theme_name}] ERROR: {e}")
        errors[f"doubao_{theme_name}"] = str(e)

def gen_gemini(theme_name, prompt):
    """Generate image using Gemini API"""
    try:
        print(f"[gemini/{theme_name}] Starting generation...")
        proxy = os.environ.get("HTTPS_PROXY") or os.environ.get("HTTP_PROXY")
        if proxy:
            os.environ['http_proxy'] = proxy
            os.environ['https_proxy'] = proxy
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=GEMINI_KEY, http_options=types.HttpOptions(timeout=300000))
        response = client.models.generate_content(
            model="gemini-3-pro-image-preview",
            contents=prompt,
            config=types.GenerateContentConfig(response_modalities=["image", "text"])
        )

        # Find and save image from response
        saved = False
        for part in response.candidates[0].content.parts:
            if hasattr(part, 'inline_data') and part.inline_data is not None:
                out_path = os.path.join(OUT_DIR, f"cover_{theme_name}_nb.png")
                with open(out_path, "wb") as f:
                    f.write(part.inline_data.data)
                print(f"[gemini/{theme_name}] Saved to {out_path}")
                results[f"gemini_{theme_name}"] = out_path
                saved = True
                break
        if not saved:
            print(f"[gemini/{theme_name}] No image in response")
            errors[f"gemini_{theme_name}"] = "No image data in response"
    except Exception as e:
        print(f"[gemini/{theme_name}] ERROR: {e}")
        errors[f"gemini_{theme_name}"] = str(e)

# Run all 4 generations in parallel
threads = []
for theme_name, prompts in themes.items():
    t1 = threading.Thread(target=gen_doubao, args=(theme_name, prompts["doubao"]))
    t2 = threading.Thread(target=gen_gemini, args=(theme_name, prompts["gemini"]))
    threads.extend([t1, t2])
    t1.start()
    t2.start()

for t in threads:
    t.join()

print(f"\n=== Results ===")
print(f"Success: {len(results)}/4")
for k, v in results.items():
    print(f"  {k}: {v}")
if errors:
    print(f"Errors: {len(errors)}")
    for k, v in errors.items():
        print(f"  {k}: {v}")
