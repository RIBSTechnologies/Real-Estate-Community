from odoo import models, fields, api
from odoo.exceptions import ValidationError

class ContractPaymentEditWizard(models.TransientModel):
    _name = "contract.payment.edit.wizard"
    _description = "Edit Contract Payment"

    payment_type = fields.Selection(
        [
            ('bank', 'Bank Transfer'),
            ('cheque', 'Cheque'),
            ('cash', 'Cash'),
        ],
        string='Payment Type',
    )
    payment_id = fields.Many2one(
        "contract.payments",
        string="Payment",
        required=True,
        readonly=True
    )

    amount = fields.Monetary(
        string="Amount",
        required=True
    )
    currency_id = fields.Many2one(
        "res.currency",
        related="payment_id.currency_id",
        readonly=True
    )
    remitter_bank_id = fields.Many2one('res.bank', string="Remitter Bank Name")
    chq_due_date = fields.Date(string="Due Date")
    leasing_reason = fields.Text(string="Leasing Comment")
    attachment_ids = fields.Many2many(
        'ir.attachment',
        string='Attachments'
    )
    journal_id = fields.Many2one(
        'account.journal',
        domain=lambda self: [
            '|',
            ('company_id', 'parent_of', self.env.company.id),
            ('company_id', 'child_of', self.env.company.id),
            ('type', 'in', ('bank', 'cash', 'credit')),
        ], string='Beneficiary Bank'
    )
    cheque_num = fields.Char('Cheque Number')
    ref = fields.Char('Reference')

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        payment = self.env["contract.payments"].browse(
            self.env.context.get("default_payment_id")
        )
        if payment:
            res.update({
                "payment_type": payment.payment_type,
                "payment_id": payment.id,
                "amount": payment.amount,
                "remitter_bank_id": payment.remitter_bank_id.id,
                "chq_due_date": payment.chq_due_date,
                "leasing_reason": payment.leasing_reason,
                "journal_id": payment.journal_id,
                "cheque_num": payment.cheque_num,
                "ref": payment.ref,
                "attachment_ids": [(6, 0, payment.attachment_ids.ids)],
            })
        return res

    def action_confirm(self):
        self.ensure_one()
        payment = self.payment_id
        if self.chq_due_date and self.chq_due_date < payment.contract_id.start_date:
            raise ValidationError('Due Date cannot be before Contract Start Date.')
        payment.write({
            "payment_type":self.payment_type,
            "amount": self.amount,
            "chq_due_date": self.chq_due_date,
            "remitter_bank_id": self.remitter_bank_id.id,
            "leasing_reason": self.leasing_reason,
            "journal_id": self.journal_id,
            "cheque_num": self.cheque_num,
            "ref": self.ref,
            "attachment_ids": [(6, 0, self.attachment_ids.ids)],
            "comment_added": True,
            "leasing_comment_added": True,
            "finance_comment_added": False,
        })

        # if payment.contract_id:
        #     payment.contract_id.message_post(
        #         body="Payment updated by Leasing team."
        #     )
        self.make_latest_attachment_public(payment)
        return {"type": "ir.actions.act_window_close"}


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

