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
    ('x_fakturiert_eur',   'float',     'Fakturiert € (RG-Datum im Monat)', {}),
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

# ------------------------------------------------- 1b) Zugriffsrechte (ACL)
# Ohne ir.model.access kann niemand (auch kein Admin-UI-Nutzer) das Modell
# lesen. Interne Benutzer: lesen; Administratoren: alles.
def xmlid(ref):
    mod, name = ref.split('.')
    d = kw('ir.model.data', 'search_read',
           [[['module', '=', mod], ['name', '=', name]]], {'fields': ['res_id'], 'limit': 1})
    return d[0]['res_id']


for acl_name, group_ref, perms in [
    ('access_x_umsatzreport_user', 'base.group_user',
     {'perm_read': True, 'perm_write': False, 'perm_create': False, 'perm_unlink': False}),
    ('access_x_umsatzreport_admin', 'base.group_system',
     {'perm_read': True, 'perm_write': True, 'perm_create': True, 'perm_unlink': True}),
]:
    vals = {'name': acl_name, 'model_id': model_id, 'group_id': xmlid(group_ref)}
    vals.update(perms)
    _, how = upsert('ir.model.access',
                    [['model_id', '=', model_id], ['name', '=', acl_name]], vals)
    print(f'  ACL {acl_name} {how}')

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

EMP = {}
akt_kw = None
for (k, ws, wend) in wochen:
    if ws <= heute <= wend:
        akt_kw = k

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
            if lv.employee_id:
                em = EMP.setdefault(lv.employee_id.name, {'wp': 0.0, 'wi': 0.0, 'mp': 0.0, 'mi': 0.0, 'abw': 0.0})
                em['abw'] += std * n / tot_wd

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
    if s.employee_ids:
        anteil = h / len(s.employee_ids)
        for e in s.employee_ids:
            em = EMP.setdefault(e.name, {'wp': 0.0, 'wi': 0.0, 'mp': 0.0, 'mi': 0.0, 'abw': 0.0})
            em['mp'] += anteil
            if kwnr == akt_kw:
                em['wp'] += anteil
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

# --- Fakturiert: gebuchte Ausgangsrechnungen (inkl. Gutschriften) mit
# Rechnungsdatum im laufenden Monat – unabhängig von der Planung. Faengt
# Umsatz, der ohne (geplante) Einsaetze fakturiert wird.
FAKT = {'pk45b': 0.0, 'uebrige': 0.0}
for mv in env['account.move'].search([('move_type', 'in', ['out_invoice', 'out_refund']),
                                      ('state', '=', 'posted'),
                                      ('invoice_date', '>=', str(m_start)),
                                      ('invoice_date', '<', str(m_ende))]):
    rp = mv.partner_id.commercial_partner_id if mv.partner_id else False
    kl = 'uebrige'
    if rp and (rp.id in pk_pat or any(c.id in pk_pat for c in rp.child_ids)):
        kl = 'pk45b'
    FAKT[kl] += mv.amount_untaxed_signed or 0.0

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
    if l.employee_id:
        em = EMP.setdefault(l.employee_id.name, {'wp': 0.0, 'wi': 0.0, 'mp': 0.0, 'mi': 0.0, 'abw': 0.0})
        em['mi'] += l.unit_amount or 0.0
        if kwnr == akt_kw:
            em['wi'] += l.unit_amount or 0.0

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
    LEER = {'plan_h': 0.0, 'plan_eur': 0.0, 'abr_h': 0.0, 'abr_eur': 0.0, 'ist_h': 0.0}
    mail_wochen.append((label, W.get((kwnr, 'pk45b'), LEER), W.get((kwnr, 'uebrige'), LEER),
                        g, abw, kwnr == akt_kw))

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
        'x_prognose_eur': round(prognose, 2), 'x_fakturiert_eur': round(FAKT[kl], 2),
        'x_ampel': 'gruen' if prognose >= pr['plan'] * 0.9 else 'gelb',
        'x_hinweis': hinw,
    })
fakt_sum = FAKT['pk45b'] + FAKT['uebrige']
rows.append({
    'x_name': 'Prognose %s · Gesamt' % ym,
    'x_monat_ym': ym, 'x_typ': 'prognose', 'x_klasse': 'gesamt', 'x_sortier': 902,
    'x_plan_eur': round(plan_sum, 2), 'x_abrechenbar_eur': round(abr_sum, 2),
    'x_prognose_eur': round(prog_sum, 2), 'x_fakturiert_eur': round(fakt_sum, 2),
    'x_ampel': 'gruen' if prog_sum >= plan_sum * 0.9 else 'gelb',
    'x_hinweis': 'Prognose = erwartete Leistung des Monats; Fakturiert = Rechnungen mit RG-Datum im Monat',
})
for r in rows:
    env['x_umsatzreport'].create(r)

