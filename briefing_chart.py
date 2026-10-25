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
BARS = 60                                  # 10 days of 4h candles (the owner: the 1h was unreadable against
                                           # daily / weekly zones)


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


def plan(price: float, zones: List[Dict], atr_1d: Optional[float] = None, ath: Optional[float] = None,
         ath_days: int = 0, atr_1h: Optional[float] = None) -> Dict:
    """
    The two scenarios of the card (eng-74, the 2026-10-07 review):
    - price INSIDE a zone: long = a 1h close above it + a retest, short = a 1h close below it + a retest;
    - price BETWEEN zones: long = the retest of the nearest support from above with a reaction, short = the retest of
      the nearest resistance from below with a rejection;
    a retest / close counts within the zone's measured pierce (`tol`: Murphy - zones, not prices; Bulkowski - the
    close beyond decides, not an exact touch); the stop beyond the WHOLE zone + `pad` (the p80 pierce clamped to 0.5-1 ATR(1h) -
    Osler: stops cluster just beyond levels; was a quarter of the zone / 0.1%: ETH's stop sat 6 dollars below the
    edge); targets are real zones' near edges only - ATR steps only above the highest high of the history held
    (`ath`, price discovery), labelled; percentages from the ENTRY.
    """
    up = sorted([z for z in zones if z['side'] == 1], key=lambda z: z['lo'])          # near -> far
    dn = sorted([z for z in zones if z['side'] == -1], key=lambda z: -z['hi'])        # near -> far
    cur = next((z for z in zones if z['side'] == 0), None)
    names = {}
    for i, z in enumerate(up):
        names[id(z)] = [('ЛОКАЛЬНОЕ СОПРОТИВЛЕНИЕ', 'первая зона для шорта', RED3),
                        ('СОПРОТИВЛЕНИЕ', 'возможен отскок / ложный пробой', RED2),
                        ('ГЛОБАЛЬНОЕ СОПРОТИВЛЕНИЕ', 'здесь основная ликвидность, фиксация прибыли', RED)][min(i, 2)]
    for i, z in enumerate(dn):
        names[id(z)] = [('БЛИЖАЙШАЯ ПОДДЕРЖКА', 'первая зона для лонга', GREEN),
                        ('ПОДДЕРЖКА', 'возможен отскок / ложный пробой', GREEN),
                        ('КЛЮЧЕВАЯ ПОДДЕРЖКА', 'глобальный уровень', GREEN2)][min(i, 2)]
    if cur:
        names[id(cur)] = ('ЗОНА РЕАКЦИИ', 'цена в зоне: ждём закрытие 1h за ней', BLUE)
    out = {'names': names, 'cur': cur, 'up': up, 'dn': dn, 'long': None, 'short': None}

    def targets(side, entry, first=None):
        # eng-168v (audit #7, traced on 16 days of saved scenarios): the CURRENT zone (price inside it at the post) lay
        # between a support-bounce / resistance-fade entry and its TP1 in 125 entered scenarios, at a median 0.52R -
        # targets were taken from the resistances / supports only, so the first obstacle was skipped and 104 of them
        # passed R:R >= 1 on a farther zone. The current zone beyond the entry is a target / obstacle like the others.
        pool = up if side > 0 else dn
        if cur is not None and side * ((cur['lo'] if side > 0 else cur['hi']) - entry) > 0:
            pool = sorted(pool + [cur], key=lambda z: z['lo'] if side > 0 else -z['hi'])
        # a range trade's first target is the zone's opposite boundary (buy support, sell resistance)
        tg = [first] if first is not None and side * (first - entry) > 0 else []
        for z in pool:
            # the zone's near edge; when the entry already sits inside the zone, its level price, else its far edge
            # (ETH's short at 2 564 inside the support 2 484-2 568: the target is 2 484, not 2 397 beyond it)
            near, far = (z['lo'], z['hi']) if side > 0 else (z['hi'], z['lo'])
            pick = next((p for p in (near, z.get('mid', near), far) if side * (p - entry) > z.get('tol', 0.0)), None)
            if pick is not None and (not tg or side * (pick - tg[-1]) > 0):
                tg.append(pick)
            if len(tg) == 3:
                break
        note = ''
        if side > 0 and len(tg) < 3 and atr_1d and ath and max([entry] + tg) >= ath:
            # price discovery: above the highest high of the history held there is no level - daily-ATR steps
            while len(tg) < 3:
                tg.append(max([entry] + tg) + atr_1d)
            note = f"выше максимума за {ath_days} дн.: цели = +ATR дня"
        elif len(tg) < 3 and tg:
            note = 'дальше уровней в окне брифинга нет'
        return tg, note

    def push_stop(side, stop):
        """A stop inside another zone goes beyond that zone's far edge + its pad (Osler: stops cluster just beyond a
        level - BTC's short stop 84 087 sat inside the resistance 83 577-84 273)."""
        # eng-168j (audit): beyond EVERY zone the stop lands in (one push left it inside the next stacked zone). A chain
        # that makes the stop too wide is not published: scenario() rejects R:R < 1 with the pushed stop (ETH's long
        # stop at -3.8% was published before that check existed)
        for z in (up if side < 0 else dn):                   # near -> far
            if z['lo'] - z.get('tol', 0.0) <= stop <= z['hi'] + z.get('tol', 0.0):
                stop = (z['hi'] + z.get('pad', 0.0)) if side < 0 else (z['lo'] - z.get('pad', 0.0))
        return stop

    def scenario(side, e0, e1, stop, cond, tag, first=None, zone=None):
        # eng-168y: the confirming candle follows the governing zone's timeframe (4h for 4h / 1d / higher map levels)
        tf = (zone or {}).get('conf_tf', '1h')
        cond = cond.replace('1h', tf)
        e = (e0 + e1) / 2
        stop = push_stop(side, stop)
        tg, note = targets(side, e, first)
        if not tg:
            return None
        # eng-168k (audit): R:R >= 1 from the WORST price of the entry range (the web checklist's measure too)
        worst = max(e0, e1) if side > 0 else min(e0, e1)
        # eng-168x (the owner): the briefing is ANALYSIS - a possible scenario, not a trade order. A scenario whose TP1 is
        # closer than its stop (R:R < 1 from the worst entry) is still shown, marked 'as a trade: unfavourable'
        # (rr_ok False); it was dropped, and with the honest obstacle map (eng-168v) most cards had no scenario at all.
        # The trade-grade scenarios (rr_ok) are preferred when choosing a variant and tallied apart.
        rr_ok = side * (tg[0] - worst) >= abs(worst - stop)
        return {'entry': (e0, e1), 'targets': tg, 'stop': stop, 'cond': cond, 'note': note, 'tag': tag, 'rr_ok': rr_ok,
                'conf_tf': tf,
                # eng-168o (audit #4): the breakeven share on the same basis as the R:R check - the worst entry
                'p': abs(worst - stop) / (abs(worst - stop) + abs(tg[0] - worst))}
    def bounce():
        """Long from the nearest support below: its test + a bullish 1h reaction candle."""
        if not dn:
            return None
        z = dn[0]
        return scenario(1, z['lo'], z['hi'] + z.get('tol', 0.0), z['lo'] - z.get('pad', 0.0),
                        f"тест зоны {_fmt(z['lo'])}–{_fmt(z['hi'])} и бычья свеча 1h с закрытием выше "
                        f"{_fmt(z['hi'] + z.get('tol', 0.0))}", 'отскок от поддержки', zone=z)

    def fade():
        """Short from the nearest resistance above: its test + a bearish 1h reaction candle (the reference card)."""
        if not up:
            return None
        z = up[0]
        return scenario(-1, z['lo'] - z.get('tol', 0.0), z['hi'], z['hi'] + z.get('pad', 0.0),
                        f"тест зоны {_fmt(z['lo'])}–{_fmt(z['hi'])} и медвежья свеча 1h с закрытием ниже "
                        f"{_fmt(z['lo'] - z.get('tol', 0.0))}", 'отказ от сопротивления', zone=z)

    if cur:
        tol, pad = cur.get('tol') or 0.0, cur.get('pad', 0.0)
        # eng-168n (audit #3): inside the current zone the variant follows WHERE the price is in it, not the best R:R
        # (the edge variants won by their short stop even with price pressed against the opposite edge). An edge-to-
        # edge trade only in a zone at least 1.5 1h-ATR wide (a narrower one is eaten by the reaction candle); its
        # entry band at most 0.3 of the zone from the edge. A preferred variant that fails R:R >= 1 (worst entry,
        # pushed stop) falls back to the next valid one.
        width = cur['hi'] - cur['lo']
        a1h = atr_1h or (atr_1d / 5 if atr_1d else 0.0)
        wide = bool(a1h) and width >= 1.5 * a1h
        pos = (price - cur['lo']) / width if width > 0 else 0.5
        band = min(tol, 0.3 * width) if width > 0 else tol

        def first_valid(*cands):
            # eng-168x: the first trade-grade (R:R >= 1) variant in the position's order, else the first possible one
            return next((c for c in cands if c and c.get('rr_ok')), None) or next((c for c in cands if c), None)

        def mark(c):
            if c:
                c['cur_bound'] = True          # tied to the current zone: the pair cancels each other (OCO)
            return c
        up_break = lambda: mark(scenario(1, cur['hi'], cur['hi'] + tol, cur['lo'] - pad,
                                         f"закрытие 1h выше {_fmt(cur['hi'])}, ретест и бычья свеча 1h с закрытием выше {_fmt(cur['hi'] + tol)}",
                                         'закрепление выше', zone=cur))
        from_low = lambda: mark(scenario(1, cur['lo'], cur['lo'] + band, cur['lo'] - pad,
                                         f"тест низа {_fmt(cur['lo'])} (допуск {_fmt(band)}) и бычья свеча 1h с закрытием выше {_fmt(cur['lo'] + band)}",
                                         'от низа зоны', first=cur['hi'], zone=cur)) if wide else None
        dn_break = lambda: mark(scenario(-1, cur['lo'] - tol, cur['lo'], cur['hi'] + pad,
                                         f"закрытие 1h ниже {_fmt(cur['lo'])}, ретест и медвежья свеча 1h с закрытием ниже {_fmt(cur['lo'] - tol)}",
                                         'закрепление ниже', zone=cur))
        from_top = lambda: mark(scenario(-1, cur['hi'] - band, cur['hi'], cur['hi'] + pad,
                                         f"тест верха {_fmt(cur['hi'])} (допуск {_fmt(band)}) и медвежья свеча 1h с закрытием ниже {_fmt(cur['hi'] - band)}",
                                         'от верха зоны', first=cur['lo'], zone=cur)) if wide else None
        if pos >= 0.65:
            out['long'] = first_valid(up_break(), bounce(), from_low())
        elif pos <= 0.40 and wide:
            out['long'] = first_valid(from_low(), bounce(), up_break())
        else:
            out['long'] = first_valid(bounce(), up_break(), from_low())
        if pos <= 0.35:
            out['short'] = first_valid(dn_break(), fade(), from_top())
        elif pos >= 0.60 and wide:
            out['short'] = first_valid(from_top(), fade(), dn_break())
        else:
            out['short'] = first_valid(fade(), dn_break(), from_top())
        if out['long'] and out['short'] and out['long'].get('cur_bound') and out['short'].get('cur_bound'):
            out['oco'] = True
        # eng-168o (audit #4): a rejected candidate left 'нет выгодного входа' on the card although another variant
        # of that side was chosen - the skip text stays only when the side has no scenario
        for side_ in ('long', 'short'):
            if out[side_]:
                out.pop('skip_' + side_, None)
    else:
        if dn:
            z = dn[0]
            out['long'] = scenario(1, z['lo'], z['hi'] + z.get('tol', 0.0), z['lo'] - z.get('pad', 0.0),
                                   f"тест зоны {_fmt(z['lo'])}–{_fmt(z['hi'])} и бычья свеча 1h с закрытием выше "
                                   f"{_fmt(z['hi'] + z.get('tol', 0.0))}", 'отскок от поддержки', zone=z)
        if up:
            z = up[0]
            out['short'] = scenario(-1, z['lo'] - z.get('tol', 0.0), z['hi'], z['hi'] + z.get('pad', 0.0),
                                    f"тест зоны {_fmt(z['lo'])}–{_fmt(z['hi'])} и медвежья свеча 1h с закрытием ниже "
                                    f"{_fmt(z['lo'] - z.get('tol', 0.0))}", 'отказ от сопротивления', zone=z)
    return out


