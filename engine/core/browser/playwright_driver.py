from typing import Any
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
        self._browser = await self._playwright.chromium.launch(headless=True)
        self._page = await self._browser.new_page()
        await self._page.goto(url)

    async def click(self, locator: Any):
        selector = to_selector_string(locator)
        await self._page.click(selector)

    async def type(self, locator: Any, text: str):
        selector = to_selector_string(locator)
        await self._page.fill(selector, text)

    async def press(self, key: str):
        # Playwright expects e.g. "Enter", "Escape", "Control+A"
        await self._page.keyboard.press(key)

    async def screenshot(self, path: str):
        await self._page.screenshot(path=path)

    async def close(self):
        await self._browser.close()
        await self._playwright.stop()
