from playwright.async_api import async_playwright
from engine.core.browser.browser_port import IBrowser


class PlaywrightBrowser(IBrowser):
    """Async Playwright implementation."""

    def __init__(self):
        self._playwright = None
        self._browser = None
        self._page = None

    async def open(self, url: str):
        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(headless=True)
        self._page = await self._browser.new_page()
        await self._page.goto(url)

    async def click(self, selector: str):
        await self._page.click(selector)

    async def type(self, selector: str, text: str):
        await self._page.fill(selector, text)

    async def screenshot(self, path: str):
        await self._page.screenshot(path=path)

    async def close(self):
        await self._browser.close()
        await self._playwright.stop()
