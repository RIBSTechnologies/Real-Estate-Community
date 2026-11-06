from odoo import models, fields


class AccountAnalyticPlan(models.Model):
    _inherit = 'account.analytic.plan'

    customized_type = fields.Selection([
        ('property_type', 'Property Type'),
        ('building', 'Building'),
        ('units', 'Units')
    ])

    _customized_type_unique = models.Constraint(
        'unique(customized_type)',
        'Each Customized Type can only be used once.',
    )