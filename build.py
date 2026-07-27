#!/usr/bin/env python3
"""Build the static recipe viewer (index.html) from Josh's Notion Recipes database.

Usage:  python3 build.py [output_path]        # default: ./index.html

Reads Notion through the `tools notion ...` CLI (the connected Notion integration
supplies auth - there are no keys in this file or this repo). See README.md.
"""
import base64, html, io, json, os, re, subprocess, sys, tempfile
from collections import Counter
from datetime import datetime
from PIL import Image

DATA_SOURCE_ID = "338302d3-e376-8022-9690-000b195d7cfb"   # Recipes database
OUT = sys.argv[1] if len(sys.argv) > 1 else "index.html"
WORK = tempfile.mkdtemp(prefix="recipes-")


def tools(*args):
    r = subprocess.run(["tools", *args], capture_output=True, text=True)
    if r.returncode != 0:
        raise SystemExit("tools %s failed: %s" % (" ".join(args), r.stderr.strip() or r.stdout.strip()))
    return json.loads(r.stdout)


def prop(p):
    t = p.get("type")
    if t in ("rich_text", "title"):
        return "".join(x.get("plain_text", "") for x in p[t])
    if t == "multi_select":
        return [x["name"] for x in p[t]]
    if t == "number":
        return p[t]
    return None


print("querying Notion...")
rows = tools("notion", "query-data-source", "--data-source-id", DATA_SOURCE_ID,
             "--body", json.dumps({"page_size": 100}), "--json")["results"]

data = []
for r in rows:
    pr = r["properties"]
    cov = r.get("cover")
    data.append(dict(
        id=r["id"], url=r["url"],
        title=prop(pr["Name"]),
        tags=prop(pr["Tags"]),
        prep=prop(pr["Preparation Time"]),
        serv=prop(pr["Servings"]),
        ing=prop(pr["Ingredients"]),          # categorized one-liner, used for the shopping list
        ins=prop(pr["Instructions"]),         # short summary; page body is the real method
        notes=prop(pr["Notes"]),
        cover=(cov.get("external") or cov.get("file") or {}).get("url") if cov else None,
    ))
data = [r for r in data if (r["title"] or "").strip()]
print("  %d recipes" % len(data))

# page bodies (full quantities + numbered steps live here, not in the properties)
for r in data:
    print("  body: %s" % r["title"])
    r["md"] = tools("notion", "read-page-markdown", "--page-id", r["id"], "--json")["result"]["markdown"]

# covers: Notion's S3 links expire, so every image is downloaded and embedded as a data URI
def img_data(url, w=900, q=68):
    if not url:
        return None
    p = os.path.join(WORK, "cover")
    if subprocess.run(["curl", "-sL", "--max-time", "30", "-A", "Mozilla/5.0", "-o", p, url]).returncode:
        return None
    try:
        im = Image.open(p).convert("RGB")
    except Exception:
        return None
    if im.width > w:
        im = im.resize((w, round(im.height * w / im.width)), Image.LANCZOS)
    b = io.BytesIO()
    im.save(b, "WEBP", quality=q, method=5)
    return "data:image/webp;base64," + base64.b64encode(b.getvalue()).decode()

for r in data:
    print("  cover: %s" % r["title"])
    r["imgdata"] = img_data(r["cover"])

recipes = data

def esc(s): return html.escape(s or '')

def inline(s):
    s = re.sub(r'\\([\\`*_{}\[\]()#+\-.!~>|])', r'\1', s)
    s = esc(s)
    s = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', s)
    s = re.sub(r'(?<!\*)\*([^*]+)\*(?!\*)', r'<em>\1</em>', s)
    s = re.sub(r'\[([^\]]+)\]\(([^)]+)\)', r'<a href="\2" target="_blank" rel="noopener">\1</a>', s)
    return s

