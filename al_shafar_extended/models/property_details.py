# -*- coding: utf-8 -*-

from odoo import models, fields, api, _

class PropertyDetails(models.Model):
    _inherit = 'property.details'

    deposit_basis = fields.Selection([
        ('rent', 'Rent Value'),
        ('contract', 'Contract Value'),
    ], string="Deposit Basis", default='rent',
       help="Base amount the Deposit % is applied on when a contract is created:\n"
            "- Rent Value: Deposit % of the unit's Yearly Rent (current behavior).\n"
            "- Contract Value: Deposit % of the specific contract's total Contract Value.")

    multi_contract_ids = fields.Many2many(
        'tenancy.details',
        relation='property_details_tenancy_details_rel',
        column1='property_details_id',
        column2='tenancy_details_id',
        string="Multi Contracts",
        domain=[('is_multi_contract', '=', True)]
    )
    multi_contract_count = fields.Integer(
        string="Multi Contracts Count",
        compute="_compute_multi_contract_count"
    )

    unit_m_size = fields.Float(
        string="Unit M Size",
        compute="_compute_unit_m_size",
        store=True,
        digits=(12, 4),
        help="Cross-unit conversion of Total Area, using the "
             "'1 sq.m = ? sq.ft' ratio configured in Settings:\n"
             "- Area Measurement Unit = sq.m: Total Area converted to sq.ft.\n"
             "- Area Measurement Unit = sq.ft: Total Area converted to sq.m.\n"
             "- Any other Area Measurement Unit (sq.yd, cu.ft, cu.m): 0, "
             "since the configured ratio only applies to sq.m / sq.ft.\n"
             "Recalculates automatically whenever Total Area, the Area "
             "Measurement Unit, or the conversion ratio in Settings change."
    )

    unit_size_sqm = fields.Float(
        string="Unit Size (Sq.M)",
        digits=(12, 4),
        help="Enter the Unit Size in square meters. It is automatically "
             "multiplied by the '1 sq.m = ? sq.ft' ratio configured in "
             "Settings (default 10.7639) and written into the 'Unit Size' "
             "field, which always stores the value in sq.ft."
    )

    @api.onchange('unit_size_sqm')
    def _onchange_unit_size_sqm(self):
        for rec in self:
            if rec.unit_size_sqm:
                ratio = rec.company_id.sqm_to_sqft_ratio or 10.7639
                rec.unit_size = rec.unit_size_sqm * ratio

    @api.depends('multi_contract_ids')
    def _compute_multi_contract_count(self):
        for rec in self:
            rec.multi_contract_count = len(rec.multi_contract_ids)

    @api.depends('total_area', 'measure_unit', 'company_id.sqm_to_sqft_ratio')
    def _compute_unit_m_size(self):
        for rec in self:
            ratio = rec.company_id.sqm_to_sqft_ratio
            if rec.measure_unit == 'sq_m':
                # sq.m -> sq.ft
                rec.unit_m_size = rec.total_area * ratio
            elif rec.measure_unit == 'sq_ft' and ratio:
                # sq.ft -> sq.m
                rec.unit_m_size = rec.total_area / ratio
            else:
                rec.unit_m_size = 0.0

    @api.model
    def get_property_stats(self):
        """Extends rental_management's dashboard data with the "Portfolio
        Overview" tiles (see al_shafar_extended/static/src/xml/
        rental_dashboard_portfolio_overview.xml): total properties
        (Buildings)/units/parking, and units/parking currently available
        vs. occupied. Existing keys/behavior from the base method are
        untouched."""
        data = super().get_property_stats()
        company_domain = [('company_id', 'in', self.env.companies.ids)]

        # Fix "Expiring Soon" (the 'close_contract' key, shown on the
        # "Rent Contract Statics" row): the base method computes it as
        # ANY contract with 1-120 days left, regardless of contract_type -
        # a different, narrower definition than "Expiring Soon" everywhere
        # else on this dashboard (contract_type = 'expiring_soon', set by
        # tenancy.details.tenancy_expire() up to 180 days out - see the
        # "Expiring Soon Contracts" bucket section and the mini Contracts/
        # Status widget above the All Contracts list, both of which
        # already use contract_type = 'expiring_soon' and therefore show
        # the correct total). Recomputed here so Active (311) + Expiring
        # Soon + Expired (25) actually sum to Total Contracts, instead of
        # silently disagreeing with every other "Expiring Soon" figure on
        # the same page.
        data['close_contract'] = self.env['tenancy.details'].sudo().search_count(
            [('contract_type', '=', 'expiring_soon')] + company_domain)
        # A parking unit is a property.details record whose Sub Type is
        # "Parking" (Configurations > Types > Property Sub-Types) - a
        # user-created record with no fixed id, matched by name. This is
        # a completely separate concept from parking.slots/
        # parking.allocation (the amenity-slot assignment used on
        # regular residential/commercial units via parking_ids) - that
        # model is not used for this section at all.
        parking_subtype_domain = [('property_subtype_id.name', 'ilike', 'parking')]

        property_obj = self.env['property.details'].sudo()
        project_obj = self.env['property.project'].sudo()

        data['total_properties_count'] = project_obj.search_count(company_domain)
        data['total_units_count'] = property_obj.search_count(company_domain)
        data['total_parking_units_count'] = property_obj.search_count(
            parking_subtype_domain + company_domain)
        data['available_units_count'] = property_obj.search_count(
            [('stage', '=', 'available')] + company_domain)

        occupied_units = property_obj.search([('stage', '=', 'on_lease')] + company_domain)
        data['occupied_units_count'] = len(occupied_units)
        data['occupied_parking_units_count'] = property_obj.search_count(
            parking_subtype_domain + [('stage', '=', 'on_lease')] + company_domain)

        # Normal Units / Parking Units cards (Portfolio Overview): each
        # needs its own total/on-rent/available split - the counts above
        # mix both subtypes together (occupied_units_count/available_units_
        # count count every unit regardless of subtype), so Normal-only
        # figures aren't otherwise available.
        not_parking_subtype_domain = [('property_subtype_id.name', 'not ilike', 'parking')]
        data['normal_units_count'] = property_obj.search_count(
            not_parking_subtype_domain + company_domain)
        data['available_normal_units_count'] = property_obj.search_count(
            [('stage', '=', 'available')] + not_parking_subtype_domain + company_domain)
        data['available_parking_units_count'] = property_obj.search_count(
            [('stage', '=', 'available')] + parking_subtype_domain + company_domain)
        data['occupied_normal_units_count'] = property_obj.search_count(
            [('stage', '=', 'on_lease')] + not_parking_subtype_domain + company_domain)

        # Single-Unit vs Multi-Unit CONTRACTS, split by Normal/Parking -
        # per contract, matching the "Total Contracts" grouped card's
        # single_unit_contracts_total_count/multi_unit_contracts_total_count
        # (so Normal + Parking sums back to those totals: 638+7=645,
        # 34+5=39). A previous version of this counted UNITS instead of
        # CONTRACTS for the multi-unit side (every unit in
        # tenancy.details.unit_ids across ALL multi-contracts), which
        # massively over-counted since one multi-contract spans many
        # units - e.g. showing 694 instead of 34.
        #
        # A single contract has exactly one unit (property_id), so
        # classifying it by that unit's subtype is unambiguous. A multi
        # contract can genuinely mix Normal and Parking units (e.g. a
        # couple of apartments plus a few parking slots bundled in one
        # lease) - it only counts as Parking if ALL of its units are
        # parking-subtype; a contract with even one non-parking unit
        # counts as Normal. Every contract still lands in exactly one
        # bucket, so Normal + Parking always adds up to the contract-level
        # total (see rental_dashboard_portfolio_overview.js
        # classifyContractsByType for the matching click-through logic -
        # keep both in sync if this rule ever changes).
        # Closed contracts (contract_type='close_contract' - set when a
        # contract is superseded by a renewal, not the same thing as
        # "Expired") are excluded from every contract count on this
        # dashboard, so Total Contracts always equals Running + Expiring
        # Soon + Expired (+ Draft/Cancelled, if any) and the Single/Multi
        # breakdowns stay consistent with it.
        not_closed_domain = [('contract_type', '!=', 'close_contract')]

        tenancy_obj = self.env['tenancy.details'].sudo()
        single_contracts = tenancy_obj.search(
            [('is_multi_contract', '=', False), ('property_id', '!=', False)]
            + not_closed_domain + company_domain)
        multi_contracts = tenancy_obj.search(
            [('is_multi_contract', '=', True)] + not_closed_domain + company_domain)

        def _is_parking(unit):
            return bool(unit.property_subtype_id and 'parking' in (unit.property_subtype_id.name or '').lower())

        normal_single = single_contracts.filtered(lambda c: not _is_parking(c.property_id))
        parking_single = single_contracts.filtered(lambda c: _is_parking(c.property_id))
        # A multi-contract genuinely can mix Normal and Parking units (e.g.
        # a couple of apartments plus a few parking slots bundled in one
        # lease) - classifying by the first unit alone put some mixed
        # contracts in the wrong bucket. Only count a contract as Parking
        # if ALL of its units are parking-subtype; any contract with at
        # least one non-parking unit counts as Normal.
        parking_multi = multi_contracts.filtered(
            lambda c: c.unit_ids and all(_is_parking(u) for u in c.unit_ids))
        normal_multi = multi_contracts - parking_multi

        data['normal_single_unit_contracts_count'] = len(normal_single)
        data['normal_multi_unit_contracts_count'] = len(normal_multi)
        data['parking_single_unit_contracts_count'] = len(parking_single)
        data['parking_multi_unit_contracts_count'] = len(parking_multi)

        # "Rent Contract Statics" section: the base method already
        # returns draft_contract/running_contract/expire_contract - only
        # the grand total across every contract is new here. Excludes
        # closed contracts (see not_closed_domain above) so this equals
        # Running + Expiring Soon + Expired (+ Draft/Cancelled, if any).
        data['total_contracts_count'] = tenancy_obj.search_count(
            not_closed_domain + company_domain)

        # "Total Contracts" grouped card breakdown: per-contract (not
        # per-unit) Single/Multi count, excluding closed contracts, split
        # by is_multi_contract.
        data['single_unit_contracts_total_count'] = tenancy_obj.search_count(
            [('is_multi_contract', '=', False)] + not_closed_domain + company_domain)
        data['multi_unit_contracts_total_count'] = tenancy_obj.search_count(
            [('is_multi_contract', '=', True)] + not_closed_domain + company_domain)

        # "Documents Expired" (Action Required): same partner.documents
        # model/verified_status field the base method's own
        # 'unapproved_documents' ('pending') already uses - just the
        # 'expired' bucket instead, set by tenancy.details.
        # check_expiring_documents() whenever a document's expiry_date has
        # passed.
        data['documents_expired_count'] = self.env['partner.documents'].sudo().search_count(
            [('verified_status', '=', 'expired')])

        # "Expiring Soon Contracts" section: non-overlapping day-range
        # buckets, so every expiring_soon contract lands in exactly one
        # tile and the 7 tiles sum to the total instead of each tile
        # re-counting the same contracts (as the old cumulative "days_left
        # <= N" thresholds did). Reuses the exact same bucket definitions
        # as the other "Expiring Soon" widget (the mini bar above the All
        # Contracts list - see tenancy.details._EXPIRING_SOON_DAY_BUCKETS
        # and retrieve_contract_list_dashboard_data), so both dashboards
        # agree on what "0-60 / 60-90 / ... / 160+" mean.
        tenancy_obj = self.env['tenancy.details'].sudo()
        expiring_soon_domain = [('contract_type', '=', 'expiring_soon')] + company_domain
        for key, extra_domain in tenancy_obj._EXPIRING_SOON_DAY_BUCKETS:
            data[f'{key}_count'] = tenancy_obj.search_count(expiring_soon_domain + extra_domain)

        return data

    def action_view_multi_contracts(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Multi Contracts'),
            'res_model': 'tenancy.details',
            'domain': [('id', 'in', self.multi_contract_ids.ids)],
            'view_mode': 'list,form',
            'target': 'current',
            'context': {'create': False},
        }
