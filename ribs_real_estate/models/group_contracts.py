from odoo import models, fields, api

class GroupContracts(models.Model):
    _name = 'group.contracts'
    _description = 'Group Contracts'

    name = fields.Char(string='Contract Name', required=True)
    days_left = fields.Integer(string='Days Left', readonly=True)
    contract_ids = fields.Many2many('tenancy.details', string='Contracts', readonly=True)
    unit_ids = fields.Many2many('property.details', string='Units', readonly=True)
    duration_type = fields.Selection([('by_duration', 'By Duration'),
                                      ('by_date', 'By Date')], default='by_duration', readonly=True)
    start_date = fields.Date(string='Start Date', default=fields.Date.today, readonly=True)
    end_date = fields.Date(string='End Date', readonly=True)
    
