"""
Suno 直连客户端 — 替代 kie.ai
使用 Clerk JWT 鉴权，自动刷新 access token
"""
import os, json, time, urllib.request, urllib.error, urllib.parse, sys, subprocess


def _prompt_heartbeat_refresh():
    """
    弹出 macOS 对话框，提醒用户在 Chrome 里刷新 suno.com（Turnstile 心跳）。
    仅在 macOS 本地运行时生效，云端/Linux 自动跳过。

    ⚠️ 注意（推测，未验证）：
    目前假设 Suno generate 422 "Token validation failed" 的根因是 Clerk captcha_heartbeat 过期。
    这是推测，尚未通过抓包/源码/官方文档验证。实际原因可能不同。
    如果刷新后仍然 422，需要重新调查根因，不要继续假设是心跳问题。
    """
    if sys.platform != "darwin":
        return  # 非 macOS（如 Linux 云端），跳过
    script = '''
    tell application "Google Chrome"
        open location "https://suno.com/create"
    end tell
    tell application "System Events"
        tell process "Google Chrome"
            set frontmost to true
        end tell
    end tell
    display dialog "请在 Chrome 里滚动/点击一下 suno.com 页面（刷新 Turnstile 心跳），然后点 OK 继续提交。" ¬
        buttons {"OK"} default button "OK" with title "Suno 提交前确认" with icon caution
    '''
    subprocess.run(["osascript", "-e", script], check=True)
    time.sleep(2)  # 给 Clerk heartbeat 一点时间刷新

CLERK_BASE = "https://auth.suno.com"
STUDIO_BASE = "https://studio-api-prod.suno.com"
CLERK_JS_VERSION = "4.72.0-snapshot.vc141245"

ENV_FILE = os.path.join(os.path.dirname(__file__), ".env")


def load_env():
    env = {}
    if os.path.exists(ENV_FILE):
        for line in open(ENV_FILE):
            line = line.strip()
            if "=" in line and not line.startswith("#"):
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip()
    return env


def save_env_key(key, value):
    """更新 .env 中的单个 key"""
    lines = open(ENV_FILE).readlines() if os.path.exists(ENV_FILE) else []
    found = False
    new_lines = []
    for line in lines:
        if line.startswith(f"{key}="):
            new_lines.append(f"{key}={value}\n")
            found = True
        else:
            new_lines.append(line)
    if not found:
        new_lines.append(f"{key}={value}\n")
    with open(ENV_FILE, "w") as f:
        f.writelines(new_lines)


def _request(url, *, method="GET", headers=None, body=None, proxy=None):
    req = urllib.request.Request(url, method=method, headers=headers or {})
    if body:
        req.data = json.dumps(body).encode() if isinstance(body, dict) else body
    if proxy:
        req.set_proxy(proxy, "https")
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, {}


