# -*- coding: utf-8 -*-

from odoo import api, SUPERUSER_ID


def migrate(cr, version):
    """pdc.wizard.tenancy_id (added in 18.0.1.0.1) only ever computed from
    invoice_id/invoice_ids, which stay empty until the cheque is registered
    (contract.payments.line_received). Every PDC cheque generated from a
    contract's payment schedule (tenancy.details.action_send_active_contract)
    but not yet received was therefore left with tenancy_id = False - Group
    By Contract Number in "PDC Cheque Payment" showed those under a blank
    bucket instead of the contract.

    _compute_tenancy_id now also falls back to contract_payment_ids.contract_id
    (contract.payments.payment_pdc_id is set at creation time, well before any
    invoice is linked), but that only fires on a future write - existing rows
    keep their stale stored value until touched. One-time backfill: recompute
    tenancy_id for every pdc.wizard that doesn't have it set yet.
    """
    env = api.Environment(cr, SUPERUSER_ID, {})
    pdc_wizard = env['pdc.wizard']
    if 'tenancy_id' not in pdc_wizard._fields:
        return
    records = pdc_wizard.search([('tenancy_id', '=', False)])
    if records:
        records._compute_tenancy_id()
        records.flush_recordset(['tenancy_id'])
