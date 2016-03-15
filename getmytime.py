#!/usr/bin/env python
# -*- coding: utf-8 -*-
from __future__ import print_function
from __future__ import unicode_literals
from __future__ import division

import os
import re
import sys
import argparse
import json
import logging
import requests
import time
import itertools
import fileinput

from datetime import date, datetime, timedelta


ID_REGEX = re.compile('(?P<id>\d{8})')

log = logging.getLogger(__name__)
log.addHandler(logging.StreamHandler(sys.stderr))
log.setLevel(logging.DEBUG)


def getenv(key):
    try:
        return os.environ[key]
    except KeyError:
        print('Environmental variable required: ' + key)
        sys.exit(1)


class GetMyTimeError(Exception):
    pass


class GetMyTimeApi(object):
    URL = 'https://app.getmytime.com/service.aspx'

    def login(self, username, password):
        #time.sleep(1)

        params = {
            'object': 'getmytime.api.usermanager',
            'method': 'login',
        }
        form_data = {
            'username': username,
            'password': password,
        }

        r = requests.post(self.URL, params=params, data=form_data)
        payload = r.json()

        if 'error' in payload:
            raise GetMyTimeError(payload)

        self.cookies = r.cookies
        self.fetch_lookups()

    def fetch_lookups(self):
        #time.sleep(1)

        params = {
            'object': 'getmytime.api.managemanager',
            'method': 'fetchLookups',
        }
        form_data = {
            'lookups': '[projectgroups],[customerjobs],[serviceitems]',
        }

        r = requests.post(self.URL, params=params, data=form_data,
                          cookies=self.cookies)

        payload = r.json()
        lookup = lambda k, a, b: dict((row[a], row[b].replace('&amp;', '&'))
                                      for row in payload[k]['rows'])

        self.lookups = {
            'jobs': lookup('customerjobs',
                           'intClientJobListID', 'strClientJobName'),
            'tasks': lookup('serviceitems',
                            'intTaskListID', 'strTaskName'),
        }

    def fetch_entries(self, start_date, end_date):
        curdate = start_date

        while curdate < end_date:
            time.sleep(1)

            params = {
                'object': 'getmytime.api.timeentrymanager',
                'method': 'fetchTimeEntries',
            }
            form_data = {
                'employeeid': self.cookies['userid'],
                'startdate': '{:%m/%d/%Y}'.format(curdate),
            }

            r = requests.post(self.URL, params=params, data=form_data,
                              cookies=self.cookies)

            payload = r.json()

            if 'error' in payload:
                raise GetMyTimeError(payload)

            try:
                rows = payload['rows']
            except KeyError:
                # No records were found.
                raise GetMyTimeError(payload)

            by_date = lambda entry: entry['entry_date']
            entries = self.parse_entries(payload['rows'])
            entries = sorted(entries, key=by_date)

            for entry in entries:
                if entry['entry_date'] < end_date:
                    yield entry

            curdate += timedelta(days=7)

    def parse_entries(self, rows):
        jobs = self.lookups['jobs']
        tasks = self.lookups['tasks']
        for row in rows:
            minutes = int(row['intMinutes'])
            hrs, mins = self.format_minutes(minutes)
            yield {
                'id': row['intTimeEntryID'],
                'billable': 'Yes' if row['blnBillable'] == 'True' else 'No ',
                'approved': 'Yes' if row['blnApproved'] == 'True' else 'No ',
                'billable_sym': '$' if row['blnBillable'] == 'True' else ' ',
                'approved_sym': '*' if row['blnApproved'] == 'True' else ' ',
                'job': jobs[row['intClientJobListID']],
                'task': tasks[row['intTaskListID']],
                'comments': row['strComments'].replace('\n', ' '),
                'entry_date': datetime.strptime(row['dtmTimeWorkedDate'],
                                                '%m/%d/%Y %I:%M:%S %p'),
                'minutes': minutes,
                'minutes_str': mins,
                'hours_str': hrs,
            }

    def format_minutes(self, minutes):
        hours = minutes // 60
        minutes -= hours * 60
        return (str(hours) + 'h' if hours > 0 else '',
                str(minutes) + 'm' if minutes > 0 else '')

    def get_ls_tmpl(self, show_comments, oneline):
        if oneline:
            tmpl = '{id} {entry_date:%Y-%m-%d} {approved_sym}{billable_sym} ' \
                   '{hours_str:>3}{minutes_str:>3} {job} > {task}'
            if show_comments:
                tmpl += '; Notes: {comments}'
        else:
            tmpl = 'ID: {id}\nDate: {entry_date:%Y-%m-%d}\nBillable: {billable}\n' \
                   'Approved: {approved}\nJob: {job}\nTask: {task}\n' \
                   'Duration: {hours_str}{minutes_str}\nNotes: {comments}\n'
        return tmpl


    def ls(self, entries, show_comments=False, oneline=False, custom_tmpl=None):
        if custom_tmpl:
            tmpl = custom_tmpl
        else:
            tmpl = self.get_ls_tmpl(show_comments, oneline)

        try:
            for entry in entries:
                print(tmpl.format(**entry))
        except KeyError as ex:
            log.error('Invalid template: Time entries do not have a "{}" field.'.format(ex.message))
        sys.stdout.flush()

    def ls_total(self, entries):
        grand_total = 0
        by_date = lambda entry: entry['entry_date']
        entries_by_date = itertools.groupby(entries, key=by_date)
        for entry_date, entries in entries_by_date:
            total = sum(entry['minutes'] for entry in entries)
            hrs, mins = self.format_minutes(total)
            grand_total += total
            print('{:%Y-%m-%d} {:>3}{:>3}'.format(entry_date, hrs, mins))
        sys.stdout.flush()

        hrs, mins = self.format_minutes(grand_total)
        print('{:>14}{:>3}'.format(hrs, mins))

    def rm(self, ids, dry_run=False):
        # time.sleep(1)
        total = 0

        for id in ids:
            log.debug('Deleting {}'.format(id))

            if dry_run:
                continue

            params = {
                'object': 'getmytime.api.timeentrymanager',
                'method': 'deleteTimeEntry',
            }
            form_data = {
                'timeentryid': id,
            }

            r = requests.post(self.URL, params=params, data=form_data,
                              cookies=self.cookies)

            payload = r.json()

            if 'error' in payload:
                raise GetMyTimeError(payload)

            log.info(r.text)
            total += 1

        print('Deleted {} record(s)'.format(total))


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


