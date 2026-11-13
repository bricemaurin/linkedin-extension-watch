#!/usr/bin/env python3
"""build_dataset.py: merge one check into the public dataset.

Inputs (all from the same day):
  --list       CSV with extension_id, probed_file (output of extract_linkedin_list.py)
  --store      CSV of Chrome Web Store details (output of enrich_store.py)
  --flags      CSV of manifest flags (output of fetch_manifests.py)
  --manifests  JSONL of raw manifests (output of fetch_manifests.py), used to explain why a file check fails
  --date       YYYY-MM-DD of the check
  --source     URL of the LinkedIn file the list was extracted from
  --sha256     SHA-256 of that file
Outputs: data/<date>/extensions.csv, data/latest.csv, data/latest.json (compact, read by the checker tool).
Vendor descriptions and raw manifests are not published."""
import argparse, csv, datetime, fnmatch, json, os, re
ap = argparse.ArgumentParser()
for a in ['list', 'store', 'flags', 'manifests', 'date', 'source', 'sha256']: ap.add_argument('--' + a, required=True)
A = ap.parse_args()
ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
CATS = [
    ('Contact data & email/phone finders', r'email finder|find (an |any |anyone.s |b2b |work )?(emails?|phone|contacts?)|phone number|contact (info|data|details|finder)|b2b (data|contact)|email (lookup|extractor|address)|enrich|verify emails?|email verif|lead data|mobile number|direct dial|rocketreach|zoominfo|signalhire|seamless\.ai|contactout|kaspr|lusha|cognism|hunter\.io|snov|skrapp|wiza|apollo'),
    ('LinkedIn outreach & prospecting', r'outreach|prospect|auto[- ]?connect|connection requests?|sales navigator|lead gen|(mass|bulk) (message|messaging|invite|invitation|connect|dm)|linkedin (automation|automator|bot|autopilot|messag)|automat\w* (linkedin|your linkedin)|auto[- ]?(invite|endorse|visit|withdraw)|engagement pod|social selling|dux-soup|lemlist|waalaxy|phantombuster|expandi|octopus crm|linked helper'),
    ('Scrapers & data export', r'scrap|extract (data|emails?|profiles?|leads|contacts)|data extract|export (profiles?|contacts|leads|connections|data|to|your)|crawler|data miner|to (csv|excel|google sheets)'),
    ('CRM & sales connectors', r'\bcrm\b|hubspot|salesforce|pipedrive|zoho|close\.com|attio|bitrix|freshsales|save (leads|profiles?|contacts?) to'),
    ('Job search & recruiting', r'\bjobs?\b|job search|recruit|resume|\bcv\b|cover letter|applicant|candidate|\bats\b|hiring|career|sourcing|talent acquisition'),
    ('Writing & AI assistants', r'grammar|writing assistant|ai writ|ghostwrit|ai comment|comment (generator|assistant|writer)|linkedin comment|post (generator|writer|creator)|linkedin posts?|carousel|caption|rewrite|paraphras|chatgpt|\bgpt|\bai (assistant|sidebar|chat|agent)|chat with|translat'),
]
ALL = re.compile(r'^(<all_urls>|\*://\*/\*|https?://\*/\*|\*://\*/.*|https?://\*/.*)$')
lst = [r for r in csv.DictReader(open(A.list, encoding='utf-8-sig'))]
store = {r['extension_id']: r for r in csv.DictReader(open(A.store, encoding='utf-8-sig'))}
flags = {r['extension_id']: r for r in csv.DictReader(open(A.flags, encoding='utf-8-sig'))}
man = {}
for l in open(A.manifests, encoding='utf-8'):
    d = json.loads(l); man[d['extension_id']] = d['manifest']
def iso(s):
    try: return datetime.datetime.strptime(s, '%B %d, %Y').date().isoformat()
    except Exception: return ''
def reason(eid, probed):
    try: m = json.loads(man[eid].lstrip('﻿'))
    except Exception: return 'manifest_unreadable'
    war = m.get('web_accessible_resources') or []
    if not war: return 'no_exposed_files'
    ents = [e for e in war if isinstance(e, dict) and any(fnmatch.fnmatch(probed, x.lstrip('/')) for x in e.get('resources', []) if isinstance(x, str))]
    if not ents: return 'file_renamed_or_removed'
    if all(e.get('use_dynamic_url') for e in ents): return 'dynamic_url'
    return 'exposed_to_other_sites_only'
COLS = ['extension_id', 'probed_file', 'on_chrome_web_store', 'name', 'store_category', 'users', 'rating', 'rating_count', 'last_updated',
        'developer', 'developer_country', 'manifest_read', 'file_check_works', 'reason_if_not', 'runs_on_linkedin', 'runs_on_all_sites',
        'requests_cookies', 'keyword_category', 'mentions_linkedin']
rows = []
for r in lst:
    eid, probed = r['extension_id'], r['probed_file']; s = store.get(eid, {}); f = flags.get(eid, {})
    on = s.get('status') == 'ok'; mok = f.get('manifest_status') == 'ok'
    text = (s.get('name', '') + ' ' + s.get('description', '')).lower()
    works = ('yes' if f.get('exposed_to_linkedin') == '1' else 'no') if mok else 'unknown'
    rows.append({'extension_id': eid, 'probed_file': probed, 'on_chrome_web_store': 'yes' if on else 'no', 'name': s.get('name', ''),
                 'store_category': s.get('category', ''), 'users': s.get('users', ''), 'rating': s.get('rating', ''), 'rating_count': s.get('rating_count', ''),
                 'last_updated': iso(s.get('updated', '')), 'developer': s.get('developer', ''), 'developer_country': s.get('developer_country', ''),
                 'manifest_read': 'yes' if mok else 'no', 'file_check_works': works, 'reason_if_not': reason(eid, probed) if works == 'no' else '',
                 'runs_on_linkedin': f.get('runs_on_linkedin', ''), 'runs_on_all_sites': f.get('runs_on_all_sites', ''), 'requests_cookies': f.get('cookies', ''),
                 'keyword_category': (next((c for c, p in CATS if re.search(p, text)), 'Other') if on else 'Not on the store'),
                 'mentions_linkedin': '1' if 'linkedin' in text else '0'})
os.makedirs(os.path.join(ROOT, 'data', A.date), exist_ok=True)
for path in [os.path.join(ROOT, 'data', A.date, 'extensions.csv'), os.path.join(ROOT, 'data', 'latest.csv')]:
    with open(path, 'w', newline='', encoding='utf-8') as fh:
        w = csv.DictWriter(fh, fieldnames=COLS); w.writeheader(); w.writerows(rows)
compact = {'checked_on': A.date, 'source_file': A.source, 'source_sha256': A.sha256, 'count': len(rows),
           'fields': ['id', 'file', 'name', 'users', 'file_check_works', 'reason_if_not', 'on_store'],
           'extensions': [[r['extension_id'], r['probed_file'], r['name'], int(r['users'] or 0), r['file_check_works'], r['reason_if_not'], r['on_chrome_web_store'] == 'yes'] for r in rows]}
json.dump(compact, open(os.path.join(ROOT, 'data', 'latest.json'), 'w', encoding='utf-8'), ensure_ascii=False, separators=(',', ':'))
from collections import Counter
print(len(rows), 'rows;', Counter(r['file_check_works'] for r in rows), Counter(r['reason_if_not'] for r in rows if r['reason_if_not']))
