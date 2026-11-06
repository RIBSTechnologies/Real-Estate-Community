from odoo import models, fields, _


class AccountPaymentRegister(models.TransientModel):

    _inherit = 'account.payment.register'

    cheque_ref = fields.Char(string='Cheque Reference')

    def action_create_payments(self):
        ctx = dict(self.env.context)
        inv_id = ctx.get('invoice_id')

        res = super().action_create_payments()
        if isinstance(res, bool):
            payment = self.env['account.payment'].search([],order='id desc', limit=1)
            if payment:
                payment.write({'invoice_id': inv_id, 'cheque_ref':self.cheque_ref})
            return res
        return res

