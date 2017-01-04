#!/usr/bin/env python
# -*- coding: utf-8 -*-
from __future__ import print_function
from __future__ import unicode_literals
from __future__ import division

import os
import sys
import csv
import argparse
import logging

from datetime import timedelta
from dateutil import parser

from api import GetMyTimeAPI, InvalidTimeEntryError, GetMyTimeError
from api import log as api_log


log = logging.getLogger(__name__)


TIMESHEET_CSV_FIELDS = [
    'ID',
    'Date',
    'Hours',
    'Customer',
    'Activity',
    'Billable',
    'Notes',
]


def getenv(key):
    try:
        return os.environ[key]
    except KeyError:
        log.error('Environmental variable required "{}"'.format(key))
        sys.exit(1)


def find_entry(api, row, dry_run=False):
    """
    Find time entry by date, customer, activity, and minutes.
    Useful for finding entries without an ID.
    """
    startdate = parser.parse(row['Date'])
    enddate = startdate + timedelta(hours=24)

    entries = api.fetch_entries(startdate, enddate)

    for entry in entries:
        match = unicode(row['Customer']) == unicode(entry['customer']) and \
            unicode(row['Activity']) == unicode(entry['task']) and \
            unicode(row['Hours']) == unicode(entry['hours'])
        if match:
            return entry

    return None


def handle_create_entry(api, row, dry_run=False):
    try:
        hours = float(row['Hours'])
    except ValueError:
        raise Exception('ERROR: Expected Hours column to contain a valid number')

    minutes = int(hours * 60)
    tags = ['billable'] if row['Billable'] == 'Billable' else []

    api.create_time_entry(
        startdate=row['Date'],
        enddate=None,
        customer=row['Customer'],
        activity=row['Activity'],
        comments=row['Notes'],
        tags=tags,
        minutes=minutes,
        dry_run=dry_run,
    )

    if dry_run:
        return

    entry = find_entry(api, row)

    if entry:
        row['ID'] = entry['id']
    else:
        log.error('ERROR: Unable to obtain insert ID for time entry')


def handle_delete_entry(api, row, dry_run=False):
    id = abs(int(row['ID']))
    api.delete_entry(id, dry_run=dry_run)
    row['Deleted'] = True


def handle_row_action(api, row, dry_run=False):
    """
    Detect row action and execute the correct API call.
    The row argument may be mutated to add the "Deleted" field (marked
    for deletion) or update the "ID" field (for new entries).
    """
    # Empty string or 0 is used to indicate "new entry".
    try:
        id = int(row['ID'])
    except ValueError:
        id = None

    if not id:
        handle_create_entry(api, row, dry_run)
    elif id < 0:
        handle_delete_entry(api, row, dry_run)


def cmd_upload(args, api):
    """
    Perform an action for each row in the timesheet CSV and produce
    a new timesheet based on the result.
    """
    bakfile = args.filename + '.bak'
    tmpfile = args.filename + '.tmp'

    with open(args.filename, 'r') as fp_read, \
            open(tmpfile, 'w') as fp_write:

        reader = csv.DictReader(fp_read)
        writer = csv.DictWriter(fp_write, fieldnames=TIMESHEET_CSV_FIELDS)

        writer.writeheader()

        for row in reader:
            try:
                handle_row_action(api, row, dry_run=args.dry_run)

            except (InvalidTimeEntryError, GetMyTimeError) as ex:
                log.debug(row)
                friendly_exception_log(ex)

            except Exception as ex:
                # All possible exceptions should be ignored to prevent
                # corrupting the timesheet file.
                log.exception(ex.message)

            # Don't include deleted records in the new timesheet.
            if not row.get('Deleted', False):
                writer.writerow(row)

    if not args.dry_run:
        os.rename(args.filename, bakfile)
        os.rename(tmpfile, args.filename)


