from odoo import models, fields, api
from odoo.exceptions import UserError

class BulkPDCUpload(models.TransientModel):
    _name = 'bulk.pdc.upload'
    _description = 'Bulk PDC Upload Wizard'

    tenancy_id = fields.Many2one('tenancy.details', string='Contract')
    pdc_lines = fields.One2many('bulk.pdc.line', 'wizard_id', string='PDC Lines')
    journal_id = fields.Many2one('account.journal', string='Journal')
    invoice_id = fields.Many2one('account.move', string='Invoice')
    currency_id = fields.Many2one(
        'res.currency',
        related='invoice_id.currency_id',
        string='Currency',
        store=True,
        readonly=True,
    )

    invoice_amount = fields.Monetary(
        related='invoice_id.amount_residual',
        string='Invoice Amount',
        currency_field='currency_id',
        store=True,
        readonly=True,
    )


    def create_bulk_pdc(self):
        self.ensure_one()

        if not self.journal_id:
            raise UserError("Please select a journal for PDCs.")
        
        if not self.pdc_lines:
            raise UserError("Please add a line.")

        total_amount = sum(self.pdc_lines.mapped('amount'))
        if total_amount != self.invoice_id.amount_residual:
            raise UserError("Total PDC amount must equal the invoice amount.")

        for line in self.pdc_lines:
            if line.amount <= 0:
                raise UserError("Amount must be greater than zero.")
            
            # if line.due_date < fields.Date.today():
            #     raise UserError("Due date cannot be in the past.")

            if line.due_date > self.invoice_id.invoice_date_due:
                raise UserError("Due date cannot be greater than invoice due date.")

            payment = self.env['pdc.wizard'].create({
                'partner_id': self.tenancy_id.tenancy_id.id,
                'payment_amount': line.amount,
                'due_date': line.due_date,
                'journal_id': self.journal_id.id,
                'reference': line.cheque_ref or '',
                'cheque_number': line.cheque_num,
                'bank_id': line.remitter_bank,
                'payment_date': fields.Date.today(),
                'currency_id': self.env.company.currency_id.id,
                'payment_type': 'receive_money',
                'memo': self.invoice_id.name,
            })

            if line.attachment_ids:
                new_attachments = []
                for att in line.attachment_ids:
                    new_att = att.sudo().copy({
                        'res_model': 'pdc.wizard',
                        'res_id': payment.id,
                    })
                    new_attachments.append(new_att.id)
                payment.write({'attachment_ids': [(6, 0, new_attachments)]})

            if self.invoice_id.state == 'draft':
                self.invoice_id.action_post()

            if self.invoice_id:
                payment.write({'invoice_ids': [(6, 0, [self.invoice_id.id])]})

        return {'type': 'ir.actions.act_window_close'}


class BulkPDCLine(models.TransientModel):
    _name = 'bulk.pdc.line'
    _description = 'Bulk PDC Line'

    wizard_id = fields.Many2one('bulk.pdc.upload', string='Wizard')
    # inv_id = fields.Many2one('account.move', string='Invoice', readonly=True)
    due_date = fields.Date(string='Due Date')
    amount = fields.Float(string='Amount')
    cheque_ref = fields.Char(string='Cheque Ref')
    cheque_num = fields.Char(string='Cheque Number')
    journal_id = fields.Many2one('account.journal', string='Journal')
    attachment_ids = fields.Many2many('ir.attachment', string='Attachments')

    # @api.model
    # def create(self, vals):
    #     record = super().create(vals)
    #     if record.wizard_id and not record.inv_id:
    #         first_line = record.wizard_id.pdc_lines[:1]
    #         if first_line and first_line.inv_id:
    #             record.inv_id = first_line.inv_id.id
    #     return record

    # @api.onchange('wizard_id')
    # def _onchange_wizard_id(self):
    #     if self.wizard_id and not self.inv_id:
    #         first_line = self.wizard_id.pdc_lines[:1]
    #         if first_line and first_line.inv_id:
    #             self.inv_id = first_line.inv_id.id

    # @api.onchange('due_date')
    # def _onchange_due_date(self):
    #     if self.due_date and self.due_date < fields.Date.today():
    #         raise UserError("Due date cannot be in the past.")
        