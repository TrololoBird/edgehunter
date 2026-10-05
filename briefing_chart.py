"""
The briefing card as a picture, laid out as the owner's reference (an analyst's BingX card, 2026-10-05):

  header   big price (green / red by the day), "<SYMBOL> · 1h · за сутки +x%", 24h high / low and the 1h ATR at the
           right; the timeframe tabs 1м 15м 1ч 4ч 1д with 1ч selected
  chart    ~3 days of 1h candles in the left ~60% of the width (room on the right), dates under it; six horizontal
           zones - ГЛОБАЛЬНОЕ СОПРОТИВЛЕНИЕ / СОПРОТИВЛЕНИЕ / ЛОКАЛЬНОЕ СОПРОТИВЛЕНИЕ / ЗОНА ПОДДЕРЖКИ / РЕАКЦИЯ /
           СЛЕДУЮЩАЯ ПОДДЕРЖКА / КЛЮЧЕВАЯ ПОДДЕРЖКА - each a tinted band with its name and role on the left, "lo – hi"
           in the middle and a coloured tag at the right with its upper edge and the distance in %; the price as a
           dashed line with a dark tag "price / HH:MM UTC"; the LONG tag (пробой и закрепление) near the top, the
           SHORT tag (пробой поддержки) near the bottom
  boxes    ЛОНГ (только после подтверждения): entry just above the watched zone after acceptance, targets at the three
           resistances' upper edges, stop below the next support's upper edge, condition "пробой и ретест зоны X";
           ШОРТ (при подтверждении): entry in the local resistance (отскок / реакция), targets the watched zone's low
           and the supports' upper edges, stop above the second resistance, condition "сигнал на разворот в зоне"
  footer   "СЕЙЧАС ЦЕНА ВНУТРИ ЗОНЫ lo – hi. ЖДЁМ ПОДТВЕРЖДЕНИЯ." / "Входить в середине диапазона не рекомендуется."

The % in the scenario tags is NOT the analyst's unexplained "probability": it is the driftless random-walk chance that
TP1 trades before the stop from the entry (stop distance / (stop + TP1 distance)), marked with * and explained.
"""
import io
from datetime import datetime, timezone
from typing import Dict, List, Optional

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import FancyBboxPatch, Rectangle  # noqa: E402

RED, RED2, RED3 = '#c0392b', '#d9534f', '#e57373'
BLUE, GREEN, GREEN2 = '#3b5bdb', '#2f9e44', '#1e7b3a'
GREY, DARK = '#7a7a7a', '#222222'
UP_C, DN_C = '#26a69a', '#ef5350'
BARS = 66                                  # ~2.75 days of 1h candles, as the reference


def _fmt(p: float) -> str:
    if p is None:
        return '—'
    if p >= 1000:
        return f"{p:,.0f}".replace(',', ' ')
    if p >= 100:
        return f"{p:,.1f}".replace(',', ' ')
    if p >= 1:
        return f"{p:.3f}".rstrip('0').rstrip('.') if p < 10 else f"{p:.2f}"
    return f"{p:.5g}"


def _pct(x: float, price: float) -> str:
    return f"{(x / price - 1) * 100:+.1f}%"


