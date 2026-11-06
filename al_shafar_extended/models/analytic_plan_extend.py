# -*- coding: utf-8 -*-
# Extend the customized_type selection on account.analytic.plan
# to add 'sub_type' as a valid value.
import logging
import re

from odoo import models, fields, api

_logger = logging.getLogger(__name__)


def _normalize_cost_center_key(name):
    """'G&A' / 'Sales & Marketing' / 'SalesMarketing' all fold to the same
    key, so the 'Cost Center' plan's hand-typed account names (e.g. 'G&A')
    can be matched against the 'Sub Cost Center' department plan names
    (e.g. 'GA') without depending on either side's exact spelling."""
    return re.sub(r'[^A-Z0-9]', '', (name or '').upper())

# The Al-Shafar analytic plan types shown as columns on the analytic
# distribution widget — identified by customized_type, in the left-to-right
# order they should display. 'property_type' and 'sub_type' used to be
# included too (4 plans, for 7 total with the 3 extra ones below) but were
# dropped from the widget on request - Building/Unit + the 3 extra plans is
# now the full column set (5 total). The 'property_type'/'sub_type' plans,
# accounts and auto-mapping (ResidentialType, PropertySubType) below are left
# in place (still used elsewhere, e.g. residential_type_id on the building)
# - only their appearance in this widget and in the auto-filled invoice-line
# distribution (see AccountMove._get_four_level_analytic_accounts) was
# removed.
_ALSHAFAR_PLAN_TYPES_ORDERED = ['building', 'units']

# 3 additional plans shown in invoices — identified by exact name (no
# customized_type set), in display order. Sub Cost Center is last, right
# after Cost Center, on purpose - it's the newest/most specific of the two.
_EXTRA_PLAN_NAMES_ORDERED = ['AR Type', 'Cost Center', 'Sub Cost Center']

# 'Sub Cost Center' root plan -> one child plan per department -> its flat
# list of analytic accounts. Unlike AR Type/Cost Center (created by hand,
# never reproduced by code), this one IS reproduced by _ensure_sub_cost_center
# below so it exists the same way on every environment, not just wherever it
# was first typed in through the UI.
_SUB_COST_CENTER_STRUCTURE = {
    'Operation': [
        'Cleaning & Janitization', 'Construction', 'Designing', 'Development',
        'Engineering', 'Installation', 'Leasing', 'Logistics',
        'Maintenance - Electrical', 'Maintenance - Mechanical', 'Maintenance - Plumbing',
        'Management', 'Marketing', 'Procurement', 'Security Services',
    ],
    'GA': ['Accounts', 'Admin', 'Directors', 'HR', 'IT', 'Management'],
    'SalesMarketing': ['E-Commerce', 'Marketing', 'Sales'],
}


