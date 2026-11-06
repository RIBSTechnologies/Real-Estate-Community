# -*- coding: utf-8 -*-

from odoo import models, fields


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    settlement_method = fields.Selection(
        related='company_id.settlement_method',
        readonly=False,
        string="Contract Termination Settlement Method"
    )

    sqm_to_sqft_ratio = fields.Float(
        related='company_id.sqm_to_sqft_ratio',
        readonly=False,
        string="1 sq.m = ? sq.ft"
    )
