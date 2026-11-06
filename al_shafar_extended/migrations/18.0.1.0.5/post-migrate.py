# -*- coding: utf-8 -*-

import logging

from odoo import api, SUPERUSER_ID

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    """One-time cleanup for the "Full Payment" PDC schedule bug (see
    ribs_real_estate/models/tenancy_details.py get_payment_term_qty):
    'full_payment' used to map to a months_per_payment of 1, so
    contract_payment_pdc() generated one contract.payments schedule line
    per month of the contract instead of a single lump-sum line for the
    whole duration. Fixed going forward; this backfills contracts that
    already got the wrong schedule.

    Only regenerates a contract's schedule (contract_payment_pdc(), which
    wipes and rebuilds contract_payment_ids from scratch) when NONE of its
    existing lines have been touched by anything real yet - no
    payment_ref (linked account.payment/pdc.wizard) and no
    line_payment_received='received'. A contract with even one such line
    is left completely untouched and only logged: collapsing a schedule
    that a real cheque/payment already points to is a business decision
    for finance to make, not something to do silently in a migration.
    """
    env = api.Environment(cr, SUPERUSER_ID, {})
    tenancy_obj = env['tenancy.details']

    candidates = tenancy_obj.search([('payment_term', '=', 'full_payment')])
    fixed, needs_review, errored = [], [], []

    for contract in candidates:
        lines = contract.contract_payment_ids
        if len(lines) <= 1:
            continue  # already correct (or nothing generated yet)

        touched = lines.filtered(
            lambda l: l.payment_ref or l.line_payment_received == 'received'
        )
        if touched:
            needs_review.append(contract.tenancy_seq or str(contract.id))
            continue

        try:
            contract.contract_payment_pdc()
            fixed.append(contract.tenancy_seq or str(contract.id))
        except Exception:  # noqa: BLE001 - one bad record must not abort the migration
            _logger.exception(
                "full_payment PDC schedule fix: could not regenerate contract %s",
                contract.tenancy_seq or contract.id)
            errored.append(contract.tenancy_seq or str(contract.id))

    _logger.info(
        "full_payment PDC schedule fix: %s contract(s) regenerated, "
        "%s need manual review (already has a real payment/PDC linked to "
        "a schedule line), %s errored.\n"
        "Regenerated: %s\nNeeds manual review: %s\nErrored: %s",
        len(fixed), len(needs_review), len(errored), fixed, needs_review, errored,
    )
