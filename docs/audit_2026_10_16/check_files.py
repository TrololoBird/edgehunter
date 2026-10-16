import ast,json,subprocess,re,pickletools,hashlib,pathlib
import numpy as np
import polars as pl
root=pathlib.Path(__file__).resolve().parents[2]; out=root/'docs/audit_2026_10_16'; files=subprocess.check_output(['git','ls-files'],cwd=root,text=True).splitlines(); data=[]
for fn in files:
 p=root/fn; b=p.read_bytes(); a={'path':fn,'bytes':len(b),'sha256':hashlib.sha256(b).hexdigest()}
 try:
  if p.suffix=='.py':
   s=b.decode(); t=ast.parse(s);a['format']='Python AST PASS';a['lines']=len(s.splitlines());a['functions']=[{'name':n.name,'line':n.lineno,'end':n.end_lineno} for n in ast.walk(t) if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef))]; a['risk_lines']=[{'line':i,'text':line.strip()[:240]} for i,line in enumerate(s.splitlines(),1) if re.search(r'shift\(-|bfill|backward|train_test_split|\.fit\(|pickle.load|eval\(|shell=True|verify=False|random\.choice|np\.quantile|searchsorted|sort\(|ORDER BY|except Exception',line)]
  elif p.suffix=='.json':
   d=json.loads(b);a['format']='JSON PASS';a['structure']={'type':type(d).__name__,'len':len(d),'keys':list(d)[:25] if isinstance(d,dict) else None}
  elif p.suffix=='.parquet':
   d=pl.read_parquet(p);a['format']='Parquet full decode PASS';a['shape']=d.shape;a['schema']={k:str(v) for k,v in d.schema.items()};a['nulls']=d.null_count().to_dicts()[0];a['nonfinite']={k:int((~d[k].is_finite() & d[k].is_not_null()).sum()) for k,v in d.schema.items() if v in (pl.Float32,pl.Float64)}
  elif p.suffix=='.npz':
   with np.load(p,allow_pickle=False) as z:
    a['format']='NPZ PASS (allow_pickle=False)';a['arrays']={k:{'shape':z[k].shape,'dtype':str(z[k].dtype),'nonfinite':int((~np.isfinite(z[k])).sum()) if z[k].dtype.kind in 'fc' else None} for k in z.files}
  elif p.suffix=='.pkl':
   ops=list(pickletools.genops(b));a['format']='Pickle opcode parse PASS, NOT executed';a['opcodes']=len(ops);a['globals']=[str(arg) for op,arg,pos in ops if op.name in ('GLOBAL','STACK_GLOBAL')][:15];a['tail_strings']=[arg for op,arg,pos in ops if op.name in ('SHORT_BINUNICODE','BINUNICODE')][-35:]
  elif p.suffix in ('.md','.txt'):
   s=b.decode();a['format']='UTF-8 PASS';a['lines']=len(s.splitlines());a['headings']=re.findall(r'^#{1,4} .+',s,re.M);a['versions']=list(dict.fromkeys(re.findall(r'eng-?\d+',s)))[:30];a['risk_lines']=[{'line':i,'text':line.strip()[:240]} for i,line in enumerate(s.splitlines(),1) if re.search(r'void|INVALID|невалид|look.ahead|surviv|устар|не доказ|НЕ |не прош|fail|no evidence|no verdict|verdict|итог|вывод|conclusion|PASS',line,re.I)][:12]
  else:a['format']='UTF-8 PASS';b.decode()
 except Exception as e:a['error']=str(e)
 data.append(a)
(out/'file_checks.json').write_text(json.dumps(data,ensure_ascii=False,indent=2))
for a in data:
 if 'error'in a:print('ERROR',a['path'],a['error'])
print('FILES',len(data),'PY',sum(a['path'].endswith('.py') for a in data))
