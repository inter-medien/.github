#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Installer: Täglicher Umsatz-Report (Plan / Ist / Abrechenbar) in Odoo anlegen.

Legt per JSON-RPC an (idempotent – mehrfaches Ausführen aktualisiert):
  - Modell x_umsatzreport "Umsatz-Report" mit Feldern
  - Server-Action "HL: Umsatz-Report berechnen" (aktueller Monat je Woche,
    Monats-Prognose, Vormonat "noch abzurechnen")
  - Listen-, Pivot-, Graph- und Suchansicht
  - Menüpunkt "Umsatz-Report"
  - Täglichen Cron ~05:30 (04:30 UTC) inkl. Mail an Zeidler + Kremer

Fachliche Regeln:
  - §45b: 43 €/h bis 31.12.2026, 53 €/h ab 01.01.2027
    (Slots mit gesetztem x_umsatz werden übernommen; 2027er-Slots, deren
    x_umsatz noch mit 43 €/h gerechnet wurde, werden auf 53 €/h umgerechnet)
  - Übrige Leistungen: 56 €/h, wo kein x_umsatz am Slot steht
  - Kostenfreie Erstgespräche (x_ist_erstgespraech) fließen nicht ein
  - Urlaubs-Platzhalter-Slots (x_hr_leave_id) fließen nicht ein
  - Genehmigte Abwesenheiten (hr.leave, Urlaub/Krankheit) werden je Woche
    ausgewiesen und mindern die Prognose (kollidierende geplante Slots)
  - Prognose = bereits abrechenbar + geplante Slots x Realisierungsquote
    (Quote aus den letzten 3 Monaten, begrenzt auf 60–100 %)
  - Vormonat: Summe aller Slots mit Status "abrechenbar (offen)" als
    Abrechnungs-To-do (ihr rechnet ab dem 1. den Vormonat ab)

Ausführen:  ODOO_HANSEHELDEN=https://hansehelden.odoo.com \
            ODOO_HANSEHELDEN_LOGIN=... ODOO_HANSEHELDEN_KEY=... \
            python3 odoo-umsatzreport-installer.py
