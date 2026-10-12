"""ORB on majors only (daily open, session range, session Stretch), net and gross of costs. Run: python -I majors.py"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bt, sessions
SETS = {'top5 (BTC ETH SOL BNB XRP)': {'BTCUSDT', 'ETHUSDT', 'SOLUSDT', 'BNBUSDT', 'XRPUSDT'}}
SETS['top10 (+DOGE ADA AVAX LINK BCH)'] = SETS['top5 (BTC ETH SOL BNB XRP)'] | {'DOGEUSDT', 'ADAUSDT', 'AVAXUSDT', 'LINKUSDT', 'BCHUSDT'}
full = bt.load()
rep = []
for cost in (0.0020, 0.0007, 0.0):
    bt.COST = cost
    for sname, syms in SETS.items():
        data = {k: v for k, v in full.items() if k in syms}
        bt.load = lambda d=data: d
        r = {'daily open +- Stretch (bot)': bt.run_orb(data)['A base: stop / session close']}
        for mode, tag in (('range', '30m range'), ('stretch', 'open +- Stretch')):
            for k, v in sessions.run(mode).items():
                r[f"{k.split(' (')[0]} {tag}"] = v
        rep.append(bt.table(f"{sname}, costs {cost:.2%}", r)); print(rep[-1], flush=True)
open('report_majors.md', 'w').write('\n'.join(rep) + '\n')