class AccountAnalyticPlan(models.Model):
    _inherit = 'account.analytic.plan'

    customized_type = fields.Selection(
        selection_add=[('sub_type', 'Sub Type')],
        ondelete={'sub_type': 'set null'},
    )

    @api.model
    def get_relevant_plans(self, **kwargs):
        """
        Override to restrict the analytic widget columns on invoices to:
          - The 2 Al-Shafar plans: Building, Units
          - AR Type  (5 accounts: Contract, Legal action fees, Return cheques, VAT, Withdraw cheques)
          - Cost Center  (3 accounts: G&A, Operation, Sales & Marketing)
          - Sub Cost Center  (3 sub-plans: Operation, GA, SalesMarketing, each with its own accounts)
        All other plans (Property Type, Sub Type, PROJECT, RESIDENTIAL PLAN, RIBS, etc.) are hidden.
        """
        all_plans = super().get_relevant_plans(**kwargs)

        # The 4 customized_type Al-Shafar plans, ranked by their type's position
        # in _ALSHAFAR_PLAN_TYPES_ORDERED - keyed off customized_type, not name,
        # since an existing plan can carry a different display name than
        # whatever _get_plan() would use as a fresh-create default (e.g. this
        # DB's "units" plan is named "Unit", not "Units").
        alshafar_plans = self.sudo().search([
            ('customized_type', 'in', _ALSHAFAR_PLAN_TYPES_ORDERED),
            ('parent_id', '=', False),
        ])
        alshafar_rank = {
            plan.id: _ALSHAFAR_PLAN_TYPES_ORDERED.index(plan.customized_type)
            for plan in alshafar_plans
        }

        # AR Type / Cost Center / Sub Cost Center - no customized_type, so these
        # can only be matched (and ranked) by exact name.
        extra_plans = self.sudo().search([
            ('name', 'in', _EXTRA_PLAN_NAMES_ORDERED),
            ('parent_id', '=', False),
        ])
        base = len(_ALSHAFAR_PLAN_TYPES_ORDERED)
        extra_rank = {
            plan.id: base + _EXTRA_PLAN_NAMES_ORDERED.index(plan.name)
            for plan in extra_plans
        }

        rank = {**alshafar_rank, **extra_rank}

        filtered = [p for p in all_plans if p['id'] in rank]
        filtered.sort(key=lambda p: rank[p['id']])
        return filtered

    @api.model
    def _ensure_sub_cost_center(self):
        """
        Idempotent setup for the 'Sub Cost Center' analytic plan: a root plan
        with one child plan per department (Operation / GA / SalesMarketing),
        each holding its own flat list of analytic accounts (see
        _SUB_COST_CENTER_STRUCTURE above).

        Each of those accounts also gets cost_center_account_id set to the
        matching account under the (hand-created) 'Cost Center' plan - e.g.
        every account under the 'GA' department plan points at the 'G&A'
        Cost Center account - so the analytic widget can filter Sub Cost
        Center choices by the Cost Center picked on the same line, the same
        way it already filters Unit choices by Building
        (analytic_distribution_extend.js).

        Called via a <function> tag in data/init_sub_cost_center.xml, which
        is NOT gated by noupdate - it runs on every module install/upgrade,
        on every environment (dev/staging/production), so this plan exists
        the same way everywhere instead of only wherever someone happened to
        set it up by hand once. Search-then-create at every level, so re-
        running it (e.g. on an environment that already has it) is a no-op.
        """
        Plan = self.env['account.analytic.plan'].sudo()
        Account = self.env['account.analytic.account'].sudo()

        root = Plan.search([('name', '=', 'Sub Cost Center'), ('parent_id', '=', False)], limit=1)
        if not root:
            root = Plan.create({'name': 'Sub Cost Center'})
            _logger.info("al_shafar_extended: created analytic plan 'Sub Cost Center' (id=%s)", root.id)

        # 'Cost Center' plan/accounts are created by hand (not by this
        # module) - match its accounts to a Sub Cost Center department by
        # normalized name ('G&A' <-> 'GA', 'Sales & Marketing' <-> 'SalesMarketing').
        cost_center_plan = Plan.search([('name', '=', 'Cost Center'), ('parent_id', '=', False)], limit=1)
        cost_center_by_key = {}
        if cost_center_plan:
            for acc in Account.search([('plan_id', '=', cost_center_plan.id)]):
                cost_center_by_key[_normalize_cost_center_key(acc.name)] = acc
        else:
            _logger.warning(
                "al_shafar_extended: no 'Cost Center' plan found - Sub Cost Center accounts "
                "won't be filtered by Cost Center in the analytic widget until it exists.")

        for sub_name, account_names in _SUB_COST_CENTER_STRUCTURE.items():
            sub_plan = Plan.search([('name', '=', sub_name), ('parent_id', '=', root.id)], limit=1)
            if not sub_plan:
                sub_plan = Plan.create({'name': sub_name, 'parent_id': root.id})
                _logger.info(
                    "al_shafar_extended: created analytic sub-plan '%s' under Sub Cost Center (id=%s)",
                    sub_name, sub_plan.id)

            cost_center_account = cost_center_by_key.get(_normalize_cost_center_key(sub_name))
            if cost_center_plan and not cost_center_account:
                _logger.warning(
                    "al_shafar_extended: no 'Cost Center' account matches Sub Cost Center "
                    "department '%s' - link cost_center_account_id by hand on its accounts.",
                    sub_name)

            for acc_name in account_names:
                exists = Account.search([('name', '=', acc_name), ('plan_id', '=', sub_plan.id)], limit=1)
                if not exists:
                    exists = Account.create({'name': acc_name, 'plan_id': sub_plan.id})
                    _logger.info(
                        "al_shafar_extended: created analytic account '%s' under '%s'",
                        acc_name, sub_name)
                if cost_center_account and exists.cost_center_account_id.id != cost_center_account.id:
                    exists.write({'cost_center_account_id': cost_center_account.id})

        # Run archive & link self-healing
        self._ensure_analytic_clean_and_linked()

    @api.model
    def _ensure_analytic_clean_and_linked(self):
        """
        Synchronize building_account_id on all unit analytic accounts from
        property.details -> property.project -> building_account_id.
        """
        self.env.cr.execute("""
            UPDATE account_analytic_account aa
            SET building_account_id = pp.building_account_id
            FROM property_details pd
            JOIN property_project pp ON pd.property_project_id = pp.id
            WHERE pd.unit_account_id = aa.id
              AND pp.building_account_id IS NOT NULL
              AND (aa.building_account_id IS NULL OR aa.building_account_id != pp.building_account_id);
        """)
        _logger.info("al_shafar_extended: synchronized building_account_id on unit accounts")

    @api.model
    def get_relevant_plans(self, **kwargs):
        """
        Override to restrict the analytic widget columns on invoices to:
          - The 2 Al-Shafar plans: Building, Units
          - AR Type  (5 accounts: Contract, Legal action fees, Return cheques, VAT, Withdraw cheques)
          - Cost Center  (3 accounts: G&A, Operation, Sales & Marketing)
          - Sub Cost Center  (3 sub-plans: Operation, GA, SalesMarketing, each with its own accounts)
        All other plans (Property Type, Sub Type, PROJECT, RESIDENTIAL PLAN, RIBS, etc.) are hidden.
        """
        all_plans = super().get_relevant_plans(**kwargs)

        # The customized_type Al-Shafar plans (Building, Units)
        alshafar_plans = self.sudo().search([
            ('customized_type', 'in', _ALSHAFAR_PLAN_TYPES_ORDERED),
            ('parent_id', '=', False),
        ])
        alshafar_rank = {
            plan.id: _ALSHAFAR_PLAN_TYPES_ORDERED.index(plan.customized_type)
            for plan in alshafar_plans
        }

        # AR Type / Cost Center / Sub Cost Center
        extra_plans = self.sudo().search([
            ('name', 'in', _EXTRA_PLAN_NAMES_ORDERED),
            ('parent_id', '=', False),
        ])
        base = len(_ALSHAFAR_PLAN_TYPES_ORDERED)
        extra_rank = {
            plan.id: base + _EXTRA_PLAN_NAMES_ORDERED.index(plan.name)
            for plan in extra_plans
        }

        rank = {**alshafar_rank, **extra_rank}

        # Build plan types mapping for customized_type (used by frontend JS)
        plan_types = {p.id: p.customized_type for p in alshafar_plans}

        filtered = [p for p in all_plans if p['id'] in rank]
        for p in filtered:
            p['customized_type'] = plan_types.get(p['id'])
        filtered.sort(key=lambda p: rank[p['id']])
        return filtered

    @api.model
    def _ensure_optional_applicability(self):
        """
        Business decision: NO analytic plan should ever block posting an
        invoice/bill - whether all 4 Al-Shafar levels (Property Type, Sub
        Type, Building, Units) resolve or not, and regardless of any
        other plan (AR Type, Cost Center, Sub Cost Center, or anything
        added later) being partially or fully unfilled. Odoo's own
        posting validation ("One or more lines require a 100% analytic
        distribution") only fires for plans whose Applicability is set to
        Mandatory, so every Applicability rule, on every plan, company,
        and business domain, is forced to 'optional' here - not scoped to
        the 4 Al-Shafar plans only, since a Mandatory rule on ANY other
        plan (e.g. AR Type/Cost Center/Sub Cost Center, which are never
        auto-filled by account_move.py at all) blocks posting just the
        same.

        Idempotent - a no-op once every rule is already optional. Called
        via a <function> tag (data/ensure_analytic_optional.xml) with no
        noupdate, so this self-heals on every install/upgrade regardless
        of whether a Mandatory rule was set (or reset) by hand, on this
        plan or any other, before or after this ran.
        """
        mandatory_rules = self.env['account.analytic.applicability'].sudo().search([
            ('applicability', '=', 'mandatory'),
        ])
        if mandatory_rules:
            plan_names = mandatory_rules.mapped('analytic_plan_id.name')
            mandatory_rules.write({'applicability': 'optional'})
            _logger.info(
                "al_shafar_extended: relaxed %s analytic applicability rule(s) "
                "from mandatory to optional across plans %s",
                len(mandatory_rules), plan_names)