def plan(price: float, zones: List[Dict], atr_1d: Optional[float] = None) -> Dict:
    up = sorted([z for z in zones if z['side'] == 1], key=lambda z: z['lo'])          # local, resistance, global
    dn = sorted([z for z in zones if z['side'] == -1], key=lambda z: -z['hi'])        # next, key
    cur = next((z for z in zones if z['side'] == 0), None)
    names = {}
    for i, z in enumerate(up):
        names[id(z)] = [('ЛОКАЛЬНОЕ СОПРОТИВЛЕНИЕ', 'первая зона для шорта', RED3),
                        ('СОПРОТИВЛЕНИЕ', 'возможен отскок / ложный пробой', RED2),
                        ('ГЛОБАЛЬНОЕ СОПРОТИВЛЕНИЕ', 'здесь основная ликвидность, фиксация прибыли', RED)][min(i, 2)]
    for i, z in enumerate(dn):
        names[id(z)] = [('СЛЕДУЮЩАЯ ПОДДЕРЖКА', 'где возможен отскок', GREEN),
                        ('КЛЮЧЕВАЯ ПОДДЕРЖКА', 'глобальный уровень', GREEN2)][min(i, 1)]
    # role reversal (polarity): the watched zone's role follows the price AT THE POST - inside it is a reaction zone,
    # above it a support (its retest from above is the long), below it a resistance (its retest from below the short);
    # the scenarios are built from that same position, so the card cannot contradict the price
    rel = None
    if cur:
        rel = 'inside' if cur['lo'] <= price <= cur['hi'] else ('above' if price > cur['hi'] else 'below')
        names[id(cur)] = {'inside': ('ЗОНА РЕАКЦИИ', 'цена в зоне: ждём выход и закрепление', BLUE),
                          'above': ('ЗОНА ПОДДЕРЖКИ', 'пробита вверх: ретест сверху = лонг', BLUE),
                          'below': ('ЗОНА СОПРОТИВЛЕНИЯ', 'пробита вниз: ретест снизу = шорт', BLUE)}[rel]
    out = {'names': names, 'cur': cur, 'rel': rel, 'up': up, 'dn': dn, 'long': None, 'short': None}
    if not cur:
        return out
    tick = price * 0.0001
    buf = max((cur['hi'] - cur['lo']) * 0.25, price * 0.001)          # beyond the zone, not on its edge
    # LONG: acceptance above the zone (or, once above it, its retest); stop below the zone; targets the resistances
    if rel == 'above':
        e0, e1, cond = cur['lo'], cur['hi'], f"ретест зоны {_fmt(cur['lo'])}–{_fmt(cur['hi'])} сверху и реакция"
    else:
        e0, e1, cond = cur['hi'], cur['hi'] + max(price * 0.0007, tick), f"закрытие 1h выше {_fmt(cur['hi'])} и ретест"
    stop = cur['lo'] - buf
    tg = [z['hi'] for z in up if z['hi'] > max(e1, price)][:3]
    discovery = len(tg) < 3 and bool(atr_1d)
    while discovery and len(tg) < 3:
        tg.append((tg[-1] if tg else max(e1, price)) + atr_1d)
    if tg:
        e = (e0 + e1) / 2
        out['long'] = {'entry': (e0, e1), 'targets': tg, 'stop': stop, 'cond': cond,
                       'note': 'выше зон нет: цели = +ATR дня' if discovery else '',
                       'tag': 'закрепление выше' if rel != 'above' else 'ретест поддержки',
                       'p': (e - stop) / ((e - stop) + (tg[0] - e))}
    # SHORT: the zone's breakdown (or, once below it, its retest from below); stop above the zone; targets the supports
    if rel == 'below':
        e0, e1, cond = cur['lo'], cur['hi'], f"ретест зоны {_fmt(cur['lo'])}–{_fmt(cur['hi'])} снизу и отказ"
    else:
        e0, e1, cond = cur['lo'] - max(price * 0.0007, tick), cur['lo'], f"закрытие 1h ниже {_fmt(cur['lo'])} и ретест"
    stop = cur['hi'] + buf
    tg = [z['hi'] for z in dn if z['hi'] < min(e0, price)][:3]     # in front of the supports (their upper edge)
    if tg:
        e = (e0 + e1) / 2
        out['short'] = {'entry': (e0, e1), 'targets': tg, 'stop': stop, 'cond': cond, 'note': '',
                        'tag': 'пробой поддержки' if rel != 'below' else 'ретест сопротивления',
                        'p': (stop - e) / ((stop - e) + (e - tg[0]))}
    return out


