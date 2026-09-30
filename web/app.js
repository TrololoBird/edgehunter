'use strict';
/* Microstructure Scanner browser dashboard: state over /ws after every scan, history / coin details over /api. */

const $ = (sel, root = document) => root.querySelector(sel);
let S = null;                       // latest state from the bot
let tab = localStorage.getItem('tab') || 'wait';
// table id -> {key, asc}; waiting cards open sorted by the distance to their zone (cards in the zone first)
const sorts = { wait: { key: 'До зоны', asc: true } };
const cache = {};                   // api url -> {t, data}
let filterText = '';
let hours = Number(localStorage.getItem('hours') || 24);

// ------------------------------------------------------------------------------------------------ formatting

function fp(v) {
  if (v === null || v === undefined || Number.isNaN(v)) return '—';
  const a = Math.abs(v);
  if (a === 0) return '0';
  if (a >= 1000) return v.toFixed(a >= 1e5 ? 0 : 1);
  const digits = Math.max(2, 4 - Math.floor(Math.log10(a)));
  return v.toFixed(Math.min(digits, 10));
}
function pct(v, d = 2, colored = true) {
  if (v === null || v === undefined || Number.isNaN(v)) return '<span class="dim">—</span>';
  const s = (v >= 0 ? '+' : '') + (v * 100).toFixed(d) + '%';
  if (!colored) return s;
  return `<span class="${v > 0 ? 'up' : v < 0 ? 'down' : ''}">${s}</span>`;
}
// Sizing facts of an entered card (webui.sizing_view): information, never an order
function sizingText(z) {
  const parts = [`стоп ${(z.stop_pct * 100).toFixed(2)}%`, `плечо ≤ ${z.max_leverage}× (изолированная маржа: ликвидация дальше стопа)`];
  if (z.funding_8h !== null && z.funding_8h !== undefined)
    parts.push(`фандинг ${z.funding_8h >= 0 ? 'платите' : 'получаете'} ${Math.abs(z.funding_8h * 100).toFixed(3)}%/8ч`);
  if (z.notional_usd) parts.push(`объём $${usd(z.notional_usd)} (маржа $${usd(z.margin_usd)} при ${z.max_leverage}×, риск $${usd(z.risk_usd)})`);
  return parts.join(' · ');
}
function usd(v) {
  if (v === null || v === undefined) return '—';
  const a = Math.abs(v);
  for (const [d, s] of [[1e9, 'B'], [1e6, 'M'], [1e3, 'K']]) {
    if (a >= d) { const x = v / d; return (Math.abs(x) >= 100 ? x.toFixed(0) : x.toFixed(1)) + s; }
  }
  return v.toFixed(0);
}
function ago(sec) {
  if (!sec && sec !== 0) return '—';
  sec = Math.max(0, Math.round(sec));
  if (sec < 60) return sec + 'с';
  if (sec < 3600) return Math.floor(sec / 60) + 'м';
  return Math.floor(sec / 3600) + 'ч' + String(Math.floor(sec % 3600 / 60)).padStart(2, '0');
}
function clock(ms) {
  const d = new Date(ms);
  return d.toLocaleString('ru-RU', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' });
}
const esc = s => String(s ?? '').replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
const nowSec = () => Date.now() / 1000;
const dirPill = d => d > 0 ? '<span class="pill long">▲ LONG</span>' : d < 0 ? '<span class="pill short">▼ SHORT</span>' : '<span class="pill muted">↕</span>';

// ------------------------------------------------------------------------------------------------ vocabulary

const STATUS = {
  BIAS: ['строится план', 'muted', 'грузится история монеты / карта уровней, или нога перестала подходить'],
  WATCH: ['ждёт отката', 'muted', 'цена ещё не в зоне входа'],
  ZONE: ['ждёт триггер', 'zone', 'цена в зоне (у пробоя — диапазон построен): ждём слом структуры / закрытие за диапазоном'],
  ENTRY: ['вход', 'entry', 'вход по правилам семейства'],
  TP1: ['TP1 ✓', 'good', ''], TP2: ['TP2 ✓✓', 'good', ''], TP3: ['TP3 ✓✓✓', 'good', ''],
  SL: ['стоп', 'bad', ''], MISSED: ['пропущен', 'muted', 'цена дошла до TP1 раньше входа'],
  EXPIRED: ['истёк', 'muted', ''], INVALID: ['отменён', 'bad', ''], CLOSED: ['закрыт', 'muted', ''],
};
const statusPill = st => { const [t, c, tip] = STATUS[st] || [st, 'muted', '']; return `<span class="pill ${c}" title="${esc(tip)}">${esc(t)}</span>`; };
const VETO = {
  perp_led: 'движение ведёт перп, спот не подтверждает', no_orderflow: 'нет подтверждения ордерфлоу',
  no_oi: 'открытый интерес не подтверждает (у продолжения должен расти, после снятия стопов — падать)',
  no_flow: 'поток тейкеров против сделки', no_spot: 'спот против сделки',
  no_data: 'у монеты нет данных, без которых стратегию не оценить (спот для продолжения движения)',
  against_tide: 'против «прилива» (Элдер): тренд монеты на 1h или BTC за час против сделки',
  no_level: 'в полосе отката 0.382–0.618 нет ни уровня карты, ни EMA20 — не за что зацепиться',
  weak_trend: 'откат к EMA20 без уровня карты, а ADX ≤ 30: по Рашке (Holy Grail) такой откат торгуется только в сильном тренде',
  no_spring_test: 'нет теста spring (объём отката высокий)', low_rr: 'R:R до TP1 < 1', regime: 'сетап минусовой в этом режиме рынка',
  no_leg: 'нет подходящей ноги: не из чего строить план', no_room: 'цена уже прошла все цели', same_leg: 'по этой ноге карточка уже была',
  market_move: 'движение всего рынка: тот же сетап у многих монет сразу',
  against_trend: 'против тренда монеты на 1h: снятие ликвидности против тренда обычно проваливается', disabled: 'стратегия выключена в конфиге', not_in_pool: 'монета не в пуле этой стратегии (класс / сектор / волатильность / плохая история на ней)',
  off_session: 'вне торговой сессии системы (SMT: 02:00–10:00 Нью-Йорк)',
};
// Strategies: each has its own anchor, entry and targets (strategies/)
const FAMILY = {
  wyckoff_range: ['Вайкофф: спринг / UTAD', 'торговый диапазон на 1h (24–168 ч) после остановки тренда; прокол края и возврат внутрь; вход на тесте (откат к спрингу, слом структуры 15m), стоп за экстремумом спринга, цель — противоположный край диапазона'],
  trend: ['продолжение тренда', 'пробой BB с ростом OI на 15m; нога по длительности (15m/1h/4h), вход на откате 0.382–0.786 по слому структуры 5m/15m/1h; цели — продолжение'],
  momentum: ['импульс', 'импульс за 5 минут с ростом OI и потоком — торгуется откат ноги, к которой он относится; нога по длительности, вход 5m/15m/1h; цели — продолжение'],
  wyckoff: ['Вайкофф-разворот', 'фазы на 15m: накопление, spring, капитуляция, распределение; вход на подтверждении или на ретесте; цели — сторона диапазона (A, B) или возврат к среднему (C, E)'],
  sweep: ['снятие ликвидности', 'свеча 15m сняла пул стопов старших ТФ (свинги 1h, равные уровни, хай/лой дня и недели, сессии) и закрылась обратно на объёме; против тренда монеты не берётся; вход только после слома структуры 5m в зоне свипа (сам свип — ещё не разворот); цели — ликвидность на другой стороне'],
  absorption: ['поглощение', 'агрессия в значимый уровень (пул 1h/4h, сильная зона, ликвидность стакана) без движения цены (1m); вход по слому структуры 5m; цели — возврат к среднему (VWAP, POC, узлы объёма)'],
  exhaustion: ['истощение каскада', 'каскад ликвидаций перехлёстывает цену; вход по слому структуры 5m против каскада; цели — возврат к среднему и откат 38–62% каскада'],
  breakout: ['пробой с инициативой', 'закрытие 15m за диапазоном на объёме ≥1.5× с потоком в ту же сторону и удержание следующей свечой; обязателен рост OI, пробой без спота (ведёт перп) отсеивается; стоп — середина диапазона; цели — мерное движение'],
  // crypto_maniac's systems (github.com/roman-boop), ported with their own entry and exit
  supply_demand: ['спрос/предложение (maniac)', 'зона 15m: последняя противоположная свеча или пинбар у локального экстремума, уход ≥2 ATR за 4 свечи; вход по пинбару 5m на ретесте зоны; стоп за пинбаром и зоной; зона мертва при закрытии 15m за ней'],
  auction: ['аукцион, POC (maniac)', 'POC консолидации 1h (узкий диапазон, концентрированный объём), подтверждённый импульсом ≥1 высоты диапазона; ретест с реакцией закрытием ≥0.15 ATR; вход на закрытии; стоп за экстремумом теста +0.35 ATR; цель — ближайший сильный нетронутый POC (иначе 2.5R)'],
  smt: ['SMT / Quasimodo (maniac)', 'свип внешнего пула 15m двумя свечами (прокол без закрепа + реакция), SMT-дивергенция с BTC (для BTC — ETH) или Quasimodo; вход по инверсии FVG на 5m в сессию 02–10 Нью-Йорк; стоп за свипом +0.1 ATR; цель — противоположный пул (≥2R) или 2.5R'],
  trendline: ['трендовая линия (maniac)', 'наклонная линия через ≥3 пивота 15m без закрытий за ней; пробой двумя закрытиями ≥0.15 ATR с сильной свечой; вход на закрытии; стоп за структурой 5m; цель — первый якорь линии (R:R ≥ 1)'],
  thirdeye: ['Third Eye (maniac)', '1h: CCI(25) пересекает ±98, цена и линии Ишимоку за облаком, EMA200, фильтры ADX/RSI/NATR/ширины BB; вход на закрытии; стоп 1%, тейк 5%'],
  fib05: ['Фибо 0.5 (maniac)', '1h: импульс по структуре HH/HL; свеча прокалывает 0.5 импульса и закрывается обратно; вход на закрытии; стоп — начало импульса; цель — конец импульса (дальше у автора трейлинг)'],
  bomberman: ['Bomberman (maniac)', '1h: пересечение MACD и сигнальной по стороне EMA100 после QML, без сжатия BB; вход на закрытии; стоп 1.5 ATR, цель 2R'],
  csi: ['Боллинджер + CSI (maniac)', '15m: закрытие за BB(40, 1.5) внутри кластера свечного сентимента CSI той же стороны, RSI(96); вход на закрытии; стоп 0.4%, выход через 3 свечи'],
  oi_accum: ['набор OI (maniac)', 'OI +5% за час при росте цены не больше половины этого, OI за сутки обгоняет цену; только лонг, вход сразу; стоп 2%, тейки 4% и 6%'],
};
const SETUP_RU = {
  'BULL A': 'сжатие + рост OI (не Вайкофф)', 'BULL B': 'spring 15m (старый)', 'BULL E': 'кульминация продаж (не вход по Вайкоффу)',
  'BEAR C': 'дивергенция дельты на хае (не Вайкофф)', 'SPRING': 'спринг Вайкоффа (1h диапазон)', 'UTAD': 'UTAD Вайкоффа (1h диапазон)',
  'BULL F': 'закрытие над полосой Боллинджера', 'BEAR D': 'закрытие под полосой Боллинджера', 'IMPULSE UP': 'импульс вверх', 'IMPULSE DOWN': 'импульс вниз',
  'SWEEP LOW': 'сняты стопы снизу', 'SWEEP HIGH': 'сняты стопы сверху', 'FLUSH REVERSAL': 'после слива лонгов',
  'SQUEEZE REVERSAL': 'после сквиза шортов', 'ABSORB BID': 'продажи поглощены', 'ABSORB ASK': 'покупки поглощены',
  'BREAKOUT UP': 'пробой вверх', 'BREAKOUT DOWN': 'пробой вниз',
  'SD DEMAND': 'зона спроса', 'SD SUPPLY': 'зона предложения', 'AUCTION LONG': 'ретест POC вверх', 'AUCTION SHORT': 'ретест POC вниз',
  'SMT LOW': 'свип минимума + SMT', 'SMT HIGH': 'свип максимума + SMT', 'TRENDLINE UP': 'пробой линии вверх', 'TRENDLINE DOWN': 'пробой линии вниз',
  'THIRD EYE LONG': 'CCI + Ишимоку вверх', 'THIRD EYE SHORT': 'CCI + Ишимоку вниз', 'FIB 0.5 LONG': 'откат к 0.5 вверх', 'FIB 0.5 SHORT': 'откат к 0.5 вниз',
  'BOMBERMAN LONG': 'MACD + QML вверх', 'BOMBERMAN SHORT': 'MACD + QML вниз', 'CSI LONG': 'BB + CSI вверх', 'CSI SHORT': 'BB + CSI вниз',
  'OI ACCUMULATION': 'набор OI без цены',
};
const STRATEGY_OF = {
  'BULL F': 'trend', 'BEAR D': 'trend', 'IMPULSE UP': 'momentum', 'IMPULSE DOWN': 'momentum',
  'BULL A': 'wyckoff', 'BULL B': 'wyckoff', 'BULL E': 'wyckoff', 'BEAR C': 'wyckoff', 'SPRING': 'wyckoff_range', 'UTAD': 'wyckoff_range',
  'SWEEP LOW': 'sweep', 'SWEEP HIGH': 'sweep', 'ABSORB BID': 'absorption', 'ABSORB ASK': 'absorption',
  'FLUSH REVERSAL': 'exhaustion', 'SQUEEZE REVERSAL': 'exhaustion', 'BREAKOUT UP': 'breakout', 'BREAKOUT DOWN': 'breakout',
  'SD DEMAND': 'supply_demand', 'SD SUPPLY': 'supply_demand', 'AUCTION LONG': 'auction', 'AUCTION SHORT': 'auction',
  'SMT LOW': 'smt', 'SMT HIGH': 'smt', 'TRENDLINE UP': 'trendline', 'TRENDLINE DOWN': 'trendline',
  'THIRD EYE LONG': 'thirdeye', 'THIRD EYE SHORT': 'thirdeye', 'FIB 0.5 LONG': 'fib05', 'FIB 0.5 SHORT': 'fib05',
  'BOMBERMAN LONG': 'bomberman', 'BOMBERMAN SHORT': 'bomberman', 'CSI LONG': 'csi', 'CSI SHORT': 'csi',
  'OI ACCUMULATION': 'oi_accum',
};
const familyOf = setup => STRATEGY_OF[setup] || '';
const setupLabel = setup => {
  const fam = FAMILY[familyOf(setup)];
  const neg = ((S && S.archive_negative) || []).includes(setup)
    ? ' <span class="pill warn" title="На архиве (6–12 мес.) этот сетап терял после издержек. Карточка показывается ради живой проверки с данными, которых нет в архиве">архив −</span>' : '';
  return `${esc(setup)}${neg}${SETUP_RU[setup] ? ' <span class="dim">· ' + esc(SETUP_RU[setup]) + '</span>' : ''}` +
    (fam ? `<br><span class="family" title="${esc(fam[1])}">${esc(fam[0])}</span>` : '');
};
// The plan's anchor in words: a leg, a level, a range
function anchorText(c) {
  const a = c.anchor; if (!a) return '—';
  if (a.type === 'leg') return `<b>нога ${esc(a.tf)}</b> ${fp(a.start)} → ${fp(a.end)} ${pct(a.end / a.start - 1, 1)}` +
    (a.end_ts && a.start_ts ? `<br><span class="src">${ago((a.end_ts - a.start_ts) / 1000)}${a.label === 'cascade' ? ', каскад' : ''}, вход по ${c.trigger_minutes}m</span>` : '');
  if (a.type === 'level') return `<b>уровень</b> ${esc(a.label || '')} ${fp(a.level)}<br><span class="src">экстремум ${fp(a.extreme)}, вход по ${c.trigger_minutes}m</span>`;
  if (a.type === 'range') return `<b>диапазон ${esc(a.tf)}</b> ${fp(a.lo)}–${fp(a.hi)}<br><span class="src">вход на удержании или ретест ${c.trigger_minutes}m</span>`;
  return '—';
}
const vetoRu = r => (r || '').split(',').filter(Boolean).map(x => VETO[x] || x).join(', ');
const ANOMALY_TIP = {
  'VOLUME SPIKE': 'объём минуты в разы выше обычного', 'ABSORPTION': 'большой объём без движения цены',
  'WHALES BUY': 'крупные рыночные покупки (свипы)', 'WHALES SELL': 'крупные рыночные продажи (свипы)',
  'ALGO BUY': 'серия однонаправленных крупных покупок', 'ALGO SELL': 'серия однонаправленных крупных продаж',
  'SHORT SQUEEZE': 'рост с ликвидациями шортов', 'LONG FLUSH': 'падение с ликвидациями лонгов',
  'LIQ CASCADE': 'каскад ликвидаций', 'OI SURGE': 'резкий рост открытого интереса', 'OI FLUSH': 'резкое закрытие позиций',
  'IMPULSE UP': 'импульс вверх с ростом OI', 'IMPULSE DOWN': 'импульс вниз с ростом OI',
  'IMPULSE UNCONFIRMED': 'импульс без подтверждения OI/потока', 'ONE-VENUE': 'поток почти целиком с одной биржи',
  'UNUSUAL': 'ML: редкое сочетание факторов',
};
function reasonRu(r) {
  if (!r) return '';
  let m;
  if ((m = r.match(/^TP1 (\S+) \((.*)\) reached before an entry; (\d+) trigger\(s\) vetoed(?:: (.*))?$/)))
    return `цена дошла до TP1 ${m[1]} (${m[2]}) раньше входа; отсеяно триггеров: ${m[3]}` + (m[4] ? ` (${vetoRu(m[4].replace(/, /g, ','))})` : '');
  if ((m = r.match(/^TP1 (\S+) \((.*)\) reached before an entry; no (\d+)m trigger$/)))
    return `цена дошла до TP1 ${m[1]} (${m[2]}) раньше входа; ${m[3]}m-триггера не было`;
  const dur = (n, u) => n + (u === 'm' ? 'м' : 'ч');
  if ((m = r.match(/^no valid (\d+)m trigger in the zone for (\d+)([mh])(?: \((\d+) vetoed\))?/)))
    return `${dur(m[2], m[3])} в зоне без годного ${m[1]}m-триггера` + (m[4] ? ` (отсеяно: ${m[4]})` : '');
  if ((m = r.match(/^price did not reach the zone in (\d+)([mh])/))) return `цена не дошла до зоны за ${dur(m[1], m[2])}`;
  if ((m = r.match(/^no breakout close beyond the range in (\d+)([mh])(?: \((\d+) vetoed\))?/)))
    return `за ${dur(m[1], m[2])} не было закрытия за диапазоном` + (m[3] ? ` (отсеяно: ${m[3]})` : '');
  if ((m = r.match(/^price (\S+) left the range the other way \((\S+)\)/))) return `цена ${m[1]} вышла из диапазона в другую сторону (${m[2]})`;
  if ((m = r.match(/^no 15m history for (\d+)([mh])/))) return `${dur(m[1], m[2])} не было 15m-истории`;
  if ((m = r.match(/^no qualifying 15m leg for (\d+)h/))) return `${m[1]}ч не было подходящей 15m-ноги`;
  if ((m = r.match(/^the leg stopped qualifying and did not return for (\d+)([mh])/))) return `нога перестала подходить и не вернулась за ${dur(m[1], m[2])}`;
  if ((m = r.match(/^price (\S+) beyond the reversed leg's end (\S+) and its stop pool \((\S+)\)/)))
    return `цена ${m[1]} за концом ноги ${m[2]} и пулом стопов за ним (${m[3]}): разворот не состоялся`;
  if ((m = r.match(/^price (\S+) beyond the extreme (\S+) at (.+) \((\S+)\)$/)))
    return `цена ${m[1]} за экстремумом ${m[2]} у ${m[3]} (${m[4]}): уровень не удержал`;
  if ((m = r.match(/^price (\S+) back inside the range past its middle \((\S+)\)/))) return `цена ${m[1]} вернулась в диапазон за его середину (${m[2]}): пробой не удержался`;
  if (r.startsWith('the strategy no longer exists')) return 'стратегия больше не существует';
  if ((m = r.match(/^opposite setup (.+) confirmed: closed at market/))) return `противоположный сетап ${m[1]}: закрыт по рынку`;
  if ((m = r.match(/^opposite setup (.+) confirmed/))) return `отменён противоположным сетапом ${m[1]}`;
  if (r.startsWith('the pullback erased')) return 'откат съел весь импульс';
  if ((m = r.match(/^late signal: price was already beyond TP1 (\S+) \((.*)\)/))) return `поздний сигнал: к подтверждению сетапа цена уже прошла TP1 ${m[1]} (${m[2]})`;
  if ((m = r.match(/^stop (\S+) hit(?: after TP(\d))?/))) return `стоп ${m[1]}` + (m[2] ? ` после TP${m[2]}` : '');
  if ((m = r.match(/^TP3 (\S+) reached/))) return `TP3 ${m[1]} достигнут`;
  if ((m = r.match(/^trade open (\d+)([mh])/))) return `сделка ${dur(m[1], m[2])}: закрыта по рынку`;
  return r;
}
const KIND_COLORS = {
  equal: '#b28cff', pdhl: '#ff9f43', poc: '#3cc7e8', va: '#3cc7e8', hvn: '#3cc7e8', liq_est: '#ff5c8a',
  liq_hit: '#ff8ac0', swing_1h: '#9aa6b8', swing_15m: '#6f7a8c', wall: '#f5c542', vwap: '#5b8cff', fib: '#8e7cc3',
  range: '#ff9f43', liq_hl: '#ff3b3b', book: '#e0a0ff',
};
const KIND_NAMES = {
  equal: 'равные хаи/лои (стопы)', pdhl: 'хай/лоу дня', poc: 'POC', va: 'value area', hvn: 'узел объёма',
  book: 'ликвидность стакана (стояла ≥10м)', liq_est: 'ликвидации (оценка)', liq_hit: 'ликвидации (факт)', swing_1h: 'свинг 1h', swing_15m: 'свинг 15m',
  wall: 'стена стакана', vwap: 'VWAP', fib: 'Фибоначчи', range: 'край диапазона', liq_hl: 'ликвидации крупных счетов HL',
};

// ------------------------------------------------------------------------------------------------ tables

/* cols: [{k: title, v: row => html, s: row => sort value, num: bool, wrap: bool}] */
function table(id, cols, rows, opts = {}) {
  if (!rows.length) return `<div class="empty">${opts.empty || 'пусто'}</div>`;
  const st = sorts[id];
  if (st) {
    const col = cols.find(c => c.k === st.key);
    if (col && col.s) {
      rows = rows.slice().sort((a, b) => {
        const x = col.s(a), y = col.s(b);
        if (x === y) return 0;
        if (x === null || x === undefined) return 1;
        if (y === null || y === undefined) return -1;
        return (x < y ? -1 : 1) * (st.asc ? 1 : -1);
      });
    }
  }
  const head = cols.map(c => `<th data-table="${id}" data-key="${esc(c.k)}" class="${c.num ? 'num' : ''} ${st && st.key === c.k ? 'sorted' + (st.asc ? ' asc' : '') : ''}" title="${esc(c.tip || '')}">${esc(c.k)}</th>`).join('');
  const body = rows.map(r => {
    const cls = [opts.rowClass ? opts.rowClass(r) : '', r.symbol ? 'click' : ''].join(' ');
    return `<tr class="${cls}" data-symbol="${esc(r.symbol || '')}">` +
      cols.map(c => `<td class="${c.num ? 'num' : ''} ${c.wrap ? 'wrap' : ''}">${c.v(r) ?? ''}</td>`).join('') + '</tr>';
  }).join('');
  return `<div class="tablewrap"><table><thead><tr>${head}</tr></thead><tbody>${body}</tbody></table></div>`;
}

document.addEventListener('click', e => {
  const th = e.target.closest('th[data-table]');
  if (th) {
    const id = th.dataset.table, key = th.dataset.key;
    const cur = sorts[id];
    sorts[id] = { key, asc: cur && cur.key === key ? !cur.asc : false };
    if (th.closest('#drawer')) drawCoin(false); else render();
    return;
  }
  const tr = e.target.closest('tr[data-symbol]');
  if (tr && tr.dataset.symbol) {
    const card = (S && S.cards || []).find(c => c.symbol === tr.dataset.symbol && !c.finished);
    openCoin(tr.dataset.symbol, card ? card.tf : null);
  }
});

async function api(url, maxAge = 30) {
  const hit = cache[url];
  if (hit && Date.now() - hit.t < maxAge * 1000) return hit.data;
  const res = await fetch(url);
  const data = url.startsWith('/api/stats') ? await res.text() : await res.json();
  cache[url] = { t: Date.now(), data };
  return data;
}

// ------------------------------------------------------------------------------------------------ header

function renderHeader() {
  if (!S) return;
  const m = S.market || {};
  let html = '';
  for (const [k, v] of Object.entries(m)) html += `<span><b>${k}</b>${fp(v.price)} ${pct(v.change_5m)}</span>`;
  const ml = S.ml || {};
  if (ml.regime) html += `<span><b>режим</b><span class="${ml.regime.startsWith('up') ? 'up' : ml.regime.startsWith('down') ? 'down' : ''}">${esc(ml.regime)}</span></span>`;
  const down = Object.entries(S.venues || {}).filter(([, v]) => v.connected === 0 || v.connected === false).map(([k]) => k);
  html += `<span class="dim">${S.symbols} монет · скан ${S.timing.scan.toFixed(2)}с${down.length ? ' · <span class="down">нет связи: ' + down.join(', ') + '</span>' : ''}</span>`;
  $('#market').innerHTML = html;
  $('#status').textContent = S.status ? '⏳ ' + S.status : '';
  const cards = S.cards || [];
  $('#n-trade').textContent = cards.filter(c => c.entered_at && !c.finished).length;
  $('#n-wait').textContent = cards.filter(c => !c.entered_at && !c.finished).length;
  $('#n-done').textContent = Object.values((S.session || {}).results || {}).reduce((a, b) => a + b, 0);
  $('#n-anom').textContent = (S.anomalies || []).length;
  $('#n-forming').textContent = (S.forming || []).length + (S.vetoed || []).length;
}

// ------------------------------------------------------------------------------------------------ tabs

function setupCell(c) {
  return `<b>${esc(c.name)}</b> ${dirPill(c.direction)}<br>${setupLabel(c.setup)}`;
}
function targetsCell(targets, sources) {
  if (!targets || !targets.length) return '—';
  return targets.map((t, i) => `<span class="tp">TP${i + 1} ${fp(t)} <span class="src">${esc((sources || [])[i] || '')}</span></span>`).join('');
}
const CONFIRM_RU = {
  flow: ['поток', 'поток тейкеров на фьючерсах после экстремума в сторону сделки'],
  spot: ['спот', 'спот покупает / продаёт в сторону сделки: не только плечо'],
  oi: ['OI', 'открытый интерес за час: у продолжения растёт (новые позиции), после снятия стопов / каскада падает'],
  orderflow: ['ордерфлоу', 'у экстремума: перекос в футпринте, поглощение или дивергенция CVD'],
};
function confirmsCell(c) {
  const cf = c.confirms || {}, req = new Set(c.required || []);
  if (!Object.keys(cf).length) return '<span class="dim">ещё нет входа</span>';
  return Object.keys(CONFIRM_RU).map(k => {
    const v = cf[k], [name, tip] = CONFIRM_RU[k], star = req.has(k) ? '★' : '';
    if (v === null || v === undefined) return `<span class="pill muted" title="${esc(tip)}: нет данных">${star}${name} ?</span>`;
    if (v === 'n/a') {
      const raw = k === 'oi' && typeof cf._oi_1h === 'number' ? ` ${(cf._oi_1h * 100).toFixed(1)}%` : '';
      return `<span class="pill muted" title="${esc(tip)}: не применимо к этой монете / стратегии (сырое изменение OI за 1ч показано справочно)">${name} —${raw}</span>`;
    }
    const label = typeof v === 'string' ? `${name}: ${v}` : name;
    return `<span class="pill ${v ? 'good' : 'bad'}" title="${esc(tip)}">${star}${v ? '✓' : '✗'} ${esc(label)}</span>`;
  }).join(' ');
}
const crowdCell = c => !c.crowd ? '—' : c.crowd >= 5 ? `<span class="pill warn" title="движение всего рынка">${c.crowd}</span>` : String(c.crowd);
function progressBar(c) {
  const lv = c.levels; if (!lv || !c.price) return '';
  const d = c.direction, lo = lv.sl, hi = lv.tp3;
  const pos = v => Math.max(0, Math.min(100, (v - lo) / (hi - lo) * 100));
  const ticks = [lv.entry, lv.tp1, lv.tp2].map(v => `<i style="left:${pos(v)}%"></i>`).join('');
  const color = c.r_now >= 0 ? 'var(--green)' : 'var(--red)';
  return `<div class="bar" title="SL → TP3">${ticks}<b style="left:${pos(c.price)}%;background:${color}"></b></div>`;
}

function renderTrade() {
  const rows = (S.cards || []).filter(c => c.entered_at && !c.finished);
  return `<div class="hint">Карточки, где сработал вход. Цели и стоп — из карты уровней монеты (источник под ценой). R сейчас — результат в единицах риска.</div>` +
    table('trade', [
      { k: 'Монета', v: setupCell, s: c => c.name },
      { k: 'Статус', v: c => statusPill(c.status) },
      { k: 'Цена', v: c => fp(c.price), num: true },
      { k: 'Вход', v: c => fp(c.levels.entry), num: true },
      { k: 'Стоп', v: c => `${fp(c.levels.sl)}<br><span class="src">${esc(c.levels.sl_src || '')}</span>`, num: true },
      { k: 'Цели', v: c => targetsCell([c.levels.tp1, c.levels.tp2, c.levels.tp3], [c.levels.tp1_src, c.levels.tp2_src, c.levels.tp3_src]) },
      { k: 'R:R', v: c => (c.levels.rr_tp1 || 0).toFixed(1), s: c => c.levels.rr_tp1, num: true },
      { k: 'R сейчас', v: c => c.r_now === null ? '—' : `<span class="${c.r_now >= 0 ? 'up' : 'down'}">${c.r_now.toFixed(2)}R</span>${progressBar(c)}`, s: c => c.r_now, num: true },
      { k: 'Подтверждения', v: confirmsCell, s: c => Object.values(c.confirms || {}).filter(v => v === true || (typeof v === 'string' && v !== 'n/a')).length, num: true,
        tip: 'на входе: поток тейкеров, спот, открытый интерес, ордерфлоу у экстремума; ★ — обязательное для этой стратегии' },
      { k: 'Толпа', v: crowdCell, s: c => c.crowd || 0, num: true, tip: 'сколько монет дали сетап того же направления за 5 минут: много — это движение всего рынка' },
      { k: 'Вход был', v: c => ago(nowSec() - c.entered_at), s: c => -c.entered_at, num: true },
      { k: 'Почему', v: c => esc((c.why || []).join(' · ')), wrap: true },
    ], rows, { empty: 'Открытых сделок нет.' });
}

function renderWait() {
  const rows = (S.cards || []).filter(c => !c.entered_at && !c.finished);
  return `<div class="hint">Сетапы, ждущие входа. У каждого семейства своя механика (наведи на название семейства).
    <b>Зона</b> — где ищется триггер (у пробоя — сам диапазон). <b>Цели</b> — ближайшие сильные уровни карты за ценой.
    Если цена дойдёт до TP1 раньше входа — «пропущен»; если пробьёт экстремум разворота — «отменён».
    <b>Отсеяно</b> — сколько триггеров не прошли фильтры и почему.</div>` +
    table('wait', [
      { k: 'Монета', v: setupCell, s: c => c.name },
      { k: 'Статус', v: c => statusPill(c.status), s: c => ({ ZONE: 0, WATCH: 1, BIAS: 2 })[c.status] },
      { k: 'Цена', v: c => fp(c.price), num: true },
      { k: 'Опора', v: c => anchorText(c), s: c => c.tf || '', tip: 'на что опирается сетап: нога (импульс / разворот / каскад), уровень (снятый пул, уровень поглощения) или диапазон (пробой); вход — на таймфрейме в 3–6 раз мельче структуры' },
      { k: 'Зона', v: c => c.zone && c.zone[0] ? `${fp(c.zone[0])} – ${fp(c.zone[1])}<br><span class="src">${esc(c.zone_src || '')}</span>` : '—' },
      { k: 'До зоны', v: c => c.status === 'ZONE' ? '<span class="warn">в зоне</span>' : pct(c.dist_to_zone, 2, false), s: c => c.status === 'ZONE' ? 0 : Math.abs(c.dist_to_zone ?? 9), num: true },
      { k: 'Цели', v: c => targetsCell(c.targets, c.target_src) },
      { k: 'Толпа', v: crowdCell, s: c => c.crowd || 0, num: true, tip: 'сколько монет дали сетап того же направления за 5 минут: много — это движение всего рынка' },
      { k: 'Отсеяно', v: c => c.vetoed_triggers ? `${c.vetoed_triggers}<br><span class="src">${esc(vetoRu([...new Set(c.veto_log)].join(',')))}</span>` : '0', s: c => c.vetoed_triggers, num: true },
      { k: 'Возраст', v: c => ago(nowSec() - c.created), s: c => -c.created, num: true },
      { k: 'Почему', v: c => esc((c.why || []).join(' · ')), wrap: true },
    ], rows, { empty: 'Ожидающих сетапов нет.' });
}

function hoursPicker() {
  return `<label>за <select id="hours">${[3, 6, 12, 24, 48, 72, 168].map(h => `<option value="${h}" ${h === hours ? 'selected' : ''}>${h < 48 ? h + 'ч' : h / 24 + 'д'}</option>`).join('')}</select></label>`;
}
function filterBox() {
  return `<input id="filter" placeholder="фильтр: монета или метка" value="${esc(filterText)}">`;
}
const matches = r => !filterText || (r.name + ' ' + (r.group_key || r.label || r.setup || '')).toLowerCase().includes(filterText.toLowerCase());
const dirRet = (r, h) => r[`ret_${h}`] === null || r[`ret_${h}`] === undefined ? null : r[`ret_${h}`] * (r.direction || 1);

async function renderDone() {
  const [cards, entries] = await Promise.all([api(`/api/history?kind=card&hours=${hours}`), api(`/api/history?kind=entry&hours=${hours}`)]);
  const c = cards.filter(matches), e = entries.filter(matches);
  const results = (S.session || {}).results || {};
  const summary = Object.entries(results).map(([k, v]) => `${statusPill(k.split(' ')[0])} ${v}`).join(' &nbsp; ');
  return `<div class="toolbar">${hoursPicker()} ${filterBox()} <span class="dim">эта сессия:</span> ${summary || '—'}</div>
    <h3>Итоги карточек <small>что стало с каждой карточкой и что цена сделала ПОСЛЕ (в сторону сетапа)</small></h3>
    <div class="hint">«Потом» — движение цены после завершения в сторону сетапа: у пропущенных показывает, сколько движения прошло без входа;
    «к рынку» — то же минус средняя доходность всех монет (убирает общий рост/падение рынка; медиана смещена: средняя монета обгоняет её на ~0.1% за 4ч).</div>` +
    table('cards', [
      { k: 'Время', v: r => clock(r.ts_ms), s: r => r.ts_ms },
      { k: 'Монета', v: r => `<b>${esc(r.name)}</b> ${dirPill(r.direction)}`, s: r => r.name },
      { k: 'Сетап', v: r => setupLabel(r.group_key.split(' ').slice(1).join(' ')), s: r => r.group_key },
      { k: 'Итог', v: r => statusPill(r.group_key.split(' ')[0]), s: r => r.group_key.split(' ')[0] },
      { k: 'Причина', v: r => esc(reasonRu(r.reason)), wrap: true },
      { k: 'Цена', v: r => fp(r.price), num: true },
      { k: 'Жизнь', v: r => r.setup_ts_ms ? ago((r.ts_ms - r.setup_ts_ms) / 1000) : '—', s: r => r.ts_ms - (r.setup_ts_ms || r.ts_ms), num: true },
      { k: 'Потом 15м', v: r => pct(dirRet(r, '15m')), s: r => dirRet(r, '15m'), num: true },
      { k: 'Потом 1ч', v: r => pct(dirRet(r, '1h')), s: r => dirRet(r, '1h'), num: true },
      { k: 'Потом 4ч', v: r => pct(dirRet(r, '4h')), s: r => dirRet(r, '4h'), num: true },
      { k: 'к рынку 4ч', v: r => pct(r.edge_4h), s: r => r.edge_4h, num: true, tip: 'доходность минус средняя доходность всех монет' },
    ], c, { empty: 'Завершённых карточек за период нет (итоги пишутся начиная с этой версии).' }) +
    `<h3>Входы <small>включая отсеянные фильтрами: так видно, правильно ли их отсеяли</small></h3>` +
    table('entries', [
      { k: 'Время', v: r => clock(r.ts_ms), s: r => r.ts_ms },
      { k: 'Монета', v: r => `<b>${esc(r.name)}</b> ${dirPill(r.direction)}`, s: r => r.name },
      { k: 'Сетап', v: r => setupLabel(r.group_key.replace('ENTRY ', '')), s: r => r.group_key },
      { k: 'Фильтр', v: r => r.vetoed ? `<span class="pill bad" title="${esc(vetoRu(r.vetoed))}">✗ ${esc(vetoRu(r.vetoed))}</span>` : '<span class="pill good">прошёл</span>', s: r => r.vetoed || '' },
      { k: 'Вход', v: r => fp(r.entry), num: true },
      { k: 'Стоп', v: r => `${fp(r.sl)}<br><span class="src">${esc(r.sl_src || '')}</span>`, num: true },
      { k: 'TP1', v: r => `${fp(r.tp1)}<br><span class="src">${esc(r.tp1_src || '')}</span>`, num: true },
      { k: 'R:R', v: r => r.rr_tp1 ? r.rr_tp1.toFixed(1) : '—', s: r => r.rr_tp1, num: true },
      { k: 'Подтверждения', v: r => r.confirms ? confirmsCell(r) : '—', s: r => Object.values(r.confirms || {}).filter(v => v === true || (typeof v === 'string' && v !== 'n/a')).length, num: true },
      { k: 'Исход 4ч', v: r => r.outcome ? statusPill(r.outcome === 'SKIPPED' ? 'MISSED' : r.outcome === 'OPEN' ? 'CLOSED' : r.outcome) + (r.outcome === 'SKIPPED' ? ' <span class="dim">пропущен</span>' : '') : '<span class="dim">ждём 4ч</span>', s: r => r.outcome },
      { k: 'R @TP1', v: r => r.r_tp1 === null || r.r_tp1 === undefined ? '—' : `<span class="${r.r_tp1 >= 0 ? 'up' : 'down'}">${r.r_tp1.toFixed(2)}R</span>`, s: r => r.r_tp1, num: true },
      { k: 'Потом 1ч', v: r => pct(dirRet(r, '1h')), s: r => dirRet(r, '1h'), num: true },
    ], e, { empty: 'Входов за период нет.' });
}

async function renderAnom() {
  const [hist, summary] = await Promise.all([api(`/api/history?kind=anomaly&hours=${hours}`), api(`/api/anomaly_stats?hours=${hours}`, 60)]);
  const live = (S.anomalies || []).filter(matches);
  const h = hist.filter(matches);
  return `<div class="toolbar">${hoursPicker()} ${filterBox()}</div>
    <h3>Сейчас <small>одна строка на монету, держится ${60}с после последнего срабатывания</small></h3>` +
    table('anom-live', [
      { k: 'Монета', v: r => `<b>${esc(r.name)}</b>`, s: r => r.name },
      { k: 'Метка', v: r => `<span title="${esc(ANOMALY_TIP[r.label] || '')}">${esc(r.label)}</span>`, s: r => r.label },
      { k: 'Правила', v: r => esc((r.rules || []).join(', ')) },
      { k: 'RVOL', v: r => r.sig.rvol_1m ? r.sig.rvol_1m.toFixed(1) + 'x' : '—', s: r => r.sig.rvol_1m, num: true },
      { k: 'Цена 5м', v: r => pct(r.sig.price_change_5m), s: r => r.sig.price_change_5m, num: true },
      { k: 'OI 5м', v: r => pct(r.sig.oi_change_5m), s: r => r.sig.oi_change_5m, num: true },
      { k: 'Киты', v: r => r.sig.whale_net_5m ? `<span class="${r.sig.whale_net_5m > 0 ? 'up' : 'down'}">${r.sig.whale_net_5m.toFixed(1)}</span>` : '—', s: r => r.sig.whale_net_5m, num: true, tip: 'чистые свипы китов за 5м, в размерах кита монеты' },
      { k: 'Ликв. L/S', v: r => `${usd(r.sig.liq_long_5m || 0)} / ${usd(r.sig.liq_short_5m || 0)}`, s: r => (r.sig.liq_long_5m || 0) + (r.sig.liq_short_5m || 0), num: true },
      { k: 'Длится', v: r => ago(r.last_seen - r.first_seen), s: r => r.last_seen - r.first_seen, num: true },
      { k: 'Контекст', v: r => esc((r.why || []).join(' · ')), wrap: true },
    ], live, { empty: 'Сейчас аномалий нет.' }) +
    `<h3>Что было дальше по меткам <small>за ${hours}ч; для направленных меток движение считается в их сторону</small></h3>
    <div class="hint">Попадание — доля случаев, когда цена пошла в сторону метки. «к рынку» — минус средняя доходность всех монет за то же время.
    Для ↕-меток (без направления) показан средний размер движения в любую сторону.</div>` +
    table('anom-sum', [
      { k: 'Метка', v: r => `<span title="${esc(ANOMALY_TIP[r.label] || '')}">${esc(r.label)}</span> ${r.directional ? '' : '<span class="dim">↕</span>'}`, s: r => r.label },
      { k: 'N', v: r => r.n, s: r => r.n, num: true },
      ...['15m', '1h', '4h'].flatMap(hz => [
        { k: `${hz} ср.`, v: r => pct(r[`avg_${hz}`]), s: r => r[`avg_${hz}`], num: true },
        { k: `${hz} попад.`, v: r => r[`hit_${hz}`] === null ? '—' : (r[`hit_${hz}`] * 100).toFixed(0) + '%', s: r => r[`hit_${hz}`], num: true },
      ]),
      { k: 'к рынку 1ч', v: r => pct(r.edge_1h), s: r => r.edge_1h, num: true },
      { k: 'к рынку 4ч', v: r => pct(r.edge_4h), s: r => r.edge_4h, num: true },
    ], summary, { empty: 'Нет данных за период.' }) +
    `<h3>История <small>каждое событие и что цена сделала потом (в сторону метки)</small></h3>` +
    table('anom-hist', [
      { k: 'Время', v: r => clock(r.ts_ms), s: r => r.ts_ms },
      { k: 'Монета', v: r => `<b>${esc(r.name)}</b>`, s: r => r.name },
      { k: 'Метка', v: r => `${esc(r.group_key)} ${r.direction ? (r.direction > 0 ? '<span class="up">▲</span>' : '<span class="down">▼</span>') : ''}`, s: r => r.group_key },
      { k: 'Цена', v: r => fp(r.price), num: true },
      { k: 'Цена 5м', v: r => pct(r.price_change_5m), s: r => r.price_change_5m, num: true },
      { k: 'RVOL', v: r => r.rvol_1m ? r.rvol_1m.toFixed(1) + 'x' : '—', s: r => r.rvol_1m, num: true },
      { k: 'Киты', v: r => r.whale_net_5m ? r.whale_net_5m.toFixed(1) : '—', s: r => r.whale_net_5m, num: true },
      { k: 'Потом 15м', v: r => pct(dirRet(r, '15m')), s: r => dirRet(r, '15m'), num: true },
      { k: 'Потом 1ч', v: r => pct(dirRet(r, '1h')), s: r => dirRet(r, '1h'), num: true },
      { k: 'Потом 4ч', v: r => pct(dirRet(r, '4h')), s: r => dirRet(r, '4h'), num: true },
      { k: 'к рынку 1ч', v: r => pct(r.edge_1h), s: r => r.edge_1h, num: true },
    ], h, { empty: 'Нет аномалий за период.' });
}

// Small-cap pumps / dumps of the last 48h and their first pullback (pumps.py; research/pumps*.md)
function pumpsHtml() {
  const rows = (S.pumps || []).filter(matches);
  const st = rows.length ? rows[0].stats : null;
  return `<h3>Пампы и дампы щитков за 48ч <small>вне топ-30 по объёму; +15% (−15%) за ≤6ч на объёме ×3; первый откат 38.2–61.8%</small></h3>` +
    table('pumps', [
      { k: 'Монета', v: r => `<b>${esc(r.name)}</b> ${r.kind === 'pump' ? 'памп' : 'дамп'}`, s: r => r.name },
      { k: 'Когда', v: r => clock(r.event_ts), s: r => r.event_ts },
      { k: 'Ход', v: r => pct(r.direction * r.move), s: r => r.move, num: true },
      { k: 'База → пик', v: r => `${fp(r.base)} → ${fp(r.peak)}` },
      { k: 'Зона отката', v: r => `${fp(r.zone[0])} – ${fp(r.zone[1])}` },
      { k: 'Состояние', v: r => esc(r.state) + (r.levels ? ` · ${r.trade_dir > 0 ? 'лонг' : 'шорт'} ${fp(r.levels.entry)}, стоп ${fp(r.levels.stop)}, цели ${fp(r.levels.tp1)} / ${fp(r.levels.tp2)}` : ''), wrap: true },
      { k: 'История правила', v: r => `${esc(r.stats.label)}: ${esc(r.stats.verdict)}, ${esc(r.stats.r)}, цель ${esc(r.stats.hit)}`, wrap: true },
    ], rows, { empty: 'Пампов и дампов щитков за 48ч нет.' });
}

// Per-strategy coin pools (pools.py): which coins each strategy trades, and the ones excluded by their results
function poolsHtml() {
  const p = S.pools;
  if (!p || !p.updated) return '<h3>Пулы монет стратегий</h3><div class="hint">Строятся (через ~2 минуты после старта, затем раз в час).</div>';
  const rows = Object.entries(p.pools).map(([k, v]) => ({ k, coins: v, excl: p.excluded[k] || {} }));
  return `<h3>Пулы монет стратегий <small>каждая стратегия торгует только свои монеты; обновлено ${ago(nowSec() - p.updated)} назад</small></h3>` +
    table('pools', [
      { k: 'Стратегия', v: r => esc((FAMILY[r.k] || [r.k])[0]), s: r => r.k },
      { k: 'Монеты', v: r => r.coins.map(c => `${esc(c)} <span class="src">${esc((p.classes[c] || {}).sector || '')}</span>`).join(', '), wrap: true },
      { k: 'Исключены по истории', v: r => Object.entries(r.excl).map(([c, x]) => `${esc(c)} (${x.entries} входов, ${x.r > 0 ? '+' : ''}${x.r}R)`).join(', ') || '—', wrap: true },
    ], rows, { empty: 'Нет пулов.' });
}

function renderForming() {
  const f = (S.forming || []).filter(matches), v = (S.vetoed || []).filter(matches);
  return `<div class="toolbar">${filterBox()}</div>
    <h3>Формируются <small>фазы набрали часть баллов на закрытой 15m-свече, карточки ещё нет</small></h3>` +
    table('forming', [
      { k: 'Монета', v: r => `<b>${esc(r.name)}</b> ${dirPill(r.direction)}`, s: r => r.name },
      { k: 'Фазы', v: r => r.phases.map(p => `${p.name} ${p.score}/${p.max}`).join(', '), s: r => Math.max(0, ...r.phases.map(p => p.score)), num: false },
      { k: 'Цена 5м', v: r => pct(r.sig.price_change_5m), s: r => r.sig.price_change_5m, num: true },
      { k: 'Покупатели', v: r => r.sig.delta_ratio === null ? '—' : ((1 + r.sig.delta_ratio) / 2 * 100).toFixed(0) + '%', s: r => r.sig.delta_ratio, num: true },
      { k: 'Контекст', v: r => esc((r.why || []).join(' · ')), wrap: true },
    ], f, { empty: 'Ничего не формируется.' }) +
    pumpsHtml() + poolsHtml() +
    `<h3>Отсеяны на этом скане <small>сетапы, которые не стали карточками</small></h3>` +
    table('vetoed', [
      { k: 'Монета', v: r => `<b>${esc(r.name)}</b>`, s: r => r.name },
      { k: 'Сетап', v: r => setupLabel(r.setup), s: r => r.setup },
      { k: 'Причина', v: r => esc(vetoRu(r.reason)), s: r => r.reason },
    ], v, { empty: 'Нет.' });
}

async function renderStats() {
  const days = hours / 24;
  const html = await api(`/api/stats?days=${days}`, 60);
  return `<div class="toolbar">${hoursPicker()} <span class="dim">отчёт stats.py по текущей версии логики (${esc(S.logic_version)})</span></div>${html}`;
}

function renderHealth() {
  const v = S.venues || {};
  const boxes = Object.entries(v).sort().map(([name, st]) => `<div class="box"><h4>${esc(name)} ${st.connected === 0 || st.connected === false ? '<span class="pill bad">нет связи</span>' : '<span class="pill good">ok</span>'}</h4>
    <div class="kv">${Object.entries(st).map(([k, x]) => `<span>${esc(k)}</span><span class="mono">${typeof x === 'number' ? (Math.abs(x) >= 1000 ? usd(x) : +x.toFixed(2)) : esc(x)}</span>`).join('')}</div></div>`).join('');
  const ml = S.ml || {};
  return `<div class="grid">
    <div class="box"><h4>Скан</h4><div class="kv"><span>tier-0</span><span class="mono">${S.timing.tier0.toFixed(2)}с</span>
      <span>скан</span><span class="mono">${S.timing.scan.toFixed(2)}с</span><span>тяжёлый проход</span><span class="mono">${S.timing.heavy.toFixed(2)}с</span>
      <span>монет</span><span class="mono">${S.symbols}</span><span>стаканов</span><span class="mono">${S.hot}</span>
      <span>логика</span><span class="mono">${esc(S.logic_version)}</span></div></div>
    <div class="box"><h4>ML</h4><div class="kv"><span>режим</span><span>${esc(ml.regime || '—')}</span>
      <span>модель аномалий</span><span>${ml.anomaly_ready ? 'обучена ' + Math.round(ml.anomaly_age_min) + 'м назад' : 'копит ' + ml.anomaly_samples + ' сэмплов'}</span>
      <span>P(edge)</span><span>${ml.p_n} размеченных${ml.p_mature ? '' : ' (показ с 300)'}${ml.p_accuracy ? ', точность ' + (ml.p_accuracy * 100).toFixed(0) + '%' : ''}</span>
      <span>режимы</span><span>${ml.regime_candles} свечей${ml.regime_age_h != null ? ', модель ' + ml.regime_age_h.toFixed(1) + 'ч' : ''}</span>
      <span>предобучение</span><span>${ml.pretrained_rows ? ml.pretrained_rows + ' строк, ' + ml.pretrained_coins + ' монет, ' + esc(ml.pretrained_span) + ' (' + ml.pretrained_age_d.toFixed(1) + 'д назад)' : 'нет'}${ml.pretrain_running ? ' · <span class="warn">идёт обучение</span>' : ''}</span></div></div>
  </div><h3>Биржи</h3><div class="grid">${boxes}</div>`;
}

const RENDER = { trade: renderTrade, wait: renderWait, done: renderDone, anom: renderAnom, forming: renderForming, stats: renderStats, health: renderHealth };
let renderSeq = 0;
async function render() {
  if (!S) { $('#view').innerHTML = '<div class="empty">Подключение к боту…</div>'; return; }
  renderHeader();
  const seq = ++renderSeq;
  const focus = document.activeElement && document.activeElement.id;
  const pos = focus === 'filter' ? document.activeElement.selectionStart : null;
  let html;
  try { html = await RENDER[tab](); } catch (err) { html = `<div class="empty">Ошибка: ${esc(err.message)}</div>`; }
  if (seq !== renderSeq) return;
  const y = window.scrollY;
  $('#view').innerHTML = html;
  window.scrollTo(0, y);
  if (focus === 'filter') { const f = $('#filter'); f.focus(); f.setSelectionRange(pos, pos); }
}

document.addEventListener('input', e => {
  if (e.target.id === 'filter') { filterText = e.target.value; render(); }
});
document.addEventListener('change', e => {
  if (e.target.id === 'hours') { hours = Number(e.target.value); localStorage.setItem('hours', hours); render(); }
});
document.querySelectorAll('#tabs button').forEach(b => b.addEventListener('click', () => {
  tab = b.dataset.tab; localStorage.setItem('tab', tab); setActiveTab(); render();
}));
function setActiveTab() { document.querySelectorAll('#tabs button').forEach(b => b.classList.toggle('active', b.dataset.tab === tab)); }

// Live tabs re-render on every state; journal-backed tabs every 60s (their data changes slowly)
let lastSlow = 0;
function onState() {
  const slow = ['done', 'anom', 'stats'].includes(tab);
  if (!slow || Date.now() - lastSlow > 60000) { lastSlow = Date.now(); render(); } else renderHeader();
}

// ------------------------------------------------------------------------------------------------ websocket

function connect() {
  const ws = new WebSocket(`ws://${location.host}/ws`);
  ws.onopen = () => $('#conn').className = 'dot on';
  ws.onmessage = ev => { S = JSON.parse(ev.data); onState(); if (coin && Date.now() - coinLoaded > 20000) loadCoin(); };
  ws.onclose = () => { $('#conn').className = 'dot off'; setTimeout(connect, 2000); };
}

// ------------------------------------------------------------------------------------------------ coin drawer

let coin = null, coinLoaded = 0, chart = null, series = null, tf = 15, coinData = null, priceLines = [];
const tzShift = -new Date().getTimezoneOffset() * 60;

function openCoin(symbol, leg) {
  coin = symbol;
  // The chart matches the card's leg: 1h candles for a 1h / 4h leg (the whole leg visible), 5m for the minute legs of
  // momentum / sweep / exhaustion / absorption / range setups, 15m otherwise
  tf = leg === '1h' || leg === '4h' ? 60 : leg === '1m' || leg === '5m' ? 5 : 15;
  document.querySelectorAll('.tf').forEach(x => x.classList.toggle('active', Number(x.dataset.tf) === tf));
  $('#drawer').classList.remove('hidden');
  $('#d-title').textContent = symbol.replace(':USDT', '').replace('/USDT', '');
  $('#d-body').innerHTML = '<div class="empty">Загрузка карты уровней…</div>';
  if (!chart) {
    chart = LightweightCharts.createChart($('#chart'), {
      autoSize: true, layout: { background: { color: 'transparent' }, textColor: getComputedStyle(document.body).color },
      grid: { vertLines: { color: 'rgba(128,128,128,.08)' }, horzLines: { color: 'rgba(128,128,128,.08)' } },
      timeScale: { timeVisible: true, secondsVisible: false }, rightPriceScale: { scaleMargins: { top: 0.08, bottom: 0.08 } },
    });
    chart.timeScale().subscribeVisibleLogicalRangeChange(() => requestAnimationFrame(drawHeat));
    series = chart.addCandlestickSeries({ upColor: '#2ecc71', downColor: '#ff5c5c', borderVisible: false, wickUpColor: '#2ecc71', wickDownColor: '#ff5c5c', priceFormat: { type: 'price', precision: 6, minMove: 0.000001 } });
  }
  coinData = null;
  loadCoin(true);
}
$('#d-close').addEventListener('click', () => { coin = null; $('#drawer').classList.add('hidden'); });
document.addEventListener('keydown', e => { if (e.key === 'Escape' && coin) $('#d-close').click(); });
document.querySelectorAll('.tf').forEach(b => b.addEventListener('click', () => {
  tf = Number(b.dataset.tf); document.querySelectorAll('.tf').forEach(x => x.classList.toggle('active', x === b)); drawCoin(true);
}));

async function loadCoin(fit = false) {
  const symbol = coin; coinLoaded = Date.now();
  try {
    const data = await (await fetch(`/api/coin?symbol=${encodeURIComponent(symbol)}`)).json();
    if (symbol !== coin) return;
    coinData = data; drawCoin(fit);
    // The 1h / 5m history is loading in the background: ask again shortly
    if (!data.htf_loaded && !data.note) setTimeout(() => { if (coin === symbol) loadCoin(false); }, 4000);
  } catch (err) { $('#d-body').innerHTML = `<div class="empty">Ошибка: ${esc(err.message)}</div>`; }
}

// The two-sided scenario card (scenarios.py): the reaction zone, resistances above, supports below, a long
// (breakout and retest) and a short (rejection) plan; the probability is the trained model's only when it beat the
// geometric baseline out of sample (the source is shown).
function htfLine(h) {
  if (!h || h.trend_w === undefined) return '<div class="hint">Старший диапазон (день / неделя) ещё грузится.</div>';
  const t = h.trend_w > 0.5 ? 'вверх' : h.trend_w < -0.5 ? 'вниз' : 'боковик';
  return `<div class="hint">Неделя: тренд ${t} (EMA20 недель ${h.trend_w > 0 ? '+' : ''}${h.trend_w.toFixed(1)}% за 4 недели) · цена в ${Math.round(h.range_pos_30d * 100)}% 30-дневного диапазона</div>`;
}

function statsLine(st) {
  if (!st) return '';
  return '<div class="hint">История триггеров (архив, 478 монет, 2024–2026): ' + Object.values(st).map(x =>
    `${esc(x.label)} — цель ${Math.round(x.hit * 100)}% при геометрии ${Math.round(x.geo * 100)}%, ${x.r > 0 ? '+' : ''}${x.r.toFixed(2)}R`).join(' · ') + '</div>';
}

function scenarioHtml(s, price) {
  if (!s) return '<h3>Сценарии</h3><div class="hint">Нет сценария: мало 1h истории или нет уровней по обе стороны цены.</div>';
  const zone = (z, name, hint) => `<span>${name}</span><span>${fp(z.lo)} – ${fp(z.hi)} ${pct(z.price / price - 1)} <span class="src">${esc(hint || z.label)}</span></span>`;
  const names = ['локальное сопротивление', 'сопротивление', 'глобальное сопротивление'];
  let rows = s.above.slice().reverse().map((z, i, a) => zone(z, names[a.length - 1 - i])).join('');
  rows += zone(s.reaction, '<b>зона реакции</b>', 'текущая зона: ' + s.reaction.label);
  rows += s.below.map((z, i) => zone(z, i === 0 ? 'следующая поддержка' : 'ключевая поддержка')).join('');
  const plan = (p, name, cls) => `<div class="${cls}"><b>${name}</b> <small>${esc(p.trigger)}</small><div class="kv">
    <span>вход</span><span>${fp(p.entry)}</span>
    <span>цели</span><span>${p.targets.map((t, i) => `${fp(t)} ${pct(t / price - 1)} <small>R:R ${p.rr[i] ?? '—'}</small>`).join(' · ')}</span>
    <span>стоп</span><span>${fp(p.stop)} ${pct(p.stop / price - 1)}</span></div></div>`;
  const pu = s.p_up_first;
  const warn = s.status === 'inside' ? '<div class="hint">Цена внутри зоны реакции: ждём выхода и подтверждения, вход из середины диапазона не планируется.</div>' : '';
  const m = s.macro || {};
  const num = (v, d = 2) => (v === null || v === undefined || Number.isNaN(v)) ? '—' : (v > 0 ? '+' : '') + v.toFixed(d);
  const macro = m.us10y != null ? `<div class="hint">Макро (FRED, дневные, с задержкой в день): US10Y ${m.us10y.toFixed(2)}% (${num(m.us10y_5d_bp, 0)} б.п. за 5 дней) ·
    доллар ${m.dxy != null ? m.dxy.toFixed(1) : '—'} (${num(m.dxy_5d)}%) · Brent ${m.brent != null ? m.brent.toFixed(1) : '—'} (${num(m.brent_5d)}%)</div>` : '';
  return `<h3>Сценарии <small>1h, ATR 1h ${fp(s.atr_1h)}</small></h3>${macro}
    <div class="kv">${rows}</div>
    <div class="hint">Вероятность дойти до первого сопротивления раньше первой поддержки: <b>${Math.round(pu * 100)}%</b>
      (вниз первой: ${Math.round((1 - pu) * 100)}%) — ${esc(s.p_source)}</div>${warn}
    ${plan(s.long, 'ЛОНГ', 'scen-long')}${plan(s.short, 'ШОРТ', 'scen-short')}
    ${htfLine(s.htf)}${statsLine(s.trigger_stats)}
    <div class="hint">Сценарий — механические правила по уровням, не рекомендация; проверка: research/scenario_model.md, research/level_triggers.md.</div>`;
}

function drawCoin(fit) {
  const d = coinData; if (!d || d.error) { $('#d-body').innerHTML = `<div class="empty">${esc(d && d.error)}</div>`; return; }
  const raw = tf === 60 ? (d.candles_1h || []) : tf === 15 ? d.candles_15m : d.candles_5m;
  const bars = raw.map(c => ({ time: Math.floor(c[0] / 1000) + tzShift, open: c[1], high: c[2], low: c[3], close: c[4] }));
  const precision = d.price ? Math.min(10, Math.max(2, 4 - Math.floor(Math.log10(d.price)))) : 4;
  series.applyOptions({ priceFormat: { type: 'price', precision, minMove: Math.pow(10, -precision) } });
  series.setData(bars);
  const barTimes = new Set(bars.map(b => b.time));
  priceLines.forEach(l => series.removePriceLine(l)); priceLines = [];
  const line = (price, color, title, style = 0, width = 1, axis = true) => {
    if (price === null || price === undefined) return;
    priceLines.push(series.createPriceLine({ price, color, lineWidth: width, lineStyle: style, axisLabelVisible: axis, title }));
  };
  const zones = (d.zones || []).slice().sort((a, b) => b.strength - a.strength).slice(0, 28);
  const usedKinds = new Set();
  for (const z of zones) {
    const kind = z.kinds[0]; usedKinds.add(kind);
    const strong = z.strength >= 2;
    line(z.price, KIND_COLORS[kind] || '#888', strong ? z.label.split(' · ')[0] : '', strong ? 0 : 2, z.strength >= 4 ? 2 : 1, strong);
  }
  const card = (d.cards || []).find(c => !c.finished) || (d.cards || [])[0];
  if (card) {
    if (card.zone && card.zone[0] && !card.entered_at) { line(card.zone[0], '#f5c542', 'зона', 1, 2); line(card.zone[1], '#f5c542', 'зона', 1, 2); }
    if (card.levels) {
      const lv = card.levels;
      line(lv.entry, '#3cc7e8', 'вход', 0, 2); line(lv.sl, '#ff5c5c', 'стоп', 0, 2);
      [lv.tp1, lv.tp2, lv.tp3].forEach((t, i) => line(t, '#2ecc71', 'TP' + (i + 1), 0, 2));
    } else (card.targets || []).forEach((t, i) => line(t, '#2ecc71', 'TP' + (i + 1), 2, 1));
  }
  if (!card && d.scenario) {
    const s = d.scenario;
    line(s.reaction.hi, '#4a8cff', 'реакция', 2, 2); line(s.reaction.lo, '#4a8cff', '', 2, 2, false);
    s.above.forEach((z, i) => line(z.lo, '#ff5c5c', ['лок. сопр.', 'сопр.', 'глоб. сопр.'][i], 0, 2));
    s.below.forEach((z, i) => line(z.hi, '#2ecc71', ['поддержка', 'ключ. поддержка'][i], 0, 2));
  }
  // Journal events as markers on the bar they happened in
  const size = tf * 60;   // bar size in seconds (5 / 15 / 60 minutes)
  const markers = (d.journal || []).filter(r => r.kind !== 'structured').map(r => {
    const t = Math.floor(r.ts_ms / 1000 / size) * size + tzShift;
    if (r.kind === 'setup') return { time: t, position: r.direction > 0 ? 'belowBar' : 'aboveBar', color: '#e0a0ff', shape: 'circle', text: (SETUP_RU[r.group_key] || r.group_key).split(' ')[0] };
    if (r.kind === 'anomaly') return { time: t, position: r.direction < 0 ? 'aboveBar' : 'belowBar', color: r.direction > 0 ? '#2ecc71' : r.direction < 0 ? '#ff5c5c' : '#9aa6b8', shape: 'circle', text: r.group_key.split(' ')[0].slice(0, 6) };
    if (r.kind === 'entry') return { time: t, position: r.direction > 0 ? 'belowBar' : 'aboveBar', color: r.vetoed ? '#9aa6b8' : '#3cc7e8', shape: r.direction > 0 ? 'arrowUp' : 'arrowDown', text: r.vetoed ? '✗' : 'вход' };
    if (r.kind === 'card') return { time: t, position: 'aboveBar', color: '#f5c542', shape: 'square', text: r.group_key.split(' ')[0].toLowerCase() };
    return null;
  }).filter(m => m && barTimes.has(m.time)).sort((a, b) => a.time - b.time);
  series.setMarkers(markers);
  if (fit) chart.timeScale().fitContent();
  drawHeat();

  $('#d-title').innerHTML = `${esc(d.symbol.replace(':USDT', '').replace('/USDT', ''))} <small>${fp(d.price)} · ATR 15m ${fp(d.atr)}${d.note ? ' · монета вне текущей вселенной: без карты уровней' : d.htf_loaded ? '' : ' · 1h история ещё грузится'}</small>`;
  $('#legend').innerHTML = [...usedKinds].map(k => `<span><i style="background:${KIND_COLORS[k] || '#888'}"></i>${esc(KIND_NAMES[k] || k)}</span>`).join('') +
    '<span class="dim">сплошные — сильные зоны (конфлюэнция ≥ 2), пунктир — слабые</span>';

  let body = '';
  for (const c of d.cards || []) {
    body += `<h3>${dirPill(c.direction)} ${esc(c.setup)} <small>${esc((FAMILY[c.strategy] || [''])[0])}</small> ${statusPill(c.status)} <small>${c.finished ? esc(reasonRu(c.finish_reason)) : 'создан ' + ago(nowSec() - c.created) + ' назад'}</small></h3>
      <div class="hint">опора: ${anchorText(c)}</div>
      <div class="hint">${esc((c.why || []).join(' · '))}</div>
      <div class="kv">${c.zone && c.zone[0] ? `<span>зона</span><span>${fp(c.zone[0])} – ${fp(c.zone[1])} <span class="src">${esc(c.zone_src || '')}</span></span>` : ''}
      ${c.levels ? `<span>вход / стоп</span><span>${fp(c.levels.entry)} / ${fp(c.levels.sl)} <span class="src">${esc(c.levels.sl_src || '')}</span></span>` : ''}
      ${c.sizing ? `<span>позиция</span><span>${sizingText(c.sizing)}</span>` : ''}
      <span>цели</span><span>${targetsCell(c.levels ? [c.levels.tp1, c.levels.tp2, c.levels.tp3] : c.targets, c.levels ? [c.levels.tp1_src, c.levels.tp2_src, c.levels.tp3_src] : c.target_src)}</span>
      ${c.vetoed_triggers ? `<span>отсеяно</span><span>${c.vetoed_triggers}${c.veto_log.length ? ': ' + esc(vetoRu([...new Set(c.veto_log)].join(','))) : ''}</span>` : ''}
      ${(c.veto_notes || []).length ? `<span title="стоп за структурой не окупается целью: почему сигнал возник в этой точке">стоп далеко</span><span class="src">${esc(c.veto_notes[c.veto_notes.length - 1])}</span>` : ''}</div>`;
  }
  body += scenarioHtml(d.scenario, d.price);
  body += `<h3>Карта уровней <small>ближайшие к цене; сила = сумма весов источников</small></h3>` +
    table('zones', [
      { k: 'Цена', v: z => fp(z.price), s: z => z.price, num: true },
      { k: 'От цены', v: z => pct(d.price ? z.price / d.price - 1 : null), s: z => d.price ? z.price / d.price - 1 : 0, num: true },
      { k: 'Сила', v: z => z.strength.toFixed(1), s: z => z.strength, num: true },
      { k: 'Источники', v: z => esc(z.label), wrap: true },
      { k: 'Тип', v: z => z.kinds.map(k => `<span style="color:${KIND_COLORS[k] || '#888'}">${esc(KIND_NAMES[k] || k)}</span>`).join(', '), wrap: true },
    ], (d.zones || []).slice().sort((a, b) => b.price - a.price), { empty: 'Карта ещё не построена (нужна история свечей).' }) +
    `<h3>Журнал монеты за 48ч</h3>` +
    table('coin-journal', [
      { k: 'Время', v: r => clock(r.ts_ms), s: r => r.ts_ms },
      { k: 'Тип', v: r => ({ anomaly: 'аномалия', structured: 'фаза', setup: 'сетап', entry: 'вход', card: 'итог' })[r.kind] || r.kind },
      { k: 'Событие', v: r => `${esc(r.group_key)} ${r.vetoed ? '<span class="dim">✗ ' + esc(vetoRu(r.vetoed)) + '</span>' : ''}${r.reason ? '<br><span class="src">' + esc(reasonRu(r.reason)) + '</span>' : ''}`, wrap: true },
      { k: 'Цена', v: r => fp(r.price), num: true },
      { k: 'Потом 15м', v: r => pct(dirRet(r, '15m')), num: true },
      { k: 'Потом 1ч', v: r => pct(dirRet(r, '1h')), num: true },
      { k: 'Потом 4ч', v: r => pct(dirRet(r, '4h')), num: true },
    ], d.journal || [], { empty: 'Событий нет.' });
  $('#d-body').innerHTML = body;
}

// ------------------------------------------------------------------------------------------------ heatmap
// Order-book history behind the candles: each 500-level snapshot (30s) is averaged into the bar it belongs to; the
// brightness is the resting USD in the price bucket relative to the largest one on screen (bids green, asks red).

function drawHeat() {
  const canvas = $('#heat'); if (!canvas || !chart) return;
  const box = $('#chart').getBoundingClientRect();
  const dpr = window.devicePixelRatio || 1;
  canvas.width = Math.round(box.width * dpr); canvas.height = Math.round(box.height * dpr);
  const ctx = canvas.getContext('2d'); ctx.setTransform(dpr, 0, 0, dpr, 0, 0); ctx.clearRect(0, 0, box.width, box.height);
  const hm = coinData && coinData.heatmap;
  if (!hm || !hm.snapshots.length || !$('#heat-on').checked) return;
  const size = tf * 60, bars = new Map();
  for (const [ms, levels] of hm.snapshots) {
    const t = Math.floor(ms / 1000 / size) * size + tzShift;
    let bar = bars.get(t); if (!bar) { bar = { n: 0, v: new Map() }; bars.set(t, bar); }
    bar.n += 1;
    for (const [price, usd] of levels) bar.v.set(price, (bar.v.get(price) || 0) + usd);
  }
  const spacing = chart.timeScale().options().barSpacing;
  const plotWidth = box.width - chart.priceScale('right').width();
  let max = 0;
  const cells = [];
  for (const [t, bar] of bars) {
    const x = chart.timeScale().timeToCoordinate(t); if (x === null) continue;
    for (const [price, sum] of bar.v) {
      const usd = sum / bar.n;
      const y1 = series.priceToCoordinate(price + hm.step / 2), y2 = series.priceToCoordinate(price - hm.step / 2);
      if (y1 === null || y2 === null) continue;
      cells.push([x, y1, y2, usd]); max = Math.max(max, Math.abs(usd));
    }
  }
  if (!max) return;
  for (const [x, y1, y2, usd] of cells) {
    if (x - spacing / 2 > plotWidth) continue;
    const a = Math.min(0.55, Math.pow(Math.abs(usd) / max, 0.6) * 0.55);
    if (a < 0.03) continue;
    ctx.fillStyle = usd > 0 ? `rgba(46,204,113,${a})` : `rgba(255,92,92,${a})`;
    ctx.fillRect(x - spacing / 2, Math.min(y1, y2), spacing, Math.max(1, Math.abs(y2 - y1)));
  }
}
$('#heat-on').addEventListener('change', drawHeat);
window.addEventListener('resize', () => requestAnimationFrame(drawHeat));
// The price scale can move without an event (auto-scale): redraw while the panel is open
setInterval(() => { if (coin) drawHeat(); }, 1000);

// ------------------------------------------------------------------------------------------------ theme / start

function applyTheme(t) { document.documentElement.dataset.theme = t; localStorage.setItem('theme', t); if (chart) chart.applyOptions({ layout: { textColor: getComputedStyle(document.body).color } }); }
applyTheme(localStorage.getItem('theme') || (matchMedia('(prefers-color-scheme: light)').matches ? 'light' : 'dark'));
$('#theme').addEventListener('click', () => applyTheme(document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark'));
setActiveTab();
render();
connect();
