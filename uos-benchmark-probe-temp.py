import io,json,zipfile,urllib.request
from pathlib import Path
out=Path('uos-benchmark-probe-output'); out.mkdir(exist_ok=True)
r={}
urls=['https://www.borsaistanbul.com/files/DataFilePaths.zip','https://www.borsaistanbul.com/datum/DataFilePaths.zip','http://www.borsaistanbul.com/datum/DataFilePaths.zip']
for url in urls:
    try:
        req=urllib.request.Request(url,headers={'User-Agent':'Mozilla/5.0'})
        with urllib.request.urlopen(req,timeout=30) as resp:
            b=resp.read(); status=resp.status; ct=resp.headers.get('Content-Type')
        item={'status':status,'content_type':ct,'bytes':len(b)}
        if zipfile.is_zipfile(io.BytesIO(b)):
            z=zipfile.ZipFile(io.BytesIO(b)); item['zip_names']=z.namelist()
            for n in z.namelist():
                try:
                    data=z.read(n)
                    (out/('extracted_'+Path(n).name)).write_bytes(data)
                except Exception as e: item.setdefault('extract_errors',[]).append([n,repr(e)])
        else:
            item['head']=b[:500].decode('utf-8','replace')
        r[url]=item
    except Exception as e:r[url]={'error':repr(e)}
(out/'probe.json').write_text(json.dumps(r,indent=2,ensure_ascii=False))
print(json.dumps(r,indent=2,ensure_ascii=False))
