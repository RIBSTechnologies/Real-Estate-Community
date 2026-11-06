from odoo import models, fields, api

class ContractPaymentCommentWizard(models.TransientModel):
    _name = 'contract.payment.comment.wizard'
    _description = 'Contract Payment Comment Wizard'

    payment_id = fields.Many2one(
        'contract.payments',
        required=True
    )
    comment = fields.Text(
        string='Comment',
        required=True
    )
    attachment_ids = fields.Many2many(
        'ir.attachment',
        string='Attachments'
    )

    def action_reject(self):
        self.ensure_one()

        payment = self.payment_id

        payment.write({
            'leasing_comment_added' : False,
            'finance_comment_added': True,
            'rejected_reason': self.comment,
            'rejected_attachment_ids': [(6, 0, self.attachment_ids.ids)],
            'comment_added': True,
            'line_payment_received': 'not_received',
        })
        self.make_latest_attachment_public(payment)
        return {'type': 'ir.actions.act_window_close'}

    def action_close(self):
        return {'type': 'ir.actions.act_window_close'}

    def make_latest_attachment_public(self, payment):
        Attachment = self.env['ir.attachment']
        attachment = Attachment.search([
            ('create_uid', '=', self.env.user.id),
            ('res_model', 'in', [
                'contract.payment.comment.wizard',
                'contract.payment.edit.wizard',
            ]),
        ], order='create_date desc', limit=1)
        if attachment:
            attachment.write({
                'public': True,
                'res_model': 'contract.payments',
                'res_id': payment.id,
            })

