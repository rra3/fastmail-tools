#!/usr/bin/env python3
"""Show top email senders from Fastmail across all mailboxes."""

import argparse
import os
import sys
import time
from collections import Counter
from datetime import datetime, timedelta, timezone

import requests

JMAP_SESSION_URL = "https://api.fastmail.com/jmap/session"
JMAP_USING = ["urn:ietf:params:jmap:core", "urn:ietf:params:jmap:mail"]
BATCH_SIZE = 50
MAX_RETRIES = 5
RETRY_BACKOFF = 2  # seconds, doubled each retry


def get_api_info(token):
    r = requests.get(JMAP_SESSION_URL, headers={"Authorization": f"Bearer {token}"})
    r.raise_for_status()
    session = r.json()
    api_url = session["apiUrl"]
    account_id = list(session["accounts"].keys())[0]
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    return api_url, account_id, headers


def fetch_sender_batch(api_url, account_id, headers, after, position,
                       calculate_total=False):
    """Fetch a batch of email sender addresses starting at position."""
    query_params = {
        "accountId": account_id,
        "filter": {"after": after},
        "sort": [{"property": "receivedAt", "isAscending": False}],
        "position": position,
        "limit": BATCH_SIZE,
    }
    if calculate_total:
        query_params["calculateTotal"] = True

    body = {
        "using": JMAP_USING,
        "methodCalls": [
            ["Email/query", query_params, "0"],
            [
                "Email/get",
                {
                    "accountId": account_id,
                    "#ids": {
                        "resultOf": "0",
                        "name": "Email/query",
                        "path": "/ids/*",
                    },
                    "properties": ["from"],
                },
                "1",
            ],
        ],
    }
    r = requests.post(api_url, headers=headers, json=body, timeout=30)
    r.raise_for_status()
    resp = r.json()

    query_result = resp["methodResponses"][0][1]
    total = query_result.get("total")

    get_result = resp["methodResponses"][1]
    if get_result[0] == "error":
        raise RuntimeError(f"JMAP error: {get_result[1]}")

    emails = get_result[1]["list"]
    return emails, total


def collect_senders(token, api_url, account_id, headers, after):
    """Paginate through all emails since `after` and count senders."""
    counts = Counter()
    position = 0
    total = None
    retries = 0

    while True:
        try:
            need_total = total is None
            emails, batch_total = fetch_sender_batch(
                api_url, account_id, headers, after, position,
                calculate_total=need_total,
            )
            retries = 0  # reset on success

            if need_total and batch_total is not None:
                total = batch_total

            if not emails:
                break

            for email in emails:
                frm = email.get("from") or [{}]
                addr = frm[0].get("email", "unknown").lower()
                counts[addr] += 1

            position += len(emails)
            total_str = str(total) if total else "?"
            print(
                f"\r  fetched {position}/{total_str} emails...",
                end="", file=sys.stderr,
            )

            if total and position >= total:
                break

        except (requests.exceptions.ConnectionError,
                requests.exceptions.Timeout) as e:
            retries += 1
            if retries > MAX_RETRIES:
                raise
            wait = RETRY_BACKOFF * (2 ** (retries - 1))
            print(
                f"\n  connection error, retrying in {wait}s ({retries}/{MAX_RETRIES})...",
                file=sys.stderr,
            )
            time.sleep(wait)
            # refresh session in case it expired
            api_url, account_id, headers = get_api_info(token)

        except requests.exceptions.HTTPError as e:
            if e.response is not None and e.response.status_code in (401, 403):
                retries += 1
                if retries > MAX_RETRIES:
                    raise
                print("\n  session expired, refreshing...", file=sys.stderr)
                time.sleep(1)
                api_url, account_id, headers = get_api_info(token)
            else:
                raise

    print(file=sys.stderr)
    return counts, position


def main():
    parser = argparse.ArgumentParser(description="Top email senders from Fastmail")
    parser.add_argument(
        "-n", type=int, default=25, help="Number of top senders to show (default: 25)"
    )
    parser.add_argument(
        "--months", type=int, default=6,
        help="How many months back to look (default: 6)"
    )
    args = parser.parse_args()

    token = os.environ.get("FASTMAIL_TOKEN")
    if not token:
        print("Error: FASTMAIL_TOKEN environment variable not set", file=sys.stderr)
        sys.exit(1)

    since = datetime.now(timezone.utc) - timedelta(days=args.months * 30)
    after = since.strftime("%Y-%m-%dT%H:%M:%SZ")

    print(f"Fetching emails since {since.strftime('%Y-%m-%d')}...", file=sys.stderr)

    api_url, account_id, headers = get_api_info(token)
    counts, total = collect_senders(token, api_url, account_id, headers, after)

    top = counts.most_common(args.n)
    if not top:
        print("No emails found.", file=sys.stderr)
        return

    rank_width = len(str(args.n))
    count_width = len(str(top[0][1]))

    for i, (addr, count) in enumerate(top, 1):
        print(f"  {i:>{rank_width}}. {count:>{count_width}}  {addr}")

    print(f"\n  {len(counts)} unique senders, {total} emails total", file=sys.stderr)


if __name__ == "__main__":
    main()