def render_md(md):
    lines = md.split('\n')
    out, i = [], 0
    listbuf, listtype = [], None
    def flush():
        nonlocal listbuf, listtype
        if listbuf:
            out.append('<%s class="rl">%s</%s>' % (listtype, ''.join('<li>%s</li>' % x for x in listbuf), listtype))
            listbuf, listtype = [], None
    while i < len(lines):
        ln = lines[i]
        m = re.match(r'\s*<callout icon="([^"]*)"[^>]*>\s*$', ln)
        if m:
            flush(); icon = m.group(1); body = []
            i += 1
            while i < len(lines) and '</callout>' not in lines[i]:
                body.append(lines[i].strip()); i += 1
            i += 1
            out.append('<div class="note"><span class="note-i">%s</span><div>%s</div></div>' % (esc(icon), inline(' '.join(x for x in body if x))))
            continue
        s = ln.strip()
        if not s:
            flush(); i += 1; continue
        if s == '---':
            flush(); i += 1; continue
        m = re.match(r'(#{1,6})\s+(.*)', s)
        if m:
            flush()
            lvl = len(m.group(1))
            cls = 'sec' if lvl <= 2 else 'sub'
            out.append('<h3 class="%s">%s</h3>' % (cls, inline(m.group(2))))
            i += 1; continue
        m = re.match(r'[-*]\s+(.*)', s)
        if m:
            if listtype and listtype != 'ul': flush()
            listtype = 'ul'; listbuf.append(inline(m.group(1))); i += 1; continue
        m = re.match(r'\d+[.)]\s+(.*)', s)
        if m:
            if listtype and listtype != 'ol': flush()
            listtype = 'ol'; listbuf.append(inline(m.group(1))); i += 1; continue
        flush(); out.append('<p>%s</p>' % inline(s)); i += 1
    flush()
    return '\n'.join(out)


# tag ordering by frequency
from collections import Counter
cnt = Counter(t for r in recipes for t in (r['tags'] or []))
tags = [t for t, _ in cnt.most_common()]
def slug(t): return re.sub(r'[^a-z0-9]+', '-', t.lower()).strip('-')

def rid(r): return 'r' + r['id'].split('-')[0][:8] + r['id'][-4:]

cards, details = [], []
for r in recipes:
    tg = r['tags'] or []
    meta = []
    if r['prep']: meta.append(f"{r['prep']} min")
    if r['serv']: meta.append(f"serves {r['serv']}")
    metatxt = ' · '.join(meta) or (tg[0] if tg else '')
    im = r['imgdata']
    thumb = f'<div class="ph i-{rid(r)}"></div>' if im else '<div class="ph noimg">🍳</div>'
    cards.append(f'''<a class="card" href="#{rid(r)}" data-tags="{' '.join(slug(t) for t in tg)}">
  <div class="ph-wrap">{thumb}</div>
  <div class="card-b"><h2>{esc(r['title'])}</h2><div class="meta">{esc(metatxt)}</div></div>
</a>''')

    hero = f'<div class="heroimg i-{rid(r)}"></div>' if im else ''
    pills = ''.join(f'<span class="pill">{esc(t)}</span>' for t in tg)
    shop = ''
    if r['ing']:
        rows = ''.join(
            f'<div class="shop-row"><span class="shop-k">{esc(l.split(":",1)[0])}</span><span>{esc(l.split(":",1)[1].strip())}</span></div>'
            if ':' in l else f'<div class="shop-row"><span></span><span>{esc(l)}</span></div>'
            for l in r['ing'].split('\n') if l.strip())
        shop = f'<details class="shop"><summary>Shopping list</summary>{rows}</details>'
    src = f'<p class="src">{inline(r["notes"])}</p>' if r['notes'] else ''
    body = render_md(r['md']) if r['md'] else (f'<h3 class="sec">Instructions</h3><p>{inline(r["ins"])}</p>' if r['ins'] else '')
    details.append(f'''<div class="detail" id="{rid(r)}">
 <div class="sheet">
  <a class="close" href="#top" aria-label="Close">&#10005;</a>
  <div class="hero">{hero}</div>
  <div class="dbody">
   <h1>{esc(r['title'])}</h1>
   <div class="meta big">{esc(metatxt)}</div>
   <div class="pills">{pills}</div>
   {body}
   {shop}
   {src}
   <a class="notion" href="{esc(r['url'])}" target="_blank" rel="noopener">Open in Notion &rarr;</a>
  </div>
 </div>
</div>''')

