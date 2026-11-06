# -*- coding: utf-8 -*-

from odoo import fields, models

# Label / Memo are called "Narration" across accounting. Only the field
# label changes (lists, forms, filters, exports); the fields themselves
# and their data are untouched.


class AccountMoveLine(models.Model):
    _inherit = 'account.move.line'

    name = fields.Char(string='Narration')


class AccountBankStatementLine(models.Model):
    _inherit = 'account.bank.statement.line'

    payment_ref = fields.Char(string='Narration')


class AccountPayment(models.Model):
    _inherit = 'account.payment'

    memo = fields.Char(string='Narration')


class AccountPaymentRegister(models.TransientModel):
    _inherit = 'account.payment.register'

    communication = fields.Char(string='Narration')
    writeoff_label = fields.Char(string='Narration')


class PdcWizard(models.Model):
    _inherit = 'pdc.wizard'

    memo = fields.Char(string='Narration')
