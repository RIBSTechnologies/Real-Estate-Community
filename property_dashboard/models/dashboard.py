# -*- coding: utf-8 -*-
"""
Property Dashboard - data layer (fixed).

Main fixes vs the previous version
----------------------------------
1.  Selection labels (stage / type / contract_type) are now read from the DB
    with fields_get() instead of being hard-coded.  Hard-coded keys were the
    #1 reason charts came back empty: if rental_management uses e.g.
    'on_rent' instead of 'on_lease', every hard-coded lookup silently
    returned 0.
2.  read_group() replaced by a version-safe wrapper (_read_group on 17/18/19,
    read_group as fallback).  On Odoo 18 the old call signature was raising
    and the bare `except` swallowed it -> empty charts.
3.  _company_domain() no longer adds company_id to models that don't have it
    (property.project) -> "Buildings" KPI was always 0.
4.  Monthly trend used 12 separate searches + mapped().  Now ONE search_read
    on account.move.  Much faster and it no longer returns 0 when
    rent.invoice.invoice_date is empty (falls back to move.invoice_date).
5.  Year filter now covers contracts + properties, not only invoices, the
    year list is built from real data (past AND future years), and the
    default year falls back to the latest year that actually has data.
6.  get_diagnostics() added - tells you exactly which model/field is missing
    on this database instead of failing silently.
"""

import calendar
import logging
from datetime import date, timedelta

from odoo import api, fields, models

_logger = logging.getLogger(__name__)

# Fallback ordering / labels only.  The real labels are read from the DB.
STAGE_FALLBACK = [
    ('draft', 'Draft'),
    ('available', 'Available'),
    ('booked', 'In Booking'),
    ('on_lease', 'On Rent'),
    ('sale', 'In Sale'),
    ('sold', 'Sold'),
]
TYPE_FALLBACK = [
    ('land', 'Land'),
    ('residential', 'Residential'),
    ('commercial', 'Commercial'),
    ('industrial', 'Industrial'),
]
CONTRACT_FALLBACK = [
    ('new_contract', 'Draft'),
    ('running_contract', 'Running'),
    ('expire_contract', 'Expired'),
    ('close_contract', 'Closed'),
    ('cancel_contract', 'Cancelled'),
]

# Stage keys that mean "rented out" / "sold" - checked against whatever the
# DB actually exposes, so a rename upstream does not break occupancy.
RENTED_KEYS = ('on_lease', 'on_rent', 'rented', 'lease')
SOLD_KEYS = ('sold',)
AVAILABLE_KEYS = ('available', 'free')
BOOKED_KEYS = ('booked', 'booking', 'reserved')
IN_SALE_KEYS = ('sale', 'for_sale', 'in_sale')

EXPIRY_WINDOW_DAYS = 90


