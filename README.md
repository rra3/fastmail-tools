# fastmail-tools

A collection of command-line tools for Fastmail, built on the JMAP API.

## Setup

Requires Python 3 and the `requests` library:

```bash
pip install requests
```

Create a Fastmail API token at **Settings > Privacy & Security > API tokens** with at least these scopes:

- `urn:ietf:params:jmap:core`
- `urn:ietf:params:jmap:mail`

Export it:

```bash
export FASTMAIL_TOKEN=your_token_here
```

## Tools

### fasttail — fetch and tail recent emails

Procmail-style log output for your Fastmail inbox.

```bash
python3 fasttail.py          # last 10 emails
python3 fasttail.py -n 20    # last 20 emails
```

Output:

```
From sender@example.com  Wed Feb 11 14:07:58 2026
 Subject: The innovation is real
  Folder: Inbox	136985
```

Options:

- `--color auto|always|never` — color output (default: `auto`)
- `--no-pager` — disable built-in `less` pager

#### Daemon mode

Poll for new messages and append to a log file:

```bash
python3 fasttail.py --daemon &
tail -f ~/.fastmail.log
```

- `--logfile PATH` — log file path (default: `~/.fastmail.log`)
- `--interval SECONDS` — polling interval (default: `60`)
- `--backfill N` — write last N emails to log on startup (default: `0`)

### top_senders — rank senders by volume

Show your top email senders across all mailboxes.

```bash
python3 top_senders.py              # top 25 senders, last 6 months
python3 top_senders.py -n 50        # top 50
python3 top_senders.py --months 12  # last year
```

Output:

```
   1. 904  hello@pacas.us
   2. 783  harryanddavid@harryanddavid-email.com
   3. 772  info@jomashop.com
  ...
```

### unsubscribe — unsubscribe from a sender

Find and execute the unsubscribe mechanism for a given sender.

```bash
python3 unsubscribe.py hello@pacas.us           # unsubscribe
python3 unsubscribe.py --dry-run hello@pacas.us  # just show what it would do
```

Tries three strategies in priority order:

1. **RFC 8058 one-click POST** — `List-Unsubscribe-Post` header (most reliable)
2. **List-Unsubscribe header URL** — visit the URL, submit any confirmation form
3. **HTML body link** — parse the email for unsubscribe links

Some senders require JavaScript or manual confirmation; the tool will print the URL to open in a browser when it can't complete the process automatically.