def render(name: str, candles: List[List[float]], price: float, zones: List[Dict], atr_1h: Optional[float],
           bias_text: str = '', atr_1d: Optional[float] = None, source: str = 'Binance') -> bytes:
    """PNG bytes of the card. `candles`: 1h [ts, o, h, l, c, ...], oldest first (the forming one may be last)."""
    p = plan(price, zones, atr_1d)
    c = candles[-BARS:]
    day = candles[-24:]
    hi24, lo24 = max(x[2] for x in day), min(x[3] for x in day)
    chg = (price / day[0][1] - 1) * 100
    W, H = 9.21, 12.7
    fig = plt.figure(figsize=(W, H), dpi=100)
    fig.patch.set_facecolor('white')

    # ---- header
    fig.text(0.037, 0.972, _fmt(price), fontsize=38, weight='bold', color=GREEN if chg >= 0 else RED, va='top')
    fig.text(0.037, 0.912, f"{name}  ·  1h  ·  за сутки {chg:+.2f}%", fontsize=13.5, color=GREY, va='top')
    for k, (lab, val) in enumerate((('Макс. 24ч', _fmt(hi24)), ('Мин. 24ч', _fmt(lo24)),
                                    ('ATR 1ч', (f"{atr_1h:,.0f}".replace(',', ' ') if atr_1h and atr_1h >= 10
                                               else f"{atr_1h:.3g}" if atr_1h else '—')))):
        fig.text(0.64, 0.972 - k * 0.0255, lab, fontsize=12, color=GREY, va='top')
        fig.text(0.963, 0.972 - k * 0.0255, val, fontsize=12, weight='bold', ha='right', va='top')
    for k, tf in enumerate(('1м', '15м', '1ч', '4ч', '1д')):
        x = 0.04 + k * 0.073
        if tf == '1ч':
            fig.patches.append(FancyBboxPatch((x - 0.018, 0.866), 0.05, 0.022, transform=fig.transFigure,
                                              boxstyle='round,pad=0.003', fc='#eef0f3', ec='none'))
        fig.text(x, 0.877, tf, fontsize=12.5, color='#333' if tf == '1ч' else GREY, va='center')
    if bias_text:
        fig.text(0.42, 0.877, bias_text, fontsize=9.5, color='#555', va='center')

    # ---- chart
    ax = fig.add_axes([0.0, 0.245, 0.87, 0.61])
    n = len(c)
    for i, x in enumerate(c):
        col = UP_C if x[4] >= x[1] else DN_C
        ax.plot([i, i], [x[3], x[2]], color=col, lw=0.9, zorder=3)
        ax.add_patch(Rectangle((i - 0.33, min(x[1], x[4])), 0.66, max(abs(x[4] - x[1]), price * 2e-5), color=col,
                               zorder=3))
    ys = [z['lo'] for z in zones] + [z['hi'] for z in zones] + [x[3] for x in c] + [x[2] for x in c]
    lo_y, hi_y = min(ys), max(ys)
    pad = (hi_y - lo_y) * 0.05
    y0, y1 = lo_y - pad, hi_y + pad
    ax.set_ylim(y0, y1)
    xmax = n / 0.6                                   # candles in the left 60%
    ax.set_xlim(-1, xmax)

    def fy(v):                                       # data y -> figure y
        return 0.245 + 0.61 * (v - y0) / (y1 - y0)
    for z in zones:
        title, sub, col = p['names'].get(id(z), ('ЗОНА', '', GREY))
        ax.axhspan(z['lo'], z['hi'], color=col, alpha=0.17, zorder=1)
        for edge in (z['lo'], z['hi']):
            ax.axhline(edge, color=col, lw=1.0, alpha=0.9, zorder=2)
        ym = (z['lo'] + z['hi']) / 2
        ax.annotate(title, (1.5, ym), xytext=(0, 1), textcoords='offset points', fontsize=13, weight='bold',
                    color=col, va='bottom', zorder=6)
        ax.annotate(sub, (1.5, ym), xytext=(0, -10), textcoords='offset points', fontsize=8.8, color='#333',
                    va='top', zorder=6)
        ax.text(xmax * 0.455, ym, f"{_fmt(z['lo'])} – {_fmt(z['hi'])}", fontsize=12, weight='bold', va='center',
                zorder=6)
        if z['side'] != 0:
            fig.text(0.877, fy(z['hi']), f"{_fmt(z['hi'])}\n{_pct(z['hi'], price)}", fontsize=11.5, weight='bold',
                     color='white', va='center', linespacing=1.0,
                     bbox=dict(boxstyle='round,pad=0.35', fc=col, ec='none'))
    ax.axhline(price, color='#333', ls=(0, (5, 4)), lw=0.9, zorder=4)
    fig.text(0.877, fy(price), f"{_fmt(price)}\n{datetime.now(timezone.utc):%H:%M} UTC", fontsize=11.5,
             weight='bold', color='white', va='center', linespacing=1.0,
             bbox=dict(boxstyle='round,pad=0.35', fc=DARK, ec='none'))
    # scenario tags
    if p['long']:
        ax.text(xmax * 0.8, y1 - pad * 0.3, f"ЛОНГ СЦЕНАРИЙ\n({p['long']['tag']})\nВероятность: {p['long']['p'] * 100:.0f}%*",
                fontsize=9.5, weight='bold', color='white', ha='center', va='top', zorder=7, linespacing=1.3,
                bbox=dict(boxstyle='round,pad=0.5', fc=GREEN2, ec='none'))
    if p['short']:
        ax.text(xmax * 0.8, y0 + pad * 0.3, f"ШОРТ СЦЕНАРИЙ\n({p['short']['tag']})\nВероятность: {p['short']['p'] * 100:.0f}%*",
                fontsize=9.5, weight='bold', color='white', ha='center', va='bottom', zorder=7, linespacing=1.3,
                bbox=dict(boxstyle='round,pad=0.5', fc=RED, ec='none'))
    ax.text(1.5, y0 + pad * 0.15, source, fontsize=13, weight='bold', color='#d0d0d0', zorder=5)
    # axes: price ticks on the right, three dates under the candles
    ax.yaxis.tick_right()
    ax.tick_params(axis='y', labelsize=11, colors=GREY, length=0, pad=-2)
    ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: _fmt(v)))
    ticks = [8, n // 2, n - 6] if n > 16 else []
    ax.set_xticks(ticks)
    ax.set_xticklabels([datetime.fromtimestamp(c[i][0] / 1000, timezone.utc).strftime('%d.%m %H:%M') for i in ticks],
                       fontsize=10, color=GREY)
    ax.tick_params(axis='x', length=0)
    for sp in ax.spines.values():
        sp.set_visible(False)
    ax.grid(axis='y', color='#ececec', zorder=0)

    # ---- scenario boxes
    for k, side in enumerate(('long', 'short')):
        s = p[side]
        x0 = 0.02 + k * 0.49
        col = GREEN if side == 'long' else RED
        fig.patches.append(FancyBboxPatch((x0, 0.083), 0.47, 0.135, transform=fig.transFigure,
                                          boxstyle='round,pad=0.006', fc='#eef7ee' if side == 'long' else '#fdeeee',
                                          ec=col, lw=1.2))
        fig.text(x0 + 0.015, 0.206, 'ЛОНГ' if side == 'long' else 'ШОРТ', fontsize=15, weight='bold', color=col,
                 va='top')
        fig.text(x0 + (0.095 if side == 'long' else 0.098), 0.2015,
                 '(только после подтверждения)' if side == 'long' else '(при подтверждении)', fontsize=9.5,
                 color=col, va='top')
        if not s:
            fig.text(x0 + 0.015, 0.165, 'нет уровней для сценария', fontsize=10, color=GREY)
            continue
        e = s['entry']
        rows = [('Вход:', f"{_fmt(e[0])} – {_fmt(e[1])} ({s['tag']})")]
        for i, t in enumerate(s['targets']):
            rows.append(('Цели:' if i == 0 else '', f"{_fmt(t)}  ({_pct(t, price)})"))
        rows.append(('Стоп:', f"{'ниже' if side == 'long' else 'выше'} {_fmt(s['stop'])} ({_pct(s['stop'], price)})"))
        rows.append(('Условия:', s['cond']))
        if s.get('note'):
            rows.append(('', s['note']))
        for i, (a, b) in enumerate(rows):
            y = 0.181 - i * 0.0150
            fig.text(x0 + 0.015, y, a, fontsize=10, weight='bold', va='top')
            fig.text(x0 + 0.105, y, b, fontsize=10, va='top')
    cur = p['cur']
    inside = cur and cur['lo'] <= price <= cur['hi']
    msg = (f"СЕЙЧАС ЦЕНА ВНУТРИ ЗОНЫ {_fmt(cur['lo'])} – {_fmt(cur['hi'])}. ЖДЁМ ПОДТВЕРЖДЕНИЯ." if inside else
           f"ЦЕНА {'НАД' if cur and price > cur['hi'] else 'ПОД'} ЗОНОЙ {_fmt(cur['lo'])} – {_fmt(cur['hi'])}. "
           f"ЖДЁМ РЕТЕСТА." if cur else 'ЗОН РЯДОМ НЕТ.')
    fig.patches.append(FancyBboxPatch((0.02, 0.018), 0.96, 0.05, transform=fig.transFigure,
                                      boxstyle='round,pad=0.006', fc='#fdeeee', ec=RED, lw=1.2))
    fig.text(0.04, 0.058, '⚠  ' + msg, fontsize=11.5, weight='bold', color=RED, va='top')
    fig.text(0.075, 0.036, 'Входить в середине диапазона не рекомендуется.', fontsize=9.5, color=RED, va='top')
    fig.text(0.98, 0.006, '*случайное блуждание: шанс TP1 раньше стопа по расстояниям, не прогноз · правила бота, '
                          'не совет', fontsize=7, color=GREY, ha='right', va='bottom')
    buf = io.BytesIO()
    fig.savefig(buf, format='png')
    plt.close(fig)
    return buf.getvalue()
