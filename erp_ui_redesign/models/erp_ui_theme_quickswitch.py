# -*- coding: utf-8 -*-
from odoo import api, fields, models

SITE_DEFAULT = '__site_default__'


class ErpUiThemeQuickswitch(models.TransientModel):
    """Quick, no-admin-required theme popup, opened from the systray icon.

    Deliberately separate from `erp.ui.redesign.settings` (the
    `base.group_system`-only wizard under Settings > ERP UI Redesign, which
    still controls the SITE-WIDE default via ir.config_parameter). This one
    is reachable by any internal user and only ever writes to that user's
    OWN `res.users.erp_ui_theme` - never the site default.
    """
    _name = 'erp.ui.theme.quickswitch'
    _description = 'Quick Theme Switch'

    theme = fields.Selection(
        selection=[
            (SITE_DEFAULT, 'Use Site Default'),
            ('vibrant', 'Vibrant / 3D (gradients, glow, motion)'),
            ('minimal', 'Minimal (flat, quiet, client-facing)'),
            ('classic', 'Classic (plain Odoo purple, no flourishes)'),
        ],
        string="Theme",
        required=True,
        default=SITE_DEFAULT,
    )

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        if 'theme' in fields_list:
            res['theme'] = self.env.user.erp_ui_theme or SITE_DEFAULT
        return res

    def action_apply(self):
        """Write ONLY to the calling user's own record. `sudo()` here is
        safe/scoped: `self.env.user` always resolves to the current
        session's user, so this can never be used to change anyone else's
        theme, regardless of that user's own res.users access rights."""
        self.ensure_one()
        value = False if self.theme == SITE_DEFAULT else self.theme
        self.env.user.sudo().write({'erp_ui_theme': value})
        # Full reload so the new theme is visible immediately, rather than
        # only after the user's next manual refresh.
        return {'type': 'ir.actions.client', 'tag': 'reload'}
