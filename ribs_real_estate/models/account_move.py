from odoo import models, fields, api, _
import base64
from datetime import datetime, timedelta
from collections import defaultdict
from odoo.exceptions import UserError
import logging

_logger = logging.getLogger(__name__)


class AccountMove(models.Model):
    _inherit = 'account.move'
    
    pending_invoice_reminder_sent = fields.Boolean(string="Pending Invoice Reminder Sent", default=False)
    invoice_id_added_to_payments = fields.Char(compute='_compute_add_report_id', string='Additional Report ID')
    report_ref = fields.Char(string='Report Ref', store=True)

    @api.depends('matched_payment_ids')
    def _compute_add_report_id(self):
        for rec in self:
            rec.invoice_id_added_to_payments = False
            if rec.matched_payment_ids:
                for payment in rec.matched_payment_ids:
                    payment.invoice_id = self.id
            elif rec.pdc_payment_count:
                for pdc in rec.pdc_payment_ids:
                    pdc.invoice_id = self.id

    # def write(self, vals):
    #     if self.env.context.get('skip_report_ref'):
    #         return super().write(vals)

    #     res = super().write(vals)

    #     for record in self:
    #         if record.tenancy_id:
    #             suffix = (
    #                 f"{record.tenancy_id.property_project_id.name}--"
    #                 f"{record.tenancy_id.property_id.name}--"
    #                 f"{record.tenancy_id.tenancy_seq} "
    #                 f"(From: {record.tenancy_id.start_date} "
    #                 f"To: {record.tenancy_id.end_date})"
    #             )

    #             record.with_context(skip_report_ref=True).write({
    #                 'report_ref': suffix
    #             })

    #     return res



    @api.model_create_multi
    def create(self, vals_list):
        record = super().create(vals_list)

        if record.tenancy_id:
            property_name = (
                record.tenancy_id.property_id.name
                if record.tenancy_id.property_id
                else ", ".join(record.tenancy_id.unit_ids.mapped("name"))
            )
            suffix = (
                f"{record.tenancy_id.property_project_id.name}--"
                f"{property_name}--"
                f"{record.tenancy_id.tenancy_seq} "
                f"(From: {record.tenancy_id.start_date} "
                f"To: {record.tenancy_id.end_date})"
            )
            record.with_context(skip_report_ref=True).write({
                'report_ref': suffix
            })
        return record

    def send_pending_invoice_reminder(self):
        today = datetime.today().date()
        last_week = today - timedelta(days=6)

        invoices = self.env['account.move'].search([
            ('pending_invoice_reminder_sent', '=', False),
            ('move_type', '=', 'out_invoice'),
            ('payment_state', '!=', 'paid'),
            ('tenancy_property_id', '!=', False),
            ('invoice_date', '>=', last_week),
            ('invoice_date', '<=', today),
        ])
        
        if not invoices:
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
                'account.action_report_invoice_document',
                'account.report_invoice',
                'account.account_invoices'
            ]
            for xml_id in possible_xml_ids:
                try:
                    report = self.env.ref(xml_id).sudo()
                    if report._name == 'ir.actions.report' and report.report_type == 'qweb-pdf':
                        break
                except ValueError:
                    continue
            if not report:
                raise UserError(
                    "Invoice report not found. Tried XML IDs: {}. "
                    "Please ensure the 'account' module is installed and the invoice report exists.".format(possible_xml_ids)
                )

        report_ref = report.report_name 

        for partner, partner_invoices in grouped.items():
            if not partner.email:
                continue  
            attachments = []
            for inv in partner_invoices:
                try:
                    pdf_content, _ = self.env['ir.actions.report']._render_qweb_pdf(
                        report_ref=report_ref,
                        res_ids=[inv.id]
                    )
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
                    raise UserError(f"Failed to generate PDF for invoice {inv.name}: {str(e)}")
            
            if not attachments:
                continue  

            mail_values = {
                'subject': f'Pending Invoices Reminder - {partner.name}',
                'body_html':  f'''<p>Dear {partner.name},</p>
                                <p>Please find attached your pending invoices from the last 7 days.</p>
                                <p>Regards</p>
                                <p>Thank You</p>''',
                'email_to': partner.email,
                'attachment_ids': [(6, 0, attachments)],
            }
            try:
                self.env['mail.mail'].sudo().create(mail_values).send()
                for inv in partner_invoices:
                    inv.sudo().write({'pending_invoice_reminder_sent': True})
            except Exception as e:
                raise UserError(f'Failed to send email to {partner.email}: {str(e)}')

    def action_register_payment(self, ctx=None):
        res = super().action_register_payment()

        extra_context = {
            'invoice_id': self.id,  
        }

        if 'context' in res:
            res['context'].update(extra_context)
        else:
            res['context'] = extra_context

        return res

    def open_deferred_entries(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _("Deferred Entries"),
            'res_model': 'account.move.line',
            'domain': [('id', 'in', self.deferred_move_ids.line_ids.ids)],
            'views': [(self.env.ref('account_accountant.view_deferred_entries_tree').id, 'list')],
            'context': {
                'expand': True,
            }
        }
    
    def js_assign_outstanding_line(self, line_id):
        print(line_id,'line_idline_id')
        ''' Called by the 'payment' widget to reconcile a suggested journal item to the present
        invoice.

        :param line_id: The id of the line to reconcile with the current invoice.
        '''
        self.ensure_one()
        lines = self.env['account.move.line'].browse(line_id)
        lines += self.line_ids.filtered(lambda line: line.account_id == lines[0].account_id and not line.reconciled)

        #assign the analytic account to je
        analytic_account = self.tenancy_property_id.analytic_account_id
        if analytic_account:
            move_lines = lines.mapped('move_id').line_ids
            move_lines.write({
                'analytic_distribution': {analytic_account.id: 100}
            })

        return lines.reconcile()


