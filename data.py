"""Data layer for Arc browser history queries."""

import os
import shutil
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Optional

# Chrome/Chromium epoch starts at Jan 1, 1601
# Unix epoch starts at Jan 1, 1970
# Difference in seconds: 11644473600
CHROME_EPOCH_OFFSET = 11644473600

HISTORY_PATHS = {
    "default": Path.home() / "Library/Application Support/Arc/User Data/Default/History",
    "profile7": Path.home() / "Library/Application Support/Arc/User Data/Profile 7/History",
}

TEMP_DIR = Path("/tmp/arc_history_search")


def chrome_time_to_datetime(chrome_time: int) -> datetime:
    """Convert Chrome timestamp (microseconds since 1601) to datetime."""
    unix_timestamp = (chrome_time / 1_000_000) - CHROME_EPOCH_OFFSET
    return datetime.fromtimestamp(unix_timestamp)


def datetime_to_chrome_time(dt: datetime) -> int:
    """Convert datetime to Chrome timestamp."""
    unix_timestamp = dt.timestamp()
    return int((unix_timestamp + CHROME_EPOCH_OFFSET) * 1_000_000)


def copy_history_files() -> dict[str, Optional[Path]]:
    """Copy history files to temp location. Returns paths to copied files."""
    TEMP_DIR.mkdir(parents=True, exist_ok=True)

    copied = {}
    for profile, source_path in HISTORY_PATHS.items():
        dest_path = TEMP_DIR / f"{profile}_History"
        if source_path.exists():
            try:
                shutil.copy2(source_path, dest_path)
                copied[profile] = dest_path
            except Exception as e:
                print(f"Warning: Could not copy {profile} history: {e}")
                copied[profile] = None
        else:
            copied[profile] = None

    return copied


def get_history_db_path(profile: str) -> Optional[Path]:
    """Get path to copied history database for a profile."""
    path = TEMP_DIR / f"{profile}_History"
    return path if path.exists() else None


def _build_where_clause(
    keyword: Optional[str] = None,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
) -> tuple[str, list]:
    """Build WHERE clause and params from filters."""
    clauses = []
    params = []

    if keyword:
        clauses.append("(urls.url LIKE ? OR urls.title LIKE ?)")
        keyword_pattern = f"%{keyword}%"
        params.extend([keyword_pattern, keyword_pattern])

    if start_date:
        clauses.append("visits.visit_time >= ?")
        params.append(datetime_to_chrome_time(start_date))

    if end_date:
        end_of_day = datetime(end_date.year, end_date.month, end_date.day, 23, 59, 59)
        clauses.append("visits.visit_time <= ?")
        params.append(datetime_to_chrome_time(end_of_day))

    where = " AND ".join(clauses) if clauses else "1=1"
    return where, params


def _query_profile_count(db_path: Path, where: str, params: list) -> int:
    """Get total count for a profile with given filters."""
    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        cursor = conn.cursor()
        cursor.execute(
            f"SELECT COUNT(*) FROM visits JOIN urls ON visits.url = urls.id WHERE {where}",
            params,
        )
        count = cursor.fetchone()[0]
        conn.close()
        return count
    except Exception as e:
        print(f"Error counting: {e}")
        return 0


def _query_profile_rows(
    db_path: Path, where: str, params: list, limit: int, offset: int, profile: str
) -> list[dict]:
    """Get paginated rows from a profile."""
    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute(
            f"""
            SELECT urls.url, urls.title, visits.visit_time
            FROM visits
            JOIN urls ON visits.url = urls.id
            WHERE {where}
            ORDER BY visits.visit_time DESC
            LIMIT ? OFFSET ?
            """,
            params + [limit, offset],
        )
        results = []
        for row in cursor.fetchall():
            visit_time = chrome_time_to_datetime(row["visit_time"])
            results.append({
                "url": row["url"],
                "title": row["title"] or "(No title)",
                "visit_time": visit_time.isoformat(),
                "visit_time_display": visit_time.strftime("%Y-%m-%d %H:%M:%S"),
                "profile": profile,
            })
        conn.close()
        return results
    except Exception as e:
        print(f"Error querying {profile}: {e}")
        return []


def search_history(
    keyword: Optional[str] = None,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    profiles: Optional[list[str]] = None,
    page: int = 1,
    per_page: int = 50,
) -> tuple[list[dict], int]:
    """
    Search history with filters. Uses SQL-level pagination.

    Returns:
        Tuple of (results list, total count)
    """
    if profiles is None:
        profiles = ["default", "profile7"]

    where, params = _build_where_clause(keyword, start_date, end_date)

    # Filter to profiles that have a database
    active_profiles = []
    for profile in profiles:
        db_path = get_history_db_path(profile)
        if db_path is not None:
            active_profiles.append((profile, db_path))

    if not active_profiles:
        return [], 0

    # Single profile: pure SQL pagination
    if len(active_profiles) == 1:
        profile, db_path = active_profiles[0]
        total_count = _query_profile_count(db_path, where, params)
        offset = (page - 1) * per_page
        results = _query_profile_rows(db_path, where, params, per_page, offset, profile)
        return results, total_count

    # Multiple profiles: get counts, fetch enough from each to fill the page, merge
    total_count = sum(
        _query_profile_count(db_path, where, params)
        for _, db_path in active_profiles
    )

    # Fetch (page * per_page) from each profile to ensure correct merge ordering
    fetch_limit = page * per_page
    all_results = []
    for profile, db_path in active_profiles:
        rows = _query_profile_rows(db_path, where, params, fetch_limit, 0, profile)
        all_results.extend(rows)

    # Sort merged results and take the right page
    all_results.sort(key=lambda x: x["visit_time"], reverse=True)
    start_idx = (page - 1) * per_page
    end_idx = start_idx + per_page
    paginated_results = all_results[start_idx:end_idx]

    return paginated_results, total_count
