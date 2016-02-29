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

        if 'Incorrect' in r.text:
            raise GetMyTimeError(r.text)

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

    def ls(self, startdate):
        #time.sleep(1)

        employeeid = self.cookies['userid']
        startdate = '{:%m/%d/%Y}'.format(startdate)

        params = {
            'object': 'getmytime.api.timeentrymanager',
            'method': 'fetchTimeEntries',
        }
        form_data = {
            'employeeid': employeeid,
            'startdate': startdate,
        }

        r = requests.post(self.URL, params=params, data=form_data,
                          cookies=self.cookies)

        if 'error' in r.text:
            raise GetMyTimeError(r.text)

        payload = r.json()

        jobs = self.lookups['jobs']
        tasks = self.lookups['tasks']

        def parse_lines():
            for row in payload['rows']:
                yield {
                    'id': row['intTimeEntryID'],
                    'billable': '$' if row['blnBillable'] == 'True' else ' ',
                    'approved': '*' if row['blnApproved'] == 'True' else ' ',
                    'job': jobs[row['intClientJobListID']],
                    'task': tasks[row['intTaskListID']],
                    'comments': row['strComments'].replace('\n', ' '),
                    'entry_date': datetime.strptime(row['dtmTimeWorkedDate'],
                                                    '%m/%d/%Y %I:%M:%S %p'),
                    'minutes': row['intMinutes'] + 'm',
                }

        lines = sorted(parse_lines(), key=lambda line: line['entry_date'])
        for line in lines:
            print(('{id}{approved} {billable} {entry_date:%Y-%m-%d} '
                   '{minutes:4} {job} ({task}) {comments}').format(**line))

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
            log.debug(r.text)


def main():
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(help='sub-command help')

    parser1 = subparsers.add_parser('ls')
    parser1.add_argument('--startdate')
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
            startdate = parse_date(args.startdate,
                                   default=datetime.now() - timedelta(days=7))
            api.ls(startdate)
        elif args.cmd == 'rm':
            api.rm(args.ids)

    except GetMyTimeError as ex:
        data = json.loads(ex.message)
        code, message = data['error']['code'], data['error']['message']
        print('{} {}'.format(code, message))
        sys.exit(1)


if __name__ == '__main__':
    main()
