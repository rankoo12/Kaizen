from typing import Any
import os
import asyncio
import threading
from playwright.async_api import async_playwright
from engine.core.browser.browser_port import IBrowser
from engine.core.commands.selector import to_selector_string


class PlaywrightBrowser(IBrowser):
    """Async Playwright implementation."""

    def __init__(self):
        self._playwright = None
        self._browser = None
        self._page = None
        # Headless toggle via env (defaults to True). Prefer KAIZEN_HEADFUL=true to force headed.
        headless = True
        try:
            if str(os.environ.get("KAIZEN_HEADFUL", "")).lower() in ("1", "true", "yes"):  # headed
                headless = False
            elif os.environ.get("KAIZEN_HEADLESS") is not None:
                headless = str(os.environ.get("KAIZEN_HEADLESS")).lower() not in ("0", "false", "no")
        except Exception:
            headless = True
        self._headless = headless
        try:
            self._slowmo = int(os.environ.get("KAIZEN_PW_SLOWMO", "0") or 0)
        except Exception:
            self._slowmo = 0
        # Default timeouts (ms)
        try:
            self._timeout_ms = int(os.environ.get("KAIZEN_PW_TIMEOUT_MS", "10000") or 10000)
        except Exception:
            self._timeout_ms = 10000
        try:
            self._nav_timeout_ms = int(os.environ.get("KAIZEN_PW_NAV_TIMEOUT_MS", "15000") or 15000)
        except Exception:
            self._nav_timeout_ms = 15000
        self._nav_wait = str(os.environ.get("KAIZEN_NAV_WAIT", "domcontentloaded") or "domcontentloaded")
        self._loop = None
        self._thread = None
        self._ensure_loop()

    def _ensure_loop(self) -> None:
        if self._loop is not None:
            return
        loop = asyncio.new_event_loop()
        def _runner():
            asyncio.set_event_loop(loop)
            loop.run_forever()
        t = threading.Thread(target=_runner, daemon=True)
        t.start()
        self._loop = loop
        self._thread = t

    def run_coro(self, coro):
        """Run a coroutine on the browser's dedicated loop and return result."""
        self._ensure_loop()
        fut = asyncio.run_coroutine_threadsafe(coro, self._loop)
        return fut.result()

    async def open(self, url: str):
        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(headless=self._headless, slow_mo=self._slowmo or 0)
        self._page = await self._browser.new_page()
        # Set default timeouts on the page
        try:
            self._page.set_default_timeout(self._timeout_ms)
            self._page.set_default_navigation_timeout(self._nav_timeout_ms)
        except Exception:
            pass
        resp = None
        try:
            resp = await self._page.goto(url, wait_until=self._nav_wait)
        except Exception:
            resp = None
        # Simple retry on server errors
        try:
            status = resp.status if resp is not None else None
        except Exception:
            status = None
        if status is None or (isinstance(status, int) and status >= 500):
            try:
                await self._page.reload(wait_until=self._nav_wait)
            except Exception:
                pass

    async def click(self, locator: Any):
        selector = to_selector_string(locator)
        # Prefer check() for radios/checkboxes or associated labels; fallback to click()
        try:
            await self._page.check(selector)
            return
        except Exception:
            # Not a checkable control; fall back to a regular click
            pass
        await self._page.click(selector)

    async def dblclick(self, locator: Any):
        selector = to_selector_string(locator)
        await self._page.dblclick(selector)

    async def right_click(self, locator: Any):
        selector = to_selector_string(locator)
        await self._page.click(selector, button="right")

    async def hover(self, locator: Any):
        selector = to_selector_string(locator)
        await self._page.hover(selector)

    async def focus(self, locator: Any):
        selector = to_selector_string(locator)
        await self._page.focus(selector)

    async def blur(self, locator: Any):
        selector = to_selector_string(locator)
        try:
            await self._page.locator(selector).evaluate("e => e.blur()")
        except Exception:
            # best-effort: tab away
            try:
                await self._page.keyboard.press("Tab")
            except Exception:
                pass

    async def clear(self, locator: Any):
        selector = to_selector_string(locator)
        await self._page.fill(selector, "")

    async def type(self, locator: Any, text: str, clear: bool = False):
        selector = to_selector_string(locator)
        if clear:
            try:
                await self._page.fill(selector, "")
            except Exception:
                pass
        await self._page.fill(selector, text)

    async def select_option(self, locator: Any, option: dict):
        selector = to_selector_string(locator)
        opt = {}
        if isinstance(option, dict):
            for k in ("value", "label", "index"):
                if option.get(k) is not None:
                    opt[k] = option.get(k)
        await self._page.select_option(selector, **opt)

    async def set_input_files(self, locator: Any, files: list[str]):
        selector = to_selector_string(locator)
        await self._page.set_input_files(selector, files)

    async def drag(self, locator: Any, dx: int, dy: int):
        selector = to_selector_string(locator)
        box = await self._page.locator(selector).bounding_box()
        if not box:
            return
        start_x = box["x"] + box["width"] / 2
        start_y = box["y"] + box["height"] / 2
        await self._page.mouse.move(start_x, start_y)
        await self._page.mouse.down()
        await self._page.mouse.move(start_x + int(dx), start_y + int(dy))
        await self._page.mouse.up()

    async def press(self, key: str):
        # Playwright expects e.g. "Enter", "Escape", "Control+A"
        await self._page.keyboard.press(key)

    async def drag_and_drop(self, source: Any, target: Any):
        src = to_selector_string(source)
        dst = to_selector_string(target)
        await self._page.locator(src).drag_to(self._page.locator(dst))

    async def screenshot(self, path: str):
        await self._page.screenshot(path=path)

    async def evaluate(self, script: str):
        return await self._page.evaluate(script)

    async def frames(self):
        try:
            return self._page.frames
        except Exception:
            return []

    async def scroll(self, x: int, y: int):
        try:
            await self._page.evaluate(
                "(x,y)=>{window.scrollBy(x,y);}",
                x,
                y,
            )
        except Exception:
            # Fallback via mouse wheel for vertical scroll
            try:
                await self._page.mouse.wheel(int(x) or 0, int(y) or 0)
            except Exception:
                pass

    async def close(self):
        await self._browser.close()
        await self._playwright.stop()
