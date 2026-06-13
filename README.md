# Quick project to showcase correlation of Life Expectancy and Unemployment organised by county and population.

## WHOOP band connector

`whoop_connector.py` pulls your personal sleep, recovery, strain, and workout
data from the WHOOP v2 API into CSV files (`whoop_data/`) so you can analyse it
with pandas / Claude.

### Setup (one time)

1. Create an app at the [WHOOP Developer Dashboard](https://developer-dashboard.whoop.com)
   (log in with your normal WHOOP account).
2. In the app settings, add this Redirect URI exactly: `http://localhost:8765/callback`
3. Enable all read scopes (recovery, cycles, sleep, workout, profile, body
   measurement) and **offline** (needed so you don't have to log in every time).
4. Install dependencies: `pip install requests pandas matplotlib`
5. Set your credentials (from the dashboard) as environment variables:

   ```bash
   export WHOOP_CLIENT_ID="..."
   export WHOOP_CLIENT_SECRET="..."
   ```

   On Windows PowerShell: `$env:WHOOP_CLIENT_ID="..."` etc.

### Usage

```bash
python whoop_connector.py             # last 90 days
python whoop_connector.py --days 365  # last year
python whoop_connector.py --all       # full history
```

The first run opens your browser to authorize the app; after that, tokens are
cached in `.whoop_tokens.json` and refreshed automatically.

Output files in `whoop_data/` (gitignored, since it's personal health data):

| File | Contents |
|---|---|
| `sleep.csv` | Every sleep: stages, efficiency, performance %, respiratory rate |
| `recovery.csv` | Daily recovery score, HRV, resting heart rate, SpO2, skin temp |
| `cycles.csv` | Daily physiological cycles: strain, calories, avg/max heart rate |
| `workouts.csv` | Workouts: sport, strain, heart-rate zones, distance, calories |
| `profile.json` | Your profile and body measurements |

`whoop_analysis.py` is a starter script that joins sleep and recovery and plots
time-in-bed vs. recovery score. To analyse with Claude, just run the connector
and ask Claude to read the CSVs in `whoop_data/`.
