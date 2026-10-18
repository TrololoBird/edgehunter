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
import json
import platform
import time
from typing import Callable, Dict, List, Optional, Set

import aiohttp

from config import CONFIG
from storage import atomic_write

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
        # audit B05: trading instructions (ENTRY / SL / RESTOP ...) outrank briefings for the send lock, wait for it a
        # bounded time and, when Telegram does not take them, wait in a file outbox (survives a restart) until they are
        # delivered or too old to act on
        self._prio_waiting = 0
        self._outbox: List[Dict] = self._load_outbox()
        self._retry_task: Optional[asyncio.Task] = None
        # audit 2026-10-18 P1: a queued card event knows its card and its place in the card's event order, so a retry
        # can drop what the card's later state made wrong (an ENTRY of a closed trade, a RESTOP behind a newer one).
        # `check(item)` is set by the scanner: None = still actionable, else the reason it is not
        self._seq = max([int(i.get('seq') or 0) for i in self._outbox] + [0])
        self._last_event: Dict[str, int] = {}
        for i in self._outbox:
            if i.get('card'):
                self._last_event[i['card']] = max(self._last_event.get(i['card'], 0), int(i.get('seq') or 0))
        self.check: Optional[Callable[[Dict], Optional[str]]] = None

    OUTBOX_PATH = 'notify_outbox.json'
    OUTBOX_TTL_SEC = 900.0          # a trading instruction older than this is dropped: its price is no longer actionable
    LATE_NOTE_SEC = 60.0
    PRIORITY_LOCK_WAIT_SEC = 20.0

    def _load_outbox(self) -> List[Dict]:
        try:
            with open(self.OUTBOX_PATH, encoding='utf-8') as fh:
                items = json.load(fh)
            return [i for i in items if isinstance(i, dict) and 'text' in i and 'chat' in i]
        except (OSError, ValueError):
            return []

    def _save_outbox(self) -> None:
        try:
            atomic_write(self.OUTBOX_PATH, json.dumps(self._outbox, ensure_ascii=False).encode('utf-8'))
        except OSError as e:
            logger.warning(f"Telegram outbox not saved: {e!r}")

    def resume(self) -> None:
        """Start the retry task for messages left in the outbox by a previous run."""
        if self._outbox and self._retry_task is None:
            self._retry_task = asyncio.get_running_loop().create_task(self._retry_loop())

    async def _retry_loop(self) -> None:
        delay = 5.0
        try:
            while self._outbox:
                await asyncio.sleep(delay)
                delay = min(delay * 2, 60.0)
                token, _ = self._creds()
                # audit V08: every item stays IN the outbox until Telegram took it (was: the batch was taken out before
                # the awaits, so a shutdown mid-pass saved an empty outbox and lost an undelivered SL); a message queued
                # while this pass sends is appended behind it
                for item in list(self._outbox):
                    age = time.time() - float(item.get('ts') or 0)
                    if age > self.OUTBOX_TTL_SEC:
                        logger.warning(f"Telegram message dropped after {age:.0f}s undelivered: {item['text'][:60]!r}")
                        self._outbox.remove(item)
                        self._save_outbox()
                        continue
                    stale = self._stale(item)
                    if stale:
                        logger.info(f"Telegram message not retried ({stale}): {item['text'][:60]!r}")
                        self._outbox.remove(item)
                        self._save_outbox()
                        continue
                    text = item['text']
                    if age > self.LATE_NOTE_SEC:
                        text = (f"⏱ <i>доставлено с опозданием {age / 60:.0f} мин: цены могли уйти, "
                                f"проверь актуальность перед действием</i>\n{text}")
                    ok = bool(token) and await self._telegram_to(token, item['chat'], item.get('thread'), text,
                                                                 item.get('html', True), priority=True, queue=False)
                    if ok:
                        self._outbox.remove(item)
                        self._save_outbox()
        finally:
            self._retry_task = None

    def _stale(self, item: Dict) -> Optional[str]:
        """Why a queued card event is no longer an instruction (None: deliver it)."""
        card, event = item.get('card'), item.get('event') or ''
        if not card:
            return None
        if event == 'RESTOP' and self._last_event.get(card, 0) > int(item.get('seq') or 0):
            return 'a newer event of the card superseded it'
        if event == 'ENTRY' and self.check is not None:
            try:
                return self.check(item)
            except Exception as e:                       # a check that fails never blocks a delivery
                logger.warning(f"Telegram outbox check failed: {e!r}")
        return None

    SENT_DB_PATH = 'data/tg_sent.db'

    def _log_sent(self, kind: str, chat, thread, text: str, status, ok: bool) -> None:
        """Every Telegram send attempt with its full text (data/tg_sent.db), so alerts can be reviewed afterwards."""
        try:
            import sqlite3
            con = sqlite3.connect(self.SENT_DB_PATH, timeout=2)
            try:
                con.execute("CREATE TABLE IF NOT EXISTS sent (id INTEGER PRIMARY KEY, ts_ms INTEGER, kind TEXT, "
                            "chat TEXT, thread INTEGER, status TEXT, ok INTEGER, text TEXT)")
                con.execute("INSERT INTO sent (ts_ms, kind, chat, thread, status, ok, text) VALUES (?,?,?,?,?,?,?)",
                            (int(time.time() * 1000), kind, str(chat), thread, str(status), int(ok), text))
                con.commit()
            finally:
                con.close()
        except Exception as e:
            logger.warning(f"Telegram send log not written: {e!r}")

    def _lock(self) -> asyncio.Lock:
        if self._send_lock is None:
            self._send_lock = asyncio.Lock()
        return self._send_lock

    def _redact(self, e: BaseException) -> str:
        """An error's repr without the bot token (aiohttp errors can carry the request URL /bot<token>/...)."""
        text, (token, _) = repr(e), self._creds()
        return text.replace(token, '<token>') if token else text

    async def _post(self, method: str, timeout: float, priority: bool = False, **kw):
        """POST to the Bot API under the send lock; a 429 waits its retry_after (<= 60 s) and retries twice.
        Returns (status, body text)."""
        token, _ = self._creds()
        if self._session is None:
            self._session = aiohttp.ClientSession()
        if priority:
            self._prio_waiting += 1
            try:
                await asyncio.wait_for(self._lock().acquire(), self.PRIORITY_LOCK_WAIT_SEC)
            except asyncio.TimeoutError:
                raise ConnectionError(f"send lock busy for {self.PRIORITY_LOCK_WAIT_SEC:.0f}s")
            finally:
                self._prio_waiting -= 1
        else:
            # a briefing / photo lets waiting trading instructions go first (bounded, so it is never starved forever)
            waited = 0.0
            while self._prio_waiting and waited < 30.0:
                await asyncio.sleep(0.2)
                waited += 0.2
            await self._lock().acquire()
        try:
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
        finally:
            self._lock().release()

    @property
    def enabled(self) -> bool:
        return self.cfg.enabled

    def wants(self, event: str) -> bool:
        return self.enabled and any(event.startswith(e) for e in self.cfg.events)

    def send(self, event: str, title: str, text: str, card: Optional[str] = None):
        """Fire-and-forget; `event` is matched against notify.events (ENTRY, TP, SL, ZONE); `card` identifies the card
        for the outbox's staleness check."""
        meta = None
        if card:
            self._seq += 1
            self._last_event[card] = self._seq
            meta = {'card': card, 'event': event, 'seq': self._seq}
        if not self.wants(event):
            return
        loop = asyncio.get_running_loop()
        import re
        plain = re.sub(r'</?[a-zA-Z][^>]*>', '', text)
        for coro in (self._toast(title, plain), self._telegram(f"<b>{title}</b>\n{text}", html=True, topic='signals', priority=True,
                                                                     meta=meta)):
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
            self._log_sent('photo', chat, thread, caption, status, status == 200)
            if status != 200:
                logger.warning(f"Telegram photo failed: HTTP {status} {body[:200]}")
        except Exception as e:
            self._log_sent('photo', chat, thread, caption, self._redact(e)[:200], False)
            logger.warning(f"Telegram photo failed: {self._redact(e)}")

    async def _send_chunks(self, chunks, topic: str = 'alerts'):
        for c in chunks:
            await self._telegram(c, html=True, topic=topic)

    async def _telegram(self, text: str, html: bool = False, topic: str = 'alerts', priority: bool = False,
                        meta: Optional[Dict] = None):
        token, _ = self._creds()
        if not token:
            return
        for chat, thread in self._targets(topic):
            await self._telegram_to(token, chat, thread, text, html, priority, meta=meta)

    async def _telegram_to(self, token: str, chat, thread, text: str, html: bool, priority: bool = False,
                           queue: bool = True, meta: Optional[Dict] = None) -> bool:
        """One message to one destination; True when Telegram took it. With `priority` (a trading instruction) a failed
        delivery (HTTP 5xx / 429 / a network error / a busy lock) goes to the outbox for the retry loop (audit B05)."""
        retryable = False
        try:
            payload = {'chat_id': chat, 'text': text[:4000], 'disable_web_page_preview': True}
            if thread:
                payload['message_thread_id'] = thread
            if html:
                payload['parse_mode'] = 'HTML'
            status, body = await self._post('sendMessage', 10, priority=priority, json=payload)
            if status == 200:
                self._log_sent('message', chat, thread, text, status, True)
                return True
            body = body[:200]
            if html and status == 400 and "can't parse entities" in body:
                # a bare '<' in the text ("R:R 1.55 < 2", 2026-10-06 09:16) breaks Telegram's HTML: the
                # message goes out as plain text instead of not at all
                import re
                return await self._telegram_to(token, chat, thread, re.sub(r'</?[a-zA-Z][^>]*>', '', text), False,
                                               priority, queue, meta)
            retryable = status >= 500 or status == 429
            self._log_sent('message', chat, thread, text, f"{status} {body}", False)
            logger.warning(f"Telegram notification failed: HTTP {status} {body}")
        except Exception as e:
            retryable = True
            self._log_sent('message', chat, thread, text, self._redact(e)[:200], False)
            logger.warning(f"Telegram notification failed: {self._redact(e)}")    # repr: a timeout's str() is empty
        if priority and queue and retryable:
            self._outbox.append({'text': text, 'chat': chat, 'thread': thread, 'html': html, 'ts': time.time(),
                                 **(meta or {})})
            self._save_outbox()
            self.resume()
        return False

    async def close(self):
        if self._retry_task is not None:
            self._retry_task.cancel()
        self._save_outbox()
        for task in list(self._tasks):
            task.cancel()
        if self._tasks:
            await asyncio.wait(self._tasks, timeout=2)
        if self._session:
            await self._session.close()
