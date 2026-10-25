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
  if (v === null || v === undefined || !Number.isFinite(v)) return '—';
  const a = Math.abs(v);
  if (a === 0) return '0';
  if (a >= 1000) return v.toFixed(a >= 1e5 ? 0 : 1);
  const digits = Math.max(2, 4 - Math.floor(Math.log10(a)));
  return v.toFixed(Math.min(digits, 10));
}
// R the same way everywhere: sign, 2 decimals, colored
function rFmt(v) {
  if (v === null || v === undefined || !Number.isFinite(v)) return '<span class="dim">—</span>';
  return `<span class="${v > 0 ? 'up' : v < 0 ? 'down' : ''}">${v > 0 ? '+' : ''}${v.toFixed(2)}R</span>`;
}
function pct(v, d = 2, colored = true) {
  if (v === null || v === undefined || !Number.isFinite(v)) return '<span class="dim">—</span>';
  const s = (v >= 0 ? '+' : '') + (v * 100).toFixed(d) + '%';
  if (!colored) return s;
  return `<span class="${v > 0 ? 'up' : v < 0 ? 'down' : ''}">${s}</span>`;
}
// Sizing facts of an entered card (webui.sizing_view): information, never an order
function sizingText(z) {
  const lev = z.max_leverage ? `плечо ≤ ${z.max_leverage}× (ликвидация дальше стопа)` : 'плеча, при котором ликвидация дальше стопа, нет';
  const parts = [`стоп ${(z.stop_pct * 100).toFixed(2)}%`, lev];
  if (z.funding_8h !== null && z.funding_8h !== undefined)
    parts.push(`фандинг ${z.funding_8h >= 0 ? 'платите' : 'получаете'} ${Math.abs(z.funding_8h * 100).toFixed(3)}%/8ч`);
  if (z.notional_usd) parts.push(`объём $${usd(z.notional_usd)}` + (z.max_leverage ? ` (маржа $${usd(z.margin_usd)} при ${z.max_leverage}×` : ' (') + `, риск $${usd(z.risk_usd)})`);
  if (z.assumptions) parts.push(z.assumptions);
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
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
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
  event_risk: 'риск-событие биржи: метка Monitoring, делистинг Binance / Upbit или предупреждение Upbit — лонги запрещены',
  perp_led: 'движение ведёт перп, спот не подтверждает', no_orderflow: 'нет подтверждения ордерфлоу',
  no_oi: 'открытый интерес не подтверждает (у продолжения должен расти, после снятия стопов — падать)',
  no_flow: 'поток тейкеров против сделки', no_spot: 'спот против сделки',
  no_data: 'у монеты нет данных, без которых стратегию не оценить (спот для продолжения движения)',
  against_tide: 'против «прилива» (Элдер): тренд монеты на 1h или BTC за час против сделки',
  no_level: 'в полосе отката 0.382–0.618 нет ни уровня карты, ни EMA20 — не за что зацепиться',
  no_confirmation: 'ни одного подтверждения входа (поток, спот, OI, ордерфлоу) — по практике ордерфлоу вход только после подтверждения',
  weak_trend: 'откат к EMA20 без уровня карты, а ADX ≤ 30: по Рашке (Holy Grail) такой откат торгуется только в сильном тренде',
  no_spring_test: 'нет теста spring (объём отката высокий)', low_rr: 'R:R до TP1 < 1', regime: 'сетап минусовой в этом режиме рынка',
  no_leg: 'нет подходящей ноги: не из чего строить план', no_room: 'цена уже прошла все цели', same_leg: 'по этой ноге карточка уже была',
  market_move: 'движение всего рынка: тот же сетап у многих монет сразу',
  against_trend: 'против тренда монеты на 1h: снятие ликвидности против тренда обычно проваливается', disabled: 'стратегия выключена в конфиге', not_in_pool: 'монета не в пуле этой стратегии (класс / сектор / волатильность / плохая история на ней)',
  off_session: 'вне торговой сессии системы (SMT: 02:00–10:00 Нью-Йорк)',
};
// Strategies: each has its own anchor, entry and targets (strategies/)
// audit N33: what the code does now (timeframes, entry, stop, exit), checked against strategies/; the setup -> strategy
// map and each setup's mode (on / shadow / off) come from the registry (S.registry), not a hand-kept list
const FAMILY = {
  continuation: ['продолжение после импульса (ICT OTE)', 'импульс; откат в зону 0.62–0.79 ноги; вход по закрытию свечи, коснувшейся зоны (не лимит); стоп за началом импульса; цели — расширения ноги и уровни карты'],
  wyckoff: ['Вайкофф', 'SPRING / UTAD: прокол границы диапазона 4h с возвратом и тест; цель — противоположная сторона / P&F. FLUSH / SQUEEZE REVERSAL — только тень (не торгуются)'],
  sweep: ['снятие ликвидности (ICT)', 'SWEEP: 15m прокол пула с возвратом, затем MSS + FVG на младшем ТФ, вход по подтверждающему закрытию. SILVER BULLET: окна NY 03–04, 10–11, 14–15, FVG после снятия ликвидности, новый вход только внутри часа окна'],
  breakout: ['пробой: черепахи и Боллинджер Method I', 'BREAKOUT: дневной канал 20 (S1, пропуск после прибыльного) / 55 (S2), стоп 2N, +1 юнит каждые ½N до 4, выход по 10/20-дневному противоположному каналу. BB1: 4h — первое закрытие за полосой после сжатия (125 баров), подтверждение Intraday Intensity, выход по Parabolic SAR'],
  supply_demand: ['спрос / предложение (Сейден)', 'зона 4h; вход по подтверждающему закрытию после касания ближней границы; стоп за дальней границей; R:R до TP1 ≥ 3 (до ближайшей противоположной зоны); ≥ 8 из 10 баллов'],
  market_profile: ['Market Profile (Далтон)', 'VA80: возврат во вчерашнюю value area (TPO, 30-минутные периоды) двумя закрытиями → противоположный край; AUCTION: неудачный выход за VA с возвратом → противоположный край VA, выход в конце сессии'],
  trendline: ['трендовая линия (Эдвардс и Маги)', 'TL EM: линия через два последних пивота 2/2 на 1h; пробой — два закрытия 1h на ≥ 3% от линии (вверх — с объёмом); вход на ретесте линии и сломе младшего ТФ'],
  bollinger: ['W / M Боллинджера', '4h BB(20, 2): W-дно / M-вершина; половина на полосе в момент сигнала, остаток — до противоположной полосы 4h. BB3 (Method III) — только тень'],
  orb: ['диапазон открытия (Крэбел)', 'Stretch — среднее за 10 дней min(H−O, O−L); диапазон первых 5 минут сессии ± Stretch (три сессии); вход стоп-ордером на касании уровня, стоп — противоположный уровень; выход в конце сессии'],
  pump: ['памп / дамп', 'DUMP BOUNCE SHORT: дамп ≥ порога на объёме, минимум фиксируется при истощении, отскок к 38.2–61.8%, закрытие 1h под минимумом предыдущей свечи → шорт; TP1 — минимум дампа, TP2 — расширение 1.618. PUMP START / TOP выключены'],
  cup_handle: ['чашка с ручкой (О\'Нил)', 'дневки: чашка 7–65 недель (49–455 дней), глубина 12–33%, U-форма; ручка 1–8 недель в верхней половине ≤ 12% на падающем объёме; вход на закрытии выше пивота на объёме ≥ 1.4×; стоп под ручкой, не дальше 8% (иначе отказ); цели — доля глубины чашки (Булковски)'],
  connors: ['RSI(2) (Коннорс)', 'дневки, по книге (Connors/Alvarez 2008, гл. 9): выше SMA200 закрытие с RSI(2) < 5 → лонг на закрытии (RSI2X LONG); без стопа, плечо 1×; выход по закрытию выше SMA5. Вход на возврате из зоны (RSI2) и зеркальный шорт — только тень'],
  po3: ['Power of Three (ICT)', 'азиатский диапазон 20:00–00:00 NY, манипуляция за его границу в Лондоне 02:00–05:00 NY, MSS / FVG; цель — другая сторона Азии'],
  oi_build: ['рост OI', 'часовой рост OI выше обычного темпа, направление по цене — только тень (не торгуется)'],
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
  'BOMBERMAN LONG': 'MACD + QML вверх', 'BOMBERMAN SHORT': 'MACD + QML вниз', 'BB W-BOTTOM': 'W-дно Боллинджера', 'BB M-TOP': 'M-вершина Боллинджера',
  'PUMP START': 'начало пампа', 'PUMP TOP': 'вершина пампа', 'CUP HANDLE': 'чашка с ручкой',
  'SILVER BULLET LONG': 'Silver Bullet вверх', 'SILVER BULLET SHORT': 'Silver Bullet вниз',
  'VA80 LONG': 'возврат в value area снизу', 'VA80 SHORT': 'возврат в value area сверху',
  'ORB UP': 'пробой диапазона открытия вверх', 'ORB DOWN': 'пробой диапазона открытия вниз',
  'RSI2 LONG': 'RSI(2) возврат из перепроданности (тень)', 'RSI2 SHORT': 'RSI(2) возврат из перекупленности (тень)',
  'RSI2X LONG': 'RSI(2) < 5 выше SMA200 (по книге)', 'RSI2X SHORT': 'RSI(2) > 95 ниже SMA200 (тень)',
  'TL EM UP': 'пробой трендовой линии вверх', 'TL EM DOWN': 'пробой трендовой линии вниз',
  'BB1 UP': 'расширение после сжатия вверх', 'BB1 DOWN': 'расширение после сжатия вниз',
  'BB3 BUY': 'Bollinger Method III вверх (тень)', 'BB3 SELL': 'Bollinger Method III вниз (тень)',
  'PO3 LONG': 'Power of Three вверх', 'PO3 SHORT': 'Power of Three вниз',
  'OI BUILD LONG': 'рост OI вверх (тень)', 'OI BUILD SHORT': 'рост OI вниз (тень)',
  'DUMP BOUNCE SHORT': 'шорт первого отскока после дампа',
};
const STRATEGY_OF = {
  'BULL F': 'continuation', 'BEAR D': 'continuation', 'IMPULSE UP': 'continuation', 'IMPULSE DOWN': 'continuation',
  'SPRING': 'wyckoff', 'UTAD': 'wyckoff', 'FLUSH REVERSAL': 'wyckoff', 'SQUEEZE REVERSAL': 'wyckoff',
  'SWEEP LOW': 'sweep', 'SWEEP HIGH': 'sweep', 'SILVER BULLET LONG': 'sweep', 'SILVER BULLET SHORT': 'sweep',
  'BREAKOUT UP': 'breakout', 'BREAKOUT DOWN': 'breakout',
  'SD DEMAND': 'supply_demand', 'SD SUPPLY': 'supply_demand',
  'AUCTION LONG': 'market_profile', 'AUCTION SHORT': 'market_profile', 'VA80 LONG': 'market_profile', 'VA80 SHORT': 'market_profile',
  'TRENDLINE UP': 'trendline', 'TRENDLINE DOWN': 'trendline', 'BB W-BOTTOM': 'bollinger', 'BB M-TOP': 'bollinger',
  'ORB UP': 'orb', 'ORB DOWN': 'orb', 'RSI2 LONG': 'connors', 'RSI2 SHORT': 'connors',
  'PUMP START': 'pump', 'PUMP TOP': 'pump', 'CUP HANDLE': 'cup_handle',
};
const familyOf = setup => {
  const reg = S && S.registry && S.registry[setup];
  if (!reg) return STRATEGY_OF[setup] || '';
  // BB1 is registered under 'breakout' with the Turtles; its own text is in FAMILY.breakout
  return reg.strategy;
};
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
  equal: '#b28cff', pdhl: '#ff9f43', poc: '#3cc7e8', va: '#3cc7e8', hvn: '#3cc7e8', lvn: '#2a8fa8', liq_est: '#ff5c8a',
  liq_hit: '#ff8ac0', swing_1h: '#9aa6b8', swing_15m: '#6f7a8c', swing_1d: '#c9d1dd', wall: '#f5c542', vwap: '#5b8cff',
  fib: '#8e7cc3', range: '#ff9f43', liq_hl: '#ff3b3b', book: '#e0a0ff', round: '#7d8590', open: '#d4a017', htf: '#c9d1dd',
};
// ICT zones by family (the timeframe is the suffix): order blocks orange, FVGs teal, breakers violet, BPR gold
const ICT_COLORS = { ob: '#ff8c42', fvg: '#2ec4b6', breaker: '#a06cd5', bpr: '#e9c46a' };
const ICT_NAMES = { ob: 'ордерблок', fvg: 'FVG', breaker: 'breaker', bpr: 'BPR (наложение FVG)' };
const KIND_NAMES = {
  equal: 'равные хаи/лои (стопы)', pdhl: 'хай/лоу дня', poc: 'POC', va: 'value area', hvn: 'узел объёма', lvn: 'провал объёма (LVN)',
  book: 'ликвидность стакана (стояла ≥10м)', liq_est: 'ликвидации (оценка)', liq_hit: 'ликвидации (факт)', swing_1h: 'свинг 1h', swing_15m: 'свинг 15m',
  swing_1d: 'свинг дня', wall: 'стена стакана', vwap: 'VWAP', fib: 'Фибоначчи', range: 'край диапазона', liq_hl: 'ликвидации крупных счетов HL',
  round: 'круглое число', open: 'открытие дня / недели', htf: 'старший ТФ',
};
const kindColor = k => KIND_COLORS[k] || ICT_COLORS[(k || '').split('_')[0]] || '#888';
const kindName = k => KIND_NAMES[k] || (ICT_NAMES[(k || '').split('_')[0]] ? `${ICT_NAMES[k.split('_')[0]]} ${k.split('_')[1]}` : k);

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
        if (x === null || x === undefined || Number.isNaN(x)) return 1;
        if (y === null || y === undefined || Number.isNaN(y)) return -1;
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
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  const data = url.startsWith('/api/stats') ? await res.text() : await res.json();
  cache[url] = { t: Date.now(), data };
  return data;
}

