import csv
from datetime import datetime, timezone
import os
import time
import requests
import sys

GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN")

if not GITHUB_TOKEN:
    print("Error: 'GITHUB_TOKEN' not set.")
    sys.exit(1)

data_dir = sys.argv[sys.argv.index("-d") + 1] if "-d" in sys.argv else "data"
os.makedirs(data_dir, exist_ok=True)

TRAFFIC_FILE = f"{data_dir}/github_traffic.csv"
REFERRERS_FILE = f"{data_dir}/github_referrers.csv"
PATHS_FILE = f"{data_dir}/github_paths.csv"

today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")

headers = {
    "Accept": "application/vnd.github+json",
    "Authorization": f"Bearer {GITHUB_TOKEN}",
    "X-GitHub-Api-Version": "2026-03-10"
}

def safe_get(url, headers):
    """Makes a GET request while defensively managing GitHub's primary and secondary rate limits."""
    while True:
        res = requests.get(url, headers=headers)

        if res.status_code in (403, 429):
            if "Retry-After" in res.headers:
                wait_time = int(res.headers["Retry-After"])
                print(
                    f"Secondary rate limit triggered. Pausing for {wait_time} seconds..."
                )
                time.sleep(wait_time)
                continue

            if res.headers.get("X-RateLimit-Remaining") == "0":
                reset_timestamp = int(res.headers.get("X-RateLimit-Reset", 0))
                wait_time = max(int(reset_timestamp - time.time()) + 1, 1)
                print(
                    f"Primary rate limit reached. Sleeping until reset ({wait_time} seconds)..."
                )
                time.sleep(wait_time)
                continue

        res.raise_for_status()
        return res


existing_traffic = {}
if os.path.exists(TRAFFIC_FILE):
    with open(TRAFFIC_FILE, mode="r", newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            existing_traffic[(row["repository"], row["date"])] = {
                "views_total": int(row["views_total"] or 0),
                "views_unique": int(row["views_unique"] or 0),
                "clones_total": int(row["clones_total"] or 0),
                "clones_unique": int(row["clones_unique"] or 0),
            }

existing_referrers = {}
if os.path.exists(REFERRERS_FILE):
    with open(REFERRERS_FILE, mode="r", newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            existing_referrers[
                (row["run_date"], row["repository"], row["referrer"])
            ] = {
                "total": int(row["total"] or 0),
                "unique": int(row["unique"] or 0),
            }

existing_paths = {}
if os.path.exists(PATHS_FILE):
    with open(PATHS_FILE, mode="r", newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            existing_paths[(row["run_date"], row["repository"], row["path"])] = {
                "title": row["title"],
                "total": int(row["total"] or 0),
                "unique": int(row["unique"] or 0),
            }

try:
    response = safe_get(
        "https://api.github.com/user/repos?per_page=100", headers
    )
    repos_list = response.json()
except requests.exceptions.RequestException as e:
    print(f"Failed to fetch repositories: {e}")
    sys.exit(1)

for r in repos_list:
    if r["private"]:
        continue
    name = r["full_name"]

    try:
        v_res = safe_get(
            f"https://api.github.com/repos/{name}/traffic/views", headers
        ).json()
        for v in v_res.get("views", []):
            date = v["timestamp"].split("T")[0]
            key = (name, date)
            existing_traffic.setdefault(
                key,
                {
                    "views_total": 0,
                    "views_unique": 0,
                    "clones_total": 0,
                    "clones_unique": 0,
                },
            )
            existing_traffic[key]["views_total"] = v["count"]
            existing_traffic[key]["views_unique"] = v["uniques"]
    except Exception as e:
        print(f"  Error fetching views for {name}: {e}")

    try:
        c_res = safe_get(
            f"https://api.github.com/repos/{name}/traffic/clones", headers
        ).json()
        for c in c_res.get("clones", []):
            date = c["timestamp"].split("T")[0]
            key = (name, date)
            existing_traffic.setdefault(
                key,
                {
                    "views_total": 0,
                    "views_unique": 0,
                    "clones_total": 0,
                    "clones_unique": 0,
                },
            )
            existing_traffic[key]["clones_total"] = c["count"]
            existing_traffic[key]["clones_unique"] = c["uniques"]
    except Exception as e:
        print(f"  Error fetching clones for {name}: {e}")

    try:
        ref_res = safe_get(
            f"https://api.github.com/repos/{name}/traffic/popular/referrers",
            headers,
        ).json()
        for ref in ref_res:
            key = (today_str, name, ref["referrer"])
            existing_referrers[key] = {
                "total": ref["count"],
                "unique": ref["uniques"],
            }
    except Exception as e:
        print(f"  Error fetching referrers for {name}: {e}")

    try:
        path_res = safe_get(
            f"https://api.github.com/repos/{name}/traffic/popular/paths",
            headers,
        ).json()
        for p in path_res:
            key = (today_str, name, p["path"])
            existing_paths[key] = {
                "title": p.get("title", ""),
                "total": p["count"],
                "unique": p["uniques"],
            }
    except Exception as e:
        print(f"  Error fetching paths for {name}: {e}")

with open(TRAFFIC_FILE, mode="w", newline="", encoding="utf-8") as f:
    writer = csv.DictWriter(
        f,
        fieldnames=[
            "date",
            "repository",
            "views_total",
            "views_unique",
            "clones_total",
            "clones_unique",
        ],
    )
    writer.writeheader()
    for (repo, date), s in sorted(existing_traffic.items()):
        if not any(s.values()):
            continue
        writer.writerow(
            {
                "date": date,
                "repository": repo,
                "views_total": s["views_total"],
                "views_unique": s["views_unique"],
                "clones_total": s["clones_total"],
                "clones_unique": s["clones_unique"],
            }
        )

with open(REFERRERS_FILE, mode="w", newline="", encoding="utf-8") as f:
    writer = csv.DictWriter(
        f,
        fieldnames=["run_date", "repository", "referrer", "total", "unique"],
    )
    writer.writeheader()
    for (run_date, repo, referrer), s in sorted(existing_referrers.items()):
        writer.writerow(
            {
                "run_date": run_date,
                "repository": repo,
                "referrer": referrer,
                "total": s["total"],
                "unique": s["unique"],
            }
        )

with open(PATHS_FILE, mode="w", newline="", encoding="utf-8") as f:
    writer = csv.DictWriter(
        f,
        fieldnames=[
            "run_date",
            "repository",
            "path",
            "title",
            "total",
            "unique",
        ],
    )
    writer.writeheader()
    for (run_date, repo, path), s in sorted(existing_paths.items()):
        writer.writerow(
            {
                "run_date": run_date,
                "repository": repo,
                "path": path,
                "title": s["title"],
                "total": s["total"],
                "unique": s["unique"],
            }
        )
