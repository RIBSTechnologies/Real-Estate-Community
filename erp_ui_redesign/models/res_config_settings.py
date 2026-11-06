# -*- coding: utf-8 -*-
from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    # `config_parameter` does all the work: Odoo reads/writes this straight
    # to `ir.config_parameter` under the given key, so no custom
    # get_values()/set_values() override is needed just to persist the
    # choice. The JS side (erp_ui_enhance.js) reads the same key at web
    # client startup and applies it as a CSS variable.
    erp_ui_font_family = fields.Selection(
        selection=[
            ('default', 'Odoo Default'),
            ('inter', 'Inter'),
            ('roboto', 'Roboto'),
            ('system', 'System UI (native, fastest)'),
            ('georgia', 'Georgia (serif)'),
        ],
        string="Interface Font",
        default='default',
        config_parameter='erp_ui_redesign.font_family',
        help="Changes the font used across form and list views for every "
             "user on this database. Takes effect after a page refresh.",
    )