// ------------------------------------------------------------------------------------------------ header

function renderHeader() {
  if (!S) return;
  const m = S.market || {};
  let html = '';
  for (const [k, v] of Object.entries(m)) html += `<span><b>${esc(k)}</b>${fp(v.price)} ${pct(v.change_5m)}</span>`;
  const ml = S.ml || {};
  if (ml.regime) html += `<span><b>режим</b><span class="${ml.regime.startsWith('up') ? 'up' : ml.regime.startsWith('down') ? 'down' : ''}">${esc(ml.regime)}</span></span>`;
  const NEWS = { binance_delist: ['делистинг Binance', 'down'], binance_listing: ['листинг Binance', 'up'],
    upbit_delist: ['делистинг Upbit', 'down'], upbit_warning: ['предупреждение Upbit', 'down'], upbit_listing: ['листинг Upbit KRW', 'up'], upbit_unwarn: ['Upbit снял предупреждение', 'up'] };
  const news = (S.news || []).filter(n => n.risk || nowSec() - n.ts < 172800);
  if (news.length) html += `<span title="${esc(news.map(n => `${n.base}: ${(NEWS[n.kind] || [n.kind])[0]}, ${ago(nowSec() - n.ts)} назад${n.risk ? ' — лонги запрещены' : ''}`).join('\n'))}"><b>анонсы</b>${news.slice(0, 6).map(n => `<span class="${(NEWS[n.kind] || ['', ''])[1]}">${esc(n.base)}${n.risk ? '⚠' : ''}</span>`).join(' ')}${news.length > 6 ? ' …' : ''}</span>`;
  const down = Object.entries(S.venues || {}).filter(([, v]) => v.connected === 0 || v.connected === false).map(([k]) => k);
  html += `<span class="dim">${S.symbols} монет · скан ${(S.timing?.scan ?? 0).toFixed(2)}с${down.length ? ' · <span class="down">нет связи: ' + esc(down.join(', ')) + '</span>' : ''}</span>`;
  $('#market').innerHTML = html;
  document.documentElement.style.setProperty('--hdr-h', $('#top').offsetHeight + 'px');   // the header wraps on narrow screens
  $('#status').textContent = S.status ? '⏳ ' + S.status : '';
  const cards = S.cards || [];
  const inTrade = cards.filter(c => c.entered_at && !c.finished);
  $('#n-trade').textContent = inTrade.length + (inTrade.some(c => c.demo !== undefined) ? ` · BingX ${inTrade.filter(c => c.demo && !c.demo.closed_ms).length}` : '');
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
  const lo = lv.sl, hi = lv.tp3 ?? lv.tp2 ?? lv.tp1;
  if (lo == null || hi == null || hi === lo) return '';
  const pos = v => Math.max(0, Math.min(100, (v - lo) / (hi - lo) * 100));
  const ticks = [lv.entry, lv.tp1, lv.tp2].filter(v => v != null).map(v => `<i style="left:${pos(v)}%"></i>`).join('');
  const color = c.r_now >= 0 ? 'var(--green)' : 'var(--red)';
  return `<div class="bar" title="SL → TP3">${ticks}<b style="left:${pos(c.price)}%;background:${color}"></b></div>`;
}

// the BingX demo mirror of a card in a trade: a position, or why there is none (the card's own trade goes on)
const DEMO_RU = { NO_MARKET: 'нет рынка на BingX', OVERLAP: 'монета занята другой карточкой', ERROR: 'ошибка ордера',
  EXCHANGE: 'закрыта биржей', UNTRACKED: 'закрыта как неотслеживаемая', ORPHAN: 'закрыта: карточка потерялась', SL: 'стоп',
  CLOSED: 'закрыта', TP3: 'TP3', NO_STOP: 'без стопа — закрыта' };
function demoCell(c) {
  const d = c.demo;
  if (!d) return '<span class="dim" title="BingX-демо не открывало эту карточку (до запуска демо, вне лимита или фильтров)">нет</span>';
  if (!d.closed_ms) return '<span class="pill good">в позиции</span>';
  const why = DEMO_RU[d.reason] || d.reason || '';
  return `<span class="pill bad" title="${esc(d.error || '')}">нет</span><br><span class="src">${esc(why)}${d.r !== null && d.r !== undefined ? ' ' + rFmt(d.r) : ''}, ${new Date(d.closed_ms).toLocaleString('ru', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' })}</span>`;
}
function renderTrade() {
  const rows = (S.cards || []).filter(c => c.entered_at && !c.finished).filter(matches);
  return `<div class="toolbar">${filterBox()}</div><div class="hint">Карточки, где сработал вход. Цели и стоп — из карты уровней монеты (источник под ценой). R сейчас — результат в единицах риска.</div>` +
    table('trade', [
      { k: 'Монета', v: setupCell, s: c => c.name },
      { k: 'Статус', v: c => statusPill(c.status) },
      { k: 'BingX', v: demoCell, s: c => c.demo ? (c.demo.closed_ms ? 1 : 0) : 2, tip: 'позиция зеркала на BingX-демо; если её нет — причина (наведите на «нет»)' },
      { k: 'Цена', v: c => fp(c.price), num: true },
      { k: 'Вход', v: c => fp(c.levels?.entry), num: true },
      { k: 'Стоп', v: c => c.levels ? `${fp(c.levels.sl)}<br><span class="src">${esc(c.levels.sl_src || '')}</span>` : '—', num: true },
      { k: 'Цели', v: c => c.levels ? targetsCell([c.levels.tp1, c.levels.tp2, c.levels.tp3], [c.levels.tp1_src, c.levels.tp2_src, c.levels.tp3_src]) : targetsCell(c.targets, c.target_src) },
      { k: 'R:R', v: c => (c.levels?.rr_tp1 || 0).toFixed(1), s: c => c.levels?.rr_tp1, num: true },
      { k: 'R сейчас', v: c => `${rFmt(c.r_now)}${c.r_now === null ? '' : progressBar(c)}`, s: c => c.r_now, num: true },
      { k: 'Подтверждения', v: confirmsCell, s: c => Object.values(c.confirms || {}).filter(v => v === true || (typeof v === 'string' && v !== 'n/a')).length, num: true,
        tip: 'на входе: поток тейкеров, спот, открытый интерес, ордерфлоу у экстремума; ★ — обязательное для этой стратегии' },
      { k: 'Толпа', v: crowdCell, s: c => c.crowd || 0, num: true, tip: 'сколько монет дали сетап того же направления за 5 минут: много — это движение всего рынка' },
      { k: 'Вход был', v: c => ago(nowSec() - c.entered_at), s: c => -c.entered_at, num: true },
      { k: 'Почему', v: c => esc((c.why || []).join(' · ')), wrap: true },
    ], rows, { empty: 'Открытых сделок нет.' });
}

