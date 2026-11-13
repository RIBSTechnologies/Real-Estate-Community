from odoo import models


class IrHttp(models.AbstractModel):
    _inherit = 'ir.http'

    def session_info(self):
        result = super().session_info()
        if self.env.user:
            result['lg_color_scheme'] = self.env.user.lg_color_scheme or 'dark'
        return result
