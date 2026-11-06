# -*- coding: utf-8 -*-

import logging

from odoo import models

_logger = logging.getLogger(__name__)


class ActiveContract(models.Model):
    _inherit = 'active.contract'

    def action_create_contract(self):
        """After activation, ribs_real_estate writes the contract period on
        every invoice line except the last one by position
        (invoice_line_ids[:-1]), so Security Deposit / Ejari lines get
        deferred dates too, and skit_contract_entries fills lines without
        analytic with the property's own account. Re-sync every draft
        invoice of the contract: period on the rent line(s) only, and the
        rent line's analytic distribution on every line."""
        tenancy = self.env['tenancy.details'].browse(self.env.context.get('active_id'))
        if tenancy.payment_term == 'full_payment' and self.type != 'automatic':
            # Full Payment's single invoice is built by
            # tenancy.details.action_active_contract (automatic path);
            # the manual installment path has no Full Payment branch.
            self.type = 'automatic'
        result = super().action_create_contract()
        if not tenancy:
            return result
        invoices = self.env['account.move'].sudo().search([
            ('tenancy_id', '=', tenancy.id),
            ('move_type', 'in', ('out_invoice', 'out_receipt')),
            ('state', '=', 'draft'),
        ])
        for move in invoices:
            try:
                move._sync_analytic_from_rent_line()
                move._apply_deferred_period()
            except Exception as exc:
                _logger.warning(
                    "al_shafar_extended: activation line sync failed invoice %s: %s",
                    move.id, exc)
        return result
