#!/usr/bin/env python3
"""Claude API 生成推荐语（≤15字，1句）"""

import anthropic, os
from dotenv import load_dotenv
from pathlib import Path

load_dotenv(Path(__file__).parent / ".env")

PROMPT_TEMPLATE = """你是一个抖音推歌博主，人设是"深夜替你听完100首歌，只留下这1首"。
写1句推荐旁白。
要求：≤15字，只说1句，禁止广告体
风格：筛选感+场景代入（深夜/凌晨/失眠）或行为说穿
禁止出现：宝藏、神仙、绝了、yyds、好听哭了
歌曲信息：{song_name} / {artist} / 情绪：{emotion}
只输出1句话，不加序号，不加引号，不加任何说明"""

def gen_recommendation(song_name: str, artist: str, emotion: str) -> str:
    key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not key or key == "待填写":
        fallback = "深夜听到这首，发给你"
        print(f"⚠️  ANTHROPIC_API_KEY 未配置，使用默认推荐语: {fallback}")
        return fallback
    client = anthropic.Anthropic(api_key=key)
    prompt = PROMPT_TEMPLATE.format(
        song_name=song_name, artist=artist, emotion=emotion
    )
    msg = client.messages.create(
        model="claude-opus-4-6",
        max_tokens=64,
        messages=[{"role": "user", "content": prompt}]
    )
    text = msg.content[0].text.strip()
    if len(text) > 20:
        text = text[:15]
    return text

if __name__ == "__main__":
    # ANTHROPIC_API_KEY 可能是 "待填写"，跳过实际调用，只验证模块加载
    key = os.environ.get("ANTHROPIC_API_KEY", "")
    if key and key != "待填写":
        result = gen_recommendation("晴天", "周杰伦", "思念/暗恋")
        print(f"推荐语：{result}（{len(result)}字）")
    else:
        print("⚠️  ANTHROPIC_API_KEY 未配置，跳过实际调用。模块加载正常。")