anchors = '<span class="f" id="all"></span>' + ''.join(f'<span class="f" id="t-{slug(t)}"></span>' for t in tags)
chips = '<a class="chip" href="#all">All</a>' + ''.join(f'<a class="chip" href="#t-{slug(t)}">{esc(t)}</a>' for t in tags)
img_css = '\n'.join(f'.i-{rid(r)}{{background-image:url({r["imgdata"]})}}' for r in recipes if r['imgdata'])
filter_css = '\n'.join(
    f'#t-{slug(t)}:target ~ .grid .card:not([data-tags~="{slug(t)}"]){{display:none}}\n'
    f'#t-{slug(t)}:target ~ .bar .chip[href="#t-{slug(t)}"]{{background:var(--ink);color:#fff;border-color:var(--ink)}}'
    for t in tags)

CSS = '''
*{box-sizing:border-box;margin:0;padding:0;-webkit-tap-highlight-color:transparent}
:root{--bg:#faf7f2;--card:#fff;--ink:#1d1a16;--mut:#8a8073;--line:#e8e1d6;--acc:#b8502a}
html{scroll-behavior:smooth}
body{background:var(--bg);color:var(--ink);font:16px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;-webkit-font-smoothing:antialiased;padding-bottom:48px}
a{color:inherit;text-decoration:none}
.wrap{max-width:920px;margin:0 auto;padding:0 14px}
header{padding:26px 0 8px}
header h1{font:600 30px/1.1 ui-serif,Georgia,"Times New Roman",serif;letter-spacing:-.01em}
header p{color:var(--mut);font-size:13px;margin-top:5px}
.bar{display:flex;gap:7px;overflow-x:auto;padding:14px 14px 12px;margin:0 -14px;scrollbar-width:none;position:sticky;top:0;background:linear-gradient(var(--bg) 72%,rgba(250,247,242,0));z-index:5}
.bar::-webkit-scrollbar{display:none}
.chip{flex:0 0 auto;border:1px solid var(--line);background:var(--card);border-radius:999px;padding:7px 13px;font-size:13.5px;font-weight:500;color:#4a443c}
.grid{display:grid;grid-template-columns:1fr 1fr;gap:14px 12px;padding-top:4px}
@media(min-width:620px){.grid{grid-template-columns:repeat(3,1fr);gap:20px 16px}}
.card{display:block;background:var(--card);border:1px solid var(--line);border-radius:14px;overflow:hidden;box-shadow:0 1px 2px rgba(30,25,18,.04)}
.ph-wrap{aspect-ratio:4/3;background:#efe9e0;overflow:hidden}
.ph{width:100%;height:100%;background-size:cover;background-position:center}
.noimg{display:flex;align-items:center;justify-content:center;font-size:30px}
.card-b{padding:10px 11px 12px;min-height:70px}
.card-b h2{font:600 15px/1.28 ui-serif,Georgia,serif;letter-spacing:-.005em;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}
.meta{color:var(--mut);font-size:12px;margin-top:5px}
.meta.big{font-size:13.5px;margin-top:8px}
.f{position:absolute;top:0;left:0;width:0;height:0;overflow:hidden}
.wrap{position:relative}
/* detail */
.detail{position:fixed;inset:0;z-index:20;background:var(--bg);overflow-y:auto;-webkit-overflow-scrolling:touch;opacity:0;pointer-events:none;transform:translateY(14px)}
.detail:target{opacity:1;pointer-events:auto;transform:none;transition:opacity .18s ease,transform .18s ease}
html:has(.detail:target){overflow:hidden}
.sheet{max-width:720px;margin:0 auto;padding-bottom:60px}
.hero{aspect-ratio:16/10;background:#efe9e0}
.heroimg{width:100%;height:100%;background-size:cover;background-position:center}
.close{position:fixed;top:14px;left:14px;width:34px;height:34px;border-radius:50%;background:rgba(255,255,255,.94);display:flex;align-items:center;justify-content:center;font-size:14px;box-shadow:0 2px 8px rgba(0,0,0,.18);z-index:3}
.dbody{padding:20px 16px 0}
.dbody h1{font:600 26px/1.15 ui-serif,Georgia,serif;letter-spacing:-.015em}
.pills{display:flex;flex-wrap:wrap;gap:6px;margin:12px 0 4px}
.pill{font-size:11.5px;letter-spacing:.02em;text-transform:lowercase;background:#f0e9dd;color:#6d6252;border-radius:999px;padding:4px 9px}
.dbody h3.sec{font:600 12px/1 -apple-system,sans-serif;letter-spacing:.09em;text-transform:uppercase;color:var(--acc);margin:26px 0 10px;padding-top:18px;border-top:1px solid var(--line)}
.dbody h3.sub{font:600 15px/1.3 ui-serif,Georgia,serif;margin:18px 0 7px}
.rl{margin:0 0 4px;padding-left:0;list-style:none}
ul.rl li{position:relative;padding:6px 0 6px 18px;border-bottom:1px solid rgba(232,225,214,.7);font-size:15.5px}
ul.rl li:before{content:"";position:absolute;left:3px;top:14px;width:5px;height:5px;border-radius:50%;background:#cbbfae}
ol.rl{counter-reset:s}
ol.rl li{counter-increment:s;position:relative;padding:0 0 16px 34px;font-size:15.5px;line-height:1.55}
ol.rl li:before{content:counter(s);position:absolute;left:0;top:1px;width:23px;height:23px;border-radius:50%;background:var(--acc);color:#fff;font-size:12px;font-weight:600;display:flex;align-items:center;justify-content:center}
.dbody p{margin:8px 0;font-size:15.5px}
.note{display:flex;gap:9px;background:#f3ede3;border-radius:11px;padding:12px 13px;margin:14px 0;font-size:14.5px;line-height:1.45;color:#5c5346}
.note-i{flex:0 0 auto}
.shop{margin:22px 0 0;border:1px solid var(--line);border-radius:12px;background:var(--card);overflow:hidden}
.shop summary{padding:13px 14px;font-size:13px;font-weight:600;letter-spacing:.05em;text-transform:uppercase;color:var(--acc);cursor:pointer}
.shop-row{display:flex;gap:10px;padding:9px 14px;border-top:1px solid var(--line);font-size:14.5px}
.shop-k{flex:0 0 74px;color:var(--mut);font-size:12.5px;text-transform:capitalize;padding-top:2px}
.src{color:var(--mut);font-size:13px;margin-top:20px;font-style:italic}
.notion{display:inline-block;margin-top:22px;font-size:14px;color:var(--acc);font-weight:500}
footer{color:var(--mut);font-size:12px;text-align:center;padding:34px 0 10px}
'''

HTML = f'''<!doctype html>
<html lang="en"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="default">
<meta name="apple-mobile-web-app-title" content="Recipes">
<meta name="theme-color" content="#faf7f2">
<title>Josh's Recipes</title>
<style>{CSS}
{filter_css}
{img_css}
</style>
</head>
<body id="top">
<div class="wrap">
<header><h1>Recipes</h1><p>{len(recipes)} recipes &middot; from your Notion hub</p></header>
{anchors}
<div class="bar">{chips}</div>
<div class="grid">
{''.join(cards)}
</div>
<footer>Mockup &middot; pulled from Notion {datetime.now().strftime('%b %-d, %Y')}</footer>
</div>
{''.join(details)}
</body></html>'''

open(OUT, 'w').write(HTML)
print('wrote %s - %d bytes, %d recipes, %d tags' % (OUT, len(HTML), len(recipes), len(tags)))
