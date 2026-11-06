# -*- coding: utf-8 -*-
"""
Al-Shafar Extended — 4-Level Analytic Account Setup

Plan "Property Type"  (customized_type='property_type')
  └── "Residential" / "Commercial" / "Industrial" / "Land"

Plan "Sub Type"       (customized_type='sub_type')
  └── "Villa" / "Warehouse" / "Factories" / ...

Plan "Building"       (customized_type='building')
  └── "<Building Name>"

Plan "Units"          (customized_type='units')
  └── "<Unit Name>"

Invoice → all 4 evenly distributed (25% each if all present)
"""

import logging
import math

from odoo import models, fields, api, _
from odoo.exceptions import ValidationError
from odoo.tools.float_utils import float_compare, float_is_zero

_logger = logging.getLogger(__name__)

# Name of the auto-added rounding-adjustment invoice line (see
# AccountMove._apply_rounding_adjustment below). Used to find/skip an
# already-added one so it's never duplicated.
ROUNDING_LINE_NAME = 'Rounding Adjustment'

PROP_TYPE_MAP = {
    'residential': 'Residential',
    'villa':       'Villa',
    'commercial':  'Commercial',
    'industrial':  'Industrial',
    'land':        'Land',
}


def _sql_set(env, table, field, value, record_id):
    """Direct SQL — avoids triggering write() recursion."""
    env.cr.execute(
        "UPDATE %s SET %s = %%s WHERE id = %%s" % (table, field),
        (value, record_id)
    )


# ─────────────────────────────────────────────────────────────────────────────
class ResidentialType(models.Model):
    _name = 'residential.type'
    _description = 'Residential Type'
    _order = 'name'

    name = fields.Char(string='Property Type', required=True)
    analytic_plan_id = fields.Many2one(
        'account.analytic.plan', string='Analytic Plan', ondelete='set null')
    analytic_account_id = fields.Many2one(
        'account.analytic.account', string='Analytic Account', ondelete='set null')
    active = fields.Boolean(default=True)

    _name_unique = models.Constraint(
        'unique(name)',
        'Property Type name must be unique!',
    )

    @api.model
    def _get_plan(self, customized_type, plan_name):
        plan = self.env['account.analytic.plan'].sudo().search(
            [('customized_type', '=', customized_type)], limit=1)
        if not plan:
            plan = self.env['account.analytic.plan'].sudo().create({
                'name': plan_name,
                'customized_type': customized_type,
            })
            _logger.info("al_shafar_extended: created plan '%s' (%s)",
                         plan_name, customized_type)
        return plan

    @api.model
    def _ensure_defaults(self):
        """Make sure the 5 property types exist. They no longer get an
        analytic plan/account: the only analytic plans kept are Building,
        Units, AR Type, Cost Center and Sub Cost Center (Property Type and
        Sub Type were removed - see AccountAnalyticAccount._cleanup_al_shafar_analytic)."""
        for type_name in ['Residential', 'Villa', 'Commercial', 'Industrial', 'Land']:
            if not self.sudo().search([('name', '=', type_name)], limit=1):
                self.sudo().create({'name': type_name})

    @api.model_create_multi
    def create(self, vals_list):
        # name has a DB-level unique constraint, but a row with that name can
        # already exist without an ir.model.data link to this record's xmlid
        # (e.g. created by hand, or by data that loaded before this xmlid
        # existed) - in which case a plain create() would hit the unique
        # constraint instead of just reusing it. Order must match vals_list
        # 1:1 since the data loader zips them together to bind xmlids.
        records = self.browse()
        for vals in vals_list:
            name = vals.get('name')
            existing = self.search([('name', '=', name)], limit=1) if name else self.browse()
            records |= existing or super(ResidentialType, self).create(vals)
        self._ensure_defaults()
        return records


