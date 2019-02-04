#!/usr/bin/env python
# -*- coding: utf-8 -*-
from __future__ import print_function
from __future__ import unicode_literals
from __future__ import division

import os
import re
import sys
import json
import argparse
import logging
import fileinput
import itertools

from datetime import date, datetime, timedelta

from api import GetMyTimeAPI, InvalidTimeEntryError, GetMyTimeError, format_minutes
from api import log as api_log


ID_REGEX = re.compile('(?P<id>\d{8})')

log = logging.getLogger(__name__)


def getenv(key):
    try:
        return os.environ[key]
    except KeyError:
        print('Environmental variable required: ' + key)
        sys.exit(1)


def detect_ids(lines):
    """Return list of ids scraped from each line in lines"""
    for line in lines:
        match = ID_REGEX.search(line)
        if match:
            yield int(match.group('id'))


def get_date_range(args):
    if args.today:
        start_date = date.today()
        end_date = start_date + timedelta(days=1)
        return start_date, end_date

    if args.startdate:
        start_date = datetime.strptime(args.startdate, '%Y-%m-%d')
    else:
        # Subtract 6 days so time entries from today appear by default.
        start_date = datetime.now() - timedelta(days=6)

    if args.enddate:
        end_date = datetime.strptime(args.enddate, '%Y-%m-%d')
    else:
        end_date = start_date + timedelta(days=7)

    return start_date, end_date


def get_ls_tmpl(show_comments, oneline):
    if oneline:
        tmpl = '{id} {entry_date:%Y-%m-%d} {approved_sym}{billable_sym} ' \
               '{hours_str:>3}{minutes_str:>3} {customer} > {task}'
        if show_comments:
            tmpl += '; Notes: {comments}'
    else:
        tmpl = 'ID: {id}\nDate: {entry_date:%Y-%m-%d}\nBillable: {billable}\n' \
               'Approved: {approved}\nCustomer: {customer}\nTask: {task}\n' \
               'Duration: {hours_str}{minutes_str}\nNotes: {comments}\n'
    return tmpl


def ls(entries, show_comments=False, oneline=False, custom_tmpl=None):
    if custom_tmpl:
        tmpl = custom_tmpl
    else:
        tmpl = get_ls_tmpl(show_comments, oneline)

    try:
        for entry in entries:
            print(tmpl.format(**entry))
    except KeyError as ex:
        log.error('Invalid template: Time entries do not have a "{}" field.'.format(ex.message))


def ls_total(entries, args):
    grand_total = 0

    entries = list(entries)
    customer_maxlen = max(len(entry['customer']) for entry in entries)

    group_by_fields = args.group_by.split(',') if args.group_by \
        else ['entry_date']

    row_fmt = []
    for field in group_by_fields:
        if field == 'entry_date':
            row_fmt.append('{0:%Y-%m-%d}')
        elif field == 'entry_week':
            row_fmt.append('{1:%Y-%m-%d}')
        elif field == 'customer':
            row_fmt.append('{2:<' + str(customer_maxlen) + '}')
    row_fmt = ' '.join(row_fmt) + ' {3:>3}{4:>3}'

    entry_key = lambda entry: tuple(entry[k] for k in group_by_fields)
    entries = sorted(entries, key=entry_key)
    grouped_entries = itertools.groupby(entries, key=entry_key)

    for key, entries in grouped_entries:
        entries = list(entries)

        entry_date = entries[0]['entry_date']
        entry_week = entries[0]['entry_week']
        customer = entries[0]['customer']

        total = sum(entry['minutes'] for entry in entries)
        hrs, mins = format_minutes(total)
        grand_total += total

        print(row_fmt.format(entry_date, entry_week, customer, hrs, mins))

    hrs, mins = format_minutes(grand_total)
    print('{:}{:>3}'.format(hrs, mins))


def create_entries(api, entries, **flags):
    print('Importing {} entries...'.format(len(entries)))
    for entry in entries:
        record = {}
        record.update(entry)
        record.update(flags)
        api.create_time_entry(**record)
    print('Done')


