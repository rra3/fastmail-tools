# fasttail

A command-line tool to fetch recent emails from Fastmail using the JMAP API, with procmail-style log output.

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

## Usage

### Fetch recent emails

```bash
python3 fasttail.py          # last 10 emails
python3 fasttail.py -n 20    # last 20 emails
```

Output is procmail `LOGABSTRACT` style:

```
From sender@example.com  Wed Feb 11 14:07:58 2026
 Subject: The innovation is real
  Folder: Inbox	136985
```

### Color output

```bash
python3 fasttail.py --color auto     # default — color in terminal, plain when piped
python3 fasttail.py --color always   # force color on
python3 fasttail.py --color never    # no color
```

### Pager

By default, output is paged through `less` when running in a terminal. Disable with:

```bash
python3 fasttail.py --no-pager
```

### Daemon mode

Run as a background process that polls Fastmail for new messages and appends them to a log file:

```bash
# Terminal 1: start the daemon
python3 fasttail.py --daemon &

# Terminal 2: watch for new mail
tail -f ~/.fastmail.log
```

Options:

- `--logfile PATH` — log file path (default: `~/.fastmail.log`)
- `--interval SECONDS` — polling interval (default: `60`)

```bash
python3 fasttail.py --daemon --logfile /tmp/mail.log --interval 30
```

The daemon seeds the last 50 email IDs on startup so it won't flood the log with old mail — only new arrivals get appended. Stop it with Ctrl-C or `kill`.