class account_move(models.Model):
    _inherit = 'account.move.line'

    report_ref = fields.Char('Report Ref', compute='_compute_report_ref', store=True)
    # Provided by Enterprise account_accountant; declared here so contract
    # periods can still be stored on Community. Same column names, so the
    # data carries over if Enterprise is installed later.
    deferred_start_date = fields.Date(string="Start Date", copy=False)
    deferred_end_date = fields.Date(string="End Date", copy=False)

    @api.depends('move_id.report_ref')
    def _compute_report_ref(self):
        for line in self:
            line.report_ref = line.move_id.report_ref

    @api.depends("account_id", "partner_id", "product_id")
    def _compute_analytic_distribution(self):
        """Update analytic distribution on move lines."""
        super()._compute_analytic_distribution()

        ctx_tenancy = self.env.context.get("tenancy_id")

        for line in self:
            tenancy = (
                line.move_id.tenancy_property_id
                or ctx_tenancy
                or (
                    line.move_id.maintenance_request_id.property_id
                    if line.move_id.maintenance_request_id
                    else False
                )
            )

            dist = {}

            # ==========================================================
            # Multi Contract
            # ==========================================================
            if (
                line.move_id.tenancy_id
                and line.move_id.tenancy_id.is_multi_contract
            ):
                project = line.move_id.tenancy_id.property_project_id

                property_type = (
                    project.property_type_account_id.id
                    if project and project.property_type_account_id
                    else False
                )

                building = (
                    project.building_account_id.id
                    if project and project.building_account_id
                    else False
                )

                unit = line.move_id.tenancy_id.unit_ids.filtered(
                    lambda u: u.default_product_id.id == line.product_id.id
                )[:1]


                if unit:
                    account_ids = []

                    if property_type:
                        account_ids.append(str(property_type))

                    if building:
                        account_ids.append(str(building))

                    if unit.unit_account_id:
                        account_ids.append(str(unit.unit_account_id.id))

                    if account_ids:
                        dist[",".join(account_ids)] = 100

            # ==========================================================
            # Single Contract
            # ==========================================================
            else:
                if tenancy:
                    project = tenancy.property_project_id

                    property_type = (
                        project.property_type_account_id.id
                        if project and project.property_type_account_id
                        else False
                    )

                    building = (
                        project.building_account_id.id
                        if project and project.building_account_id
                        else False
                    )

                    account_ids = []

                    if property_type:
                        account_ids.append(str(property_type))

                    if building:
                        account_ids.append(str(building))

                    if tenancy.unit_account_id:
                        account_ids.append(str(tenancy.unit_account_id.id))

                    if account_ids:
                        dist[",".join(account_ids)] = 100

            if dist:
                _logger.warning("Before: %s", line.analytic_distribution)
                line.analytic_distribution = dist
                _logger.warning("After: %s", line.analytic_distribution)

    def _inverse_analytic_distribution(self):
        """Update analytic distribution for tax lines."""
        super()._inverse_analytic_distribution()

        for line in self:
            move = line._origin.move_id

            if line.analytic_distribution:
                continue

            tenancy = (
                move.tenancy_property_id
                or (
                    move.maintenance_request_id.property_id
                    if move.maintenance_request_id
                    else False
                )
            )

            dist = {}

            # ==========================================================
            # Multi Contract
            # ==========================================================
            if move.tenancy_id and move.tenancy_id.is_multi_contract:
                project = move.tenancy_id.property_project_id

                property_type = (
                    project.property_type_account_id.id
                    if project and project.property_type_account_id
                    else False
                )

                building = (
                    project.building_account_id.id
                    if project and project.building_account_id
                    else False
                )

                unit = move.tenancy_id.unit_ids.filtered(
                    lambda u: u.default_product_id == line.product_id
                )[:1]

                if unit:
                    account_ids = []

                    if property_type:
                        account_ids.append(str(property_type))

                    if building:
                        account_ids.append(str(building))

                    if unit.unit_account_id:
                        account_ids.append(str(unit.unit_account_id.id))

                    if account_ids:
                        dist[",".join(account_ids)] = 100

            # ==========================================================
            # Single Contract
            # ==========================================================
            else:
                if tenancy:
                    project = tenancy.property_project_id

                    property_type = (
                        project.property_type_account_id.id
                        if project and project.property_type_account_id
                        else False
                    )

                    building = (
                        project.building_account_id.id
                        if project and project.building_account_id
                        else False
                    )

                    account_ids = []

                    if property_type:
                        account_ids.append(str(property_type))

                    if building:
                        account_ids.append(str(building))

                    if tenancy.unit_account_id:
                        account_ids.append(str(tenancy.unit_account_id.id))

                    if account_ids:
                        dist[",".join(account_ids)] = 100

            if dist:
                _logger.warning("Before: %s", line.analytic_distribution)
                line.analytic_distribution = dist
                _logger.warning("After: %s", line.analytic_distribution)
