import os
from pathlib import Path
import requests

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
r = requests.post(
    "https://ark.cn-beijing.volces.com/api/v3/images/generations",
    headers={"Authorization": f"Bearer {ARK_KEY}", "Content-Type": "application/json"},
    json={
        "model": "doubao-seedream-3-0-t2i-250415",
        "prompt": "一颗嫩绿的小芽从泥土中破土而出",
        "width": 1024,
        "height": 1024,
        "response_format": "b64_json",
        "n": 1
    },
    timeout=300
)
data = r.json()
# Print structure without the actual image data
import json
if "data" in data:
    for item in data["data"]:
        print("Keys in data item:", list(item.keys()))
        for k, v in item.items():
            if k in ("b64_json", "b64"):
                print(f"  {k}: <base64 data, length={len(v)}>")
            else:
                print(f"  {k}: {v}")
else:
    print(json.dumps(data, indent=2, ensure_ascii=False))
