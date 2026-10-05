"""
Optional notifications for a manual trader away from the screen (CONFIG.notify, off by default).

- Windows balloon notification through PowerShell (System.Windows.Forms, no extra packages).
- Telegram: the bot token / chat id of config.local.toml, else the environment's TELEGRAM_BOT_TOKEN /
  TELEGRAM_CHANNEL_ID (the owner's channel). `post` sends briefings / watch alerts (briefing.py) as HTML.
Sending runs in background tasks with a timeout, so a slow network never blocks the scan loop.
"""
import asyncio
import logging
import os
import errors
import platform
from typing import Optional, Set

import aiohttp

from config import CONFIG

logger = logging.getLogger(__name__)

_TOAST_PS = r"""
Add-Type -AssemblyName System.Windows.Forms
$n = New-Object System.Windows.Forms.NotifyIcon
$n.Icon = [System.Drawing.SystemIcons]::Information
$n.BalloonTipTitle = $env:SCANNER_TITLE
$n.BalloonTipText = $env:SCANNER_TEXT
$n.Visible = $true
$n.ShowBalloonTip(8000)
Start-Sleep -Seconds 9
$n.Dispose()
"""


class Notifier:
    def __init__(self):
        self.cfg = CONFIG.notify
        self._tasks: Set[asyncio.Task] = set()
        self._session: Optional[aiohttp.ClientSession] = None

    @property
    def enabled(self) -> bool:
        return self.cfg.enabled

    def wants(self, event: str) -> bool:
        return self.enabled and any(event.startswith(e) for e in self.cfg.events)

    def send(self, event: str, title: str, text: str):
        """Fire-and-forget; `event` is matched against notify.events (ENTRY, TP, SL, ZONE)."""
        if not self.wants(event):
            return
        loop = asyncio.get_running_loop()
        for coro in (self._toast(title, text), self._telegram(f"{title}\n{text}")):
            task = loop.create_task(coro)
            self._tasks.add(task)
            task.add_done_callback(self._tasks.discard)

    async def _toast(self, title: str, text: str):
        if not self.cfg.toast or platform.system() != 'Windows':
            return
        try:
            import os
            env = dict(os.environ, SCANNER_TITLE=title[:60], SCANNER_TEXT=text[:250])
            proc = await asyncio.create_subprocess_exec(
                'powershell', '-NoProfile', '-NonInteractive', '-Command', _TOAST_PS, env=env,
                stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL,
            )
            await asyncio.wait_for(proc.wait(), timeout=20)
        except Exception as e:
            errors.report('notifier._toast', e, "Toast failed")

    def _creds(self):
        return (self.cfg.telegram_token or os.environ.get('TELEGRAM_BOT_TOKEN', ''),
                self.cfg.telegram_chat_id or os.environ.get('TELEGRAM_CHANNEL_ID', ''))

    def post(self, text: str):
        """A briefing / watch alert (HTML), Telegram only; long texts are split at blank lines."""
        if not self.enabled or not text:
            return
        loop = asyncio.get_running_loop()
        chunks, cur = [], ''
        for part in text.split('\n\n'):
            if cur and len(cur) + len(part) > 3800:
                chunks.append(cur)
                cur = ''
            cur = f"{cur}\n\n{part}" if cur else part
        if cur:
            chunks.append(cur)
        task = loop.create_task(self._send_chunks(chunks))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def _send_chunks(self, chunks):
        for c in chunks:
            await self._telegram(c, html=True)

    async def _telegram(self, text: str, html: bool = False):
        token, chat = self._creds()
        if not token or not chat:
            return
        try:
            if self._session is None:
                self._session = aiohttp.ClientSession()
            payload = {'chat_id': chat, 'text': text[:4000], 'disable_web_page_preview': True}
            if html:
                payload['parse_mode'] = 'HTML'
            async with self._session.post(f"https://api.telegram.org/bot{token}/sendMessage",
                                          json=payload,
                                          timeout=aiohttp.ClientTimeout(total=10)) as resp:
                if resp.status != 200:
                    logger.warning(f"Telegram notification failed: HTTP {resp.status} {(await resp.text())[:200]}")
        except Exception as e:
            logger.warning(f"Telegram notification failed: {e}")

    async def close(self):
        for task in list(self._tasks):
            task.cancel()
        if self._tasks:
            await asyncio.wait(self._tasks, timeout=2)
        if self._session:
            await self._session.close()
