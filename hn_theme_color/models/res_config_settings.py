import re

from odoo import api, fields, models
from odoo.exceptions import ValidationError

PARAM = 'hn_theme_color.primary'
HEX = re.compile(r'^#[0-9a-fA-F]{6}$')

PRESETS = [
    ('#71639e', 'Odoo purple (default)'),
    ('#714b67', 'Plum'),
    ('#1f6feb', 'Blue'),
    ('#0e7490', 'Teal'),
    ('#15803d', 'Green'),
    ('#b45309', 'Amber'),
    ('#c2410c', 'Orange'),
    ('#b91c1c', 'Red'),
    ('#be185d', 'Pink'),
    ('#334155', 'Slate'),
]


def theme_scss(color):
    """SCSS read before Odoo's variables: Community, and enterprise-like themes for Community."""
    if not color:
        return '// Theme Color: Odoo default colors\n'
    return (
        '// Theme Color: generated from Settings, do not edit\n'
        f'$o-community-color: {color};\n'
        f'$o-enterprise-color: {color};\n'
        f'$o-brand-odoo: {color};\n'
        f'$o-brand-primary: {color};\n'
        f'$o-enterprise-action-color: {color};\n'
        f'$o-action: {color};\n'
    )


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    hn_theme_color = fields.Char('Theme color', config_parameter=PARAM,
                                 help="Main color of Odoo: buttons, links, top menu and highlights.")
    hn_theme_color_preset = fields.Selection(PRESETS, 'Preset', store=False)

    @api.onchange('hn_theme_color_preset')
    def _onchange_hn_theme_color_preset(self):
        if self.hn_theme_color_preset:
            self.hn_theme_color = self.hn_theme_color_preset

    @api.constrains('hn_theme_color')
    def _check_hn_theme_color(self):
        for settings in self:
            if settings.hn_theme_color and not HEX.match(settings.hn_theme_color):
                raise ValidationError(self.env._("The theme color must be a color like #1f6feb."))

    def _hn_theme_attachment(self):
        return self.env.ref('hn_theme_color.theme_color_scss', raise_if_not_found=False)

    def _hn_apply_theme_color(self, color):
        """Write the SCSS of ``color`` (False = Odoo default). Returns True if it changed."""
        attachment = self._hn_theme_attachment()
        if not attachment:
            return False
        content = theme_scss((color or '').lower() or False).encode()
        # Odoo 20: binary fields read as a BinaryValue; compare its bytes.
        if attachment.sudo().raw.content == content:
            return False
        attachment.sudo().write({'raw': content})
        self.env.transaction.invalidate_ormcache('assets')  # Odoo 20 API
        return True

    def execute(self):
        result = super().execute()
        # Odoo 20: get_param/set_param were replaced by typed getters/setters.
        color = self.env['ir.config_parameter'].sudo().get_str(PARAM) or False
        if self._hn_apply_theme_color(color):
            # the stylesheets are rebuilt with the new color when the page reloads
            return {'type': 'ir.actions.client', 'tag': 'reload'}
        return result

    def action_hn_theme_color_reset(self):
        self.env['ir.config_parameter'].sudo().set_str(PARAM, False)
        self._hn_apply_theme_color(False)
        return {'type': 'ir.actions.client', 'tag': 'reload'}
