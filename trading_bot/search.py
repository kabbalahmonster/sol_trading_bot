#!/usr/bin/env python3
"""Jupiter token search helper (Ultra API / lite).

This is a tiny CLI tool to look up token metadata by symbol/name/mint.

Uses (no API key required):
  https://lite-api.jup.ag/ultra/v1/search?query=<QUERY>

USAGE:
  python search.py --query BANKR
  python search.py --query 4BmaxxckzuAnFZANYP8uZ4MQUBLoKBHxbx1xbZSDbank

Output:
- Prints the raw JSON and a short summary (id/name/symbol/mcap).

NOTE:
- Jupiter search is best-effort and sometimes returns multiple matches.
"""

import argparse
import requests


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--query", required=True, help="Symbol/name/mint to search")
    args = ap.parse_args()

    url = "https://lite-api.jup.ag/ultra/v1/search"
    r = requests.get(url, params={"query": args.query}, headers={"Accept": "application/json"}, timeout=20)
    r.raise_for_status()

    data = r.json()
    print(data)

    if isinstance(data, list):
        for item in data:
            print("id:", item.get("id"))
            print("name:", item.get("name"))
            print("symbol:", item.get("symbol"))
            print("mcap:", item.get("mcap"))
            print("-")


if __name__ == "__main__":
    main()
