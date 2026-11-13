# LinkedIn Extension Watch

The list of Chrome extensions that linkedin.com looks for in its visitors' browsers, extracted from LinkedIn's own JavaScript, dated, and checked against the Chrome Web Store.

**Latest check: November 13, 2026.** LinkedIn's file listed **4,934 extensions**. Of the 4,550 we could check, **2,835 (62%)** still exposed the file LinkedIn requests, so only those can actually be found by its file check.

## How LinkedIn checks for extensions

Chrome extensions can make some of their files available to web pages (`web_accessible_resources`). Each extension has a fixed 32-letter ID, so those files have predictable addresses: `chrome-extension://<id>/<file>`. LinkedIn's code holds a list of IDs, each paired with one file, and requests every file. If the file loads, the extension is installed.

In the file we downloaded on November 13, 2026 (`https://static.licdn.com/aero-v1/sc/h/7tp80l6fkzdh33znzfl0w5xuc`, 2.7 MB, SHA-256 `40a49e1d85faf742fbc23d6b1bbbe81ec05aac5f382ce85fd6865206592e20a2`), the code:

- requests each file, all at once or one by one with a delay, optionally when the browser is idle;
- only runs when the user agent contains "Chrome" (Chrome, Edge, Brave, Opera);
- reports the IDs that answered through a tracking event named `AedEvent`;
- also scans the page for any `chrome-extension://` address and reports those IDs in a `SpectroscopyEvent`.

Failed requests appear in the Chrome console as `chrome-extension://invalid/`.

## Data

| File | Content |
|---|---|
| `data/latest.csv` | The most recent check, one row per extension |
| `data/latest.json` | The same, compact, read by the online checker |
| `data/<date>/extensions.csv` | Each check, kept as it was |

Columns of the CSV files:

| Column | Meaning |
|---|---|
| `extension_id` | Chrome extension ID |
| `probed_file` | File LinkedIn's code requests for this extension |
| `on_chrome_web_store` | `yes` if the extension still has a store page on the check date |
| `name`, `store_category`, `users`, `rating`, `rating_count`, `last_updated`, `developer`, `developer_country` | From the Chrome Web Store page on the check date (country only when the publisher shows an address) |
| `manifest_read` | `yes` if we could read the current version's `manifest.json` |
| `file_check_works` | `yes` if that version exposes `probed_file` to linkedin.com (detectable by the file check), `no` if not, `unknown` if no manifest |
| `reason_if_not` | `no_exposed_files`, `file_renamed_or_removed`, `exposed_to_other_sites_only` or `dynamic_url` (Chrome's `use_dynamic_url` option) |
| `runs_on_linkedin`, `runs_on_all_sites`, `requests_cookies` | From the manifest: `1` or `0` |
| `keyword_category` | Our approximate category, from keywords in the store name and description |
| `mentions_linkedin` | `1` if the store name or description mentions LinkedIn |

Caveats: `file_check_works` describes the version on the Chrome Web Store on the check date; an older version installed on a computer may behave differently. LinkedIn's page scan can still spot an extension that adds its own elements to LinkedIn pages, even when the file check fails. Categories are approximate.

## Method and scripts

1. `scripts/extract_linkedin_list.py`: extract the `{id, file}` pairs from LinkedIn's file, with its SHA-256, and compare with the previous check.
2. `scripts/enrich_store.py`: read each extension's Chrome Web Store page.
3. `scripts/fetch_manifests.py`: read each extension's `manifest.json` from Google's update server with range requests (the extensions are never downloaded in full or run).
4. `scripts/build_dataset.py`: merge the three into `data/<date>/extensions.csv`, `data/latest.csv` and `data/latest.json`.

We don't publish LinkedIn's file, the extensions' descriptions or their raw manifests.

## History

| Date | Source | Extensions listed |
|---|---|---|
| 2025-09-02 | Public gist (jeremy-hyde) | 1,854 |
| 2026-02 | Copy of LinkedIn's file (github.com/Ambushfall/detect-linkedin) | 6,153 |
| 2026-04-03 | BleepingComputer's test | 6,236 |
| 2026-04-16 | Copy of the list (github.com/appleflyerv3/LinkedIn-Extensions) | 4,278 |
| 2026-11-13 | This repository | 4,934 |

## License and credit

Data: [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/). Credit "La Growth Machine, LinkedIn Extension Watch" with a link to this repository. Scripts: MIT (see `LICENSE`).

Maintained by Brice Maurin, CEO of [La Growth Machine](https://lagrowthmachine.com), an outreach platform that runs LinkedIn from the cloud. We have a stake in this topic, so we publish the data and the method for anyone to check. Corrections are welcome through issues.
