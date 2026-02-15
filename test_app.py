"""Tests for Arc History Search."""

import json
import os
import sqlite3
import tempfile
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

import pytest

from data import (
    CHROME_EPOCH_OFFSET,
    chrome_time_to_datetime,
    datetime_to_chrome_time,
    search_history,
    get_history_db_path,
    TEMP_DIR,
)


class TestChromeTimeConversion:
    """Tests for Chrome timestamp conversion functions."""

    def test_chrome_time_to_datetime_known_value(self):
        # Test with a known local datetime
        # Create a datetime, convert to Chrome time, then back
        test_dt = datetime(2020, 1, 1, 12, 0, 0)  # Noon on Jan 1, 2020
        chrome_time = datetime_to_chrome_time(test_dt)
        result = chrome_time_to_datetime(chrome_time)
        assert result.year == 2020
        assert result.month == 1
        assert result.day == 1
        assert result.hour == 12

    def test_datetime_to_chrome_time_known_value(self):
        dt = datetime(2020, 1, 1, 0, 0, 0)
        chrome_time = datetime_to_chrome_time(dt)
        # Convert back to verify
        result = chrome_time_to_datetime(chrome_time)
        assert result.year == 2020
        assert result.month == 1
        assert result.day == 1

    def test_roundtrip_conversion(self):
        original = datetime(2023, 6, 15, 14, 30, 45)
        chrome_time = datetime_to_chrome_time(original)
        result = chrome_time_to_datetime(chrome_time)
        assert result.year == original.year
        assert result.month == original.month
        assert result.day == original.day
        assert result.hour == original.hour
        assert result.minute == original.minute
        assert result.second == original.second


class TestSearchHistory:
    """Tests for the search_history function using a mock database."""

    @pytest.fixture
    def mock_history_db(self):
        """Create a temporary SQLite database with test data."""
        TEMP_DIR.mkdir(parents=True, exist_ok=True)
        db_path = TEMP_DIR / "test_profile_History"

        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # Create tables matching Chrome's schema
        cursor.execute("""
            CREATE TABLE urls (
                id INTEGER PRIMARY KEY,
                url TEXT,
                title TEXT
            )
        """)
        cursor.execute("""
            CREATE TABLE visits (
                id INTEGER PRIMARY KEY,
                url INTEGER,
                visit_time INTEGER
            )
        """)

        # Insert test data
        test_urls = [
            (1, "https://github.com/anthropics/claude", "Anthropic Claude"),
            (2, "https://google.com/search?q=python", "Python - Google Search"),
            (3, "https://stackoverflow.com/questions/123", "How to code - Stack Overflow"),
            (4, "https://example.com/page", "Example Page"),
        ]
        cursor.executemany("INSERT INTO urls VALUES (?, ?, ?)", test_urls)

        # Create visits with different times
        # Using dates: Jan 1 2024, Jan 15 2024, Feb 1 2024, Feb 15 2024
        test_visits = [
            (1, 1, datetime_to_chrome_time(datetime(2024, 1, 1, 10, 0, 0))),
            (2, 2, datetime_to_chrome_time(datetime(2024, 1, 15, 12, 0, 0))),
            (3, 3, datetime_to_chrome_time(datetime(2024, 2, 1, 14, 0, 0))),
            (4, 4, datetime_to_chrome_time(datetime(2024, 2, 15, 16, 0, 0))),
        ]
        cursor.executemany("INSERT INTO visits VALUES (?, ?, ?)", test_visits)

        conn.commit()
        conn.close()

        yield db_path

        # Cleanup
        if db_path.exists():
            db_path.unlink()

    def test_search_all_results(self, mock_history_db):
        """Test searching without any filters."""
        # Rename the test db to match expected profile name
        test_profile_path = TEMP_DIR / "testprofile_History"
        if mock_history_db != test_profile_path:
            mock_history_db.rename(test_profile_path)

        results, total = search_history(profiles=["testprofile"])
        assert total == 4
        assert len(results) == 4

        # Clean up
        test_profile_path.unlink()

    def test_search_by_keyword(self, mock_history_db):
        """Test keyword search in URL and title."""
        test_profile_path = TEMP_DIR / "testprofile_History"
        if mock_history_db != test_profile_path:
            mock_history_db.rename(test_profile_path)

        # Search for "github"
        results, total = search_history(keyword="github", profiles=["testprofile"])
        assert total == 1
        assert "github" in results[0]["url"].lower()

        # Search for "python" (in title)
        results, total = search_history(keyword="python", profiles=["testprofile"])
        assert total == 1
        assert "python" in results[0]["title"].lower()

        # Clean up
        test_profile_path.unlink()

    def test_search_by_date_range(self, mock_history_db):
        """Test filtering by date range."""
        test_profile_path = TEMP_DIR / "testprofile_History"
        if mock_history_db != test_profile_path:
            mock_history_db.rename(test_profile_path)

        # Search January only
        results, total = search_history(
            start_date=datetime(2024, 1, 1),
            end_date=datetime(2024, 1, 31),
            profiles=["testprofile"],
        )
        assert total == 2

        # Search February only
        results, total = search_history(
            start_date=datetime(2024, 2, 1),
            end_date=datetime(2024, 2, 28),
            profiles=["testprofile"],
        )
        assert total == 2

        # Clean up
        test_profile_path.unlink()

    def test_search_combined_filters(self, mock_history_db):
        """Test combining keyword and date filters."""
        test_profile_path = TEMP_DIR / "testprofile_History"
        if mock_history_db != test_profile_path:
            mock_history_db.rename(test_profile_path)

        # Search for "stack" in February
        results, total = search_history(
            keyword="stack",
            start_date=datetime(2024, 2, 1),
            end_date=datetime(2024, 2, 28),
            profiles=["testprofile"],
        )
        assert total == 1
        assert "stackoverflow" in results[0]["url"]

        # Search for "stack" in January (should find nothing)
        results, total = search_history(
            keyword="stack",
            start_date=datetime(2024, 1, 1),
            end_date=datetime(2024, 1, 31),
            profiles=["testprofile"],
        )
        assert total == 0

        # Clean up
        test_profile_path.unlink()

    def test_pagination(self, mock_history_db):
        """Test pagination of results."""
        test_profile_path = TEMP_DIR / "testprofile_History"
        if mock_history_db != test_profile_path:
            mock_history_db.rename(test_profile_path)

        # Get first page with 2 results per page
        results, total = search_history(profiles=["testprofile"], page=1, per_page=2)
        assert total == 4
        assert len(results) == 2

        # Get second page
        results2, total2 = search_history(profiles=["testprofile"], page=2, per_page=2)
        assert total2 == 4
        assert len(results2) == 2

        # Results should be different
        assert results[0]["url"] != results2[0]["url"]

        # Clean up
        test_profile_path.unlink()

    def test_results_sorted_by_time_descending(self, mock_history_db):
        """Test that results are sorted by visit time descending."""
        test_profile_path = TEMP_DIR / "testprofile_History"
        if mock_history_db != test_profile_path:
            mock_history_db.rename(test_profile_path)

        results, _ = search_history(profiles=["testprofile"])

        # Most recent should be first (Feb 15)
        assert "example.com" in results[0]["url"]
        # Oldest should be last (Jan 1)
        assert "github.com" in results[-1]["url"]

        # Clean up
        test_profile_path.unlink()


