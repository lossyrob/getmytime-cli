#!/usr/bin/env python
# -*- coding: utf-8 -*-
from __future__ import print_function
from __future__ import unicode_literals
from __future__ import division

import sys
import time
import logging
import requests
import itertools

from datetime import datetime, timedelta


log = logging.getLogger(__name__)
log.addHandler(logging.StreamHandler(sys.stderr))
log.setLevel(logging.DEBUG)


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

    def create(self, entries, **flags):
        yield 'Importing {} entries...'.format(len(entries))
        for entry in entries:
            record = {}
            record.update(entry)
            record.update(flags)
            self.create_time_entry(**record)
        yield 'Done'

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
            hrs, mins = self.format_minutes(minutes)
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

    def format_minutes(self, minutes):
        hours = minutes // 60
        minutes -= hours * 60
        return (str(hours) + 'h' if hours > 0 else '',
                str(minutes) + 'm' if minutes > 0 else '')

    def get_ls_tmpl(self, show_comments, oneline):
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

    def ls(self, entries, show_comments=False, oneline=False, custom_tmpl=None):
        if custom_tmpl:
            tmpl = custom_tmpl
        else:
            tmpl = self.get_ls_tmpl(show_comments, oneline)

        try:
            for entry in entries:
                yield tmpl.format(**entry)
        except KeyError as ex:
            log.error('Invalid template: Time entries do not have a "{}" field.'.format(ex.message))

    def ls_total(self, entries, args):
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
            hrs, mins = self.format_minutes(total)
            grand_total += total

            yield row_fmt.format(entry_date, entry_week, customer, hrs, mins)

        hrs, mins = self.format_minutes(grand_total)
        yield '{:}{:>3}'.format(hrs, mins)

    def rm(self, ids, dry_run=False):
        time.sleep(1)

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

        yield 'Deleted {} record(s)'.format(total)
