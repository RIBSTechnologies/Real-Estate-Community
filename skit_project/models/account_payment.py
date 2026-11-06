from odoo import fields, models

#inherit account payment model
class AccountPayment(models.Model):
    _inherit = "account.payment"

    def action_post(self):
        """ extend method to update analytic distribution for journal entries"""
        res = super().action_post()
        for payment in self:
            move = payment.move_id
            property_id = False
            if move.ref:
                move_id = self.env['account.move'].sudo().search([('name','=',move.ref)])
                property_id = move_id.tenancy_property_id
                if move_id.maintenance_request_id and move_id.maintenance_request_id.property_id:
                    property_id = move_id.maintenance_request_id.property_id
            if not property_id:
                continue
            tenancy_id = property_id.analytic_account_id
            if not tenancy_id:
                continue
            analytic_distribution = {
                tenancy_id.id: 100
            }
            for line in move.line_ids:
                line.write({
                    'analytic_distribution': analytic_distribution
                })
        return res