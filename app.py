"""Flask server for Arc browser history search."""

from datetime import date, datetime
from flask import Flask, render_template, request, jsonify
from data import copy_history_files, search_history

app = Flask(__name__)

PER_PAGE = 50


@app.route("/")
def index():
    """Serve the main UI."""
    return render_template("index.html")


@app.route("/search")
def search():
    """Search history with filters."""
    keyword = request.args.get("q", "").strip() or None
    start_date_str = request.args.get("start", "").strip()
    end_date_str = request.args.get("end", "").strip()
    profile = request.args.get("profile", "both")
    page = int(request.args.get("page", 1))

    # Parse dates
    start_date = None
    end_date = None

    if start_date_str:
        try:
            d = date.fromisoformat(start_date_str)
            start_date = datetime(d.year, d.month, d.day)
        except ValueError:
            pass

    if end_date_str:
        try:
            d = date.fromisoformat(end_date_str)
            end_date = datetime(d.year, d.month, d.day)
        except ValueError:
            pass

    # Determine profiles to search
    if profile == "default":
        profiles = ["default"]
    elif profile == "profile7":
        profiles = ["profile7"]
    else:
        profiles = ["default", "profile7"]

    results, total_count = search_history(
        keyword=keyword,
        start_date=start_date,
        end_date=end_date,
        profiles=profiles,
        page=page,
        per_page=PER_PAGE,
    )

    total_pages = (total_count + PER_PAGE - 1) // PER_PAGE

    return jsonify({
        "results": results,
        "total_count": total_count,
        "page": page,
        "per_page": PER_PAGE,
        "total_pages": total_pages,
    })


@app.route("/refresh", methods=["POST"])
def refresh():
    """Re-copy history files from Arc."""
    copied = copy_history_files()
    available = [profile for profile, path in copied.items() if path is not None]
    return jsonify({
        "success": True,
        "message": f"Refreshed history for: {', '.join(available) if available else 'none'}",
        "profiles_available": available,
    })


if __name__ == "__main__":
    print("Copying Arc history files...")
    copied = copy_history_files()
    for profile, path in copied.items():
        if path:
            print(f"  ✓ {profile}: {path}")
        else:
            print(f"  ✗ {profile}: not found or could not copy")

    print("\nStarting server at http://localhost:8000")
    app.run(host="localhost", port=8000)
