# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import ValidationError


class GroupMultiContractsSplit(models.Model):
    """Extend Multi Contract Wizard: Add Single vs Split option"""
    _inherit = 'group.multi.contracts'

    split_into_units = fields.Boolean(
        string="Split into Unit Contracts",
        default=False,
        help=(
            "If checked, a SEPARATE contract is created for each selected unit "
            "using that unit's individual rent amount.\n"
            "If unchecked (default), a SINGLE combined contract is created for "
            "all units with the total rent amount."
        )
    )

    # Only available units of the building (on-lease units stay
    # selectable when renewing an existing contract).
    unit_ids = fields.Many2many(
        domain="[('property_project_id', '=', property_id), '|', ('stage', '=', 'available'),"
               " ('stage', '=', is_from_existing_contract and 'on_lease' or 'available')]")

    @api.depends(
        "unit_line_ids.total",
        "unit_line_ids.discount_amount",
        "unit_line_ids.total_rent_year",
        "unit_ids",
        "unit_ids.price_yearly",
    )
    def _compute_totals(self):
        """Rent typed on a unit line (e.g. a unit with zero rent) drives
        Total Rent instead of the unit's own price_yearly."""
        # A Total Rent typed in the wizard is kept while no unit line
        # carries a rent of its own.
        typed = {rec.id: rec.total_rent_year for rec in self}
        super()._compute_totals()
        for rec in self:
            line_rent = sum(rec.unit_line_ids.mapped('total_rent_year'))
            if rec.overall_discount:
                continue
            rec.total_rent_year = line_rent or typed.get(rec.id) or rec.total_rent_year

    @api.onchange('unit_line_ids')
    def _onchange_unit_line_rent(self):
        for rec in self:
            if not rec.unit_line_ids:
                continue
            line_rent = sum(rec.unit_line_ids.mapped('total_rent_year'))
            if line_rent and not rec.overall_discount:
                rec.total_rent_year = line_rent
            deposit = sum(rec.unit_line_ids.mapped('deposit_amount'))
            if deposit:
                rec.deposit_amount = deposit
                rec.is_any_deposit = True

    def _apply_wizard_rent_to_lines(self):
        """Unit rent first; units still at zero share whatever is left of
        the Total Rent typed in the wizard, so the contract, its payments
        and invoices all carry a rent."""
        zero_lines = self.unit_line_ids.filtered(lambda l: (l.total_rent_year or 0.0) <= 0.0)
        if not zero_lines:
            return
        entered = sum((self.unit_line_ids - zero_lines).mapped('total_rent_year'))
        remaining = (self.total_rent_year or 0.0) - entered
        if remaining <= 0.0:
            return
        share = round(remaining / len(zero_lines), 2)
        for index, line in enumerate(zero_lines):
            # last line takes the rounding difference
            line.total_rent_year = (
                remaining - share * (len(zero_lines) - 1)
                if index == len(zero_lines) - 1 else share)
        zero_lines._compute_total()

    ACTIVE_CONTRACT_TYPES = ('running_contract', 'expiring_soon',
                             'closure_pending_approval', 'closure_final_approval')

    def _check_unit_contract_overlap(self):
        """Block a new contract on any unit that already has an active
        contract overlapping the selected start / end date. The contract
        being renewed (opened from tenancy.details) is not counted."""
        end_date = self.end_date or self.duration_end_date
        if not self.unit_ids or not self.start_date or not end_date:
            return
        domain = [
            ('contract_type', 'in', self.ACTIVE_CONTRACT_TYPES),
            ('start_date', '<=', end_date),
            ('end_date', '>=', self.start_date),
            '|', ('property_id', 'in', self.unit_ids.ids),
                 ('unit_ids', 'in', self.unit_ids.ids),
        ]
        if self.env.context.get('active_model') == 'tenancy.details' and self.env.context.get('active_id'):
            domain.append(('id', '!=', self.env.context['active_id']))
        contracts = self.env['tenancy.details'].sudo().search(domain)
        if not contracts:
            return
        details = []
        for unit in self.unit_ids:
            for contract in contracts.filtered(
                    lambda c: c.property_id == unit or unit in c.unit_ids):
                details.append(_(
                    "%(unit)s: %(contract)s (%(start)s to %(end)s)",
                    unit=unit.name, contract=contract.tenancy_seq or contract.display_name,
                    start=contract.start_date, end=contract.end_date))
        raise ValidationError(_(
            "These units already have an active contract in the selected period:\n%s\n\n"
            "Please choose a different period or remove these units.",
            "\n".join(details)))

    def _check_unit_rent_entered(self):
        self._apply_wizard_rent_to_lines()
        missing = self.unit_line_ids.filtered(lambda l: (l.total_rent_year or 0.0) <= 0.0)
        if missing:
            raise ValidationError(_(
                "Please enter the rent for: %s (in the unit line or as Total Rent).",
                ', '.join(missing.mapped('property_id.name'))))

    # ------------------------------------------------------------------ #
    #  Override contract_action to support split mode                      #
    # ------------------------------------------------------------------ #
    def contract_action(self):
        """
        Single Contract mode  (split_into_units = False):
            Delegates entirely to the original wizard logic.

        Split Contract mode  (split_into_units = True):
            Creates one tenancy.details record per selected unit,
            using each unit's individual rent from unit_line_ids.
            The first created contract is returned for navigation.
        """
        self._check_unit_contract_overlap()
        self._check_unit_rent_entered()
        if not self.split_into_units:
            # ── Single Contract (original behaviour) ──────────────────
            result = super().contract_action()
            if self.payment_term == 'full_payment':
                # ribs_real_estate creates a Full Payment contract straight
                # as running (invoice skipped below); keep it draft like
                # every other payment term until it is activated.
                contract = self.env['tenancy.details'].browse(
                    (result or {}).get('res_id'))
                if contract:
                    contract.write({
                        'contract_type': 'new_contract',
                        'active_contract_state': False,
                        'last_invoice_payment_date': False,
                    })
            return result

        # ── Split-per-Unit flow ───────────────────────────────────────
        self.ensure_one()
        if not self.unit_ids:
            raise ValidationError(_("Please select at least one unit."))

        # Resolve duration for by-date contracts
        if self.is_by_date:
            if not self.duration_end_date and self.end_date:
                self.duration_end_date = self.end_date
            elif not self.end_date and self.duration_end_date:
                self.end_date = self.duration_end_date
            if not self.duration_end_date:
                raise ValidationError(
                    _("Please set an End Date before creating the contract.")
                )
            self.action_generate_duration()
            duration_rec = self._get_or_create_duration()
            self.duration_id = duration_rec.id

        self.customer_id.user_type = 'customer'

        # Build a lookup: unit_id → rent amount from unit_line_ids
        unit_rent_map = {}
        for line in self.unit_line_ids:
            if line.property_id:
                # Use discounted total if a discount was applied, else full rent
                unit_rent_map[line.property_id.id] = (
                    line.total if line.discount_applied else line.total_rent_year
                )

        created_contracts = self.env['tenancy.details']

        for unit in self.unit_ids:
            # Determine this unit's individual rent
            unit_rent = unit_rent_map.get(unit.id, unit.price_yearly or 0.0)

            # Build base contract data (same as get_contract_info but per-unit)
            record = {
                # Customer
                'tenancy_id': self.customer_id.id,
                # Property (single unit per contract in split mode)
                'property_id': unit.id,
                'property_project_id': unit.property_project_id.id,
                'unit_ids': [(6, 0, [unit.id])],
                'total_rent_year': unit_rent,
                'final_rent_unit': self.rent_unit,
                'property_landlord_id': self.property_id.landlord_id.id,
                # Contract
                'duration_type': self.duration_type,
                'duration_end_date': self.duration_end_date,
                'duration_id': self.duration_id.id,
                'start_date': self.start_date,
                'invoice_start_date': self.start_date,
                'end_date': self.end_date,
                'payment_term': self.payment_term,
                # Deposit (split equally across units)
                'is_any_deposit': self.is_any_deposit,
                'deposit_amount': (
                    round(self.deposit_amount / len(self.unit_ids), 2)
                    if self.is_any_deposit and self.deposit_amount else 0.0
                ),
                # Agreement / items / taxes
                'agreement': self.agreement,
                'agreement_template_id': self.agreement_template_id.id,
                'installment_item_id': self.installment_item_id.id,
                'broker_item_id': self.broker_item_id.id,
                'deposit_item_id': self.deposit_item_id.id,
                'maintenance_item_id': self.maintenance_item_id.id,
                'tax_ids': [(6, 0, self.tax_ids.ids)],
                'instalment_tax': self.instalment_tax,
                'service_tax': self.service_tax,
                'deposit_tax': self.deposit_tax,
                'term_condition': self.term_condition,
                # Flags
                'is_multi_contract': False,   # Each is now its own single contract
                'is_by_date': self.is_by_date,
                # Full Payment too stays draft; its invoice is created
                # when the contract is activated.
                'contract_type': 'new_contract',
            }

            # Added services (duplicate per unit)
            if self.is_added_services and self.added_service_ids:
                record['is_added_services'] = True
                record['added_service_ids'] = [
                    (0, 0, {'service_id': s.service_id.id, 'price': s.price})
                    for s in self.added_service_ids
                ]
                record['added_service_invoice'] = self.added_service_invoice

            # Create the per-unit contract
            contract = self.env['tenancy.details'].sudo().create(record)
            contract._onchange_agreement_template_id()
            contract.contract_payment_pdc()

            if self.is_by_date:
                contract.write({'end_date': self.duration_end_date})

            created_contracts |= contract

        # Mark all selected units as on_lease
        self.unit_ids.write({'stage': 'on_lease'})
        self.customer_id.is_tenancy = True

        if not created_contracts:
            raise ValidationError(_("No contracts were created. Please check your configuration."))

        # If only one unit → open its contract form directly
        if len(created_contracts) == 1:
            return {
                'type': 'ir.actions.act_window',
                'name': _('Contract'),
                'res_model': 'tenancy.details',
                'res_id': created_contracts.id,
                'view_mode': 'form,list',
                'target': 'current',
            }

        # Multiple contracts → open a list filtered to the newly created ones
        return {
            'type': 'ir.actions.act_window',
            'name': _('Split Contracts'),
            'res_model': 'tenancy.details',
            'domain': [('id', 'in', created_contracts.ids)],
            'view_mode': 'list,form',
            'target': 'current',
        }

    # Full Payment invoice is created on activation
    # (tenancy.details.action_active_contract), not at contract creation.
    def action_create_full_payment_invoice(self, contract_id):
        return

    def _process_by_dated_full_payment(self, contract_id):
        return


class GroupMultiContractLine(models.Model):
    _inherit = 'group.multi.contract.line'

    @api.onchange('total_rent_year')
    def _onchange_total_rent_year_al_shafar(self):
        """Rent typed in the wizard: recompute the line's amounts (the
        compute has no depends) and a percentage-based deposit."""
        for line in self:
            unit = line.property_id
            if unit.deposit_type == 'percent':
                line.deposit_amount = (line.total_rent_year or 0.0) * (unit.deposit_percentage or 0.0) / 100.0
            line._compute_total()
