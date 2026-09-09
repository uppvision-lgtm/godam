"""Live browser run (session-id based).

Opens a Playwright browser, authenticates using the Instagram ``sessionid``
cookie, then runs the comment job while streaming JPEG frames and a step log
to the frontend.

Playwright is started on a dedicated thread with a Proactor event loop. Uvicorn
``--reload`` on Windows uses SelectorEventLoop, which cannot spawn Chromium
(``NotImplementedError`` with an empty message).
"""

import asyncio
import logging
import os
import sys
import threading
import uuid
from urllib.parse import unquote

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
        self._thread: threading.Thread | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._ready = threading.Event()

    def add_log(self, text: str) -> None:
        self.logs.append(text)
        if len(self.logs) > 300:
            del self.logs[:-300]
        logger.info("[%s] %s", self.token[:6], text)

    def _fail_start(self, exc: BaseException) -> None:
        detail = str(exc).strip() or repr(exc)
        logger.exception("Gagal menyiapkan browser")
        self.status = "error"
        self.message = f"Gagal menyiapkan browser: {type(exc).__name__}: {detail}"
        self.add_log(f"Error: {type(exc).__name__}: {detail}")
        self._ready.set()

    async def start(
        self,
        username: str,
        session_id: str,
        target: str,
        comment_count: int,
        max_posts: int = 3,
    ) -> None:
        self._thread = threading.Thread(
            target=self._thread_main,
            args=(username, session_id, target, comment_count, max_posts),
            daemon=True,
            name=f"live-{self.token[:6]}",
        )
        self._thread.start()
        await asyncio.to_thread(self._ready.wait, 45)

    def _thread_main(
        self,
        username: str,
        session_id: str,
        target: str,
        comment_count: int,
        max_posts: int,
    ) -> None:
        if sys.platform == "win32":
            asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
        try:
            asyncio.run(self._async_main(username, session_id, target, comment_count, max_posts))
        except Exception as exc:
            if self.status == "starting":
                self._fail_start(exc)

    async def _async_main(
        self,
        username: str,
        session_id: str,
        target: str,
        comment_count: int,
        max_posts: int,
    ) -> None:
        self._loop = asyncio.get_running_loop()
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

            await _add_session_cookie(self._page, unquote(session_id).strip())
            self.status = "running"
            self.message = f"Session dipasang. Membuka @{target} ..."
            self.add_log(f"Session diterima untuk akun {username}")
            self.add_log(f"Menuju channel @{target}")
            self._ready.set()
            self._capture_task = asyncio.create_task(self._capture_loop())
            self._job_task = asyncio.create_task(
                self._run_job(username, target, comment_count, max_posts)
            )
            await self._job_task
        except Exception as exc:
            if self.status in {"starting", "running"} and self.result is None:
                if self.status == "starting":
                    self._fail_start(exc)
                else:
                    self.status = "error"
                    self.message = f"Job gagal: {exc}"
                    self.add_log(f"Error: {exc}")
        finally:
            self._ready.set()
            await self._shutdown_browser()

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
        except asyncio.CancelledError:
            raise
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

    async def _shutdown_browser(self) -> None:
        self._running = False
        for task in (self._capture_task, self._job_task):
            if task is None or task.done():
                continue
            task.cancel()
            try:
                await task
            except (asyncio.CancelledError, Exception):
                pass
        browser, playwright = self._browser, self._playwright
        self._browser = None
        self._playwright = None
        self._page = None
        self._context = None
        try:
            if browser is not None:
                await browser.close()
        except Exception:
            pass
        try:
            if playwright is not None:
                await playwright.stop()
        except Exception:
            pass

    async def close(self) -> None:
        self._running = False
        loop = self._loop
        if loop is not None and loop.is_running():
            future = asyncio.run_coroutine_threadsafe(self._shutdown_browser(), loop)
            try:
                await asyncio.wrap_future(future)
            except Exception:
                pass
        if self._thread is not None and self._thread.is_alive():
            await asyncio.to_thread(self._thread.join, 15)


def _get_session(token: str) -> LiveSession:
    session = _SESSIONS.get(token)
    if session is None:
        raise HTTPException(status_code=404, detail="Live session tidak ditemukan")
    return session


@router.post("/start")
async def start_live(request: StartRequest) -> dict:
    if not request.username.strip() or not request.session_id.strip() or not request.target.strip():
        raise HTTPException(status_code=422, detail="username, session_id, dan target wajib diisi")
    if not (1 <= request.comment_count <= 100):
        raise HTTPException(status_code=422, detail="comment_count harus 1-100")
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
