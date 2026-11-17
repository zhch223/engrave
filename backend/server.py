# -*- coding: utf-8 -*-
"""
星语铭后端管理系统（零依赖，Python 标准库实现）

公开接口（供前台留言板调用）:
    GET  /api/messages?profile=<id>   获取指定人物的留言（按时间倒序）
    POST /api/messages                提交留言  body: {"profile","name","content"}
    GET  /api/health                  健康检查

认证:
    POST /api/login                   登录 body: {"username","password"} → 设置会话 Cookie
    POST /api/logout                  退出登录
    GET  /api/auth/check              检查登录状态

管理接口（需登录，Cookie 鉴权）:
    GET    /admin                              管理后台页面（未登录由页面内登录框接管）
    GET    /api/admin/stats                    留言统计
    GET    /api/admin/messages?profile=&q=     留言列表（可过滤）
    DELETE /api/admin/messages?id=             删除单条留言
    POST   /api/admin/clear                    清空留言 {"profile":"id"} 或 {"all":true}

资料卡管理（需登录）:
    GET    /api/admin/people                   人物列表
    GET    /api/admin/people/<id>              读取资料卡 {info, bio}
    PUT    /api/admin/people/<id>              保存资料卡 {info?, bio?, avatarB64?}
    POST   /api/admin/people                   新建人物
    DELETE /api/admin/people/<id>              删除人物

静态服务:
    其余路径提供前台静态文件（前后端同端口），backend 目录与穿越路径一律 403

账号配置: backend/auth.json（首次启动自动生成默认账号 admin / admin123，请及时修改）
"""
import base64
import json
import os
import re
import secrets
import shutil
import threading
import time
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs, quote, unquote

PORT = 8080
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_FILE = os.path.join(BASE_DIR, "messages.json")
ADMIN_FILE = os.path.join(BASE_DIR, "admin.html")
AUTH_FILE = os.path.join(BASE_DIR, "auth.json")
FRONTEND_DATA = os.path.normpath(os.path.join(BASE_DIR, "..", "data"))
FRONTEND_ROOT = os.path.normpath(os.path.join(BASE_DIR, ".."))
PEOPLE_DIR = os.path.join(FRONTEND_DATA, "people")
PROFILES_FILE = os.path.join(FRONTEND_DATA, "profiles.json")

MIME_MAP = {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "application/javascript; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png",
    ".gif": "image/gif", ".svg": "image/svg+xml", ".webp": "image/webp",
    ".ico": "image/x-icon",
    ".md": "text/markdown; charset=utf-8",
    ".woff": "font/woff", ".woff2": "font/woff2", ".ttf": "font/ttf",
}

ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
_lock = threading.Lock()
SESSION_TTL = 24 * 3600  # 会话有效期 24 小时
SESSIONS = {}            # token -> 过期时间戳

# 限流：(类别, IP) -> [时间戳]，滑动窗口
RATE_LIMITS = {}
MAX_MESSAGES = 5000      # 留言总量上限，防撑爆存储


def _rate_ok(bucket, ip, limit, window):
    now = time.time()
    key = (bucket, ip)
    lst = [t for t in RATE_LIMITS.get(key, []) if now - t < window]
    if len(lst) >= limit:
        RATE_LIMITS[key] = lst
        return False
    lst.append(now)
    RATE_LIMITS[key] = lst
    return True

# 投稿
CONTRIB_DIR = os.path.join(BASE_DIR, "contributions")
CONTRIB_INDEX = os.path.join(BASE_DIR, "contributions.json")
MAX_UPLOAD = 200 * 1024 * 1024          # 文件本体上限 200MB
UPLOAD_OVERHEAD = 2 * 1024 * 1024       # multipart 编码额外开销容忍


def _ensure_auth_file():
    """首次运行生成默认账号文件。"""
    if not os.path.exists(AUTH_FILE):
        with open(AUTH_FILE, "w", encoding="utf-8") as f:
            json.dump({"username": "admin", "password": "admin123"}, f, ensure_ascii=False, indent=2)
        print("已生成默认账号 admin / admin123（配置文件 backend/auth.json，请尽快修改密码）")


