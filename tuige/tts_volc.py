#!/usr/bin/env python3
"""火山引擎 TTS — 将文字合成为 WAV 音频"""

import os, json, uuid, base64, requests
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

VOLC_URL = "https://openspeech.bytedance.com/api/v1/tts"

def synthesize(text: str, output_path: str) -> str:
    app_id = os.environ.get("VOLC_APP_ID", "")
    token = os.environ.get("VOLC_ACCESS_TOKEN", "")
    if not app_id or app_id == "待填写" or not token or token == "待填写":
        # 生成静音占位音频（3秒），避免流水线中断
        import wave, struct, array
        with wave.open(output_path, 'w') as wf:
            wf.setnchannels(1); wf.setsampwidth(2); wf.setframerate(22050)
            wf.writeframes(array.array('h', [0] * 22050 * 3).tobytes())
        print(f"⚠️  VOLC 未配置，生成静音占位音频: {output_path}")
        return output_path
    voice_type = os.environ.get("VOLC_VOICE_TYPE", "zh_female_tianmeixiaoyuan_moon_bigtts")

    payload = {
        "app": {"appid": app_id, "token": token, "cluster": "volcano_tts"},
        "user": {"uid": "tuige_user"},
        "audio": {
            "voice_type": voice_type,
            "encoding": "wav",
            "speed_ratio": 1.0,
            "volume_ratio": 1.0,
            "pitch_ratio": 1.0,
        },
        "request": {
            "reqid": str(uuid.uuid4()),
            "text": text,
            "text_type": "plain",
            "operation": "query",
            "with_frontend": 1,
            "frontend_type": "unitTson",
        },
    }

    headers = {"Authorization": f"Bearer;{token}"}
    resp = requests.post(VOLC_URL, json=payload, headers=headers, timeout=30)
    resp.raise_for_status()

    data = resp.json()
    if data.get("code") != 3000:
        raise RuntimeError(f"TTS 失败: {data.get('message')} (code={data.get('code')})")

    audio_bytes = base64.b64decode(data["data"])
    with open(output_path, "wb") as f:
        f.write(audio_bytes)

    print(f"✅ TTS 已生成: {output_path} ({len(audio_bytes)//1024}KB)")
    return output_path

if __name__ == "__main__":
    app_id = os.environ.get("VOLC_APP_ID", "")
    token = os.environ.get("VOLC_ACCESS_TOKEN", "")
    if not app_id or app_id == "待填写" or not token or token == "待填写":
        print("⚠️  VOLC_APP_ID / VOLC_ACCESS_TOKEN 未配置，跳过实际调用。模块加载正常。")
    else:
        import tempfile
        out = tempfile.mktemp(suffix=".wav")
        synthesize("凌晨听到这首，想起一个人", out)
        print(f"试听: open {out}")
