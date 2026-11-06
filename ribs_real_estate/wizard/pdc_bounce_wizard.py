from odoo import fields, models
from datetime import date, datetime, time, timedelta


class PdcBounceWizard(models.TransientModel):
    _name = 'pdc.bounce.wizard'
    _description = "PDC Bounce Wizard"

    penalty_confirmation = fields.Boolean(default=False, string='''Do you want to apply a penalty for the bounced 
                                          cheque? This will generate a new invoice under the contract 
                                          for the penalty amount.''')
    penalty_amount = fields.Float(string='Penalty Amount', required=True)


    def action_apply(self):
        inv_id = self.env.context.get('default_inv')
        pdc_name = self.env.context.get('default_name')
        pdc = self.env['pdc.wizard'].search([('name', '=', pdc_name)])
        invoice = self.env['account.move'].search([('id', '=', inv_id)], limit=1)
        if not invoice.tenancy_id:
            pdc.action_bounced()
        product = self.env['product.product'].search([('name', '=', 'PDC Bouncing Charges')])

        invoice_lines = []

        if not product:
            product = self.env['product.product'].create([{'name': 'PDC Bouncing Charges'}])
            
        description = f"""Bouncing Charges for {invoice.name} Invoice and Payment of {pdc_name}"""
        invoice_lines.append((0, 0, {
            'product_id': product.id,
            'quantity': 1,
            'name': description,
            'price_unit': self.penalty_amount,
            'tax_ids': None,
            # 'account_id': invoice.tenancy_property_id.property_project_id.pdc_penalty_creation_id.id,
        }))

        invoice_id = self.env['account.move'].sudo().create({
            'partner_id': invoice.partner_id.id,
            'move_type': 'out_invoice',
            'invoice_date': date.today(),
            'invoice_line_ids': invoice_lines,
            'tenancy_id': invoice.tenancy_id.id,
        })
        invoice_id.action_post()         
        rent_invoice = self.env['rent.invoice'].create([
        {
            'tenancy_id': invoice.tenancy_id.id,
            'customer_id': invoice.partner_id.id,
            'type': 'penalty',
            'rent_invoice_id': invoice_id.id,
            'description': description,
            'amount': self.penalty_amount,
            'invoice_date': date.today(),
        }])
        invoice.tenancy_id.write({
            'rent_invoice_ids': [(4, rent_invoice.id)]
        })
        pdc.action_bounced()
        # pdc.write({'state': 'bounced'})