"""
import datetime
import json
import os
import urllib.request

URL = os.environ['ODOO_HANSEHELDEN'].rstrip('/')
DB = 'hansehelden'
LOGIN = os.environ['ODOO_HANSEHELDEN_LOGIN']
KEY = os.environ['ODOO_HANSEHELDEN_KEY']

MAIL_AN = 'zeidler@hansehelden.de,kremer@hansehelden.de'


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
model_id, how = upsert('ir.model', [['model', '=', 'x_umsatzreport']], {
    'name': 'Umsatz-Report', 'model': 'x_umsatzreport', 'state': 'manual',
})
print(f'Modell x_umsatzreport {how} (id {model_id})')

FIELDS = [
    ('x_name',             'char',      'Zeile', {}),
    ('x_monat_ym',         'char',      'Monat', {}),
    ('x_typ',              'selection', 'Typ', {'selection': "[('vormonat','Vormonat offen'),('woche','Woche'),('prognose','Monats-Prognose')]"}),
    ('x_klasse',           'selection', 'Klasse', {'selection': "[('pk45b','§45b'),('uebrige','Übrige Leistungen'),('gesamt','Gesamt')]"}),
    ('x_sortier',          'integer',   'Sortierung', {}),
    ('x_plan_h',           'float',     'Plan h', {}),
    ('x_ist_h',            'float',     'Ist h (Zeiterfassung)', {}),
    ('x_abrechenbar_h',    'float',     'Abrechenbar h', {}),
    ('x_plan_eur',         'float',     'Plan €', {}),
    ('x_abrechenbar_eur',  'float',     'Abrechenbar €', {}),
    ('x_prognose_eur',     'float',     'Prognose €', {}),
    ('x_abw_h',            'float',     'Abwesenheit h', {}),
    ('x_ampel',            'selection', 'Ampel', {'selection': "[('gruen','OK'),('gelb','Prüfen'),('rot','Lücke')]"}),
    ('x_hinweis',          'char',      'Hinweis', {}),
]
for name, ttype, label, extra in FIELDS:
    vals = {'model_id': model_id, 'name': name, 'ttype': ttype,
            'field_description': label, 'state': 'manual'}
    vals.update(extra)
    _, how = upsert('ir.model.fields', [['model_id', '=', model_id], ['name', '=', name]], vals)
    print(f'  Feld {name} {how}')

# -------------------------------------------- 2) Server-Action (Berechnung)
CODE = r'''
# Umsatz-Report: aktueller Monat je Woche + Prognose + Vormonat offen.
# Saetze: §45b 43 EUR/h bis 31.12.2026, 53 EUR/h ab 01.01.2027; Uebrige 56 EUR/h.
# Erstgespraeche und Urlaubs-Platzhalter-Slots fliessen nicht ein.
heute = datetime.date.today()
jahr, monat = heute.year, heute.month
m_start = datetime.date(jahr, monat, 1)
m_ende = datetime.date(jahr + 1, 1, 1) if monat == 12 else datetime.date(jahr, monat + 1, 1)
ym = '%04d-%02d' % (jahr, monat)
vj, vm = (jahr - 1, 12) if monat == 1 else (jahr, monat - 1)
v_start = datetime.date(vj, vm, 1)
vym = '%04d-%02d' % (vj, vm)

pk_pat = set(n['x_patient_id'][0] for n in env['x_pk_nachweis'].search_read(
    [('x_patient_id', '!=', False)], ['x_patient_id']))

env['x_umsatzreport'].search([]).unlink()

# --- Wochen des Monats (Mo-So, auf den Monat geschnitten)
wochen = []
d = m_start
while d < m_ende:
    wd = d - datetime.timedelta(days=d.weekday())
    we = wd + datetime.timedelta(days=6)
    ws = d
    wend = we if we < m_ende else (m_ende - datetime.timedelta(days=1))
    wochen.append((d.isocalendar()[1], ws, wend))
    d = we + datetime.timedelta(days=1)

# --- Abwesenheiten (genehmigt + zur Genehmigung): Stunden je Woche, Tage je Mitarbeiter
leaves = env['hr.leave'].search([('state', 'in', ['validate', 'confirm']),
                                 ('date_from', '<', str(m_ende)), ('date_to', '>=', str(m_start))])
ABW = {}
leave_tage = set()
for lv in leaves:
    lf = lv.date_from.date()
    lt = lv.date_to.date()
    tot_wd = 0
    dd = lf
    while dd <= lt:
        if dd.weekday() < 5:
            tot_wd += 1
        dd += datetime.timedelta(days=1)
    std = lv.number_of_hours or (lv.number_of_days or 0.0) * 8.0
    for (kwnr, ws, wend) in wochen:
        os_ = lf if lf > ws else ws
        oe = lt if lt < wend else wend
        if os_ > oe:
            continue
        n = 0
        dd = os_
        while dd <= oe:
            if dd.weekday() < 5:
                n += 1
            if lv.employee_id:
                leave_tage.add((lv.employee_id.id, dd))
            dd += datetime.timedelta(days=1)
        if tot_wd:
            ABW[kwnr] = ABW.get(kwnr, 0.0) + std * n / tot_wd

# --- Realisierungsquote aus den letzten 3 Monaten
q_start = v_start
for schritt in range(2):
    q_start = datetime.date(q_start.year - 1, 12, 1) if q_start.month == 1 else datetime.date(q_start.year, q_start.month - 1, 1)
h_plan = 0.0
h_real = 0.0
for s in env['planning.slot'].search([('start_datetime', '>=', str(q_start)),
                                      ('start_datetime', '<', str(m_start))]):
    if s.x_ist_erstgespraech or s.x_hr_leave_id:
        continue
    st = s.x_umsatz_status or 'geplant'
    if st == 'nicht_abrechenbar':
        continue
    d = s.start_datetime.date()
    kl_pk = bool(s.partner_id and s.partner_id.id in pk_pat)
    satz = (43.0 if d < datetime.date(2027, 1, 1) else 53.0) if kl_pk else 56.0
    eur = s.x_umsatz or ((s.allocated_hours or 0.0) * satz)
    h_plan += eur
    if st in ('offen', 'abgerechnet'):
        h_real += eur
quote = (h_real / h_plan) if h_plan > 0 else 0.9
if quote < 0.6:
    quote = 0.6
if quote > 1.0:
    quote = 1.0

# --- Slots des aktuellen Monats
W = {}
PROG = {'pk45b': {'abr': 0.0, 'plan': 0.0, 'zukunft': 0.0, 'entfall': 0.0},
        'uebrige': {'abr': 0.0, 'plan': 0.0, 'zukunft': 0.0, 'entfall': 0.0}}
for s in env['planning.slot'].search([('start_datetime', '>=', str(m_start)),
                                      ('start_datetime', '<', str(m_ende))]):
    if s.x_ist_erstgespraech or s.x_hr_leave_id:
        continue
    d = s.start_datetime.date()
    kl = 'pk45b' if (s.partner_id and s.partner_id.id in pk_pat) else 'uebrige'
    satz = (43.0 if d < datetime.date(2027, 1, 1) else 53.0) if kl == 'pk45b' else 56.0
    h = s.allocated_hours or 0.0
    eur = s.x_umsatz or (h * satz)
    # 2027er-§45b-Slots, deren x_umsatz noch mit 43 EUR/h gerechnet wurde, umrechnen
    if kl == 'pk45b' and d >= datetime.date(2027, 1, 1) and s.x_umsatz and abs(s.x_umsatz - h * 43.0) < 0.05:
        eur = h * 53.0
    st = s.x_umsatz_status or 'geplant'
    kwnr = None
    for (k, ws, wend) in wochen:
        if ws <= d <= wend:
            kwnr = k
            break
    key = (kwnr, kl)
    w = W.setdefault(key, {'plan_h': 0.0, 'plan_eur': 0.0, 'abr_h': 0.0, 'abr_eur': 0.0, 'ist_h': 0.0})
    w['plan_h'] += h
    if st != 'nicht_abrechenbar':
        w['plan_eur'] += eur
        PROG[kl]['plan'] += eur
        if st in ('offen', 'abgerechnet'):
            w['abr_h'] += h
            w['abr_eur'] += eur
            PROG[kl]['abr'] += eur
        elif st == 'geplant':
            kollidiert = False
            for e in s.employee_ids:
                if (e.id, d) in leave_tage:
                    kollidiert = True
                    break
            if kollidiert:
                PROG[kl]['entfall'] += eur
            else:
                PROG[kl]['zukunft'] += eur

# --- Zeiterfassung des aktuellen Monats
for l in env['account.analytic.line'].search([('date', '>=', str(m_start)),
                                              ('date', '<', str(m_ende)),
                                              ('employee_id', '!=', False)]):
    pn = (l.project_id.name or '').lower()
    if 'intern' in pn or 'fahrt' in pn:
        continue
    if l.planning_slot_id and l.planning_slot_id.x_ist_erstgespraech:
        continue
    p = l.partner_id
    if not p and l.planning_slot_id:
        p = l.planning_slot_id.partner_id
    if not p and l.project_id:
        p = l.project_id.partner_id
    kl = 'pk45b' if (p and p.id in pk_pat) else 'uebrige'
    d = l.date
    kwnr = None
    for (k, ws, wend) in wochen:
        if ws <= d <= wend:
            kwnr = k
            break
    key = (kwnr, kl)
    w = W.setdefault(key, {'plan_h': 0.0, 'plan_eur': 0.0, 'abr_h': 0.0, 'abr_eur': 0.0, 'ist_h': 0.0})
    w['ist_h'] += l.unit_amount or 0.0

# --- Vormonat: noch abzurechnen (Status offen)
V = {'pk45b': 0.0, 'uebrige': 0.0}
for s in env['planning.slot'].search([('start_datetime', '>=', str(v_start)),
                                      ('start_datetime', '<', str(m_start)),
                                      ('x_umsatz_status', '=', 'offen')]):
    if s.x_ist_erstgespraech or s.x_hr_leave_id:
        continue
    d = s.start_datetime.date()
    kl = 'pk45b' if (s.partner_id and s.partner_id.id in pk_pat) else 'uebrige'
    satz = (43.0 if d < datetime.date(2027, 1, 1) else 53.0) if kl == 'pk45b' else 56.0
    V[kl] += s.x_umsatz or ((s.allocated_hours or 0.0) * satz)

# ================================================================ Zeilen
KL_NAME = {'pk45b': '§45b', 'uebrige': 'Übrige Leistungen', 'gesamt': 'Gesamt'}
rows = []

# Vormonat (oben)
v_sum = V['pk45b'] + V['uebrige']
for i, kl in enumerate(['pk45b', 'uebrige', 'gesamt']):
    betrag = v_sum if kl == 'gesamt' else V[kl]
    rows.append({
        'x_name': 'Vormonat %s · noch abzurechnen · %s' % (vym, KL_NAME[kl]),
        'x_monat_ym': vym, 'x_typ': 'vormonat', 'x_klasse': kl, 'x_sortier': i,
        'x_abrechenbar_eur': round(betrag, 2),
        'x_ampel': 'gelb' if betrag > 0.005 else 'gruen',
        'x_hinweis': 'Slots mit Status "abrechenbar (offen)" – jetzt Rechnungen stellen' if betrag > 0.005 else 'Alles abgerechnet',
    })

# Wochen
sortnr = 100
mail_wochen = []
for (kwnr, ws, wend) in wochen:
    g = {'plan_h': 0.0, 'plan_eur': 0.0, 'abr_h': 0.0, 'abr_eur': 0.0, 'ist_h': 0.0}
    label = 'KW%02d (%s–%s)' % (kwnr, ws.strftime('%d.%m.'), wend.strftime('%d.%m.'))
    for kl in ['pk45b', 'uebrige']:
        w = W.get((kwnr, kl), {'plan_h': 0.0, 'plan_eur': 0.0, 'abr_h': 0.0, 'abr_eur': 0.0, 'ist_h': 0.0})
        for f in g:
            g[f] += w[f]
        vorbei = wend < heute
        ampel = 'gruen'
        hinweis = ''
        if vorbei and w['plan_h'] > 0.1:
            if w['ist_h'] < w['plan_h'] * 0.8:
                ampel = 'rot'
                hinweis = 'Ist deutlich unter Plan – Zeiten pruefen'
            elif w['ist_h'] < w['plan_h'] * 0.95:
                ampel = 'gelb'
                hinweis = 'Ist leicht unter Plan'
        rows.append({
            'x_name': label + ' · ' + KL_NAME[kl],
            'x_monat_ym': ym, 'x_typ': 'woche', 'x_klasse': kl, 'x_sortier': sortnr,
            'x_plan_h': round(w['plan_h'], 2), 'x_ist_h': round(w['ist_h'], 2),
            'x_abrechenbar_h': round(w['abr_h'], 2),
            'x_plan_eur': round(w['plan_eur'], 2), 'x_abrechenbar_eur': round(w['abr_eur'], 2),
            'x_ampel': ampel, 'x_hinweis': hinweis,
        })
        sortnr += 1
    abw = ABW.get(kwnr, 0.0)
    rows.append({
        'x_name': label + ' · Gesamt',
        'x_monat_ym': ym, 'x_typ': 'woche', 'x_klasse': 'gesamt', 'x_sortier': sortnr,
        'x_plan_h': round(g['plan_h'], 2), 'x_ist_h': round(g['ist_h'], 2),
        'x_abrechenbar_h': round(g['abr_h'], 2),
        'x_plan_eur': round(g['plan_eur'], 2), 'x_abrechenbar_eur': round(g['abr_eur'], 2),
        'x_abw_h': round(abw, 2),
        'x_ampel': 'gruen', 'x_hinweis': ('inkl. %.1f h Abwesenheit' % abw) if abw else '',
    })
    sortnr += 1
    mail_wochen.append((label, g, abw))

# Monats-Prognose
prog_sum = 0.0
plan_sum = 0.0
abr_sum = 0.0
for i, kl in enumerate(['pk45b', 'uebrige']):
    pr = PROG[kl]
    prognose = pr['abr'] + pr['zukunft'] * quote
    prog_sum += prognose
    plan_sum += pr['plan']
    abr_sum += pr['abr']
    hinw = 'Quote %.0f%%; %.0f € entfallen durch Abwesenheit' % (quote * 100.0, pr['entfall']) if pr['entfall'] > 0.005 else 'Realisierungsquote %.0f%% (letzte 3 Monate)' % (quote * 100.0)
    if kl == 'pk45b':
        hinw += ' · Satz: 43 €/h bis 31.12.26, 53 €/h ab 01.01.27'
    rows.append({
        'x_name': 'Prognose %s · %s' % (ym, KL_NAME[kl]),
        'x_monat_ym': ym, 'x_typ': 'prognose', 'x_klasse': kl, 'x_sortier': 900 + i,
        'x_plan_eur': round(pr['plan'], 2), 'x_abrechenbar_eur': round(pr['abr'], 2),
        'x_prognose_eur': round(prognose, 2),
        'x_ampel': 'gruen' if prognose >= pr['plan'] * 0.9 else 'gelb',
        'x_hinweis': hinw,
    })
rows.append({
    'x_name': 'Prognose %s · Gesamt' % ym,
    'x_monat_ym': ym, 'x_typ': 'prognose', 'x_klasse': 'gesamt', 'x_sortier': 902,
    'x_plan_eur': round(plan_sum, 2), 'x_abrechenbar_eur': round(abr_sum, 2),
    'x_prognose_eur': round(prog_sum, 2),
    'x_ampel': 'gruen' if prog_sum >= plan_sum * 0.9 else 'gelb',
    'x_hinweis': 'Erwarteter Monatsumsatz (ohne Erstgespraeche, inkl. Abwesenheiten)',
})
for r in rows:
    env['x_umsatzreport'].create(r)

# ================================================================ Mail
if env.context.get('umsatzreport_mail'):
    try:
        zeilen = ''
        for (label, g, abw) in mail_wochen:
            zeilen += ('<tr><td style="padding:2px 8px;">%s</td>'
                       '<td style="padding:2px 8px;text-align:right;">%.1f h</td>'
                       '<td style="padding:2px 8px;text-align:right;">%.1f h</td>'
                       '<td style="padding:2px 8px;text-align:right;">%.2f €</td>'
                       '<td style="padding:2px 8px;text-align:right;">%.2f €</td>'
                       '<td style="padding:2px 8px;text-align:right;">%.1f h</td></tr>'
                       % (label, g['plan_h'], g['ist_h'], g['plan_eur'], g['abr_eur'], abw))
        body = (
            '<div style="font-family:sans-serif;font-size:13px;">'
            '<h2 style="margin:0 0 6px;">Umsatz-Report %s</h2>'
            '<p style="margin:0 0 10px;color:#666;">Stand %s · §45b vs. Übrige · ohne Erstgespräche</p>'
            '<p style="margin:0 0 10px;"><b>Vormonat %s noch abzurechnen: %.2f €</b> (§45b %.2f € · Übrige %.2f €)</p>'
            '<table style="border-collapse:collapse;font-size:13px;" border="1" cellspacing="0">'
            '<tr style="background:#1f3a5f;color:#fff;"><th style="padding:3px 8px;">Woche</th>'
            '<th style="padding:3px 8px;">Plan h</th><th style="padding:3px 8px;">Ist h</th>'
            '<th style="padding:3px 8px;">Plan €</th><th style="padding:3px 8px;">Abrechenbar €</th>'
            '<th style="padding:3px 8px;">Abwesenheit</th></tr>%s</table>'
            '<p style="margin:10px 0 0;font-size:15px;"><b>Monats-Prognose: %.2f €</b> '
            '(Plan %.2f € · schon abrechenbar %.2f € · Quote %.0f%%)</p>'
            '<p style="margin:6px 0 0;color:#666;">Details: Odoo → Menü „Umsatz-Report“</p></div>'
            % (ym, heute.strftime('%d.%m.%Y'), vym, v_sum, V['pk45b'], V['uebrige'],
               zeilen, prog_sum, plan_sum, abr_sum, quote * 100.0)
        )
        env['mail.mail'].create({
            'subject': 'Umsatz-Report %s · Prognose %.0f € · Vormonat offen %.0f €' % (ym, prog_sum, v_sum),
            'body_html': body,
            'email_to': '__MAIL_AN__',
            'auto_delete': True,
        }).send()
    except Exception:
        pass
'''.replace('__MAIL_AN__', MAIL_AN)

act_vals = {'name': 'HL: Umsatz-Report berechnen', 'model_id': model_id,
            'state': 'code', 'code': CODE, 'binding_model_id': model_id,
            'binding_type': 'action'}
action_id, how = upsert('ir.actions.server',
                        [['name', '=', 'HL: Umsatz-Report berechnen']], act_vals)
print(f'Server-Action {how} (id {action_id})')

# ---------------------------------------------------------------- 3) Views
LIST = ('<list decoration-success="x_ampel==\'gruen\'" decoration-warning="x_ampel==\'gelb\'" '
        'decoration-danger="x_ampel==\'rot\'" decoration-bf="x_klasse==\'gesamt\'" '
        'default_order="x_sortier">'
        '<field name="x_name"/><field name="x_klasse"/>'
        '<field name="x_plan_h" sum="Summe"/><field name="x_ist_h" sum="Summe"/>'
        '<field name="x_abrechenbar_h"/><field name="x_abw_h"/>'
        '<field name="x_plan_eur"/><field name="x_abrechenbar_eur"/>'
        '<field name="x_prognose_eur"/>'
        '<field name="x_ampel" optional="hide"/><field name="x_hinweis"/></list>')
SEARCH = ('<search><field name="x_name"/>'
          '<filter name="f_woche" string="Wochen" domain="[(\'x_typ\',\'=\',\'woche\')]"/>'
          '<filter name="f_prog" string="Prognose" domain="[(\'x_typ\',\'=\',\'prognose\')]"/>'
          '<filter name="f_vormonat" string="Vormonat offen" domain="[(\'x_typ\',\'=\',\'vormonat\')]"/>'
          '<filter name="f_ohne_gesamt" string="ohne Gesamt-Zeilen" domain="[(\'x_klasse\',\'!=\',\'gesamt\')]"/>'
          '<group expand="1" string="Gruppierung">'
          '<filter name="g_typ" string="Typ" context="{\'group_by\':\'x_typ\'}"/>'
          '<filter name="g_klasse" string="Klasse" context="{\'group_by\':\'x_klasse\'}"/>'
          '</group></search>')
PIVOT = ('<pivot><field name="x_name" type="row"/><field name="x_klasse" type="col"/>'
         '<field name="x_plan_h" type="measure"/><field name="x_ist_h" type="measure"/>'
         '<field name="x_plan_eur" type="measure"/><field name="x_abrechenbar_eur" type="measure"/></pivot>')
GRAPH = ('<graph type="bar"><field name="x_name"/><field name="x_plan_eur" type="measure"/></graph>')
for vtype, arch in [('list', LIST), ('search', SEARCH), ('pivot', PIVOT), ('graph', GRAPH)]:
    _, how = upsert('ir.ui.view',
                    [['model', '=', 'x_umsatzreport'], ['type', '=', vtype], ['name', '=', 'x_umsatzreport_' + vtype]],
                    {'name': 'x_umsatzreport_' + vtype, 'model': 'x_umsatzreport', 'type': vtype, 'arch_base': arch})
    print(f'View {vtype} {how}')

win_id, how = upsert('ir.actions.act_window', [['res_model', '=', 'x_umsatzreport']], {
    'name': 'Umsatz-Report', 'res_model': 'x_umsatzreport',
    'view_mode': 'list,pivot,graph'})
print(f'Fenster-Aktion {how} (id {win_id})')

menu_id, how = upsert('ir.ui.menu', [['name', '=', 'Umsatz-Report']], {
    'name': 'Umsatz-Report', 'action': 'ir.actions.act_window,%d' % win_id})
print(f'Menüpunkt {how} (id {menu_id})')

# ---------------------------------------------------------------- 4) Cron (täglich ~05:30, mit Mail)
morgen = datetime.datetime.utcnow().date() + datetime.timedelta(days=1)
nextcall = morgen.strftime('%Y-%m-%d') + ' 04:30:00'  # 05:30 CET (06:30 im Sommer)
cron_vals = {'name': 'HL: Umsatz-Report (täglich, Mail)', 'model_id': model_id,
             'state': 'code',
             'code': 'env["ir.actions.server"].browse(%d).with_context(umsatzreport_mail=True).run()' % action_id,
             'interval_number': 1, 'interval_type': 'days',
             'nextcall': nextcall, 'active': True}
try:
    _, how = upsert('ir.cron', [['name', '=', 'HL: Umsatz-Report (täglich, Mail)']], cron_vals)
    print(f'Cron {how} (nächster Lauf {nextcall} UTC, Mail an {MAIL_AN})')
except SystemExit as e:
    print(f'Cron konnte nicht angelegt werden: {e}')
    print('Bitte manuell: Einstellungen → Technisch → Geplante Aktionen.')

# ---------------------------------------------------------------- 5) Erster Lauf (ohne Mail)
print('Starte erste Berechnung (ohne Mail) ...')
kw('ir.actions.server', 'run', [[action_id]])
n = kw('x_umsatzreport', 'search_count', [[]])
print(f'Fertig: {n} Report-Zeilen berechnet.')
print('In Odoo: Hauptmenü → "Umsatz-Report" (ggf. Browser neu laden).')
print('Test-Mail: In Odoo die Server-Aktion "HL: Umsatz-Report berechnen" ist ohne Mail;')
print('die tägliche Mail kommt über den Cron. Zum Sofort-Test den Cron in den')
print('Geplanten Aktionen öffnen und "Manuell ausführen" klicken.')