function renderWait() {
  const rows = (S.cards || []).filter(c => !c.entered_at && !c.finished).filter(matches);
  return `<div class="toolbar">${filterBox()}</div><div class="hint">Сетапы, ждущие входа. У каждого семейства своя механика (наведи на название семейства).
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
let filterDir = Number(localStorage.getItem('fdir') || 0), filterStrat = localStorage.getItem('fstrat') || '';
function filterBox() {
  const strats = [...new Set((S.cards || []).map(c => c.strategy || c.mode).filter(Boolean))].sort();
  return `<input id="filter" placeholder="фильтр: монета или метка" value="${esc(filterText)}">
    <select id="fdir" title="направление"><option value="0">↕ все</option><option value="1" ${filterDir > 0 ? 'selected' : ''}>▲ long</option><option value="-1" ${filterDir < 0 ? 'selected' : ''}>▼ short</option></select>
    <select id="fstrat" title="стратегия"><option value="">все стратегии</option>${strats.map(x => `<option ${x === filterStrat ? 'selected' : ''}>${esc(x)}</option>`).join('')}</select>`;
}
const matches = r => (!filterText || (r.name + ' ' + (r.group_key || r.label || r.setup || '')).toLowerCase().includes(filterText.toLowerCase()))
  && (!filterDir || Math.sign(r.direction || 0) === filterDir)
  && (!filterStrat || (r.strategy || r.mode || familyOf(r.setup || r.group_key)) === filterStrat);
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
      { k: 'Метка', v: r => `<span title="${esc(ANOMALY_TIP[r.label] || '')}" class="${r.effect && r.effect.x < 1.1 ? 'dim' : ''}">${esc(r.label)}</span>`, s: r => r.label },
      { k: 'Эффект', v: r => r.effect ? `<span class="${r.effect.x >= 1.2 ? 'up' : 'dim'}" title="по журналу за 14 дней (${r.effect.n} случаев): размах цены за 4ч после такой метки против обычного 4-часового размаха этой же монеты; x1.0 = метка ничего не добавляет">x${r.effect.x.toFixed(2)}</span>` : '—', s: r => r.effect ? r.effect.x : 0, num: true },
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
      { k: 'Зона отката', v: r => r.zone ? `${fp(r.zone[0])} – ${fp(r.zone[1])}` : '—' },
      { k: 'Состояние', v: r => esc(r.state) + (r.levels ? ` · ${r.trade_dir > 0 ? 'лонг' : 'шорт'} ${fp(r.levels.entry)}, стоп ${fp(r.levels.stop)}, цели ${fp(r.levels.tp1)} / ${fp(r.levels.tp2)}` : ''), wrap: true },
      { k: 'История правила', v: r => r.stats ? `${esc(r.stats.label)}: ${esc(r.stats.verdict)}, ${esc(r.stats.r)}, цель ${esc(r.stats.hit)}` : '—', wrap: true },
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
      { k: 'Исключены по истории', v: r => Object.entries(r.excl).map(([c, x]) => `${esc(c)} (${x.blocks} 4ч-блоков, доказанный минус, ${x.r > 0 ? '+' : ''}${x.r}R)`).join(', ') || '—', wrap: true },
    ], rows, { empty: 'Нет пулов.' });
}

function renderForming() {
  const f = (S.forming || []).filter(matches), v = (S.vetoed || []).filter(matches);
  return `<div class="toolbar">${filterBox()}</div>
    <h3>Формируются <small>фазы набрали часть баллов на закрытой 15m-свече, карточки ещё нет</small></h3>` +
    table('forming', [
      { k: 'Монета', v: r => `<b>${esc(r.name)}</b> ${dirPill(r.direction)}`, s: r => r.name },
      { k: 'Фазы', v: r => r.phases.map(p => `${esc(p.name)} ${esc(p.score)}/${esc(p.max)}`).join(', '), s: r => Math.max(0, ...r.phases.map(p => p.score)), num: false },
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
  const [html, demo] = await Promise.all([api(`/api/stats?days=${days}`, 60), api('/api/demo', 60).catch(() => null)]);
  return `<div class="toolbar">${hoursPicker()} <span class="dim">отчёт stats.py по текущей версии логики (${esc(S.logic_version)})</span></div>${demoHtml(demo)}${html}`;
}

// The BingX demo account: equity curve in R with its drawdown, and each strategy's total with a daily-R sparkline
function demoHtml(demo) {
  // the same period as the stats report (the picker): the all-time total mixed in the executor's first days (stops
  // missing on BingX, orphans) and setups switched off since
  const since = Date.now() - hours * 3600e3;
  const tr = (demo && demo.trades || []).filter(t => t.r !== null && t.closed_ms && t.closed_ms >= since);
  const open = (demo && demo.trades || []).filter(t => !t.closed_ms).length;
  if (!tr.length) return `<h3>Демо-счёт BingX: за период закрытых сделок нет${open ? ` · открыто ${open}` : ''}</h3>`;
  const per = {};
  for (const t of tr) {
    const st = per[t.strategy || '?'] = per[t.strategy || '?'] || { strategy: t.strategy || '?', n: 0, wins: 0, r: 0, days: {} };
    st.n++; st.wins += t.r > 0; st.r += t.r;
    const day = Math.floor(t.closed_ms / 86400000); st.days[day] = (st.days[day] || 0) + t.r;
  }
  const strategies = Object.values(per).map(st => ({ ...st, days: Object.entries(st.days).sort((a, b) => a[0] - b[0]) })).sort((a, b) => a.r - b.r);
  let eq = 0, peak = 0, maxDd = 0;
  const pts = tr.map(t => { eq += t.r; peak = Math.max(peak, eq); maxDd = Math.min(maxDd, eq - peak); return [t.closed_ms, eq, eq - peak]; });
  const w = 720, h = 160, x0 = pts[0][0], x1 = pts[pts.length - 1][0] || x0 + 1;
  const lo = Math.min(0, ...pts.map(p => p[1]), maxDd), hi = Math.max(0.5, ...pts.map(p => p[1]));
  const X = t => ((t - x0) / Math.max(1, x1 - x0) * (w - 40) + 36).toFixed(1), Y = v => (h - 14 - (v - lo) / (hi - lo) * (h - 24)).toFixed(1);
  const line = pts.map(p => `${X(p[0])},${Y(p[1])}`).join(' ');
  const dd = pts.map(p => `${X(p[0])},${Y(p[2])}`).join(' ');
  const svg = `<svg class="equity" viewBox="0 0 ${w} ${h}" role="img" aria-label="кривая доходности демо в R">
    <line x1="36" x2="${w - 4}" y1="${Y(0)}" y2="${Y(0)}" class="axis"/>
    <text x="2" y="${+Y(hi) + 4}" class="tick">${hi.toFixed(1)}R</text><text x="2" y="${+Y(lo) + 4}" class="tick">${lo.toFixed(1)}R</text>
    <polygon points="${X(x0)},${Y(0)} ${dd} ${X(x1)},${Y(0)}" class="dd"/>
    <polyline points="${line}" class="eq"/></svg>`;
  const rows = strategies.map(st => `<tr><td>${esc(st.strategy)}</td><td class="num">${st.n}</td>
    <td class="num">${st.n ? Math.round(st.wins / st.n * 100) : 0}%</td><td class="num">${rFmt(st.r)}</td>
    <td>${barsSpark(st.days.map(d => d[1]))}</td></tr>`).join('');
  return `<h3>Демо-счёт BingX за ${hours >= 48 ? Math.round(hours / 24) + ' дн' : hours + ' ч'}: ${tr.length} сделок, итог ${rFmt(eq)}, макс. просадка ${rFmt(maxDd)}${open ? ` · открыто ${open}` : ''}</h3>${svg}
    <div class="tablewrap"><table class="tbl"><thead><tr><th>Стратегия</th><th>Сделок</th><th>В плюс</th><th>R</th><th>R по дням</th></tr></thead><tbody>${rows}</tbody></table></div>`;
}
function barsSpark(v) {
  if (!v.length) return '';
  const m = Math.max(...v.map(Math.abs), 0.01), bw = 6, h = 24;
  return `<svg class="spark" width="${v.length * bw}" height="${h}">${v.map((x, i) => {
    const bh = Math.max(1, Math.abs(x) / m * (h / 2));
    return `<rect x="${i * bw}" y="${x >= 0 ? h / 2 - bh : h / 2}" width="${bw - 1}" height="${bh}" fill="${x >= 0 ? 'var(--green)' : 'var(--red)'}"/>`;
  }).join('')}</svg>`;
}

function renderHealth() {
  const v = S.venues || {};
  const boxes = Object.entries(v).sort().map(([name, st]) => `<div class="box"><h4>${esc(name)} ${st.connected === 0 || st.connected === false ? '<span class="pill bad">нет связи</span>' : '<span class="pill good">ok</span>'}</h4>
    <div class="kv">${Object.entries(st).map(([k, x]) => `<span>${esc(k)}</span><span class="mono">${typeof x === 'number' ? (Math.abs(x) >= 1000 ? usd(x) : +x.toFixed(2)) : esc(x)}</span>`).join('')}</div></div>`).join('');
  const ml = S.ml || {};
  return `<div class="grid">
    <div class="box"><h4>Скан</h4><div class="kv"><span>tier-0</span><span class="mono">${S.timing.tier0.toFixed(2)}с ${spark('tier0', 'var(--cyan)')}</span>
      <span>скан</span><span class="mono">${S.timing.scan.toFixed(2)}с ${spark('scan', 'var(--violet)')}</span><span>тяжёлый проход</span><span class="mono">${S.timing.heavy.toFixed(2)}с ${spark('heavy', 'var(--orange)')}</span>
      <span>монет</span><span class="mono">${S.symbols}</span><span>стаканов</span><span class="mono">${S.hot}</span>
      <span>логика</span><span class="mono">${esc(S.logic_version)}</span></div></div>
    <div class="box"><h4>ML</h4><div class="kv"><span>режим</span><span>${esc(ml.regime || '—')}</span>
      <span>модель аномалий</span><span>${ml.anomaly_ready ? 'обучена ' + Math.round(ml.anomaly_age_min) + 'м назад' : 'копит ' + ml.anomaly_samples + ' сэмплов'}</span>
      <span>P(edge)</span><span>${ml.p_n} размеченных${ml.p_mature ? '' : ' (показ с 300)'}${ml.p_accuracy ? ', точность ' + (ml.p_accuracy * 100).toFixed(0) + '%' : ''}</span>
      <span>режимы</span><span>${ml.regime_candles} свечей${ml.regime_age_h != null ? ', модель ' + ml.regime_age_h.toFixed(1) + 'ч' : ''}</span>
      <span>предобучение</span><span>${ml.pretrained_rows ? ml.pretrained_rows + ' строк, ' + ml.pretrained_coins + ' монет, ' + esc(ml.pretrained_span) + ' (' + ml.pretrained_age_d.toFixed(1) + 'д назад)' : 'нет'}${ml.pretrain_running ? ' · <span class="warn">идёт обучение</span>' : ''}</span></div></div>
  </div><h3>Биржи</h3><div class="grid">${boxes}</div>`;
}

// ------------------------------------------------------------------------------------------------ analysis tab
// Pinned coins always + any typed ticker: zones, scenarios and a mechanical checklist (briefing.Briefing.analyze).
let anQuery = localStorage.getItem('anq') || '', anLast = 0;
const VERDICT_CLS = { 'нет': 'bad', 'осторожно': 'warn', 'приемлемо': 'warn', 'формальные условия выполнены': 'good' };
// eng-168o: the verdict of a limited analysis carries a prefix; a limited one is never shown as 'good'
const verdictCls = v => { const base = String(v || '').replace(/^ограниченный анализ: /, ''); const c = VERDICT_CLS[base] || '';
  return base !== String(v || '') && c === 'good' ? 'warn' : c; };
function anCard(a) {
  const altLine = x => (x && x.alternatives && x.alternatives.length) ? `<div class="dim warn">другие контракты по этому тикеру: ${x.alternatives.map(esc).join(', ')}</div>` : '';
  if (!a || a.error) return `<div class="box"><h4>${esc((a && a.symbol) || '')}</h4><div class="empty">${esc((a && a.error) || 'нет данных')}</div>${altLine(a)}</div>`;
  const zones = (a.zones || []).slice().sort((x, y) => y.lo - x.lo).map(z => {
    const tag = z.side > 0 ? '<span class="bad">сопр.</span>' : z.side < 0 ? '<span class="good">подд.</span>' : '<span class="cyan">цена в зоне</span>';
    return `<tr><td>${tag}</td><td class="mono">${fp(z.lo)}–${fp(z.hi)}</td><td class="mono">${Math.round(z.strength)}</td><td>${esc(z.label)}</td></tr>`;
  }).join('');
  const sc = ['long', 'short'].map(k => {
    const s = a.scenarios && a.scenarios[k];
    if (!s) return `<div class="box"><h4>${k === 'long' ? 'Лонг' : 'Шорт'}</h4><div class="dim">сценария нет</div></div>`;
    const checks = s.checks.map(([n, st, v]) => `<span>${esc(n)}</span><span class="${st === 'ok' ? 'good' : st === 'bad' ? 'bad' : 'warn'}">${esc(v)}</span>`).join('');
    return `<div class="box"><h4>${esc(s.name)} <span class="pill ${verdictCls(s.verdict)}">${esc(s.verdict)}</span></h4>
      <div class="dim">${esc(s.cond)}</div>
      <div class="kv"><span>вход</span><span class="mono">${fp(s.entry[0])}–${fp(s.entry[1])}</span><span>стоп</span><span class="mono">${fp(s.stop)}</span>
      <span>цели</span><span class="mono">${s.targets.map(fp).join(' / ')}</span><span>R:R до TP1</span><span class="mono">${s.rr.toFixed(1)}</span>
      <span>безубыточная доля TP1*</span><span class="mono">${(s.p * 100).toFixed(0)}%</span>${checks}</div></div>`;
  }).join('');
  const T = (a.outcomes && a.outcomes.tally) || {};
  const NM = { tp1: 'TP1', stop: 'стоп', open: 'без исхода', cancelled: 'отменён', no_entry: 'не сработал' };
  const oc = Object.keys(T).length ? `<div class="dim">Исходы брифингов за ${a.outcomes.days} дн.: ` + Object.entries(T).map(([side, m]) =>
    side + ' — ' + Object.entries(m).map(([k, n]) => `${NM[k] || k} ${n}`).join(', ')).join(' · ') + '</div>' : '';
  const cards = (a.cards || []).map(c => `${esc(c.mode)} ${esc(c.setup)} ${c.direction > 0 ? '▲' : '▼'} ${esc(c.status)}`).join(' · ');
  return `<div class="box an-card"><h4>${esc(a.base)} <span class="mono">${fp(a.price)}</span>
      ${a.chg_day != null ? `<span class="${a.chg_day >= 0 ? 'good' : 'bad'}">${a.chg_day >= 0 ? '+' : ''}${a.chg_day.toFixed(2)}%</span>` : ''}
      ${a.light ? '<span class="pill warn" title="монета вне вселенной бота: только свечи Binance, без потоков, ликвидаций и карты уровней">только свечи</span>' : ''}</h4>
    <div class="dim">${esc(a.bias_line || '')}</div>
    ${(a.notices || []).map(n => `<div class="dim warn">${esc(n)}</div>`).join('')}
    ${altLine(a)}
    ${a.data_as_of && a.data_as_of.fetched_at ? `<div class="dim">загружено: ${new Date(a.data_as_of.fetched_at * 1000).toLocaleTimeString()} (цена — последнее значение текущей 1h на момент загрузки)</div>` : ''}
    ${a.data_as_of && a.data_as_of.last_closed_1h ? `<div class="dim">данные: последняя закрытая 1h ${new Date(a.data_as_of.last_closed_1h).toLocaleString()} · ${a.data_as_of.source === 'binance_rest' ? 'REST Binance' : 'память бота'}</div>` : ''}
    ${a.macro && a.macro.length ? `<div class="warn">Макро сегодня (МСК): ${a.macro.map(esc).join(', ')}</div>` : ''}
    ${cards ? `<div>Карточки бота: ${cards}</div>` : ''}
    <div class="tablewrap"><table><tbody>${zones || '<tr><td class="dim">зон рядом нет</td></tr>'}</tbody></table></div>
    ${oc}<div class="grid">${sc}</div></div>`;
}
async function refreshAnalysis() {
  const pin = $('#an-pinned'), res = $('#an-result');
  if (!pin || !res) return;
  anLast = Date.now();
  const [p, one] = await Promise.all([
    api('/api/pinned', 20).catch(() => null),
    anQuery ? api('/api/analysis?symbol=' + encodeURIComponent(anQuery), 20).catch(() => null) : null]);
  if (tab !== 'analysis') return;
  res.innerHTML = anQuery ? (one ? anCard(one) : '<div class="empty">Ошибка запроса</div>') : '';
  const ot = $('#an-total');
  if (ot) {
    const T = (p && p.outcomes && p.outcomes.tally) || {};
    const NM = { tp1: 'TP1', stop: 'стоп', open: 'вход без исхода', cancelled: 'отменён', no_entry: 'не сработал' };
    ot.innerHTML = Object.keys(T).length ? `<div class="dim">Исходы сценариев брифингов, все закреплённые монеты, ${p.outcomes.days} дн. (копится с трёх сводок в день, 12 ч на сценарий): `
      + Object.entries(T).map(([side, m]) => `<b>${esc(side)}</b>: ` + Object.entries(m).map(([k, n]) => `${NM[k] || k} ${n}`).join(', ')).join(' · ') + '</div>' : '';
  }
  pin.innerHTML = p && p.coins.length ? p.coins.map(anCard).join('') : '<div class="empty">Нет данных</div>';
}
function renderAnalysis() {
  if (!$('#an-pinned')) {
    $('#view').innerHTML = `<div class="box"><form id="an-form"><input id="an-q" placeholder="Тикер любой монеты, например PEPE или SOL" value="${esc(anQuery)}" autocomplete="off" maxlength="24"> <button>Показать</button></form>
      <div class="dim">Уровни и чек-лист — механические правила (зоны разворотов 1h/4h/1d, ATR, старший ТФ, макро, карточки бота), не совет и не гарантия. R:R брутто, без комиссий и проскальзывания; пороги чек-листа не измерены. *Шанс TP1 по расстоянию — модель случайного блуждания без дрейфа.</div></div>
      <div id="an-result"></div><h3>Закреплённые монеты</h3><div id="an-total"></div><div id="an-pinned"><div class="empty">Загрузка…</div></div>`;
  }
  return refreshAnalysis();
}
document.addEventListener('submit', e => {
  if (e.target.id !== 'an-form') return;
  e.preventDefault();
  anQuery = $('#an-q').value.trim().toUpperCase(); localStorage.setItem('anq', anQuery);
  $('#an-result').innerHTML = anQuery ? '<div class="empty">Загрузка…</div>' : '';
  refreshAnalysis();
});

const RENDER = { trade: renderTrade, wait: renderWait, done: renderDone, anom: renderAnom, forming: renderForming, stats: renderStats, health: renderHealth, analysis: null };
if (!(tab in RENDER)) tab = 'wait';
let renderSeq = 0;
async function render() {
  if (!S) { $('#view').innerHTML = '<div class="empty">Подключение к боту…</div>'; return; }
  renderHeader();
  if (document.activeElement && document.activeElement.tagName === 'SELECT' && document.activeElement.closest('#view')) return;   // an open list closes on re-render
  if (tab === 'analysis') { renderSeq++; await renderAnalysis(); return; }
  const seq = ++renderSeq;
  const focus = document.activeElement && document.activeElement.id;
  const pos = focus === 'filter' ? document.activeElement.selectionStart : null;
  let html;
  try { html = await RENDER[tab](); } catch (err) { html = `<div class="empty">Ошибка: ${esc(err.message)}</div>`; }
  if (seq !== renderSeq) return;
  const y = window.scrollY;
  const hs = [...document.querySelectorAll('#view .tablewrap')].map(el => el.scrollLeft);
  $('#view').innerHTML = html;
  document.querySelectorAll('#view .tablewrap').forEach((el, i) => { if (hs[i]) el.scrollLeft = hs[i]; });
  window.scrollTo(0, y);
  if (focus === 'filter') { const f = $('#filter'); f.focus(); f.setSelectionRange(pos, pos); }
}

document.addEventListener('input', e => {
  if (e.target.id === 'filter') { filterText = e.target.value; render(); }
});
document.addEventListener('change', e => {
  if (e.target.id === 'hours') { hours = Number(e.target.value); localStorage.setItem('hours', hours); render(); }
  if (e.target.id === 'fdir') { filterDir = Number(e.target.value); localStorage.setItem('fdir', filterDir); render(); }
  if (e.target.id === 'fstrat') { filterStrat = e.target.value; localStorage.setItem('fstrat', filterStrat); render(); }
});
document.querySelectorAll('#tabs button').forEach(b => b.addEventListener('click', () => {
  if (tab === b.dataset.tab) return;
  tab = b.dataset.tab; localStorage.setItem('tab', tab); setActiveTab();
  if (['done', 'anom', 'stats', 'analysis'].includes(tab)) $('#view').innerHTML = '<div class="empty">Загрузка…</div>';
  render();
}));
function setActiveTab() { document.querySelectorAll('#tabs button').forEach(b => b.classList.toggle('active', b.dataset.tab === tab)); }

// Live tabs re-render on every state; journal-backed tabs every 60s (their data changes slowly)
let lastSlow = 0;
function onState() {
  const slow = ['done', 'anom', 'stats', 'analysis'].includes(tab);
  if (!slow || Date.now() - lastSlow > 60000) { lastSlow = Date.now(); render(); } else renderHeader();
}

// ------------------------------------------------------------------------------------------------ websocket

let lastMsg = 0, retry = 0;
function connect() {
  const ws = new WebSocket(`${location.protocol === "https:" ? "wss" : "ws"}://${location.host}/ws`);
  ws.onopen = () => { $('#conn').className = 'dot on'; retry = 0; };
  ws.onmessage = ev => {
    S = JSON.parse(ev.data); lastMsg = Date.now(); onState(); notifyTrades(); healthSample();
    if (coin && Date.now() - coinLoaded > 20000) loadCoin();
  };
  // backoff 2s .. 30s: a restarting bot is not hammered every 2 seconds
  ws.onclose = () => { $('#conn').className = 'dot off'; retry += 1; setTimeout(connect, Math.min(30000, 2000 * retry)); };
}
setInterval(() => {
  const age = lastMsg ? Math.round((Date.now() - lastMsg) / 1000) : null;
  $('#conn').title = age === null ? 'нет связи с ботом' : `связь с ботом · обновлено ${age}с назад`;
  if (age !== null && age > 30) $('#conn').className = 'dot off';
  const ca = $('#conn-age');   // touch screens have no tooltips: the age as text
  ca.textContent = age === null ? 'нет связи' : age > 10 ? `${age}с назад` : '';
  ca.className = age === null || age > 30 ? 'down mono' : 'dim mono';
}, 1000);

