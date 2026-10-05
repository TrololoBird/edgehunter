"""
The briefing card as a picture (the owner's reference: a 1h chart with named zones - global / resistance / local
resistance, the zone price sits in, next / key support - price tags with the distance in %, the long and the short
scenario with entry, three targets, stop and condition, and a warning while price sits inside a zone).

Built from briefing.Briefing.key_zones (the 1h+ zones of the plans' map). The scenario's number is NOT a forecast: it
is the driftless random-walk chance that TP1 trades before the stop (stop distance / (stop + TP1 distance)), labelled
as such - the analyst's "50% / 55%" carry no stated method.
"""
import io
from typing import Dict, List, Optional

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import FancyBboxPatch, Rectangle  # noqa: E402

RED, RED2, RED3 = '#c62828', '#e05555', '#ec8a8a'
BLUE, GREEN, GREEN2 = '#3b5bdb', '#2f9e44', '#1b7a35'
GREY = '#666666'


def _fmt(p: float) -> str:
    if p >= 1000:
        return f"{p:,.0f}".replace(',', ' ')
    if p >= 10:
        return f"{p:,.2f}".replace(',', ' ')
    return f"{p:.6g}"


def plan(price: float, zones: List[Dict], atr_1d: Optional[float] = None) -> Dict:
    """Names, long / short scenarios from the zones (sides: 1 above, 0 inside, -1 below)."""
    up = sorted([z for z in zones if z['side'] == 1], key=lambda z: z['lo'])          # nearest first
    dn = sorted([z for z in zones if z['side'] == -1], key=lambda z: -z['hi'])        # nearest first
    cur = next((z for z in zones if z['side'] == 0), None)
    names = {}
    for i, z in enumerate(up):
        names[id(z)] = (['ЛОКАЛЬНОЕ СОПРОТИВЛЕНИЕ', 'СОПРОТИВЛЕНИЕ', 'ГЛОБАЛЬНОЕ СОПРОТИВЛЕНИЕ'][min(i, 2)],
                        ['первая зона для шорта', 'возможен отскок / ложный пробой',
                         'основная ликвидность, фиксация прибыли'][min(i, 2)], [RED3, RED2, RED][min(i, 2)])
    for i, z in enumerate(dn):
        names[id(z)] = (['СЛЕДУЮЩАЯ ПОДДЕРЖКА', 'КЛЮЧЕВАЯ ПОДДЕРЖКА', 'ГЛОБАЛЬНАЯ ПОДДЕРЖКА'][min(i, 2)],
                        ['где возможен отскок', 'глобальный уровень', 'последний рубеж'][min(i, 2)],
                        [GREEN, GREEN2, GREEN2][min(i, 2)])
    if cur:
        names[id(cur)] = ('ЗОНА ПОДДЕРЖКИ / РЕАКЦИЯ', 'текущая зона, за которой следим', BLUE)
    out = {'names': names, 'cur': cur, 'up': up, 'dn': dn, 'long': None, 'short': None}
    # long: acceptance above the zone price sits in (or the nearest resistance), targets the resistances,
    # stop below the next support
    trig = cur['hi'] if cur else (up[0]['hi'] if up else None)
    tgts = [z['lo'] for z in up if trig is None or z['lo'] > trig][:3]
    discovery = False
    if trig is not None and len(tgts) < 3 and atr_1d:
        # nothing (more) above on the 1h+ map: price discovery - steps of half a daily ATR, labelled as such
        base = tgts[-1] if tgts else trig
        tgts += [base + 0.5 * atr_1d * k for k in range(1, 4 - len(tgts))]
        discovery = True
    if trig is not None and tgts and dn:
        stop = dn[0]['lo']
        out['long'] = {'entry': (trig, trig * 1.0015), 'targets': tgts, 'stop': stop,
                       'cond': f"пробой и ретест зоны {_fmt(trig)}" + ('\nвыше уровней нет: цели по ATR дня'
                                                                              if discovery else ''),
                       'p': (trig - stop) / ((trig - stop) + (tgts[0] - trig))}
    # short: the reaction at the nearest resistance, targets the zone below / supports, stop above the next resistance
    if up:
        top = up[0]
        tg = ([cur['hi']] if cur else []) + [z['hi'] for z in dn]
        stop = up[1]['hi'] if len(up) > 1 else top['hi'] + (0.5 * atr_1d if atr_1d else (top['hi'] - top['lo']) * 2)
        if tg:
            e = top['lo']
            out['short'] = {'entry': (top['lo'], top['hi']), 'targets': tg[:3], 'stop': stop,
                            'cond': 'сигнал на разворот в зоне', 'p': (stop - e) / ((stop - e) + (e - tg[0]))}
    return out