class SunoClient:
    def __init__(self, refresh_token: str = None, proxy: str = None):
        env = load_env()
        # 优先级：传入参数 > Chrome动态读取 > .env静态值
        if refresh_token:
            self.refresh_token = refresh_token
        else:
            # 优先从 Chrome cookies 动态读取（token 始终最新）
            try:
                from pycookiecheat import chrome_cookies
                auth_cookies = chrome_cookies("https://auth.suno.com")
                self.refresh_token = (
                    auth_cookies.get("__client") or
                    auth_cookies.get("__client_Jnxw-muT") or ""
                )
                if self.refresh_token:
                    print("[suno] 已从 Chrome 动态读取 __client token", flush=True)
            except Exception:
                self.refresh_token = ""
            # fallback: 从 .env 读取
            if not self.refresh_token:
                cookie_str = env.get("SUNO_COOKIE", "")
                client_part = next(
                    (p.strip() for p in cookie_str.split(";") if "__client=" in p), ""
                )
                self.refresh_token = client_part.replace("__client=", "").strip()
                if self.refresh_token:
                    print("[suno] 已从 .env 读取 __client token（静态，可能过期）", flush=True)

        self.proxy = proxy or os.environ.get("HTTPS_PROXY") or os.environ.get("HTTP_PROXY") or ""
        self._access_token = None
        self._session_id = None
        self._token_exp = 0

    # ── Token 管理 ──────────────────────────────────────────────────────────

    def _get_sessions(self):
        """用 __client cookie 查询当前 sessions"""
        url = f"{CLERK_BASE}/v1/client?_clerk_js_version={CLERK_JS_VERSION}"
        status, data = _request(url, headers={
            "Cookie": f"__client={self.refresh_token}",
            "User-Agent": "Mozilla/5.0",
        })
        if status != 200:
            raise RuntimeError(f"Clerk /v1/client 返回 {status}")
        sessions = data.get("response", {}).get("sessions", [])
        # 取 active session
        active = [s for s in sessions if s.get("status") == "active"]
        if not active:
            raise RuntimeError("没有 active session，Refresh Token 可能已失效")
        return active[0]["id"]

    def _refresh_access_token(self):
        if not self._session_id:
            self._session_id = self._get_sessions()
        url = (f"{CLERK_BASE}/v1/client/sessions/{self._session_id}/tokens"
               f"?_clerk_js_version={CLERK_JS_VERSION}")
        status, data = _request(url, method="POST", headers={
            "Cookie": f"__client={self.refresh_token}",
            "Content-Type": "application/json",
            "User-Agent": "Mozilla/5.0",
        })
        if status != 200:
            raise RuntimeError(f"Token 刷新失败 {status}: {data}")
        token = data.get("jwt") or data.get("token")
        if not token:
            raise RuntimeError(f"刷新响应中无 token: {data}")
        self._access_token = token
        self._token_exp = time.time() + 3300  # 55 分钟刷一次
        print(f"[suno] access token 已刷新", flush=True)

    def _token(self):
        if not self._access_token or time.time() > self._token_exp:
            self._refresh_access_token()
        return self._access_token

    def _auth_headers(self):
        token = self._token()
        return {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
            "Origin": "https://suno.com",
            "Referer": "https://suno.com/",
            "Cookie": f"__client={self.refresh_token}; __session={token}",
        }

    # ── 核心 API ────────────────────────────────────────────────────────────

    def get_credits(self):
        """查询剩余积分"""
        status, data = _request(
            f"{STUDIO_BASE}/api/billing/info/",
            headers=self._auth_headers(),
        )
        if status != 200:
            raise RuntimeError(f"billing/info 返回 {status}")
        return data.get("total_credits_left", 0)

    def upload_audio(self, file_path: str) -> str:
        """
        上传本地音频文件到 Suno S3，返回 upload_id（用于 cover_remix / inspo_generate）
        支持 mp3/wav，文件大小上限 ~500MB
        """
        import mimetypes, urllib.parse
        ext = os.path.splitext(file_path)[1].lower().lstrip(".")
        content_type = "audio/mpeg" if ext == "mp3" else "audio/wav"

        # Step1: 获取 S3 预签名凭证
        status, data = _request(
            f"{STUDIO_BASE}/api/uploads/audio/",
            method="POST",
            headers=self._auth_headers(),
            body={"extension": ext},
        )
        if status != 200:
            raise RuntimeError(f"uploads/audio 返回 {status}: {data}")

        upload_id = data["id"]
        s3_url    = data["url"]
        fields    = data["fields"]
        print(f"[suno] 拿到 upload_id={upload_id}", flush=True)

        # Step2: 上传文件到 S3（multipart/form-data）
        boundary = "----SunoUploadBoundary"
        parts = []
        for k, v in fields.items():
            parts.append(f"--{boundary}\r\nContent-Disposition: form-data; name=\"{k}\"\r\n\r\n{v}".encode())
        with open(file_path, "rb") as f:
            file_data = f.read()
        parts.append(
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"upload.{ext}\"\r\nContent-Type: {content_type}\r\n\r\n".encode()
            + file_data
        )
        parts.append(f"--{boundary}--".encode())
        body_bytes = b"\r\n".join(parts)

        s3_req = urllib.request.Request(
            s3_url, method="POST",
            headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
            data=body_bytes,
        )
        try:
            with urllib.request.urlopen(s3_req, timeout=120) as r:
                print(f"[suno] S3 上传完成，status={r.status}", flush=True)
        except urllib.error.HTTPError as e:
            raise RuntimeError(f"S3 上传失败 {e.code}: {e.read().decode()}")

        return upload_id

    def cover_remix(self, upload_id: str, style: str, title: str,
                    lyrics: str = "") -> list[str]:
        """
        cover-remix 模式（歌曲二创）：上传本地音频后换声线/风格
        task: cover + is_remix: true  endpoint: /api/generate/v2-web/

        upload_id: upload_audio() 返回的 ID（上传本地音频后得到，作为 cover_clip_id 传入）
        style:     Style Prompt（tags 字段，≤200字符）
        lyrics:    歌词（prompt 字段，传原曲歌词或留空）

        完整调用流程：
            upload_id = client.upload_audio("/path/to/song.mp3")
            ids = client.cover_remix(upload_id, style, title, lyrics)
        """
        _prompt_heartbeat_refresh()
        if len(style) > 200:
            raise ValueError(f"Style Prompt 超过200字符（{len(style)}字符），请裁剪")
        body = {
            "generation_type": "TEXT",
            "task": "cover",
            "mv": "chirp-crow",
            "title": title,
            "prompt": lyrics,
            "tags": style,
            "negative_tags": "",
            "cover_clip_id": upload_id,
            "is_remix": True,
            "make_instrumental": False,
            "token": None,
            "override_fields": [],
            "persona_id": None,
            "metadata": {
                "create_mode": "custom",
                "is_max_mode": False,
                "is_mumble": False,
                "is_remix": True,
            },
        }
        status, data = _request(
            f"{STUDIO_BASE}/api/generate/v2-web/",
            method="POST",
            headers=self._auth_headers(),
            body=body,
        )
        if status not in (200, 201):
            raise RuntimeError(f"cover_remix 返回 {status}: {data}")
        clips = data.get("clips") or []
        ids = [c["id"] for c in clips]
        print(f"[suno] cover-remix 已提交，clip_ids={ids}", flush=True)
        return ids

    def _get_user_tier(self) -> str:
        """从 billing/info 获取当前用户的 plan id（user_tier）"""
        status, data = _request(
            f"{STUDIO_BASE}/api/billing/info/",
            headers=self._auth_headers(),
        )
        if status != 200:
            return None
        return data.get("plan", {}).get("id")

    def inspo_generate(self, clip_id: str, description: str, title: str,
                       lyrics: str = "", style: str = "") -> list[str]:
        """
        cover-inspo 模式：以已有 clip 为旋律灵感，生成全新歌曲
        task: playlist_condition  endpoint: /api/generate/v2-web/

        clip_id:     已有 Suno clip ID（作为 playlist_clip_ids 传入）
        description: 风格描述（仅记录用，不传给 Suno）
        style:       Style Prompt（tags 字段，显式指定声线/风格；留空则 Suno 从参考 clip 自动推断）
        lyrics:      歌词（prompt 字段，留空则 Suno 自动生成）
        """
        import uuid as _uuid
        _prompt_heartbeat_refresh()
        user_tier = self._get_user_tier()
        body = {
            "generation_type": "TEXT",
            "task": "playlist_condition",
            "mv": "chirp-crow",
            "prompt": lyrics,
            "tags": style,
            "negative_tags": "",
            "playlist_clip_ids": [clip_id],
            "playlist_id": "inspiration",
            "make_instrumental": False,
            "token": None,
            "transaction_uuid": str(_uuid.uuid4()),
            "override_fields": [],
            "persona_id": None,
            "cover_clip_id": None,
            "artist_clip_id": None,
            "continue_clip_id": None,
            "continue_at": None,
            "user_uploaded_images_b64": None,
            "title": title,
            "metadata": {
                "web_client_pathname": "/create",
                "is_max_mode": False,
                "is_mumble": False,
                "create_mode": "custom",
                "create_session_token": str(_uuid.uuid4()),
                "disable_volume_normalization": False,
                "user_tier": user_tier,
            },
        }
        status, data = _request(
            f"{STUDIO_BASE}/api/generate/v2-web/",
            method="POST",
            headers=self._auth_headers(),
            body=body,
        )
        if status not in (200, 201):
            raise RuntimeError(f"inspo_generate 返回 {status}: {data}")
        clips = data.get("clips") or []
        ids = [c["id"] for c in clips]
        print(f"[suno] cover-inspo 已提交，clip_ids={ids}", flush=True)
        return ids

    def custom_generate(self, lyrics: str, style: str, title: str,
                        make_instrumental=False) -> list[str]:
        """
        生成歌曲，返回 clip_id 列表（通常2个）
        lyrics: 完整歌词（含 [Verse] 等标签）
        style:  Style Prompt（≤200字符）
        title:  歌曲名
        """
        import uuid as _uuid
        _prompt_heartbeat_refresh()
        if len(style) > 200:
            raise ValueError(f"Style Prompt 超过200字符（当前{len(style)}字符），请裁剪后重试")
        user_tier = self._get_user_tier()
        body = {
            "generation_type": "TEXT",
            "mv": "chirp-crow",
            "prompt": lyrics,
            "tags": style,
            "negative_tags": "",
            "title": title,
            "make_instrumental": make_instrumental,
            "token": None,
            "transaction_uuid": str(_uuid.uuid4()),
            "override_fields": [],
            "persona_id": None,
            "cover_clip_id": None,
            "artist_clip_id": None,
            "continue_clip_id": None,
            "continue_at": None,
            "user_uploaded_images_b64": None,
            "playlist_clip_ids": None,
            "metadata": {
                "web_client_pathname": "/create",
                "is_max_mode": False,
                "is_mumble": False,
                "create_mode": "custom",
                "create_session_token": str(_uuid.uuid4()),
                "disable_volume_normalization": False,
                "user_tier": user_tier,
            },
        }
        status, data = _request(
            f"{STUDIO_BASE}/api/generate/v2-web/",
            method="POST",
            headers=self._auth_headers(),
            body=body,
        )
        if status not in (200, 201):
            raise RuntimeError(f"generate 返回 {status}: {data}")
        clips = data.get("clips") or []
        ids = [c["id"] for c in clips]
        print(f"[suno] 已提交，clip_ids={ids}", flush=True)
        return ids

    def wait_for_clips(self, clip_ids: list[str],
                       timeout=300, interval=5) -> list[dict]:
        """轮询直到所有 clip 完成，返回 clip 列表"""
        deadline = time.time() + timeout
        while time.time() < deadline:
            ids_param = ",".join(clip_ids)
            status, data = _request(
                f"{STUDIO_BASE}/api/feed/?ids={ids_param}",
                headers=self._auth_headers(),
            )
            if status != 200:
                raise RuntimeError(f"feed 返回 {status}")
            clips = data if isinstance(data, list) else data.get("clips", [])
            statuses = [c.get("status", "") for c in clips]
            print(f"[suno] 状态: {statuses}", flush=True)
            if all(s in ("complete", "error") for s in statuses):
                failed = [c for c in clips if c.get("status") == "error"]
                if failed:
                    print(f"[suno] ⚠️ {len(failed)} 个 clip 生成失败", flush=True)
                return [c for c in clips if c.get("status") == "complete"]
            time.sleep(interval)
        raise TimeoutError(f"等待超时（{timeout}s）")

    def download_clip(self, clip: dict, out_dir: str, filename: str = None) -> str:
        """下载 clip 音频到 out_dir，优先 WAV，回退 MP3"""
        audio_url = clip.get("audio_url") or clip.get("video_url")
        if not audio_url:
            raise ValueError(f"clip {clip.get('id')} 无 audio_url")
        os.makedirs(out_dir, exist_ok=True)

        # 优先尝试 WAV（无损，高质量）
        wav_url = audio_url.replace(".mp3", ".wav")
        try:
            req = urllib.request.Request(wav_url, method="HEAD",
                                         headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=10) as r:
                if r.status == 200:
                    audio_url = wav_url
                    print(f"[suno] WAV 可用，切换到 WAV 下载", flush=True)
        except Exception:
            pass  # WAV 不可用，继续用 MP3

        ext = ".wav" if audio_url.endswith(".wav") else ".mp3"
        if filename:
            # 替换调用方传入的扩展名
            base = filename.rsplit(".", 1)[0] if "." in filename else filename
            fname = base + ext
        else:
            fname = f"{clip['id']}{ext}"
        out_path = os.path.join(out_dir, fname)
        print(f"[suno] 下载 {audio_url} → {out_path}", flush=True)
        urllib.request.urlretrieve(audio_url, out_path)
        return out_path


