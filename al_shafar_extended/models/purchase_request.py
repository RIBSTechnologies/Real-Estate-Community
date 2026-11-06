# -*- coding: utf-8 -*-

from odoo import api, fields, models


class PurchaseRequest(models.Model):
    _inherit = 'purchase.request'

    parts_total_untaxed_amount = fields.Monetary(
        string='Parts Total Untaxed Amount', compute='_compute_parts_total_untaxed_amount',
        help="Total untaxed amount actually billed by vendors (posted vendor bills/refunds) "
             "against the Purchase Order lines raised from this request, as opposed to "
             "'Estimated Cost' which reflects the original estimate.")

    @api.depends(
        'line_ids.purchase_lines.invoice_lines.price_subtotal',
        'line_ids.purchase_lines.invoice_lines.move_id.state',
        'line_ids.purchase_lines.invoice_lines.move_id.move_type',
    )
    def _compute_parts_total_untaxed_amount(self):
        for request in self:
            bill_lines = request.line_ids.purchase_lines.invoice_lines.filtered(
                lambda line: line.move_id.state == 'posted'
                and line.move_id.move_type in ('in_invoice', 'in_refund')
            )
            request.parts_total_untaxed_amount = sum(
                line.price_subtotal if line.move_id.move_type == 'in_invoice' else -line.price_subtotal
                for line in bill_lines
            )