def _load_auth():
    try:
        with open(AUTH_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {"username": "admin", "password": "admin123"}


def _new_session():
    token = secrets.token_hex(32)
    SESSIONS[token] = time.time() + SESSION_TTL
    return token


def _check_session(token):
    exp = SESSIONS.get(token)
    if exp is None:
        return False
    if time.time() > exp:
        SESSIONS.pop(token, None)
        return False
    return True


def _session_token(cookie_header):
    if not cookie_header:
        return None
    for part in cookie_header.split(";"):
        k, _, v = part.strip().partition("=")
        if k == "session":
            return v
    return None


# ================= 存储基础 =================

def _load_messages():
    if not os.path.exists(DATA_FILE):
        return []
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return []


def _save_messages(messages):
    tmp = DATA_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(messages, f, ensure_ascii=False, indent=2)
    os.replace(tmp, DATA_FILE)


def _load_profiles():
    try:
        with open(PROFILES_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return []


def _save_profiles(ids):
    with open(PROFILES_FILE, "w", encoding="utf-8") as f:
        json.dump(ids, f, ensure_ascii=False, indent=2)
        f.write("\n")


def _person_dir(pid):
    return os.path.join(PEOPLE_DIR, pid)


def _resources_dir(pid):
    return os.path.join(PEOPLE_DIR, pid, "resources")


# 原文件编辑：允许的扩展名与大小上限
EDITABLE_EXT = {".txt", ".md", ".json"}
MAX_TEXT_EDIT = 2 * 1024 * 1024


def _person_file_path(pid, rel):
    """校验人物目录下的相对路径，防止目录穿越。合法返回绝对路径，否则 None。"""
    rel = rel.replace("\\", "/").strip("/")
    if not rel or any(seg in ("", ".", "..") for seg in rel.split("/")):
        return None
    if os.path.splitext(rel)[1].lower() not in EDITABLE_EXT:
        return None
    pd = os.path.normpath(_person_dir(pid))
    fp = os.path.normpath(os.path.join(pd, rel))
    return fp if fp.startswith(pd + os.sep) else None


def _read_text(path):
    if not os.path.exists(path):
        return ""
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


# ================= 资料卡操作 =================

def _list_people():
    ids = _load_profiles()
    result = []
    for pid in ids:
        d = _person_dir(str(pid))
        result.append({
            "id": pid,
            "hasInfo": os.path.exists(os.path.join(d, "info.json")),
            "hasBio": os.path.exists(os.path.join(d, "bio.md")),
            "hasAvatar": os.path.exists(os.path.join(d, "avatar.jpg")),
        })
    if os.path.isdir(PEOPLE_DIR):
        for name in sorted(os.listdir(PEOPLE_DIR)):
            if name not in ids and os.path.isdir(_person_dir(name)):
                result.append({"id": name, "hasInfo": os.path.exists(os.path.join(_person_dir(name), "info.json")),
                               "hasBio": os.path.exists(os.path.join(_person_dir(name), "bio.md")),
                               "hasAvatar": os.path.exists(os.path.join(_person_dir(name), "avatar.jpg")),
                               "orphan": True})
    return result


def _get_person(pid):
    if not ID_RE.match(pid):
        return None
    d = _person_dir(pid)
    if not os.path.isdir(d):
        return None
    info = {}
    info_path = os.path.join(d, "info.json")
    if os.path.exists(info_path):
        try:
            with open(info_path, "r", encoding="utf-8") as f:
                info = json.load(f)
        except json.JSONDecodeError:
            info = {"_error": "info.json 解析失败"}
    return {"id": pid, "info": info, "bio": _read_text(os.path.join(d, "bio.md"))}


def _save_person_files(pid, info=None, bio=None, avatar_b64=None):
    d = _person_dir(pid)
    os.makedirs(d, exist_ok=True)
    if info is not None:
        info["id"] = pid
        with open(os.path.join(d, "info.json"), "w", encoding="utf-8") as f:
            json.dump(info, f, ensure_ascii=False, indent=2)
    if bio is not None:
        with open(os.path.join(d, "bio.md"), "w", encoding="utf-8") as f:
            f.write(bio)
    if avatar_b64:
        if "," in avatar_b64 and avatar_b64.strip().startswith("data:"):
            avatar_b64 = avatar_b64.split(",", 1)[1]
        try:
            img = base64.b64decode(avatar_b64, validate=False)
        except Exception:
            raise ValueError("头像数据不是合法的 base64")
        if len(img) > 3 * 1024 * 1024:
            raise ValueError("头像文件过大（最大 3MB）")
        with open(os.path.join(d, "avatar.jpg"), "wb") as f:
            f.write(img)


def _add_to_profiles(pid):
    ids = _load_profiles()
    if pid not in ids:
        pos = len(ids)
        if "example" in ids:
            pos = ids.index("example")
        ids.insert(pos, pid)
        _save_profiles(ids)


def _remove_from_profiles(pid):
    ids = _load_profiles()
    if pid in ids:
        ids.remove(pid)
        _save_profiles(ids)


def _read_admin_html():
    with open(ADMIN_FILE, "rb") as f:
        return f.read()


# ================= 投稿 =================

def _load_contribs():
    if not os.path.exists(CONTRIB_INDEX):
        return []
    try:
        with open(CONTRIB_INDEX, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return []


def _save_contribs(items):
    with open(CONTRIB_INDEX, "w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False, indent=2)


def _safe_filename(name):
    """保留原始可读字符，去掉路径与危险字符。"""
    name = os.path.basename(name or "").strip()
    name = re.sub(r'[\\/:*?"<>|\x00-\x1f]', "_", name)
    return name[:120] or "file"


def _parse_multipart(body, boundary):
    """解析 multipart/form-data，返回 {name: (filename或None, bytes)}"""
    parts = {}
    delim = b"--" + boundary
    for segment in body.split(delim):
        segment = segment.strip(b"\r\n")
        if not segment or segment == b"--":
            continue
        header_blob, _, payload = segment.partition(b"\r\n\r\n")
        if payload.endswith(b"\r\n"):
            payload = payload[:-2]
        headers = {}
        for line in header_blob.split(b"\r\n"):
            k, _, v = line.partition(b":")
            headers[k.strip().lower().decode("latin-1", "ignore")] = v.strip().decode("latin-1", "ignore")
        disp = headers.get("content-disposition", "")
        name_m = re.search(r'name="([^"]*)"', disp)
        if not name_m:
            continue
        file_m = re.search(r'filename="([^"]*)"', disp)
        parts[name_m.group(1)] = (file_m.group(1) if file_m else None, payload)
    return parts


class Handler(BaseHTTPRequestHandler):
    server_version = "AdminSystem/4.1"
    timeout = 30  # socket 读写超时，防 Slowloris 挂起连接

    # ---------- 基础 ----------
    def _cors(self):
        pass  # 同源部署，不再放行任意跨域（Access-Control-Allow-Origin: *）

    def _send(self, code, payload, set_cookie=None, clear_cookie=False):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        if set_cookie:
            self.send_header("Set-Cookie", f"session={set_cookie}; HttpOnly; Path=/; Max-Age={SESSION_TTL}; SameSite=Lax")
        if clear_cookie:
            self.send_header("Set-Cookie", "session=; HttpOnly; Path=/; Max-Age=0; SameSite=Lax")
        self._cors()
        self.end_headers()
        self.wfile.write(body)

    def _send_html(self, body):
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _serve_static(self, path):
        path = unquote(path)  # 浏览器会把中文路径编码成 %XX，需还原后再找文件
        rel = path.lstrip("/")
        if not rel or path.endswith("/"):
            rel = (rel + "/index.html").lstrip("/")
        file_path = os.path.normpath(os.path.join(FRONTEND_ROOT, rel))
        # 黑名单必须在 normpath 之后判断，否则 backend/../ 等形式会绕过拦截
        try:
            norm_rel = os.path.relpath(file_path, FRONTEND_ROOT)
        except ValueError:
            self._send(403, {"error": "forbidden"})
            return
        parts = norm_rel.split(os.sep)
        if norm_rel.startswith("..") or "backend" in parts or ".git" in parts:
            self._send(403, {"error": "forbidden"})
            return
        if os.path.isdir(file_path):
            file_path = os.path.join(file_path, "index.html")
        if not os.path.isfile(file_path):
            file_path = os.path.join(FRONTEND_ROOT, "404.html")
            if not os.path.isfile(file_path):
                self._send(404, {"error": "not found"})
                return
        ext = os.path.splitext(file_path)[1].lower()
        with open(file_path, "rb") as f:
            body = f.read()
        self.send_response(200 if not file_path.endswith("404.html") else 404)
        self.send_header("Content-Type", MIME_MAP.get(ext, "application/octet-stream"))
        if ext == ".svg" or (ext in (".html", ".htm") and parts[0] == "data"):
            # SVG 与上传的 HTML 内联脚本可执行，加 CSP sandbox 禁脚本（正常显示不受影响）
            self.send_header("Content-Security-Policy", "sandbox")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_json_body(self):
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length) if length else b"{}"
        try:
            return json.loads(raw.decode("utf-8")), None
        except (ValueError, UnicodeDecodeError):
            return None, "请求体不是合法 JSON"

    def _is_authed(self):
        return _check_session(_session_token(self.headers.get("Cookie")))

    def do_OPTIONS(self):
        self.send_response(204)
        self._cors()
        self.end_headers()

    # ---------- GET ----------
    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path

        if path == "/admin":
            self._send_html(_read_admin_html())
            return

        if path == "/api/auth/check":
            self._send(200, {"ok": self._is_authed()})
            return

        if path == "/api/health":
            self._send(200, {"status": "ok"})
            return

        if path == "/api/messages":
            profile = (parse_qs(parsed.query).get("profile") or [""])[0].strip()
            messages = _load_messages()
            if profile:
                messages = [m for m in messages if m.get("profile") == profile]
            messages.sort(key=lambda m: m.get("time", ""), reverse=True)
            self._send(200, {"total": len(messages), "messages": messages})
            return

        # ---- 以下管理接口均需登录 ----
        if path.startswith("/api/admin/"):
            if not self._is_authed():
                self._send(401, {"error": "未登录或会话已过期"})
                return

        if path == "/api/admin/stats":
            messages = _load_messages()
            by_profile = {}
            for m in messages:
                p = m.get("profile", "?")
                by_profile[p] = by_profile.get(p, 0) + 1
            today = datetime.now().strftime("%Y-%m-%d")
            self._send(200, {
                "total": len(messages),
                "profiles": len(by_profile),
                "today": sum(1 for m in messages if m.get("time", "").startswith(today)),
                "by_profile": by_profile,
            })
            return

        if path == "/api/admin/messages":
            qs = parse_qs(parsed.query)
            profile = (qs.get("profile") or [""])[0].strip()
            query = (qs.get("q") or [""])[0].strip().lower()
            messages = _load_messages()
            if profile:
                messages = [m for m in messages if m.get("profile") == profile]
            if query:
                messages = [m for m in messages
                            if query in m.get("name", "").lower()
                            or query in m.get("content", "").lower()
                            or query in m.get("profile", "").lower()]
            messages.sort(key=lambda m: m.get("time", ""), reverse=True)
            self._send(200, {"total": len(messages), "messages": messages})
            return

        if path == "/api/admin/people":
            self._send(200, {"people": _list_people()})
            return

        # 资源文件列表
        m = re.match(r"^/api/admin/people/([^/]+)/resources$", path)
        if m:
            pid = unquote(m.group(1))
            if not ID_RE.match(pid) or not os.path.isdir(_person_dir(pid)):
                self._send(404, {"error": "人物不存在"})
                return
            rd = _resources_dir(pid)
            files = []
            if os.path.isdir(rd):
                for name in sorted(os.listdir(rd)):
                    fp = os.path.join(rd, name)
                    if os.path.isfile(fp):
                        files.append({"name": name, "size": os.path.getsize(fp),
                                      "mtime": datetime.fromtimestamp(os.path.getmtime(fp)).strftime("%Y-%m-%d %H:%M")})
            self._send(200, {"files": files})
            return

        # 目录预览（递归列出人物目录下全部文件）
        m = re.match(r"^/api/admin/people/([^/]+)/files$", path)
        if m:
            pid = unquote(m.group(1))
            if not ID_RE.match(pid) or not os.path.isdir(_person_dir(pid)):
                self._send(404, {"error": "人物不存在"})
                return
            pd = _person_dir(pid)
            files = []
            for root, _dirs, names in os.walk(pd):
                for name in names:
                    fp = os.path.join(root, name)
                    rel = os.path.relpath(fp, pd).replace("\\", "/")
                    files.append({
                        "path": rel,
                        "size": os.path.getsize(fp),
                        "editable": os.path.splitext(name)[1].lower() in EDITABLE_EXT,
                        "mtime": datetime.fromtimestamp(os.path.getmtime(fp)).strftime("%Y-%m-%d %H:%M"),
                    })
            files.sort(key=lambda f: f["path"])
            self._send(200, {"files": files})
            return

        # 读取原文件内容（仅 txt/md/json）
        m = re.match(r"^/api/admin/people/([^/]+)/file/(.+)$", path)
        if m:
            pid = unquote(m.group(1))
            fp = _person_file_path(pid, unquote(m.group(2)))
            if not fp or not os.path.isfile(fp):
                self._send(404, {"error": "文件不存在或不可编辑"})
                return
            if os.path.getsize(fp) > MAX_TEXT_EDIT:
                self._send(413, {"error": "文件过大，不支持在线编辑（上限 2MB）"})
                return
            with open(fp, "r", encoding="utf-8") as f:
                content = f.read()
            self._send(200, {"path": unquote(m.group(2)).replace("\\", "/").strip("/"), "content": content})
            return

        m = re.match(r"^/api/admin/people/([^/]+)$", path)
        if m:
            person = _get_person(m.group(1))
            if person is None:
                self._send(404, {"error": "人物不存在"})
            else:
                self._send(200, person)
            return

        # ---- 投稿管理 ----
        if path == "/api/admin/contributions":
            items = sorted(_load_contribs(), key=lambda x: x.get("id", ""), reverse=True)
            total = sum(i.get("size", 0) for i in items)
            self._send(200, {"total": len(items), "totalSize": total, "items": items})
            return

        m = re.match(r"^/api/admin/contributions/([^/]+)/file$", path)
        if m:
            item = next((i for i in _load_contribs() if i.get("id") == m.group(1)), None)
            fp = os.path.join(CONTRIB_DIR, item["store"]) if item else None
            if not item or not os.path.isfile(fp):
                self._send(404, {"error": "投稿文件不存在"})
                return
            size = os.path.getsize(fp)
            self.send_response(200)
            self.send_header("Content-Type", "application/octet-stream")
            self.send_header("Content-Length", str(size))
            self.send_header("Content-Disposition",
                             "attachment; filename*=UTF-8''" + quote(item.get("orig", "file")))
            self.end_headers()
            with open(fp, "rb") as f:
                shutil.copyfileobj(f, self.wfile)
            return

        self._serve_static(path)

    # ---------- POST ----------
    def do_POST(self):
        path = urlparse(self.path).path

        if path == "/api/login":
            if not _rate_ok("login", self.client_address[0], 5, 300):
                self._send(429, {"error": "尝试过于频繁，请 5 分钟后再试"})
                return
            data, err = self._read_json_body()
            if err:
                self._send(400, {"error": err})
                return
            auth = _load_auth()
            if (str(data.get("username", "")).strip() == auth.get("username")
                    and str(data.get("password", "")) == auth.get("password")):
                self._send(200, {"ok": True}, set_cookie=_new_session())
            else:
                time.sleep(0.4)  # 简单防爆破
                self._send(401, {"error": "用户名或密码错误"})
            return

        if path == "/api/logout":
            token = _session_token(self.headers.get("Cookie"))
            SESSIONS.pop(token, None)
            self._send(200, {"ok": True}, clear_cookie=True)
            return

        if path == "/api/messages":
            if not _rate_ok("msg", self.client_address[0], 5, 60):
                self._send(429, {"error": "发送太频繁，休息一下再留言吧"})
                return
            data, err = self._read_json_body()
            if err:
                self._send(400, {"error": err})
                return
            profile = str(data.get("profile", "")).strip()
            name = str(data.get("name", "")).strip() or "匿名"
            content = str(data.get("content", "")).strip()
            if not profile or len(profile) > 64:
                self._send(400, {"error": "缺少或非法的 profile 字段"})
                return
            if not content:
                self._send(400, {"error": "留言内容不能为空"})
                return
            if len(name) > 32:
                self._send(400, {"error": "昵称过长（最多 32 字）"})
                return
            if len(content) > 500:
                self._send(400, {"error": "留言内容过长（最多 500 字）"})
                return
            message = {
                "id": datetime.now().strftime("%Y%m%d%H%M%S%f"),
                "profile": profile,
                "name": name,
                "content": content,
                "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            }
            with _lock:
                messages = _load_messages()
                if len(messages) >= MAX_MESSAGES:
                    self._send(429, {"error": "留言已达总量上限，请联系管理员清理"})
                    return
                messages.append(message)
                _save_messages(messages)
            self._send(201, {"ok": True, "message": message})
            return

        # ---- 投稿提交（公开接口，≤200MB，任意类型） ----
        if path == "/api/contribute":
            ctype = self.headers.get("Content-Type", "")
            m = re.search(r'boundary=([^;]+)', ctype)
            if "multipart/form-data" not in ctype or not m:
                self._send(400, {"error": "需要 multipart/form-data 上传"})
                return
            declared = int(self.headers.get("Content-Length", 0) or 0)
            if declared > MAX_UPLOAD + UPLOAD_OVERHEAD:
                self._send(413, {"error": "文件过大，投稿上限 200MB"})
                return
            body = self.rfile.read(declared) if declared else b""
            if not body:
                self._send(400, {"error": "请求体为空"})
                return
            try:
                parts = _parse_multipart(body, m.group(1).strip('"').encode("latin-1"))
            except Exception:
                self._send(400, {"error": "上传数据解析失败"})
                return
            filename, payload = parts.get("file", (None, b""))
            if not filename:
                self._send(400, {"error": "缺少文件字段 file"})
                return
            try:  # multipart 头按 latin-1 解码，还原客户端发来的 UTF-8 文件名
                filename = filename.encode("latin-1").decode("utf-8")
            except (UnicodeEncodeError, UnicodeDecodeError, AttributeError):
                pass
            if len(payload) > MAX_UPLOAD:
                self._send(413, {"error": "文件过大，投稿上限 200MB"})
                return
            if not payload:
                self._send(400, {"error": "不能上传空文件"})
                return
            submitter = parts.get("name", (None, b""))[1].decode("utf-8", "ignore").strip()[:32] or "匿名"
            note = parts.get("note", (None, b""))[1].decode("utf-8", "ignore").strip()[:200]
            cid = datetime.now().strftime("%Y%m%d%H%M%S") + secrets.token_hex(4)
            orig = _safe_filename(filename)
            os.makedirs(CONTRIB_DIR, exist_ok=True)
            store_name = f"{cid}_{orig}"
            with open(os.path.join(CONTRIB_DIR, store_name), "wb") as f:
                f.write(payload)
            record = {
                "id": cid,
                "orig": orig,
                "store": store_name,
                "size": len(payload),
                "name": submitter,
                "note": note,
                "ip": self.client_address[0],
                "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            }
            with _lock:
                items = _load_contribs()
                items.append(record)
                _save_contribs(items)
            self._send(201, {"ok": True, "id": cid, "file": orig, "size": len(payload)})
            return

        # ---- 管理接口鉴权 ----
        if path.startswith("/api/admin/"):
            if not self._is_authed():
                self._send(401, {"error": "未登录或会话已过期"})
                return

        if path == "/api/admin/clear":
            data, err = self._read_json_body()
            if err:
                self._send(400, {"error": err})
                return
            with _lock:
                if data.get("all"):
                    _save_messages([])
                    self._send(200, {"ok": True, "removed": "all"})
                    return
                profile = str(data.get("profile", "")).strip()
                if not profile:
                    self._send(400, {"error": "需要 profile 字段或 all: true"})
                    return
                messages = _load_messages()
                kept = [m for m in messages if m.get("profile") != profile]
                _save_messages(kept)
            self._send(200, {"ok": True, "removed": len(messages) - len(kept)})
            return

        if path == "/api/admin/people":
            data, err = self._read_json_body()
            if err:
                self._send(400, {"error": err})
                return
            pid = str(data.get("id", "")).strip()
            if not ID_RE.match(pid):
                self._send(400, {"error": "ID 只能包含字母、数字、下划线、连字符（1-64 位）"})
                return
            with _lock:
                if os.path.isdir(_person_dir(pid)):
                    self._send(409, {"error": f"人物 {pid} 已存在"})
                    return
                try:
                    _save_person_files(pid, info=data.get("info", {"id": pid, "name": pid}),
                                       bio=data.get("bio"), avatar_b64=data.get("avatarB64"))
                    _add_to_profiles(pid)
                except ValueError as e:
                    self._send(400, {"error": str(e)})
                    return
            self._send(201, {"ok": True, "id": pid})
            return

        # ---- 资源文件上传（存到 data/people/<id>/resources/，目录不存在自动创建） ----
        m = re.match(r"^/api/admin/people/([^/]+)/resources$", path)
        if m:
            pid = unquote(m.group(1))
            if not ID_RE.match(pid) or not os.path.isdir(_person_dir(pid)):
                self._send(404, {"error": "人物不存在"})
                return
            ctype = self.headers.get("Content-Type", "")
            bm = re.search(r'boundary=([^;]+)', ctype)
            if "multipart/form-data" not in ctype or not bm:
                self._send(400, {"error": "需要 multipart/form-data 上传"})
                return
            declared = int(self.headers.get("Content-Length", 0) or 0)
            if declared > MAX_UPLOAD + UPLOAD_OVERHEAD:
                self._send(413, {"error": "文件过大，上限 200MB"})
                return
            body = self.rfile.read(declared) if declared else b""
            try:
                parts = _parse_multipart(body, bm.group(1).strip('"').encode("latin-1"))
            except Exception:
                self._send(400, {"error": "上传数据解析失败"})
                return
            filename, payload = parts.get("file", (None, b""))
            if not filename:
                self._send(400, {"error": "缺少文件字段 file"})
                return
            try:  # 还原 UTF-8 文件名
                filename = filename.encode("latin-1").decode("utf-8")
            except (UnicodeEncodeError, UnicodeDecodeError, AttributeError):
                pass
            if len(payload) > MAX_UPLOAD:
                self._send(413, {"error": "文件过大，上限 200MB"})
                return
            if not payload:
                self._send(400, {"error": "不能上传空文件"})
                return
            orig = _safe_filename(filename)
            rd = _resources_dir(pid)
            os.makedirs(rd, exist_ok=True)
            store = orig
            if os.path.exists(os.path.join(rd, store)):  # 同名不覆盖，加时间戳
                stem, ext = os.path.splitext(orig)
                store = f"{stem}_{datetime.now().strftime('%H%M%S')}{ext}"
            with open(os.path.join(rd, store), "wb") as f:
                f.write(payload)
            self._send(201, {"ok": True, "name": store, "size": len(payload),
                             "path": f"/data/people/{pid}/resources/{quote(store)}"})
            return

        self._send(404, {"error": "not found"})

    # ---------- PUT ----------
    def do_PUT(self):
        path = urlparse(self.path).path
        if path.startswith("/api/admin/") and not self._is_authed():
            self._send(401, {"error": "未登录或会话已过期"})
            return

        # 保存原文件（仅 txt/md/json）
        m = re.match(r"^/api/admin/people/([^/]+)/file/(.+)$", path)
        if m:
            pid = unquote(m.group(1))
            fp = _person_file_path(pid, unquote(m.group(2)))
            if not fp:
                self._send(400, {"error": "路径非法或扩展名不可编辑（仅支持 txt/md/json）"})
                return
            data, err = self._read_json_body()
            if err:
                self._send(400, {"error": err})
                return
            content = data.get("content", "")
            if not isinstance(content, str):
                self._send(400, {"error": "content 必须是字符串"})
                return
            encoded = content.encode("utf-8")
            if len(encoded) > MAX_TEXT_EDIT:
                self._send(413, {"error": "内容过大，上限 2MB"})
                return
            if fp.lower().endswith(".json"):
                try:
                    json.loads(content)
                except (ValueError, UnicodeDecodeError) as e:
                    self._send(400, {"error": f"JSON 校验失败，未保存：{e}"})
                    return
            os.makedirs(os.path.dirname(fp), exist_ok=True)
            with open(fp, "w", encoding="utf-8", newline="") as f:
                f.write(content)
            self._send(200, {"ok": True, "path": unquote(m.group(2)).replace("\\", "/").strip("/")})
            return

        m = re.match(r"^/api/admin/people/([^/]+)$", path)
        if not m:
            self._send(404, {"error": "not found"})
            return
        pid = m.group(1)
        if not ID_RE.match(pid):
            self._send(400, {"error": "非法的人物 ID"})
            return
        data, err = self._read_json_body()
        if err:
            self._send(400, {"error": err})
            return
        with _lock:
            if not os.path.isdir(_person_dir(pid)):
                self._send(404, {"error": "人物不存在"})
                return
            try:
                _save_person_files(pid, info=data.get("info"), bio=data.get("bio"),
                                   avatar_b64=data.get("avatarB64"))
            except ValueError as e:
                self._send(400, {"error": str(e)})
                return
        self._send(200, {"ok": True, "id": pid})

    # ---------- DELETE ----------
    def do_DELETE(self):
        path = urlparse(self.path).path
        if path.startswith("/api/admin/") and not self._is_authed():
            self._send(401, {"error": "未登录或会话已过期"})
            return

        if path == "/api/admin/messages":
            msg_id = (parse_qs(urlparse(self.path).query).get("id") or [""])[0].strip()
            if not msg_id:
                self._send(400, {"error": "缺少 id 参数"})
                return
            with _lock:
                messages = _load_messages()
                kept = [m for m in messages if m.get("id") != msg_id]
                if len(kept) == len(messages):
                    self._send(404, {"error": "留言不存在"})
                    return
                _save_messages(kept)
            self._send(200, {"ok": True})
            return

        m = re.match(r"^/api/admin/people/([^/]+)$", path)
        if m:
            pid = m.group(1)
            if not ID_RE.match(pid):
                self._send(400, {"error": "非法的人物 ID"})
                return
            with _lock:
                d = _person_dir(pid)
                if not os.path.isdir(d):
                    self._send(404, {"error": "人物不存在"})
                    return
                shutil.rmtree(d)
                _remove_from_profiles(pid)
            self._send(200, {"ok": True})
            return

        m = re.match(r"^/api/admin/contributions/([^/]+)$", path)
        if m:
            with _lock:
                items = _load_contribs()
                item = next((i for i in items if i.get("id") == m.group(1)), None)
                if not item:
                    self._send(404, {"error": "投稿不存在"})
                    return
                fp = os.path.join(CONTRIB_DIR, item["store"])
                if os.path.isfile(fp):
                    os.remove(fp)
                _save_contribs([i for i in items if i.get("id") != item["id"]])
            self._send(200, {"ok": True})
            return

        # 删除资料资源文件
        m = re.match(r"^/api/admin/people/([^/]+)/resources/(.+)$", path)
        if m:
            pid = unquote(m.group(1))
            name = _safe_filename(unquote(m.group(2)))
            if not ID_RE.match(pid):
                self._send(400, {"error": "非法的人物 ID"})
                return
            rd = os.path.normpath(_resources_dir(pid))
            fp = os.path.normpath(os.path.join(rd, name))
            if not fp.startswith(rd) or not os.path.isfile(fp):
                self._send(404, {"error": "文件不存在"})
                return
            os.remove(fp)
            self._send(200, {"ok": True})
            return

        self._send(404, {"error": "not found"})

    def log_message(self, fmt, *args):
        pass


if __name__ == "__main__":
    _ensure_auth_file()
    server = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)  # 监听所有网卡，允许手机等局域网设备访问
    print(f"星语铭后端管理系统已启动")
    print(f"  站点首页: http://127.0.0.1:{PORT}/")
    print(f"  管理后台: http://127.0.0.1:{PORT}/admin （需登录）")
    print(f"  资料卡目录: {PEOPLE_DIR}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.shutdown()
