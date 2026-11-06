from odoo import models, fields, api

class AccountPayment(models.Model):
    _inherit = 'account.payment'

    invoice_id = fields.Char(string='Invoice Id', readonly=True)
    cheque_ref = fields.Char(string='Cheque Reference', readonly=True)
    report_ref = fields.Char('Report Reference')
    # report_ref = fields.Char('Report Reference', compute='_compute_report_ref')


    # @api.depends('invoice_id')
    # def _compute_report_ref(self):
    #     for rec in self:
    #         rec.report_ref = False
    #         invoice = rec.invoice_id
    #         if not invoice:
    #             continue
    #         contract_seq = invoice.tenancy_id.tenancy_seq
    #         if not contract_seq:
    #             continue
    #         cheque_ref = rec.cheque_ref or ''
    #         date_str = rec.date or ''
    #         rec.report_ref = f"{contract_seq}-{cheque_ref}-{date_str}"

    def get_invoice_id(self):
        if self.invoice_id :
            invoice = self.env['account.move'].browse(int(self.invoice_id))
        return invoice.name


