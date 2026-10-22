import re,base64,os,sys
s=open('guide.src.html',encoding='utf-8').read()
missing=[]
def rep(m):
    n=m.group(1); f=f'images/{n}.webp'
    if not os.path.exists(f): missing.append(n); return m.group(0)
    b=base64.b64encode(open(f,'rb').read()).decode()
    from PIL import Image
    w,h=Image.open(f).size
    return f'data-shot="{n}" data-w="{w}" data-h="{h}" data-src="data:image/webp;base64,{b}"'
s=re.sub(r'data-shot="([\w-]+)"',rep,s)
open('../fide-test-development-user-guide.html','w',encoding='utf-8').write('<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover"></head><body>'+s+'</body></html>')
print('missing',missing, 'size', len(s)//1024,'KB')
used=set(re.findall(r'data-shot="([\w-]+)"',open('guide.src.html').read()))
print('unused', set(f[:-5] for f in os.listdir('images'))-used)
