# -*- coding: utf-8 -*-

import logging
from odoo import models, fields, api, _

_logger = logging.getLogger(__name__)


class PDCWizardExtended(models.Model):
    _inherit = 'pdc.wizard'

    contract_payment_ids = fields.One2many(
        'contract.payments', 'payment_pdc_id',
        string="Contract Payment Lines",
    )
    tenancy_id = fields.Many2one(
        'tenancy.details',
        string="Contract",
        compute='_compute_tenancy_id',
        store=True,
        help="Rent contract this PDC cheque belongs to, used to filter/search/group PDC payments by Contract Number.",
    )

    @api.depends(
        'contract_payment_ids.contract_id',
        'invoice_id', 'invoice_id.tenancy_id',
        'invoice_ids', 'invoice_ids.tenancy_id',
    )
    def _compute_tenancy_id(self):
        """PDC cheques created from the contract's payment schedule
        (tenancy.details.action_send_active_contract) are linked back to
        their contract.payments line (payment_pdc_id) as soon as they're
        created - well before they're ever registered against an invoice.
        Prefer that link first, since invoice_id/invoice_ids only get
        populated once the cheque is registered (contract.payments.
        line_received), which left tenancy_id blank - and every PDC
        "Group By Contract" bucket empty - for every not-yet-received
        cheque."""
        for rec in self:
            rec.tenancy_id = (
                rec.contract_payment_ids[:1].contract_id
                or rec.invoice_id.tenancy_id
                or rec.invoice_ids[:1].tenancy_id
            )

    @api.model
    def action_auto_deposit_due_pdc(self):
        """
        Cron Job Method: Automatically deposits registered PDC cheques whose due date
        is on or before today.
        """
        today = fields.Date.today()
        _logger.info("Starting Automated PDC Deposit Cron for due_date <= %s", today)

        # Search for registered PDC records that have reached or passed their due date
        pdc_records = self.search([
            ('state', '=', 'registered'),
            ('due_date', '<=', today),
        ])

        _logger.info("Found %d PDC record(s) eligible for automated deposit.", len(pdc_records))

        success_count = 0
        fail_count = 0

        for pdc in pdc_records:
            try:
                pdc.action_deposited()
                pdc.message_post(
                    body=_("PDC cheque %s was automatically deposited by daily scheduled job on due date (%s).") % (
                        pdc.cheque_number or pdc.name or '', pdc.due_date
                    ),
                    message_type='notification'
                )
                success_count += 1
            except Exception as e:
                fail_count += 1
                _logger.error("Failed to auto-deposit PDC ID %s (%s): %s", pdc.id, pdc.name, str(e))
                pdc.message_post(
                    body=_("Automated PDC Deposit failed on due date (%s): %s") % (pdc.due_date, str(e)),
                    message_type='notification'
                )

        _logger.info("PDC Auto-Deposit Cron completed: %d succeeded, %d failed.", success_count, fail_count)

    @api.model
    def action_deposit_cheque(self):
        """
        Override existing sh_pdc action_deposit_cheque to ensure it uses due_date
        and processes all due PDC cheques.
        """
        self.action_auto_deposit_due_pdc()
