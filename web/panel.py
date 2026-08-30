import asyncio
import secrets
from pathlib import Path
from urllib.parse import urlencode

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
import uvicorn

from cogs import common


class WebPanel:
    def __init__(self, bot) -> None:
        self.bot = bot
        self.port = 8080
        self.mod_role_id = common.mod_role_id
        self.oauth_authorize_url = "https://discord.com/api/oauth2/authorize"
        self.oauth_token_url = "https://discord.com/api/oauth2/token"
        self.oauth_user_url = "https://discord.com/api/users/@me"
        self.oauth_scopes = "identify"
        self.oauth_callback_path = "/auth/callback"
        self.identity_bot_owner = "總管理員"
        self.identity_mod = "MOD"
        self.identity_member = "一般成員"
        self.package_dir = Path(__file__).resolve().parent
        self.templates = Jinja2Templates(directory=str(self.package_dir / "templates"))
        self.secret_config = common.mongo_storage.read_secret_config()
        self.client_id = str(self.secret_config.get("DISCORD_CLIENT_ID") or "")
        self.client_secret = str(self.secret_config.get("DISCORD_CLIENT_SECRET") or "")
        self.session_secret = str(self.secret_config.get("WEB_SESSION_SECRET") or secrets.token_hex(32))
        self.public_base_url = ""
        if common.mongo_storage.get_runtime_env() == "PRD":
            self.public_base_url = str(self.secret_config.get("WEB_PUBLIC_BASE_URL") or "").rstrip("/")
        self.session_https_only = self.public_base_url.startswith("https://")
        self.app = self.create_app()

    def create_app(self) -> FastAPI:
        """
        建立 FastAPI 應用與路由。

        Returns:
            app (FastAPI): "FastAPI()"
        """
        app = FastAPI(title="偽造妹妹伺服器互動面板")
        app.add_middleware(
            SessionMiddleware,
            secret_key=self.session_secret,
            same_site="lax",
            https_only=self.session_https_only,
        )
        app.mount("/static", StaticFiles(directory=str(self.package_dir / "static")), name="static")
        app.state.web_panel = self
        app.add_api_route("/", self.index, methods=["GET"], response_class=HTMLResponse, name="index")
        app.add_api_route("/auth/login", self.auth_login, methods=["GET"], name="auth_login")
        app.add_api_route("/auth/callback", self.auth_callback, methods=["GET"], name="auth_callback")
        app.add_api_route("/auth/logout", self.auth_logout, methods=["GET"], name="auth_logout")
        app.add_api_route("/panel", self.panel, methods=["GET"], response_class=HTMLResponse, name="panel")
        app.add_api_route("/auction", self.auction_page, methods=["GET"], response_class=HTMLResponse, name="auction")
        app.add_api_route("/api/auction/list", self.auction_list, methods=["GET"], name="auction_list")
        app.add_api_route("/api/auction/bid", self.auction_bid, methods=["POST"], name="auction_bid")
        return app

    async def index(self, request: Request):
        """
        首頁：已登入導向面板，否則顯示登入頁。

        Args:
            request (Request): FastAPI request

        Returns:
            response: HTML 或導向
        """
        if request.session.get("user_id"):
            return RedirectResponse(url="/panel", status_code=302)
        return self.templates.TemplateResponse(
            request,
            "login.html",
            {"title": "偽造妹妹伺服器互動面板", "error": None},
        )

    async def auth_login(self, request: Request):
        """
        導向 Discord OAuth 授權頁。

        Args:
            request (Request): FastAPI request

        Returns:
            response: 導向或錯誤頁
        """
        if not self.client_id or not self.client_secret:
            return self.templates.TemplateResponse(
                request,
                "login.html",
                {
                    "title": "偽造妹妹伺服器互動面板",
                    "error": "尚未設定 Discord OAuth（請檢查 secret.json 的 DISCORD_CLIENT_ID / DISCORD_CLIENT_SECRET）。",
                },
                status_code=500,
            )
        state = secrets.token_urlsafe(16)
        redirect_uri = self.build_redirect_uri(request)
        request.session["oauth_state"] = state
        request.session["oauth_redirect_uri"] = redirect_uri
        query = urlencode(
            {
                "client_id": self.client_id,
                "response_type": "code",
                "redirect_uri": redirect_uri,
                "scope": self.oauth_scopes,
                "state": state,
            }
        )
        return RedirectResponse(url=f"{self.oauth_authorize_url}?{query}", status_code=302)

    async def auth_callback(self, request: Request, code: str | None = None, state: str | None = None, error: str | None = None):
        """
        處理 Discord OAuth callback。

        Args:
            request (Request): FastAPI request
            code (str | None): "oauth_code"
            state (str | None): "csrf_state"
            error (str | None): "access_denied"

        Returns:
            response: 導向面板或錯誤頁
        """
        if error:
            return self.templates.TemplateResponse(
                request,
                "login.html",
                {"title": "偽造妹妹伺服器互動面板", "error": f"Discord 登入失敗：{error}"},
                status_code=400,
            )
        expected_state = request.session.pop("oauth_state", None)
        redirect_uri = request.session.pop("oauth_redirect_uri", None) or self.build_redirect_uri(request)
        if not code or not state or state != expected_state:
            return self.templates.TemplateResponse(
                request,
                "login.html",
                {"title": "偽造妹妹伺服器互動面板", "error": "登入驗證失敗，請重新嘗試。"},
                status_code=400,
            )
        user_info = await self.exchange_code_for_user(code, redirect_uri)
        if user_info is None:
            return self.templates.TemplateResponse(
                request,
                "login.html",
                {"title": "偽造妹妹伺服器互動面板", "error": "無法取得 Discord 使用者資料。"},
                status_code=400,
            )
        request.session["user_id"] = str(user_info["id"])
        request.session["username"] = user_info.get("global_name") or user_info.get("username") or "未知使用者"
        request.session["avatar"] = self.build_avatar_url(user_info)
        next_path = self.safe_next_path(request.session.pop("login_next", None))
        return RedirectResponse(url=next_path, status_code=302)

    async def auth_logout(self, request: Request):
        """
        清除登入 session。

        Args:
            request (Request): FastAPI request

        Returns:
            response: 導向首頁
        """
        request.session.clear()
        return RedirectResponse(url="/", status_code=302)

    async def panel(self, request: Request):
        """
        互動面板主頁：檢查群籍後顯示等級／蛋糕／身份。

        Args:
            request (Request): FastAPI request

        Returns:
            response: 面板、拒絕頁或導向登入
        """
        reject, context = await self.load_panel_context(request, "/panel")
        if reject is not None:
            return reject
        context["title"] = "偽造妹妹伺服器互動面板"
        context["active_nav"] = "home"
        return self.templates.TemplateResponse(request, "panel.html", context)

    async def auction_page(self, request: Request):
        """
        拍賣所列表頁。

        Args:
            request (Request): FastAPI request

        Returns:
            response: 拍賣所、拒絕頁或導向登入
        """
        reject, context = await self.load_panel_context(request, "/auction")
        if reject is not None:
            return reject
        context["title"] = "拍賣所"
        context["active_nav"] = "auction"
        return self.templates.TemplateResponse(request, "auction.html", context)

    async def auction_list(self, request: Request):
        """
        回傳進行中／已結束競標列表。

        Args:
            request (Request): FastAPI request

        Returns:
            response (JSONResponse): "{'active': [], 'ended': []}"
        """
        reject, context = await self.load_panel_context(request, "/auction")
        if reject is not None:
            if isinstance(reject, RedirectResponse):
                return JSONResponse({"ok": False, "error": "請先登入"}, status_code=401)
            return JSONResponse({"ok": False, "error": "你不在偽造妹妹伺服器中"}, status_code=403)
        house = getattr(self.bot, "auction_house", None)
        viewer_id = int(context["user_id"])
        active = house.list_active_public(viewer_id) if house is not None else []
        ended = await house.list_ended_public() if house is not None else []
        return JSONResponse(
            {
                "cake": context["cake"],
                "active": active,
                "ended": ended,
            }
        )

    async def auction_bid(self, request: Request):
        """
        將網頁出價放入佇列並回傳處理結果。

        Args:
            request (Request): FastAPI request

        Returns:
            response (JSONResponse): "{'ok': True, 'price': 65000}"
        """
        reject, context = await self.load_panel_context(request, "/auction")
        if reject is not None:
            if isinstance(reject, RedirectResponse):
                return JSONResponse({"ok": False, "error": "請先登入"}, status_code=401)
            return JSONResponse({"ok": False, "error": "你不在偽造妹妹伺服器中"}, status_code=403)
        house = getattr(self.bot, "auction_house", None)
        if house is None:
            return JSONResponse({"ok": False, "error": "拍賣所尚未就緒"}, status_code=503)
        try:
            body = await request.json()
            auction_id = int(body.get("auction_id"))
            expected_price = int(body.get("expected_price"))
        except Exception:
            return JSONResponse({"ok": False, "error": "出價資料格式錯誤"}, status_code=400)
        if auction_id < 1 or expected_price < 1:
            return JSONResponse({"ok": False, "error": "出價資料格式錯誤"}, status_code=400)
        display_name = house.resolve_name(int(context["user_id"])) or context["username"]
        result = await house.enqueue_bid(auction_id, int(context["user_id"]), expected_price, display_name)
        user_data = await common.mongo_storage.ensure_user_document(context["user_id"])
        result["cake"] = user_data.get("cake", 0)
        return JSONResponse(result)

    async def load_panel_context(self, request: Request, next_path: str):
        """
        確認已登入且在群內，並組出共用頁面資料。

        Args:
            request (Request): FastAPI request
            next_path (str): "/auction"

        Returns:
            result (tuple): "(None, {'user_id': '4108', 'cake': 0})"
        """
        user_id = request.session.get("user_id")
        if not user_id:
            request.session["login_next"] = next_path
            return RedirectResponse(url="/", status_code=302), None

        guild = self.bot.get_guild(common.fake_sister_server_id)
        member = guild.get_member(int(user_id)) if guild is not None else None
        if member is None:
            denied = self.templates.TemplateResponse(
                request,
                "denied.html",
                {
                    "title": "拒絕訪問",
                    "username": request.session.get("username"),
                    "avatar": request.session.get("avatar"),
                    "message": "你不在偽造妹妹伺服器中，無法使用互動面板。",
                },
                status_code=403,
            )
            return denied, None

        user_data = await common.mongo_storage.ensure_user_document(user_id)
        context = {
            "user_id": user_id,
            "username": request.session.get("username"),
            "avatar": request.session.get("avatar"),
            "level": user_data.get("level", 1),
            "cake": user_data.get("cake", 0),
            "identity": self.resolve_identity(member),
        }
        return None, context

    def safe_next_path(self, path: str | None, default: str = "/panel") -> str:
        """
        過濾登入後導向路徑，避免開放重新導向。

        Args:
            path (str | None): "/auction"
            default (str): "/panel"

        Returns:
            next_path (str): "/auction"
        """
        if not path or not path.startswith("/") or path.startswith("//"):
            return default
        return path

    def build_redirect_uri(self, request: Request) -> str:
        """
        組出 OAuth callback。正式環境優先用 WEB_PUBLIC_BASE_URL（避免反向代理造成 http/https 不符）。

        Args:
            request (Request): FastAPI request

        Returns:
            redirect_uri (str): "https://fake-sister.ani20168.com/auth/callback"
        """
        if self.public_base_url:
            return f"{self.public_base_url}{self.oauth_callback_path}"
        return str(request.url_for("auth_callback"))

    def build_avatar_url(self, user_info: dict) -> str:
        """
        組出 Discord 頭像網址。

        Args:
            user_info (dict): "{'id': '4108', 'avatar': 'abc'}"

        Returns:
            avatar_url (str): "https://cdn.discordapp.com/avatars/..."
        """
        user_id = user_info.get("id")
        avatar_hash = user_info.get("avatar")
        if user_id and avatar_hash:
            return f"https://cdn.discordapp.com/avatars/{user_id}/{avatar_hash}.png?size=64"
        discriminator = user_info.get("discriminator") or "0"
        try:
            index = int(discriminator) % 5
        except ValueError:
            index = 0
        return f"https://cdn.discordapp.com/embed/avatars/{index}.png"

    def resolve_identity(self, member) -> str:
        """
        依 bot_owner / MOD 身分組判定顯示身份。

        Args:
            member: Discord guild member

        Returns:
            identity (str): "總管理員"
        """
        if member.id == common.bot_owner_id:
            return self.identity_bot_owner
        if any(role.id == self.mod_role_id for role in member.roles):
            return self.identity_mod
        return self.identity_member

    async def exchange_code_for_user(self, code: str, redirect_uri: str) -> dict | None:
        """
        用授權碼交換 access token 並取得使用者資料。

        Args:
            code (str): "oauth_authorization_code"
            redirect_uri (str): "http://localhost:8080/auth/callback"

        Returns:
            user_info (dict | None): "{'id': '4108', 'username': 'ani'}"
        """
        session = self.bot.session
        token_data = {
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_uri,
        }
        headers = {"Content-Type": "application/x-www-form-urlencoded"}
        async with session.post(self.oauth_token_url, data=token_data, headers=headers) as token_response:
            if token_response.status != 200:
                return None
            token_payload = await token_response.json()
        access_token = token_payload.get("access_token")
        if not access_token:
            return None
        user_headers = {"Authorization": f"Bearer {access_token}"}
        async with session.get(self.oauth_user_url, headers=user_headers) as user_response:
            if user_response.status != 200:
                return None
            return await user_response.json()

    async def start(self) -> None:
        """
        在現有 event loop 啟動 uvicorn。
        """
        config = uvicorn.Config(
            self.app,
            host="0.0.0.0",
            port=self.port,
            log_level="info",
            proxy_headers=True,
            forwarded_allow_ips="*",
        )
        server = uvicorn.Server(config)
        await server.serve()


def start_web_panel(bot) -> asyncio.Task:
    """
    建立 WebPanel 並以背景 task 啟動。

    Args:
        bot: Discord bot 實例

    Returns:
        task (asyncio.Task): "Task(...)"
    """
    panel = WebPanel(bot)
    bot.web_panel = panel
    return asyncio.create_task(panel.start())
