#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Installer: Abrechnungs-Abgleich (Stunden vs. Abrechnung) in Odoo anlegen.

Legt per XML-RPC an (idempotent – mehrfaches Ausführen aktualisiert):
  - Modell x_abgleich "Abrechnungs-Abgleich" mit Feldern
  - Server-Action "HL: Abrechnungs-Abgleich berechnen" (letzte 3 Monate)
  - Listen-, Pivot- und Suchansicht (Ampel-Färbung, Gruppierung Monat/Kunde)
  - Menüpunkt "Abrechnungs-Abgleich" (unter Hauptmenü)
  - Täglichen Cron 05:30

Ausführen:  ODOO_HANSEHELDEN=https://hansehelden.odoo.com \
            ODOO_HANSEHELDEN_LOGIN=... ODOO_HANSEHELDEN_KEY=... \
            python3 odoo-abgleich-installer.py
"""
import json
import os
import urllib.request

URL = os.environ['ODOO_HANSEHELDEN'].rstrip('/')
DB = 'hansehelden'
LOGIN = os.environ['ODOO_HANSEHELDEN_LOGIN']
KEY = os.environ['ODOO_HANSEHELDEN_KEY']


def rpc(service, method, args):
    payload = json.dumps({'jsonrpc': '2.0', 'method': 'call',
                          'params': {'service': service, 'method': method, 'args': args},
                          'id': 1}).encode()
    req = urllib.request.Request(URL + '/jsonrpc', data=payload,
                                 headers={'Content-Type': 'application/json'})
    r = json.load(urllib.request.urlopen(req, timeout=60))
    if 'error' in r:
        raise SystemExit('Odoo-Fehler: ' + json.dumps(
            r['error'].get('data', {}).get('message') or r['error'], ensure_ascii=False)[:600])
    return r['result']


UID = rpc('common', 'authenticate', [DB, LOGIN, KEY, {}])


def kw(model, method, args, kwargs=None):
    return rpc('object', 'execute_kw', [DB, UID, KEY, model, method, args, kwargs or {}])


def upsert(model, domain, values):
    ids = kw(model, 'search', [domain], {'limit': 1})
    if ids:
        kw(model, 'write', [ids, values])
        return ids[0], 'aktualisiert'
    return kw(model, 'create', [values]), 'angelegt'


# ---------------------------------------------------------------- 1) Modell
model_id, how = upsert('ir.model', [['model', '=', 'x_abgleich']], {
    'name': 'Abrechnungs-Abgleich', 'model': 'x_abgleich', 'state': 'manual',
})
print(f'Modell x_abgleich {how} (id {model_id})')

FIELDS = [
    ('x_name',            'char',      'Bezeichnung', {}),
    ('x_monat_ym',        'char',      'Monat', {}),
    ('x_partner_id',      'many2one',  'Kunde', {'relation': 'res.partner'}),
    ('x_klasse',          'selection', 'Klasse', {'selection': "[('pk45b','§45b Pflegekasse'),('gewerbe','Gewerbe/Privat'),('vertrag','Vertragskunde'),('pruefen','Bitte prüfen')]"}),
    ('x_stunden',         'float',     'Stunden erfasst', {}),
    ('x_erwartet_eur',    'float',     'Erwartet € (56 €/h)', {}),
    ('x_gedeckt_eur',     'float',     'Gedeckt € (Rechnungen M..M+1)', {}),
    ('x_delta_eur',       'float',     'Delta €', {}),
    ('x_nachweis_stunden','float',     'Nachweis-Stunden', {}),
    ('x_nachweis_status', 'char',      'Nachweis-Status', {}),
    ('x_ampel',           'selection', 'Ampel', {'selection': "[('gruen','OK'),('gelb','Prüfen'),('rot','Lücke')]"}),
    ('x_hinweis',         'char',      'Hinweis', {}),
]
for name, ttype, label, extra in FIELDS:
    vals = {'model_id': model_id, 'name': name, 'ttype': ttype,
            'field_description': label, 'state': 'manual'}
    vals.update(extra)
    _, how = upsert('ir.model.fields', [['model_id', '=', model_id], ['name', '=', name]], vals)
    print(f'  Feld {name} {how}')

# ------------------------------------------------- 1b) Zugriffsrechte (ACL)
# Mit SKIP_ACL=1 überspringbar (z. B. wenn die Rechte manuell in der
# Oberfläche angelegt werden: Einstellungen → Technisch → Zugriffsrechte).
def xmlid(ref):
    mod, name = ref.split('.')
    d = kw('ir.model.data', 'search_read',
           [[['module', '=', mod], ['name', '=', name]]], {'fields': ['res_id'], 'limit': 1})
    return d[0]['res_id']


if os.environ.get('SKIP_ACL'):
    print('  ACL-Anlage übersprungen (SKIP_ACL gesetzt) – Rechte manuell anlegen!')
else:
    for acl_name, group_ref, perms in [
        ('access_x_abgleich_user', 'base.group_user',
         {'perm_read': True, 'perm_write': False, 'perm_create': False, 'perm_unlink': False}),
        ('access_x_abgleich_admin', 'base.group_system',
         {'perm_read': True, 'perm_write': True, 'perm_create': True, 'perm_unlink': True}),
    ]:
        vals = {'name': acl_name, 'model_id': model_id, 'group_id': xmlid(group_ref)}
        vals.update(perms)
        _, how = upsert('ir.model.access',
                        [['model_id', '=', model_id], ['name', '=', acl_name]], vals)
        print(f'  ACL {acl_name} {how}')

# -------------------------------------------- 2) Server-Action (Berechnung)
CODE = r'''
# Abrechnungs-Abgleich: letzte 3 Monate (inkl. laufendem) neu berechnen.
# Stundensatz Gewerbe/Privat: 56 EUR netto. Deckung = Rechnungen an den
# (kaufmännischen) Kunden mit Datum im Leistungsmonat M oder M+1.
# §45b-Patienten werden über Leistungsnachweise (x_pk_nachweis) geprüft,
# da deren Rechnung an die Pflegekasse geht.
SATZ = 56.0
today = datetime.date.today()
monate = []
y, m = today.year, today.month
for _ in range(3):
    monate.append((y, m))
    m -= 1
    if m == 0:
        m, y = 12, y - 1

pk_patienten = set(n['x_patient_id'][0] for n in env['x_pk_nachweis'].search_read(
    [('x_patient_id', '!=', False)], ['x_patient_id']))
mitarbeiter_partner = set(e.user_id.partner_id.id
    for e in env['hr.employee'].search([('user_id', '!=', False)]) if e.user_id.partner_id)

# Vertragskunden (Monatspauschale statt Stundenabrechnung) + aktive Abos
vertrag_roots = set()
for vp in env['res.partner'].search([('x_vertragskunde', '=', True)]):
    vertrag_roots.add(vp.commercial_partner_id.id if vp.commercial_partner_id else vp.id)
abo_pauschale = {}
for so in env['sale.order'].search([('subscription_state', '=', '3_progress')]):
    rp = so.partner_id.commercial_partner_id.id if so.partner_id else 0
    abo_pauschale[rp] = abo_pauschale.get(rp, 0.0) + (so.recurring_total or 0.0)

for (jahr, monat) in monate:
    start = datetime.date(jahr, monat, 1)
    ende = datetime.date(jahr + 1, 1, 1) if monat == 12 else datetime.date(jahr, monat + 1, 1)
    ym = '%04d-%02d' % (jahr, monat)
    inv_ende = datetime.date(jahr + (1 if monat >= 11 else 0), ((monat + 1) % 12) + 1, 1)

    env['x_abgleich'].search([('x_monat_ym', '=', ym)]).unlink()

    lines = env['account.analytic.line'].search([
        ('date', '>=', start), ('date', '<', ende), ('employee_id', '!=', False)])
    agg = {}
    for l in lines:
        pname = l.project_id.name or ''
        pl = pname.lower()
        # 'fahrtzeit' statt 'fahrt': Kundenprojekte wie "Logistikfahrten"
        # (ESB) sind abrechenbare Arbeit und gehoeren in den Abgleich.
        if 'intern' in pl or 'fahrtzeit' in pl:
            continue
        p = l.partner_id
        if not p and l.planning_slot_id:
            p = l.planning_slot_id.partner_id
        if not p and l.project_id:
            p = l.project_id.partner_id
        key = p.commercial_partner_id.id if p else 0
        agg.setdefault(key, {'stunden': 0.0, 'partner': p.commercial_partner_id if p else False})
        agg[key]['stunden'] += l.unit_amount or 0.0

    for key, a in agg.items():
        p = a['partner']
        std = round(a['stunden'], 2)
        vals = {'x_monat_ym': ym, 'x_stunden': std,
                'x_partner_id': p.id if p else False,
                'x_name': ym + u' · ' + (p.name if p else 'OHNE KUNDE')}
        if not p:
            vals.update({'x_klasse': 'pruefen', 'x_ampel': 'rot',
                         'x_hinweis': 'Zeiterfassung ohne Kundenzuordnung'})
        elif p.id in mitarbeiter_partner:
            vals.update({'x_klasse': 'pruefen', 'x_ampel': 'rot',
                         'x_hinweis': 'Zeit auf Mitarbeiter statt Kunde gebucht'})
        elif p.id in pk_patienten or any(c.id in pk_patienten for c in p.child_ids):
            pids = [p.id] + [c.id for c in p.child_ids]
            nws = env['x_pk_nachweis'].search([
                ('x_patient_id', 'in', pids), ('x_monat', '=', str(monat)), ('x_jahr', '=', str(jahr))])
            nw_std = sum(n.x_summe_stunden or 0.0 for n in nws)
            states = set(n.x_state for n in nws)
            vals.update({'x_klasse': 'pk45b', 'x_nachweis_stunden': round(nw_std, 2),
                         'x_nachweis_status': ', '.join(sorted(states)) or 'KEIN NACHWEIS'})
            if not nws:
                vals.update({'x_ampel': 'rot', 'x_hinweis': 'Kein Leistungsnachweis zum Monat'})
            elif std > nw_std + 0.26:
                vals.update({'x_ampel': 'rot', 'x_hinweis':
                             '%.2f h erfasst, nur %.2f h im Nachweis' % (std, nw_std)})
            elif states & {'draft', 'wait_sig'}:
                vals.update({'x_ampel': 'gelb', 'x_hinweis': 'Nachweis noch nicht unterschrieben'})
            elif not (states & {'eingereicht', 'invoiced'}):
                vals.update({'x_ampel': 'gelb', 'x_hinweis': 'Unterschrieben, aber noch nicht eingereicht'})
            else:
                vals.update({'x_ampel': 'gruen', 'x_hinweis': 'Nachweis eingereicht/abgerechnet'})
        elif p.id in vertrag_roots:
            # Vertragskunde: Massstab ist die Monats-Pauschale (aktives Abo),
            # nicht Stunden x Satz. Fehlt die Monatsrechnung, ist das ein
            # klassischer Durchrutscher -> rot.
            pausch = round(abo_pauschale.get(p.id, 0.0), 2)
            invs = env['account.move'].search([
                ('move_type', '=', 'out_invoice'), ('state', '=', 'posted'),
                ('partner_id', 'child_of', p.id),
                ('invoice_date', '>=', start), ('invoice_date', '<', ende)])
            gedeckt = round(sum(i.amount_untaxed_signed for i in invs), 2)
            vals.update({'x_klasse': 'vertrag', 'x_erwartet_eur': pausch,
                         'x_gedeckt_eur': gedeckt,
                         'x_delta_eur': round(gedeckt - pausch, 2)})
            laufend = ende > today
            if pausch <= 0:
                vals.update({'x_ampel': 'rot',
                             'x_hinweis': 'Vertragskunde OHNE aktives Abo (%.2f h erfasst) - Pauschale pruefen!' % std})
            elif gedeckt <= 0:
                vals.update({'x_ampel': 'gelb' if laufend else 'rot',
                             'x_hinweis': 'Vertragsrechnung fehlt (Pauschale %.2f EUR/Monat)' % pausch
                                          + (' (Monat laeuft noch)' if laufend else '')})
            elif gedeckt < pausch * 0.99:
                vals.update({'x_ampel': 'gelb',
                             'x_hinweis': 'Rechnung %.2f EUR unter Pauschale %.2f EUR' % (gedeckt, pausch)})
            else:
                vals.update({'x_ampel': 'gruen', 'x_hinweis': 'Vertrag fakturiert (%.2f h geleistet)' % std})
        else:
            erwartet = round(std * SATZ, 2)
            invs = env['account.move'].search([
                ('move_type', '=', 'out_invoice'), ('state', '=', 'posted'),
                ('partner_id', 'child_of', p.id),
                ('invoice_date', '>=', start), ('invoice_date', '<', inv_ende)])
            gedeckt = round(sum(i.amount_untaxed_signed for i in invs), 2)
            vals.update({'x_klasse': 'gewerbe', 'x_erwartet_eur': erwartet,
                         'x_gedeckt_eur': gedeckt,
                         'x_delta_eur': round(gedeckt - erwartet, 2)})
            laufend = ende > today
            if gedeckt <= 0:
                vals.update({'x_ampel': 'gelb' if laufend else 'rot',
                             'x_hinweis': 'Keine Rechnung in M/M+1' + (' (Monat läuft noch)' if laufend else '')})
            elif gedeckt < erwartet * 0.8:
                vals.update({'x_ampel': 'gelb',
                             'x_hinweis': 'Rechnungen decken nur %.0f%% der Erwartung' % (100.0 * gedeckt / erwartet)})
            else:
                vals.update({'x_ampel': 'gruen', 'x_hinweis': 'Gedeckt'})
        env['x_abgleich'].create(vals)
'''

act_vals = {'name': 'HL: Abrechnungs-Abgleich berechnen', 'model_id': model_id,
            'state': 'code', 'code': CODE, 'binding_model_id': model_id,
            'binding_type': 'action'}
action_id, how = upsert('ir.actions.server',
                        [['name', '=', 'HL: Abrechnungs-Abgleich berechnen']], act_vals)
print(f'Server-Action {how} (id {action_id})')

# ---------------------------------------------------------------- 3) Views
LIST = ('<list decoration-success="x_ampel==\'gruen\'" decoration-warning="x_ampel==\'gelb\'" '
        'decoration-danger="x_ampel==\'rot\'" default_order="x_monat_ym desc, x_ampel desc">'
        '<field name="x_monat_ym"/><field name="x_partner_id"/><field name="x_klasse"/>'
        '<field name="x_stunden" sum="Summe"/><field name="x_erwartet_eur" sum="Summe"/>'
        '<field name="x_gedeckt_eur" sum="Summe"/><field name="x_delta_eur" sum="Summe"/>'
        '<field name="x_nachweis_stunden"/><field name="x_nachweis_status"/>'
        '<field name="x_ampel"/><field name="x_hinweis"/></list>')
SEARCH = ('<search><field name="x_partner_id"/><field name="x_monat_ym"/>'
          '<filter name="rot" string="Lücken (rot)" domain="[(\'x_ampel\',\'=\',\'rot\')]"/>'
          '<filter name="gelb" string="Prüfen (gelb)" domain="[(\'x_ampel\',\'=\',\'gelb\')]"/>'
          '<group>'
          '<filter name="g_monat" string="Monat" context="{\'group_by\':\'x_monat_ym\'}"/>'
          '<filter name="g_kunde" string="Kunde" context="{\'group_by\':\'x_partner_id\'}"/>'
          '<filter name="g_ampel" string="Ampel" context="{\'group_by\':\'x_ampel\'}"/>'
          '</group></search>')
PIVOT = ('<pivot><field name="x_monat_ym" type="col"/><field name="x_partner_id" type="row"/>'
         '<field name="x_stunden" type="measure"/><field name="x_delta_eur" type="measure"/></pivot>')
for vtype, arch in [('list', LIST), ('search', SEARCH), ('pivot', PIVOT)]:
    _, how = upsert('ir.ui.view',
                    [['model', '=', 'x_abgleich'], ['type', '=', vtype], ['name', '=', 'x_abgleich_' + vtype]],
                    {'name': 'x_abgleich_' + vtype, 'model': 'x_abgleich', 'type': vtype, 'arch_base': arch})
    print(f'View {vtype} {how}')

win_id, how = upsert('ir.actions.act_window', [['res_model', '=', 'x_abgleich']], {
    'name': 'Abrechnungs-Abgleich', 'res_model': 'x_abgleich',
    'view_mode': 'list,pivot', 'context': "{'search_default_g_monat': 1}"})
print(f'Fenster-Aktion {how} (id {win_id})')

menu_id, how = upsert('ir.ui.menu', [['name', '=', 'Abrechnungs-Abgleich']], {
    'name': 'Abrechnungs-Abgleich', 'action': 'ir.actions.act_window,%d' % win_id})
print(f'Menüpunkt {how} (id {menu_id})')

# ---------------------------------------------------------------- 4) Cron
cron_vals = {'name': 'HL: Abrechnungs-Abgleich (täglich)', 'model_id': model_id,
             'state': 'code', 'code': 'env["ir.actions.server"].browse(%d).run()' % action_id,
             'interval_number': 1, 'interval_type': 'days', 'active': True}
cron_id, how = upsert('ir.cron', [['name', '=', 'HL: Abrechnungs-Abgleich (täglich)']], cron_vals)
print(f'Cron {how}')

# ---------------------------------------------------------------- 5) Erster Lauf
# ir.actions.server.run() per RPC scheitert an Rechten – der Cron-Trigger
# (identisch zum Button "Manuell ausführen") funktioniert. Ohne Zugriffs-
# rechte (ACL) schlägt die Berechnung fehl – dann zuerst Rechte anlegen
# und den Cron erneut manuell ausführen.
print('Starte erste Berechnung über den Cron ...')
try:
    kw('ir.cron', 'method_direct_trigger', [[cron_id]])
    n = kw('x_abgleich', 'search_count', [[]])
    rot = kw('x_abgleich', 'search_count', [[['x_ampel', '=', 'rot']]])
    print(f'Fertig: {n} Abgleich-Zeilen berechnet, davon {rot} rote Lücken.')
    print('In Odoo: Hauptmenü -> "Abrechnungs-Abgleich" (ggf. Browser neu laden).')
except SystemExit as e:
    print(f'Erster Lauf noch nicht möglich: {e}')
    print('Vermutlich fehlen die Zugriffsrechte (ir.model.access) für x_abgleich.')
    print('Rechte anlegen, dann Cron "HL: Abrechnungs-Abgleich (täglich)" manuell ausführen.')
