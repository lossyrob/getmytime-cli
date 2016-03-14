#!/usr/bin/env python
# -*- coding: utf-8 -*-
from __future__ import print_function
from __future__ import unicode_literals
from __future__ import division

import os
import argparse
import json
import logging
import requests
import sys
import time

from itertools import groupby
from datetime import datetime, timedelta


log = logging.getLogger(__name__)
log.addHandler(logging.StreamHandler(sys.stderr))
log.setLevel(logging.DEBUG)


def getenv(key):
    try:
        return os.environ[key]
    except KeyError:
        print('Environmental variable required: ' + key)
        sys.exit(1)


def parse_date(value, default=None):
    if not value:
        return default
    return datetime.strptime(value, '%Y-%m-%d')


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

    def fetch_entries(self, startdate, enddate):
        curdate = startdate

        while curdate < enddate:
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
                yield payload['rows']
            except KeyError:
                # No records were found.
                raise GetMyTimeError(payload)

            curdate += timedelta(days=7)

    def parse_entries(self, rows):
        jobs = self.lookups['jobs']
        tasks = self.lookups['tasks']
        for row in rows:
            minutes = int(row['intMinutes'])
            hrs, mins = self.format_minutes(minutes)
            yield {
                'id': row['intTimeEntryID'],
                'billable': '$' if row['blnBillable'] == 'True' else ' ',
                'approved': '*' if row['blnApproved'] == 'True' else ' ',
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

    def ls(self, xentries):
        for entries in xentries:
            lines = self.parse_entries(entries)
            lines = sorted(lines, key=lambda line: line['entry_date'])
            line_tmpl = '{id} {approved}{billable} {entry_date:%Y-%m-%d} ' \
                        '{hours_str:>3}{minutes_str:>3} {job} ({task}) ' \
                        '{comments}'

            for line in lines:
                print(line_tmpl.format(**line))

            sys.stdout.flush()

    def ls_total(self, xentries):
        grand_total = 0

        for entries in xentries:
            lines = self.parse_entries(entries)
            lines = sorted(lines, key=lambda line: line['entry_date'])
            lines_by_day = groupby(lines, key=lambda line: line['entry_date'])

            for entry_date, lines in lines_by_day:
                total = sum(line['minutes'] for line in lines)
                hrs, mins = self.format_minutes(total)
                grand_total += total
                print('{:%Y-%m-%d} {:>3}{:>3}'.format(entry_date, hrs, mins))
            sys.stdout.flush()

        hrs, mins = self.format_minutes(grand_total)
        print('{:>14}{:>3}'.format(hrs, mins))

    def rm(self, ids):
        # time.sleep(1)
        for id in ids:
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
            print(r.text)


def main():
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(help='sub-command help')

    parser1 = subparsers.add_parser('ls')
    parser1.add_argument('--startdate')
    parser1.add_argument('--enddate')
    parser1.add_argument('--total', action='store_true')
    parser1.set_defaults(cmd='ls')

    parser2 = subparsers.add_parser('rm')
    parser2.add_argument('ids', type=int, nargs='+')
    parser2.set_defaults(cmd='rm')

    args = parser.parse_args()

    username = getenv('GETMYTIME_USERNAME')
    password = getenv('GETMYTIME_PASSWORD')

    try:
        api = GetMyTimeApi()
        api.login(username, password)

        if args.cmd == 'ls':
            if args.startdate:
                startdate = datetime.strptime(args.startdate, '%Y-%m-%d')
            else:
                startdate = datetime.now() - timedelta(days=7)

            if args.enddate:
                enddate = datetime.strptime(args.enddate, '%Y-%m-%d')
            else:
                enddate = startdate + timedelta(days=7)

            entries = api.fetch_entries(startdate, enddate)

            if args.total:
                api.ls_total(entries)
            else:
                api.ls(entries)

        elif args.cmd == 'rm':
            api.rm(args.ids)

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