# ─────────────────────────────────────────────────────────────────────────────
class PropertySubType(models.Model):
    _inherit = 'property.sub.type'

    subtype_account_id = fields.Many2one(
        'account.analytic.account',
        string='Sub Type Analytic Account',
        domain="[('plan_id.customized_type', '=', 'sub_type')]",
        ondelete='set null',
    )

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        for rec in records:
            rec._setup_subtype_analytic()
        return records

    def write(self, vals):
        result = super().write(vals)
        skip = {'subtype_account_id', '__last_update', 'write_date', 'write_uid'}
        if set(vals.keys()) - skip:
            for rec in self:
                rec._setup_subtype_analytic()
        return result

    @api.model
    def _backfill_all_subtypes(self):
        """
        Ensure every existing property.sub.type record has a subtype_account_id.
        Called from the Sync Analytic button and on invoice creation to catch
        pre-existing records (e.g. 'Factories') created before this module.
        """
        unmapped = self.sudo().search([('subtype_account_id', '=', False), ('name', '!=', False)])
        for rec in unmapped:
            try:
                rec._setup_subtype_analytic()
            except Exception as exc:
                _logger.warning(
                    "al_shafar_extended: backfill subtype failed '%s': %s",
                    rec.name, exc)

    def _setup_subtype_analytic(self):
        """No-op: the Sub Type analytic plan was removed (only Building,
        Units, AR Type, Cost Center and Sub Cost Center are kept). Kept as a
        method so existing callers (sync button, create/write) still work."""
        return False


# ─────────────────────────────────────────────────────────────────────────────
class PropertyProject(models.Model):
    _inherit = 'property.project'

    residential_type_id = fields.Many2one(
        'residential.type', string='Residential Type (Analytic)', ondelete='set null')

    @api.model_create_multi
    def create(self, vals_list):
        result = super().create(vals_list)
        self.env['residential.type']._ensure_defaults()
        for building in result:
            building._setup_building_analytic()
        return result

    def write(self, vals):
        result = super().write(vals)
        skip = {
            'building_account_id', 'property_type_account_id',
            'residential_type_id', '__last_update', 'write_date', 'write_uid',
        }
        if set(vals.keys()) - skip:
            self.env['residential.type']._ensure_defaults()
            for building in self:
                building._setup_building_analytic()
        return result

    def action_sync_analytic_accounts(self):
        """Sync button — force the Building + Unit accounts for this building and its units."""
        self.env['residential.type']._ensure_defaults()
        # Backfill ALL unmapped property.sub.type records first
        self.env['property.sub.type']._backfill_all_subtypes()
        for building in self:
            if building.property_subtype_id:
                building.property_subtype_id._setup_subtype_analytic()
            building._setup_building_analytic()
        units = self.env['property.details'].sudo().search(
            [('property_project_id', 'in', self.ids)])
        for unit in units:
            # Also sync unit-level subtype (e.g. Industrial Type / Factories)
            if unit.property_subtype_id:
                unit.property_subtype_id._setup_subtype_analytic()
            unit._setup_unit_analytic()
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Sync Complete',
                'message': 'Building and unit analytic accounts synced.',
                'type': 'success', 'sticky': False,
            }
        }

    def _setup_building_analytic(self):
        self.ensure_one()
        ResType = self.env['residential.type']
        
        # Ensure defaults are created and correct first
        ResType._ensure_defaults()

        # Step 1: residential_type_id
        raw = (getattr(self, 'property_type', None) or '').lower()
        type_name = PROP_TYPE_MAP.get(raw, 'Residential')
        res_type = ResType.sudo().search([('name', '=', type_name)], limit=1)
        if res_type and self.residential_type_id.id != res_type.id:
            _sql_set(self.env, 'property_project',
                     'residential_type_id', res_type.id, self.id)
            self.invalidate_recordset(['residential_type_id'])

        res_type = self.residential_type_id
        if not res_type:
            return

        # Step 2: the Property Type / Sub Type analytic plans were removed -
        # make sure no stale Property Type account stays on the building
        # (ribs_real_estate adds it to invoice lines whenever it is set).
        if self.property_type_account_id:
            _sql_set(self.env, 'property_project', 'property_type_account_id', None, self.id)
            self.invalidate_recordset(['property_type_account_id'])

        # Step 3: building_account_id
        if self.building_account_id:
            if self.building_account_id.name != self.name:
                self.building_account_id.sudo().write({'name': self.name})
            return

        building_plan = ResType._get_plan('building', 'Building')
        existing = self.env['account.analytic.account'].sudo().search([
            ('name', '=', self.name), ('plan_id', '=', building_plan.id),
        ], limit=1)
        account = existing
        if not account:
            try:
                account = self.env['account.analytic.account'].sudo().create({
                    'name': self.name, 'plan_id': building_plan.id,
                })
            except Exception as exc:
                _logger.error("al_shafar_extended: building account failed '%s': %s",
                              self.name, exc)
                return

        _sql_set(self.env, 'property_project',
                 'building_account_id', account.id, self.id)
        self.invalidate_recordset(['building_account_id'])
        _logger.info("al_shafar_extended: building account set '%s'", self.name)

        # Sync building_account_id to its unit accounts
        if self.building_account_id:
            units = self.env['property.details'].sudo().search([
                ('property_project_id', '=', self.id),
                ('unit_account_id', '!=', False),
            ])
            unit_accs = units.mapped('unit_account_id').filtered(
                lambda a: a.building_account_id.id != self.building_account_id.id
            )
            if unit_accs:
                unit_accs.sudo().write({'building_account_id': self.building_account_id.id})

    def unlink(self):
        b_accs = self.mapped('building_account_id')
        res = super().unlink()
        if b_accs:
            b_accs.sudo().write({'active': False})
        return res


