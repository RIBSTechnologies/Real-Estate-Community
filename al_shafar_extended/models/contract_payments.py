# -*- coding: utf-8 -*-

from odoo import models


class ContractPayments(models.Model):
    _inherit = 'contract.payments'

    def _reconcile_cash_bank_payment(self, payment, invoices):
        """Cash/Bank Transfer lines only get an account.payment created in
        draft (tenancy.details.action_send_active_contract) and are then
        marked 'paid' by a direct field write, which never posts the payment
        or reconciles it against the invoice - amount_residual never moves.
        Post the payment and reconcile it against the linked invoice(s),
        mirroring what the Cheque/PDC flow already achieves via
        pdc.wizard.action_register()."""
        if not payment:
            return
        if payment.state == 'draft':
            payment.action_post()
        invoices = invoices.filtered(lambda m: m.state == 'posted' and m.amount_residual)
        if not invoices or not payment.move_id:
            return
        account = payment.destination_account_id
        lines_to_reconcile = (invoices.line_ids | payment.move_id.line_ids).filtered(
            lambda l: l.account_id == account and not l.reconciled
        )
        if len(lines_to_reconcile) > 1:
            lines_to_reconcile.reconcile()

    def _post_invoices_before_reconcile(self, invoices):
        """pdc.wizard.action_register() (sh_pdc/wizard/pdc_payment_wizard.py)
        always posts its OWN journal entry right before reconciling, but
        never posts the invoice side - so registering a PDC against a
        still-draft rent invoice fails with Odoo's own
        "You can only reconcile posted entries.". Same fix as
        _reconcile_cash_bank_payment already applies to the payment side
        for Cash/Bank Transfer lines, just applied to the invoice side of
        the Cheque/PDC path instead."""
        invoices.filtered(lambda m: m.state == 'draft').action_post()

    def _unreconcile_cash_bank_payment(self, payment):
        """Undo _reconcile_cash_bank_payment: once a payment is actually
        posted/reconciled, force-writing its state back to 'draft' (the
        original behavior) has no real effect and leaves the invoice still
        reconciled against a payment shown as draft. Break the
        reconciliation and cancel the payment through the proper API."""
        if not payment or payment.state in ('draft', 'canceled'):
            return
        if payment.move_id:
            reconciled_lines = payment.move_id.line_ids.filtered(lambda l: l.reconciled)
            if reconciled_lines:
                reconciled_lines.remove_move_reconcile()
        payment.action_cancel()

    def received(self):
        self.has_accounting_access()
        for contract_payments in self.contract_id.contract_payment_ids:
            contract_payments.finance_comment_added = False
            contract_payments.leasing_comment_added = False
            contract_payments.payments_received = 'received'
            contract_payments.line_payment_received = 'received'
            invoices = contract_payments.contract_invoice_ids.mapped('rent_invoice_id')
            if contract_payments.payment_pdc_id:
                self._post_invoices_before_reconcile(invoices)
                contract_payments.payment_pdc_id.action_register()
            elif contract_payments.payment_account_id:
                self._reconcile_cash_bank_payment(contract_payments.payment_account_id, invoices)
        self._update_parent_received_status()

    def not_received(self):
        self.has_accounting_access()
        for contract_payments in self.contract_id.contract_payment_ids:
            contract_payments.finance_comment_added = True
            contract_payments.leasing_comment_added = False
            contract_payments.payments_received = 'not_received'
            contract_payments.line_payment_received = 'not_received'
            if contract_payments.payment_pdc_id:
                contract_payments.payment_pdc_id.state = 'draft'
            elif contract_payments.payment_account_id:
                self._unreconcile_cash_bank_payment(contract_payments.payment_account_id)
        self._update_parent_received_status()

    def line_received(self):
        if not self.financial_person_id:
            self.financial_person_id = self.env.user.id
        self.has_accounting_access()
        for record in self:
            record.finance_comment_added = False
            record.leasing_comment_added = False
            record.line_payment_received = 'received'
            invoices = record.contract_invoice_ids.mapped('rent_invoice_id')
            if record.payment_pdc_id:
                self._post_invoices_before_reconcile(invoices)
                record.payment_pdc_id.invoice_ids = [
                    (6, 0, invoices.ids)
                ]
                record.payment_pdc_id.action_register()
            elif record.payment_account_id:
                self._reconcile_cash_bank_payment(record.payment_account_id, invoices)
            self._update_parent_received_status()

    def line_not_received(self):
        if not self.financial_person_id:
            self.financial_person_id = self.env.user.id
        self.has_accounting_access()
        for record in self:
            record.line_payment_received = 'not_received'
            if record.payment_pdc_id:
                record.payment_pdc_id.state = 'draft'
            elif record.payment_account_id:
                self._unreconcile_cash_bank_payment(record.payment_account_id)
            self._update_parent_received_status()
