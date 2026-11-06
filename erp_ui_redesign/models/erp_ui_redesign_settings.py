# -*- coding: utf-8 -*-
from odoo import api, fields, models


class ErpUiRedesignSettings(models.TransientModel):
    """Standalone settings wizard for this module's appearance options.

    Deliberately its OWN model - not `res.config.settings`, and not
    inheriting it. That model is special-cased by Odoo's web client: any
    action pointing at it renders inside the main Settings app's tab bar
    (General Settings / Users & Companies / Translations / ... ), which is
    exactly why the font picker showed up wedged into the Settings app in
    an earlier version instead of living in its own separate menu. A
    plain, independent TransientModel has none of that special-casing, so
    its menu, action, and popup are fully separate from core Settings.
    """
    _name = 'erp.ui.redesign.settings'
    _description = 'ERP UI Redesign Settings'

    font_family = fields.Selection(
        selection=[
            ('default', 'Odoo Default'),
            ('inter', 'Inter'),
            ('roboto', 'Roboto'),
            ('system', 'System UI (native, fastest)'),
            ('georgia', 'Georgia (serif)'),
        ],
        string="Interface Font",
        default='default',
    )

    theme = fields.Selection(
        selection=[
            ('vibrant', 'Vibrant / 3D (gradients, glow, motion)'),
            ('minimal', 'Minimal (flat, quiet, client-facing)'),
            ('classic', 'Classic (plain Odoo purple, no flourishes)'),
        ],
        string="Visual Theme",
        default='vibrant',
        help="Vibrant is this module's original look: gradients, glowing "
             "buttons, and a pulsing status pill. Minimal and Classic keep "
             "every layout/alignment fix but flatten the decoration for a "
             "quieter, client-facing screen.",
    )

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        params = self.env['ir.config_parameter'].sudo()
        if 'font_family' in fields_list:
            res['font_family'] = params.get_str('erp_ui_redesign.font_family', 'default')
        if 'theme' in fields_list:
            res['theme'] = params.get_str('erp_ui_redesign.theme', 'vibrant')
        return res

    def action_save(self):
        self.ensure_one()
        params = self.env['ir.config_parameter'].sudo()
        params.set_str('erp_ui_redesign.font_family', self.font_family or 'default')
        params.set_str('erp_ui_redesign.theme', self.theme or 'vibrant')
        return {'type': 'ir.actions.act_window_close'}
