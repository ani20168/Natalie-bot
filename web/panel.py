import asyncio
import secrets
from pathlib import Path
from urllib.parse import urlencode

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
import uvicorn

from cogs import common


class AuctionSocketClient:
    """一條拍賣所 WebSocket 連線。"""

    def __init__(self, websocket: WebSocket, user_id: str):
        self.websocket = websocket
        self.user_id = user_id


class AuctionSocketHub:
    """把拍賣所狀態推給所有已連線的網頁。"""

    def __init__(self, panel: "WebPanel"):
        self.panel = panel
        self.broadcast_seconds = 1
        self.clients: list[AuctionSocketClient] = []
        self.broadcast_lock = asyncio.Lock()
        self.tick_task: asyncio.Task | None = None

    def start_tick(self):
        """開始每秒推送。"""
        if self.tick_task is None or self.tick_task.done():
            self.tick_task = asyncio.create_task(self.run_tick())

    def stop_tick(self):
        """停止每秒推送。"""
        if self.tick_task is None:
            return
        self.tick_task.cancel()
        self.tick_task = None

    def add_client(self, client: AuctionSocketClient):
        """
        登記連線。

        Args:
            client (AuctionSocketClient): WebSocket 連線
        """
        self.clients.append(client)

    def remove_client(self, client: AuctionSocketClient):
        """
        移除連線。

        Args:
            client (AuctionSocketClient): WebSocket 連線
        """
        if client in self.clients:
            self.clients.remove(client)

    async def run_tick(self):
        """有進行中的競標時，每秒向網頁推送最新狀態。"""
        while True:
            await asyncio.sleep(self.broadcast_seconds)
            if not self.clients:
                continue
            house = getattr(self.panel.bot, "auction_house", None)
            if house is None or not house.active:
                continue
            await self.broadcast()

    async def send_to(self, client: AuctionSocketClient):
        """
        推送一份快照給單一連線。

        Args:
            client (AuctionSocketClient): WebSocket 連線
        """
        payload = await self.build_snapshot(client.user_id)
        await client.websocket.send_json(payload)

    async def broadcast(self):
        """向所有連線推送各自的拍賣所快照。"""
        async with self.broadcast_lock:
            if not self.clients:
                return
            house = getattr(self.panel.bot, "auction_house", None)
            ended = await house.list_ended_public() if house is not None else []
            stale: list[AuctionSocketClient] = []
            for client in list(self.clients):
                try:
                    payload = await self.build_snapshot(client.user_id, ended)
                    await client.websocket.send_json(payload)
                except Exception:
                    stale.append(client)
            for client in stale:
                self.remove_client(client)

    async def build_snapshot(self, user_id: str, ended: list[dict] | None = None) -> dict:
        """
        組出該使用者看到的拍賣所資料。

        Args:
            user_id (str): "410847926236086272"
            ended (list | None): "[{'id': 1}]"

        Returns:
            payload (dict): "{'cake': 0, 'active': [], 'ended': []}"
        """
        house = getattr(self.panel.bot, "auction_house", None)
        viewer_id = int(user_id)
        if ended is None:
            ended = await house.list_ended_public() if house is not None else []
        user_data = await common.mongo_storage.get_user(user_id)
        cake = user_data.get("cake", 0) if isinstance(user_data, dict) else 0
        return {
            "cake": cake,
            "active": house.list_active_public(viewer_id) if house is not None else [],
            "ended": ended,
            "permissions": await self.panel.permissions_for_user(user_id),
        }


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
        self.permission_role_owner = "owner"
        self.permission_role_mod = "mod"
        self.permission_role_member = "member"
        self.permission_role_keys = [self.permission_role_owner, self.permission_role_mod, self.permission_role_member]
        self.permission_role_labels = {
            self.permission_role_owner: self.identity_bot_owner,
            self.permission_role_mod: self.identity_mod,
            self.permission_role_member: self.identity_member,
        }
        self.permission_auction_cancel = "auction_cancel"
        self.permission_auction_delete = "auction_delete"
        self.permission_shop_visit = "shop_visit"
        self.permission_shop_edit_description = "shop_edit_description"
        self.permission_shop_admin = "shop_admin"
        self.permission_catalog = [
            {
                "key": "auction",
                "label": "拍賣所",
                "permissions": [
                    {
                        "key": self.permission_auction_cancel,
                        "label": "撤銷競標",
                        "description": "結束這個競標，會變成已結束，但是全部人的蛋糕會歸還",
                    },
                    {
                        "key": self.permission_auction_delete,
                        "label": "刪除紀錄",
                        "description": "從網頁已結束列表移除這筆競標，Discord 訊息不會更動，競標 ID 照常往上累計",
                    },
                ],
            },
            {
                "key": "shop",
                "label": "商店",
                "permissions": [
                    {
                        "key": self.permission_shop_visit,
                        "label": "造訪商店",
                        "description": "側邊選單會顯示商店，也可以進入商店頁",
                    },
                    {
                        "key": self.permission_shop_edit_description,
                        "label": "編輯商品描述",
                        "description": "可以修改商店商品的描述文字",
                    },
                    {
                        "key": self.permission_shop_admin,
                        "label": "後台管理",
                        "description": "可以進入商店後台，調整手續費等設定",
                    },
                ],
            },
        ]
        self.permission_document_id = "grants"
        self.permission_grants_cache: dict | None = None
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
        self.auction_hub = AuctionSocketHub(self)
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
        app.add_api_route("/api/auction/cancel", self.auction_cancel, methods=["POST"], name="auction_cancel")
        app.add_api_route("/api/auction/delete", self.auction_delete, methods=["POST"], name="auction_delete")
        app.add_api_route("/permissions", self.permissions_page, methods=["GET"], response_class=HTMLResponse, name="permissions")
        app.add_api_route("/api/permissions", self.permissions_update, methods=["POST"], name="permissions_update")
        app.add_api_route("/shop", self.shop_page, methods=["GET"], response_class=HTMLResponse, name="shop")
        app.add_api_route("/shop/history", self.shop_history_page, methods=["GET"], response_class=HTMLResponse, name="shop_history")
        app.add_api_route("/shop/admin", self.shop_admin_page, methods=["GET"], response_class=HTMLResponse, name="shop_admin")
        app.add_api_route("/api/shop/catalog", self.shop_catalog, methods=["GET"], name="shop_catalog")
        app.add_api_route("/api/shop/product", self.shop_product, methods=["GET"], name="shop_product")
        app.add_api_route("/api/shop/buy-order", self.shop_buy_order, methods=["POST"], name="shop_buy_order")
        app.add_api_route("/api/shop/buy-order/cancel", self.shop_buy_order_cancel, methods=["POST"], name="shop_buy_order_cancel")
        app.add_api_route("/api/shop/sell-order", self.shop_sell_order, methods=["POST"], name="shop_sell_order")
        app.add_api_route("/api/shop/sell-order/cancel", self.shop_sell_order_cancel, methods=["POST"], name="shop_sell_order_cancel")
        app.add_api_route("/api/shop/buy-listing", self.shop_buy_listing, methods=["POST"], name="shop_buy_listing")
        app.add_api_route("/api/shop/quick-sell", self.shop_quick_sell, methods=["POST"], name="shop_quick_sell")
        app.add_api_route("/api/shop/skill-pickaxes", self.shop_skill_pickaxes, methods=["GET"], name="shop_skill_pickaxes")
        app.add_api_route("/api/shop/description", self.shop_description, methods=["POST"], name="shop_description")
        app.add_api_route("/api/shop/history", self.shop_history, methods=["GET"], name="shop_history_api")
        app.add_api_route("/api/shop/fee", self.shop_fee_update, methods=["POST"], name="shop_fee_update")
        app.add_api_websocket_route("/ws/auction", self.auction_socket, name="auction_socket")
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
                "permissions": context["permissions"],
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

    async def auction_cancel(self, request: Request):
        """
        撤銷進行中的競標，並歸還全部出價蛋糕。

        Args:
            request (Request): FastAPI request

        Returns:
            response (JSONResponse): "{'ok': True}"
        """
        reject, context = await self.load_panel_context(request, "/auction")
        if reject is not None:
            if isinstance(reject, RedirectResponse):
                return JSONResponse({"ok": False, "error": "請先登入"}, status_code=401)
            return JSONResponse({"ok": False, "error": "你不在偽造妹妹伺服器中"}, status_code=403)
        if not context["permissions"].get(self.permission_auction_cancel):
            return JSONResponse({"ok": False, "error": "你沒有撤銷競標的權限"}, status_code=403)
        house = getattr(self.bot, "auction_house", None)
        if house is None:
            return JSONResponse({"ok": False, "error": "拍賣所尚未就緒"}, status_code=503)
        try:
            body = await request.json()
            auction_id = int(body.get("auction_id"))
        except Exception:
            return JSONResponse({"ok": False, "error": "撤銷資料格式錯誤"}, status_code=400)
        if auction_id < 1:
            return JSONResponse({"ok": False, "error": "撤銷資料格式錯誤"}, status_code=400)
        result = await house.cancel(auction_id, int(context["user_id"]))
        user_data = await common.mongo_storage.ensure_user_document(context["user_id"])
        result["cake"] = user_data.get("cake", 0)
        return JSONResponse(result)

    async def auction_delete(self, request: Request):
        """
        刪除已結束競標的網頁紀錄，不更動 Discord 訊息與競標 ID 計數。

        Args:
            request (Request): FastAPI request

        Returns:
            response (JSONResponse): "{'ok': True}"
        """
        reject, context = await self.load_panel_context(request, "/auction")
        if reject is not None:
            if isinstance(reject, RedirectResponse):
                return JSONResponse({"ok": False, "error": "請先登入"}, status_code=401)
            return JSONResponse({"ok": False, "error": "你不在偽造妹妹伺服器中"}, status_code=403)
        if not context["permissions"].get(self.permission_auction_delete):
            return JSONResponse({"ok": False, "error": "你沒有刪除紀錄的權限"}, status_code=403)
        house = getattr(self.bot, "auction_house", None)
        if house is None:
            return JSONResponse({"ok": False, "error": "拍賣所尚未就緒"}, status_code=503)
        try:
            body = await request.json()
            auction_id = int(body.get("auction_id"))
        except Exception:
            return JSONResponse({"ok": False, "error": "刪除資料格式錯誤"}, status_code=400)
        if auction_id < 1:
            return JSONResponse({"ok": False, "error": "刪除資料格式錯誤"}, status_code=400)
        result = await house.delete_record(auction_id)
        return JSONResponse(result)

    async def permissions_page(self, request: Request):
        """
        權限控制頁，僅總管理員可進入。

        Args:
            request (Request): FastAPI request

        Returns:
            response: 權限頁、拒絕頁或導向
        """
        reject, context = await self.load_panel_context(request, "/permissions")
        if reject is not None:
            return reject
        if context["identity_key"] != self.permission_role_owner:
            return RedirectResponse(url="/panel", status_code=302)
        context["title"] = "權限控制"
        context["active_nav"] = "permissions"
        context["permission_catalog"] = self.permission_catalog
        context["permission_role_keys"] = self.permission_role_keys
        context["permission_role_labels"] = self.permission_role_labels
        context["permission_grants"] = await self.load_permission_grants()
        return self.templates.TemplateResponse(request, "permissions.html", context)

    async def permissions_update(self, request: Request):
        """
        更新單一權限勾選，僅總管理員可操作。

        Args:
            request (Request): FastAPI request

        Returns:
            response (JSONResponse): "{'ok': True}"
        """
        reject, context = await self.load_panel_context(request, "/permissions")
        if reject is not None:
            if isinstance(reject, RedirectResponse):
                return JSONResponse({"ok": False, "error": "請先登入"}, status_code=401)
            return JSONResponse({"ok": False, "error": "你不在偽造妹妹伺服器中"}, status_code=403)
        if context["identity_key"] != self.permission_role_owner:
            return JSONResponse({"ok": False, "error": "只有總管理員可以使用權限控制"}, status_code=403)
        try:
            body = await request.json()
            permission_key = str(body.get("permission") or "")
            role_key = str(body.get("role") or "")
            enabled = bool(body.get("enabled"))
        except Exception:
            return JSONResponse({"ok": False, "error": "權限資料格式錯誤"}, status_code=400)
        grants = await self.load_permission_grants()
        if permission_key not in grants or role_key not in self.permission_role_keys:
            return JSONResponse({"ok": False, "error": "未知的權限或身分"}, status_code=400)
        grants[permission_key][role_key] = enabled
        await self.persist_permission_grants(grants)
        await self.auction_hub.broadcast()
        return JSONResponse({"ok": True, "grants": grants})

    async def shop_page(self, request: Request):
        """
        商店頁。

        Args:
            request (Request): FastAPI request

        Returns:
            response: 商店、拒絕頁或導向登入
        """
        reject, context = await self.load_panel_context(request, "/shop")
        if reject is not None:
            return reject
        if not context["permissions"].get(self.permission_shop_visit):
            return RedirectResponse(url="/panel", status_code=302)
        context["title"] = "商店"
        context["active_nav"] = "shop"
        house = getattr(self.bot, "shop_house", None)
        if house is None:
            context["fee_percent_text"] = "0"
        else:
            context["fee_percent_text"] = house.format_fee_percent(await house.fee_percent_for_user(context["user_id"]))
        return self.templates.TemplateResponse(request, "shop.html", context)

    async def shop_history_page(self, request: Request):
        """
        商店交易歷史頁。

        Args:
            request (Request): FastAPI request

        Returns:
            response: 歷史、拒絕頁或導向登入
        """
        reject, context = await self.load_panel_context(request, "/shop/history")
        if reject is not None:
            return reject
        if not context["permissions"].get(self.permission_shop_visit):
            return RedirectResponse(url="/panel", status_code=302)
        context["title"] = "商店交易歷史"
        context["active_nav"] = "shop"
        return self.templates.TemplateResponse(request, "shop_history.html", context)

    async def shop_admin_page(self, request: Request):
        """
        商店後台管理頁。

        Args:
            request (Request): FastAPI request

        Returns:
            response: 後台、拒絕頁或導向登入
        """
        reject, context = await self.load_panel_context(request, "/shop/admin")
        if reject is not None:
            return reject
        if not context["permissions"].get(self.permission_shop_visit):
            return RedirectResponse(url="/panel", status_code=302)
        if not context["permissions"].get(self.permission_shop_admin):
            return RedirectResponse(url="/shop", status_code=302)
        context["title"] = "商店後台管理"
        context["active_nav"] = "shop"
        house = getattr(self.bot, "shop_house", None)
        if house is None:
            context.update({
                "fee_percent_text": "0",
                "vip_fee_percent_text": "0",
                "svip_fee_percent_text": "0",
            })
        else:
            context.update(house.fee_settings_public(await house.get_fee_settings()))
        return self.templates.TemplateResponse(request, "shop_admin.html", context)

    async def shop_api_context(self, request: Request, next_path: str = "/shop"):
        """
        商店 API 共用登入／群籍檢查。

        Args:
            request (Request): FastAPI request
            next_path (str): "/shop"

        Returns:
            result (tuple): "(None, {'user_id': '4108'}, shop_house)"
        """
        reject, context = await self.load_panel_context(request, next_path)
        if reject is not None:
            if isinstance(reject, RedirectResponse):
                return JSONResponse({"ok": False, "error": "請先登入"}, status_code=401), None, None
            return JSONResponse({"ok": False, "error": "你不在偽造妹妹伺服器中"}, status_code=403), None, None
        if not context["permissions"].get(self.permission_shop_visit):
            return JSONResponse({"ok": False, "error": "你沒有造訪商店的權限"}, status_code=403), None, None
        house = getattr(self.bot, "shop_house", None)
        if house is None:
            return JSONResponse({"ok": False, "error": "商店尚未就緒"}, status_code=503), None, None
        return None, context, house

    async def shop_action_payload(self, house, context: dict, product_id: str | None = None) -> dict:
        """
        動作後回傳蛋糕與（可選）商品最新狀態。

        Args:
            house: ShopHouse
            context (dict): "{'user_id': '4108'}"
            product_id (str | None): "mining_collection:昆蟲化石"

        Returns:
            payload (dict): "{'cake': 0}"
        """
        user_data = await common.mongo_storage.ensure_user_document(context["user_id"])
        payload = {"cake": user_data.get("cake", 0)}
        if product_id:
            detail = await house.product_detail(product_id, context["user_id"], context["permissions"])
            if detail is not None:
                payload.update(detail)
        return payload

    async def shop_catalog(self, request: Request, category: str = "server"):
        """
        回傳分類商品列表。

        Args:
            request (Request): FastAPI request
            category (str): "mining"

        Returns:
            response (JSONResponse): "{'ok': True, 'products': []}"
        """
        reject, context, house = await self.shop_api_context(request)
        if reject is not None:
            return reject
        chosen = category if category in house.category_labels else house.category_server
        products = await house.list_products(chosen)
        if not products:
            await house.ensure_catalog()
            products = await house.list_products(chosen)
        return JSONResponse(
            {
                "ok": True,
                "cake": context["cake"],
                "category": chosen,
                "categories": await house.list_categories(),
                "products": products,
            },
            headers={"Cache-Control": "no-store"},
        )

    async def shop_product(self, request: Request, product_id: str = ""):
        """
        回傳商品詳細與掛單。

        Args:
            request (Request): FastAPI request
            product_id (str): "mining_collection:昆蟲化石"

        Returns:
            response (JSONResponse): "{'ok': True, 'product': {}}"
        """
        reject, context, house = await self.shop_api_context(request)
        if reject is not None:
            return reject
        if not product_id:
            return JSONResponse({"ok": False, "error": "缺少商品"}, status_code=400)
        detail = await house.product_detail(product_id, context["user_id"], context["permissions"])
        if detail is None:
            return JSONResponse({"ok": False, "error": "找不到這個商品"}, status_code=404)
        return JSONResponse({"ok": True, "cake": context["cake"], **detail})

    async def shop_skill_pickaxes(self, request: Request, product_id: str = ""):
        """
        列出使用者背包中符合此商品的技能礦鎬。

        Args:
            request (Request): FastAPI request
            product_id (str): "skill_pickaxe:災禍鎬"

        Returns:
            response (JSONResponse): "{'ok': True, 'items': []}"
        """
        reject, context, house = await self.shop_api_context(request)
        if reject is not None:
            return reject
        if not product_id:
            return JSONResponse({"ok": False, "error": "缺少商品"}, status_code=400)
        product = await house.get_product(product_id)
        if product is None:
            return JSONResponse({"ok": False, "error": "找不到這個商品"}, status_code=404)
        if product.get("kind") != house.kind_skill_pickaxe:
            return JSONResponse({"ok": False, "error": "這個商品不是技能礦鎬"}, status_code=400)
        return JSONResponse(
            {"ok": True, "items": await house.list_skill_pickaxes_for_product(context["user_id"], product)}
        )

    async def shop_buy_order(self, request: Request):
        """
        建立求購單。

        Args:
            request (Request): FastAPI request

        Returns:
            response (JSONResponse): "{'ok': True}"
        """
        reject, context, house = await self.shop_api_context(request)
        if reject is not None:
            return reject
        try:
            body = await request.json()
            product_id = str(body.get("product_id") or "")
            price = body.get("price")
            quantity = body.get("quantity")
        except Exception:
            return JSONResponse({"ok": False, "error": "求購資料格式錯誤"}, status_code=400)
        if not product_id:
            return JSONResponse({"ok": False, "error": "缺少商品"}, status_code=400)
        result = await house.create_buy_order(product_id, context["user_id"], price, quantity, context["username"])
        result.update(await self.shop_action_payload(house, context, product_id))
        return JSONResponse(result)

    async def shop_buy_order_cancel(self, request: Request):
        """
        取消求購單。

        Args:
            request (Request): FastAPI request

        Returns:
            response (JSONResponse): "{'ok': True}"
        """
        reject, context, house = await self.shop_api_context(request)
        if reject is not None:
            return reject
        try:
            body = await request.json()
            order_id = int(body.get("order_id"))
            product_id = str(body.get("product_id") or "")
        except Exception:
            return JSONResponse({"ok": False, "error": "取消資料格式錯誤"}, status_code=400)
        result = await house.cancel_buy_order(order_id, context["user_id"])
        result.update(await self.shop_action_payload(house, context, product_id or None))
        return JSONResponse(result)

    async def shop_sell_order(self, request: Request):
        """
        建立賣單。

        Args:
            request (Request): FastAPI request

        Returns:
            response (JSONResponse): "{'ok': True}"
        """
        reject, context, house = await self.shop_api_context(request)
        if reject is not None:
            return reject
        try:
            body = await request.json()
            product_id = str(body.get("product_id") or "")
            price = body.get("price")
            quantity = body.get("quantity")
            bag_slot = body.get("bag_slot")
        except Exception:
            return JSONResponse({"ok": False, "error": "販賣資料格式錯誤"}, status_code=400)
        if not product_id:
            return JSONResponse({"ok": False, "error": "缺少商品"}, status_code=400)
        result = await house.create_sell_order(
            product_id, context["user_id"], price, quantity, context["username"], bag_slot
        )
        result.update(await self.shop_action_payload(house, context, product_id))
        return JSONResponse(result)

    async def shop_sell_order_cancel(self, request: Request):
        """
        下架賣單。

        Args:
            request (Request): FastAPI request

        Returns:
            response (JSONResponse): "{'ok': True}"
        """
        reject, context, house = await self.shop_api_context(request)
        if reject is not None:
            return reject
        try:
            body = await request.json()
            order_id = int(body.get("order_id"))
            product_id = str(body.get("product_id") or "")
        except Exception:
            return JSONResponse({"ok": False, "error": "下架資料格式錯誤"}, status_code=400)
        result = await house.cancel_sell_order(order_id, context["user_id"])
        result.update(await self.shop_action_payload(house, context, product_id or None))
        return JSONResponse(result)

    async def shop_buy_listing(self, request: Request):
        """
        購買賣單。

        Args:
            request (Request): FastAPI request

        Returns:
            response (JSONResponse): "{'ok': True}"
        """
        reject, context, house = await self.shop_api_context(request)
        if reject is not None:
            return reject
        try:
            body = await request.json()
            order_id = int(body.get("order_id"))
            quantity = body.get("quantity")
            product_id = str(body.get("product_id") or "")
        except Exception:
            return JSONResponse({"ok": False, "error": "購買資料格式錯誤"}, status_code=400)
        result = await house.buy_listing(order_id, context["user_id"], quantity, context["username"])
        result.update(await self.shop_action_payload(house, context, product_id or None))
        return JSONResponse(result)

    async def shop_quick_sell(self, request: Request):
        """
        以最高求購價快速販賣。

        Args:
            request (Request): FastAPI request

        Returns:
            response (JSONResponse): "{'ok': True}"
        """
        reject, context, house = await self.shop_api_context(request)
        if reject is not None:
            return reject
        try:
            body = await request.json()
            product_id = str(body.get("product_id") or "")
            quantity = body.get("quantity")
            bag_slot = body.get("bag_slot")
        except Exception:
            return JSONResponse({"ok": False, "error": "快速販賣資料格式錯誤"}, status_code=400)
        if not product_id:
            return JSONResponse({"ok": False, "error": "缺少商品"}, status_code=400)
        result = await house.quick_sell(product_id, context["user_id"], quantity, context["username"], bag_slot)
        result.update(await self.shop_action_payload(house, context, product_id))
        return JSONResponse(result)

    async def shop_description(self, request: Request):
        """
        修改商品描述。

        Args:
            request (Request): FastAPI request

        Returns:
            response (JSONResponse): "{'ok': True}"
        """
        reject, context, house = await self.shop_api_context(request)
        if reject is not None:
            return reject
        if not context["permissions"].get(self.permission_shop_edit_description):
            return JSONResponse({"ok": False, "error": "你沒有編輯商品描述的權限"}, status_code=403)
        try:
            body = await request.json()
            product_id = str(body.get("product_id") or "")
            description = str(body.get("description") or "")
        except Exception:
            return JSONResponse({"ok": False, "error": "描述資料格式錯誤"}, status_code=400)
        if not product_id:
            return JSONResponse({"ok": False, "error": "缺少商品"}, status_code=400)
        result = await house.update_description(product_id, description)
        result.update(await self.shop_action_payload(house, context, product_id))
        return JSONResponse(result)

    async def shop_history(self, request: Request):
        """
        回傳自己的商店成交紀錄。

        Args:
            request (Request): FastAPI request

        Returns:
            response (JSONResponse): "{'ok': True, 'items': []}"
        """
        reject, context, house = await self.shop_api_context(request, "/shop/history")
        if reject is not None:
            return reject
        return JSONResponse(
            {
                "ok": True,
                "cake": context["cake"],
                "user_id": context["user_id"],
                "items": await house.list_my_history(context["user_id"]),
            }
        )

    async def shop_fee_update(self, request: Request):
        """
        更新一般／VIP／至寶商店手續費百分比。

        Args:
            request (Request): FastAPI request

        Returns:
            response (JSONResponse): "{'ok': True, 'fee_percent': 5.0}"
        """
        reject, context, house = await self.shop_api_context(request, "/shop/admin")
        if reject is not None:
            return reject
        if not context["permissions"].get(self.permission_shop_admin):
            return JSONResponse({"ok": False, "error": "你沒有商店後台管理的權限"}, status_code=403)
        try:
            body = await request.json()
            fee_percent = body.get("fee_percent")
            vip_fee_percent = body.get("vip_fee_percent")
            svip_fee_percent = body.get("svip_fee_percent")
        except Exception:
            return JSONResponse({"ok": False, "error": "手續費資料格式錯誤"}, status_code=400)
        result = await house.set_fee_settings(fee_percent, vip_fee_percent, svip_fee_percent)
        return JSONResponse(result)

    async def auction_socket(self, websocket: WebSocket):
        """
        拍賣所即時更新通道：連上後立刻推一次，之後每秒與出價時再推。

        Args:
            websocket (WebSocket): 瀏覽器連線
        """
        session = websocket.scope.get("session") or {}
        user_id = session.get("user_id")
        guild = self.bot.get_guild(common.fake_sister_server_id)
        member = guild.get_member(int(user_id)) if guild is not None and user_id else None
        await websocket.accept()
        if not user_id:
            await websocket.close(code=4401)
            return
        if member is None:
            await websocket.close(code=4403)
            return
        client = AuctionSocketClient(websocket, str(user_id))
        self.auction_hub.add_client(client)
        try:
            await self.auction_hub.send_to(client)
            while True:
                await websocket.receive()
        except WebSocketDisconnect:
            pass
        except Exception:
            pass
        self.auction_hub.remove_client(client)

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
        identity_key = self.resolve_identity_key(member)
        context = {
            "user_id": user_id,
            "username": request.session.get("username"),
            "avatar": request.session.get("avatar"),
            "level": user_data.get("level", 1),
            "cake": user_data.get("cake", 0),
            "identity": self.permission_role_labels[identity_key],
            "identity_key": identity_key,
            "show_permission_nav": identity_key == self.permission_role_owner,
            "permissions": await self.permissions_for_role(identity_key),
        }
        context["show_shop_nav"] = bool(context["permissions"].get(self.permission_shop_visit))
        context["show_shop_admin"] = bool(context["permissions"].get(self.permission_shop_admin))
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

    def resolve_identity_key(self, member) -> str:
        """
        依 bot_owner / MOD 身分組判定權限身分鍵。

        Args:
            member: Discord guild member

        Returns:
            identity_key (str): "owner"
        """
        if member.id == common.bot_owner_id:
            return self.permission_role_owner
        if any(role.id == self.mod_role_id for role in member.roles):
            return self.permission_role_mod
        return self.permission_role_member

    def empty_permission_grants(self) -> dict:
        """
        產出全部未勾選的權限表。

        Returns:
            grants (dict): "{'auction_cancel': {'owner': False, 'mod': False, 'member': False}}"
        """
        grants = {}
        for category in self.permission_catalog:
            for permission in category["permissions"]:
                grants[permission["key"]] = {role_key: False for role_key in self.permission_role_keys}
        return grants

    async def load_permission_grants(self) -> dict:
        """
        讀取權限勾選（快取優先，缺欄位當未勾選）。

        Returns:
            grants (dict): "{'auction_cancel': {'owner': False, 'mod': False, 'member': False}}"
        """
        grants = self.empty_permission_grants()
        stored = self.permission_grants_cache
        if stored is None:
            collection = common.mongo_storage.get_collection("web_permission")
            document = await collection.find_one({"_id": self.permission_document_id})
            stored = document if isinstance(document, dict) else {}
        for permission_key in grants:
            role_grants = stored.get(permission_key) if isinstance(stored, dict) else None
            if not isinstance(role_grants, dict):
                continue
            for role_key in self.permission_role_keys:
                grants[permission_key][role_key] = bool(role_grants.get(role_key, False))
        self.permission_grants_cache = grants
        return grants

    async def persist_permission_grants(self, grants: dict):
        """
        寫入權限勾選並更新快取。

        Args:
            grants (dict): "{'auction_cancel': {'owner': True, 'mod': False, 'member': False}}"
        """
        collection = common.mongo_storage.get_collection("web_permission")
        await collection.replace_one(
            {"_id": self.permission_document_id},
            {"_id": self.permission_document_id, **grants},
            upsert=True,
        )
        self.permission_grants_cache = grants

    async def permissions_for_role(self, role_key: str) -> dict:
        """
        依身分取出該角色已開放的功能。

        Args:
            role_key (str): "owner"

        Returns:
            flags (dict): "{'auction_cancel': False}"
        """
        grants = await self.load_permission_grants()
        return {permission_key: bool(role_grants.get(role_key, False)) for permission_key, role_grants in grants.items()}

    async def permissions_for_user(self, user_id: str) -> dict:
        """
        依使用者在群內身分取出已開放的功能。

        Args:
            user_id (str): "410847926236086272"

        Returns:
            flags (dict): "{'auction_cancel': False}"
        """
        guild = self.bot.get_guild(common.fake_sister_server_id)
        member = guild.get_member(int(user_id)) if guild is not None else None
        if member is None:
            return {permission_key: False for permission_key in self.empty_permission_grants()}
        return await self.permissions_for_role(self.resolve_identity_key(member))

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
        self.auction_hub.start_tick()
        try:
            await server.serve()
        finally:
            self.auction_hub.stop_tick()


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
