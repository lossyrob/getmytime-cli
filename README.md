# GetMyTime CLI

This is the unofficial command line interface for [GetMyTime](http://www.getmytime.com).
Basic functionality exists to list, delete, and create timesheet records.

Designed to work with [Hamster GetMyTime](https://github.com/kdeloach/hamster-getmytime)!

### Setup

The following environmental variables are required:

* `GETMYTIME_USERNAME`
* `GETMYTIME_PASSWORD`

### Usage

```bash
> ./getmytime.py ls -h
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
> ./getmytime.py rm -h
usage: getmytime.py rm [-h] [--dry-run] [ids [ids ...]]

positional arguments:
  ids         (defaults to stdin if empty)

optional arguments:
  -h, --help  show this help message and exit
  --dry-run   do nothing destructive (useful for testing)
```

```bash
> ./getmytime.py import -h
usage: getmytime.py import [-h] [--dry-run] [-f] [file]

positional arguments:
  file         timesheet records JSON (defaults to stdin)

optional arguments:
  -h, --help   show this help message and exit
  --dry-run    do nothing destructive (useful for testing)
  -f, --force  ignore some validation rules
```

```bash
> ./getmytime.py lookups -h
usage: getmytime.py lookups [-h] [--raw]

optional arguments:
  -h, --help  show this help message and exit
  --raw       output raw values from server
```