def main():
    log.addHandler(logging.StreamHandler(sys.stderr))
    api_log.addHandler(logging.StreamHandler(sys.stderr))
    log.setLevel(logging.INFO)
    api_log.setLevel(logging.INFO)

    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(help='sub-command help')

    parser1 = subparsers.add_parser('ls')
    parser1.add_argument('startdate', nargs='?',
                         help='format: YYYY-MM-DD, inclusive (default: today)')
    parser1.add_argument('enddate', nargs='?',
                         help='format: YYYY-MM-DD, exclusive (default: startdate + 7 days)')
    parser1.add_argument('--today', action='store_true',
                         help='show results for today only (overrides --startdate and --enddate)')
    parser1.add_argument('--comments', action='store_true',
                         help='show comments (only relevant for --oneline)')
    parser1.add_argument('--oneline', action='store_true',
                         help='output single line per time entry')
    parser1.add_argument('--tmpl', type=str,
                         help='custom template per time entry')
    parser1.add_argument('--total', action='store_true',
                         help='show daily and weekly totals')
    parser1.add_argument('--group-by',
                         help='group totals by entry_date, entry_week, or customer')
    parser1.set_defaults(cmd='ls')

    parser2 = subparsers.add_parser('rm')
    parser2.add_argument('ids', type=int, nargs='*',
                         help='(defaults to stdin if empty)')
    parser2.add_argument('--dry-run', action='store_true',
                         help='do nothing destructive (useful for testing)')
    parser2.set_defaults(cmd='rm')

    parser3 = subparsers.add_parser('import')
    parser3.add_argument('file', nargs='?', default='-',
                         help='timesheet records JSON (defaults to stdin)')
    parser3.add_argument('--dry-run', action='store_true',
                         help='do nothing destructive (useful for testing)')
    parser3.add_argument('-f', '--force', action='store_true',
                         help='ignore some validation rules')
    parser3.set_defaults(cmd='import')

    parser4 = subparsers.add_parser('lookups')
    parser4.add_argument('--raw', action='store_true',
                         help='output raw values from server')
    parser4.set_defaults(cmd='lookups')

    args = parser.parse_args()

    username = getenv('GETMYTIME_USERNAME')
    password = getenv('GETMYTIME_PASSWORD')

    if not hasattr(args, 'cmd'):
        parser.print_help(sys.stderr)
        sys.exit(1)

    try:
        api = GetMyTimeAPI()
        api.login(username, password)

        if args.cmd == 'ls':
            start_date, end_date = get_date_range(args)
            entries = api.fetch_entries(start_date, end_date)

            if args.total:
                ls_total(entries, args)
            else:
                ls(entries,
                   show_comments=args.comments,
                   oneline=args.oneline,
                   custom_tmpl=args.tmpl)

        elif args.cmd == 'rm':
            ids = args.ids if args.ids else detect_ids(fileinput.input('-'))
            api.rm(ids, dry_run=args.dry_run)

        elif args.cmd == 'import':
            lines = fileinput.input(args.file)
            contents = ''.join(lines)
            entries = json.loads(contents)
            create_entries(api, entries, dry_run=args.dry_run, force=args.force)

        elif args.cmd == 'lookups':
            if args.raw:
                print(json.dumps(api.lookups))
            else:
                print(json.dumps({
                    'lookupByName': api.lookupByName,
                    'lookupById': api.lookupById,
                }))

    except (InvalidTimeEntryError, GetMyTimeError) as ex:
        data = ex.message
        if isinstance(data, basestring):
            log.error('Error: {}'.format(data))
        elif 'message' in data:
            log.error('{}'.format(data['message']))
        elif 'error' in data:
            code = data['error']['code']
            message = data['error']['message']
            log.error('{} {}'.format(code, message))
        else:
            log.exception(ex)
        sys.exit(1)


if __name__ == '__main__':
    main()
