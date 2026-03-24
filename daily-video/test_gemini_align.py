#!/usr/bin/env python3
"""
测试 Gemini API 歌词时间戳对齐能力

用法:
  python test_gemini_align.py [audio_file] [lyrics_file]

默认使用:
  audio: 输出文件/歌曲/2026-03-12/cover/榜单-晴日西多士-口袋里的糖/榜单-晴日西多士-口袋里的糖-1.wav
  lyrics: 同目录下 lyrics_final.md
"""

import os
import sys
import json
import re
import base64
import mimetypes
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

# === 配置 ===
GEMINI_API_KEY = os.environ["GEMINI_API_KEY"]
PROXY = os.environ.get("HTTPS_PROXY") or os.environ.get("HTTP_PROXY")
MODEL = "gemini-3-flash-preview"

# 默认测试文件
DEFAULT_AUDIO = os.path.expanduser(
    "~/Documents/claude/输出文件/歌曲/2026-03-12/cover/"
    "榜单-晴日西多士-口袋里的糖/榜单-晴日西多士-口袋里的糖-1.wav"
)
DEFAULT_LYRICS = os.path.expanduser(
    "~/Documents/claude/输出文件/歌曲/2026-03-12/cover/"
    "榜单-晴日西多士-口袋里的糖/lyrics_final.md"
)


def parse_lyrics_from_md(md_path: str) -> str:
    """从 lyrics_final.md 提取纯歌词文本（去掉元信息头和段落标记）"""
    with open(md_path, "r", encoding="utf-8") as f:
        text = f.read()

    # 去掉 --- 之前的元信息
    if "---" in text:
        text = text.split("---", 1)[1]

    # 提取歌词行（去掉 [Verse 1] 等段落标记，保留纯歌词）
    lines = []
    for line in text.strip().splitlines():
        line = line.strip()
        if not line:
            continue
        # 跳过段落标记行如 [Verse 1], [Chorus], [Bridge] 等
        if re.match(r'^\[.*\]$', line):
            continue
        # 去掉行内注音标记如 (zhuàng), (fā)
        line = re.sub(r'\([a-zA-Zàáèéìíòóùúüǖǘǚǜ]+\)', '', line).strip()
        if line:
            lines.append(line)
    return "\n".join(lines)


def align_lyrics_with_gemini(audio_path: str, lyrics_text: str) -> list:
    """
    调用 Gemini API，上传音频 + 歌词文本，要求返回每句歌词的精确时间戳。

    返回格式: [{"start": 0.0, "end": 2.5, "text": "歌词内容"}, ...]
    """
    # 设置代理
    if PROXY:
        os.environ['http_proxy'] = PROXY
        os.environ['https_proxy'] = PROXY

    from google import genai
    from google.genai import types

    client = genai.Client(
        api_key=GEMINI_API_KEY,
        http_options=types.HttpOptions(timeout=300000),
    )

    # 读取音频文件并编码
    mime_type, _ = mimetypes.guess_type(audio_path)
    if mime_type is None:
        # 根据扩展名推断
        ext = os.path.splitext(audio_path)[1].lower()
        mime_map = {".wav": "audio/wav", ".mp3": "audio/mpeg", ".m4a": "audio/mp4"}
        mime_type = mime_map.get(ext, "audio/wav")

    print(f"[info] 音频文件: {audio_path}")
    print(f"[info] MIME类型: {mime_type}")
    print(f"[info] 文件大小: {os.path.getsize(audio_path) / 1024 / 1024:.1f} MB")
    print(f"[info] 歌词行数: {len(lyrics_text.splitlines())}")

    with open(audio_path, "rb") as f:
        audio_data = f.read()

    # 方式一：使用 File API 上传（推荐，支持大文件）
    print("[info] 上传音频到 Gemini File API...")
    uploaded_file = client.files.upload(
        file=audio_path,
        config=types.UploadFileConfig(mime_type=mime_type),
    )
    print(f"[info] 上传完成: {uploaded_file.name}, state={uploaded_file.state}")

    # 等待文件处理完成
    import time
    while uploaded_file.state.name == "PROCESSING":
        print("[info] 等待文件处理...")
        time.sleep(2)
        uploaded_file = client.files.get(name=uploaded_file.name)

    if uploaded_file.state.name == "FAILED":
        raise RuntimeError(f"文件处理失败: {uploaded_file.state}")

    print(f"[info] 文件就绪: state={uploaded_file.state}")

    # 构建 prompt
    prompt = (
        "这是一段歌曲音频，以下是歌词原文。"
        "请仔细聆听音频，精确标注每句歌词的开始时间和结束时间（精确到0.1秒）。\n"
        "要求：\n"
        "1. 每句歌词单独标注，不要合并多句\n"
        "2. 时间戳必须与音频中实际演唱的位置对齐\n"
        "3. 注意区分前奏、间奏、尾奏等无歌词部分\n"
        "4. 只返回JSON数组，不要其他文字\n\n"
        '输出格式为JSON数组：[{"start": 0.0, "end": 2.5, "text": "歌词内容"}]\n\n'
        f"歌词：\n{lyrics_text}"
    )

    # 调用 API
    print("[info] 调用 Gemini API 进行时间戳对齐...")
    response = client.models.generate_content(
        model=MODEL,
        contents=[
            types.Content(
                parts=[
                    types.Part.from_uri(
                        file_uri=uploaded_file.uri,
                        mime_type=mime_type,
                    ),
                    types.Part.from_text(text=prompt),
                ]
            )
        ],
        config=types.GenerateContentConfig(
            temperature=0.1,  # 低温度提高确定性
            response_mime_type="application/json",
        ),
    )

    # 解析响应
    raw_text = response.text.strip()
    print(f"[info] 原始响应长度: {len(raw_text)} 字符")

    # 尝试从响应中提取 JSON
    try:
        result = json.loads(raw_text)
    except json.JSONDecodeError:
        # 尝试提取 ```json ... ``` 代码块
        json_match = re.search(r'```json\s*(.*?)\s*```', raw_text, re.DOTALL)
        if json_match:
            result = json.loads(json_match.group(1))
        else:
            # 尝试提取方括号内容
            bracket_match = re.search(r'\[.*\]', raw_text, re.DOTALL)
            if bracket_match:
                result = json.loads(bracket_match.group(0))
            else:
                print(f"[error] 无法解析响应:\n{raw_text[:500]}")
                return []

    # 清理上传的文件
    try:
        client.files.delete(name=uploaded_file.name)
        print("[info] 已清理上传的文件")
    except Exception:
        pass

    return result


