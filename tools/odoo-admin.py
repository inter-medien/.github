#!/usr/bin/env python3
"""Eng umrissenes Odoo-Admin-Skript für hansehelden.odoo.com.

Erlaubt NUR die zwei vom User freigegebenen Verwaltungs-Operationen:
  set-calendar-hours   Vertragsstunden eines Arbeitszeitkalenders setzen
  grant-self-attendance  User zur Gruppe "Self Attendance Edit" hinzufügen

Zugangsdaten kommen aus den Umgebungs-Secrets (ODOO_HANSEHELDEN_*).
"""
import argparse
import json
import os
import sys
import urllib.request

URL = os.environ['ODOO_HANSEHELDEN'].rstrip('/')
DB = 'hansehelden'
LOGIN = os.environ['ODOO_HANSEHELDEN_LOGIN']
KEY = os.environ['ODOO_HANSEHELDEN_KEY']

SELF_ATTENDANCE_GROUP_ID = 97  # "Attendances / Self Attendance Edit"


def rpc(service, method, args):
    payload = json.dumps({'jsonrpc': '2.0', 'method': 'call',
                          'params': {'service': service, 'method': method, 'args': args},
                          'id': 1}).encode()
    req = urllib.request.Request(URL + '/jsonrpc', data=payload,
                                 headers={'Content-Type': 'application/json'})
    r = json.load(urllib.request.urlopen(req, timeout=30))
    if 'error' in r:
        raise SystemExit('Odoo-Fehler: ' + json.dumps(r['error'].get('data', {}).get('message') or r['error'])[:300])
    return r['result']


def main():
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest='cmd', required=True)

    c1 = sub.add_parser('set-calendar-hours', help='full_time_required_hours eines resource.calendar setzen')
    c1.add_argument('--id', type=int, required=True)
    c1.add_argument('--hours', type=float, required=True)

    c2 = sub.add_parser('grant-self-attendance', help='res.users zur Gruppe Self Attendance Edit hinzufügen')
    c2.add_argument('--user-id', type=int, required=True)

    a = p.parse_args()
    uid = rpc('common', 'authenticate', [DB, LOGIN, KEY, {}])

    def kw(model, method, args, kwargs=None):
        return rpc('object', 'execute_kw', [DB, uid, KEY, model, method, args, kwargs or {}])

    if a.cmd == 'set-calendar-hours':
        before = kw('resource.calendar', 'read', [[a.id], ['name', 'full_time_required_hours']])
        kw('resource.calendar', 'write', [[a.id], {'full_time_required_hours': a.hours}])
        after = kw('resource.calendar', 'read', [[a.id], ['name', 'full_time_required_hours']])
        print('Vorher:', before)
        print('Nachher:', after)
    elif a.cmd == 'grant-self-attendance':
        kw('res.groups', 'write', [[SELF_ATTENDANCE_GROUP_ID], {'user_ids': [[4, a.user_id]]}])
        g = kw('res.groups', 'read', [[SELF_ATTENDANCE_GROUP_ID], ['full_name', 'all_user_ids']])
        print('Gruppe jetzt:', g)


if __name__ == '__main__':
    main()