# ─────────────────────────────────────────────────────────────────────────────
class PropertyDetails(models.Model):
    _inherit = 'property.details'

    @api.model_create_multi
    def create(self, vals_list):
        result = super().create(vals_list)
        for unit in result:
            unit._setup_unit_analytic()
        return result

    def write(self, vals):
        result = super().write(vals)
        skip = {
            'unit_account_id', 'analytic_account_id',
            '__last_update', 'write_date', 'write_uid',
        }
        if set(vals.keys()) - skip:
            for unit in self:
                unit._setup_unit_analytic()
        return result

    def unlink(self):
        unit_accs = self.mapped('unit_account_id')
        res = super().unlink()
        if unit_accs:
            unit_accs.sudo().write({'active': False})
        return res

    def _unit_analytic_name(self):
        """Unit analytic accounts are named after the Property Code (e.g.
        6-V-01), falling back to the unit name while no code is set. Property
        Code is not unique in the database, so a code shared with another unit
        gets the unit name appended to keep the accounts distinguishable."""
        self.ensure_one()
        code = (self.property_seq or '').strip()
        if not code:
            return self.name
        shared = self.sudo().with_context(active_test=False).search_count([
            ('property_seq', '=', self.property_seq), ('id', '!=', self.id)])
        return '%s (%s)' % (code, self.name) if shared else code

    def _setup_unit_analytic(self):
        """Every unit gets its own Units analytic account - even without a
        building (the building link is then just left empty), and never one
        already linked to another unit."""
        self.ensure_one()
        building = self.property_project_id
        if building and not building.building_account_id:
            building._setup_building_analytic()
        building_acc_id = building.building_account_id.id if building.building_account_id else False
        account_name = self._unit_analytic_name()

        if self.unit_account_id:
            vals = {}
            if self.unit_account_id.name != account_name:
                vals['name'] = account_name
            if building_acc_id and self.unit_account_id.building_account_id.id != building_acc_id:
                vals['building_account_id'] = building_acc_id
            if vals:
                self.unit_account_id.sudo().write(vals)
            return

        units_plan = self.env['residential.type']._get_plan('units', 'Units')
        # Reuse an orphan account with this name (e.g. left by an earlier run),
        # but never one another unit already owns - two units sharing a code or
        # name used to end up sharing one account.
        taken = self.sudo().with_context(active_test=False).search([
            ('unit_account_id', '!=', False), ('id', '!=', self.id)]).mapped('unit_account_id').ids
        base_domain = [
            ('name', '=', account_name),
            ('plan_id', '=', units_plan.id),
            ('id', 'not in', taken),
        ]
        existing = False
        if building_acc_id:
            existing = self.env['account.analytic.account'].sudo().search(
                base_domain + [('building_account_id', '=', building_acc_id)], limit=1)
        if not existing:
            existing = self.env['account.analytic.account'].sudo().search(base_domain, limit=1)

        if existing:
            if building_acc_id and existing.building_account_id.id != building_acc_id:
                existing.sudo().write({'building_account_id': building_acc_id})
            _sql_set(self.env, 'property_details',
                     'unit_account_id', existing.id, self.id)
            self.invalidate_recordset(['unit_account_id'])
            return

        try:
            unit_acc = self.env['account.analytic.account'].sudo().create({
                'name': account_name,
                'plan_id': units_plan.id,
                'building_account_id': building_acc_id,
            })
            _sql_set(self.env, 'property_details',
                     'unit_account_id', unit_acc.id, self.id)
            self.invalidate_recordset(['unit_account_id'])
            _logger.info("al_shafar_extended: unit account '%s'", account_name)
        except Exception as exc:
            _logger.error("al_shafar_extended: unit account failed '%s': %s",
                          account_name, exc)


