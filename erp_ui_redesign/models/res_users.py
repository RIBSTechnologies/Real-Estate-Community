# -*- coding: utf-8 -*-
from odoo import fields, models


class ResUsers(models.Model):
    """Personal theme override, separate from the site-wide admin default.

    The site default (`erp_ui_redesign.theme`, an ir.config_parameter set via
    Settings > ERP UI Redesign > Appearance Settings) still applies to
    everyone. This field lets an individual user override JUST their own
    view via the systray "Choose Theme" popup, without touching the site
    default or requiring `base.group_system`. Blank/False means "no
    override - use the site default", which is also what picking "Use Site
    Default" in that popup writes back.

    Selection values are kept in sync by hand with
    `erp.ui.redesign.settings.theme` and `erp.ui.theme.quickswitch.theme` -
    three short, stable lists were judged simpler than factoring out a
    shared constant across three files for this module's size.
    """
    _inherit = 'res.users'

    erp_ui_theme = fields.Selection(
        selection=[
            ('vibrant', 'Vibrant / 3D (gradients, glow, motion)'),
            ('minimal', 'Minimal (flat, quiet, client-facing)'),
            ('classic', 'Classic (plain Odoo purple, no flourishes)'),
        ],
        string="My Theme Override",
        default=False,
        help="Personal override of the site's default Visual Theme. Leave "
             "blank to follow the site default set by an administrator.",
    )