def render(name: str, candles: List[List[float]], price: float, zones: List[Dict], atr_1h: Optional[float],
           bias_text: str = '', atr_1d: Optional[float] = None, source: str = 'Binance',
           candles_1h: Optional[List[List[float]]] = None, ath: Optional[float] = None, ath_days: int = 0,
           hi24: Optional[float] = None, lo24: Optional[float] = None, context_text: str = '',
           tf_label: str = '4h') -> bytes:
    """`candles`: 4h candles drawn on the chart; `atr_1h`: the drawn timeframe's ATR (4h); `candles_1h` for the 24h
    change / high / low."""
    """PNG bytes of the card. `candles`: 1h [ts, o, h, l, c, ...], oldest first (the forming one may be last)."""
    p = plan(price, zones, atr_1d, ath, ath_days)
    c = candles[-BARS:]
    day = (candles_1h or [])[-24:] or candles[-6:]
    # the 24h extremes from the caller's minute candles when it has them (the 1h candles lag a minute after the hour:
    # XAU showed a 24h low of 4 114 with the price at 4 093)
    hi24 = max(hi24 if hi24 is not None else max(x[2] for x in day), price)
    lo24 = min(lo24 if lo24 is not None else min(x[3] for x in day), price)
    chg = (price / day[0][1] - 1) * 100
    W, H = 9.21, 12.7
    fig = plt.figure(figsize=(W, H), dpi=100)
    fig.patch.set_facecolor('white')

    # ---- header
    fig.text(0.037, 0.972, _fmt(price), fontsize=38, weight='bold', color=GREEN if chg >= 0 else RED, va='top')
    fig.text(0.037, 0.912, f"{name}  ·  {tf_label}  ·  за сутки {chg:+.2f}%", fontsize=13.5, color=GREY, va='top')
    for k, (lab, val) in enumerate((('Макс. 24ч', _fmt(hi24)), ('Мин. 24ч', _fmt(lo24)),
                                    (f"ATR {tf_label.replace('h', 'ч')}", (f"{atr_1h:,.0f}".replace(',', ' ') if atr_1h and atr_1h >= 10
                                               else f"{atr_1h:.3g}" if atr_1h else '—')))):
        fig.text(0.64, 0.972 - k * 0.0255, lab, fontsize=12, color=GREY, va='top')
        fig.text(0.963, 0.972 - k * 0.0255, val, fontsize=12, weight='bold', ha='right', va='top')
    for k, tf in enumerate(('1м', '15м', '1ч', '4ч', '1д')):
        x = 0.04 + k * 0.073
        if tf == tf_label.replace('h', 'ч'):
            fig.patches.append(FancyBboxPatch((x - 0.018, 0.866), 0.05, 0.022, transform=fig.transFigure,
                                              boxstyle='round,pad=0.003', fc='#eef0f3', ec='none'))
        fig.text(x, 0.877, tf, fontsize=12.5, color='#333' if tf == tf_label.replace('h', 'ч') else GREY, va='center')
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
    ys += [t for side in ('long', 'short') if p[side] for t in p[side]['targets'][:3]]   # the paths stay inside
    lo_y, hi_y = min(ys), max(ys)
    pad = (hi_y - lo_y) * 0.05
    y0, y1 = lo_y - pad, hi_y + pad
    ax.set_ylim(y0, y1)
    xmax = n / 0.6                                   # candles in the left 60%, the paths on the right
    ax.set_xlim(-1, xmax)

    def fy(v):                                       # data y -> figure y
        return 0.245 + 0.61 * (v - y0) / (y1 - y0)
    tags: List[list] = []
    # labels of close zones pushed apart (each takes ~5% of the chart's height: two lines of text)
    label_y, gap = {}, (y1 - y0) * 0.075
    for z in sorted(zones, key=lambda z: (z['lo'] + z['hi']) / 2):
        y = (z['lo'] + z['hi']) / 2
        if label_y:
            y = max(y, max(label_y.values()) + gap)
        label_y[id(z)] = y
    for z in zones:
        title, sub, col = p['names'].get(id(z), ('ЗОНА', '', GREY))
        ax.axhspan(z['lo'], z['hi'], color=col, alpha=0.17, zorder=1)
        for edge in (z['lo'], z['hi']):
            ax.axhline(edge, color=col, lw=1.0, alpha=0.9, zorder=2)
        ym = label_y.get(id(z), (z['lo'] + z['hi']) / 2)
        ax.annotate(title, (1.5, ym), xytext=(0, 1), textcoords='offset points', fontsize=13, weight='bold',
                    color=col, va='bottom', zorder=6)
        sub = z.get('desc') or (f"{sub} · {z['label']}" if z.get('label') else sub)
        sub = sub if len(sub) <= 95 else sub[:94] + '…'              # one line inside the chart
        ax.annotate(sub, (1.5, ym), xytext=(0, -10), textcoords='offset points', fontsize=8.8, color='#333',
                    va='top', zorder=6)
        ax.text(xmax * 0.455, ym, f"{_fmt(z['lo'])} – {_fmt(z['hi'])}", fontsize=12, weight='bold', va='center',
                zorder=6)
        if z['side'] != 0:
            edge = z['lo'] if z['side'] == 1 else z['hi']           # the near edge, as the targets
            tags.append([fy(edge), f"{_fmt(edge)}\n{_pct(edge, price)}", col])
    ax.axhline(price, color='#333', ls=(0, (5, 4)), lw=0.9, zorder=4)
    tags.append([fy(price), f"{_fmt(price)}\n{datetime.now(timezone.utc):%H:%M} UTC", DARK])
    # right-hand tags pushed apart so none covers another (the price tag keeps its place)
    tags.sort(key=lambda t: t[0])
    k0 = next(i for i, t in enumerate(tags) if t[2] == DARK)
    for i in range(k0 + 1, len(tags)):
        tags[i][0] = max(tags[i][0], tags[i - 1][0] + 0.038)
    for i in range(k0 - 1, -1, -1):
        tags[i][0] = min(tags[i][0], tags[i + 1][0] - 0.038)
    for ty, text, colr in tags:
        fig.text(0.877, ty, text, fontsize=11.5, weight='bold', color='white', va='center', linespacing=1.0,
                 bbox=dict(boxstyle='round,pad=0.35', fc=colr, ec='none'))
    # the window's extremes, labelled (the reference marks them)
    ih = max(range(n), key=lambda i: c[i][2])
    il = min(range(n), key=lambda i: c[i][3])
    ax.annotate(_fmt(c[ih][2]), (ih, c[ih][2]), xytext=(0, 4), textcoords='offset points', ha='center',
                fontsize=10, weight='bold', zorder=6)
    ax.annotate(_fmt(c[il][3]), (il, c[il][3]), xytext=(0, -4), textcoords='offset points', ha='center', va='top',
                fontsize=10, weight='bold', zorder=6)
    # the scenarios' paths from the last candle: solid to TP1, dashed beyond
    import numpy as np
    for side, colr in (('long', GREEN2), ('short', RED)):
        sc = p[side]
        if not sc:
            continue
        pts = [(n - 1, price), (n + (xmax - n) * 0.15, (sc['entry'][0] + sc['entry'][1]) / 2)]
        for k, t in enumerate(sc['targets'][:3]):
            pts.append((n + (xmax - n) * (0.35 + 0.22 * k), t))
        xs_, ys_ = np.array([q[0] for q in pts]), np.array([q[1] for q in pts])
        ax.plot(xs_[:3], ys_[:3], color=colr, lw=2.2, zorder=5)
        ax.plot(xs_[2:], ys_[2:], color=colr, lw=2.2, ls=(0, (3, 2)), zorder=5)
        ax.annotate('', xy=(xs_[-1], ys_[-1]), xytext=(xs_[-2], ys_[-2]),
                    arrowprops=dict(arrowstyle='->', color=colr, lw=2.2, ls='--'), zorder=5)
    # scenario tags
    if p['long']:
        ax.text(xmax * 0.8, y1 - pad * 0.3, f"ЛОНГ СЦЕНАРИЙ\n({p['long']['tag']})\n" + (f"безубыточная доля TP1: {p['long']['p'] * 100:.0f}%*" if p['long'].get('rr_ok', True) else 'как сделка невыгодно: цель ближе стопа'),
                fontsize=9.5, weight='bold', color='white', ha='center', va='top', zorder=7, linespacing=1.3,
                bbox=dict(boxstyle='round,pad=0.5', fc=GREEN2, ec='none'))
    if p['short']:
        ax.text(xmax * 0.8, y0 + pad * 0.3, f"ШОРТ СЦЕНАРИЙ\n({p['short']['tag']})\n" + (f"безубыточная доля TP1: {p['short']['p'] * 100:.0f}%*" if p['short'].get('rr_ok', True) else 'как сделка невыгодно: цель ближе стопа'),
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
            fig.text(x0 + 0.015, 0.175, p.get('skip_' + side) or 'нет уровней для сценария', fontsize=10, color=GREY,
                     va='top', linespacing=1.4)
            continue
        e = s['entry']
        em = (e[0] + e[1]) / 2                      # percentages from the ENTRY, not from the current price
        rows = [('Вход:', f"{_fmt(e[0])} – {_fmt(e[1])} ({s['tag']})")]
        for i, t in enumerate(s['targets']):
            rows.append(('Цели:' if i == 0 else '', f"{_fmt(t)}  ({_pct(t, em)} от входа)"))
        rows.append(('Стоп:', f"{'ниже' if side == 'long' else 'выше'} {_fmt(s['stop'])} ({_pct(s['stop'], em)} от входа)"))
        import textwrap
        for i, line in enumerate(textwrap.wrap(s['cond'], 38)):     # long conditions wrap inside the box
            rows.append(('Условия:' if i == 0 else '', line))
        if s.get('note'):
            rows.append(('', s['note']))
        step, fs = (0.0150, 10) if len(rows) <= 7 else (0.0120, 9)      # fit the box: 9 rows at most
        for i, (a, b) in enumerate(rows):
            y = 0.181 - i * step
            fig.text(x0 + 0.015, y, a, fontsize=fs, weight='bold', va='top')
            fig.text(x0 + 0.105, y, b, fontsize=fs, va='top')
    cur = p['cur']
    if cur:
        where = 'В ЗОНЕ' if cur['lo'] <= price <= cur['hi'] else ('У ВЕРХА ЗОНЫ' if price > cur['hi'] else 'У НИЗА ЗОНЫ')
        msg = f"ЦЕНА {where} {_fmt(cur['lo'])} – {_fmt(cur['hi'])}. ЖДЁМ ЗАКРЫТИЯ 1H ЗА НЕЙ."
    else:
        a = _fmt(p['dn'][0]['hi']) if p['dn'] else '—'
        b = _fmt(p['up'][0]['lo']) if p['up'] else '—'
        msg = f"ЦЕНА МЕЖДУ ЗОНАМИ {a} И {b}. ЖДЁМ РЕТЕСТА ОДНОЙ ИЗ НИХ."
    msg_sub = context_text or 'Входить в середине диапазона не рекомендуется.'
    fig.patches.append(FancyBboxPatch((0.02, 0.018), 0.96, 0.05, transform=fig.transFigure,
                                      boxstyle='round,pad=0.006', fc='#fdeeee', ec=RED, lw=1.2))
    fig.text(0.04, 0.058, '⚠  ' + msg, fontsize=11.5, weight='bold', color=RED, va='top')
    fig.text(0.075, 0.036, msg_sub, fontsize=9.5, color=RED, va='top')
    fig.text(0.98, 0.006, '*доля сделок с TP1, при которой сценарий в ноль (по расстояниям, без комиссий); это не прогноз · зоны — прошлые развороты цены, реакция не гарантирована · не совет', fontsize=7, color=GREY, ha='right', va='bottom')
    buf = io.BytesIO()
    fig.savefig(buf, format='png')
    plt.close(fig)
    return buf.getvalue()