# ─────────────────────────────────────────────────────────────────────────────
class AccountMove(models.Model):
    _inherit = 'account.move'

    def _get_four_level_analytic_accounts(self):
        """
        Returns [building_acc_id, unit_acc_id].

        Used to only return up to 4 levels (Property Type, Sub Type,
        Building, Units) - Property Type and Sub Type were dropped on
        request (the analytic distribution widget on invoices now shows 5
        columns instead of 7: Building, Unit, AR Type, Cost Center, Sub
        Cost Center - see AccountAnalyticPlan.get_relevant_plans in
        analytic_plan_extend.py). Kept the original method name to avoid
        churn in the one caller (_apply_analytic_to_lines below).
        """
        self.ensure_one()
        accounts = []

        unit = None
        if self.tenancy_id and self.tenancy_id.property_id:
            unit = self.tenancy_id.property_id
        if not unit:
            return accounts

        building = unit.property_project_id
        if not building:
            return accounts

        # Ensure building accounts are set correctly and self-healed
        building._setup_building_analytic()
        building.invalidate_recordset([
            'building_account_id', 'property_type_account_id', 'residential_type_id'
        ])

        # 1. Building account — fresh DB read
        self.env.cr.execute(
            "SELECT building_account_id FROM property_project WHERE id = %s",
            (building.id,))
        row = self.env.cr.fetchone()
        if row and row[0]:
            accounts.append(row[0])

        # 2. Unit account — fresh DB read
        self.env.cr.execute(
            "SELECT unit_account_id FROM property_details WHERE id = %s",
            (unit.id,))
        row = self.env.cr.fetchone()
        if not (row and row[0]):
            unit._setup_unit_analytic()
            self.env.cr.execute(
                "SELECT unit_account_id FROM property_details WHERE id = %s",
                (unit.id,))
            row = self.env.cr.fetchone()
        if row and row[0]:
            accounts.append(row[0])

        # Deduplicate preserving order
        seen, result = set(), []
        for acc_id in accounts:
            if acc_id not in seen:
                seen.add(acc_id)
                result.append(acc_id)

        _logger.info(
            "al_shafar_extended: invoice %s → analytic accounts %s",
            self.id or 'NEW', result)
        return result

    def _build_analytic_distribution(self, account_ids):
        if not account_ids:
            return {}
        # Co-select all analytic accounts on a single line with 100% distribution
        key = ",".join(str(acc_id) for acc_id in account_ids if acc_id)
        return {key: 100.0} if key else {}

    def _apply_analytic_to_lines(self, force=False):
        """
        Set analytic_distribution on invoice lines.
        force=True: overwrite existing distribution (used by re-apply button).
        """
        self.ensure_one()
        account_ids = self._get_four_level_analytic_accounts()
        if not account_ids:
            return
        distribution = self._build_analytic_distribution(account_ids)
        for line in self.invoice_line_ids:
            if force or not line.analytic_distribution:
                try:
                    line.analytic_distribution = distribution
                except Exception as exc:
                    _logger.warning(
                        "al_shafar_extended: analytic set failed line %s: %s",
                        line.id, exc)

    def _apply_rounding_adjustment(self):
        """
        Round the invoice's total UP to the next whole currency unit
        (ceiling) - e.g. 10.5 -> 11, 110.6 -> 111, 49999.98 -> 50000 -
        by adding one extra line for the difference. Every other line
        (rent, deposit, maintenance, service, tax, ...) keeps its exact
        calculated amount; only the total is adjusted, via this one
        dedicated line.

        Reuses the first existing line's product (and therefore its
        income account) so this needs no new product/account setup -
        the adjustment line posts to the exact same account family the
        rest of the invoice already uses. No tax is applied to it, so
        it can't itself pull the total away from a whole number.

        Idempotent: does nothing if the total is already whole, if a
        rounding line was already added (matched by name), or if the
        invoice is no longer in draft (can't safely add a line to an
        already-posted move here).
        """
        self.ensure_one()
        if self.state != 'draft' or not self.invoice_line_ids:
            return
        if self.invoice_line_ids.filtered(lambda l: l.name == ROUNDING_LINE_NAME):
            return
        total = self.amount_total
        precision = self.currency_id.decimal_places if self.currency_id else 2
        rounded_total = math.ceil(total)
        delta = rounded_total - total
        if delta <= 0.0 or float_is_zero(delta, precision_digits=precision):
            return
        product = self.invoice_line_ids[0].product_id
        # sequence: ribs_real_estate's own action_create_contract
        # (wizard/active_contract.py) later does
        # invoice_line_ids[:-1].write({deferred_start_date/end_date: ...})
        # to apply the contract's period to every line EXCEPT the last
        # one (the deposit line, which shouldn't get deferred-revenue
        # dates). That's a positional assumption - appending this line
        # normally would make IT the new last line instead, and the real
        # deposit line would incorrectly slide into the group that gets
        # written to. A low sequence keeps this line ahead of the
        # existing ones instead, so whichever line was last before
        # (the deposit line) still is.
        self.write({
            'invoice_line_ids': [(0, 0, {
                'name': ROUNDING_LINE_NAME,
                'product_id': product.id if product else False,
                'quantity': 1,
                'price_unit': delta,
                'tax_ids': False,
                'sequence': 1,
            })]
        })
        _logger.info(
            "al_shafar_extended: rounded invoice %s total %s -> %s (+%s)",
            self.id, total, rounded_total, delta)

    def _apply_deferred_period(self):
        """
        More robust re-implementation of the deferred-date sync
        ribs_real_estate's own action_create_contract already attempts
        (wizard/active_contract.py, gated by the exact same setting,
        company.auto_apply_contract_period): that code excludes the
        invoice's LAST line by POSITION (invoice_line_ids[:-1]),
        assuming it's always the deposit line - confirmed broken two
        ways in practice:
          - An invoice with only ONE line (e.g. a Full Payment contract
            with no deposit) has invoice_line_ids[:-1] == empty, so
            NOTHING gets a deferred date at all - there was no real
            "last line to exclude" to begin with.
          - Any line added after the true last line (e.g. this
            module's own rounding-adjustment line, before its sequence
            fix above) becomes the new last line, wrongly letting the
            real deposit line slide into the group that DOES get
            written.

        This instead selects lines by IDENTITY (product_id / name), not
        position, so it's correct no matter how many lines the invoice
        has or what order they're in. Same trigger, same target fields,
        same source dates (tenancy_id.start_date/end_date) as the
        existing logic - only HOW the lines are selected is different.

        Only the property rent line(s) get the contract period - Security
        Deposit, Ejari and every other service line are not deferred
        revenue, so any period already written on them (e.g. by
        ribs_real_estate's positional write) is cleared.
        """
        self.ensure_one()
        tenancy = self.tenancy_id
        if not tenancy or not tenancy.company_id.auto_apply_contract_period:
            return
        if not tenancy.start_date or not tenancy.end_date:
            return
        rent_lines = self._get_rent_lines()
        lines = rent_lines.filtered(
            lambda l: l.deferred_start_date != tenancy.start_date
            or l.deferred_end_date != tenancy.end_date
        )
        if lines:
            lines.write({
                'deferred_start_date': tenancy.start_date,
                'deferred_end_date': tenancy.end_date,
            })
            _logger.info(
                "al_shafar_extended: applied deferred period %s -> %s on %s line(s) of invoice %s",
                tenancy.start_date, tenancy.end_date, len(lines), self.id)
        other_lines = (self.invoice_line_ids - rent_lines).filtered(
            lambda l: l.deferred_start_date or l.deferred_end_date)
        if other_lines:
            other_lines.write({
                'deferred_start_date': False,
                'deferred_end_date': False,
            })

    def _get_rent_lines(self):
        """Property rent lines of a contract invoice: the contract's
        installment product, or a unit's own product on multi-unit
        contracts. A contract with no Installment Item builds its rent
        line without a product, so product-less lines count as rent too
        (deposit / Ejari / service lines always carry their product).
        The rounding line reuses the rent product but is excluded by
        name."""
        self.ensure_one()
        tenancy = self.tenancy_id
        rent_products = tenancy.installment_item_id | tenancy.unit_ids.mapped('default_product_id')
        return self.invoice_line_ids.filtered(
            lambda l: (not l.product_id or l.product_id in rent_products)
            and l.name != ROUNDING_LINE_NAME
        )

    def _sync_analytic_from_rent_line(self):
        """Copy the rent line's analytic distribution to every other line
        (Security Deposit, Ejari, services, rounding) so the whole invoice
        is mapped the same way as the property rent."""
        self.ensure_one()
        rent_line = self._get_rent_lines().filtered('analytic_distribution')[:1]
        if not rent_line:
            return
        distribution = rent_line.analytic_distribution
        lines = self.invoice_line_ids.filtered(
            lambda l: l.analytic_distribution != distribution)
        if lines:
            lines.write({'analytic_distribution': distribution})

    def action_reapply_analytic(self):
        """
        Button on invoice — force re-apply all 4 analytic accounts to all lines.
        Use this for invoices created before the module was installed.
        """
        self.ensure_one()
        self._apply_analytic_to_lines(force=True)
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Analytic Updated',
                'message': 'All 4 analytic accounts re-applied to invoice lines.',
                'type': 'success', 'sticky': False,
            }
        }

    def _strip_archived_cleanup_analytics(self):
        """Drop analytic accounts archived by _cleanup_al_shafar_analytic
        (Property Type / Sub Type accounts like 'Residential', stray
        Building / Units accounts) from the lines' analytic_distribution.
        Entries drafted or duplicated before the cleanup still carry them,
        and posting with an archived analytic account is refused."""
        Account = self.env['account.analytic.account'].sudo().with_context(active_test=False)
        archived = Account.search([
            ('active', '=', False),
            ('root_plan_id.customized_type', 'in', ('property_type', 'sub_type', 'building', 'units')),
        ])
        if not archived:
            return
        archived_ids = {str(acc_id) for acc_id in archived.ids}
        for line in self.line_ids.filtered('analytic_distribution'):
            new_dist, changed = {}, False
            for key, percent in line.analytic_distribution.items():
                ids = [part for part in str(key).split(',') if part.strip()]
                kept = [part for part in ids if part.strip() not in archived_ids]
                if len(kept) != len(ids):
                    changed = True
                if kept:
                    new_key = ','.join(kept)
                    new_dist[new_key] = new_dist.get(new_key, 0.0) + percent
            if changed:
                line.analytic_distribution = new_dist or False
        # Lines left without Building / Unit get them back from the contract.
        for move in self:
            if move.move_type in ('out_invoice', 'out_receipt') and move.tenancy_id:
                move._apply_analytic_to_lines(force=False)

    def _post(self, soft=True):
        self._strip_archived_cleanup_analytics()
        return super()._post(soft=soft)

    @api.model_create_multi
    def create(self, vals_list):
        result = super().create(vals_list)
        # Ensure all existing sub types are mapped before applying analytic
        self.env['property.sub.type']._backfill_all_subtypes()
        for move in result:
            if move.move_type in ('out_invoice', 'out_receipt') and move.tenancy_id:
                try:
                    # force=True: always overwrite any analytic Odoo auto-set
                    # (e.g. the project-level 'RESIDENTIAL PLAN' account)
                    move._apply_analytic_to_lines(force=True)
                    move._sync_analytic_from_rent_line()
                except Exception as exc:
                    _logger.warning(
                        "al_shafar_extended: analytic auto-fill failed invoice %s: %s",
                        move.id, exc)
                # No rounding adjustment line: the invoice carries the exact
                # rent (see _apply_rounding_adjustment, no longer called).
                try:
                    move._apply_deferred_period()
                except Exception as exc:
                    _logger.warning(
                        "al_shafar_extended: deferred period sync failed invoice %s: %s",
                        move.id, exc)
        return result

    def write(self, vals):
        result = super().write(vals)
        if 'tenancy_id' in vals:
            for move in self:
                if move.move_type in ('out_invoice', 'out_receipt') and move.tenancy_id:
                    try:
                        # force=True: overwrite any stale/project analytic distribution
                        move._apply_analytic_to_lines(force=True)
                        move._sync_analytic_from_rent_line()
                    except Exception as exc:
                        _logger.warning(
                            "al_shafar_extended: analytic re-apply failed %s: %s",
                            move.id, exc)
                    try:
                        move._apply_deferred_period()
                    except Exception as exc:
                        _logger.warning(
                            "al_shafar_extended: deferred period sync failed invoice %s: %s",
                            move.id, exc)
        return result


