from odoo import models, fields, api
from odoo.exceptions import UserError

class PropertyPayment(models.TransientModel):
    """Rent contract extra payment"""
    _inherit = 'property.payment.wizard'
    
    
    def property_payment_action(self):
        """Process rent contract payment"""
        if self.type == 'extra_service':
            invoice_id = self.env['account.move'].sudo().create({
                'partner_id': self.customer_id.id,
                'tenancy_id': self.tenancy_id.id,
                'move_type': 'out_invoice',
                'invoice_date': self.invoice_date,
                'invoice_line_ids': [(0, 0, {
                    'product_id': self.service_id.id,
                    'name': self.description,
                    'quantity': 1,
                    'price_unit': self.amount,
                    'tax_ids': self.tax_ids.ids,
                    # 'account_id': self.tenancy_id.property_id.property_project_id.invoice_creation_id.id,
                })]
            })
            self.env['contract.extra.service.line'].sudo().create({
                'contract_id': self.tenancy_id.id,
                'service_id': self.service_id.id,
                'price': invoice_id.amount_total,
                'invoice_id': invoice_id.id
            })
            if not self.tenancy_id.is_added_services:
                self.tenancy_id.is_added_services = True
        else:
            self.process_contract_invoice()

    def process_contract_invoice(self):
        """Process contract payment invoice"""
        invoice_post_type = self.env['ir.config_parameter'].sudo(
        ).get_str('rental_management.invoice_post_type', False)
        invoice_id = self.env['account.move'].sudo().create({
            'partner_id': self.customer_id.id,
            'tenancy_id': self.tenancy_id.id,
            'move_type': 'out_invoice',
            'invoice_date': self.invoice_date,
            'invoice_line_ids': [(0, 0, {
                'product_id': self.service_id.id,
                'name': self.description,
                'quantity': 1,
                'price_unit': self.amount,
                'tax_ids': self.tax_ids.ids,
                # 'account_id': self.tenancy_id.property_id.property_project_id.invoice_creation_id.id,
            })]
        })
        if invoice_post_type == 'automatically':
            invoice_id.action_post()
        self.env['rent.invoice'].create({
            'tenancy_id': self.tenancy_id.id,
            'type': self.type,
            'invoice_date': self.invoice_date,
            'amount': self.amount,
            'description': self.description,
            'rent_invoice_id': invoice_id.id
        })

    def property_bill_action(self):
        """Property Rent contract bill """
        if self.amount < 1:
            raise UserError("Amount should be greater than zero.")
        invoice_post_type = self.env['ir.config_parameter'].sudo(
        ).get_str('rental_management.invoice_post_type', False)
        data = {
            'partner_id': self.vendor_id.id,
            'tenancy_id': self.tenancy_id.id,
            'move_type': 'in_invoice',
            'invoice_date': self.invoice_date,
            'invoice_line_ids': [(0, 0, {
                'product_id': self.service_id.id,
                'name': self.description,
                'quantity': 1,
                'price_unit': self.amount,
                'tax_ids': self.tax_ids.ids,
                # 'account_id': self.tenancy_id.property_id.property_project_id.bill_creation_id.id,
            })]
        }
        bill_id = self.env['account.move'].sudo().create(data)
        if invoice_post_type == 'automatically':
            bill_id.action_post()

        self.env['rent.bill'].create({
            'tenancy_id': self.tenancy_id.id,
            'bill_type': self.bill_type,
            'invoice_date': self.invoice_date,
            'amount': self.amount,
            'description': self.description,
            'rent_bill_id': bill_id.id,
            'vendor_id': self.vendor_id.id
        })
