import os
import requests
import base64
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

ARK_KEY = os.environ["ARK_API_KEY"]
OUT_DIR = "/Users/xuejin/Documents/claude/输出文件/2026-03-12/cover/成品曲-晴日西多士-春芽-植树节"

themes = {
    "泥土发芽": "一颗嫩绿的小芽从龟裂的泥土中破土而出，柔和的清晨阳光照射，微距特写镜头，小叶片上挂着晶莹的露珠，温暖的大地色调搭配清新的绿色点缀，高品质摄影风格，细节丰富，唯美自然",
    "山坡小树": "一棵小树苗种在阳光明媚的山坡上，旁边放着一个浇水壶，欢快的春天氛围，明亮鲜艳的色彩，微风轻拂，背景柔和虚化，高品质摄影风格，温馨治愈，充满希望"
}

def gen(theme_name, prompt):
    try:
        print(f"[doubao/{theme_name}] Starting...")
        r = requests.post(
            "https://ark.cn-beijing.volces.com/api/v3/images/generations",
            headers={"Authorization": f"Bearer {ARK_KEY}", "Content-Type": "application/json"},
            json={
                "model": "doubao-seedream-3-0-t2i-250415",
                "prompt": prompt,
                "response_format": "b64_json",
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
        print(f"[doubao/{theme_name}] Saved: {out_path}")
    except Exception as e:
        print(f"[doubao/{theme_name}] ERROR: {e}")

threads = []
for name, prompt in themes.items():
    t = threading.Thread(target=gen, args=(name, prompt))
    threads.append(t)
    t.start()
for t in threads:
    t.join()
print("Done.")
