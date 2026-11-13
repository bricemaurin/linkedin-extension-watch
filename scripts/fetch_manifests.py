#!/usr/bin/env python3
"""fetch_manifests.py: read each extension's manifest.json without downloading the whole package.

Source: Google's official extension update server (clients2.google.com), using HTTP range requests: CRX header,
end of the zip (central directory), then the manifest.json entry only. Nothing is executed; only the manifest text is kept.
Usage: python3 scripts/fetch_manifests.py <list CSV with extension_id,probed_file[,status]> <YYYY-MM-DD> [--only id1,id2]
Writes data/manifests-<date>.jsonl (raw manifests, not published) and data/manifest-flags-<date>.csv:
- runs_on_linkedin / runs_on_all_sites: content scripts or host permissions covering linkedin.com, or every site;
- cookies, webRequest, scripting, tabs: requested permissions;
- probed_file_exposed: is the file LinkedIn requests declared in web_accessible_resources;
- exposed_to_linkedin: is that file reachable from a linkedin.com page (MV3 "matches", no "use_dynamic_url"),
  i.e. can LinkedIn's file check actually detect the extension."""
import csv, fnmatch, json, os, re, struct, sys, time, urllib.request, urllib.error, zlib
from concurrent.futures import ThreadPoolExecutor
D = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'data')
UA = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36'
class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k): return None
noredir = urllib.request.build_opener(NoRedirect)
def blob_url(eid):
    u = ('https://clients2.google.com/service/update2/crx?response=redirect&prodversion=131.0.0.0'
         f'&acceptformat=crx2,crx3&x=id%3D{eid}%26uc')
    try:
        noredir.open(urllib.request.Request(u, headers={'User-Agent': UA}), timeout=30); return None
    except urllib.error.HTTPError as e:
        return e.headers.get('Location') if e.code in (301, 302, 303, 307) else None
def rng(url, spec):
    for attempt in range(3):
        try:
            req = urllib.request.Request(url, headers={'User-Agent': UA, 'Range': f'bytes={spec}'})
            with urllib.request.urlopen(req, timeout=30) as r:
                total = int((r.headers.get('Content-Range') or '/0').split('/')[-1] or 0)
                return r.read(), total
        except urllib.error.HTTPError as e:
            if e.code == 429: time.sleep(5 * (attempt + 1)); continue
            if e.code == 416: return b'', 0
            time.sleep(1)
        except Exception: time.sleep(1)
    raise RuntimeError('range failed')
def loads(t):
    t = t.lstrip('﻿')
    try: return json.loads(t)
    except Exception:
        t2 = re.sub(r'/\*.*?\*/', '', t, flags=re.S); t2 = re.sub(r'(?m)^\s*//.*$', '', t2); t2 = re.sub(r',(\s*[}\]])', r'\1', t2)
        return json.loads(t2)
def manifest(eid):
    url = blob_url(eid)
    if not url: return None, 'no_package'
    head, total = rng(url, '0-15')
    if head[:4] != b'Cr24': return None, 'not_crx'
    ver = struct.unpack('<I', head[4:8])[0]
    zip_start = 12 + struct.unpack('<I', head[8:12])[0] if ver == 3 else 16 + struct.unpack('<I', head[8:12])[0] + struct.unpack('<I', head[12:16])[0]
    tail_len = min(total, 65536 + 22)
    tail, _ = rng(url, f'{total - tail_len}-{total - 1}'); tail_start = total - tail_len
    k = tail.rfind(b'PK\x05\x06')
    if k < 0: return None, 'no_eocd'
    cd_size, cd_off = struct.unpack('<II', tail[k + 12:k + 20])
    def cd_bytes(base):
        a = base + cd_off
        return tail[a - tail_start:a - tail_start + cd_size] if a >= tail_start else rng(url, f'{a}-{a + cd_size - 1}')[0]
    for base in (zip_start, 0):
        cd = cd_bytes(base)
        if cd[:4] == b'PK\x01\x02': break
    else: return None, 'bad_cd'
    p = 0
    while p + 46 <= len(cd) and cd[p:p + 4] == b'PK\x01\x02':
        meth, = struct.unpack('<H', cd[p + 10:p + 12]); csize, = struct.unpack('<I', cd[p + 20:p + 24])
        nl, xl, cl = struct.unpack('<HHH', cd[p + 28:p + 34]); lho, = struct.unpack('<I', cd[p + 42:p + 46])
        name = cd[p + 46:p + 46 + nl].decode('utf-8', 'replace')
        if name == 'manifest.json':
            a = base + lho; blob, _ = rng(url, f'{a}-{a + 30 + nl + 2048 + csize}')
            if blob[:4] != b'PK\x03\x04': return None, 'bad_local'
            lnl, lxl = struct.unpack('<HH', blob[26:30]); data = blob[30 + lnl + lxl:30 + lnl + lxl + csize]
            raw = zlib.decompress(data, -15) if meth == 8 else data
            return raw.decode('utf-8', 'replace'), 'ok'
        p += 46 + nl + xl + cl
    return None, 'no_manifest'
