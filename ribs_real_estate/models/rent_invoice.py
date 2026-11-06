from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError
import base64
import logging
_logger = logging.getLogger(__name__)
from collections import defaultdict


class RentInvoiceInherit(models.Model):
    _inherit = 'rent.invoice'
    
    invoice_state = fields.Selection(related='rent_invoice_id.state', string='Invoice State', readonly=True)
    contract_type = fields.Selection(related='tenancy_id.contract_type', string='Contract State', readonly=True)
    

    def send_due_invoice_reminder(self):
        """Send due invoice reminder email with multiple invoice PDFs attached"""
        today = fields.Date.today()
        due_invoices = self.env['account.move'].search([
            ('move_type', '=', 'out_invoice'),
            ('payment_state', 'not in', ['paid','draft']),
            ('tenancy_property_id', '!=', False),
            ('invoice_date', '>', today)
        ])
        if due_invoices:
            self.send_overdue_invoice_reminder(due_invoices)
        else:
            _logger.info("No due invoices found for sending reminders.")

    def action_due_reminder(self):
        invoice = self.env['account.move'].browse(self.rent_invoice_id.id)
        if invoice:
            if invoice.state != 'posted':
                raise UserError("Invoice is not validated yet.")
            else:
                self.send_overdue_invoice_reminder(invoice)
                
                
    def send_overdue_invoice_reminder(self, invoices):
        """Send overdue invoice reminder email with multiple invoice PDFs attached"""

        if not invoices:
            _logger.warning("No invoices provided for sending reminders.")
            return  
        
        grouped = defaultdict(list)
        for inv in invoices:
            grouped[inv.partner_id].append(inv)

        report = self.env['ir.actions.report'].search([
            ('report_name', '=', 'account.report_invoice'),
            ('model', '=', 'account.move'),
            ('report_type', '=', 'qweb-pdf')
        ], limit=1)

        if not report:
            possible_xml_ids = [
                'account.account_invoices_without_payment',
                'account.account_invoices',
                'account.action_report_invoice_document',
                'account.report_invoice'
            ]
            for xml_id in possible_xml_ids:
                try:
                    report = self.env.ref(xml_id).sudo()
                    if report._name == 'ir.actions.report' and report.report_type == 'qweb-pdf':
                        break
                except ValueError:
                    continue
            if not report:
                _logger.error("Invoice report not found. Tried XML IDs: %s", possible_xml_ids)
                raise UserError(
                    _("Invoice report not found. Tried XML IDs: %s. "
                      "Please ensure the 'account' module is installed.") % possible_xml_ids
                )

        report_ref = report.report_name 

        for partner, partner_invoices in grouped.items():
            if not partner.email:
                _logger.warning("Skipping partner %s: No email address configured", partner.name)
                continue

            attachments = []
            for inv in partner_invoices:
                if inv.state != 'posted':
                    _logger.warning("Skipping invoice %s: Not in posted state", inv.name)
                    continue
                if not inv.invoice_line_ids:
                    _logger.warning("Skipping invoice %s: No invoice lines", inv.name)
                    continue

                try:
                    pdf_content, _content_type = self.env['ir.actions.report']._render_qweb_pdf(
                        report_ref=report_ref,
                        res_ids=[inv.id]
                    )
                    _logger.info("PDF generated for invoice %s (ID=%s)", inv.name, inv.id)
                    pdf_name = f"Invoice_{inv.name.replace('/', '_')}.pdf" if isinstance(inv.name, str) else "draft.pdf"

                    attachment = self.env['ir.attachment'].sudo().create({
                        'name': pdf_name,
                        'type': 'binary',
                        'raw': pdf_content,
                        'res_model': 'account.move',
                        'res_id': inv.id,
                        'mimetype': 'application/pdf',
                    })
                    attachments.append(attachment.id)
                except Exception as e:
                    _logger.error("Failed to generate PDF for invoice %s (ID=%s): %s", inv.name, inv.id, str(e))
                    continue

            if not attachments:
                _logger.warning("No valid PDFs generated for partner %s", partner.name)
                continue

            invoice_lines = "".join([
                _("<li>%s | Due: %s | Pending: %.2f</li>") % (
                    inv.name, inv.invoice_date_due or '', inv.amount_residual
                )
                for inv in partner_invoices if inv.state == 'posted'
            ])

            body_html = _(
                "<p>Dear %(customer)s,</p>"
                "<p>This is a reminder that the following invoices are still unpaid:</p>"
                "<ul>%(lines)s</ul>"
                "<p>Please make the payment at your earliest convenience.</p>"
                "<p>Thank you,</p>"
            ) % {
                'customer': partner.name,
                'lines': invoice_lines
            }

            company_secretary_email = self.env.company.company_secretary.work_email
            tenant_email = inv.partner_id.email
            manager_email = inv.tenancy_property_id.property_manager.work_email

            email_list = [email for email in [tenant_email, company_secretary_email, manager_email] if email]
            email_to = ','.join(email_list)

            mail_values = {
                'subject': _("Payment Reminder - %s") % partner.name,
                'body_html': body_html,
                'email_to': email_to,
                'attachment_ids': [(6, 0, attachments)],
            }

            try:
                mail = self.env['mail.mail'].sudo().create(mail_values)
                mail.send()
                _logger.info("Email sent to %s with attachments: %s", partner.email, attachments)
                # Optionally update invoices (if you have a similar field)
                # for inv in partner_invoices:
                #     inv.sudo().write({'pending_invoice_reminder_sent': True})
            except Exception as e:
                _logger.error("Failed to send email to %s: %s", partner.email, str(e))
                continue

    def _process_manual_daily_invoice(self):
        """Process Daily Invoice"""
        invoice_post_type = self.env['ir.config_parameter'].sudo().get_str(
            'rental_management.invoice_post_type', False)
        invoice_lines = [(0, 0, {
            'product_id': self.tenancy_id.installment_item_id.id,
            'name': self.description,
            'quantity': 1,
            'price_unit': self.amount,
            'tax_ids': self.tenancy_id.tax_ids.ids if self.tenancy_id.instalment_tax else False,
            # "account_id": self.tenancy_id.property_project_id.invoice_creation_id.id,
        })]
        if self.tenancy_id.is_extra_service and self.tenancy_id.extra_service_invoice == 'merge':
            for line in self.tenancy_id.extra_services_ids.filtered(
                    lambda line: line.service_type == 'monthly'):
                invoice_lines.append((0, 0, {
                    'product_id': line.service_id.id,
                    'name': "Service Type : Recurring" + "\n" "Service : " + str(
                        line.service_id.name),
                    'quantity': 1,
                    'price_unit': line.price * self.service_days,
                    'tax_ids': line.tenancy_id.tax_ids.ids if line.tenancy_id.service_tax else False,
                    # "account_id": self.tenancy_id.property_project_id.invoice_creation_id.id,
                }))
        if (self.tenancy_id.is_maintenance_service
                and self.tenancy_id.maintenance_rent_type == 'recurring'
                and self.tenancy_id.maintenance_service_invoice == 'merge'):
            invoice_lines.append((0, 0, {
                'product_id': self.tenancy_id.maintenance_item_id.id,
                'name': "Recurring Maintenance of " + self.tenancy_id.property_id.name,
                'quantity': 1,
                'price_unit': self.tenancy_id.total_maintenance * self.service_days,
                'tax_ids': False,
                # "account_id": self.tenancy_id.property_project_id.invoice_creation_id.id,
            }))
        invoice_id = self.env['account.move'].sudo().create({
            'partner_id': self.customer_id.id,
            'move_type': 'out_invoice',
            'invoice_date': self.invoice_date,
            'tenancy_id': self.tenancy_id.id,
            'invoice_line_ids': invoice_lines,
        })
        if invoice_post_type == 'automatically':
            invoice_id.action_post()
        self.rent_invoice_id = invoice_id.id
        self.service_amount = ((invoice_id.amount_total - self.amount)
                               if invoice_id.amount_total > 0 else 0.0)
        self.tenancy_id.action_send_tenancy_reminder()
        
        
    def _process_manual_invoice(self):
        """Process Manual Invoice : Monthly, Quarterly Yearly"""
        invoice_post_type = self.env['ir.config_parameter'].sudo().get_str(
            'rental_management.invoice_post_type', False)
        invoice_lines = []
        amount = 0.0
        if self.tenancy_id.is_extra_service and self.tenancy_id.extra_service_invoice == 'merge':
            if self.tenancy_id.payment_term in ["monthly", "half_year"]:
                for line in self.tenancy_id.extra_services_ids:
                    if line.service_type == "monthly":
                        amount = amount + line.price
                        service_invoice_record = {
                            'product_id': line.service_id.id,
                            'name': "Service Type : Recurring" + "\n" "Service : " + str(
                                line.service_id.name),
                            'quantity': 1,
                            'price_unit': line.price,
                            'tax_ids': line.tenancy_id.tax_ids.ids if line.tenancy_id.service_tax else False,
                            # "account_id": self.tenancy_id.property_project_id.invoice_creation_id.id,
                        }
                        invoice_lines.append((0, 0, service_invoice_record))
            if self.tenancy_id.payment_term == "quarterly":
                for line in self.tenancy_id.extra_services_ids:
                    if line.service_type == "monthly":
                        amount = amount + (line.price * (self.remain if self.remain > 0 else 3))
                        service_invoice_record = {
                            'product_id': line.service_id.id,
                            'name': "Service Type : Recurring" + "\n" "Service : " + str(
                                line.service_id.name),
                            'quantity': self.remain if self.remain > 0 else 3,
                            'price_unit': line.price,
                            'tax_ids': line.tenancy_id.tax_ids.ids if line.tenancy_id.service_tax else False,
                            # "account_id": self.tenancy_id.property_project_id.invoice_creation_id.id,
                        }
                        invoice_lines.append((0, 0, service_invoice_record))
            if self.tenancy_id.payment_term == "year":
                for line in self.tenancy_id.extra_services_ids:
                    if line.service_type == "monthly":
                        amount = amount + (line.price * 12)
                        service_invoice_record = {
                            'product_id': line.service_id.id,
                            'name': "Service Type : Recurring" + "\n" "Service : " + str(
                                line.service_id.name),
                            'quantity': 1,
                            'price_unit': line.price,
                            'tax_ids': line.tenancy_id.tax_ids.ids if line.tenancy_id.service_tax else False,
                            # "account_id": self.tenancy_id.property_project_id.invoice_creation_id.id,
                        }
                        invoice_lines.append((0, 0, service_invoice_record))
        if (self.tenancy_id.is_maintenance_service
                and self.tenancy_id.maintenance_rent_type == 'recurring'
                and self.tenancy_id.maintenance_service_invoice == 'merge'):
            maintenance_record = {
                'product_id': self.tenancy_id.maintenance_item_id.id,
                'name': "Recurring Maintenance of " + self.tenancy_id.property_id.name,
                'quantity': 1,
                'price_unit': self.tenancy_id.total_maintenance,
                'tax_ids': self.tenancy_id.tax_ids.ids if self.tenancy_id.instalment_tax else False,
                # "account_id": self.tenancy_id.property_project_id.invoice_creation_id.id,
            }
            if self.tenancy_id.payment_term == 'quarterly':
                maintenance_record['quantity'] = self.remain if self.remain > 0 else 3
            amount = amount + (maintenance_record['quantity'] * self.tenancy_id.total_maintenance)
            invoice_lines.append((0, 0, maintenance_record))
        record = {
            'product_id': self.tenancy_id.installment_item_id.id,
            'name': self.description,
            'quantity': 1,
            'price_unit': self.amount,
            'tax_ids': self.tenancy_id.tax_ids.ids if self.tenancy_id.instalment_tax else False,
            # "account_id": self.tenancy_id.property_project_id.invoice_creation_id.id,
        }
        invoice_lines.append((0, 0, record))
        rent_record = {
            'partner_id': self.customer_id.id,
            'move_type': 'out_invoice',
            'invoice_date': self.invoice_date,
            'tenancy_id': self.tenancy_id.id,
            'invoice_line_ids': invoice_lines,
        }
        invoice_id = self.env['account.move'].create(rent_record)
        self.service_amount = ((invoice_id.amount_total - self.amount)
                               if invoice_id.amount_total > 0 else 0.0)
        if invoice_post_type == 'automatically':
            invoice_id.action_post()
        self.rent_invoice_id = invoice_id.id
        self.tenancy_id.action_send_tenancy_reminder()

    def _process_separate_invoices(self, maintenance=None, utility=None):
        """Process Utility and Maintenance Separate Invoices"""
        qty = 1
        if self.tenancy_id.rent_unit == 'Day':
            qty = self.service_days
        else:
            if self.tenancy_id.payment_term == 'quarterly':
                qty = self.remain if self.remain > 0 else 3
        if maintenance:
            maintenance_invoice_id = self.env['account.move'].create({
                "partner_id": self.tenancy_id.tenancy_id.id,
                "move_type": "out_invoice",
                "invoice_date": self.invoice_date,
                "tenancy_id": self.tenancy_id.id,
                "invoice_line_ids": [(0, 0, {
                    "product_id": self.tenancy_id.maintenance_item_id.id,
                    "name": "Recurring Maintenance of " + self.tenancy_id.property_id.name,
                    "quantity": qty,
                    "price_unit": self.tenancy_id.total_maintenance,
                    # "account_id": self.tenancy_id.property_project_id.invoice_creation_id.id,
                })],
            })
            self.env['rent.invoice'].create({
                "tenancy_id": self.tenancy_id.id,
                "type": "maintenance",
                "invoice_date": self.invoice_date,
                "amount": maintenance_invoice_id.amount_total,
                "description": "Recurring Maintenance of " + self.tenancy_id.property_id.name,
                "rent_invoice_id": maintenance_invoice_id.id})
        if utility:
            service_invoice_lines = []
            for line in self.tenancy_id.extra_services_ids.filtered(
                    lambda line: line.service_type == 'monthly'):
                service_invoice_lines.append((0, 0, {
                    "product_id": line.service_id.id,
                    "name": f"Service Type : Recurring - {line.service_id.name}",
                    "quantity": qty,
                    "price_unit": line.price,
                    "tax_ids": self.tenancy_id.tax_ids.ids if self.tenancy_id.service_tax else False,
                    # "account_id": self.tenancy_id.property_project_id.invoice_creation_id.id,
                }))
            service_invoice_id = self.env['account.move'].create({
                "partner_id": self.tenancy_id.tenancy_id.id,
                "move_type": "out_invoice",
                "invoice_date": self.invoice_date,
                "tenancy_id": self.tenancy_id.id,
                "invoice_line_ids": service_invoice_lines,
            })
            self.env['rent.invoice'].create({
                "tenancy_id": self.tenancy_id.id,
                "type": "other",
                "invoice_date": self.invoice_date,
                "amount": service_invoice_id.amount_total,
                "description": "Recurring Utility Services",
                "rent_invoice_id": service_invoice_id.id})

    def action_upload_pdc(self):
        self.ensure_one()
        BulkPDC = self.env['bulk.pdc.upload']

        wizard = BulkPDC.create({
            'tenancy_id': self.tenancy_id.id,
            'journal_id': self.tenancy_id.property_project_id.cuc_account_id.id,
            'invoice_id': self.rent_invoice_id.id,
        })

        # line_vals = []
        # line_vals.append((0, 0, {
        #     'inv_id': self.rent_invoice_id.id,
        #     'due_date': self.invoice_date,
        #     'amount': self.amount,
        # }))
        # wizard.write({'pdc_lines': line_vals})

        return {
            'name': _('Bulk PDC Upload'),
            'type': 'ir.actions.act_window',
            'res_model': 'bulk.pdc.upload',
            'view_mode': 'form',
            'target': 'new',
            'res_id': wizard.id, 
            'view_id': self.env.ref('ribs_real_estate.view_bulk_pdc_wizard_form').id,
        }