def main():
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(help='sub-command help')

    parser1 = subparsers.add_parser('ls')
    parser1.add_argument('--startdate', help='format: YYYY-MM-DD, inclusive (default: today)')
    parser1.add_argument('--enddate', help='format: YYYY-MM-DD, exclusive (default: startdate + 7 days)')
    parser1.add_argument('--today', action='store_true', help='show results for today only (overrides --startdate and --enddate)')
    parser1.add_argument('--comments', action='store_true', help='show comments (only relevant for --oneline)')
    parser1.add_argument('--oneline', action='store_true', help='output single line per time entry')
    parser1.add_argument('--tmpl', type=str, help='custom template per time entry')
    parser1.add_argument('--total', action='store_true', help='show daily and weekly totals')
    parser1.set_defaults(cmd='ls')

    parser2 = subparsers.add_parser('rm')
    parser2.add_argument('ids', type=int, nargs='*')
    parser2.add_argument('--dry-run', action='store_true', help='do nothing destructive (useful for testing)')
    parser2.set_defaults(cmd='rm')

    args = parser.parse_args()

    username = getenv('GETMYTIME_USERNAME')
    password = getenv('GETMYTIME_PASSWORD')

    try:
        api = GetMyTimeApi()
        api.login(username, password)

        if args.cmd == 'ls':
            start_date, end_date = get_date_range(args)
            entries = api.fetch_entries(start_date, end_date)

            if args.total:
                api.ls_total(entries)
            else:
                api.ls(entries,
                       show_comments=args.comments,
                       oneline=args.oneline,
                       custom_tmpl=args.tmpl)

        elif args.cmd == 'rm':
            ids = args.ids if args.ids else detect_ids(fileinput.input('-'))
            api.rm(ids, dry_run=args.dry_run)

    except GetMyTimeError as ex:
        data = ex.message
        if 'message' in data:
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
