#!/usr/bin/env python
# -*- coding: utf-8 -*-
from __future__ import print_function
from __future__ import unicode_literals
from __future__ import division

import sys
import time
import logging
import requests

from datetime import datetime, timedelta


log = logging.getLogger(__name__)
log.addHandler(logging.StreamHandler(sys.stderr))
log.setLevel(logging.DEBUG)


def format_minutes(minutes):
    hours = minutes // 60
    minutes -= hours * 60
    return (str(hours) + 'h' if hours > 0 else '',
            str(minutes) + 'm' if minutes > 0 else '')


def lowerCaseKeys(d):
    return dict((k.lower(), v) for k, v in d.iteritems())


def unescape(d):
    return dict((k.replace('&amp;', '&'),
                 v.replace('&amp;', '&')) for k, v in d.iteritems())


class GetMyTimeError(Exception):
    pass


class InvalidTimeEntryError(Exception):
    pass


class GetMyTimeAPI(object):
    URL = 'https://app.getmytime.com/service.aspx'

    def login(self, username, password):
        time.sleep(1)

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
        self.detect_top_level_categories()

    def fetch_lookups(self):
        time.sleep(1)

        params = {
            'object': 'getmytime.api.managemanager',
            'method': 'fetchLookups',
        }
        form_data = {
            'lookups': '[customerjobs],[serviceitems]',
        }

        r = requests.post(self.URL, params=params, data=form_data,
                          cookies=self.cookies)

        payload = r.json()
        self.lookups = payload

        lookup = lambda k, a, b: dict((row[a], row[b])
                                      for row in payload[k]['rows'])

        self.lookupById = {
            'tasks': unescape(lookup('serviceitems',
                                     'intTaskListID',
                                     'strTaskName')),
            'customers': unescape(lookup('customerjobs',
                                         'intClientJobListID',
                                         'strClientJobName')),
        }
        self.lookupByName = {
            'tasks': lowerCaseKeys(unescape(lookup('serviceitems',
                                                   'strTaskName',
                                                   'intTaskListID'))),
            'customers': lowerCaseKeys(unescape(lookup('customerjobs',
                                                       'strClientJobName',
                                                       'intClientJobListID'))),
        }

    def detect_top_level_categories(self):
        tasks = self.lookupById['tasks'].values()
        customers = self.lookupById['customers'].values()
        self.topLevelCategories = {
            'tasks': set(parts[0].lower() for parts in
                         (name.split(':') for name in tasks)
                         if len(parts) > 1),
            'customers': set(parts[0].lower() for parts in
                             (name.split(':') for name in customers)
                             if len(parts) > 1),
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
                break

            by_date = lambda entry: entry['entry_date']
            entries = self.parse_entries(rows)
            entries = sorted(entries, key=by_date)

            for entry in entries:
                if entry['entry_date'] < end_date:
                    yield entry

            curdate += timedelta(days=7)

    def create_time_entry(self, startdate, enddate, customer, activity,
                          comments, tags, minutes, dry_run=False, force=False):
        customers = self.lookupByName['customers']
        tasks = self.lookupByName['tasks']

        tags = tags if tags else []

        employeeid = self.cookies['userid']
        customerid = customers[customer.lower()]
        taskid = tasks[activity.lower()]
        billable = 'billable' in tags

        params = {
            'object': 'getmytime.api.timeentrymanager',
            'method': 'createTimeEntry',
        }
        form_data = {
            'employeeid': employeeid,
            'startdate': startdate,
            'startdatetime': startdate,
            'minutes': minutes,
            'customerid': customerid,
            'taskid': taskid,
            'comments': comments,
            'billable': billable,
            'projectid': 139,  # Basic
            'classid': 0,
            'starttimer': 'false',
        }

        log.info('Submitting {} {} {}; Notes: {}'.format(
            startdate, customer, activity, comments))

        if len(comments.strip()) == 0:
            raise InvalidTimeEntryError('Comments field may not be empty')

        if activity.lower() in self.topLevelCategories['tasks']:
            raise InvalidTimeEntryError('Not allowed to use top level '
                                        'category "{}"'.format(activity))

        if customer.lower() in self.topLevelCategories['customers']:
            raise InvalidTimeEntryError('Not allowed to use top level '
                                        'category "{}"'.format(customer))

        if (not force and
                activity.lower() == 'Indirect - Admin:Miscellaneous'.lower()):
            raise InvalidTimeEntryError('Never use "Indirect - Admin:Miscellaenous"!'
                                        ' (Use `--force` to override this rule)')

        if (not force and
                ('interview' in comments or 'presentation' in comments) and
                'hiring' not in activity.lower()):
            raise InvalidTimeEntryError('Consider using "Indirect - Admin:Personnel/Hiring" for this entry.'
                                        ' (Use `--force` to override this rule)')

        if not dry_run:
            r = requests.post(self.URL, params=params, data=form_data,
                              cookies=self.cookies)

            payload = r.json()

            if 'error' in payload:
                raise GetMyTimeError(payload)

            time.sleep(1)

    def parse_entries(self, rows):
        customers = self.lookupById['customers']
        tasks = self.lookupById['tasks']
        for row in rows:
            minutes = int(row['intMinutes'])
            hrs, mins = format_minutes(minutes)
            customerId = row['intClientJobListID']
            taskId = row['intTaskListID']

            entry_date = datetime.strptime(row['dtmTimeWorkedDate'],
                                           '%m/%d/%Y %I:%M:%S %p')

            entry_week = entry_date - timedelta(days=entry_date.weekday())

            yield {
                'id': row['intTimeEntryID'],
                'billable': 'Yes' if row['blnBillable'] == 'True' else 'No ',
                'approved': 'Yes' if row['blnApproved'] == 'True' else 'No ',
                'billable_sym': '$' if row['blnBillable'] == 'True' else ' ',
                'approved_sym': '*' if row['blnApproved'] == 'True' else ' ',
                'customer': customers[customerId],
                'task': tasks[taskId],
                'comments': row['strComments'].replace('\n', ' '),
                'entry_date': entry_date,
                'entry_week': entry_week,
                'minutes': minutes,
                'minutes_str': mins,
                'hours_str': hrs,
            }

    def rm(self, ids, dry_run=False):
        for id in ids:
            log.debug('Deleting {}'.format(id))

            if dry_run:
                continue

            time.sleep(1)

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