# ─────────────────────────────────────────────────────────────────────────────
class AccountMoveLine(models.Model):
    """Business decision: analytic distribution must never block posting
    an invoice/bill line, however it resolves (fully, partially, or not
    at all). Relaxing every plan's Applicability to 'optional'
    (AccountAnalyticPlan._ensure_optional_applicability) still left
    Odoo's own hardcoded check in analytic.mixin (the mixin
    account.move.line inherits, in core's addons/analytic module)
    raising "One or more lines require a 100% analytic distribution." on
    post - that check runs independently of the Applicability config in
    some cases, so this overrides it directly instead, scoped to
    account.move.line only.

    Deliberately does NOT touch analytic.mixin itself. The same bypass for
    purchase.order.line / purchase.request.line lives in purchase_extended
    (models/analytic_distribution.py); quotations and sales orders keep
    Odoo's normal analytic validation.
    """
    _inherit = 'account.move.line'

    def _validate_distribution(self, **kwargs):
        return

    @api.constrains('analytic_distribution')
    def _check_analytic_distribution_max_100(self):
        """Under 100% per plan is allowed (see _validate_distribution
        above), but no plan column (Building, Unit, AR Type, Cost Center,
        Sub Cost Center) may total more than 100%."""
        Account = self.env['account.analytic.account'].sudo().with_context(active_test=False)
        for line in self.filtered('analytic_distribution'):
            plan_totals = {}
            for key, percent in line.analytic_distribution.items():
                ids = [int(part) for part in str(key).split(',') if part.strip().isdigit()]
                for account in Account.browse(ids).exists():
                    plan = account.root_plan_id
                    plan_totals[plan] = plan_totals.get(plan, 0.0) + (percent or 0.0)
            for plan, total in plan_totals.items():
                if float_compare(total, 100.0, precision_digits=2) > 0:
                    raise ValidationError(_(
                        "Analytic distribution for '%(plan)s' is %(total)s%% on line "
                        "'%(line)s'. Please enter 100%% or below.",
                        plan=plan.name, total=round(total, 2), line=line.name or line.display_name,
                    ))


