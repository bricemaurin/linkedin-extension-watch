#!/usr/bin/env python3
"""extract_linkedin_list.py: extract the {id, file} list from the LinkedIn JavaScript file that probes Chrome extensions.

The file is served without a .js suffix: https://static.licdn.com/aero-v1/sc/h/<hash> (on 2026-11-13: 7tp80l6fkzdh33znzfl0w5xuc).
To find it: open linkedin.com while signed in, in Chrome, with the console open (thousands of chrome-extension://invalid/ errors
point to it), or look among the static.licdn.com/aero-v1/sc/h/ files the page loads for the one containing "AedEvent".
Usage: python3 scripts/extract_linkedin_list.py <file or URL> <YYYY-MM-DD> [previous list CSV]
Writes a local copy of the file (not published), data/linkedin-probed-extensions-<date>.csv (extension_id, probed_file),
and prints the number of pairs, the SHA-256 of the file and the changes since the previous list."""
import csv, hashlib, os, re, sys, urllib.request
D = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'data')
src, date = sys.argv[1], sys.argv[2]
if src.startswith('http'):
    req = urllib.request.Request(src, headers={'User-Agent': 'Mozilla/5.0 (Macintosh) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0 Safari/537.36'})
    raw = urllib.request.urlopen(req, timeout=60).read()
else:
    raw = open(src, 'rb').read()
name = src.rstrip('/').rsplit('/', 1)[-1].split('?')[0]
rawdir = os.path.join(D, f'raw-linkedin-{date}'); os.makedirs(rawdir, exist_ok=True)
open(os.path.join(rawdir, name if name.endswith('.js') else name + '.js'), 'wb').write(raw)
t = raw.decode('utf-8', 'replace')
pairs = re.findall(r'id:\s*"([a-p]{32})"\s*,\s*file:\s*"([^"]*)"', t)
out = os.path.join(D, f'linkedin-probed-extensions-{date}.csv')
with open(out, 'w', newline='', encoding='utf-8') as f:
    w = csv.writer(f); w.writerow(['extension_id', 'probed_file']); w.writerows(pairs)
print(f'{len(pairs)} pairs ({len({p[0] for p in pairs})} IDs) -> {out}')
print('SHA-256', hashlib.sha256(raw).hexdigest(), '| AedEvent', t.count('AedEvent'), '| SpectroscopyEvent', t.count('SpectroscopyEvent'))
if len(sys.argv) > 3:
    prev = {r['extension_id']: r.get('probed_file', '') for r in csv.DictReader(open(sys.argv[3], encoding='utf-8-sig'))}
    now = dict(pairs)
    print(f'added {len(set(now) - set(prev))}, removed {len(set(prev) - set(now))}, file changed {sum(1 for i in set(now) & set(prev) if now[i] != prev[i])}')
