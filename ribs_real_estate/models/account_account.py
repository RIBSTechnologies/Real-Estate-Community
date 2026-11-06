from odoo import models, fields

class account_account(models.Model):

    _inherit = 'account.account'

    description = fields.Char(string='Description')