from odoo import models, fields, api

class AccountJournal(models.Model):
    _inherit = 'account.journal'
    
    is_pdc_journal = fields.Boolean('Is PDC Journal', default=False)