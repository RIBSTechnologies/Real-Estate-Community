# -*- coding: utf-8 -*-

from odoo import models


class AccountMove(models.Model):
    _inherit = 'account.move'

    def get_extra_print_items(self):
        """Hide Odoo's "PDF" (download the stored invoice PDF) from the
        Print menu of invoices; the Tax Invoice reports are used instead."""
        return []

    def _get_report_analytic_accounts(self, customized_type):
        """Analytic accounts used on the invoice lines whose plan (or root
        plan) is tagged with the given customized_type ('building' / 'units').

        analytic_distribution keys can hold several co-selected accounts
        joined by commas (e.g. "12,34"), so every id in a key is considered.
        Returns an empty recordset when nothing is mapped, so the report can
        hide the field entirely.
        """
        self.ensure_one()
        account_ids = []
        for line in self.invoice_line_ids:
            for key in (line.analytic_distribution or {}):
                for acc_id in str(key).split(','):
                    acc_id = acc_id.strip()
                    if acc_id.isdigit() and int(acc_id) not in account_ids:
                        account_ids.append(int(acc_id))
        accounts = self.env['account.analytic.account'].sudo().browse(account_ids).exists()
        return accounts.filtered(
            lambda a: customized_type in (a.plan_id.customized_type, a.plan_id.root_id.customized_type))

    def _get_report_building_name(self):
        return ', '.join(self._get_report_analytic_accounts('building').mapped('name'))

    def _get_report_unit_name(self):
        return ', '.join(self._get_report_analytic_accounts('units').mapped('name'))

    def _get_report_lines(self, exclude=()):
        """Invoice lines for the Tax Invoice reports, leaving out the
        'deposit' (Security Deposit) and / or 'ejari' lines named in
        exclude. Matched by product (the contract's deposit item, or a
        product named Deposit / Ejari), never by account - a rent line may
        sit on a wrongly guessed account."""
        self.ensure_one()
        deposit_product = self.tenancy_id.deposit_item_id

        def is_excluded(line):
            product = line.product_id
            if not product:
                return False
            if 'deposit' in exclude and deposit_product and product == deposit_product:
                return True
            name = (product.name or '').lower()
            return any(keyword in name for keyword in exclude)

        return self.invoice_line_ids.filtered(lambda line: not is_excluded(line))


class AccountMoveLine(models.Model):
    _inherit = 'account.move.line'

    def _get_report_analytic_names(self):
        """Names of every analytic account on the line (keys may hold several
        co-selected ids joined by commas), for the Journal Entry report."""
        self.ensure_one()
        account_ids = []
        for key in (self.analytic_distribution or {}):
            for acc_id in str(key).split(','):
                acc_id = acc_id.strip()
                if acc_id.isdigit() and int(acc_id) not in account_ids:
                    account_ids.append(int(acc_id))
        accounts = self.env['account.analytic.account'].sudo().browse(account_ids).exists()
        return ', '.join(accounts.mapped('name'))


class AccountPayment(models.Model):
    _inherit = 'account.payment'

    def _get_report_settled_moves(self):
        """Invoices (customer payment) or bills (vendor payment) settled."""
        self.ensure_one()
        return self.reconciled_invoice_ids or self.reconciled_bill_ids

    def _get_report_analytic_names(self, customized_type):
        """Building / Unit of a payment = those of the invoices / bills it settles."""
        self.ensure_one()
        accounts = self.env['account.analytic.account']
        for invoice in self._get_report_settled_moves():
            accounts |= invoice._get_report_analytic_accounts(customized_type)
        return ', '.join(accounts.mapped('name'))

    def _get_report_building_name(self):
        return self._get_report_analytic_names('building')

    def _get_report_unit_name(self):
        return self._get_report_analytic_names('units')

    def _get_report_invoice_lines(self):
        """[{'invoice', 'paid', 'residual'}] for each invoice / bill settled by
        this payment; 'paid' is only the part allocated from this payment."""
        self.ensure_one()
        result = []
        for invoice in self._get_report_settled_moves():
            partials = invoice._get_reconciled_invoices_partials()[0]
            paid = sum(abs(amount) for _partial, amount, counterpart in partials
                       if counterpart.payment_id == self)
            result.append({
                'invoice': invoice,
                'paid': paid,
                'residual': invoice.amount_residual,
            })
        return result