// browser notifications of new trades (opt-in, the bell in the header)
let notifyOn = localStorage.getItem('notify') === '1' && 'Notification' in window && Notification.permission === 'granted';
let seenTrades = null;
function bell() { $('#notify').textContent = notifyOn ? '🔔' : '🔕'; }
$('#notify').addEventListener('click', async () => {
  if (!('Notification' in window)) return;
  if (!notifyOn && Notification.permission !== 'granted') await Notification.requestPermission();
  notifyOn = !notifyOn && Notification.permission === 'granted';
  localStorage.setItem('notify', notifyOn ? '1' : '0'); bell();
});
bell();
function notifyTrades() {
  const ids = new Set((S.cards || []).filter(c => c.entered_at && !c.finished).map(c => c.symbol + '|' + (c.group_key || '')));
  if (seenTrades && notifyOn && document.hidden)
    for (const id of ids) if (!seenTrades.has(id)) new Notification('Новая сделка', { body: id.replace(':USDT', '').replace('|', ' · ') });
  seenTrades = ids;
}

// the Health tab's sparklines: the last hour of scan timings, sampled from the state pushes
const HEALTH = [];
function healthSample() {
  if (!S || !S.timing) return;
  const t = Date.now();
  if (HEALTH.length && t - HEALTH[HEALTH.length - 1].t < 10000) return;
  HEALTH.push({ t, tier0: S.timing.tier0, scan: S.timing.scan, heavy: S.timing.heavy });
  while (HEALTH.length > 360) HEALTH.shift();
}
function spark(key, color) {
  const v = HEALTH.map(h => h[key] || 0);
  if (v.length < 2) return '';
  const max = Math.max(...v, 0.01), w = 160, h = 28;
  const pts = v.map((x, i) => `${(i / (v.length - 1) * w).toFixed(1)},${(h - x / max * h).toFixed(1)}`).join(' ');
  return `<svg class="spark" viewBox="0 0 ${w} ${h}" width="${w}" height="${h}" aria-label="${key}"><polyline fill="none" stroke="${color}" stroke-width="1.5" points="${pts}"/></svg>`;
}