# -----------------------------------------------------------------------------
class AccountAnalyticAccount(models.Model):
    """
    Extend AccountAnalyticAccount with building_account_id to establish
    the direct hierarchy between unit accounts and building accounts, and
    with cost_center_account_id for the same kind of link between a Sub
    Cost Center account and its parent Cost Center account.
    """
    _inherit = 'account.analytic.account'

    building_account_id = fields.Many2one(
        'account.analytic.account',
        string='Building Analytic Account',
        index=True,
        ondelete='set null',
        domain="[('plan_id.customized_type', '=', 'building')]",
        help="Building analytic account this unit belongs to.",
    )
    unit_account_ids = fields.One2many(
        'account.analytic.account',
        'building_account_id',
        string='Unit Analytic Accounts',
    )

    cost_center_account_id = fields.Many2one(
        'account.analytic.account',
        string='Cost Center Analytic Account',
        index=True,
        ondelete='set null',
        domain="[('plan_id.name', '=', 'Cost Center'), ('plan_id.parent_id', '=', False)]",
        help="Cost Center analytic account this Sub Cost Center account belongs to. "
             "Auto-linked by department for the accounts under the 'Sub Cost Center' "
             "plan (see AccountAnalyticPlan._ensure_sub_cost_center); set by hand for any other.",
    )
    sub_cost_center_account_ids = fields.One2many(
        'account.analytic.account',
        'cost_center_account_id',
        string='Sub Cost Center Analytic Accounts',
    )