# ================================================================ Mail
if env.context.get('umsatzreport_mail'):
    try:
        MON = {1: 'Januar', 2: 'Februar', 3: 'März', 4: 'April', 5: 'Mai', 6: 'Juni',
               7: 'Juli', 8: 'August', 9: 'September', 10: 'Oktober', 11: 'November', 12: 'Dezember'}
        TD = ' style="padding:4px 10px;text-align:right;border:1px solid #d8dee6;white-space:nowrap;"'
        TDL = ' style="padding:4px 10px;border:1px solid #d8dee6;"'
        TH = ' style="padding:5px 10px;background:#1f3a5f;color:#ffffff;border:1px solid #1f3a5f;text-align:left;"'
        THR = ' style="padding:5px 10px;background:#1f3a5f;color:#ffffff;border:1px solid #1f3a5f;text-align:right;"'
        H3 = ' style="margin:18px 0 6px;color:#1f3a5f;font-size:15px;"'

        # --- Block 1: Vormonat
        vrows = ''
        for kl_label, betrag in (('§45b (Pflegekasse)', V['pk45b']), ('Übrige Leistungen', V['uebrige'])):
            vrows += ('<tr><td' + TDL + '>' + kl_label + '</td><td' + TD + '>'
                      + ('%.2f' % betrag).replace('.', ',') + ' €</td></tr>')
        vrows += ('<tr style="font-weight:bold;background:#eef2f7;"><td' + TDL + '>Gesamt</td><td' + TD + '>'
                  + ('%.2f' % v_sum).replace('.', ',') + ' €</td></tr>')

        # --- Block 2: Wochen im Detail
        wrows = ''
        for (label, wpk, wgw, g, abw, akt) in mail_wochen:
            for kl_label, w, extra in (('§45b', wpk, ''), ('Übrige', wgw, ''),
                                       ('Gesamt', g, 'font-weight:bold;background:#eef2f7;')):
                hl = 'background:#fff8dc;' if (akt and not extra) else ''
                z = '<tr style="' + hl + extra + '">'
                z += '<td' + TDL + '>' + (label + (' &#9654;' if akt else '') if kl_label == '§45b' else '') + '</td>'
                z += '<td' + TDL + '>' + kl_label + '</td>'
                for val, fmt, suffix in ((w['plan_h'], '%.1f', ''), (w['ist_h'], '%.1f', ''),
                                         (w['abr_h'], '%.1f', ''), (w['plan_eur'], '%.2f', ' €'),
                                         (w['abr_eur'], '%.2f', ' €')):
                    z += '<td' + TD + '>' + (fmt % val).replace('.', ',') + suffix + '</td>'
                z += '<td' + TD + '>' + ((('%.1f' % abw).replace('.', ',') + ' h') if (kl_label == 'Gesamt' and abw > 0.05) else '') + '</td>'
                wrows += z + '</tr>'

        # --- Block 3: Mitarbeiter (laufender Monat)
        erows = ''
        for en in sorted(EMP):
            em = EMP[en]
            delta = em['mi'] - em['mp']
            farbe = '#c62828' if delta < -2 else '#222222'
            erows += '<tr><td' + TDL + '>' + en + '</td>'
            for val in (em['wp'], em['wi'], em['mp'], em['mi']):
                erows += '<td' + TD + '>' + ('%.1f' % val).replace('.', ',') + '</td>'
            erows += ('<td' + TD + ' ><span style="color:' + farbe + ';">'
                      + ('%+.1f' % delta).replace('.', ',') + '</span></td>')
            erows += '<td' + TD + '>' + (('%.1f' % em['abw']).replace('.', ',') if em['abw'] > 0.05 else '–') + '</td></tr>'
        if not erows:
            erows = '<tr><td' + TDL + ' colspan="7">Keine Daten</td></tr>'

        # --- Block 4: Prognose + Fakturiert
        prows = ''
        for kl_label, pr, fk in (('§45b', PROG['pk45b'], FAKT['pk45b']),
                                 ('Übrige Leistungen', PROG['uebrige'], FAKT['uebrige'])):
            prg = pr['abr'] + pr['zukunft'] * quote
            prows += '<tr><td' + TDL + '>' + kl_label + '</td>'
            for val in (pr['plan'], pr['abr'], prg, fk):
                prows += '<td' + TD + '>' + ('%.2f' % val).replace('.', ',') + ' €</td>'
            prows += '</tr>'
        prows += '<tr style="font-weight:bold;background:#eef2f7;"><td' + TDL + '>Gesamt</td>'
        for val in (plan_sum, abr_sum, prog_sum, fakt_sum):
            prows += '<td' + TD + '>' + ('%.2f' % val).replace('.', ',') + ' €</td>'
        prows += '</tr>'

        body = (
            '<div style="font-family:Arial,Helvetica,sans-serif;font-size:13px;color:#222;max-width:880px;">'
            '<h2 style="margin:0 0 2px;color:#1f3a5f;">Umsatz-Report ' + MON[monat] + ' ' + str(jahr) + '</h2>'
            '<p style="margin:0 0 4px;color:#666;">Stand ' + heute.strftime('%d.%m.%Y')
            + ' · ohne Erstgespräche, interne Projekte &amp; Fahrzeiten</p>'

            '<h3' + H3 + '>1 · Vormonat ' + MON[vm] + ' – noch abzurechnen</h3>'
            '<table style="border-collapse:collapse;font-size:13px;" cellspacing="0">'
            '<tr><th' + TH + '>Klasse</th><th' + THR + '>Offen</th></tr>' + vrows + '</table>'
            + ('<p style="margin:4px 0 0;color:#b26a00;">&#9888; Diese Slots stehen auf „abrechenbar (offen)" – jetzt Rechnungen/Nachweise stellen.</p>' if v_sum > 0.005 else
               '<p style="margin:4px 0 0;color:#1b7a38;">Alles abgerechnet.</p>')

            + '<h3' + H3 + '>2 · Wochen im Detail (&#9654; = laufende Woche)</h3>'
            '<table style="border-collapse:collapse;font-size:13px;" cellspacing="0">'
            '<tr><th' + TH + '>Woche</th><th' + TH + '>Klasse</th><th' + THR + '>Plan h</th>'
            '<th' + THR + '>Ist h</th><th' + THR + '>Abrechenb. h</th><th' + THR + '>Plan</th>'
            '<th' + THR + '>Abrechenbar</th><th' + THR + '>Abwesend</th></tr>' + wrows + '</table>'

            '<h3' + H3 + '>3 · Mitarbeiter (laufender Monat)</h3>'
            '<table style="border-collapse:collapse;font-size:13px;" cellspacing="0">'
            '<tr><th' + TH + '>Mitarbeiter</th><th' + THR + '>Woche Plan h</th><th' + THR + '>Woche Ist h</th>'
            '<th' + THR + '>Monat Plan h</th><th' + THR + '>Monat Ist h</th><th' + THR + '>&#916; h</th>'
            '<th' + THR + '>Abwesend h</th></tr>' + erows + '</table>'
            '<p style="margin:4px 0 0;color:#666;">&#916; = Ist minus Plan im Monat; rot ab 2 h Rückstand. '
            'Plan aus der Einsatzplanung, Ist aus der Zeiterfassung.</p>'

            '<h3' + H3 + '>4 · Monats-Prognose &amp; Fakturierung</h3>'
            '<table style="border-collapse:collapse;font-size:13px;" cellspacing="0">'
            '<tr><th' + TH + '>Klasse</th><th' + THR + '>Plan (Leistung)</th><th' + THR + '>Schon abrechenbar</th>'
            '<th' + THR + '>Prognose Leistung</th><th' + THR + '>Fakturiert</th></tr>' + prows + '</table>'
            '<p style="margin:4px 0 0;color:#666;">Realisierungsquote ' + ('%.0f' % (quote * 100.0))
            + ' % (letzte 3 Monate) · Sätze: §45b 43 €/h bis 31.12.2026, 53 €/h ab 01.01.2027 · Übrige 56 €/h<br/>'
            '<b>Fakturiert</b> = gebuchte Ausgangsrechnungen (abzgl. Gutschriften) mit Rechnungsdatum im Monat – '
            'darin steckt v. a. die Abrechnung des Vormonats und Umsatz ohne geplante Einsätze. '
            'Nicht mit der Prognose addieren (teilweise derselbe Umsatz).</p>'

            '<p style="margin:14px 0 0;color:#666;">Details: Odoo &#8594; Menü „Umsatz-Report"</p></div>'
        )
        env['mail.mail'].create({
            'subject': 'Umsatz-Report %s · Prognose %.0f € · Fakturiert %.0f € · Vormonat offen %.0f €' % (ym, prog_sum, fakt_sum, v_sum),
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
        '<field name="x_prognose_eur"/><field name="x_fakturiert_eur"/>'
        '<field name="x_ampel" optional="hide"/><field name="x_hinweis"/></list>')
SEARCH = ('<search><field name="x_name"/>'
          '<filter name="f_woche" string="Wochen" domain="[(\'x_typ\',\'=\',\'woche\')]"/>'
          '<filter name="f_prog" string="Prognose" domain="[(\'x_typ\',\'=\',\'prognose\')]"/>'
          '<filter name="f_vormonat" string="Vormonat offen" domain="[(\'x_typ\',\'=\',\'vormonat\')]"/>'
          '<filter name="f_ohne_gesamt" string="ohne Gesamt-Zeilen" domain="[(\'x_klasse\',\'!=\',\'gesamt\')]"/>'
          '<group>'
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
cron_id, how = upsert('ir.cron', [['name', '=', 'HL: Umsatz-Report (täglich, Mail)']], cron_vals)
print(f'Cron {how} (nächster Lauf {nextcall} UTC, Mail an {MAIL_AN})')

# ---------------------------------------------------------------- 5) Erster Lauf
# ir.actions.server.run() per RPC scheitert an Rechten – der Cron-Trigger
# (identisch zum Button "Manuell ausführen") funktioniert und schickt auch
# gleich die erste Mail.
print('Starte erste Berechnung über den Cron (inkl. erster Mail) ...')
kw('ir.cron', 'method_direct_trigger', [[cron_id]])
n = kw('x_umsatzreport', 'search_count', [[]])
print(f'Fertig: {n} Report-Zeilen berechnet.')
print('In Odoo: Hauptmenü → "Umsatz-Report" (ggf. Browser neu laden).')
