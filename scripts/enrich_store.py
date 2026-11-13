#!/usr/bin/env python3
"""enrich_store.py: read the Chrome Web Store page of each extension in a list.

Usage: python3 scripts/enrich_store.py <list CSV with extension_id[,probed_file]> <YYYY-MM-DD> [--only id1,id2]
Writes data/cws-details-<date>.csv: name, description, category, users, rating, number of ratings, Featured badge, version,
last update, size, languages, publisher (name, country, website), trader status, declared data handling.
The publisher's full address and email are not kept. 6 parallel requests with a 150 ms pause."""
import csv, gzip, html, os, re, sys, time, urllib.request, urllib.error
from concurrent.futures import ThreadPoolExecutor
D = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'data')
UA = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0 Safari/537.36'
DATA_TYPES = ['Personally identifiable information', 'Health information', 'Financial and payment information',
              'Authentication information', 'Personal communications', 'Location', 'Web history', 'User activity', 'Website content']
def get(url):
    for attempt in range(4):
        try:
            req = urllib.request.Request(url, headers={'User-Agent': UA, 'Accept-Encoding': 'gzip', 'Accept-Language': 'en'})
            with urllib.request.urlopen(req, timeout=30) as r:
                b = r.read()
                if r.headers.get('Content-Encoding') == 'gzip': b = gzip.decompress(b)
                return 200, b.decode('utf-8', 'replace')
        except urllib.error.HTTPError as e:
            if e.code == 404: return 404, ''
            if e.code == 429: time.sleep(5 * (attempt + 1)); continue
            time.sleep(1)
        except Exception:
            time.sleep(1)
    return 0, ''
def T(x): return re.sub(r'\s+', ' ', html.unescape(re.sub(r'<[^>]+>', ' ', x or ''))).strip()
def label(s, name):
    m = re.search(r'<div class="QDHp8e">' + re.escape(name) + r'</div>(.*?)</li>', s, re.S)
    return T(m.group(1)) if m else ''
def parse(eid, s):
    r = {'extension_id': eid}
    m = re.search(r'<meta property="og:title" content="([^"]*)"', s)
    name = html.unescape(m.group(1)).replace(' - Chrome Web Store', '').strip() if m else ''
    if not name or name.lower() == 'chrome web store': return dict(r, status='not_found')
    r['name'] = name
    m = re.search(r'<meta property="og:description" content="([^"]*)"', s); r['description'] = T(m.group(1)) if m else ''
    m = re.search(r'href="\./category/extensions/([^"]+)"[^>]*>([^<]*)</a>([\d,]+)\+?\s*users?', s)
    if m: r['category_path'], r['category'], r['users'] = m.group(1), html.unescape(m.group(2)), m.group(3).replace(',', '')
    else:
        m = re.search(r'href="\./category/extensions/([^"]+)"[^>]*>([^<]*)</a>', s)
        if m: r['category_path'], r['category'] = m.group(1), html.unescape(m.group(2))
        m = re.search(r'>([\d,]+)\+?\s*users?<', s); r['users'] = m.group(1).replace(',', '') if m else ''
    head = s[:s.find('<h2 class="p9xg1">Details</h2>')] if '<h2 class="p9xg1">Details</h2>' in s else s[:len(s) // 2]
    m = re.search(r'aria-label="Average rating ([\d.]+) out of 5', head); r['rating'] = m.group(1) if m else ''
    m = re.search(r'>([\d.,]+[KM]?) ratings?<', head)
    if m:
        v = m.group(1).replace(',', ''); r['rating_count'] = str(round(float(v[:-1]) * (1e3 if v[-1] == 'K' else 1e6))) if v[-1] in 'KM' else v
    r['featured'] = int('>Featured</span>' in head)
    r['established_publisher'] = int('>Established publisher</span>' in head)
    for k in ['Version', 'Updated', 'Size']: r[k.lower()] = label(s, k)
    r['languages'] = label(s, 'Languages')
    m = re.search(r'<div class="QDHp8e">Developer</div>(.*?)</li>', s, re.S)
    if m:
        blk = m.group(1)
        mm = re.search(r'<div class="mdSapd">(.*?)</div>', blk, re.S)
        parts = [T(p) for p in re.split(r'<br\s*/?>', mm.group(1))] if mm else []
        r['developer'] = parts[0] if parts else ''
        last = parts[-1] if len(parts) > 1 else ''
        mc = re.search(r'\b([A-Z]{2})$', last); r['developer_country'] = mc.group(1) if mc else ''
        mw = re.search(r'<a href="(https?://[^"]+)" rel="ugc nofollow"', blk); r['developer_website'] = mw.group(1) if mw else ''
    r['trader'] = 'trader' if '<div class="QDHp8e">Trader</div>' in s else ('non-trader' if '<div class="QDHp8e">Non-trader</div>' in s else 'undeclared')
    i = s.find('handles the following:')
    if i >= 0:
        j = s.find('This developer declares', i); seg = T(s[i:j if j > 0 else i + 20000])
        r['data_handled'] = '; '.join(t for t in DATA_TYPES if t in seg)
    elif 'will not collect or use your data' in s: r['data_handled'] = 'none declared'
    else: r['data_handled'] = ''
    r['status'] = 'ok'
    return r
COLS = ['extension_id', 'probed_file', 'status', 'name', 'description', 'category', 'category_path', 'users', 'rating', 'rating_count',
        'featured', 'established_publisher', 'version', 'updated', 'size', 'languages', 'developer', 'developer_country',
        'developer_website', 'trader', 'data_handled', 'chrome_web_store_url']
def main():
    src, date = sys.argv[1], sys.argv[2]
    rows = [r for r in csv.DictReader(open(src, encoding='utf-8-sig'))]
    if '--only' in sys.argv: keep = set(sys.argv[sys.argv.index('--only') + 1].split(',')); rows = [r for r in rows if r['extension_id'] in keep]
    out = [None] * len(rows); done = [0]
    def one(i):
        eid = rows[i]['extension_id']; code, s = get(f'https://chromewebstore.google.com/detail/{eid}?hl=en')
        r = parse(eid, s) if code == 200 else {'extension_id': eid, 'status': 'not_found' if code == 404 else 'error'}
        r['probed_file'] = rows[i].get('probed_file', ''); r['chrome_web_store_url'] = f'https://chromewebstore.google.com/detail/{eid}'
        out[i] = r; done[0] += 1
        if done[0] % 250 == 0: print(f'{done[0]}/{len(rows)}', flush=True)
        time.sleep(0.15)
    with ThreadPoolExecutor(6) as ex: list(ex.map(one, range(len(rows))))
    dst = os.path.join(D, f'cws-details-{date}.csv')
    with open(dst, 'w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=COLS, extrasaction='ignore'); w.writeheader(); w.writerows(out)
    from collections import Counter
    print('done:', dst, Counter(r['status'] for r in out))
if __name__ == '__main__': main()
