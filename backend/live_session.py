"""Live browser run (session-id based).

Opens a Playwright browser inside the FastAPI process, authenticates using the
Instagram ``sessionid`` cookie, then runs the whole comment job on the visible
page while streaming JPEG frames and a step log to the frontend. The user can
therefore watch the bot work from start to finish without needing a CAPTCHA.
"""

import asyncio
import logging
import os
import uuid

from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel

from playwright.async_api import async_playwright

logger = logging.getLogger("live")
router = APIRouter(prefix="/api/live", tags=["live"])
_SESSIONS: dict[str, "LiveSession"] = {}

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)


class StartRequest(BaseModel):
    username: str
    session_id: str
    target: str
    comment_count: int = 3
    max_posts: int = 3


class LiveSession:
    def __init__(self, token: str) -> None:
        self.token = token
        self.status = "starting"  # starting|running|completed|error
        self.message = "Menyiapkan browser..."
        self.logs: list[str] = []
        self.result: dict | None = None
        self.width = 1280
        self.height = 900
        self.latest_jpeg: bytes | None = None
        self._running = True
        self._playwright = None
        self._browser = None
        self._context = None
        self._page = None
        self._capture_task: asyncio.Task | None = None
        self._job_task: asyncio.Task | None = None

    def add_log(self, text: str) -> None:
        self.logs.append(text)
        if len(self.logs) > 300:
            del self.logs[:-300]
        logger.info("[%s] %s", self.token[:6], text)

    async def start(
        self,
        username: str,
        session_id: str,
        target: str,
        comment_count: int,
        max_posts: int = 3,
    ) -> None:
        headless = os.getenv("LIVE_HEADLESS", "false").lower() == "true"
        try:
            self._playwright = await async_playwright().start()
            self._browser = await self._playwright.chromium.launch(headless=headless)
            self._context = await self._browser.new_context(
                viewport={"width": self.width, "height": self.height},
                user_agent=USER_AGENT,
            )
            self._page = await self._context.new_page()
            self._page.set_default_timeout(int(os.getenv("PLAYWRIGHT_TIMEOUT_MS", "10000")))
            self._page.set_default_navigation_timeout(
                int(os.getenv("PLAYWRIGHT_NAVIGATION_TIMEOUT_MS", "30000"))
            )
            from tasks import _add_session_cookie

            await _add_session_cookie(self._page, session_id)
            self.status = "running"
            self.message = f"Session dipasang. Membuka @{target} ..."
            self.add_log(f"Session diterima untuk akun {username}")
            self.add_log(f"Menuju channel @{target}")
            self._capture_task = asyncio.create_task(self._capture_loop())
            self._job_task = asyncio.create_task(
                self._run_job(username, target, comment_count, max_posts)
            )
        except Exception as exc:
            self.status = "error"
            self.message = f"Gagal menyiapkan browser: {exc}"
            self.add_log(f"Error: {exc}")

    async def _capture_loop(self) -> None:
        while self._running:
            try:
                if self._page is not None and not self._page.is_closed():
                    self.latest_jpeg = await self._page.screenshot(type="jpeg", quality=70)
            except Exception:
                pass
            await asyncio.sleep(0.6)

    async def _run_job(
        self,
        username: str,
        target: str,
        comment_count: int,
        max_posts: int = 3,
    ) -> None:
        try:
            from tasks import _process_posts

            result = await _process_posts(
                self._page,
                username,
                target,
                comment_count,
                log=self.add_log,
                max_posts=max_posts,
            )
            self.result = result
            self.status = "completed"
            self.message = (
                f"Job selesai: {result.get('comments_posted', 0)} komentar "
                f"pada {result.get('posts_processed', 0)} postingan."
            )
            self.add_log(self.message)
        except Exception as exc:
            self.status = "error"
            self.message = f"Job gagal: {exc}"
            self.add_log(f"Error: {exc}")
        finally:
            self._running = False
            try:
                if self._page is not None and not self._page.is_closed():
                    self.latest_jpeg = await self._page.screenshot(type="jpeg", quality=70)
            except Exception:
                pass

    async def close(self) -> None:
        self._running = False
        for task in (self._capture_task, self._job_task):
            if task is None:
                continue
            task.cancel()
            try:
                await task
            except (asyncio.CancelledError, Exception):
                pass
        try:
            if self._browser is not None:
                await self._browser.close()
        except Exception:
            pass
        try:
            if self._playwright is not None:
                await self._playwright.stop()
        except Exception:
            pass
        self._page = None
        self._context = None
        self._browser = None


def _get_session(token: str) -> LiveSession:
    session = _SESSIONS.get(token)
    if session is None:
        raise HTTPException(status_code=404, detail="Live session tidak ditemukan")
    return session


@router.post("/start")
async def start_live(request: StartRequest) -> dict:
    if not request.username.strip() or not request.session_id.strip() or not request.target.strip():
        raise HTTPException(status_code=422, detail="username, session_id, dan target wajib diisi")
    if not (1 <= request.comment_count <= 10):
        raise HTTPException(status_code=422, detail="comment_count harus 1-10")
    if not (1 <= request.max_posts <= 50):
        raise HTTPException(status_code=422, detail="max_posts harus 1-50")
    token = uuid.uuid4().hex
    session = LiveSession(token)
    _SESSIONS[token] = session
    await session.start(
        request.username.strip(),
        request.session_id.strip(),
        request.target.strip(),
        request.comment_count,
        request.max_posts,
    )
    return {"token": token, "width": session.width, "height": session.height}


@router.get("/{token}/frame")
async def live_frame(token: str) -> Response:
    session = _get_session(token)
    if not session.latest_jpeg:
        return Response(status_code=204)
    return Response(content=session.latest_jpeg, media_type="image/jpeg")


@router.get("/{token}/status")
async def live_status(token: str) -> dict:
    session = _get_session(token)
    return {
        "token": token,
        "status": session.status,
        "message": session.message,
        "logs": session.logs,
        "result": session.result,
    }


@router.post("/{token}/close")
async def live_close(token: str) -> dict:
    session = _get_session(token)
    await session.close()
    _SESSIONS.pop(token, None)
    return {"ok": True}


@router.post("/{token}/stop")
async def live_stop(token: str) -> dict:
    session = _get_session(token)
    await session.close()
    _SESSIONS.pop(token, None)
    return {"ok": True, "status": "stopped"}
