#!/usr/bin/env python
# -*- coding: utf-8 -*-
from __future__ import print_function
from __future__ import unicode_literals
from __future__ import division

import time
import logging
import requests

from datetime import datetime, timedelta


log = logging.getLogger(__name__)


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
        params = {
            'object': 'getmytime.api.usermanager',
            'method': 'login',
        }
        form_data = {
            'username': username,
            'password': password,
        }

        r = requests.post(self.URL, params=params, data=form_data)

        try:
            payload = r.json()
        except ValueError as ex:
            log.error('Error logging in. Is getmytime.com down?')
            raise GetMyTimeError(ex)

        if 'error' in payload:
            raise GetMyTimeError(payload)

        self.cookies = r.cookies
        self.fetch_lookups()
        self.detect_top_level_categories()

    def fetch_lookups(self):
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

        self.lookupById = {
            'tasks': unescape(
                {row['intTaskListID']: row['strTaskName']
                    for row in payload['serviceitems']['rows']}),
            'customers': unescape(
                {row['intClientJobListID']: row['strClientJobName']
                    for row in payload['customerjobs']['rows']}),
        }
        self.lookupByName = {
            'tasks': lowerCaseKeys(unescape(
                {row['strTaskName']: row['intTaskListID']
                    for row in payload['serviceitems']['rows']})),
            'customers': lowerCaseKeys(unescape(
                {row['strClientJobName']: row['intClientJobListID']
                    for row in payload['customerjobs']['rows']})),
        }

        time.sleep(1)

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
            time.sleep(1)

    def create_time_entry(self, startdate, enddate, customer, activity,
                          comments, tags, minutes, dry_run=False, force=False):
        minutes = int(minutes)
        employeeid = self.cookies['userid']

        customers = self.lookupByName['customers']
        try:
            customerid = customers[customer.lower()]
        except KeyError:
            raise InvalidTimeEntryError('Invalid customer "{}"'.format(customer))

        tasks = self.lookupByName['tasks']
        try:
            taskid = tasks[activity.lower()]
        except KeyError:
            raise InvalidTimeEntryError('Invalid activity "{}"'.format(activity))

        tags = tags if tags else []
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

        log.debug(form_data)
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

        if dry_run:
            return

        r = requests.post(self.URL, params=params, data=form_data,
                          cookies=self.cookies)

        payload = r.json()
        log.debug(payload)

        if 'error' in payload:
            raise GetMyTimeError(payload)

        time.sleep(1)

    def parse_entries(self, rows):
        customers = self.lookupById['customers']
        tasks = self.lookupById['tasks']
        for row in rows:
            minutes = int(row['intMinutes'])
            hours = minutes / 60.0

            hour_str, minute_str = format_minutes(minutes)

            customerId = row['intClientJobListID']
            taskId = row['intTaskListID']

            entry_date = datetime.strptime(row['dtmTimeWorkedDate'],
                                           '%m/%d/%Y %I:%M:%S %p')

            entry_week = entry_date - timedelta(days=entry_date.weekday())

            is_billable = row['blnBillable'] == 'True'
            is_approved = row['blnApproved'] == 'True'

            yield {
                'id': row['intTimeEntryID'],
                'is_billable': is_billable,
                'is_approved': is_approved,
                'billable': 'Yes' if is_billable else 'No ',
                'approved': 'Yes' if is_approved else 'No ',
                'billable_sym': '$' if is_billable else ' ',
                'approved_sym': '*' if is_approved else ' ',
                'customer': customers[customerId],
                'task': tasks[taskId],
                'comments': row['strComments'].replace('\n', ' '),
                'entry_date': entry_date,
                'entry_week': entry_week,
                'minutes': minutes,
                'minutes_str': minute_str,
                'hours': hours,
                'hours_str': hour_str,
            }

    def rm(self, ids, dry_run=False):
        for id in ids:
            self.delete_entry(id, dry_run=dry_run)

    def delete_entry(self, id, dry_run=False):
        log.info('Deleting {}'.format(id))

        if dry_run:
            return

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

        log.debug(r.text)
        time.sleep(1)
