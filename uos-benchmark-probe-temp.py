import io,json,zipfile,urllib.request
from pathlib import Path
out=Path('uos-benchmark-probe-output'); out.mkdir(exist_ok=True)
base='https://www.borsaistanbul.com'
urls={
 'ilkislem.zip':'/datum/ilkislem.zip',
 'closed_companies.xls':'/datum/IslemSirasiKapananSirketler.xls',
 'symbol_changes.zip':'/datum/payadvekoddegisiklikleri.zip',
 'pay_endeksleri.zip':'/datum/PayEndeksleri.zip',
 'thb_20260904':'/data/thb/2026/09/thb202609041.zip',
 'thb_20240102':'/data/thb/2024/01/thb202401021.zip',
 'thb_20190102':'/data/thb/2019/01/thb201901021.zip',
 'thb_20180102':'/data/thb/2018/01/thb201801021.zip'
}
r={}
for label,path in urls.items():
    url=base+path
    try:
        req=urllib.request.Request(url,headers={'User-Agent':'Mozilla/5.0'})
        with urllib.request.urlopen(req,timeout=45) as resp:
            b=resp.read(); status=resp.status; ct=resp.headers.get('Content-Type')
        (out/label).write_bytes(b)
        item={'url':url,'status':status,'content_type':ct,'bytes':len(b),'zip':zipfile.is_zipfile(io.BytesIO(b))}
        if item['zip']:
            z=zipfile.ZipFile(io.BytesIO(b)); item['zip_names']=z.namelist()
            d=out/(Path(label).stem+'_extracted'); d.mkdir(exist_ok=True)
            z.extractall(d)
        else:
            item['head']=b[:100].decode('utf-8','replace')
        r[label]=item
    except Exception as e:r[label]={'url':url,'error':repr(e)}
(out/'probe.json').write_text(json.dumps(r,indent=2,ensure_ascii=False))
print(json.dumps(r,indent=2,ensure_ascii=False))
