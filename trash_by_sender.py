#!/usr/bin/env python3
"""Move all emails from a given sender to Trash via Fastmail JMAP."""

import argparse
import os
import sys
import time

import requests

JMAP_SESSION_URL = "https://api.fastmail.com/jmap/session"
JMAP_USING = ["urn:ietf:params:jmap:core", "urn:ietf:params:jmap:mail"]
BATCH_SIZE = 50
MAX_RETRIES = 5
RETRY_BACKOFF = 2


def get_api_info(token):
    r = requests.get(JMAP_SESSION_URL, headers={"Authorization": f"Bearer {token}"})
    r.raise_for_status()
    session = r.json()
    api_url = session["apiUrl"]
    account_id = list(session["accounts"].keys())[0]
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    return api_url, account_id, headers


def get_trash_mailbox_id(api_url, account_id, headers):
    """Find the Trash mailbox ID using its role."""
    body = {
        "using": JMAP_USING,
        "methodCalls": [
            ["Mailbox/query", {
                "accountId": account_id,
                "filter": {"role": "trash"},
            }, "0"],
            ["Mailbox/get", {
                "accountId": account_id,
                "#ids": {
                    "resultOf": "0",
                    "name": "Mailbox/query",
                    "path": "/ids/*",
                },
                "properties": ["id", "name", "role"],
            }, "1"],
        ],
    }
    r = requests.post(api_url, headers=headers, json=body, timeout=30)
    r.raise_for_status()
    resp = r.json()

    mailboxes = resp["methodResponses"][1][1]["list"]
    if not mailboxes:
        print("Error: could not find Trash mailbox", file=sys.stderr)
        sys.exit(1)
    return mailboxes[0]["id"]


def query_emails_by_sender(api_url, account_id, headers, sender, position,
                           calculate_total=False):
    """Fetch a batch of email IDs from a given sender."""
    query_params = {
        "accountId": account_id,
        "filter": {"from": sender},
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
            ["Email/get", {
                "accountId": account_id,
                "#ids": {
                    "resultOf": "0",
                    "name": "Email/query",
                    "path": "/ids/*",
                },
                "properties": ["id", "subject", "from", "receivedAt"],
            }, "1"],
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


def move_to_trash(api_url, account_id, headers, email_ids, trash_id):
    """Move a batch of emails to Trash using Email/set."""
    update = {eid: {"mailboxIds": {trash_id: True}} for eid in email_ids}
    body = {
        "using": JMAP_USING,
        "methodCalls": [
            ["Email/set", {
                "accountId": account_id,
                "update": update,
            }, "0"],
        ],
    }
    r = requests.post(api_url, headers=headers, json=body, timeout=30)
    r.raise_for_status()
    resp = r.json()

    result = resp["methodResponses"][0]
    if result[0] == "error":
        raise RuntimeError(f"JMAP error: {result[1]}")

    set_result = result[1]
    errors = set_result.get("notUpdated")
    if errors:
        print(f"  warning: {len(errors)} emails failed to move", file=sys.stderr)
    return len(set_result.get("updated", {}))


def collect_all_emails(token, api_url, account_id, headers, sender, limit):
    """Paginate through all emails from sender, respecting limit."""
    all_emails = []
    position = 0
    total = None
    retries = 0

    while True:
        try:
            need_total = total is None
            emails, batch_total = query_emails_by_sender(
                api_url, account_id, headers, sender, position,
                calculate_total=need_total,
            )
            retries = 0

            if need_total and batch_total is not None:
                total = batch_total

            if not emails:
                break

            all_emails.extend(emails)
            position += len(emails)
            total_str = str(total) if total else "?"
            print(
                f"\r  found {position}/{total_str} emails...",
                end="", file=sys.stderr,
            )

            if limit and len(all_emails) >= limit:
                all_emails = all_emails[:limit]
                break

            if total and position >= total:
                break

        except (requests.exceptions.ConnectionError,
                requests.exceptions.Timeout):
            retries += 1
            if retries > MAX_RETRIES:
                raise
            wait = RETRY_BACKOFF * (2 ** (retries - 1))
            print(
                f"\n  connection error, retrying in {wait}s ({retries}/{MAX_RETRIES})...",
                file=sys.stderr,
            )
            time.sleep(wait)
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
    return all_emails, api_url, account_id, headers


def main():
    parser = argparse.ArgumentParser(
        description="Move all emails from a sender to Trash via Fastmail JMAP"
    )
    parser.add_argument("sender", help="Email address of the sender")
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Show what would be moved without doing it"
    )
    parser.add_argument(
        "--limit", type=int, default=0,
        help="Max number of emails to move (default: all)"
    )
    args = parser.parse_args()

    token = os.environ.get("FASTMAIL_TOKEN")
    if not token:
        print("Error: FASTMAIL_TOKEN environment variable not set", file=sys.stderr)
        sys.exit(1)

    api_url, account_id, headers = get_api_info(token)

    print(f"Finding emails from {args.sender}...", file=sys.stderr)
    emails, api_url, account_id, headers = collect_all_emails(
        token, api_url, account_id, headers, args.sender, args.limit,
    )

    if not emails:
        print("No emails found.", file=sys.stderr)
        return

    print(f"Found {len(emails)} email(s) from {args.sender}.", file=sys.stderr)

    if args.dry_run:
        for email in emails:
            date = email.get("receivedAt", "unknown date")[:10]
            subject = email.get("subject", "(no subject)")
            print(f"  {date}  {subject}")
        print(f"\n  {len(emails)} email(s) would be moved to Trash.", file=sys.stderr)
        return

    trash_id = get_trash_mailbox_id(api_url, account_id, headers)

    moved = 0
    for i in range(0, len(emails), BATCH_SIZE):
        batch = [e["id"] for e in emails[i:i + BATCH_SIZE]]
        moved += move_to_trash(api_url, account_id, headers, batch, trash_id)
        print(
            f"\r  moved {moved}/{len(emails)} emails...",
            end="", file=sys.stderr,
        )

    print(file=sys.stderr)
    print(f"Moved {moved} email(s) from {args.sender} to Trash.", file=sys.stderr)


if __name__ == "__main__":
    main()
