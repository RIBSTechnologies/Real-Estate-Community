from odoo import models, fields, api
from odoo.exceptions import ValidationError, UserError
import base64

class ContractPayments(models.Model):
    _name = 'contract.payments'
    _rec_name = 'contract_name'
    _order = 'payment_type, chq_due_date asc'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _description = "Contract Payments"

    company_id = fields.Many2one('res.company',
                                string='Company',
                                default=lambda self: self.env.company)
    currency_id = fields.Many2one('res.currency',
                                related='company_id.currency_id',
                                string='Currency')
    contract_id = fields.Many2one('tenancy.details')
    contract_name = fields.Char(related='contract_id.tenancy_seq')

    #since the payment can be from multiple sources, we need to track the source of payment
    payment_ref = fields.Reference(
        selection=[
            ('account.payment', 'Payment'),
            ('pdc.wizard', 'PDC Payment'),
        ],
        string='Payment Reference',
        readonly=True
    )
    payment_type = fields.Selection(
        [
            ('bank', 'Bank Transfer'),
            ('cheque', 'Cheque'),
            ('cash', 'Cash'),
        ],
        string='Payment Type',
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
    amount = fields.Monetary('Amount', required=True)
    chq_due_date = fields.Date('Date')
    remitter_bank = fields.Char('Remitter Bank Name (Legacy)')
    remitter_bank_id = fields.Many2one('res.bank', string='Remitter Bank Name')
    cheque_num = fields.Char('Cheque Number')
    ref = fields.Char('Reference')
    attachment_ids = fields.Many2many(
        'ir.attachment',
        string='Leasing Attachments'
    )
    rejected_attachment_ids = fields.Many2many(
        'ir.attachment',
        'contract_payment_reject_attachment_rel',  
        'payment_id',
        'attachment_id',
        string='Finance Attachments'
    )
    leasing_reason = fields.Text('Leasing Comment')
    rejected_reason = fields.Text('Finance Comment')
    leasing_comment_added = fields.Boolean(
        string='Leasing Comment Added', default=False
    )
    finance_comment_added = fields.Boolean(
        string='Finance Comment Added', default=False
    )
    financial_person_id = fields.Many2one(
        'res.users',
        string='Finance Person'
    )
    comment_added = fields.Boolean(
        string='Comment Added',
        default=False
    )
    is_mail_sent = fields.Boolean('Is mail sent', default=False)
    contract_responsible = fields.Many2one(related='contract_id.responsible_id', string='Responsible')
    contract_invoice_ids = fields.One2many(related='contract_id.rent_invoice_ids', string='Contract Invoices')
    contract_total_value = fields.Monetary(related='contract_id.total_contract_value', string='Contract Total Value')
    contract_status = fields.Selection(related='contract_id.contract_type', string='Status')
    contract_payment_ids = fields.One2many(related='contract_id.contract_payment_ids', string='Contract Payments')
    line_payment_received = fields.Selection(
        [('received', 'Received'), ('not_received', 'Not Received')],default='not_received', string='Payment Received Status'
    ) 
    payments_received = fields.Selection(
        [('waiting_for_approval','Waiting for Approval'), ('received', 'Received'), ('not_received', 'Not Received')],
        default='waiting_for_approval', string='Payments Received By Finance Team'
    )
    contract_payments = fields.Selection(related='contract_id.payments_received', string='Contract Payment Status')
    payment_account_id = fields.Many2one('account.payment', string='Payment', readonly=True)
    payment_pdc_id = fields.Many2one('pdc.wizard', string='PDC Payment', readonly=True)
    payment_display_id = fields.Char(compute='_compute_payment_display', string='Payment')

    @api.onchange('amount')
    def _onchange_amount(self):
        if self.amount and self.amount <= 0:
            raise ValidationError('Amount must be in postive')
    
    def received(self):
        self.has_accounting_access()
        for contract_payments in self.contract_id.contract_payment_ids:
        # for record in self:
            # record.payments_received = 'received'
            # for contract_payments in record.contract_id.contract_payment_ids:
            contract_payments.finance_comment_added = False
            contract_payments.leasing_comment_added = False
            contract_payments.payments_received = 'received'
            contract_payments.line_payment_received = 'received'
            if contract_payments.payment_pdc_id:
                contract_payments.payment_pdc_id.action_register()
            elif contract_payments.payment_account_id:
                contract_payments.payment_account_id.state = 'paid'
        self._update_parent_received_status()

    def not_received(self):
        self.has_accounting_access()
        for contract_payments in self.contract_id.contract_payment_ids:
        # for record in self:
        #     record.payments_received = 'not_received'
            # for contract_payments in record.contract_id.contract_payment_ids:
            contract_payments.finance_comment_added = True
            contract_payments.leasing_comment_added = False
            contract_payments.payments_received = 'not_received'
            contract_payments.line_payment_received = 'not_received'
            if contract_payments.payment_pdc_id:
                contract_payments.payment_pdc_id.state = 'draft'
            elif contract_payments.payment_account_id:
                contract_payments.payment_account_id.state = 'draft'
        self._update_parent_received_status()

    def line_received(self):
        if not self.financial_person_id:
            self.financial_person_id = self.env.user.id
        self.has_accounting_access()
        for record in self:
            record.finance_comment_added = False
            record.leasing_comment_added = False
            record.line_payment_received = 'received'
            invoices = record.contract_invoice_ids.mapped('rent_invoice_id')
            if record.payment_pdc_id:
                record.payment_pdc_id.invoice_ids = [
                    (6, 0, invoices.ids)
                ]
                record.payment_pdc_id.action_register()
            elif record.payment_account_id:
                record.payment_account_id.state = 'paid'
            self._update_parent_received_status()
    
    def line_not_received(self):
        if not self.financial_person_id:
            self.financial_person_id = self.env.user.id
        self.has_accounting_access()
        for record in self:
            record.line_payment_received = 'not_received'
            if record.payment_pdc_id:
                record.payment_pdc_id.state = 'draft'
            elif record.payment_account_id:
                record.payment_account_id.state = 'draft'
            self._update_parent_received_status()

    def has_accounting_access(self):
        user = self.env.user
        if not user.has_group('ribs_real_estate.property_rental_accountant'):
            print('no accesss')
            raise UserError('You do not have the required access to perform this action. Please contact your administrator.')

    def _compute_payment_display(self):
        for rec in self:
            if rec.payment_account_id:
                rec.payment_display_id = rec.payment_account_id.display_name
            elif rec.payment_pdc_id:
                rec.payment_display_id = rec.payment_pdc_id.display_name
            else:
                rec.payment_display_id = False

    def _update_parent_received_status(self):
        for rec in self:
            paid = False
            child_payments = rec.contract_id.contract_payment_ids
            if all(p.line_payment_received == 'received' for p in child_payments):
                rec.contract_id.payments_received = 'received'
                for payment in child_payments:
                # for inv in rec.contract_id.rent_invoice_ids:
                    # inv.action_post()
                    payment.payments_received = 'received'
                    paid = True
                if paid == True:
                    rec.send_mail()
            else:
                rec.contract_id.payments_received = 'not_received'
                # for inv in rec.contract_id.rent_invoice_ids:
                    # inv.button_draft()
                for payment in child_payments:
                    payment.payments_received = 'not_received'


    def action_open_add_comment_wizard(self):
        self.has_accounting_access()
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Add Comment',
            'res_model': 'contract.payment.comment.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_payment_id': self.id,
                'default_comment': self.rejected_reason,
                'default_attachment_ids': [(6, 0, self.rejected_attachment_ids.ids)],
            }
        }


    def send_mail(self):
        self.ensure_one()
        rec = self
        cash_payments = rec.contract_payment_ids.filtered(
            lambda p: p.journal_id and p.journal_id.name == 'Cash'
        )
        bank_payments = rec.contract_payment_ids.filtered(
            lambda p: p.journal_id and p.journal_id.name == 'Bank'
        )
        pdc_payments = rec.contract_payment_ids.filtered(
            lambda p: p.journal_id and p.journal_id.name == 'PDC'
        )
        attachment_ids = []

        invoices = self.env['account.move'].search([
            ('tenancy_id', '=', rec.contract_id.tenancy_id.id),
            ('move_type', '=', 'out_invoice'),
        ])

        for invoice in invoices:
            pdf_content, _ = self.env['ir.actions.report']._render_qweb_pdf(
                'account.report_invoice',
                [invoice.id]
            )

            attachment = self.env['ir.attachment'].create({
                'name': 'Invoice.pdf',
                'type': 'binary',
                'raw': pdf_content,
                'res_model': rec._name,
                'res_id': rec.id,
                'mimetype': 'application/pdf',
            })

            attachment_ids.append(attachment.id)

        template = self.env.ref(
            'ribs_real_estate.email_template_contract_payment_confirmation',
            raise_if_not_found=False
        )

        if not template:
            return
        ctx = {
            'cash_payments': cash_payments,
            'bank_payments': bank_payments,
            'pdc_payments': pdc_payments,
        }

        template.with_context(**ctx).send_mail(
            rec.id,
            email_values={
                'email_from': self.env.company.email,
                'email_to': rec.contract_id.tenancy_id.email,
                'attachment_ids': [(6, 0, attachment_ids)],
            },
            force_send=True,
        )

        body_html = template.with_context(**ctx)._render_field(
            'body_html',
            [rec.id],
            compute_lang=True
        )[rec.id]

        rec.message_post(
            body=body_html,
            attachment_ids=attachment_ids,
            subtype_xmlid="mail.mt_note",
        )

        rec.contract_id.is_confirmed_payment_mail_sent = True

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Email Sent!',
                'message': 'Payment confirmation email was sent successfully.',
                'type': 'success',
                'sticky': False,
                'next': {
                    'type': 'ir.actions.act_window_close'
                }
            }
        }


    def action_open_edit_payment_wizard(self):
        if self.env.user == self.contract_responsible or self.env.user.has_group("base.group_system"):
            self.ensure_one()
            return {
                "type": "ir.actions.act_window",
                "name": "Edit Payment",
                "res_model": "contract.payment.edit.wizard",
                "view_mode": "form",
                "target": "new",
                "context": {
                    "default_payment_id": self.id,
                },
            }
        else:
            raise UserError("You are not allowed to edit payments.")

    def write(self, vals):
        res = super().write(vals)  
        for rec in self:
            attachments = self.env['ir.attachment'].search([
                '|',
                ('res_model', '=', 'contract.payment.comment.wizard'),
                ('res_model', '=', 'contract.payment.edit.wizard'),
                ('res_model', '=', 'contract.payments'),
            ])
            attachments.sudo().write({
                'public': True,  
            })

        return res

    @api.onchange('chq_due_date')
    def _onchange_chq_due_date(self):
        if self.chq_due_date and self.chq_due_date < self.contract_id.start_date:
            raise ValidationError('Due Date cannot be before Contract Start Date.')