def entry_to_csv_row(entry):
    """
    Return entry formatted for CSV row. Should line up with TIMESHEET_CSV_FIELDS.
    """
    return {
        'ID': entry['id'],
        'Date': entry['entry_date'].strftime('%Y-%m-%d'),
        'Hours': entry['hours'],
        'Customer': entry['customer'],
        'Activity': entry['task'],
        'Billable': 'Billable' if entry['is_billable'] else 'Not-Billable',
        'Notes': entry['comments'],
    }


def deserialize_entry(row):
    """
    Return entry parsed from CSV timesheet row.
    """
    return {
        'ID': row['ID'],
        'Date': parser.parse(row['Date']),
        'Hours': float(row['Hours']),
        'Customer': row['Customer'],
        'Activity': row['Activity'],
        'Billable': 'Billable' if row['is_billable'] else 'Not-Billable',
        'Notes': row['comments'],
    }


def cmd_download(args, api):
    try:
        start_date = parser.parse(args.date)
    except ValueError:
        log.error('Unable to parse date format "{}"'.format(args.date))
        sys.exit(1)

    end_date = start_date + timedelta(days=7)
    entries = api.fetch_entries(start_date, end_date)

    w = csv.DictWriter(sys.stdout, fieldnames=TIMESHEET_CSV_FIELDS)
    w.writeheader()
    for entry in entries:
        w.writerow(entry_to_csv_row(entry))


def cmd_lookups(args, api):
    if args.kind == 'customer':
        for lookup in api.lookups['customerjobs']['rows']:
            active = lookup.get('blnStatus', 'True') == 'True'
            if active:
                print(lookup['strClientJobName'])

    elif args.kind == 'activity':
        for lookup in api.lookups['serviceitems']['rows']:
            active = lookup.get('blnStatus', 'True') == 'True'
            if active:
                print(lookup['strTaskName'])


def friendly_exception_log(ex):
    data = ex.message
    if isinstance(data, basestring):
        log.error('ERROR: {}'.format(data))
    elif 'message' in data:
        log.error('ERROR: {}'.format(data['message']))
    elif 'error' in data:
        code = data['error']['code']
        message = data['error']['message']
        log.error('ERROR {}: {}'.format(code, message))
    else:
        log.exception(ex)


def run(args):
    username = getenv('GETMYTIME_USERNAME')
    password = getenv('GETMYTIME_PASSWORD')

    try:
        api = GetMyTimeAPI()
        api.login(username, password)

        if args.cmd == 'upload':
            cmd_upload(args, api)
        elif args.cmd == 'download':
            cmd_download(args, api)
        elif args.cmd == 'lookups':
            cmd_lookups(args, api)

    except (InvalidTimeEntryError, GetMyTimeError) as ex:
        friendly_exception_log(ex)
        sys.exit(1)


def main():
    log.addHandler(logging.StreamHandler(sys.stderr))
    api_log.addHandler(logging.StreamHandler(sys.stderr))

    parser = argparse.ArgumentParser()
    parser.add_argument('-v', '--verbose', action='store_true',
                        help='Display debug messages')
    subparsers = parser.add_subparsers(help='sub-command help')

    parser1 = subparsers.add_parser('upload')
    parser1.add_argument('filename', help='Timesheet csv')
    parser1.add_argument('--dry-run', action='store_true',
                         help='Preview changes')
    parser1.set_defaults(cmd='upload')

    parser2 = subparsers.add_parser('download')
    parser2.add_argument('date', help='List entries for specified week')
    parser2.set_defaults(cmd='download')

    parser3 = subparsers.add_parser('lookups')
    parser3.add_argument('kind', choices=['customer', 'activity'],
                         help='Download specified lookups')
    parser3.set_defaults(cmd='lookups')

    args = parser.parse_args()

    log_level = logging.DEBUG if args.verbose else logging.INFO
    log.setLevel(log_level)
    api_log.setLevel(log_level)

    run(args)


if __name__ == '__main__':
    main()