def render(name: str, candles: List[List[float]], price: float, zones: List[Dict], atr_1h: Optional[float],
           bias_text: str = '', atr_1d: Optional[float] = None) -> bytes:
    """PNG bytes. `candles`: 1h [ts, o, h, l, c, ...] (the last ~4 days)."""
    p = plan(price, zones, atr_1d)
    c = candles[-96:]
    day = candles[-24:] if len(candles) >= 24 else candles
    hi24, lo24 = max(x[2] for x in day), min(x[3] for x in day)
    chg = (price / day[0][1] - 1) * 100 if day else 0.0

    fig = plt.figure(figsize=(9.2, 12.6), dpi=100)
    fig.patch.set_facecolor('white')
    # header
    fig.text(0.04, 0.965, _fmt(price), fontsize=34, weight='bold', color=GREEN if chg >= 0 else RED, va='top')
    fig.text(0.04, 0.915, f"{name} · 1h · за сутки {chg:+.2f}%", fontsize=13, color=GREY, va='top')
    if bias_text:
        fig.text(0.04, 0.892, bias_text, fontsize=10.5, color='#333333', va='top')
    for k, (lab, val) in enumerate((('Макс. 24ч', hi24), ('Мин. 24ч', lo24), ('ATR 1ч', atr_1h))):
        fig.text(0.64, 0.965 - k * 0.022, lab, fontsize=11, color=GREY, va='top')
        fig.text(0.96, 0.965 - k * 0.022, (_fmt(val) if lab != 'ATR 1ч' or val >= 1000 else f"{val:.3g}") if val else '—', fontsize=11, weight='bold', ha='right', va='top')

    ax = fig.add_axes([0.0, 0.25, 0.87, 0.62])
    for i, x in enumerate(c):
        col = '#26a69a' if x[4] >= x[1] else '#ef5350'
        ax.plot([i, i], [x[3], x[2]], color=col, lw=0.8, zorder=3)
        ax.add_patch(Rectangle((i - 0.32, min(x[1], x[4])), 0.64, max(abs(x[4] - x[1]), price * 1e-5),
                               color=col, zorder=3))
    lo_y = min([z['lo'] for z in zones] + [x[3] for x in c])
    hi_y = max([z['hi'] for z in zones] + [x[2] for x in c])
    pad = (hi_y - lo_y) * 0.06
    ax.set_ylim(lo_y - pad, hi_y + pad)
    ax.set_xlim(-1, len(c) + 4)
    ax.axhline(price, color='#333', ls='--', lw=0.8, zorder=2)
    for z in zones:
        title, sub, col = p['names'].get(id(z), ('ЗОНА', '', GREY))
        ax.axhspan(z['lo'], z['hi'], color=col, alpha=0.18, zorder=1)
        ax.axhline(z['lo'], color=col, lw=0.8, zorder=1)
        ax.axhline(z['hi'], color=col, lw=0.8, zorder=1)
        ym = (z['lo'] + z['hi']) / 2
        ax.text(1, ym, title, fontsize=12, weight='bold', color=col, va='bottom', zorder=4)
        ax.text(1, ym, sub, fontsize=8.5, color='#333', va='top', zorder=4)
        ax.text(len(c) * 0.42, ym, f"{_fmt(z['lo'])} – {_fmt(z['hi'])}", fontsize=11, weight='bold', va='center',
                zorder=4)
        edge = z['hi'] if z['side'] >= 0 else z['lo']
        fig.text(0.885, 0.25 + 0.62 * (edge - (lo_y - pad)) / (hi_y - lo_y + 2 * pad),
                 f"{_fmt(edge)}\n{(edge / price - 1) * 100:+.1f}%", fontsize=10, weight='bold', color='white',
                 va='center', bbox=dict(boxstyle='round,pad=0.3', fc=col, ec='none'))
    fig.text(0.885, 0.25 + 0.62 * (price - (lo_y - pad)) / (hi_y - lo_y + 2 * pad), _fmt(price), fontsize=11,
             weight='bold', color='white', va='center', bbox=dict(boxstyle='round,pad=0.3', fc='#222', ec='none'))
    for side in ('long', 'short'):
        s = p[side]
        if s:
            y = hi_y if side == 'long' else lo_y
            ax.text(len(c) * 0.8, y, f"{'ЛОНГ' if side == 'long' else 'ШОРТ'} СЦЕНАРИЙ\n"
                                     f"({'пробой и закрепление' if side == 'long' else 'отказ от сопротивления'})\n"
                                     f"TP1 раньше стопа: {s['p'] * 100:.0f}%*", fontsize=9, weight='bold',
                    color='white', ha='center', va='top' if side == 'long' else 'bottom', zorder=5,
                    bbox=dict(boxstyle='round,pad=0.5', fc=GREEN2 if side == 'long' else RED, ec='none'))
    ax.set_xticks([])
    ax.tick_params(axis='y', labelsize=9, colors=GREY)
    ax.yaxis.tick_right()
    for sp in ax.spines.values():
        sp.set_visible(False)
    ax.grid(axis='y', color='#eee', zorder=0)

    # scenario boxes
    for k, side in enumerate(('long', 'short')):
        s = p[side]
        x0 = 0.02 + k * 0.49
        fig.patches.append(FancyBboxPatch((x0, 0.075), 0.47, 0.155, transform=fig.transFigure,
                                          boxstyle='round,pad=0.005', fc='#eef7ee' if side == 'long' else '#fdeeee',
                                          ec=GREEN if side == 'long' else RED))
        head = 'ЛОНГ' if side == 'long' else 'ШОРТ'
        fig.text(x0 + 0.015, 0.218, head, fontsize=15, weight='bold', color=GREEN if side == 'long' else RED,
                 va='top')
        fig.text(x0 + 0.1, 0.214, '(только после подтверждения)' if side == 'long' else '(при подтверждении)',
                 fontsize=9, color=GREEN if side == 'long' else RED, va='top')
        if not s:
            fig.text(x0 + 0.015, 0.17, 'нет уровней для сценария', fontsize=10, color=GREY)
            continue
        e = s['entry']
        rows = [('Вход:', f"{_fmt(e[0])} – {_fmt(e[1])}" + (' (после закрепления)' if side == 'long' else
                                                         ' (отскок/реакция)'))]
        for i, t in enumerate(s['targets']):
            rows.append(('Цели:' if i == 0 else '', f"{_fmt(t)}  ({(t / price - 1) * 100:+.1f}%)"))
        rows.append(('Стоп:', f"{'ниже' if side == 'long' else 'выше'} {_fmt(s['stop'])} "
                              f"({(s['stop'] / price - 1) * 100:+.1f}%)"))
        rows.append(('Условия:', s['cond']))
        for i, (a, b) in enumerate(rows):
            y = 0.19 - i * 0.018
            fig.text(x0 + 0.015, y, a, fontsize=9.5, weight='bold', va='top')
            fig.text(x0 + 0.105, y, b, fontsize=9.5, va='top')
    cur = p['cur']
    msg = (f"СЕЙЧАС ЦЕНА ВНУТРИ ЗОНЫ {_fmt(cur['lo'])} – {_fmt(cur['hi'])}. ЖДЁМ ПОДТВЕРЖДЕНИЯ." if cur else
           'ЦЕНА МЕЖДУ ЗОНАМИ: ВХОД ТОЛЬКО ОТ ГРАНИЦ ПОСЛЕ РЕАКЦИИ.')
    fig.patches.append(FancyBboxPatch((0.02, 0.018), 0.96, 0.045, transform=fig.transFigure,
                                      boxstyle='round,pad=0.005', fc='#fdeeee', ec=RED))
    fig.text(0.04, 0.05, '⚠ ' + msg, fontsize=11, weight='bold', color=RED, va='top')
    fig.text(0.04, 0.032, 'Входить в середине диапазона не рекомендуется. *вероятность случайного блуждания по '
                          'расстояниям, не прогноз. Правила бота, не совет.', fontsize=7.5, color=RED, va='top')
    buf = io.BytesIO()
    fig.savefig(buf, format='png')
    plt.close(fig)
    return buf.getvalue()
