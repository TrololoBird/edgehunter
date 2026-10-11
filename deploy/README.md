# Деплой бота на VPS

Бот держит постоянные соединения с 6 биржами, пишет журнал SQLite и данные рекордера (~270 МБ в сутки), ему нужно
~1–1.5 ГБ RAM. Поэтому — свой VPS с systemd, а не бесплатные PaaS:

- **Railway / Render не подходят**: их сервера в основном в США, а Binance отвечает американским IP ошибкой 451
  (бот не получит данных); диск там временный (журнал и состояние пропадут при каждом переразвёртывании); бесплатного
  тарифа хватает на ~0.5 ГБ RAM.
- **Где брать VPS**: любой провайдер с площадкой в Европе или Азии (Германия, Нидерланды, Финляндия, Сингапур,
  Токио): 2 vCPU, 4 ГБ RAM, 80 ГБ диска — этого хватает с запасом. Перед оплатой проверьте, что с сервера отвечает
  `curl -s https://fapi.binance.com/fapi/v1/ping` (вернёт `{}`), и что страна провайдера не запрещена правилами
  Binance / BingX.
- VPN на сервере не нужен — отсюда пропадут таймауты и «timestamp is invalid», которые даёт VPN на ноутбуке.

## Установка (Ubuntu 24.04, от root)

```bash
git clone <ваш репозиторий> /opt/pump        # или scp -r папку проекта (без .venv, data, history_cache)
bash /opt/pump/deploy/install.sh
```

Скрипт ставит пакеты, синхронизацию времени (chrony — подписанные запросы к BingX требуют точных часов), swap 2 ГБ,
Python 3.14 через uv, venv с зависимостями, фаервол (открыт только SSH) и службу systemd.

Затем перенесите локальные файлы (они не в git):

```bash
scp config.local.toml root@SERVER:/opt/pump/          # ключи демо BingX; добавьте [web] open_browser = false
scp signals.db demo_trades.db scanner_state.json root@SERVER:/opt/pump/     # журнал, демо, открытые карточки
scp -r models root@SERVER:/opt/pump/                   # модель проколов overshoot.json, секторы
chown -R pump:pump /opt/pump
systemctl start pump-bot
```

Перед копированием остановите бот на ноутбуке, чтобы журнал не писался в два места.

## Работа

| Что | Команда |
|---|---|
| статус | `systemctl status pump-bot` |
| лог в реальном времени | `journalctl -u pump-bot -f` (и `/opt/pump/scanner.log`) |
| перезапуск (корректный, с сохранением) | `systemctl restart pump-bot` |
| обновление кода | `cd /opt/pump && sudo -u pump git pull && systemctl restart pump-bot` |
| дашборд с ноутбука | `ssh -L 8765:127.0.0.1:8765 root@SERVER`, затем открыть http://127.0.0.1:8765 |
| статистика | `cd /opt/pump && sudo -u pump .venv/bin/python stats.py --days 7` |

Всё после install.sh одной командой: `bash /opt/pump/deploy/setup_server.sh` (свежий код, polars 1.44.2, конфиг,
публичный дашборд, запуск). Бот слушает только 127.0.0.1; снаружи дашборд открыт ПУБЛИЧНО (без логина) через Caddy по
HTTPS на `https://<ip>.sslip.io` (`deploy/web_access.sh`). Пост в Telegram (`/api/briefing?send=1`) и `/api/debug`
отвечают только локальным запросам (`webui._local`).

## Резервные копии

Раз в сутки (cron от root):

```bash
0 4 * * * sqlite3 /opt/pump/signals.db ".backup /opt/pump/backup/signals-$(date +\%F).db" && find /opt/pump/backup -mtime +14 -delete
```

## Архивные прогоны

На VPS их можно запускать рядом с ботом (памяти хватает): `research_turtle.py`, `research_cards.py`,
`research_maniac.py`, затем `pretrain.py` — с `nice -n 10`, чтобы не мешать боту.