class TestFlaskApp:
    """Tests for the Flask API endpoints."""

    @pytest.fixture
    def client(self):
        """Create a test client."""
        from app import app
        app.config["TESTING"] = True
        with app.test_client() as client:
            yield client

    @pytest.fixture
    def mock_search_results(self):
        """Mock search results for API tests."""
        return [
            {
                "url": "https://example.com",
                "title": "Example",
                "visit_time": "2024-01-15T12:00:00",
                "visit_time_display": "2024-01-15 12:00:00",
                "profile": "default",
            }
        ]

    def test_index_route(self, client):
        """Test that the index page loads."""
        response = client.get("/")
        assert response.status_code == 200
        assert b"Arc History Search" in response.data

    def test_search_endpoint_returns_json(self, client, mock_search_results):
        """Test the search endpoint returns JSON."""
        with patch("app.search_history") as mock_search:
            mock_search.return_value = (mock_search_results, 1)
            response = client.get("/search")
            assert response.status_code == 200
            data = json.loads(response.data)
            assert "results" in data
            assert "total_count" in data
            assert "page" in data
            assert "total_pages" in data

    def test_search_with_parameters(self, client, mock_search_results):
        """Test search endpoint with query parameters."""
        with patch("app.search_history") as mock_search:
            mock_search.return_value = (mock_search_results, 1)
            response = client.get(
                "/search?q=test&start=2024-01-01&end=2024-01-31&profile=default&page=1"
            )
            assert response.status_code == 200

            # Verify search_history was called with correct parameters
            mock_search.assert_called_once()
            call_kwargs = mock_search.call_args[1]
            assert call_kwargs["keyword"] == "test"
            assert call_kwargs["profiles"] == ["default"]
            assert call_kwargs["page"] == 1

    def test_search_profile_both(self, client, mock_search_results):
        """Test search with both profiles selected."""
        with patch("app.search_history") as mock_search:
            mock_search.return_value = (mock_search_results, 1)
            response = client.get("/search?profile=both")
            assert response.status_code == 200

            call_kwargs = mock_search.call_args[1]
            assert call_kwargs["profiles"] == ["default", "profile7"]

    def test_refresh_endpoint(self, client):
        """Test the refresh endpoint."""
        with patch("app.copy_history_files") as mock_copy:
            mock_copy.return_value = {"default": Path("/tmp/test"), "profile7": None}
            response = client.post("/refresh")
            assert response.status_code == 200
            data = json.loads(response.data)
            assert data["success"] is True
            assert "default" in data["profiles_available"]


class TestEdgeCases:
    """Tests for edge cases and error handling."""

    def test_empty_keyword_is_treated_as_none(self):
        """Test that empty string keyword is treated as no keyword filter."""
        # This tests the Flask app's handling of empty query param
        from app import app
        app.config["TESTING"] = True
        with app.test_client() as client:
            with patch("app.search_history") as mock_search:
                mock_search.return_value = ([], 0)
                client.get("/search?q=")
                call_kwargs = mock_search.call_args[1]
                assert call_kwargs["keyword"] is None

    def test_invalid_date_is_ignored(self):
        """Test that invalid date strings are handled gracefully."""
        from app import app
        app.config["TESTING"] = True
        with app.test_client() as client:
            with patch("app.search_history") as mock_search:
                mock_search.return_value = ([], 0)
                response = client.get("/search?start=invalid-date")
                assert response.status_code == 200
                call_kwargs = mock_search.call_args[1]
                assert call_kwargs["start_date"] is None

    def test_missing_profile_db_handled(self):
        """Test that missing profile database doesn't crash search."""
        results, total = search_history(profiles=["nonexistent_profile"])
        assert total == 0
        assert results == []
