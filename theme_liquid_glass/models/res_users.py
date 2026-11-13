from odoo import api, fields, models

COLOR_SCHEMES = [
    ('dark', 'Dark'),
    ('light', 'Light'),
    ('system', 'Same as device'),
]


class ResUsers(models.Model):
    _inherit = 'res.users'

    lg_color_scheme = fields.Selection(
        COLOR_SCHEMES,
        string='Theme Appearance',
        default='dark',
        required=True,
        help='Liquid Glass backend appearance for this user.',
    )

    @api.model
    def lg_set_color_scheme(self, scheme):
        """Let the current user change their own appearance (no write
        access on res.users is required for that)."""
        if scheme not in dict(COLOR_SCHEMES):
            return False
        self.env.user.sudo().lg_color_scheme = scheme
        return True
