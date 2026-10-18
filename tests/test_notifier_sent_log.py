import asyncio
import sqlite3

from notifier import Notifier


def _rows(path):
    con = sqlite3.connect(path)
    try:
        return con.execute("SELECT kind, chat, thread, status, ok, text FROM sent ORDER BY id").fetchall()
    finally:
        con.close()


def test_sent_messages_are_logged(tmp_path, monkeypatch):
    n = Notifier()
    n.SENT_DB_PATH = str(tmp_path / 'tg_sent.db')
    n.OUTBOX_PATH = str(tmp_path / 'outbox.json')
    replies = iter([(200, '{}'), (500, 'oops')])

    async def fake_post(method, timeout, priority=False, **kw):
        return next(replies)
    monkeypatch.setattr(n, '_post', fake_post)

    assert asyncio.run(n._telegram_to('tok', -100, 7, '<b>ENTRY</b> WAL', True))
    assert not asyncio.run(n._telegram_to('tok', -100, None, 'SL hit', False))
    rows = _rows(n.SENT_DB_PATH)
    assert rows[0] == ('message', '-100', 7, '200', 1, '<b>ENTRY</b> WAL')
    assert rows[1][:2] == ('message', '-100') and rows[1][4] == 0 and rows[1][3].startswith('500')
    assert rows[1][5] == 'SL hit'
