# EDC Las Vegas 2027 Dawn RV Power Monitor

Pushes an alert to your phone when the **Full Price with Power Add-On** option for
**Bring Your Own RV (Dawn 4 Nights)** stops showing SOLD OUT.

It only alerts. It never buys, adds to cart, logs in, joins a queue, or tries to get past
bot protection. If a site blocks it, it logs that, warns you once, and skips that site.

## What it watches

| Target | What counts as a hit |
|---|---|
| `edc_page`: lasvegas.edc.com RV camping page | In the "Bring Your Own RV (Dawn 4 Nights)" section, the "Full Price with Power Add-On" row no longer says SOLD OUT, or has a frontgatetickets.com link. Other sections (Dusk, 11 nights) are ignored. |
| `frontgate`: the Dawn RV Front Gate event page | A ticket row mentioning "power" with a price and no sold out / unavailable marker. |
| `reddit_new`, `reddit_search`: r/electricdaisycarnival feeds | A new post with (power, hookup, 30 amp, 50 amp) AND (rv, dawn, camp). Keywords live in `config.yaml`. |

## Alerts

| Alert | Priority |
|---|---|
| DAWN RV POWER IS ON SALE (re-sent at most every 30 min while it stays on sale) | 5 urgent |
| Reddit: possible power lead | 4 |
| Page layout changed, or a site blocked us (once per incident) | 3 |
| A target failed 3 runs in a row | 3 |
| Dawn RV power back to sold out | 3 |
| Monitor alive (daily, first run after 9am Mountain Time) | 1 |

## Local setup (Windows PowerShell)

Needs Python 3.12 from python.org (tick "Add python.exe to PATH").

```powershell
cd path\to\edc-power-monitor
py -3.12 -m venv .venv
# If activation is blocked, run this once:
#   Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

Run the tests:

```powershell
python -m pytest
```

Dry run against the live sites (prints what would alert, sends nothing, writes no state):

```powershell
python monitor.py --dry-run
```

Dry run against a fixture where Dawn power is on sale (should print a p5 "DAWN RV POWER IS ON SALE"):

```powershell
python monitor.py --dry-run --edc-html tests\fixtures\edc_dawn_power_available.html
```

Send one test notification at each priority (1 through 5) to your phone:

```powershell
$env:NTFY_TOPIC = "your-long-random-topic"
python monitor.py --test-alert
```

`python monitor.py` with no flags is a normal run: it sends real alerts and updates `state.json`.

## GitHub setup

1. Create a **public** repo and push this folder to it. (Public repos get unlimited free
   Actions minutes. A private repo running every 5 minutes would use up the free allowance.)
   Nothing secret is in the code. The ntfy topic is stored as a secret.
2. Add the topic secret: repo **Settings > Secrets and variables > Actions > New repository secret**.
   Name `NTFY_TOPIC`, value your long random topic name (for example 30+ random letters and digits).
3. Optional: to use your own ntfy server, add a repository **variable** (same page, Variables tab)
   named `NTFY_SERVER`, for example `https://ntfy.example.com`. Default is `https://ntfy.sh`.
4. Repo **Settings > Actions > General > Workflow permissions**: choose "Read and write permissions"
   so the workflow can commit `state.json`.
5. **Actions** tab > **monitor** > **Run workflow** to start a manual run. The run summary shows a
   table with each target's status. Today it should show `edc_page | SOLD_OUT` and send no urgent alert.

To send the test notifications from GitHub instead of your PC: **Actions > monitor > Run workflow**,
tick "Only send one test notification at each priority", then **Run workflow**.

The `monitor` workflow runs every 5 minutes (GitHub may delay scheduled runs by a few minutes
when busy). The `keepalive` workflow runs weekly and commits a date to `state.json` if nothing
else has, because GitHub turns off scheduled workflows in public repos after 60 days without
activity.

## Phone setup (Pixel / Android)

1. Install **ntfy** from the Google Play Store.
2. Open ntfy, tap **+**, enter your topic name exactly (same as the `NTFY_TOPIC` secret), keep the
   server as `ntfy.sh`, and subscribe.
3. In ntfy, open **Settings** and turn on **Instant delivery** if offered, so alerts are not delayed by battery saving.
4. Let urgent alerts break through Do Not Disturb:
   - Android **Settings > Notifications > Do Not Disturb > Apps > Add apps > ntfy**.
   - Android **Settings > Apps > ntfy > Notifications**: open the **Max priority** channel and allow
     it to override Do Not Disturb, with sound on.
5. Android **Settings > Apps > ntfy > App battery usage**: choose **Unrestricted**.
6. Run `python monitor.py --test-alert` and check that all five arrive, with priority 5 the loudest.

## Refreshing test fixtures

**Actions > snapshot > Run workflow** fetches each target once and saves the raw HTML and feeds
to the `snapshots` branch. The EDC and Front Gate fixtures in `tests/fixtures/` were built from
those real pages on 2026-10-02.

## Configuration

Everything is in `config.yaml`: URLs, per-target `enabled`, Reddit keywords, re-alert interval,
heartbeat hour and timezone. If a target turns out to be unreadable (for example Front Gate is
rendered by JavaScript), set its `enabled: false`.

## State

`state.json` holds each target's last status, open incidents, failure counts, last alert times,
the 500 most recent Reddit post IDs, and the last heartbeat date. The workflow commits it only
when it changes. To start fresh, replace its contents with `{}` (Reddit will re-seed without
alerting on the next run).
