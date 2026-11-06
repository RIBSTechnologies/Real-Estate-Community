from odoo import fields, models, api


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    maintenance_count = fields.Integer(string="Maintenance Count", default=3, 
                                       config_parameter='ribs_real_estate.maintenance_count')

    def _get_users(self):
        users = self.env['res.users'].search([])
        return [(6, 0, users.ids)]

    force_collect_payments = fields.Boolean(string="Force user to collect payments", default=True,
                                            config_parameter='ribs_real_estate.force_collect_payments')
    authorized_users_ids = fields.Many2many('res.users', string="Authorized user", default=_get_users)

    def set_values(self):
        super().set_values()
        params = self.env['ir.config_parameter'].sudo()
        ids_string = ",".join(str(uid) for uid in self.authorized_users_ids.ids)

        params.set_str(
            'ribs_real_estate.authorized_users_ids',
            ids_string
        )
        params.set_str(
            'ribs_real_estate.force_collect_payments',
            self.force_collect_payments
        
        )

    @api.model
    def get_values(self):
        res = super().get_values()
        params = self.env['ir.config_parameter'].sudo()
        ids_string = params.get_str('ribs_real_estate.authorized_users_ids', '')

        clean_string = (
            ids_string.replace('res.users', '')
            .replace('(', '')
            .replace(')', '')
            .replace('[', '')
            .replace(']', '')
            .replace(' ', '')
        )
        if clean_string:
            ids_list = [int(x) for x in clean_string.split(',') if x.isdigit()]
        else:
            ids_list = []
        res.update({
            'authorized_users_ids': [(6, 0, ids_list)],
            'force_collect_payments': params.get_str(
                'ribs_real_estate.force_collect_payments', default=True
            ) == 'True'
        })
        return res