// ------------------------------------------------------------------------------------------------ coin drawer

let coin = null, coinLoaded = 0, chart = null, series = null, tf = 15, coinData = null, priceLines = [], fibSeries = [];
let shownZones = [];     // the zones drawn as boxes on the canvas (drawZoneBoxes)
let oiSeries = null, cvdSeries = null, cvdSpotSeries = null, demoTrades = [], seriesMarkers = null;
const tzShift = -new Date().getTimezoneOffset() * 60;

function openCoin(symbol, leg) {
  coin = symbol;
  if ($('#zone-tip')) $('#zone-tip').hidden = true;
  // The chart matches the card's leg: 1h candles for a 1h / 4h leg (the whole leg visible), 5m for the minute legs of
  // momentum / sweep / exhaustion / absorption / range setups, 15m otherwise
  tf = leg === '1h' || leg === '4h' || leg === '1d' || leg === '1w' ? 60 : leg === '1m' || leg === '5m' ? 5 : 15;
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
    // OI and CVD under the candles on their own scales (lightweight-charts 4 has no panes: overlay scales with margins)
    chart.subscribeCrosshairMove(zoneTip);
    series = chart.addSeries(LightweightCharts.CandlestickSeries, { upColor: '#2ecc71', downColor: '#ff5c5c', borderVisible: false, wickUpColor: '#2ecc71', wickDownColor: '#ff5c5c', priceFormat: { type: 'price', precision: 6, minMove: 0.000001 } });
    seriesMarkers = LightweightCharts.createSeriesMarkers(series, []);
  }
  coinData = null;
  series.setData([]); seriesMarkers.setMarkers([]);
  priceLines.forEach(l => series.removePriceLine(l)); priceLines = []; shownZones = [];
  chart.priceScale('right').applyOptions({ autoScale: true });
  loadCoin(true);
}
$('#d-close').addEventListener('click', () => { coin = null; $('#drawer').classList.add('hidden'); });
document.addEventListener('keydown', e => { if (e.key === 'Escape' && coin) $('#d-close').click(); });
document.querySelectorAll('.tf').forEach(b => b.addEventListener('click', () => {
  tf = Number(b.dataset.tf); document.querySelectorAll('.tf').forEach(x => x.classList.toggle('active', x === b)); drawCoin(true);
}));