# ── CLI 快速测试 ─────────────────────────────────────────────────────────────

def main():
    import argparse

    ap = argparse.ArgumentParser(
        description="Suno 直连客户端",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
子命令示例：
  # 查询积分
  python3 suno_client.py credits

  # cover-sample：上传本地音频，换声线/风格，歌词可自定义
  python3 suno_client.py sample \\
    --audio /path/to/ref.mp3 \\
    --style "indie pop ballad, 90 BPM, breathy female vocals" \\
    --title "告白气球-微醺版" \\
    --lyrics "[Verse]\\n歌词内容..." \\
    --start 0 --end 60 \\
    --out ~/Desktop/output/

  # cover-inspo：以参考曲为旋律灵感，生成全新歌曲
  python3 suno_client.py inspo \\
    --audio /path/to/ref.mp3 \\
    --description "indie pop ballad, 90 BPM, breathy female vocals" \\
    --title "新歌名" \\
    --lyrics "[Verse]\\n全新歌词..." \\
    --out ~/Desktop/output/
""",
    )

    sub = ap.add_subparsers(dest="cmd")

    # ── credits ──────────────────────────────────────────────────────────────
    sub.add_parser("credits", help="查询剩余积分")

    # ── remix（cover-remix，歌曲二创） ───────────────────────────────────────────
    p_sample = sub.add_parser("remix", help="cover-remix（歌曲二创）：上传音频后换声线/风格")
    p_sample.add_argument("--audio",  required=True, help="本地音频路径（mp3/wav），上传后作为 cover_clip_id")
    p_sample.add_argument("--style",  required=True, help="Style Prompt（≤200字符，tags字段）")
    p_sample.add_argument("--title",  required=True, help="歌曲名")
    p_sample.add_argument("--lyrics", default="",    help="歌词（留空则Suno自动生成）")
    p_sample.add_argument("--out",    default="/tmp/suno_out", help="输出目录")
    p_sample.add_argument("--timeout", type=int, default=400,  help="等待超时秒数")

    # ── inspo（cover-inspo） ──────────────────────────────────────────────────
    p_inspo = sub.add_parser("inspo", help="cover-inspo：以参考曲为灵感，生成全新歌曲")
    p_inspo.add_argument("--audio",       required=True, help="本地音频路径（mp3/wav）")
    p_inspo.add_argument("--description", required=True, help="风格描述（gpt_description_prompt字段）")
    p_inspo.add_argument("--title",       required=True, help="歌曲名")
    p_inspo.add_argument("--lyrics",      default="",    help="歌词（留空则Suno自动生成）")
    p_inspo.add_argument("--out",         default="/tmp/suno_out", help="输出目录")
    p_inspo.add_argument("--timeout",     type=int, default=400,   help="等待超时秒数")

    # ── 公共参数 ──────────────────────────────────────────────────────────────
    ap.add_argument("--refresh-token", help="指定 Refresh Token（否则读 .env）")

    args = ap.parse_args()

    if not args.cmd:
        ap.print_help()
        return

    client = SunoClient(refresh_token=args.refresh_token or None)

    # ── credits ──────────────────────────────────────────────────────────────
    if args.cmd == "credits":
        c = client.get_credits()
        print(f"剩余积分: {c}")

    # ── sample ────────────────────────────────────────────────────────────────
    elif args.cmd == "remix":
        print(f"[remix] 上传音频: {args.audio}")
        upload_id = client.upload_audio(args.audio)

        print(f"[remix] 提交生成，style={args.style[:50]}...")
        ids = client.cover_remix(
            upload_id=upload_id,
            style=args.style,
            title=args.title,
            lyrics=args.lyrics,
        )
        print(f"[remix] clip_ids={ids}，等待完成...")
        clips = client.wait_for_clips(ids, timeout=args.timeout)
        print(f"[remix] 完成 {len(clips)} 个 clip")
        for i, clip in enumerate(clips):
            fname = f"{args.title}_{i+1}"
            path = client.download_clip(clip, out_dir=args.out, filename=fname)
            print(f"  → {path}")

    # ── inspo ─────────────────────────────────────────────────────────────────
    elif args.cmd == "inspo":
        print(f"[inspo] 上传音频: {args.audio}")
        upload_id = client.upload_audio(args.audio)

        print(f"[inspo] 提交生成，description={args.description[:50]}...")
        ids = client.inspo_generate(
            clip_id=upload_id,
            description=args.description,
            title=args.title,
            lyrics=args.lyrics,
        )
        print(f"[inspo] clip_ids={ids}，等待完成...")
        clips = client.wait_for_clips(ids, timeout=args.timeout)
        print(f"[inspo] 完成 {len(clips)} 个 clip")
        for i, clip in enumerate(clips):
            fname = f"{args.title}_{i+1}"
            path = client.download_clip(clip, out_dir=args.out, filename=fname)
            print(f"  → {path}")


if __name__ == "__main__":
    main()