def pats(m):
    hp = list(m.get('host_permissions', []) or []) + list(m.get('optional_host_permissions', []) or [])
    perms = [x for x in (m.get('permissions', []) or []) + (m.get('optional_permissions', []) or []) if isinstance(x, str)]
    hp += [x for x in perms if '://' in x or x == '<all_urls>']
    for cs in m.get('content_scripts', []) or []: hp += cs.get('matches', []) or []
    return hp, perms
ALL = re.compile(r'^(<all_urls>|\*://\*/\*|https?://\*/\*|\*://\*/.*|https?://\*/.*)$')
def is_li(p): return 'linkedin.com' in p
def war_check(m, probed):
    war = m.get('web_accessible_resources') or []
    if not war or not probed: return 0, 0
    if m.get('manifest_version', 2) == 2:
        hit = any(fnmatch.fnmatch(probed, x.lstrip('/')) for x in war if isinstance(x, str)); return int(hit), int(hit)
    exposed = to_li = 0
    for e in war:
        if not isinstance(e, dict): continue
        if any(fnmatch.fnmatch(probed, x.lstrip('/')) for x in e.get('resources', []) if isinstance(x, str)):
            exposed = 1
            ms = e.get('matches', []) or []
            if not e.get('use_dynamic_url') and any(ALL.match(x) or is_li(x) for x in ms): to_li = 1
    return exposed, to_li
def main():
    src, date = sys.argv[1], sys.argv[2]
    rows = [r for r in csv.DictReader(open(src, encoding='utf-8-sig')) if r.get('status', 'ok') == 'ok']
    if '--only' in sys.argv: keep = set(sys.argv[sys.argv.index('--only') + 1].split(',')); rows = [r for r in rows if r['extension_id'] in keep]
    out = [None] * len(rows); done = [0]
    jl = open(os.path.join(D, f'manifests-{date}.jsonl'), 'w', encoding='utf-8')
    def one(i):
        eid, probed = rows[i]['extension_id'], rows[i].get('probed_file', '')
        try: txt, st = manifest(eid)
        except Exception as e: txt, st = None, 'error'
        r = {'extension_id': eid, 'probed_file': probed, 'manifest_status': st}
        if txt:
            jl.write(json.dumps({'extension_id': eid, 'manifest': txt}, ensure_ascii=False) + '\n')
            try:
                m = loads(txt); hp, perms = pats(m)
                ex, tl = war_check(m, probed)
                r.update(manifest_version=m.get('manifest_version', ''), version=m.get('version', ''),
                         runs_on_linkedin=int(any(is_li(p) for p in hp)), runs_on_all_sites=int(any(ALL.match(p) for p in hp)),
                         cookies=int('cookies' in perms), webRequest=int('webRequest' in perms), scripting=int('scripting' in perms),
                         tabs=int('tabs' in perms), war_entries=len(m.get('web_accessible_resources') or []),
                         probed_file_exposed=ex, exposed_to_linkedin=tl)
            except Exception: r['manifest_status'] = 'unparsable'
        out[i] = r; done[0] += 1
        if done[0] % 250 == 0: print(f'{done[0]}/{len(rows)}', flush=True)
        time.sleep(0.2)
    with ThreadPoolExecutor(4) as ex: list(ex.map(one, range(len(rows))))
    jl.close()
    cols = ['extension_id', 'probed_file', 'manifest_status', 'manifest_version', 'version', 'runs_on_linkedin', 'runs_on_all_sites',
            'cookies', 'webRequest', 'scripting', 'tabs', 'war_entries', 'probed_file_exposed', 'exposed_to_linkedin']
    dst = os.path.join(D, f'manifest-flags-{date}.csv')
    with open(dst, 'w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction='ignore'); w.writeheader(); w.writerows(out)
    from collections import Counter
    print('done:', dst, Counter(r['manifest_status'] for r in out))
if __name__ == '__main__': main()
