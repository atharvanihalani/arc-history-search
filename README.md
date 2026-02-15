# Arc History Search

A local web UI for searching your Arc browser history by keyword and date range.

![Flask](https://img.shields.io/badge/Flask-grey?logo=flask) ![Python](https://img.shields.io/badge/Python-3.10+-blue?logo=python)

## Features

- **Keyword search** across page titles and URLs
- **Date range filtering** with start/end date pickers
- **Profile selection** — search Default, Profile 7, or both
- **Paginated results** (50 per page) with SQL-level pagination
- **Refresh button** to re-copy history files while Arc is running
- **Auto-refresh** on startup

## Setup

```bash
python3 -m venv venv
source venv/bin/activate
pip install flask
```

## Usage

```bash
python app.py
```

Then open [http://localhost:8000](http://localhost:8000).

## How it works

Arc (Chromium-based) stores browsing history in SQLite databases that are locked while the browser is running. This tool:

1. Copies the History files to `/tmp/arc_history_search/` to avoid lock conflicts
2. Queries the `urls` and `visits` tables with a JOIN
3. Converts Chrome timestamps (microseconds since Jan 1, 1601) to readable dates
4. Serves results through a Flask API with a minimal frontend

## Run as a background service (macOS)

To have it start automatically on login, create a launchd plist at `~/Library/LaunchAgents/com.arc-history-search.plist`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.arc-history-search</string>
    <key>ProgramArguments</key>
    <array>
        <string>/path/to/venv/bin/python</string>
        <string>/path/to/app.py</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>WorkingDirectory</key>
    <string>/path/to/arc-history-search</string>
</dict>
</plist>
```

Then load it:

```bash
launchctl load ~/Library/LaunchAgents/com.arc-history-search.plist
```

## Tests

```bash
pip install pytest
python -m pytest test_app.py -v
```

## Configuration

Edit the `HISTORY_PATHS` dict in `data.py` to point to your Arc profile locations. The defaults are:

```
~/Library/Application Support/Arc/User Data/Default/History
~/Library/Application Support/Arc/User Data/Profile 7/History
```