class PropertyDashboard(models.AbstractModel):
    _name = 'property.dashboard'
    _description = 'Property Management Dashboard'

    # ================================================================== #
    # Generic helpers
    # ================================================================== #
    def _model(self, name):
        """Return the model if it exists on this DB, else None."""
        return self.env[name] if name in self.env else None

    def _has(self, model_name, field):
        model = self._model(model_name)
        return bool(model is not None and field in model._fields)

    def _company_domain(self, model_name):
        """Only apply the company filter when the model really has company_id."""
        if self._has(model_name, 'company_id'):
            return [('company_id', 'in', self.env.companies.ids)]
        return []

    def _count(self, model_name, domain):
        model = self._model(model_name)
        if model is None:
            return 0
        try:
            return model.search_count(domain)
        except Exception:
            _logger.warning("Dashboard count failed for %s %s", model_name, domain, exc_info=True)
            return 0

    def _selection(self, model_name, field, fallback):
        """Real selection values straight from the DB (translated labels)."""
        model = self._model(model_name)
        if model is None or field not in model._fields:
            return list(fallback)
        try:
            sel = model.fields_get([field]).get(field, {}).get('selection') or []
            sel = [(k, v) for k, v in sel]
            return sel or list(fallback)
        except Exception:
            _logger.warning("fields_get failed on %s.%s", model_name, field, exc_info=True)
            return list(fallback)

    @staticmethod
    def _match_keys(selection, wanted):
        """Return the keys present in `selection` that match any of `wanted`."""
        keys = [k for k, _ in selection]
        return [k for k in keys if k in wanted]

    # ------------------------------------------------------------------ #
    # Version-safe read_group  (Odoo 15/16 -> 19)
    # ------------------------------------------------------------------ #
    def _group_count(self, model_name, domain, field):
        """Return [(raw_key, display_label, count)] for one groupby field."""
        model = self._model(model_name)
        if model is None or field not in model._fields:
            return []

        raw_rows = []
        # Odoo 17+ signature
        try:
            for grp in model._read_group(domain, [field], ['__count']):
                raw_rows.append((grp[0], grp[1]))
        except Exception:
            raw_rows = []
            # Odoo 15/16 signature
            try:
                for g in model.read_group(domain, [field], [field], lazy=True):
                    cnt = g.get('__count')
                    if cnt is None:
                        cnt = g.get('%s_count' % field, 0)
                    raw_rows.append((g.get(field), cnt))
            except Exception:
                _logger.warning("group failed on %s.%s", model_name, field, exc_info=True)
                return []

        out = []
        for raw, cnt in raw_rows:
            key, label = self._unpack(raw)
            out.append((key, label, cnt or 0))
        return out

    @staticmethod
    def _unpack(raw):
        """Normalise a groupby value into (key, label)."""
        if hasattr(raw, '_name'):                      # recordset (_read_group)
            return (raw.id, raw.display_name) if raw else (False, False)
        if isinstance(raw, (list, tuple)) and len(raw) == 2:   # (id, name) tuple
            return raw[0], raw[1]
        if raw in (False, None):
            return False, False
        return raw, str(raw)

    def _breakdown_selection(self, model_name, domain, field, fallback):
        """Chart block for a selection field, using the DB's own labels."""
        selection = self._selection(model_name, field, fallback)
        label_map = dict(selection)
        counts = {k: c for k, _l, c in self._group_count(model_name, domain, field)}
        labels, data, keys = [], [], []
        # keep the selection's natural order
        for key, _lbl in selection:
            val = counts.get(key, 0)
            if val:
                labels.append(label_map.get(key, key))
                data.append(val)
                keys.append(key)
        # anything the DB returned that is not in the selection (dirty data)
        for key, val in counts.items():
            if key and key not in label_map and val:
                labels.append(str(key))
                data.append(val)
                keys.append(key)
        return {'labels': labels, 'data': data, 'keys': keys, 'counts': counts}

    def _breakdown_m2o(self, model_name, domain, field, limit=None):
        rows = [(k, l, c) for k, l, c in self._group_count(model_name, domain, field) if k]
        rows.sort(key=lambda r: r[2], reverse=True)
        if limit:
            rows = rows[:limit]
        return {
            'labels': [r[1] for r in rows],
            'data': [r[2] for r in rows],
            'keys': [r[0] for r in rows],
        }

    # ================================================================== #
    # YEARS  -  built from real data, not a blind today-5 loop
    # ================================================================== #
    def _minmax_year(self, model_name, field, acc):
        model = self._model(model_name)
        if model is None or field not in model._fields:
            return
        for order in ('%s asc' % field, '%s desc' % field):
            try:
                rec = model.search([(field, '!=', False)], order=order, limit=1)
            except Exception:
                return
            if rec:
                val = rec[0][field]
                if val:
                    acc.add(val.year)

    def _year_range(self):
        today = fields.Date.today()
        acc = {today.year}
        self._minmax_year('tenancy.details', 'start_date', acc)
        self._minmax_year('tenancy.details', 'end_date', acc)
        self._minmax_year('rent.invoice', 'invoice_date', acc)
        self._minmax_year('account.move', 'invoice_date', acc)
        lo, hi = min(acc), max(acc)
        # always give one year of head-room in each direction, cap the list
        lo = max(lo - 1, hi - 11)
        hi = max(hi, today.year + 1)
        return list(range(hi, lo - 1, -1))

    def _default_year(self, years):
        """Current year if it has invoice data, else the newest year that does."""
        today = fields.Date.today()
        move_ids = self._rent_move_ids()
        if not move_ids:
            return str(today.year)
        Move = self._model('account.move')
        for y in ([today.year] + [x for x in years if x != today.year]):
            try:
                if Move.search_count([('id', 'in', move_ids),
                                      ('invoice_date', '>=', date(y, 1, 1)),
                                      ('invoice_date', '<=', date(y, 12, 31))]):
                    return str(y)
            except Exception:
                break
        return str(today.year)

    # ================================================================== #
    # FILTERS
    # ================================================================== #
    @api.model
    def get_filter_data(self):
        regions, buildings, subtypes = [], [], []

        region_model = self._model('property.region')
        if region_model is not None:
            regions = [{'id': r.id, 'name': r.display_name}
                       for r in region_model.search([], order='name')]

        building_model = self._model('property.project')
        if building_model is not None:
            buildings = [{'id': b.id, 'name': b.display_name}
                         for b in building_model.search(self._company_domain('property.project'),
                                                        order='name')]

        subtype_model = self._model('property.sub.type')
        if subtype_model is not None:
            subtypes = [{'id': s.id, 'name': s.display_name,
                         'type': (s.type if 'type' in s._fields else False) or False}
                        for s in subtype_model.search([], order='name')]

        years = self._year_range()

        return {
            'types': [{'id': k, 'name': v}
                      for k, v in self._selection('property.details', 'type', TYPE_FALLBACK)],
            'sale_lease': [{'id': k, 'name': v}
                           for k, v in self._selection('property.details', 'sale_lease',
                                                       [('for_sale', 'Sale'), ('for_tenancy', 'Rent')])],
            'regions': regions,
            'buildings': buildings,
            'subtypes': subtypes,
            'fiscal_years': [{'value': str(y), 'label': str(y)} for y in years],
            'months': [{'value': m, 'label': calendar.month_name[m]} for m in range(1, 13)],
            'currency_symbol': self.env.company.currency_id.symbol or '',
            'defaults': {'fiscal_year': self._default_year(years)},
        }

    # ================================================================== #
    # DOMAIN BUILDERS
    # ================================================================== #
    def _property_domain(self, prop_type, sale_lease, region_id, building_id, subtype_id):
        domain = self._company_domain('property.details')
        if prop_type and self._has('property.details', 'type'):
            domain.append(('type', '=', prop_type))
        if sale_lease and self._has('property.details', 'sale_lease'):
            domain.append(('sale_lease', '=', sale_lease))
        if region_id and self._has('property.details', 'region_id'):
            domain.append(('region_id', '=', int(region_id)))
        if building_id and self._has('property.details', 'property_project_id'):
            domain.append(('property_project_id', '=', int(building_id)))
        if subtype_id and self._has('property.details', 'property_subtype_id'):
            domain.append(('property_subtype_id', '=', int(subtype_id)))
        return domain

    def _project_domain(self, prop_type, sale_lease, region_id, building_id, subtype_id):
        """property.project uses its own field names (property_type, not type)."""
        domain = self._company_domain('property.project')
        if building_id:
            domain.append(('id', '=', int(building_id)))
        if prop_type and self._has('property.project', 'property_type'):
            domain.append(('property_type', '=', prop_type))
        if sale_lease and self._has('property.project', 'sale_lease'):
            domain.append(('sale_lease', '=', sale_lease))
        if region_id and self._has('property.project', 'region_id'):
            domain.append(('region_id', '=', int(region_id)))
        if subtype_id and self._has('property.project', 'property_subtype_id'):
            domain.append(('property_subtype_id', '=', int(subtype_id)))
        return domain

    def _tenancy_domain(self, prop_type, sale_lease, region_id, building_id, subtype_id,
                        date_from=False, date_to=False):
        """Same filters as properties, pushed through property_id, + period overlap."""
        domain = self._company_domain('tenancy.details')
        if self._has('tenancy.details', 'property_id'):
            if prop_type:
                domain.append(('property_id.type', '=', prop_type))
            if sale_lease:
                domain.append(('property_id.sale_lease', '=', sale_lease))
            if region_id:
                domain.append(('property_id.region_id', '=', int(region_id)))
            if building_id:
                domain.append(('property_id.property_project_id', '=', int(building_id)))
            if subtype_id:
                domain.append(('property_id.property_subtype_id', '=', int(subtype_id)))
        # a contract belongs to the period if it overlaps it
        if date_from and self._has('tenancy.details', 'end_date'):
            domain += ['|', ('end_date', '=', False), ('end_date', '>=', date_from)]
        if date_to and self._has('tenancy.details', 'start_date'):
            domain.append(('start_date', '<=', date_to))
        return domain

    def _date_range(self, fiscal_year, month):
        today = fields.Date.today()
        if not fiscal_year:
            return False, False
        year = int(fiscal_year)
        if month:
            month = int(month)
            last = calendar.monthrange(year, month)[1]
            return date(year, month, 1), date(year, month, last)
        return date(year, 1, 1), date(year, 12, 31)

    # ================================================================== #
    # MAIN ENTRY POINT
    # ================================================================== #
    @api.model
    def get_dashboard_data(self, prop_type=False, sale_lease=False, region_id=False,
                           building_id=False, subtype_id=False,
                           fiscal_year=False, month=False):
        today = fields.Date.today()
        base_domain = self._property_domain(prop_type, sale_lease, region_id,
                                            building_id, subtype_id)
        date_from, date_to = self._date_range(fiscal_year, month)
        ten_domain = self._tenancy_domain(prop_type, sale_lease, region_id, building_id,
                                          subtype_id, date_from, date_to)

        # ---------- properties: ONE grouped query drives every stage KPI ----
        stage_sel = self._selection('property.details', 'stage', STAGE_FALLBACK)
        by_stage = self._breakdown_selection('property.details', base_domain, 'stage', STAGE_FALLBACK)
        stage_counts = by_stage['counts']

        def stage_total(wanted):
            return sum(stage_counts.get(k, 0) for k in self._match_keys(stage_sel, wanted))

        total_properties = self._count('property.details', base_domain)
        available = stage_total(AVAILABLE_KEYS)
        on_rent = stage_total(RENTED_KEYS)
        booked = stage_total(BOOKED_KEYS)
        sold = stage_total(SOLD_KEYS)
        in_sale = stage_total(IN_SALE_KEYS)

        project_domain = self._project_domain(prop_type, sale_lease, region_id, building_id, subtype_id)
        buildings = self._count('property.project', project_domain)

        occupied = on_rent + sold
        occupancy = (occupied / total_properties * 100.0) if total_properties else 0.0

        # ---------- contacts ----------
        tenants = self._count('res.partner', [('is_tenancy', '=', True)]) \
            if self._has('res.partner', 'is_tenancy') else 0
        buyers = self._count('res.partner', [('is_sold_customer', '=', True)]) \
            if self._has('res.partner', 'is_sold_customer') else 0
        landlords = self._landlord_count(base_domain)

        # ---------- contracts ----------
        contracts_by_status = self._breakdown_selection(
            'tenancy.details', ten_domain, 'contract_type', CONTRACT_FALLBACK)
        ct_sel = self._selection('tenancy.details', 'contract_type', CONTRACT_FALLBACK)
        running_keys = self._match_keys(ct_sel, ('running_contract', 'running', 'expiring_soon'))
        active_tenancies = sum(contracts_by_status['counts'].get(k, 0) for k in running_keys)
        total_contracts = sum(contracts_by_status['counts'].values())
        expiring_soon = self._expiring_soon(ten_domain, running_keys, today)
        contract_status_tiles = self._contract_status_tiles(ten_domain, ct_sel)

        # ---------- money (one search_read, reused by the trend) ----------
        move_ids = self._rent_move_ids()
        move_rows = self._move_rows(move_ids, date_from, date_to)
        invoice_stats = self._invoice_stats(move_rows)
        monthly_invoiced = self._monthly_invoiced(move_ids, fiscal_year or today.year)

        # ---------- charts ----------
        by_type = self._breakdown_selection('property.details', base_domain, 'type', TYPE_FALLBACK)
        by_subtype = self._breakdown_m2o('property.details', base_domain, 'property_subtype_id', limit=12)
        by_building = self._breakdown_m2o('property.details', base_domain, 'property_project_id', limit=10)
        by_region = self._breakdown_m2o('property.details', base_domain, 'region_id', limit=10)

        for block in (by_stage, by_type, contracts_by_status):
            block.pop('counts', None)

        period_label = self._period_label(fiscal_year, month)

        return {
            'kpis': {
                'total_properties': total_properties,
                'available': available,
                'on_rent': on_rent,
                'booked': booked,
                'sold': sold,
                'in_sale': in_sale,
                'buildings': buildings,
                'tenants': tenants,
                'buyers': buyers,
                'landlords': landlords,
                'active_tenancies': active_tenancies,
                'total_contracts': total_contracts,
                'expiring_soon': expiring_soon,
                'occupancy': round(occupancy, 1),
                'rent_invoiced': invoice_stats['invoiced'],
                'rent_collected': invoice_stats['collected'],
                'outstanding': invoice_stats['outstanding'],
                'invoice_count': invoice_stats['count'],
            },
            'by_stage': by_stage,
            'by_type': by_type,
            'by_subtype': by_subtype,
            'by_building': by_building,
            'by_region': by_region,
            'contracts_by_status': contracts_by_status,
            'contract_status_tiles': contract_status_tiles,
            'monthly_invoiced': monthly_invoiced,
            'recent_contracts': self._recent_contracts(ten_domain),
            'outstanding_invoices': self._outstanding_invoices(move_rows),
            'currency_symbol': self.env.company.currency_id.symbol or '',
            'period_label': period_label,
            'fiscal_year': str(fiscal_year) if fiscal_year else '',
        }

    def _period_label(self, fiscal_year, month):
        if not fiscal_year:
            return 'All Years'
        if month:
            return '%s %s' % (calendar.month_name[int(month)], fiscal_year)
        return 'FY %s' % fiscal_year

    def _landlord_count(self, base_domain):
        """Distinct landlords over the filtered properties."""
        for field in ('landlord_id', 'owner_id', 'user_id'):
            if self._has('property.details', field):
                rows = self._group_count('property.details', base_domain, field)
                return len([r for r in rows if r[0]])
        return 0

    def _expiring_soon(self, ten_domain, running_keys, today):
        if not self._has('tenancy.details', 'end_date'):
            return 0
        domain = list(ten_domain) + [
            ('end_date', '>=', today),
            ('end_date', '<=', today + timedelta(days=EXPIRY_WINDOW_DAYS)),
        ]
        if running_keys:
            domain.append(('contract_type', 'in', running_keys))
        return self._count('tenancy.details', domain)

    def _contract_status_tiles(self, ten_domain, ct_sel):
        """New / Renew / Release / Termination counts for the front-screen tile row.

        - New: contract_type == 'new_contract' (fresh draft contracts).
        - Renew: is_extended = True (set on the new contract created via the
          renew flow in ribs_real_estate's contract wizard).
        - Release / Termination: split of termination_type ('normal' / 'early'),
          a ribs_real_estate-only field - guarded so this stays 0 on plain
          rental_management installs instead of erroring out.
        """
        new_keys = self._match_keys(ct_sel, ('new_contract', 'draft'))
        new_domain = ten_domain + [('contract_type', 'in', new_keys)] if new_keys else ten_domain
        new_count = self._count('tenancy.details', new_domain) if new_keys else 0

        renew_domain = ten_domain
        renew_count = 0
        if self._has('tenancy.details', 'is_extended'):
            renew_domain = ten_domain + [('is_extended', '=', True)]
            renew_count = self._count('tenancy.details', renew_domain)

        release_domain = ten_domain + [('termination_type', '=', 'normal')]
        termination_domain = ten_domain + [('termination_type', '=', 'early')]
        release_count = 0
        termination_count = 0
        if self._has('tenancy.details', 'termination_type'):
            release_count = self._count('tenancy.details', release_domain)
            termination_count = self._count('tenancy.details', termination_domain)

        return {
            'new': {'value': new_count, 'domain': new_domain, 'label': 'New'},
            'renew': {'value': renew_count, 'domain': renew_domain, 'label': 'Renew'},
            'release': {'value': release_count, 'domain': release_domain, 'label': 'Release'},
            'termination': {'value': termination_count, 'domain': termination_domain, 'label': 'Termination'},
        }

    # ================================================================== #
    # MONEY
    # ================================================================== #
    def _rent_move_ids(self):
        """account.move ids that represent rent invoices - ONE query."""
        Rent = self._model('rent.invoice')
        if Rent is not None and 'rent_invoice_id' in Rent._fields:
            try:
                rows = Rent.search_read([('rent_invoice_id', '!=', False)], ['rent_invoice_id'])
                ids = [r['rent_invoice_id'][0] for r in rows if r.get('rent_invoice_id')]
                if ids:
                    return ids
            except Exception:
                _logger.warning("rent.invoice read failed", exc_info=True)
        # fallback: rental_management often stamps tenancy_id on the move itself
        Move = self._model('account.move')
        if Move is not None and 'tenancy_id' in Move._fields:
            try:
                return Move.search([('tenancy_id', '!=', False)]).ids
            except Exception:
                _logger.warning("account.move tenancy fallback failed", exc_info=True)
        return []

    def _move_rows(self, move_ids, date_from=False, date_to=False):
        Move = self._model('account.move')
        if Move is None or not move_ids:
            return []
        domain = [('id', 'in', move_ids), ('state', '=', 'posted')]
        if date_from:
            domain.append(('invoice_date', '>=', date_from))
        if date_to:
            domain.append(('invoice_date', '<=', date_to))
        fields_to_read = ['name', 'invoice_date', 'invoice_date_due', 'partner_id',
                          'move_type', 'amount_total_signed', 'amount_residual_signed']
        available = set(Move._fields)
        fields_to_read = [f for f in fields_to_read if f in available]
        try:
            return Move.search_read(domain, fields_to_read, order='invoice_date desc')
        except Exception:
            _logger.warning("move search_read failed", exc_info=True)
            return []

    @staticmethod
    def _row_amount(row, key, fallback_key):
        val = row.get(key)
        if val is None:
            val = row.get(fallback_key, 0.0)
        return val or 0.0

    def _invoice_stats(self, rows):
        invoiced = sum(self._row_amount(r, 'amount_total_signed', 'amount_total') for r in rows)
        outstanding = sum(self._row_amount(r, 'amount_residual_signed', 'amount_residual') for r in rows)
        return {
            'invoiced': round(invoiced, 2),
            'collected': round(invoiced - outstanding, 2),
            'outstanding': round(outstanding, 2),
            'count': len(rows),
        }

    def _monthly_invoiced(self, move_ids, year):
        """12 months of the given year - ONE query instead of twelve."""
        year = int(year)
        labels = ['%s %s' % (calendar.month_abbr[m], str(year)[-2:]) for m in range(1, 13)]
        data = [0.0] * 12
        rows = self._move_rows(move_ids, date(year, 1, 1), date(year, 12, 31))
        for r in rows:
            d = r.get('invoice_date')
            if not d:
                continue
            if isinstance(d, str):
                try:
                    d = fields.Date.from_string(d)
                except Exception:
                    continue
            data[d.month - 1] += self._row_amount(r, 'amount_total_signed', 'amount_total')
        return {'labels': labels, 'data': [round(v, 2) for v in data]}

    # ================================================================== #
    # TABLES
    # ================================================================== #
    def _recent_contracts(self, domain):
        model = self._model('tenancy.details')
        if model is None:
            return []
        try:
            recs = model.search(domain, order='id desc', limit=10)
        except Exception:
            _logger.warning("recent contracts search failed", exc_info=True)
            return []
        status_map = dict(self._selection('tenancy.details', 'contract_type', CONTRACT_FALLBACK))
        out = []
        for r in recs:
            try:
                ct = r.contract_type if 'contract_type' in r._fields else ''
                tenant = r.tenancy_id.display_name if r._fields.get('tenancy_id') and r.tenancy_id else ''
                prop = r.property_id.display_name if r._fields.get('property_id') and r.property_id else ''
                rent = 0.0
                for f in ('total_rent', 'rent_amount', 'total_amount'):
                    if f in r._fields and r[f]:
                        rent = r[f]
                        break
                seq = ''
                for f in ('tenancy_seq', 'name', 'display_name'):
                    if f in r._fields and r[f]:
                        seq = r[f]
                        break
                out.append({
                    'id': r.id,
                    'name': seq or '',
                    'tenant': tenant,
                    'property': prop,
                    'rent': round(rent or 0.0, 2),
                    'status': status_map.get(ct, ct or ''),
                    'status_key': ct or '',
                    'start': r.start_date.strftime('%d %b %Y') if r._fields.get('start_date') and r.start_date else '',
                    'end': r.end_date.strftime('%d %b %Y') if r._fields.get('end_date') and r.end_date else '',
                })
            except Exception:
                _logger.warning("contract row skipped (id=%s)", r.id, exc_info=True)
        return out

    def _outstanding_invoices(self, rows):
        out = []
        for r in rows:
            residual = self._row_amount(r, 'amount_residual_signed', 'amount_residual')
            if residual <= 0:
                continue
            partner = r.get('partner_id')
            out.append({
                'id': r['id'],
                'number': r.get('name') or '',
                'tenant': partner[1] if partner else '',
                'amount': round(residual, 2),
                'total': round(self._row_amount(r, 'amount_total_signed', 'amount_total'), 2),
                'date': r.get('invoice_date') or '',
            })
        out.sort(key=lambda x: x['amount'], reverse=True)
        return out[:10]


    # ================================================================== #
    # STATISTICS PAGE  (rebuild of rental_management's "Statistics" screen,
    # so it exists even on DBs where that menu was never shipped)
    # ================================================================== #
    def _unverified_documents(self):
        """Documents still waiting for verification - model name varies."""
        candidates = [
            ('tenancy.document', [('is_verified', '=', False)]),
            ('tenancy.document', [('verified', '=', False)]),
            ('property.document', [('is_verified', '=', False)]),
            ('property.document', [('verified', '=', False)]),
            ('tenancy.details.document', [('is_verified', '=', False)]),
        ]
        for model_name, domain in candidates:
            model = self._model(model_name)
            if model is None:
                continue
            field = domain[0][0]
            if field not in model._fields:
                continue
            return {'model': model_name, 'domain': domain,
                    'value': self._count(model_name, domain)}
        return {'model': False, 'domain': [], 'value': 0}

    def _contracts_with_dues(self, rows):
        """Distinct contracts that still have an unpaid rent invoice."""
        due_move_ids = [r['id'] for r in rows
                        if self._row_amount(r, 'amount_residual_signed', 'amount_residual') > 0]
        if not due_move_ids or not self._has('rent.invoice', 'tenancy_id'):
            return {'model': 'tenancy.details', 'domain': [], 'value': 0}
        groups = self._group_count('rent.invoice',
                                   [('rent_invoice_id', 'in', due_move_ids)], 'tenancy_id')
        ids = [g[0] for g in groups if g[0]]
        return {'model': 'tenancy.details', 'domain': [('id', 'in', ids)], 'value': len(ids)}

    @api.model
    def get_statistics_data(self):
        today = fields.Date.today()
        ten_domain = self._company_domain('tenancy.details')
        ct_sel = self._selection('tenancy.details', 'contract_type', CONTRACT_FALLBACK)
        counts = {k: c for k, _l, c in
                  self._group_count('tenancy.details', ten_domain, 'contract_type')}

        def bucket(wanted):
            keys = self._match_keys(ct_sel, wanted)
            return keys, sum(counts.get(k, 0) for k in keys)

        draft_keys, draft = bucket(('new_contract', 'draft'))
        expired_keys, expired = bucket(('expire_contract', 'expired'))
        close_keys, closed = bucket(('close_contract', 'closed'))
        running_keys, running = bucket(('running_contract', 'running'))

        expiring = self._expiring_soon(ten_domain, running_keys, today)
        expiring_domain = ten_domain + [
            ('end_date', '>=', today),
            ('end_date', '<=', today + timedelta(days=EXPIRY_WINDOW_DAYS)),
        ]
        if running_keys:
            expiring_domain.append(('contract_type', 'in', running_keys))

        docs = self._unverified_documents()

        move_ids = self._rent_move_ids()
        rows = self._move_rows(move_ids)
        dues = self._contracts_with_dues(rows)
        money = self._invoice_stats(rows)

        overdue_total, overdue_count = 0.0, 0
        for r in rows:
            residual = self._row_amount(r, 'amount_residual_signed', 'amount_residual')
            due = r.get('invoice_date_due')
            if residual <= 0 or not due:
                continue
            if isinstance(due, str):
                try:
                    due = fields.Date.from_string(due)
                except Exception:
                    continue
            if due < today:
                overdue_total += residual
                overdue_count += 1

        contracts = [
            {'key': 'draft', 'label': 'Draft Contracts', 'value': draft, 'tone': 'blue',
             'icon': 'article', 'model': 'tenancy.details',
             'domain': ten_domain + [('contract_type', 'in', draft_keys)] if draft_keys else ten_domain},
            {'key': 'expiring', 'label': 'Expiring Contracts', 'value': expiring, 'tone': 'orange',
             'icon': 'calendar_today', 'model': 'tenancy.details', 'domain': expiring_domain},
            {'key': 'expired', 'label': 'Expired Contracts', 'value': expired, 'tone': 'red',
             'icon': 'event_busy', 'model': 'tenancy.details',
             'domain': ten_domain + [('contract_type', 'in', expired_keys)] if expired_keys else ten_domain},
            {'key': 'documents', 'label': 'Documents - Not Verified', 'value': docs['value'],
             'tone': 'red', 'icon': 'description',
             'model': docs['model'] or 'tenancy.details', 'domain': docs['domain']},
            {'key': 'dues', 'label': 'Contracts - Unreceived Payments', 'value': dues['value'],
             'tone': 'green', 'icon': 'home',
             'model': dues['model'], 'domain': dues['domain']},
            {'key': 'running', 'label': 'Running Contracts', 'value': running, 'tone': 'green',
             'icon': 'play_circle', 'model': 'tenancy.details',
             'domain': ten_domain + [('contract_type', 'in', running_keys)] if running_keys else ten_domain},
            {'key': 'closed', 'label': 'Closed Contracts', 'value': closed, 'tone': 'blue',
             'icon': 'check_circle', 'model': 'tenancy.details',
             'domain': ten_domain + [('contract_type', 'in', close_keys)] if close_keys else ten_domain},
        ]

        due_domain = [('id', 'in', [r['id'] for r in rows
                                    if self._row_amount(r, 'amount_residual_signed',
                                                        'amount_residual') > 0])]
        accounting = [
            {'key': 'invoiced', 'label': 'Total Rent Invoiced', 'value': money['invoiced'],
             'tone': 'blue', 'icon': 'article', 'iconClass': 'oi-filled', 'money': True,
             'model': 'account.move', 'domain': [('id', 'in', move_ids)]},
            {'key': 'collected', 'label': 'Amount Received', 'value': money['collected'],
             'tone': 'green', 'icon': 'check', 'money': True,
             'model': 'account.move', 'domain': [('id', 'in', move_ids)]},
            {'key': 'outstanding', 'label': 'Outstanding', 'value': money['outstanding'],
             'tone': 'orange', 'icon': 'hourglass_bottom', 'money': True,
             'model': 'account.move', 'domain': due_domain},
            {'key': 'overdue', 'label': 'Overdue (%s invoices)' % overdue_count,
             'value': round(overdue_total, 2), 'tone': 'red', 'icon': 'warning',
             'money': True, 'model': 'account.move', 'domain': due_domain},
        ]

        return {
            'sections': [
                {'title': 'Rent Contract Statistics', 'icon': 'article', 'cards': contracts},
                {'title': 'Accounting Information', 'icon': 'payments', 'cards': accounting},
            ],
            'currency_symbol': self.env.company.currency_id.symbol or '',
            'documents_model': docs['model'] or '',
        }

    # ================================================================== #
    # DIAGNOSTICS  -  why is my dashboard empty?
    # ================================================================== #
    @api.model
    def get_diagnostics(self):
        checks = []

        def add(label, ok, detail=''):
            checks.append({'label': label, 'ok': bool(ok), 'detail': str(detail)})

        for m in ('property.details', 'property.project', 'tenancy.details',
                  'rent.invoice', 'property.region', 'property.sub.type', 'account.move'):
            model = self._model(m)
            add('Model %s' % m, model is not None,
                '%s records' % self._count(m, []) if model is not None else 'NOT INSTALLED')

        for m, f in (('property.details', 'stage'), ('property.details', 'type'),
                     ('property.details', 'sale_lease'), ('property.details', 'region_id'),
                     ('property.details', 'property_project_id'),
                     ('property.details', 'property_subtype_id'),
                     ('tenancy.details', 'contract_type'), ('tenancy.details', 'start_date'),
                     ('tenancy.details', 'end_date'), ('tenancy.details', 'property_id'),
                     ('rent.invoice', 'rent_invoice_id'), ('rent.invoice', 'invoice_date')):
            add('Field %s.%s' % (m, f), self._has(m, f))

        add('Selection property.details.stage', True,
            ', '.join(k for k, _ in self._selection('property.details', 'stage', STAGE_FALLBACK)))
        add('Selection tenancy.details.contract_type', True,
            ', '.join(k for k, _ in self._selection('tenancy.details', 'contract_type', CONTRACT_FALLBACK)))

        move_ids = self._rent_move_ids()
        add('Rent invoices linked to account.move', bool(move_ids), '%s moves' % len(move_ids))
        add('Companies in context', True, ', '.join(self.env.companies.mapped('name')))
        add('Years detected', True, ', '.join(str(y) for y in self._year_range()))

        # menu placement report (root-level tiles, relocation target, ...)
        try:
            checks += self.env['property.dashboard.menu.sync'].get_menu_report()
        except Exception:
            add('Menu report', False, 'menu sync helper unavailable')
        return checks
