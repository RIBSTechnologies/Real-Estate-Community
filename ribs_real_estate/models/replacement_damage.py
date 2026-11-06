from odoo import models, fields, api


class DamageReplacementDetails(models.Model):
    _name = 'damage.replacement.records'
    _description = "Damage Replacement Records"

    
    contract_id = fields.Many2one('tenancy.details')
    company_id = fields.Many2one('res.company',
                                 string='Company',
                                 default=lambda self: self.env.company)
    currency_id = fields.Many2one('res.currency',
                                  related='company_id.currency_id',
                                  string='Currency ')
    caution_type = fields.Selection( string='Type', selection=[('damage', 'Damage'), 
                                                ('replacement', 'Replacement')], required=True )
    notes = fields.Text(string='Notes', required=True)
    price = fields.Monetary(string='Price', required=True)
    
    
    