# ─────────────────────────────────────────────────────────────────────────────
class AccountAnalyticAccountCleanup(models.Model):
    _inherit = 'account.analytic.account'

    @api.model
    def _al_shafar_used_account_ids(self):
        """Analytic account ids referenced by any analytic_distribution (every
        table that has the column - invoice/bill/journal lines, PO/PR/SO
        lines, ...) or by an analytic line. Those keep their history, so they
        are archived instead of deleted."""
        cr = self.env.cr
        used = set()
        cr.execute("""
            SELECT table_name FROM information_schema.columns
            WHERE table_schema = current_schema()
              AND column_name = 'analytic_distribution' AND data_type = 'jsonb'
        """)
        for (table,) in cr.fetchall():
            cr.execute('SELECT DISTINCT jsonb_object_keys(analytic_distribution) FROM "%s" '
                       'WHERE analytic_distribution IS NOT NULL' % table)
            for (key,) in cr.fetchall():
                used.update(int(part) for part in key.split(',') if part.strip().isdigit())
        # account_analytic_line: account_id + one x_plan<N>_id column per plan
        cr.execute("""
            SELECT column_name FROM information_schema.columns
            WHERE table_schema = current_schema() AND table_name = 'account_analytic_line'
              AND (column_name = 'account_id' OR column_name ~ '^x_plan[0-9]+_id$')
        """)
        for (column,) in cr.fetchall():
            cr.execute('SELECT DISTINCT "%s" FROM account_analytic_line WHERE "%s" IS NOT NULL'
                       % (column, column))
            used.update(row[0] for row in cr.fetchall())
        return used

    @api.model
    def _cleanup_al_shafar_analytic(self):
        """One-time cleanup (run by the 18.0.1.0.56 migration, safe to re-run).

        Keeps 5 analytic plans: Building, Units, AR Type, Cost Center and Sub
        Cost Center.
          - Building: only the account linked to each real building.
          - Units: only the account linked to each real unit, renamed to its
            Property Code.
          - Property Type / Sub Type plans: every account removed, links on
            buildings / sub types / property types cleared, then the plans
            themselves deleted if nothing is left in them.
        An account that is already used (see _al_shafar_used_account_ids) or
        still referenced elsewhere is archived instead of deleted.
        AR Type / Cost Center / Sub Cost Center are not touched.
        """
        Account = self.sudo().with_context(active_test=False)
        Plan = self.env['account.analytic.plan'].sudo()
        cr = self.env.cr

        # 1. Every building / unit has its own, correctly named account.
        buildings = self.env['property.project'].sudo().with_context(active_test=False).search([])
        for building in buildings:
            building._setup_building_analytic()
        units = self.env['property.details'].sudo().with_context(active_test=False).search([], order='id')
        # Units sharing one account (same code/name): the oldest keeps it, the
        # others are detached so they get their own below.
        owner_by_account, split = {}, self.env['property.details']
        for unit in units.filtered('unit_account_id'):
            if unit.unit_account_id.id in owner_by_account:
                split |= unit
            else:
                owner_by_account[unit.unit_account_id.id] = unit
        if split:
            cr.execute("UPDATE property_details SET unit_account_id = NULL WHERE id IN %s", (tuple(split.ids),))
            units.invalidate_recordset(['unit_account_id'])
        for unit in units:
            unit._setup_unit_analytic()
        self.env.flush_all()
        units.invalidate_recordset(['unit_account_id'])
        missing = units.filtered(lambda u: not u.unit_account_id)
        _logger.info(
            "al_shafar_extended: analytic cleanup - %s units, %s split from a shared account, "
            "%s without a building, %s still without an account %s",
            len(units), len(split), len(units.filtered(lambda u: not u.property_project_id)),
            len(missing), missing.mapped('display_name')[:50])

        keep_ids = set(buildings.mapped('building_account_id').ids) | set(units.mapped('unit_account_id').ids)

        def plan_tree(customized_type):
            plans = Plan.search([('customized_type', '=', customized_type)])
            return Plan.search([('id', 'child_of', plans.ids)]) if plans else Plan

        building_units_plans = plan_tree('building') | plan_tree('units')
        removed_plans = plan_tree('property_type') | plan_tree('sub_type')

        candidates = Account.search([
            '|',
            '&', ('plan_id', 'in', building_units_plans.ids), ('id', 'not in', list(keep_ids)),
            ('plan_id', 'in', removed_plans.ids),
        ])

        # 2. Clear links to the Property Type / Sub Type accounts.
        cr.execute("UPDATE property_project SET property_type_account_id = NULL "
                   "WHERE property_type_account_id IS NOT NULL")
        cr.execute("UPDATE property_sub_type SET subtype_account_id = NULL "
                   "WHERE subtype_account_id IS NOT NULL")
        cr.execute("UPDATE residential_type SET analytic_account_id = NULL, analytic_plan_id = NULL "
                   "WHERE analytic_account_id IS NOT NULL OR analytic_plan_id IS NOT NULL")
        self.env.invalidate_all()

        # 3. Delete unused, archive the rest.
        used = self._al_shafar_used_account_ids()
        deleted, archived = [], []
        for account in candidates:
            name = account.display_name
            if account.id not in used:
                try:
                    with cr.savepoint():
                        account.unlink()
                    deleted.append(name)
                    continue
                except Exception as exc:
                    _logger.info("al_shafar_extended: analytic account '%s' still referenced (%s) - archiving",
                                 name, exc)
            if account.exists() and account.active:
                account.write({'active': False})
                archived.append(name)

        # 4. Drop the Property Type / Sub Type plans once empty (children first).
        dropped_plans = []
        for plan in removed_plans.sorted(lambda p: len(p.parent_path or ''), reverse=True):
            if Account.search_count([('plan_id', '=', plan.id)]):
                continue
            plan_name = plan.name
            try:
                with cr.savepoint():
                    plan.unlink()
                dropped_plans.append(plan_name)
            except Exception as exc:
                _logger.warning("al_shafar_extended: could not delete analytic plan '%s': %s", plan_name, exc)

        _logger.info(
            "al_shafar_extended: analytic cleanup - kept %s building/unit accounts, deleted %s, "
            "archived %s, dropped plans %s",
            len(keep_ids), len(deleted), len(archived), dropped_plans)
        return {'kept': len(keep_ids), 'deleted': deleted, 'archived': archived, 'dropped_plans': dropped_plans}
