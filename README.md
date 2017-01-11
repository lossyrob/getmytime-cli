# GetMyTime CLI

[![Docker Repository on Quay](https://quay.io/repository/kdeloach/getmytime-cli/status "Docker Repository on Quay")](https://quay.io/repository/kdeloach/getmytime-cli)

Command line interface for [GetMyTime](http://www.getmytime.com).
Basic functionality exists to list, delete, and create timesheet records.

Works great with [Hamster GetMyTime](https://github.com/kdeloach/hamster-getmytime).

## Quick Start

```
docker run --rm -ti \
    -e GETMYTIME_USERNAME=username \
    -e GETMYTIME_PASSWORD=password \
    --entrypoint bash \
    quay.io/kdeloach/getmytime-cli
```

## Setup

Docker is required.

Required environment variables:

|                      |
| -------------------  |
| `GETMYTIME_USERNAME` |
| `GETMYTIME_PASSWORD` |

Run these commands:

```sh
./scripts/update.sh
./scripts/console.sh
```

## Usage

### getmytime.py

```bash
usage: getmytime.py ls [-h] [--today] [--comments] [--oneline] [--tmpl TMPL]
                       [--total]
                       [startdate] [enddate]

positional arguments:
  startdate    format: YYYY-MM-DD, inclusive (default: today)
  enddate      format: YYYY-MM-DD, exclusive (default: startdate + 7 days)

optional arguments:
  -h, --help   show this help message and exit
  --today      show results for today only (overrides --startdate and
               --enddate)
  --comments   show comments (only relevant for --oneline)
  --oneline    output single line per time entry
  --tmpl TMPL  custom template per time entry
  --total      show daily and weekly totals
```

```bash
usage: getmytime.py rm [-h] [--dry-run] [ids [ids ...]]

positional arguments:
  ids         (defaults to stdin if empty)

optional arguments:
  -h, --help  show this help message and exit
  --dry-run   do nothing destructive (useful for testing)
```

```bash
usage: getmytime.py import [-h] [--dry-run] [-f] [file]

positional arguments:
  file         timesheet records JSON (defaults to stdin)

optional arguments:
  -h, --help   show this help message and exit
  --dry-run    do nothing destructive (useful for testing)
  -f, --force  ignore some validation rules
```

```bash
usage: getmytime.py lookups [-h] [--raw]

optional arguments:
  -h, --help  show this help message and exit
  --raw       output raw values from server
```

### getmytime-edit.py

```
usage: getmytime-edit.py download [-h] date

positional arguments:
  date        List entries for specified week

optional arguments:
  -h, --help  show this help message and exit
```

```
usage: getmytime-edit.py upload [-h] [--dry-run] filename

positional arguments:
  filename    Timesheet csv

optional arguments:
  -h, --help  show this help message and exit
  --dry-run   Preview changes
```

```
usage: getmytime-edit.py lookups [-h] {customer,activity}

positional arguments:
  {customer,activity}  Download specified lookups

optional arguments:
  -h, --help           show this help message and exit
```
