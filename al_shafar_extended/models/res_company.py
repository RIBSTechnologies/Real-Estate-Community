# -*- coding: utf-8 -*-

from odoo import models, fields


class ResCompany(models.Model):
    _inherit = 'res.company'

    settlement_method = fields.Selection([
        ('full_month', 'Full Month (Charge full month when started)'),
        ('prorated', 'Prorated by Days'),
        ('no_refund_after_month_starts', 'No Refund After Month Starts')
    ], string="Contract Termination Settlement Policy", default='full_month',
       help="Default policy used when calculating prepaid contract refunds on termination.")

    sqm_to_sqft_ratio = fields.Float(
        string="1 sq.m = ? sq.ft",
        default=10.7639,
        digits=(12, 4),
        help="Conversion factor between square meters and square feet, used "
             "to compute 'Unit M Size' on Units (property.details). "
             "Example: 10.7639 means 1 sq.m = 10.7639 sq.ft. Changing this "
             "value automatically recalculates Unit M Size on every Unit."
    )
