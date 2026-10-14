"""
Optional notifications for a manual trader away from the screen (CONFIG.notify, off by default).

- Windows balloon notification through PowerShell (System.Windows.Forms, no extra packages).
- Telegram: the bot token / chat id of config.local.toml, else the environment's TELEGRAM_BOT_TOKEN /
  TELEGRAM_CHANNEL_ID (the owner's channel). `post` sends briefings / watch alerts (briefing.py) as HTML.
  Every message has a topic (briefing / signals / alerts / demo / service): it goes to the channel (except
  'service') and, when notify.group_chat_id is set, to that topic's thread of the forum group.
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
        # eng-102: one request at a time (parallel tasks of a briefing burst hit Telegram's per-chat limit, 429)
        self._send_lock: Optional[asyncio.Lock] = None

    def _lock(self) -> asyncio.Lock:
        if self._send_lock is None:
            self._send_lock = asyncio.Lock()
        return self._send_lock

    def _redact(self, e: BaseException) -> str:
        """An error's repr without the bot token (aiohttp errors can carry the request URL /bot<token>/...)."""
        text, (token, _) = repr(e), self._creds()
        return text.replace(token, '<token>') if token else text

    async def _post(self, method: str, timeout: float, **kw):
        """POST to the Bot API under the send lock; a 429 waits its retry_after (<= 60 s) and retries twice.
        Returns (status, body text)."""
        token, _ = self._creds()
        if self._session is None:
            self._session = aiohttp.ClientSession()
        async with self._lock():
            for attempt in range(3):
                data = kw.get('data')
                if callable(data):
                    kw = dict(kw, data=data())          # a FormData is single-use: rebuilt per attempt
                async with self._session.post(f"https://api.telegram.org/bot{token}/{method}",
                                              timeout=aiohttp.ClientTimeout(total=timeout),
                                              **{k: v for k, v in kw.items()}) as resp:
                    body = await resp.text()
                    if resp.status != 429 or attempt == 2:
                        return resp.status, body
                    try:
                        import json
                        wait = float(json.loads(body).get('parameters', {}).get('retry_after', 5))
                    except (ValueError, AttributeError):
                        wait = 5.0
                    await asyncio.sleep(min(wait, 60.0) + 0.5)
                if callable(data):
                    kw = dict(kw, data=data)
        return 429, ''

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
        import re
        plain = re.sub(r'</?[a-zA-Z][^>]*>', '', text)
        for coro in (self._toast(title, plain), self._telegram(f"<b>{title}</b>\n{text}", html=True, topic='signals')):
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

    def _targets(self, topic: str):
        """(chat id, thread id or None) of every destination of a message of this topic."""
        _, channel = self._creds()
        out = [(channel, None)] if channel and topic != 'service' else []
        group = self.cfg.group_chat_id
        if group:
            out.append((group, getattr(self.cfg, f'topic_{topic}', 0) or None))
        return out

    def post(self, text: str, topic: str = 'alerts'):
        """A briefing / watch alert (HTML), Telegram only; long texts are split at blank lines."""
        if not self.enabled or not text:
            return
        loop = asyncio.get_running_loop()
        chunks, cur = [], ''
        parts = []
        for part in text.split('\n\n'):
            # eng-102: a single part over the limit (no blank lines) is split by lines, then hard
            while len(part) > 3800:
                cut = part.rfind('\n', 0, 3800)
                cut = cut if cut > 0 else 3800
                parts.append(part[:cut])
                part = part[cut:].lstrip('\n')
            parts.append(part)
        for part in parts:
            if cur and len(cur) + len(part) > 3800:
                chunks.append(cur)
                cur = ''
            cur = f"{cur}\n\n{part}" if cur else part
        if cur:
            chunks.append(cur)
        task = loop.create_task(self._send_chunks(chunks, topic))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    def post_photo(self, png: bytes, caption: str = '', topic: str = 'briefing'):
        """A briefing card (PNG) with an HTML caption (<= 1024 characters), Telegram only."""
        if not self.enabled or not png:
            return
        task = asyncio.get_running_loop().create_task(self._photo(png, caption[:1024], topic))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def _photo(self, png: bytes, caption: str, topic: str = 'briefing'):
        token, _ = self._creds()
        if not token:
            return
        for chat, thread in self._targets(topic):
            await self._photo_to(token, chat, thread, png, caption)

    async def _photo_to(self, token: str, chat, thread, png: bytes, caption: str):
        import re

        def form(html: bool = True, cap: str = caption):
            f = aiohttp.FormData()
            f.add_field('chat_id', str(chat))
            if thread:
                f.add_field('message_thread_id', str(thread))
            f.add_field('caption', cap)
            if html:
                f.add_field('parse_mode', 'HTML')
            f.add_field('photo', png, filename='card.png', content_type='image/png')
            return f
        try:
            status, body = await self._post('sendPhoto', 30, data=form)
            if status == 400 and "can't parse entities" in body:
                # eng-102: the caption cut at 1024 characters inside a tag - the card goes out with a plain caption
                plain = re.sub(r'</?[a-zA-Z][^>]*>', '', caption)
                status, body = await self._post('sendPhoto', 30, data=lambda: form(False, plain))
            if status != 200:
                logger.warning(f"Telegram photo failed: HTTP {status} {body[:200]}")
        except Exception as e:
            logger.warning(f"Telegram photo failed: {self._redact(e)}")

    async def _send_chunks(self, chunks, topic: str = 'alerts'):
        for c in chunks:
            await self._telegram(c, html=True, topic=topic)

    async def _telegram(self, text: str, html: bool = False, topic: str = 'alerts'):
        token, _ = self._creds()
        if not token:
            return
        for chat, thread in self._targets(topic):
            await self._telegram_to(token, chat, thread, text, html)

    async def _telegram_to(self, token: str, chat, thread, text: str, html: bool):
        try:
            payload = {'chat_id': chat, 'text': text[:4000], 'disable_web_page_preview': True}
            if thread:
                payload['message_thread_id'] = thread
            if html:
                payload['parse_mode'] = 'HTML'
            status, body = await self._post('sendMessage', 10, json=payload)
            if status != 200:
                body = body[:200]
                if html and status == 400 and "can't parse entities" in body:
                    # a bare '<' in the text ("R:R 1.55 < 2", 2026-10-06 09:16) breaks Telegram's HTML: the
                    # message goes out as plain text instead of not at all
                    import re
                    return await self._telegram_to(token, chat, thread, re.sub(r'</?[a-zA-Z][^>]*>', '', text), False)
                logger.warning(f"Telegram notification failed: HTTP {status} {body}")
        except Exception as e:
            logger.warning(f"Telegram notification failed: {self._redact(e)}")    # repr: a timeout's str() is empty

    async def close(self):
        for task in list(self._tasks):
            task.cancel()
        if self._tasks:
            await asyncio.wait(self._tasks, timeout=2)
        if self._session:
            await self._session.close()