def format_timestamp(seconds: float) -> str:
    """将秒数格式化为 mm:ss.d"""
    m = int(seconds) // 60
    s = seconds - m * 60
    return f"{m:02d}:{s:05.2f}"


def main():
    audio_path = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_AUDIO
    lyrics_path = sys.argv[2] if len(sys.argv) > 2 else DEFAULT_LYRICS

    if not os.path.exists(audio_path):
        print(f"[error] 音频文件不存在: {audio_path}")
        sys.exit(1)
    if not os.path.exists(lyrics_path):
        print(f"[error] 歌词文件不存在: {lyrics_path}")
        sys.exit(1)

    # 解析歌词
    if lyrics_path.endswith(".md"):
        lyrics_text = parse_lyrics_from_md(lyrics_path)
    else:
        with open(lyrics_path, "r", encoding="utf-8") as f:
            lyrics_text = f.read().strip()

    print("=" * 60)
    print("Gemini 歌词时间戳对齐测试")
    print("=" * 60)
    print(f"音频: {audio_path}")
    print(f"歌词: {lyrics_path}")
    print(f"模型: {MODEL}")
    print(f"代理: {PROXY}")
    print()
    print("--- 歌词内容 ---")
    print(lyrics_text)
    print("--- END ---")
    print()

    # 调用 Gemini
    timestamps = align_lyrics_with_gemini(audio_path, lyrics_text)

    # 输出结果
    print()
    print("=" * 60)
    print(f"对齐结果 ({len(timestamps)} 句)")
    print("=" * 60)
    for i, item in enumerate(timestamps):
        start = item.get("start", 0)
        end = item.get("end", 0)
        text = item.get("text", "")
        duration = end - start
        print(f"  [{format_timestamp(start)} -> {format_timestamp(end)}] ({duration:.1f}s) {text}")

    # 保存结果到 JSON
    out_json = os.path.splitext(audio_path)[0] + "_timestamps.json"
    with open(out_json, "w", encoding="utf-8") as f:
        json.dump(timestamps, f, ensure_ascii=False, indent=2)
    print(f"\n[info] 结果已保存: {out_json}")

    # 基本质量检查
    print("\n--- 质量检查 ---")
    lyrics_lines = lyrics_text.strip().splitlines()
    print(f"  歌词行数: {len(lyrics_lines)}")
    print(f"  时间戳数: {len(timestamps)}")
    if len(timestamps) == len(lyrics_lines):
        print("  匹配状态: MATCH")
    else:
        print(f"  匹配状态: MISMATCH (差 {abs(len(timestamps) - len(lyrics_lines))} 句)")

    # 检查时间戳是否单调递增
    monotonic = True
    for i in range(1, len(timestamps)):
        if timestamps[i]["start"] < timestamps[i - 1]["start"]:
            monotonic = False
            print(f"  [warn] 非单调递增: 第{i}句 start={timestamps[i]['start']} < 第{i-1}句 start={timestamps[i-1]['start']}")
    if monotonic:
        print("  时间顺序: OK (单调递增)")

    if timestamps:
        total_duration = timestamps[-1]["end"]
        print(f"  音频覆盖: 0s ~ {total_duration:.1f}s ({format_timestamp(total_duration)})")


if __name__ == "__main__":
    main()