let coinSeq = 0, htfTimer = null;
async function loadCoin(fit = false) {
  const symbol = coin, seq = ++coinSeq; coinLoaded = Date.now();
  clearTimeout(htfTimer);
  try {
    $('#chart').classList.add('loading');
    const [res, trades] = await Promise.all([fetch(`/api/coin?symbol=${encodeURIComponent(symbol)}`),
      fetch(`/api/demo?symbol=${encodeURIComponent(symbol)}`).then(r => r.ok ? r.json() : { trades: [] }).then(x => x.trades || []).catch(() => [])]);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    if (symbol !== coin || seq !== coinSeq) return;
    demoTrades = trades;
    coinData = data; drawCoin(fit);
    // The 1h / 5m history is loading in the background: ask again shortly
    if (!data.htf_loaded && !data.note) htfTimer = setTimeout(() => { if (coin === symbol) loadCoin(false); }, 4000);
  } catch (err) { if (symbol === coin && seq === coinSeq) $('#d-body').innerHTML = `<div class="empty">Ошибка: ${esc(err.message)}</div>`; }
  finally { if (symbol === coin && seq === coinSeq) $('#chart').classList.remove('loading'); }
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

// 4h / 1d candles from the 1h history (UTC-aligned buckets, like the exchange's): [ts, o, h, l, c, ...]
function aggregate(rows, minutes) {
  if (minutes <= 60) return rows;
  const size = minutes * 60000, out = [];
  for (const c of rows) {
    const t = Math.floor(c[0] / size) * size, last = out[out.length - 1];
    if (last && last[0] === t) { last[2] = Math.max(last[2], c[2]); last[3] = Math.min(last[3], c[3]); last[4] = c[4]; }
    else out.push([t, c[1], c[2], c[3], c[4]]);
  }
  return out;
}

// OI / CVD on the chart's timeframe: the 15m series (the 5m chart shows them per 15m, 1h+ resamples them)
function drawFlow(bars) {
  const on = $('#flow-on') && $('#flow-on').checked, rows = (coinData && coinData.flow_15m) || [];
  // v5 panes under the candles: OI (pane 1), futures / spot CVD (pane 2); removed with their series when off
  // the flow series covers ~5 days of 15m candles: a dot on the daily chart, hidden there
  if (!on || !rows.length || !bars.length || tf >= 1440) {
    for (const s of [oiSeries, cvdSeries, cvdSpotSeries]) if (s) chart.removeSeries(s);
    oiSeries = cvdSeries = cvdSpotSeries = null; return;
  }
  if (!oiSeries) {
    const opt = (color, title) => ({ color, lineWidth: 1, priceLineVisible: false, lastValueVisible: true, crosshairMarkerVisible: false, title,
      priceFormat: { type: 'volume' } });
    oiSeries = chart.addSeries(LightweightCharts.LineSeries, opt('#f5c542', 'OI'), 1);
    cvdSeries = chart.addSeries(LightweightCharts.LineSeries, opt('#3cc7e8', 'CVD фьюч'), 2);
    cvdSpotSeries = chart.addSeries(LightweightCharts.LineSeries, opt('#b28cff', 'CVD спот'), 2);
    const panes = chart.panes(), total = $('#chart').clientHeight;
    if (panes.length >= 3) { panes[1].setHeight(Math.round(total * 0.17)); panes[2].setHeight(Math.round(total * 0.17)); }
  }
  const size = Math.max(15, tf) * 60, t0 = bars[0].time, oi = new Map(), fd = new Map(), sd = new Map();
  for (const [ms, o, f, sp] of rows) {
    const t = Math.floor(ms / 1000 / size) * size + tzShift;
    if (t < t0) continue;
    if (o !== null) oi.set(t, o);
    fd.set(t, (fd.get(t) || 0) + (f || 0)); if (sp !== null) sd.set(t, (sd.get(t) || 0) + sp);
  }
  const cum = m => { let a = 0; return [...m.entries()].sort((x, y) => x[0] - y[0]).map(([time, v]) => ({ time, value: (a += v) })); };
  oiSeries.setData([...oi.entries()].sort((a, b) => a[0] - b[0]).map(([time, value]) => ({ time, value })));
  cvdSeries.setData(cum(fd)); cvdSpotSeries.setData(sd.size ? cum(sd) : []);
}

// a tooltip with the zone under the cursor: its sources, strength, timeframe
function zoneTip(param) {
  const tip = $('#zone-tip'); if (!tip) return;
  if (!param || !param.point || !coinData) { tip.hidden = true; return; }
  const price = series.coordinateToPrice(param.point.y);
  const z = price === null ? null : (coinData.zones || []).find(z => price >= z.lo && price <= z.hi);
  if (!z) { tip.hidden = true; return; }
  tip.innerHTML = `<b>${fp(z.lo)} – ${fp(z.hi)}</b> · сила ${z.strength ?? '—'}<br>${(z.kinds || []).map(k => esc(kindName(k))).join(', ')}`;
  tip.hidden = false;
  const box = $('#chart');
  tip.style.left = Math.max(4, Math.min(param.point.x + 14, box.clientWidth - 224)) + 'px';
  tip.style.top = Math.max(4, Math.min(param.point.y + 14, box.clientHeight - tip.offsetHeight - 8)) + 'px';
}

function drawCoin(fit) {
  const d = coinData; if (!d || d.error) { $('#d-body').innerHTML = `<div class="empty">${esc(d && d.error)}</div>`; return; }
  const raw = tf === 1440 ? (d.candles_1d && d.candles_1d.length ? d.candles_1d : aggregate(d.candles_1h || [], tf))
    : tf === 240 ? (d.candles_4h && d.candles_4h.length ? d.candles_4h : aggregate(d.candles_1h || [], tf))
    : tf === 60 ? (d.candles_1h || []) : tf === 15 ? (d.candles_15m || []) : (d.candles_5m || []);
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
  const card0 = (d.cards || []).find(c => !c.finished) || (d.cards || [])[0];
  // «фибо»: the card's own grid (continuation) or, for any other chart, the visible leg - the window's high and low,
  // the later one is the leg's end (retracements 0.236..0.786 from it, extensions 1.272 / 1.618 beyond)
  const fibCard = $('#fib-on').checked && card0 && card0.fib;
  const fibAuto = false;      // the visible-window grid is gone: «фибо» = the continuation card's own grid
  const fibOn = fibCard;
  // with the Fibonacci grid on, the map keeps only its strong zones: the grid is the story, the rest is noise
  const TFR = { '5m': 0, '15m': 1, '1h': 2, '4h': 3, '1d': 4, '1w': 5 };
  const chartRank = tf >= 1440 ? 4 : tf >= 240 ? 3 : tf === 60 ? 2 : tf === 15 ? 1 : 0;
  const LTF_UNTIMED = new Set(['vwap', 'round', 'book', 'liq_est', 'liq_hit', 'liq_hl', 'equal', 'hvn', 'lvn', 'wall']);
  const zoneRank = z => {           // geometry._zone_rank: the zone's highest timeframe; null = valid on every chart
    let r = -1;
    for (const k of z.kinds || []) {
      const t = k.includes('_') ? k.split('_').pop() : null;
      if (t in TFR) r = Math.max(r, TFR[t]); else if (LTF_UNTIMED.has(k)) r = Math.max(r, 1); else return null;
    }
    return r < 0 ? null : r;
  };
  const allLv = $('#lv-all') && $('#lv-all').checked;
  let hiP = -Infinity, loP = Infinity;
  for (const b of bars) { if (b.high > hiP) hiP = b.high; if (b.low < loP) loP = b.low; }
  const pad = (hiP - loP) * 0.5, px = d.price || (bars.length ? bars[bars.length - 1].close : 0);
  const perSide = allLv ? 12 : 4;
  const cand = (d.zones || []).filter(z => { const r = zoneRank(z); return r === null || r >= chartRank; })
    .filter(z => allLv || z.strength >= 2)
    .filter(z => !bars.length || (z.hi >= loP - pad && z.lo <= hiP + pad));
  const pick = side => cand.filter(z => side > 0 ? z.lo > px : z.hi < px)
    .sort((a, b) => b.strength - a.strength).slice(0, perSide);
  const around = cand.filter(z => z.lo <= px && z.hi >= px).sort((a, b) => b.strength - a.strength).slice(0, 1);
  const zones = [...pick(1), ...around, ...pick(-1)];
  const usedKinds = new Set();
  shownZones = [];
  for (const z of zones) {
    const kind = z.kinds[0]; usedKinds.add(kind);
    const strong = z.strength >= 2;
    if (z.hi > z.lo) {
      // a box: the price tag on the axis only (the line itself would cut through the box)
      shownZones.push(z);
      priceLines.push(series.createPriceLine({ price: z.price, color: kindColor(kind), lineVisible: false,
        axisLabelVisible: strong, title: strong ? z.label.split(' · ')[0] : '' }));
    } else line(z.price, kindColor(kind), strong ? z.label.split(' · ')[0] : '', strong ? 0 : 2, z.strength >= 4 ? 2 : 1, strong);
  }
  // order-book densities that stayed and price has not reached yet (webui.untaken_densities)
  const dens = (d.densities || []).slice().sort((a, b) => b.usd - a.usd);
  for (const den of [...dens.filter(x => x.side > 0).slice(0, 2), ...dens.filter(x => x.side < 0).slice(0, 2)]) {
    const usd = den.usd >= 1e6 ? (den.usd / 1e6).toFixed(1) + 'M' : (den.usd / 1e3).toFixed(0) + 'k';
    line(den.price, den.side > 0 ? '#2ecc71' : '#ff5c5c', `плотн. ${den.side > 0 ? 'bid' : 'ask'} $${usd}`, 1, 2);
  }
  // The Fibonacci grid of a continuation card (the screenshots' layout): the impulse A -> B and the pullback B -> C as
  // dashed legs, the retracements with the OTE band 0.62-0.79, the trend-based extensions 1.0 / 1.2 / 1.272 / 1.618 from C
  fibSeries.forEach(s => chart.removeSeries(s)); fibSeries = [];
  if (fibOn) {
    const f = card0.fib;
    const t = ms => Math.floor(ms / 1000 / (tf * 60)) * (tf * 60) + tzShift;
    const legLine = (pts, color) => {
      const ls = chart.addSeries(LightweightCharts.LineSeries, { color, lineWidth: 2, lineStyle: 2, priceLineVisible: false, lastValueVisible: false,
        crosshairMarkerVisible: false });
      ls.setData(pts.filter(p => p.time !== undefined && !Number.isNaN(p.time)).sort((a, b) => a.time - b.time)
        .filter((p, i, arr) => i === 0 || p.time > arr[i - 1].time));
      fibSeries.push(ls);
    };
    if (f.a_ts && f.b_ts) {
      const pts = [{ time: t(f.a_ts), value: f.a }, { time: t(f.b_ts), value: f.b }];
      const legCol = document.documentElement.dataset.theme === 'light' ? 'rgba(40,50,70,.75)' : 'rgba(201,209,221,.85)';
      legLine(pts, legCol);
      if (f.c !== undefined && card0.entered_at) legLine([{ time: t(f.b_ts), value: f.b }, { time: t(card0.entered_at * 1000), value: f.c }], legCol);
    }
    line(f.a, '#7d8590', 'A · начало импульса', 2, 1); line(f.b, '#7d8590', 'B · конец импульса', 2, 1);
    for (const [r, p] of f.retr) {
      const ote = r >= 0.618;
      line(p, ote ? '#f5c542' : '#7d8590', r === 0.705 ? 'OTE 0.705' : String(r), r === 0.705 ? 0 : 2, ote ? 2 : 1);
    }
    for (const [k, p] of f.ext || []) line(p, '#2ecc71', `ext ${k}`, 1, k === 1.618 ? 2 : 1);
    if (f.c !== undefined) line(f.c, '#9aa6b8', 'C · дно коррекции', 2, 1);
  }
  if (fibAuto) {
    const win = bars.slice(-Math.min(bars.length, 150));
    let hi = win[0], lo = win[0];
    for (const b of win) { if (b.high > hi.high) hi = b; if (b.low < lo.low) lo = b; }
    const up = lo.time < hi.time;               // low first, then high = an up leg (retracements down from the high)
    const a0 = up ? lo.low : hi.high, b0 = up ? hi.high : lo.low, rng = b0 - a0;
    line(a0, '#7d8590', 'фибо 1.0', 2, 1); line(b0, '#7d8590', 'фибо 0', 2, 1);
    for (const r of [0.236, 0.382, 0.5, 0.618, 0.786]) {
      const ote = r >= 0.618;
      line(b0 - rng * r, ote ? '#f5c542' : '#8e7cc3', 'фибо ' + r, ote ? 0 : 2, ote ? 2 : 1);
    }
    for (const k of [1.272, 1.618]) line(b0 + rng * (k - 1), '#2ecc71', 'ext ' + k, 1, 1);
  }
  const card = card0;
  if (card) {
    if (card.zone && card.zone[0] && !card.entered_at) {
      const age = card.created && !card.finished ? ` · ждёт ${ago(nowSec() - card.created)}` : '';
      line(card.zone[0], '#f5c542', 'зона' + age, 1, 2); line(card.zone[1], '#f5c542', 'зона', 1, 2);
    }
    if (card.levels) {
      const lv = card.levels;
      // a Turtle pyramid: unit 1 is the entry, units 2..4 dashed; the stop follows the LAST unit (2N below it)
      const units = card.units || [];
      line(lv.entry, '#3cc7e8', units.length > 1 ? 'вход · юнит 1' : 'вход', 0, 2);
      units.slice(1).forEach((u, i) => line(u, '#3cc7e8', `юнит ${i + 2}`, 2, 1, false));
      const slNote = /from unit (\d)/.exec(lv.sl_src || ''), be = /break-even/.test(lv.sl_src || ''), tr = /trail/.test(lv.sl_src || '');
      line(lv.sl, '#ff5c5c', slNote ? `стоп · 2N от юнита ${slNote[1]}` : be ? 'стоп · безубыток' : tr ? 'стоп · трейлинг' : 'стоп', 0, 2);
      if (card.exit_level) line(card.exit_level, '#ff9f43', `выход · ${card.trail_days}-дн. ${card.direction > 0 ? 'минимум' : 'максимум'}`, 1, 2);
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
  // entries always; anomalies / setups / cards only with «события» on (they buried the candles and the grid)
  const evOn = $('#ev-on').checked;
  const markers = (d.journal || []).filter(r => r.kind !== 'structured' && (evOn || r.kind === 'entry')).map(r => {
    const t = Math.floor(r.ts_ms / 1000 / size) * size + tzShift;
    if (r.kind === 'setup') return { time: t, position: r.direction > 0 ? 'belowBar' : 'aboveBar', color: '#e0a0ff', shape: 'circle', text: (SETUP_RU[r.group_key] || r.group_key).split(' ')[0] };
    if (r.kind === 'anomaly') return { time: t, position: r.direction < 0 ? 'aboveBar' : 'belowBar', color: r.direction > 0 ? '#2ecc71' : r.direction < 0 ? '#ff5c5c' : '#9aa6b8', shape: 'circle', text: r.group_key.split(' ')[0].slice(0, 6) };
    if (r.kind === 'entry') return { time: t, position: r.direction > 0 ? 'belowBar' : 'aboveBar', color: r.vetoed ? '#9aa6b8' : '#3cc7e8', shape: r.direction > 0 ? 'arrowUp' : 'arrowDown', text: r.vetoed ? '✗' : 'вход' };
    if (r.kind === 'card') return { time: t, position: 'aboveBar', color: '#f5c542', shape: 'square', text: r.group_key.split(' ')[0].toLowerCase() };
    return null;
  }).filter(m => m && barTimes.has(m.time)).sort((a, b) => a.time - b.time);
  // the BingX demo trades of this coin: entry / exit markers colored by result
  for (const t of demoTrades) {
    const at = ms => Math.floor(ms / 1000 / size) * size + tzShift;
    const ti = at(t.opened_ms);
    if (barTimes.has(ti)) markers.push({ time: ti, position: t.direction > 0 ? 'belowBar' : 'aboveBar', color: '#3cc7e8', shape: t.direction > 0 ? 'arrowUp' : 'arrowDown', text: 'демо' });
    if (t.closed_ms && t.r !== null && barTimes.has(at(t.closed_ms)))
      markers.push({ time: at(t.closed_ms), position: t.direction > 0 ? 'aboveBar' : 'belowBar', color: t.r >= 0 ? '#2ecc71' : '#ff5c5c', shape: 'square', text: `${t.r >= 0 ? '+' : ''}${t.r.toFixed(1)}R` });
  }
  markers.sort((a, b) => a.time - b.time);
  // several events on one bar (a daily candle holds a whole day of them) stacked into an unreadable column and their
  // texts overlapped at the top: one marker per bar and side, the most important kind kept, the rest counted
  const RANK = { 'демо': 5, 'вход': 4 };
  const merged = new Map();
  for (const m of markers) {
    const k = m.time + '|' + m.position, prev = merged.get(k);
    if (!prev) { merged.set(k, { ...m, n: 1 }); continue; }
    const keep = (RANK[m.text] || (m.shape === 'square' ? 3 : 1)) > (RANK[prev.text] || (prev.shape === 'square' ? 3 : 1)) ? { ...m, n: prev.n } : prev;
    keep.n = prev.n + 1; merged.set(k, keep);
  }
  seriesMarkers.setMarkers([...merged.values()].map(({ n, ...m }) => (n > 1 ? { ...m, text: `${m.text} +${n - 1}` } : m))
    .sort((a, b) => a.time - b.time));
  // price-axis labels closer than ~16px overlapped (0.014000 under the price, 0.008000 under «1w high»): the first drawn
  // keeps its label (the card's lines are drawn last, so walk backwards: card > zones)
  const hPx = $('#chart').clientHeight || 300, shown = bars.length ? [bars[bars.length - 1].close] : [];
  const vis = bars.length ? bars.slice(-150) : [];
  const span = vis.length ? Math.max(...vis.map(b => b.high)) - Math.min(...vis.map(b => b.low)) : 0;
  if (span > 0) for (const pl of [...priceLines].reverse()) {
    const o = pl.options(); if (!o.axisLabelVisible) continue;
    if (shown.some(p => Math.abs(p - o.price) / span * hPx < 16)) pl.applyOptions({ axisLabelVisible: false, title: '' });
    else shown.push(o.price);
  }
  drawFlow(bars);
  if (fit) {
    // a drag / wheel on the price axis turns its auto-scale off for good: the next coin (TAO ~300 -> NEAR ~5.9) kept the
    // old range and its candles sat off-screen - every new coin / timeframe starts auto-scaled again
    chart.priceScale('right').applyOptions({ autoScale: true });
    chart.timeScale().fitContent();
  }
  drawHeat();

  $('#d-title').innerHTML = `${esc(d.symbol.replace(':USDT', '').replace('/USDT', ''))} <small>${fp(d.price)} · ATR 15m ${fp(d.atr)}${d.note ? ' · монета вне текущей вселенной: без карты уровней' : d.htf_loaded ? '' : ' · 1h история ещё грузится'}</small>`;
  $('#legend').innerHTML = [...usedKinds].map(k => `<span><i style="background:${kindColor(k)}"></i>${esc(kindName(k))}</span>`).join('') +
    '<span class="dim">сплошные — сильные зоны (конфлюэнция ≥ 2), пунктир — слабые</span>' +
    ($('#heat-on').checked && d.heatmap ? '<span class="heat-scale" title="яркость = объём корзины к медиане своего бара (лог-шкала)"><i class="hs-bid"></i>bid <i class="hs-ask"></i>ask · ×2 … ×16+ к медиане</span>' : '');

  let body = '';
  const NEWS_RU = { binance_delist: 'Binance объявил делистинг', binance_listing: 'листинг на Binance',
    upbit_delist: 'Upbit объявил делистинг', upbit_warning: 'Upbit: монета в списке предупреждений', upbit_listing: 'листинг на Upbit (KRW)', upbit_unwarn: 'Upbit снял предупреждение' };
  if (d.news || d.event_risk) body += `<div class="hint ${d.event_risk ? 'down' : ''}">${d.news ? `Анонс: ${esc(NEWS_RU[d.news.kind] || d.news.kind)}, ${ago(d.news.age_h * 3600)} назад` : ''}${d.event_risk ? `${d.news ? ' · ' : ''}лонги запрещены (${esc(d.event_risk === 'monitoring' ? 'метка Monitoring на Binance' : d.event_risk.startsWith('delisting ') ? 'делистинг фьючерса ' + d.event_risk.slice(10) : NEWS_RU[d.event_risk] || d.event_risk)})` : ''}</div>`;
  for (const c of d.cards || []) {
    body += `<h3>${dirPill(c.direction)} ${esc(c.setup)} <small>${esc((FAMILY[c.strategy] || [''])[0])}</small> ${statusPill(c.status)} <small>${c.finished ? esc(reasonRu(c.finish_reason)) : 'создан ' + ago(nowSec() - c.created) + ' назад'}</small></h3>
      <div class="hint">опора: ${anchorText(c)}</div>
      <div class="hint">${esc((c.why || []).join(' · '))}</div>
      ${c.shadow_veto ? `<div class="hint">тень: запретили бы ${esc(c.shadow_veto)}</div>` : ''}
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
      { k: 'Тип', v: z => z.kinds.map(k => `<span style="color:${kindColor(k)}">${esc(kindName(k))}</span>`).join(', '), wrap: true },
    ], (d.zones || []).slice().sort((a, b) => b.price - a.price), { empty: 'Карта ещё не построена (нужна история свечей).' }) +
    `<h3>Журнал монеты за 48ч</h3>` +
    table('coin-journal', [
      { k: 'Время', v: r => clock(r.ts_ms), s: r => r.ts_ms },
      { k: 'Тип', v: r => ({ anomaly: 'аномалия', structured: 'фаза', setup: 'сетап', entry: 'вход', card: 'итог' })[r.kind] || esc(r.kind) },
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

function hexA(hex, a) {
  const h = (hex || '#888888').replace('#', ''), f = h.length === 3 ? h.split('').map(c => c + c).join('') : h;
  const n = parseInt(f.slice(0, 6), 16);
  return `rgba(${(n >> 16) & 255},${(n >> 8) & 255},${n & 255},${a})`;
}

// Zones as boxes from the candle that made them to the chart's right edge (an older origin than the visible window
// starts at the left edge; ts 0 = timeless levels such as the previous day's high span the whole width)
function drawZoneBoxes(ctx, box) {
  if (!chart || !series || !shownZones.length) return;
  const plotWidth = box.width - chart.priceScale('right').width();
  const ts = chart.timeScale();
  ctx.save();
  ctx.font = '11px system-ui, sans-serif'; ctx.textBaseline = 'top';
  const labelYs = [];
  for (const z of shownZones) {
    const y1 = series.priceToCoordinate(z.hi), y2 = series.priceToCoordinate(z.lo);
    if (y1 === null || y2 === null) continue;
    let x0 = 0;
    if (z.ts) {
      const t = Math.floor(z.ts / 1000 / (tf * 60)) * (tf * 60) + tzShift;
      const x = ts.timeToCoordinate(t);
      if (x !== null) x0 = Math.max(0, x);
      else { const vr = ts.getVisibleRange(); if (vr && t > vr.to) continue; }
    }
    if (x0 >= plotWidth) continue;
    const color = kindColor(z.kinds[0]);
    const strong = z.strength >= 2;
    const top = Math.min(y1, y2), h = Math.max(1, Math.abs(y2 - y1));
    // a wide zone (> 2 ATR of the chart's 15m ATR, or > 18% of the chart's height) is drawn as its two edges only:
    // filled, the 4h breakers / FVGs covered half the chart and hid the candles
    const wide = (coinData && coinData.atr && (z.hi - z.lo) > 2 * coinData.atr) || h > 0.18 * box.height;
    if (!wide) {
      ctx.fillStyle = hexA(color, strong ? 0.16 : 0.08);
      ctx.fillRect(x0, top, plotWidth - x0, h);
    }
    ctx.strokeStyle = hexA(color, strong ? 0.75 : 0.4); ctx.lineWidth = 1;
    ctx.setLineDash(strong ? [] : [4, 3]);
    ctx.strokeRect(x0 + 0.5, top + 0.5, plotWidth - x0 - 1, h - 1);
    if (h >= 12 && !labelYs.some(y => Math.abs(y - top) < 16)) {
      labelYs.push(top);
      ctx.fillStyle = hexA(color, 0.95);
      ctx.fillText(z.label.split(' · ').slice(0, 2).join(' · '), x0 + 4, top + 2, plotWidth - x0 - 8);
    }
  }
  ctx.restore();
}

function drawHeat() {
  const canvas = $('#heat'); if (!canvas || !chart) return;
  const box = $('#chart').getBoundingClientRect();
  const dpr = window.devicePixelRatio || 1;
  const cw = Math.round(box.width * dpr), ch = Math.round(box.height * dpr);
  if (canvas.width !== cw || canvas.height !== ch) { canvas.width = cw; canvas.height = ch; }   // assigning reallocates the buffer
  const ctx = canvas.getContext('2d'); ctx.setTransform(dpr, 0, 0, dpr, 0, 0); ctx.clearRect(0, 0, box.width, box.height);
  // only over the candles' pane (the OI / CVD panes sit below it)
  const pane0 = chart.panes()[0], paneH = pane0 ? pane0.getHeight() : box.height;
  ctx.beginPath(); ctx.rect(0, 0, box.width, paneH); ctx.clip();
  drawZoneBoxes(ctx, box);
  const hm = coinData && coinData.heatmap;
  if (!hm || !hm.snapshots.length || !$('#heat-on').checked) return;   // (the zone boxes are drawn above)
  const size = tf * 60, bars = new Map();
  for (const [ms, levels] of hm.snapshots) {
    const t = Math.floor(ms / 1000 / size) * size + tzShift;
    let bar = bars.get(t); if (!bar) { bar = { n: 0, v: new Map() }; bars.set(t, bar); }
    bar.n += 1;
    for (const [price, usd] of levels) bar.v.set(price, (bar.v.get(price) || 0) + usd);
  }
  const spacing = chart.timeScale().options().barSpacing;
  const plotWidth = box.width - chart.priceScale('right').width();
  // brightness = the bucket against the MEDIAN bucket of its own bar: only real densities light up (scaled to one
  // screen-wide maximum, every bucket of a deep book looked alike)
  const cells = [];
  for (const [t, bar] of bars) {
    const x = chart.timeScale().timeToCoordinate(t); if (x === null) continue;
    const vals = [...bar.v.values()].map(v => Math.abs(v / bar.n)).sort((a, b) => a - b);
    const med = vals.length ? vals[Math.floor(vals.length / 2)] : 0;
    if (!med) continue;
    for (const [price, sum] of bar.v) {
      const usd = sum / bar.n;
      const y1 = series.priceToCoordinate(price + hm.step / 2), y2 = series.priceToCoordinate(price - hm.step / 2);
      if (y1 === null || y2 === null) continue;
      cells.push([x, y1, y2, usd, Math.abs(usd) / med]);
    }
  }
  // only strong, persistent heat by default: a bucket that held >= 4x its bar's median in >= 3 bars of the window
  // (the bot's liquidity bands use the same idea); «всё тепло» shows every bucket >= 2x as before
  const all = $('#heat-all') && $('#heat-all').checked;
  const strongBars = new Map();
  if (!all) for (const [, y1, , usd, ratio] of cells) if (ratio >= 4) {
    const k = Math.round(y1) + (usd > 0 ? 'b' : 'a'); strongBars.set(k, (strongBars.get(k) || 0) + 1);
  }
  // the price range the last REST snapshot covered (depth.py: levels outside it are known only once they change)
  const cov = hm.cov || [];
  const cy1 = cov[1] ? series.priceToCoordinate(cov[1]) : null, cy2 = cov[0] ? series.priceToCoordinate(cov[0]) : null;
  for (const [x, y1, y2, usd, ratio] of cells) {
    if (x - spacing / 2 > plotWidth || ratio < (all ? 2 : 4)) continue;
    if (!all && (strongBars.get(Math.round(y1) + (usd > 0 ? 'b' : 'a')) || 0) < 3) continue;
    const a = Math.min(0.7, 0.18 * Math.log2(ratio));
    if (a < 0.05) continue;
    ctx.fillStyle = usd > 0 ? `rgba(46,204,113,${a})` : `rgba(255,92,92,${a})`;
    ctx.fillRect(x - spacing / 2, Math.min(y1, y2), spacing, Math.max(1, Math.abs(y2 - y1)));
  }
  if (cy1 !== null && cy2 !== null) {
    ctx.strokeStyle = 'rgba(160,170,190,.35)'; ctx.setLineDash([2, 4]);
    for (const y of [cy1, cy2]) { ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(plotWidth, y); ctx.stroke(); }
    ctx.setLineDash([]);
  }
}
$('#heat-on').addEventListener('change', drawHeat);
$('#heat-all').addEventListener('change', drawHeat);
$('#lv-all').addEventListener('change', () => drawCoin(false));
$('#flow-on').addEventListener('change', () => drawCoin(false));
// touch screens show no title tooltips: a tap on a toolbar label's «?» shows its explanation
document.querySelectorAll('.heat-toggle[title]').forEach(l => {
  const q = document.createElement('button'); q.className = 'ghost q'; q.type = 'button'; q.textContent = '?'; q.setAttribute('aria-label', 'пояснение');
  q.addEventListener('click', e => { e.preventDefault(); e.stopPropagation(); const p = $('#pop'), same = !p.hidden && p.dataset.src === l.title; p.textContent = l.title; p.dataset.src = l.title; p.hidden = same; });
  l.appendChild(q);       // inside the label: a narrow screen wrapped a lone «?» to the next line
});
document.addEventListener('click', e => { const p = $('#pop'); if (p && !p.hidden && !e.target.classList.contains('q')) p.hidden = true; });
$('#fib-on').addEventListener('change', () => drawCoin(false));
$('#ev-on').addEventListener('change', () => drawCoin(false));
window.addEventListener('resize', () => requestAnimationFrame(drawHeat));
// The price scale can move without an event (auto-scale): check once a second, redraw only when the view moved
let heatSig = '';
setInterval(() => {
  if (!coin || !chart || !series || document.hidden) return;
  const ts = chart.timeScale(), r = ts.getVisibleLogicalRange();
  const px = coinData && coinData.price;
  const sig = [r && r.from, r && r.to, px && series.priceToCoordinate(px), $('#chart').clientWidth, $('#chart').clientHeight,
               coinData && coinData.heatmap && coinData.heatmap.snapshots.length].join('|');
  if (sig !== heatSig) { heatSig = sig; drawHeat(); }
}, 1000);
$('#d-shot').addEventListener('click', () => {
  if (!chart) return;
  const src = chart.takeScreenshot(), heat = $('#heat'), out = document.createElement('canvas');
  out.width = src.width; out.height = src.height;
  const ctx = out.getContext('2d'); ctx.fillStyle = getComputedStyle(document.body).backgroundColor; ctx.fillRect(0, 0, out.width, out.height); ctx.drawImage(src, 0, 0); if (heat.width) ctx.drawImage(heat, 0, 0, src.width, src.height);
  const a = document.createElement('a'); a.download = `${coin.replace(/[/:]/g, '_')}_${tf}m.png`; a.href = out.toDataURL('image/png'); a.click();
});

// ------------------------------------------------------------------------------------------------ theme / start

function applyTheme(t) {
  document.documentElement.dataset.theme = t; localStorage.setItem('theme', t);
  const grid = t === 'light' ? 'rgba(0,0,0,.06)' : 'rgba(128,128,128,.08)';
  if (chart) chart.applyOptions({ layout: { textColor: getComputedStyle(document.body).color },
    grid: { vertLines: { color: grid }, horzLines: { color: grid } } });
}
applyTheme(localStorage.getItem('theme') || (matchMedia('(prefers-color-scheme: light)').matches ? 'light' : 'dark'));
$('#theme').addEventListener('click', () => applyTheme(document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark'));
setActiveTab();
render();
connect();
