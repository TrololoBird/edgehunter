#!/usr/bin/env python3
"""Low-overhead production sampler for the Release 1 acceptance window."""
import csv, os, subprocess, time
from pathlib import Path

def read(path):
    try: return Path(path).read_text().strip()
    except OSError: return ''

def main():
    out=os.environ.get('EDGEHUNTER_RUNTIME_OUT','runtime_observation.csv')
    c='/sys/fs/cgroup/system.slice/edgehunter-bot.service'
    exists=Path(out).exists()
    with open(out,'a',newline='') as f:
        w=csv.writer(f)
        if not exists: w.writerow(['ts','pid','restarts','memory_current','events','pressure','sqlite_fd_count'])
        while True:
            pid=subprocess.check_output(['systemctl','show','edgehunter-bot','-p','MainPID','--value'],text=True).strip()
            rest=subprocess.check_output(['systemctl','show','edgehunter-bot','-p','NRestarts','--value'],text=True).strip()
            fd=0
            try: fd=sum('signals.db' in os.readlink(f'/proc/{pid}/fd/{x}') for x in os.listdir(f'/proc/{pid}/fd'))
            except (OSError, ValueError): pass
            w.writerow([int(time.time()),pid,rest,read(f'{c}/memory.current'),read(f'{c}/memory.events'),read(f'{c}/memory.pressure'),fd]); f.flush()
            time.sleep(60)
if __name__=='__main__': main()
