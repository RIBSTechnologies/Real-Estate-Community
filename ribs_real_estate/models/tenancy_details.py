from odoo.exceptions import ValidationError, UserError
from odoo import api, fields, models, _
from dateutil.relativedelta import relativedelta
import base64
import io
import zipfile
from datetime import date, timedelta
import calendar
import logging
_logger = logging.getLogger(__name__)



class TenancyDetails(models.Model):
    _inherit = 'tenancy.details'

    # Temporarily disabled at the user's request - the "Some contracts are
    # active for this time period" overlap warning was blocking legitimate
    # multi-contract combined bookings. Commented out for now, not removed,
    # so it can be re-enabled later (see rental_management/models/rent_contract.py
    # _compute_is_contract_period_available for the original logic).
    def _compute_is_contract_period_available(self):
        for rec in self:
            rec.is_contract_period_available = True
    
    document_count = fields.Integer(compute='compute_documents_count')
    tenant_document_count = fields.Integer(compute='compute_tenant_documents_count')
    new_contract_sent = fields.Boolean(string="New Contract Sent", default=False)
    is_renewed_contract = fields.Boolean(string="Is Renewed Contract", default=False)
    sent_welcome_pack_flag = fields.Boolean(string="Sent Welcome Pack", default=False)
    key_card_remote = fields.Boolean(string="Key Card or Remote", default=False)
    parking_card_remote = fields.Boolean(string="Parking Card or Remote", default=False)
    damage_or_replacement = fields.Boolean(string="Any Damage or Replacement", default=False)
    damage_or_replacement_ids = fields.One2many('damage.replacement.records', 'contract_id')
    final_inspection_report = fields.Boolean(string="Is Final Inspection Report Completed", default=False)
    dewa_certificate_confirmation = fields.Boolean(string="Is Dewa Certificate Available", default=False)
    issue_clearance_certificate = fields.Many2many('ir.attachment', string='Attachements')
    issue_clearance_sent = fields.Boolean(default=False)
    total_rent_year = fields.Monetary(string="Total Rent (Yearly)", tracking=True)
    grace_period_value = fields.Integer(string="Grace Period")
    grace_period_unit = fields.Selection([
        ('days', 'Days'),
        ('month', 'Month'),
        ('year', 'Year'),
    ], string="Grace Period Unit", default='days')
    grace_period_start_date = fields.Date(string="Grace Start Date", compute="_compute_grace_period_dates", store=True)
    grace_period_end_date = fields.Date(string="Grace End Date", compute="_compute_grace_period_dates", store=True)
    commercial_size = fields.Float(string="Unit Size")
    commercial_rate = fields.Monetary(string="Rate")
    additional_terms = fields.Html(
        string="Additional Terms",
        default="Tenant has to pay AED 1,000.00 penalty for every bounce cheque or withdraw cheque.",
    )
    additional_term_ids = fields.One2many(
        'contract.additional.term.line', 'contract_id', string="Additional Terms",
        default=lambda self: [(0, 0, {
            'sequence': 1,
            'description': "Tenant has to pay AED 1,000.00 penalty for every bounce cheque or withdraw cheque.",
        })])
    contract_value = fields.Monetary(string="Contract Value", help="Total value of the contract", 
                    readonly=True, compute="_compute_contract_value")
    # responsible_id = fields.Many2one(
    #     'res.users',
    #     default=lambda self: self.env.user and self.env.user.id or False,
    #     string="Created By")

    activities_created = fields.Boolean('Activities Created')

    #  added this field because it is in hinawi
    contract_date = fields.Date('Contract Date', default=fields.Date.today)
    temp_seq = fields.Char('Tenancy Sequence')
    contract_payment_ids = fields.One2many('contract.payments', 'contract_id', string='contract_payment_ids')

    total_contract_value = fields.Monetary(
        string="Total Contract Value",
        store=True,
        readonly=True,
    )
    total_value_breakdown = fields.Html(string="Amount" ,compute="_compute_breakdown")
    remaining_to_pay = fields.Monetary(
        string="Balance",
        store=True,
        readonly=True,
        compute='compute_remaining_value'
    )
    contract_type = fields.Selection(selection_add=[('waiting', 'Waiting For Approval'),
                                    ('terminated', 'Terminated'),
                                    ('pre_terminated', 'Pre Terminated'),
                                    ('closure_pending_approval', 'Closure - First Approval Pending'),
                                    ('closure_final_approval', 'Closure - Final Approval Pending')],
                                    tracking=True)
    payments_received = fields.Selection([('received', 'Received'), ('not_received', 'Not Received')],
                        string="Payments Received", default='not_received')
    is_confirmed_payment_mail_sent = fields.Boolean(default=False)
    new_rent_monthly = fields.Float(string='Increased Price')

    # for closing contract
    termination_requested_person = fields.Many2one("res.users", string="Requested Person")
    closing_reason = fields.Text(string="Closing Reason")
    closing_date = fields.Date(string="Closing Date")
    termination_type = fields.Selection([
        ('normal', 'Release Contract'),
        ('early', 'Termination'),
    ], string="Termination Type")
    first_level_approval_requested_to = fields.Many2many(
        'res.users',
        'tenancy_first_level_approval_rel',  
        'tenancy_id',                         
        'user_id',                            
        string="First Level Approval Requested To"
    )
    final_level_approval_requested_to = fields.Many2many(
        'res.users',
        'tenancy_final_level_approval_rel',   
        'tenancy_id',
        'user_id',
        string="Final Level Approval Requested To"
    )
    first_level_approval_comment = fields.Text(
        string="First Level Approval Comment",
        tracking=True
    )
    first_level_approved_by = fields.Many2one(
        'res.users',
        string="First Level Approved By",
        tracking=True
    )
    first_level_approved_date = fields.Date(
        string="First Level Approved On",
        tracking=True
    )
    final_level_approval_comment = fields.Text(
        string="Final Level Approval Comment",
        tracking=True
    )
    final_level_approved_by = fields.Many2one(
        'res.users',
        string="Final Level Approved By",
        tracking=True
    )
    final_level_approved_date = fields.Date(
        string="Final Level Approved On",
        tracking=True
    )
    if_penalty = fields.Boolean(string="Penalty Applied")
    penalty_amount = fields.Float(string="Penalty Amount")
    unit_ids = fields.Many2many('property.details', string="Units")
    is_multi_contract = fields.Boolean(string="Is Multi Contract", default=False)

    # For Year/Month/Day 
    is_by_date = fields.Boolean(string="By Date", default=False)

    # def _get_report_base_filename(self):
    #     self.ensure_one()
    #     return f"Invoice_{self.id}"


    def _get_property_queryset(self):
        self.ensure_one()

        if self.is_multi_contract:
            return self.unit_ids[0]

        return self.property_id

    def _get_property_name(self):
        self.ensure_one()

        if self.is_multi_contract:
            return ', '.join(self.unit_ids.mapped('name'))

        return self.property_id.name

    @api.model
    def tenancy_expire(self):
        """
        Scheduler : Expire rent contract
        """
        today_date = fields.Date.today()
        tenancy_contracts = self.env['tenancy.details'].sudo().search(
            [('contract_type', 'in', ['expiring_soon','running_contract'])])
        for rec in tenancy_contracts:
            if rec.days_left < 1:
                rec.compute_days_left()
            if rec.contract_type == 'running_contract' and (rec.end_date - today_date).days <= 180:
                rec.contract_type = 'expiring_soon'
            if rec.contract_type in ['expiring_soon','running_contract'] and today_date > rec.end_date:
                rec.contract_type = 'expire_contract'
            
    def action_contract_details(self):
        return {
            'type': 'ir.actions.act_window',
            'name': 'Request',
            'res_model': 'contract.documents',
            'domain': [('contract_id', '=', self.id)],
            'context': {'default_contract_id': self.id},
            'view_mode': 'kanban,list,form',
            'target': 'current'
        }
        
    def compute_documents_count(self):
        for rec in self:
            document_count = self.env['contract.documents'].search_count(
                [('contract_id', 'in', [rec.id])])
            rec.document_count = document_count
    
    def action_tenant_documents(self): 
        return {
            'type': 'ir.actions.act_window',
            'name': 'Tenant Documents',
            'res_model': 'partner.documents',
            'domain': [('partner_id', '=', self.tenancy_id.id)],
            'view_mode': 'kanban,list,form',
            'target': 'current',
            'context': {
                'default_partner_id': self.tenancy_id.id,
            }
        }

    def compute_tenant_documents_count(self):
        for rec in self:
            self.compute_remaining_value()
            base_value = rec.contract_value or 0.0
            services_total = 0.0

            for line in rec.added_service_ids:
                product = line.service_id
                price = line.price or 0.0

                taxes = product.taxes_id.filtered(lambda t: t.type_tax_use == 'sale')

                if taxes:
                    tax_res = taxes.compute_all(
                        price, 
                        currency=line.currency_id,
                        quantity=1,
                        product=product,
                        partner=rec.tenant_id if hasattr(rec, "tenant_id") else None
                    )
                    services_total += tax_res['total_included']
                else:
                    services_total += price

            tenancy_tax_amount = 0.0
            if rec.tax_ids:
                tax_res = rec.tax_ids.compute_all(
                    base_value,                   
                    currency=rec.currency_id,
                    quantity=1.0
                )
                tenancy_tax_amount = tax_res['total_included'] - tax_res['total_excluded']

            deposit = rec.deposit_amount if rec.is_any_deposit else 0.0
            rec.total_contract_value = base_value + services_total + tenancy_tax_amount + deposit



            tenant_document_count = self.env['partner.documents'].search_count(
                [('partner_id', 'in', [rec.tenancy_id.id])])
            rec.tenant_document_count = tenant_document_count

    def send_contract_renewal_reminder(self):
        today = fields.Date.today()
        contracts = self.search([('contract_type', 'in', ['running_contract','expiring_soon'])])

        for contract in contracts:
            days_left = (contract.end_date - today).days

            if days_left in [140, 120, 100, 90]:
                contract.update_contract_request()

                update_rec = self.env['contract.update.register'].search([
                    ('contract_id', '=', contract.id)
                ])
                contract.new_contract_sent = True

                template = self.env.ref('ribs_real_estate.contract_renewal_reminder_template', raise_if_not_found=False)
                if template:
                    email_values = {
                        'email_from': self.env.company.email,
                        'email_to': contract.tenancy_id.email,
                    }
                    template.with_context(days_left=days_left, update_rec=update_rec).send_mail(contract.id, email_values=email_values, force_send=True)
        
        
    def send_new_contract(self):
      self.ensure_one()
      return {
          'name': _('Send New Contract Details'),
          'type': 'ir.actions.act_window',
          'view_mode': 'form',
          'res_model': 'contract.update.register',
          'target': 'new',
          'context': {
            'default_contract_id': self.id,
            'default_from_date': self.end_date,
            'default_amount_or_percentage':self.property_project_id.building_contract_increment,
            'default_amount':self.property_project_id.contract_increment_amount,
            'default_percentage':self.property_project_id.contract_increment_percentage,
          }
        }


    def group_existing_contracts(self):
        if not self:
            return

        already_grouped = self.env['group.contracts'].search([
            ('contract_ids', 'in', self.ids)
        ])
        if already_grouped:
            grouped_names = ', '.join(already_grouped.mapped('name'))
            raise ValidationError(_(
                "Some of these contracts are already grouped in: %s. Please ungroup them to proceed further." % grouped_names
            ))
        if not len(self) > 1:
            raise ValidationError(_("Please select more than one contract to group."))
        
        if any(rec.contract_type != 'running_contract' for rec in self):
            raise ValidationError(_("Only running contracts can be grouped."))

        property_ids = self.mapped('property_project_id.id')
        if len(set(property_ids)) > 1:
            raise ValidationError(_("All selected contracts must belong to the same Project."))

        start_dates = self.mapped('start_date')
        if len(set(start_dates)) > 1:
            raise ValidationError(_("All selected contracts must have the same start date."))

        end_dates = self.mapped('end_date')
        if len(set(end_dates)) > 1:
            raise ValidationError(_("All selected contracts must have the same end date."))

        today = fields.Date.today()
        days_left = max((end_dates[0] - today).days, 0)

        group = self.env['group.contracts'].sudo().create({
            'name': 'Temporary Group',
            'start_date': start_dates[0],
            'end_date': end_dates[0],
            'days_left': days_left,
            'duration_type': self[0].duration_type,
        })

        contract_ids = self.ids
        unit_ids = list(set(self.mapped('property_id.id')))
        contract_names = self.mapped('tenancy_seq')

        group.contract_ids = [(6, 0, contract_ids)]
        group.unit_ids = [(6, 0, unit_ids)]
        group.name = f"Contracts of {', '.join(contract_names)}"
        
        for rec in self:
            rec.message_post(body=f"Group '{group.name}' created with {len(self)} contracts.")
        return group
    
    def renew_contract(self):
        self.ensure_one()
        contract_has_unpaid_invoices = [
        inv for inv in self.rent_invoice_ids
            if inv.payment_state != 'paid'
        ]

        if contract_has_unpaid_invoices and not self.env.context.get('confirm_renewal'):
            return {
                'type': 'ir.actions.act_window',
                'name': _('Confirm Contract Renewal'),
                'res_model': 'contract.renew.confirm.wizard',
                'view_mode': 'form',
                'view_id': self.env.ref(
                    'ribs_real_estate.view_contract_renew_confirm_wizard_form'
                ).id,
                'target': 'new',
                'context': {
                    'default_contract_id': self.id,
                },
            }

        return self.renew_contract_confirm()

    def renew_contract_confirm(self):
        """Open the renewal wizard directly - bypasses the earlier
        new_contract_sent/approved gate (that check now only affects
        whether contract.update.register data exists to prefill the
        wizard's rent/duration, not whether the wizard opens at all)."""
        self.is_renewed_contract = True

        action_context = dict(self.env.context or {})
        action_context.update({
            'active_contract_id': self.id,
        })

        if self.is_multi_contract:
            action = self.env.ref('ribs_real_estate.group_multi_contracts_action_').sudo().read()[0]
            action_context.update({
                'is_multi_contract': True,
            })
        else:
            action = self.env.ref('rental_management.contract_wizard_action').sudo().read()[0]

        action['context'] = action_context

        return action

    def update_unit_price(self,new_contract_details):
        units = self.unit_ids if self.is_multi_contract else self.property_id

        for unit in units:
            if new_contract_details.amount_or_percentage == 'percentage':
                factor = (
                    1 + new_contract_details.percentage / 100
                    if new_contract_details.increase_or_decrease == 'increase'
                    else 1 - new_contract_details.percentage / 100
                )
                unit.price_yearly *= factor
            else:
                amount = (
                    new_contract_details.amount
                    if new_contract_details.increase_or_decrease == 'increase'
                    else -new_contract_details.amount
                )
                unit.price_yearly += amount
        
    def action_contract_close(self):
        """Status : Close contract"""
        if self.contract_type == 'running_contract' and self.remain_tenancy > 0:
            message = {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'type': 'info',
                    'title': (_('Invoice Pending !')),
                    'message': (_('To close the contract, please Settle/Cancel the invoices ')),
                    'next': {'type': 'ir.actions.act_window_close'},
                    'sticky': False,
                }
            }
            return message

        # ── Block closure if any contract payment lines are not yet received ──
        pending_payments = self.contract_payment_ids.filtered(
            lambda p: p.payments_received != 'received'
        )
        # if pending_payments:
        #     pending_count = len(pending_payments)
        #     raise ValidationError(_(
        #         "Cannot close contract %s.\n\n"
        #         "%d payment record(s) have not been fully received/confirmed yet.\n\n"
        #         "Please ensure ALL payment cheques are marked as 'Received' before closing the contract."
        #     ) % (self.tenancy_seq or '', pending_count))

        termination_type = 'normal'
        closing_date = self.end_date
        if self.days_left > 0:
            termination_type = 'early'

        return {
            'name': _('Close Contract'),
            'type': 'ir.actions.act_window',
            'view_mode': 'form',
            'res_model': 'contract.closing.wizard',
            'target': 'new',
            'context': {
                'default_contract_id': self.id,
                'default_termination_type': termination_type,
                'default_closing_date': closing_date,
            }}
    
    def sent_welcome_pack(self):
        for record in self:
            contract_docs = self.env['contract.documents'].search([
                ('contract_id', '=', record.id),
                ('include_in_email', '=', True)
            ])

            if not contract_docs:
                raise UserError("No contract documents have been marked for this tenancy. Please create the necessary documents. ")

            attachments = contract_docs.mapped('attachments')
            if not attachments:
                raise UserError("No attachments found in the selected contract documents.")

            zip_buffer = io.BytesIO()
            with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zipf:
                for attachment in attachments:
                    if attachment.raw:
                        file_data = attachment.raw.content
                        zipf.writestr(attachment.name, file_data)

            zip_buffer.seek(0)
            zip_data = zip_buffer.read()

            zip_attachment = self.env['ir.attachment'].create({
                'name': f'{record.display_name or "Tenancy"}_Welcome_Pack.zip',
                'raw': zip_data,
                'res_model': self._name,
                'res_id': record.id,
                'mimetype': 'application/zip',
            })

            template = self.env.ref('ribs_real_estate.email_template_welcome_pack', raise_if_not_found=False)
            if not template:
                raise UserError("Email template not found.")

            if not record.customer_email:
                raise UserError("Customer does not have an email address.")

            template.send_mail(record.id, force_send=True, email_values={
                'email_from': self.env.company.email,
                'email_to': record.customer_email,
                'attachment_ids': [zip_attachment.id],
            })

            record.sent_welcome_pack_flag = True

        return True

    def action_clearance_certificate(self):
        self.ensure_one()
        if not self.issue_clearance_certificate:
            raise UserError("Clearance Certificate not attached")

        document_name = self.env['document.document'].search([('name', '=', 'Issue Clearance Certificate')], limit=1)
        if not document_name:
            document_name = self.env['document.document'].create({
                'name': 'Issue Clearance Certificate'
            })

        existing_document = self.env['contract.documents'].search([
            ('contract_id', '=', self.id),
            ('document_id', '=', document_name.id),
        ], limit=1)

        if existing_document:
            existing_document.unlink()

        self.env['contract.documents'].create({
            'contract_id': self.id,
            'document_id': document_name.id,
            'attachments': self.issue_clearance_certificate,  
            'expiry_date': fields.Date.today(),
            'include_in_email': False,
        })

        template = self.env.ref('ribs_real_estate.send_issue_clearance_template', raise_if_not_found=False)

        company_secretary_email = self.env.company.company_secretary.work_email

        property_id = self._get_property_queryset()

        manager_email = property_id.property_manager.work_email
        tenant_email = self.tenancy_id.email

        email_list = [email for email in [tenant_email, company_secretary_email] if email]
        email_to = ','.join(email_list)
        if email_to:

            email_values_others = {
                'email_from': self.env.company.email,
                'email_to': email_to,
                'attachment_ids': [(6, 0, self.issue_clearance_certificate.ids)],
            }
            ctx_others = dict(self.env.context, custom_regards=property_id.property_manager.name)
            template.with_context(ctx_others).send_mail(
                self.id,
                email_values=email_values_others,
                force_send=True
            )
        if manager_email:
            email_values_manager = {
                'email_from': self.env.company.email,
                'email_to': manager_email,
                'attachment_ids': [(6, 0, self.issue_clearance_certificate.ids)],
            }
            ctx_manager = dict(self.env.context, custom_regards=self.env.company.name)
            template.with_context(ctx_manager).send_mail(
                self.id,
                email_values=email_values_manager,
                force_send=True
            )
        self.issue_clearance_sent = True

        return True

    def request_documents(self):
        if not self.customer_email:
            raise UserError("The tenant does not have an email address. Please update the tenant's email address before sending the document request.")
        return {
            'name': _('Document Request'),
            'type': 'ir.actions.act_window',
            'view_mode': 'form',
            'res_model': 'document.request',
            'target': 'new',
            'context': {
                'default_contract_id': self.id,
            }}

    def bulk_pdc_upload(self):
        self.ensure_one()
        BulkPDC = self.env['bulk.pdc.upload']

        wizard = BulkPDC.create({
            'tenancy_id': self.id,
        })

        line_vals = []
        for invoice in self.rent_invoice_ids:
            line_vals.append((0, 0, {
                'inv_id': invoice.rent_invoice_id.id,
                'due_date': invoice.invoice_date,
                'amount': invoice.amount,
            }))
        wizard.write({'pdc_lines': line_vals})

        return {
            'name': _('Bulk PDC Upload'),
            'type': 'ir.actions.act_window',
            'res_model': 'bulk.pdc.upload',
            'view_mode': 'form',
            'target': 'new',
            'res_id': wizard.id, 
            'view_id': self.env.ref('ribs_real_estate.view_bulk_pdc_wizard_form').id,
        }

    @api.depends('start_date', 'grace_period_value', 'grace_period_unit')
    def _compute_grace_period_dates(self):
        """Grace End Date is always the day before Start Date; Grace Start Date
        is that point minus the Grace Period value/unit - both always derived
        backward from Start Date rather than entered by hand."""
        for record in self:
            if record.start_date and record.grace_period_value:
                if record.grace_period_unit == 'month':
                    delta = relativedelta(months=record.grace_period_value)
                elif record.grace_period_unit == 'year':
                    delta = relativedelta(years=record.grace_period_value)
                else:
                    delta = relativedelta(days=record.grace_period_value)
                record.grace_period_end_date = record.start_date - timedelta(days=1)
                record.grace_period_start_date = record.start_date - delta
            else:
                record.grace_period_end_date = False
                record.grace_period_start_date = False

    @api.depends('total_rent_year', 'duration_id.month', 'rent_unit', 'start_date', 'end_date')
    def _compute_contract_value(self):
        for record in self:
            total_rent_year = record.total_rent_year or 0
            months = record.duration_id.month or 0

            if (not months and not record.is_by_date and record.start_date
                    and record.end_date and record.end_date >= record.start_date):
                # duration_id wasn't set (e.g. bulk-imported contracts) - derive the
                # period length from the actual dates instead of defaulting to 0.
                days = (record.end_date - record.start_date).days + 1
                months = days / 30.0

            if record.payment_term == 'daily':
                current_year = fields.Date.today().year
                days = 365
                if calendar.isleap(current_year):
                    days = 366
                record.contract_value = (total_rent_year / days) * months

            elif record.is_by_date:
                start_date = record.start_date
                end_date = record.end_date

                if not start_date or not end_date:
                    record.contract_value = 0
                    continue

                days = (end_date - start_date).days + 1

                days_in_year = 366 if calendar.isleap(start_date.year) else 365

                record.contract_value = (total_rent_year / days_in_year) * days

            elif record.rent_unit != 'Day':
                record.contract_value = total_rent_year * (months / 12)

            else:
                if record.start_date and record.duration_end_date:
                    total_days = (record.duration_end_date - record.start_date).days or 0
                else:
                    total_days =0
                    total_days = months * 30

                current_year = date.today().year
                days_in_year = 366 if calendar.isleap(current_year) else 365

                daily_rent = total_rent_year / days_in_year if days_in_year else 0
                record.contract_value = daily_rent * total_days

    @api.onchange('total_rent_year')
    def _onchange_total_rent_year(self):
        self.total_rent = self.total_rent_year / 12

    def updated_contract_details(self):
        self.ensure_one()

        record = self.env['contract.update.register'].search(
            [('contract_id', '=', self.id)],
            order='id desc', 
            limit=1
        )

        return {
            'type': 'ir.actions.act_window',
            'name': 'Updated Contract Details',
            'res_model': 'contract.update.register',
            'view_mode': 'form',
            'res_id': record.id,
            'target': 'current',
            'context': {'create': False, 'delete': False, 'readonly': True},
        }


    def check_expiring_documents(self):
        contracts = self.env['tenancy.details'].search([
            ('contract_type', '=', 'running_contract')
        ])
        
        template = self.env.ref(
            'ribs_real_estate.send_expired_document_reminder', 
            raise_if_not_found=False
        )

        leasing_group = self.env.ref('rental_management.property_rental_manager')
        leasing_team_emails = leasing_group.all_user_ids.mapped('email')

        for contract in contracts:
            tenant_email = contract.tenancy_id.email or ""
            landlord_email = contract.property_landlord_id.email or ""
            email_to = ", ".join(filter(None, [
                tenant_email,
                landlord_email,
                *leasing_team_emails
            ]))
            email_values = {
                'email_from': self.env.company.email,
                'email_to': email_to,
            }
            partner_documents = self.env['partner.documents'].search([
                ('partner_id', '=', contract.tenancy_id.id)
            ])

            expired_docs = partner_documents.filtered(
                lambda d: d.expiry_date and d.expiry_date < date.today()
            )
            if expired_docs:
                expired_docs.write({'verified_status': 'expired'})
            if expired_docs and contract:
                ctx = {
                    'expired_documents': expired_docs,
                    'contract': contract,
                }
                template.with_context(ctx).send_mail(
                    contract.id,
                    force_send=True,
                    email_values=email_values
                )

    def get_payment_term_qty(self):
        """Get qty bases on payment term"""
        if self.payment_term == 'full_payment':
            # Full Payment is a single lump-sum payment covering the
            # WHOLE contract duration, not a fixed recurring interval
            # like the other terms - its "months per payment" must be
            # the contract's own full duration, not 1. contract_payment_pdc
            # divides duration by this value to get payments_per_year;
            # returning 1 here made it create one PDC per month instead
            # of a single payment for the whole contract.
            return self.duration_id.month or 1
        payment_term_qty = {
            'half_year': 6,
            'quarterly': 3,
            'every_two_months':2,
            'every_four_months':4,
            'monthly': 1,
            'year': 1,
            'daily': 1,
        }
        return payment_term_qty.get(self.payment_term)
    
    def _get_invoice_qty_price(self):
        duration_months = self.duration_id.month
        total_amount = self.total_rent_year
        term = self.payment_term
    
        if not duration_months:
            raise ValidationError("Contract duration is missing.")
    
        # Payment term month unit mapping 
        term_month_map = {
            'monthly': 1,
            'every_two_months': 2,
            'every_four_months': 4,
            'quarterly': 3,
            'half_year': 6,
            'year': 12,
        }
            
        # Full Payment
        if term == 'full_payment':
            return 1, round(total_amount, 2)
    
        # Daily
        if term == 'daily':
            if self.is_by_date:
                if not self.start_date or not self.end_date:
                    raise ValidationError("Please set the contract start and end dates.")

                duration_days = (self.end_date - self.start_date).days + 1
            else:
                # If duration_id.month stores days for daily contracts
                duration_days = self.duration_id.month

            if not duration_days:
                raise ValidationError("Contract duration is missing.")

            return duration_days, round(total_amount / duration_days, 2)
    
        term_months = term_month_map[term]
        qty = duration_months // term_months
        price = round(total_amount / qty, 2)
        return qty, price

    def action_active_contract(self):
        """Process auto Installment for Rent Unit : Month and Year """
        invoice_post_type = self.env['ir.config_parameter'].sudo().get_str(
            'rental_management.invoice_post_type', False)
        payment_term = {'daily':'Daily', 'monthly': 'Month', 'half_year': 'Half Year',
                        'quarterly': 'Quarter', 'year': 'Year',
                        'every_two_months': 'Every Two Months',
                        'every_four_months': 'Every Four Months',}
        invoice_lines = []
        # Broker Invoice
        if self.is_any_broker:
            self.action_broker_invoice()
        # Add Installment Line
        payment_term_val = self.get_payment_term_qty()
        months = self.duration_id.month or 0
        if self.payment_term == 'daily':
            current_year = fields.Date.today().year
            days = 365
            if calendar.isleap(current_year):
                days = 366
            daily_rent = self.total_rent_year / days
            rent_amount = round(daily_rent * months, 2)

        elif self.payment_term == 'year':
            rent_amount = round(self.total_rent_year, 2)

        else:
            monthly_rent = self.total_rent_year / 12
            rent_amount = round(monthly_rent * payment_term_val, 2)

        if self.unit_ids:
            print('yesss')
            invoice_lines += self._prepare_unit_invoice_lines(
                self,
                period=self.payment_term,
                months=self.duration_id.month,
                full_term=True,
            )
        else:
            print('elseee')
            qty, unit_price = self._get_invoice_qty_price()
            
            invoice_lines.append((0, 0, {
                'product_id': self.installment_item_id.id,
                'quantity': qty,
                'name': f"Invoice Amount for {qty} Installment(s)",
                'tax_ids': self.tax_ids.ids if self.instalment_tax else False,
                'price_unit': unit_price,
            }))
        
        #set quantity as 4 and change the description when the payment term is quarterly
        # invoice_lines.append((0, 0, {
        #     'product_id': self.installment_item_id.id,
        #     'quantity': 4 if self.payment_term == 'quarterly' else 1,
        #     'name': f"Invoice Amount for 4 {payment_term.get(self.payment_term)} " if self.payment_term == 'quarterly' else f"Invoice Amount for {payment_term.get(self.payment_term)}",
        #     'tax_ids': self.tax_ids.ids if self.instalment_tax else False,
        #     'price_unit': rent_amount,
        # }))

        # invoice_lines.append((0, 0, {
        #     'product_id': self.installment_item_id.id,
        #     'quantity': 1,
        #     'name': f"First {payment_term.get(self.payment_term)} "
        #             f"Invoice of {self.property_id.name}",
        #     'tax_ids': self.tax_ids.ids if self.instalment_tax else False,
        #     'price_unit': rent_amount,
        # }))
        # Add Deposit Line

        property_name = self._get_property_name()

        if self.is_any_deposit:
            invoice_lines.append((0, 0, {
                'product_id': self.deposit_item_id.id,
                'name': 'Deposit of ' + property_name,
                'quantity': 1,
                'price_unit': self.deposit_amount,
                'tax_ids': self.tax_ids.ids if self.deposit_tax else False
            }))
        # Add Maintenance Line
        if self.is_maintenance_service and self.maintenance_service_invoice == 'merge':
            invoice_lines.append((0, 0, {
                'product_id': self.maintenance_item_id.id,
                'name': 'Maintenance of ' + property_name,
                'quantity': 3 if self.payment_term == 'quarterly' else 1,
                'price_unit': self.total_maintenance,
            }))
        # Add Extra Service
        if (self.is_added_services
                and self.added_service_ids
                and self.added_service_invoice == 'merge'):
            for line in self.added_service_ids:
                invoice_lines.append((0, 0, {
                    "product_id": line.service_id.id,
                    "name": line.service_id.name,
                    "quantity": 1,
                    "price_unit": line.price,
                }))
        if (
            self.is_added_services
            and self.added_service_ids
            and self.added_service_invoice == "separate"):
            for line in self.added_service_ids:
                invoice_lines.append((0, 0, {
                    "product_id": line.service_id.id,
                    "name": line.service_id.name,
                    "quantity": 1,
                    "price_unit": line.price,
                    # Comment out the account_id field so that the base account field works
                    # "account_id": self.property_project_id.invoice_creation_id.id,
                }))
        # Add Utility Services
        if self.is_extra_service and self.extra_service_invoice == 'merge':
            for service in self.extra_services_ids:
                service_type = 'Once' if service.service_type == 'once' else "Recurring"
                invoice_lines.append((0, 0, {
                    'product_id': service.service_id.id,
                    'name': f"Service Type : {service_type} - {service.service_id.name}",
                    'quantity': 3 if self.payment_term == 'quarterly' else 1,
                    'price_unit': service.price,
                    'tax_ids': self.tax_ids.ids if self.service_tax else False
                }))

        # Create First Installment Invoice
        invoice_id = self.env['account.move'].sudo().create({
            'partner_id': self.tenancy_id.id,
            'move_type': 'out_invoice',
            'invoice_date': self.invoice_start_date,
            'invoice_line_ids': invoice_lines,
            'tenancy_id': self.id
        })
        if invoice_post_type == 'automatically':
            invoice_id.action_post()
        self.action_create_rent_invoice_entry(
            amount=invoice_id.amount_total, invoice_id=invoice_id)
        self.action_send_active_contract()
        # Process Separate Installment: Maintenance and Services
        if self.is_maintenance_service and self.maintenance_service_invoice == 'separate':
            self._process_separate_invoices(maintenance=True)
        if self.is_extra_service and self.extra_service_invoice == 'separate':
            self._process_separate_invoices(utility=True)
        # Post Processing
        self.write({
            'contract_type': 'running_contract',
            'active_contract_state': True,
            'last_invoice_payment_date': invoice_id.invoice_date,
            "type": "automatic",
        })

    def _prepare_unit_invoice_lines(self, tenancy, period="monthly", months=0, full_term=False):
        invoice_lines = []

        for unit in tenancy.unit_ids:
            multi_line = self.env["group.multi.contract.line"].search(
                [("property_id", "=", unit.id)],
                order="id desc",
                limit=1,
            )

            if not multi_line:
                continue

            # Use the precomputed duration amount directly
            price = multi_line.amount_based_on_duration

            invoice_lines.append((0, 0, {
                "product_id": unit.default_product_id.id,
                "name": f"{unit.name}",
                "quantity": 1,
                "price_unit": price,
                "tax_ids": [(6, 0, [unit.tax_id.id])]
                    if unit.tax_id and tenancy.instalment_tax
                    else False,
                "invoice_date": tenancy.start_date,
            }))

        return invoice_lines

    def action_create_rent_invoice_entry(self, amount, invoice_id):
        """Create rent invoice entry"""
        rent_invoice = {
            'tenancy_id': self.id,
            'type': 'rent',
            'invoice_date': self.invoice_start_date,
            'rent_invoice_id': invoice_id.id,
            'amount': amount,
        }
        if self.payment_term == 'monthly':
            rent_invoice[
                'description'] = 'First Rent + Deposit' if self.is_any_deposit else "First Rent"

        if self.payment_term == 'every_two_months':
            rent_invoice[
                'description'] = ('First Two Months Rent +Deposit'
                                  if self.is_any_deposit
                                  else "First Two Months Rent")

        if self.payment_term == 'every_four_months':
            rent_invoice[
                'description'] = ('First Four Months Rent +Deposit'
                                  if self.is_any_deposit
                                  else "First Four Months Rent")

        if self.payment_term == 'quarterly':
            rent_invoice[
                'description'] = ('Invoice Amount for 4 Quarter + Deposit'
                                  if self.is_any_deposit
                                  else 'Invoice Amount for 4 Quarter')
        if self.payment_term == 'half_year':
            rent_invoice[
                'description'] = ('First Half Year Rent + Deposit'
                                  if self.is_any_deposit
                                  else 'First Half Year Rent')
        if self.payment_term == 'year':
            rent_invoice['description'] = 'First Year Rent'
        self.env['rent.invoice'].create(rent_invoice)

    @api.model
    def tenancy_recurring_every_two_months_invoice(self):
        property_name = self._get_property_name()

        """
        Scheduler : Tenancy recurring invoice for quarterly payment term & automatic installments
        """
        today_date = fields.Date.today()
        reminder_days = self.env['ir.config_parameter'].sudo().get_str(
            'rental_management.reminder_days', False)
        invoice_post_type = self.env['ir.config_parameter'].sudo().get_str(
            'rental_management.invoice_post_type', False)
        tenancy_contracts = self.env['tenancy.details'].sudo().search(
            [('contract_type', '=', 'running_contract'),
             ('payment_term', '=', 'every_two_months'),
             ('type', '=', 'automatic'),
             ('final_rent_unit', '=', 'Month')])
        for rec in tenancy_contracts:
            if rec.contract_type == 'running_contract' and rec.payment_term == 'every_two_months':
                if today_date < rec.end_date:
                    invoice_date = rec.last_invoice_payment_date + relativedelta(months=2)
                    next_next_invoice_date = invoice_date + relativedelta(months=2)
                    next_invoice_date = rec.last_invoice_payment_date + relativedelta(
                        months=2) - relativedelta(
                        days=int(reminder_days))
                    if rec.end_date < next_next_invoice_date:
                        delta = relativedelta(
                            next_next_invoice_date, rec.end_date)
                        diff = delta.months
                    else:
                        diff = 0
                    if today_date == next_invoice_date:
                        record = {
                            'product_id': rec.installment_item_id.id,
                            'name': 'Two Months Installment of ' + property_name,
                            'quantity': 1,
                            'price_unit': rec.total_rent * (2 - diff),
                            'tax_ids': rec.tax_ids.ids if rec.instalment_tax else False
                        }
                        invoice_lines = [(0, 0, record)]
                        if rec.is_extra_service and rec.extra_service_invoice == 'merge':
                            for line in rec.extra_services_ids.filtered(
                                    lambda line: line.service_type == 'monthly'):
                                invoice_lines.append((0, 0, {
                                    'product_id': line.service_id.id,
                                    'name': "Service Type : Two Months" + "\n"
                                            + f"Service : {line.service_id.name}",
                                    'quantity': (2 - diff),
                                    'price_unit': line.price * (2 - diff),
                                    'tax_ids': rec.tax_ids.ids if rec.service_tax else False
                                }))
                        if (rec.is_maintenance_service
                                and rec.maintenance_rent_type == 'recurring'
                                and rec.maintenance_service_invoice == 'merge'):
                            invoice_lines.append((0, 0, {
                                'product_id': rec.maintenance_item_id.id,
                                'name': 'Recurring Two Months Maintenance of '
                                        + property_name,
                                'quantity': (2 - diff),
                                'price_unit': rec.total_maintenance * (2 - diff),
                            }))
                        invoice_id = self.env['account.move'].sudo().create({
                            'partner_id': rec.tenancy_id.id,
                            'move_type': 'out_invoice',
                            'invoice_date': invoice_date,
                            'invoice_line_ids': invoice_lines
                        })
                        invoice_id.tenancy_id = rec.id
                        if invoice_post_type == 'automatically':
                            invoice_id.action_post()
                        rec.last_invoice_payment_date = invoice_id.invoice_date
                        rent_invoice = {
                            'tenancy_id': rec.id,
                            'type': 'rent',
                            'invoice_date': invoice_date,
                            'description': 'Two Months Installment of ' + property_name,
                            'rent_invoice_id': invoice_id.id,
                            'amount': invoice_id.amount_total,
                            'rent_amount': self.total_rent * (2 - diff)
                        }
                        self.env['rent.invoice'].create(rent_invoice)
                        # Process Separate Invoice
                        if (rec.is_maintenance_service
                                and rec.maintenance_service_invoice == 'separate'):
                            rec._process_separate_invoices(
                                maintenance=True, quarter_qty=(2 - diff))
                        if rec.is_extra_service and rec.extra_service_invoice == 'separate':
                            rec._process_separate_invoices(
                                utility=True, quarter_qty=(2 - diff))
                        # Send Reminder
                        rec.action_send_tenancy_reminder()

    @api.model
    def tenancy_recurring_every_four_months_invoice(self):
        property_name = self._get_property_name()

        """
        Scheduler : Tenancy recurring invoice for quarterly payment term & automatic installments
        """
        today_date = fields.Date.today()
        reminder_days = self.env['ir.config_parameter'].sudo().get_str(
            'rental_management.reminder_days', False)
        invoice_post_type = self.env['ir.config_parameter'].sudo().get_str(
            'rental_management.invoice_post_type', False)
        tenancy_contracts = self.env['tenancy.details'].sudo().search(
            [('contract_type', '=', 'running_contract'),
             ('payment_term', '=', 'every_four_months'),
             ('type', '=', 'automatic'),
             ('final_rent_unit', '=', 'Month')])
        for rec in tenancy_contracts:
            if rec.contract_type == 'running_contract' and rec.payment_term == 'every_four_months':
                if today_date < rec.end_date:
                    invoice_date = rec.last_invoice_payment_date + relativedelta(months=4)
                    next_next_invoice_date = invoice_date + relativedelta(months=4)
                    next_invoice_date = rec.last_invoice_payment_date + relativedelta(
                        months=4) - relativedelta(
                        days=int(reminder_days))
                    if rec.end_date < next_next_invoice_date:
                        delta = relativedelta(
                            next_next_invoice_date, rec.end_date)
                        diff = delta.months
                    else:
                        diff = 0
                    if today_date == next_invoice_date:
                        record = {
                            'product_id': rec.installment_item_id.id,
                            'name': 'Two Months Installment of ' + property_name,
                            'quantity': 1,
                            'price_unit': rec.total_rent * (4 - diff),
                            'tax_ids': rec.tax_ids.ids if rec.instalment_tax else False
                        }
                        invoice_lines = [(0, 0, record)]
                        if rec.is_extra_service and rec.extra_service_invoice == 'merge':
                            for line in rec.extra_services_ids.filtered(
                                    lambda line: line.service_type == 'monthly'):
                                invoice_lines.append((0, 0, {
                                    'product_id': line.service_id.id,
                                    'name': "Service Type : Four Months" + "\n"
                                            + f"Service : {line.service_id.name}",
                                    'quantity': (4 - diff),
                                    'price_unit': line.price * (4 - diff),
                                    'tax_ids': rec.tax_ids.ids if rec.service_tax else False
                                }))
                        if (rec.is_maintenance_service
                                and rec.maintenance_rent_type == 'recurring'
                                and rec.maintenance_service_invoice == 'merge'):
                            invoice_lines.append((0, 0, {
                                'product_id': rec.maintenance_item_id.id,
                                'name': 'Recurring Four Months Maintenance of '
                                        + property_name,
                                'quantity': (4 - diff),
                                'price_unit': rec.total_maintenance * (4 - diff),
                            }))
                        invoice_id = self.env['account.move'].sudo().create({
                            'partner_id': rec.tenancy_id.id,
                            'move_type': 'out_invoice',
                            'invoice_date': invoice_date,
                            'invoice_line_ids': invoice_lines
                        })
                        invoice_id.tenancy_id = rec.id
                        if invoice_post_type == 'automatically':
                            invoice_id.action_post()
                        rec.last_invoice_payment_date = invoice_id.invoice_date
                        rent_invoice = {
                            'tenancy_id': rec.id,
                            'type': 'rent',
                            'invoice_date': invoice_date,
                            'description': 'Four Months Installment of ' + property_name,
                            'rent_invoice_id': invoice_id.id,
                            'amount': invoice_id.amount_total,
                            'rent_amount': self.total_rent * (4 - diff)
                        }
                        self.env['rent.invoice'].create(rent_invoice)
                        # Process Separate Invoice
                        if (rec.is_maintenance_service
                                and rec.maintenance_service_invoice == 'separate'):
                            rec._process_separate_invoices(
                                maintenance=True, quarter_qty=(4 - diff))
                        if rec.is_extra_service and rec.extra_service_invoice == 'separate':
                            rec._process_separate_invoices(
                                utility=True, quarter_qty=(4 - diff))
                        # Send Reminder
                        rec.action_send_tenancy_reminder()

    @api.model
    def tenancy_yearly_invoice(self):
        property_name = self._get_property_name()
        """
        Scheduler : Tenancy recurring invoice for yearly payment term & automatic installments
        """
        today_date = fields.Date.today()
        # today_date = datetime.date(2024, 7, 1)
        reminder_days = self.env['ir.config_parameter'].sudo().get_str('rental_management.reminder_days', False)
        invoice_post_type = self.env['ir.config_parameter'].sudo().get_str('rental_management.invoice_post_type', False)
        tenancy_contracts = self.env['tenancy.details'].sudo().search(
            [('contract_type', '=', 'running_contract'), ('type', '=', 'automatic'),
             ('payment_term', '=', 'year'),
             ('final_rent_unit', '=', 'Month')])
        for rec in tenancy_contracts:
            if rec.contract_type == 'running_contract' and rec.payment_term == 'year':
                if today_date < rec.end_date:
                    invoice_date = rec.last_invoice_payment_date + relativedelta(months=12)
                    next_invoice_date = rec.last_invoice_payment_date + relativedelta(
                        months=12) - relativedelta(
                        days=int(reminder_days))
                    if rec.end_date < next_invoice_date:
                        delta = relativedelta(
                            next_invoice_date, rec.end_date)
                        diff = delta.months
                    else:
                        diff = 0
                    if today_date == next_invoice_date:
                        record = {
                            'product_id': rec.installment_item_id.id,
                            'name': "Yearly installment of " + property_name,
                            'quantity': 1,
                            'price_unit': rec.total_rent * (12 - diff),
                            'tax_ids': rec.tax_ids.ids if rec.instalment_tax else False
                        }
                        invoice_lines = [(0, 0, record)]
                        if rec.is_extra_service and rec.extra_service_invoice == 'merge':
                            for line in rec.extra_services_ids.filtered(
                                    lambda line: line.service_type == 'monthly'):
                                invoice_lines.append((0, 0, {
                                    'product_id': line.service_id.id,
                                    'name': "Service Type : Recurring" + "\n"
                                            + f"Service : {line.service_id.name}",
                                    'quantity': (12 - diff),
                                    'price_unit': line.price * (12 - diff),
                                    'tax_ids': rec.tax_ids.ids if rec.service_tax else False
                                }))

                        if (rec.is_maintenance_service
                                and rec.maintenance_rent_type == 'recurring'
                                and rec.maintenance_service_invoice == 'merge'):
                            invoice_lines.append((0, 0, {
                                'product_id': rec.maintenance_item_id.id,
                                'name': 'Recurring Monthly Maintenance of ' + property_name,
                                'quantity': (12 - diff),
                                'price_unit': rec.total_maintenance * (12 - diff),
                            }))
                        invoice_id = self.env['account.move'].sudo().create({
                            'partner_id': rec.tenancy_id.id,
                            'move_type': 'out_invoice',
                            'invoice_date': invoice_date,
                            'invoice_line_ids': invoice_lines,
                            'tenancy_id': rec.id
                        })
                        if invoice_post_type == 'automatically':
                            invoice_id.action_post()
                        rec.last_invoice_payment_date = invoice_id.invoice_date
                        rent_invoice = {
                            'tenancy_id': rec.id,
                            'type': 'rent',
                            'invoice_date': invoice_date,
                            'description': 'Installment of ' + property_name,
                            'rent_invoice_id': invoice_id.id,
                            'amount': invoice_id.amount_total,
                            'rent_amount': self.total_rent
                        }
                        self.env['rent.invoice'].create(rent_invoice)
                        # Process Separate Invoice
                        if rec.is_maintenance_service and rec.maintenance_service_invoice == 'separate':
                            rec._process_separate_invoices(maintenance=True, quarter_qty=(12 - diff))
                        if rec.is_extra_service and rec.extra_service_invoice == 'separate':
                            rec._process_separate_invoices(utility=True, quarter_qty=(12 - diff))
                    # Send Reminder
        rec.action_send_tenancy_reminder()

    @api.depends('start_date', 'month', 'rent_unit', 'payment_term', 'duration_type',
                 'duration_end_date')
    def _compute_end_date(self):
        for rec in self:
            end_date = None
            if rec.duration_type == 'by_duration' and rec.start_date:
                if rec.rent_unit == "Day":
                    delta = relativedelta(days=rec.month)
                elif rec.rent_unit == "Year" or rec.payment_term == "year":
                    delta = relativedelta(months=rec.month)
                elif rec.payment_term == "daily":
                    delta =relativedelta(days=rec.month)
                else:
                    delta = relativedelta(months=rec.month)
                end_date = rec.start_date + delta - relativedelta(days=1)

            if rec.duration_type == 'by_date' and rec.duration_end_date:
                end_date = rec.duration_end_date
            rec.end_date = end_date

    @api.onchange('chq_due_date')
    def _onchange_chq_due_date(self):
        if self.chq_due_date and self.chq_due_date < fields.Date.today():
            raise ValidationError("Due date cannot be in the past.")

    def _copy_attachments_to_record(self, source_attachments, target_model):
        if not source_attachments:
            return False

        Attachment = self.env['ir.attachment'].sudo()
        # PERF: one multi-record create() for all copied attachments
        # instead of one INSERT per attachment.
        new_attachments = Attachment.create([{
            'name': att.name,
            'raw': att.raw,
            'res_model': target_model,
            'res_id': 0,
            'mimetype': att.mimetype,
            'public': att.public,
        } for att in source_attachments])

        return [(4, new_att.id) for new_att in new_attachments]

    def action_send_active_contract(self):
        self.ensure_one()

        if self.contract_payment_ids:
            Payment = self.env['account.payment'].sudo()
            PdcWizard = self.env['pdc.wizard'].sudo()

            for line in self.contract_payment_ids:
                if line.payment_ref:
                    continue

                if line.amount <= 0:
                    raise UserError(f"Amount must be positive on payment line: {line.ref or ''}")

                payment_type = 'inbound'   
                partner_type = 'customer'

                if getattr(line.journal_id, 'is_pdc_journal', False):
                    if not line.chq_due_date:
                        raise UserError(
                            f"Cheque Due Date is required for PDC journal: {line.journal_id.name}"
                        )
                    attachment_commands = self._copy_attachments_to_record(line.attachment_ids, 'pdc.wizard')

                    pdc_vals = {
                        'name': self.env['ir.sequence'].next_by_code('pdc.payment.customer') or 'New',
                        'partner_id': self.tenancy_id.id,
                        'payment_amount': line.amount,
                        'currency_id': line.currency_id.id,
                        'journal_id': line.journal_id.id,
                        'reference': line.ref,
                        'cheque_number': line.cheque_num,
                        'remitter_bank': line.remitter_bank_id.name or line.remitter_bank,
                        'payment_date': line.chq_due_date,
                        'due_date': line.chq_due_date,
                        'payment_type': 'receive_money',
                        'attachment_ids': attachment_commands if attachment_commands else False,
                        # 'company_id': line.company_id.id,
                        # 'state': 'draft',
                        }

                    
                    pdc = PdcWizard.create(pdc_vals)

                    if attachment_commands:
                        # PERF: the attachment ids are already known from
                        # _copy_attachments_to_record - browse() + write()
                        # updates them directly without the redundant
                        # search() lookup first.
                        self.env['ir.attachment'].sudo().browse(
                            [cmd[1] for cmd in attachment_commands]
                        ).write({'res_id': pdc.id})

                    line.sudo().write({
                        'payment_ref': f'pdc.wizard,{pdc.id}',
                        'payment_pdc_id': pdc.id,
                        'payment_account_id': False,
                    })


                else:
                    attachment_commands = self._copy_attachments_to_record(line.attachment_ids, 'account.payment')
                    payment_vals = {
                        'payment_type': payment_type,
                        'partner_type': partner_type,
                        'partner_id': self.tenancy_id.id,
                        'amount': line.amount,
                        'currency_id': line.currency_id.id,
                        'journal_id': line.journal_id.id,
                        'cheque_ref': line.ref,
                        'date': fields.Date.today(),
                        'attachment_ids': attachment_commands,
                        # 'company_id': line.company_id.id,
                        # 'state': 'draft', 
                        # 'payment_method_id': self.env.ref('account.account_payment_method_manual_in').id
                        # if payment_type == 'inbound' else self.env.ref('account.account_payment_method_manual_out').id,
                    }
                    payment = Payment.create(payment_vals)

                    if attachment_commands:
                        # PERF: same as above - browse() the already-known
                        # ids instead of searching for them again.
                        self.env['ir.attachment'].sudo().browse(
                            [cmd[1] for cmd in attachment_commands]
                        ).write({'res_id': payment.id})


                    line.sudo().write({
                        'payment_ref': f'account.payment,{payment.id}',
                        'payment_account_id': payment.id,
                        'payment_pdc_id': False,
                    })
    
        # mail_template = self.env.ref(
        #     'rental_management.active_contract_mail_template', raise_if_not_found=False)
        # if mail_template:
        #     mail_template.send_mail(self.id, force_send=True)

        return True

    def write(self, vals):
        old_value = self.total_rent_year
        res = super().write(vals)

        if vals.get('contract_type') == 'running_contract':
            self.tenancy_expire()
        for rec in self:
            
            if rec.contract_type == 'new_contract' and 'total_rent_year' in vals:
                new_value = vals['total_rent_year']
                user_id = self.env.user.id
                param = self.env['ir.config_parameter'].sudo().get_str(
                    'ribs_real_estate.authorized_users_ids', ''
                )
                authorized_ids = [int(x) for x in param.split(',') if x]
                if user_id not in authorized_ids:
                    if new_value < old_value:
                        rec.contract_type = 'waiting'

                        base_url = self.env['ir.config_parameter'].sudo().get_str('web.base.url', False)
                        action = self.env.ref("ribs_real_estate.tenancy_action_id", raise_if_not_found=False)
                        action_id = action.id if action else False

                        if action_id:
                            record_url = f"{base_url}/odoo/action-{action_id}/6/{rec._name}/{rec.id}"
                        else:
                            record_url = f"{base_url}/odoo/6/{rec._name}/{rec.id}"

                        template = self.env.ref('ribs_real_estate.mail_template_rent_approval')
                        emails = self.env['res.users'].browse(authorized_ids).mapped('email')
                        emails = [e for e in emails if e]
                        if emails:
                            template.with_context(old_value=old_value,record_url=record_url).sudo().send_mail(
                                rec.id,
                                email_values={
                                    'email_to': ','.join(emails),
                                },
                                force_send=True,
                            )
        return res

    def action_approve_contract(self):
        user_id = self.env.user.id
        for rec in self:
            param = self.env['ir.config_parameter'].sudo().get_str(
                'ribs_real_estate.authorized_users_ids', ''
            )
            authorized_ids = [int(x) for x in param.split(',') if x]
            if user_id in authorized_ids:
                rec.contract_type = 'new_contract'
            else:
                raise UserError("Only Admin can perform this action.")
        return True

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if "total_rent_year" in vals:
                vals["total_rent"] = vals["total_rent_year"] / 12

        return super().create(vals_list)

    def action_active_rent_contract(self):
        """Activate contract & open wizard based on rent unit"""
        self.ensure_one()

        # Payment validations
        if (
            self.env['ir.config_parameter'].sudo().get_str(
                'ribs_real_estate.force_collect_payments', False
            ) == 'True'
            and not self.contract_payment_ids
        ):
            raise ValidationError(
                'Please add Payment Details in order to proceed'
            )

        elif self.contract_payment_ids:
            total_amount = "{:.1f}".format(
                sum(self.contract_payment_ids.mapped("amount"))
            )
            if total_amount != "{:.1f}".format(self.total_contract_value):
                raise ValidationError(
                    'The amount in the payment details does not match with the contract value'
                )

        for payment in self.contract_payment_ids:
            if not payment.journal_id:
                raise UserError(
                    'Please Add Bank List for all the payments'
                )
            if not payment.payment_type:
                raise UserError(
                    'Please Add Payment Type for all the payments'
                )

        # ---------------------------------------------------------
        # Check for unverified tenant documents
        # ---------------------------------------------------------
        unverified_docs = self.env['partner.documents'].search([
            ('partner_id', '=', self.tenancy_id.id),
            ('verified_status', '!=', 'accepted'),
        ])

        if unverified_docs and not self.env.context.get('skip_document_confirmation'):
            message = (
                "The following documents are not verified yet:\n\n"
                + "\n".join(
                    "• %s" % doc.document_id.name
                    for doc in unverified_docs
                )
                + "\n\nDo you still want to proceed?"
            )

            wizard = self.env['contract.activation.confirm'].create({
                'contract_id': self.id,
                'message': message,
            })

            return {
                'type': 'ir.actions.act_window',
                'name': 'Confirmation',
                'res_model': 'contract.activation.confirm',
                'view_mode': 'form',
                'res_id': wizard.id,
                'target': 'new',
            }

        # ---------------------------------------------------------
        # Existing activation logic
        # ---------------------------------------------------------
        if self.rent_unit == 'Day':
            wizard_id = self.env['active.contract'].with_context(
                active_id=self.id,
                skip_document_confirmation=True
            ).sudo().create({
                'contract_id': self.id,
                'type': 'manual'
            })

            if wizard_id:
                return wizard_id.action_create_contract()

        else:
            wizard_id = self.env['active.contract'].with_context(
                active_id=self.id,
                skip_document_confirmation=True
            ).sudo().create({
                'contract_id': self.id,
                'type': 'automatic'
            })

            if wizard_id:
                return wizard_id.action_create_contract()
            # action = self.env["ir.actions.act_window"]._for_xml_id(
            #     "rental_management.active_contract_action"
            # )
            # action['context'] = {
            #     'active_id': self.id,
            #     'skip_document_confirmation': True,
            # }
            # return action

    def update_contract_request(self):
        if not self.ids:  
            return

        contracts = self.env['tenancy.details'].browse(self.ids)

        for contract in contracts:
            project = contract.property_project_id
            if not project:
                continue 
            if not project.contract_increment_amount and not project.contract_increment_percentage:
                raise UserError("Please set Contract Increment Amount or Percentage in the Biilding to proceed.")

            # Check existing request
            existing_request = self.env['contract.update.register'].search(
                [('contract_id', '=', contract.id)],
                order='id desc',
                limit=1
            )

            if existing_request:
                contract.new_contract_sent = True
                continue
            
            current_rent_yearly = contract.total_rent_year or 0.0

            new_rent_yearly = current_rent_yearly

            if project.building_contract_increment == 'amount':
                increment_amount = project.contract_increment_amount or 0.0
                new_rent_yearly = current_rent_yearly + increment_amount

            elif project.building_contract_increment == 'percentage':
                percentage = project.contract_increment_percentage or 0.0
                new_rent_yearly = current_rent_yearly * (1 + percentage / 100)

            new_rent_monthly = new_rent_yearly / 12

            if contract.duration_id:
                if contract.duration_id.rent_unit == 'Day':
                    to_date = contract.end_date + relativedelta(days=contract.duration_id.month) - timedelta(days=1)
                elif contract.duration_id.rent_unit == 'Month':
                    to_date = contract.end_date + relativedelta(months=contract.duration_id.month) - timedelta(days=1)
                elif contract.duration_id.rent_unit == 'Year':
                    to_date = contract.end_date + relativedelta(years=contract.duration_id.month) - timedelta(days=1)

            new_contract_details = self.env['contract.update.register'].create({
                'contract_id': contract.id,
                'name': contract.tenancy_seq or '/',
                'increase_or_decrease': 'increase',
                'amount_or_percentage': project.building_contract_increment,
                'amount': project.contract_increment_amount if project.building_contract_increment == 'amount' else 0.0,
                'percentage': project.contract_increment_percentage if project.building_contract_increment == 'percentage' else 0.0,
                'duration_id': contract.duration_id.id if contract.duration_id else False,
                'from_date': contract.end_date + timedelta(days=1),
                'to_date': to_date, 
                'current_rent_monthly': contract.total_rent or 0.0,
                'current_rent_annually': current_rent_yearly,
                'new_rent_monthly': new_rent_monthly,
                'new_rent_annually': new_rent_yearly,
                'status': 'approved',
            })
            contract.update_unit_price(new_contract_details)
            contract.new_contract_sent = True
    
    def update_unit_price(self,new_contract_details):
        self.ensure_one()
        units = self.unit_ids if self.is_multi_contract else self.property_id

        for unit in units:
            if new_contract_details.amount_or_percentage == 'percentage':
                factor = (
                    1 + new_contract_details.percentage / 100
                    if new_contract_details.increase_or_decrease == 'increase'
                    else 1 - new_contract_details.percentage / 100
                )
                unit.price_yearly *= factor
            else:
                amount = (
                    new_contract_details.amount
                    if new_contract_details.increase_or_decrease == 'increase'
                    else -new_contract_details.amount
                )
                unit.price_yearly += amount

    @api.model
    def cron_test_active_contract(self):
        # Get first tenancy record
        tenancy = self.search([], limit=1)

        

        _logger.info(tenancy.id,"tenancy")
        if not tenancy:
            _logger.info("No tenancy record found.")
            return

        # Create wizard
        wizard = self.env["active.contract"].create({
            "type": "automatic",
        })

        # Pass active_id like the button does
        wizard = wizard.with_context(
            active_id=tenancy.id,
            active_model="tenancy.details",
        )

        # Execute existing function
        wizard.action_create_contract()

    @api.depends('contract_payment_ids.amount', 'total_contract_value')
    def compute_remaining_value(self):
        for rec in self:
            rec.remaining_to_pay = rec.total_contract_value - sum(rec.contract_payment_ids.mapped('amount'))

    @api.depends('total_rent_year','contract_value', 'deposit_amount', 'added_service_ids.price')
    def _compute_breakdown(self):
        for rec in self:

            if rec.is_by_date:
                print('before ifff')

                duration_days = rec.duration_id.month or 0

                current_year = fields.Date.today().year
                days_in_year = 366 if calendar.isleap(current_year) else 365

                daily_rent = rec.total_rent_year / days_in_year

                payment_term_days = {
                    'daily': 1,
                    'monthly': 30,
                    'every_two_months': 60,
                    'quarterly': 90,
                    'every_four_months': 120,
                    'half_year': 180,
                    'year': 365,
                    'full_payment': duration_days,
                }

                period_days = payment_term_days.get(rec.payment_term, 1)

                payments_per_year = int(duration_days // period_days)
                remaining_days = duration_days % period_days

                rent_amount = daily_rent * period_days
                remaining_amount = daily_rent * remaining_days

                yearly_total = (
                    rent_amount * payments_per_year
                ) + remaining_amount

            elif rec.contract_value and rec.duration_type != 'by_date':
                print('ifff')

                duration = rec.duration_id.month
                monthly_rent = rec.contract_value / duration
                payment_term_val = rec.get_payment_term_qty()

                rent_amount = monthly_rent * payment_term_val

                months_per_payment = rec.get_payment_term_qty()
                payments_per_year = int(duration / months_per_payment)

                remaining_payments_per_year = int(
                    duration % months_per_payment
                )

                remaining_amount = (
                    monthly_rent * remaining_payments_per_year
                )

                yearly_total = (
                    rent_amount * payments_per_year
                ) + remaining_amount

            else:
                rec.total_value_breakdown = ''
                continue

            deposit = rec.deposit_amount if rec.is_any_deposit else 0.0
            vat_total = 0.0
            price_total = 0.0
            tax_percent = 0

            for service in rec.added_service_ids:
                service_price = service.price or 0.0
                price_total += service_price

                taxes = service.service_id.taxes_id.filtered(
                    lambda t: t.amount > 0
                )

                if taxes:
                    tax_percent = sum(taxes.mapped('amount'))
                    tax_amount = service_price * (tax_percent / 100)
                    vat_total += tax_amount

            taxes = rec.tax_ids.filtered(lambda t: t.amount > 0)

            if rec.instalment_tax and taxes:
                total_tax_percent = sum(taxes.mapped('amount'))
                install_tax = yearly_total * (
                    total_tax_percent / 100
                )
            else:
                total_tax_percent = 0
                install_tax = 0

            payment_term_label = dict(
                rec._fields['payment_term'].selection
            ).get(rec.payment_term, '')

            if rec.payment_term == 'daily' and not rec.is_by_date:
                current_year = fields.Date.today().year
                days = 365

                if calendar.isleap(current_year):
                    days = 366

                rent_amount = (rec.total_rent_year / days)
                payments_per_year = duration
                yearly_total = rent_amount * payments_per_year

            total_amount = (
                yearly_total
                + install_tax
                + deposit
                + price_total
                + vat_total
            )

            if remaining_amount > 0:
                total_rent_line = (
                    f"<b>Total Rent:</b> "
                    f"({rent_amount:,.2f} × {payments_per_year} ({payment_term_label})) "
                    f"+ {remaining_amount:,.2f} (Remaining) = {yearly_total:,.2f}<br/>"
                )
            else:
                total_rent_line = (
                    f"<b>Total Rent:</b> "
                    f"({rent_amount:,.2f} × {payments_per_year} ({payment_term_label})) "
                    f"= {yearly_total:,.2f}<br/>"
                )

            rec.total_value_breakdown = f"""
                {total_rent_line}
                <b>Tax on Total Rent:</b> {int(total_tax_percent)}% = {install_tax:,.2f}<br/>
                <b>Deposit Amount:</b> {deposit:,.2f}<br/>
                <b>Extra Service:</b> {price_total:,.2f}<br/>
                <b>Tax on Extra Service:</b> {int(tax_percent)}% = {vat_total:,.2f}<br/>
                <b> Total Amount:</b> {total_amount:,.2f}
            """

    def action_recompute_contract_values_and_payments(self):
        """Regenerate contract totals/breakdown and payment (PDC) lines for
        records that were bulk-imported and so never went through the
        Contract wizard's automation. Safe to call on already-processed
        contracts for the totals part (plain recompute); regenerates
        payment lines from scratch for each record, so skip contracts
        whose payment lines were manually edited/reconciled.
        """
        self._compute_contract_value()
        self._compute_breakdown()
        errors = []
        for record in self:
            try:
                record.contract_payment_pdc()
            except (ValidationError, UserError) as e:
                errors.append(_("%s: %s") % (record.tenancy_seq or record.id, e))
        if errors:
            raise UserError(_("Payment details could not be regenerated for:\n%s") % "\n".join(errors))

    def contract_payment_pdc(self):
        self._compute_breakdown()
        property_id = self._get_property_queryset()
        self.ensure_one()

        rent_bank_ac = property_id.property_project_id.rent_bank_account_id
        vat_sec_bank_ac = property_id.property_project_id.vat_sec_bank_account_id
        security_bank_ac = property_id.property_project_id.security_bank_account_id

        pdc_journal = self.env['account.journal'].search(
            [('is_pdc_journal', '=', True)], limit=1
        )
        cash_journal = self.env['account.journal'].search(
            [('type', '=', 'cash')], limit=1
        )

        if not pdc_journal:
            raise ValidationError("PDC Journal is not configured.")

        self.contract_payment_ids = [(5, 0, 0)]
        date = self.start_date

        # =====================================================
        # RENT CALCULATION
        # =====================================================

        if self.is_by_date:
            duration_days = self.duration_id.month or 0

            current_year = fields.Date.today().year
            days_in_year = 366 if calendar.isleap(current_year) else 365

            daily_rent = self.total_rent_year / days_in_year

            payment_term_days = {
                'daily': 1,
                'monthly': 30,
                'every_two_months': 60,
                'quarterly': 90,
                'every_four_months': 120,
                'half_year': 180,
                'year': 365,
                'full_payment': duration_days,
            }

            period_days = payment_term_days.get(self.payment_term, 1)

            payments_per_year = int(duration_days // period_days)
            remaining_days = duration_days % period_days

            rent_amount = daily_rent * period_days
            remaining_amount = daily_rent * remaining_days

            yearly_total = (
                rent_amount * payments_per_year
            ) + remaining_amount

            remaining_payments_per_year = remaining_days
            months_per_payment = None

        elif self.contract_value and self.duration_type != 'by_date':
            duration = self.duration_id.month

            monthly_rent = self.contract_value / duration
            payment_term_val = self.get_payment_term_qty()

            rent_amount = monthly_rent * payment_term_val

            months_per_payment = self.get_payment_term_qty()
            payments_per_year = int(duration / months_per_payment)

            remaining_payments_per_year = int(
                duration % months_per_payment
            )

            remaining_amount = (
                monthly_rent * remaining_payments_per_year
            )

            yearly_total = (
                rent_amount * payments_per_year
            ) + remaining_amount

        else:
            return

        # =====================================================
        # DEPOSIT / TAX
        # =====================================================

        deposit = self.deposit_amount if self.is_any_deposit else 0.0
        vat_total = 0.0
        price_total = 0.0

        taxes = self.tax_ids.filtered(lambda t: t.amount > 0)

        if self.instalment_tax and taxes:
            total_tax_percent = sum(taxes.mapped('amount'))
            install_tax = yearly_total * (total_tax_percent / 100)
        else:
            install_tax = 0

        # =====================================================
        # DAILY (OLD LOGIC)
        # =====================================================

        if self.payment_term == 'daily' and not self.is_by_date:
            current_year = fields.Date.today().year
            days = 365

            if calendar.isleap(current_year):
                days = 366

            one_day = (self.total_rent_year / days)
            payments_per_year = duration
            rent_amount = one_day * payments_per_year

            self.contract_payment_ids.sudo().create({
                'payment_type':'bank',
                'contract_id': self.id,
                'journal_id': rent_bank_ac.id,
                'amount': rent_amount,
                'chq_due_date': date,
            })
            return

        total_amount = yearly_total + install_tax + price_total + vat_total
        total_pdc_rent = (rent_amount * payments_per_year) + remaining_amount
        balance_amount = total_amount - total_pdc_rent

        # =====================================================
        # RENT PDCs
        # =====================================================

        for i in range(payments_per_year):
            self.contract_payment_ids.sudo().create({
                'payment_type':'cheque',
                'contract_id': self.id,
                'journal_id': rent_bank_ac.id,
                'amount': rent_amount,
                'chq_due_date': date,
            })

            if self.is_by_date:
                date = date + relativedelta(days=period_days)
            else:
                date = date + relativedelta(months=months_per_payment)

        if remaining_amount > 0:
            self.contract_payment_ids.sudo().create({
                'payment_type':'cheque',
                'contract_id': self.id,
                'journal_id': pdc_journal.id,
                'amount': remaining_amount,
                'chq_due_date': date,
            })

        # =====================================================
        # RENT TAX
        # =====================================================

        if balance_amount > 0:
            self.contract_payment_ids.sudo().create({
                'payment_type':'bank',
                'contract_id': self.id,
                'journal_id': vat_sec_bank_ac.id,
                'amount': balance_amount,
                'chq_due_date': self.start_date,
                'ref': 'Tax on total rent',
            })

        service_total = 0.0
        service_vat_total = 0.0

        for service in self.added_service_ids:
            service_price = service.price or 0.0
            service_total += service_price

            taxes = service.service_id.taxes_id.filtered(
                lambda t: t.amount > 0
            )

            if taxes:
                tax_percent = sum(taxes.mapped('amount'))
                service_vat_total += (
                    service_price * (tax_percent / 100)
                )

        service_grand_total = service_total + service_vat_total

        if service_grand_total > 0:
            self.contract_payment_ids.sudo().create({
                'payment_type':'cash',
                'contract_id': self.id,
                'journal_id': cash_journal.id,
                'amount': service_grand_total,
                'chq_due_date': self.start_date,
                'ref': 'Extra Service Charges With VAT',
            })

        if deposit > 0:
            self.contract_payment_ids.sudo().create({
                'payment_type':'bank',
                'contract_id': self.id,
                'journal_id': security_bank_ac.id,
                'amount': deposit,
                'chq_due_date': self.start_date,
                'ref': 'Security Deposit',
            })

    def closure_final_approval(self):
        property_id = self._get_property_queryset()
        self.ensure_one()
        if (self.env.user not in self.final_level_approval_requested_to
            and not self.env.user.has_group('base.group_system')):
            raise ValidationError('You do not have permission to approve this request.')
        else:
            contract_id = self.env['tenancy.details'].browse(self.id)
            if not contract_id:
                raise ValidationError(_("No contract found to close."))

            invoice = False
            attachment_penalty = False
            all_attachments = []
            description = f"Contract Closing Charges for {contract_id.tenancy_seq}"
            currency_symbol = contract_id.currency_id.symbol or ""


            if self.if_penalty:
                product = self.env['product.product'].search([('name', '=', 'Contract Closing Charges')], limit=1)
                if not product:
                    product = self.env['product.product'].create({'name': 'Contract Closing Charges'})

                invoice_line_vals = [(0, 0, {
                    'product_id': product.id,
                    'quantity': 1,
                    'name': description,
                    'price_unit': self.penalty_amount,
                })]

                invoice = self.env['account.move'].sudo().create({
                    'partner_id': contract_id.tenancy_id.id,
                    'move_type': 'out_invoice',
                    'invoice_date': date.today(),
                    'invoice_line_ids': invoice_line_vals,
                    'tenancy_id': contract_id.id,
                })
                invoice.action_post()

                rent_invoice = self.env['rent.invoice'].create({
                    'tenancy_id': contract_id.id,
                    'customer_id': contract_id.tenancy_id.id,
                    'type': 'penalty',
                    'rent_invoice_id': invoice.id,
                    'description': description,
                    'amount': self.penalty_amount,
                    'invoice_date': date.today(),
                })

                contract_id.write({
                    'rent_invoice_ids': [(4, rent_invoice.id)],
                })

                pdf_content, _ = self.env['ir.actions.report']._render_qweb_pdf(
                    'account.account_invoices', [invoice.id]
                )
                pdf_raw = pdf_content

                attachment_penalty = self.env['ir.attachment'].create({
                    'name': f"{invoice.name or 'Invoice'}.pdf",
                    'type': 'binary',
                    'raw': pdf_raw,
                    'res_model': 'tenancy.details',
                    'res_id': contract_id.id,
                    'mimetype': 'application/pdf',
                })

                all_attachments.append(attachment_penalty.id)

            if self.termination_type == 'early':
                contract_state = 'pre_terminated'
            else:
                contract_state = 'terminated'
            contract_id.write({
                'contract_type': contract_state,
                'close_contract_state': True,
                'terminate_date': self.closing_date,
                'final_level_approved_by':self.env.user,
                'final_level_approved_date':date.today()
            })
            if self.is_multi_contract:
                self.unit_ids.write({
                    'stage': 'available',
                })
            else:
                contract_id.property_id.write({
                    'stage': 'available',
                })
            partner_ids = []

            if contract_id.tenancy_id:
                partner_ids.append(contract_id.tenancy_id.id)

            if contract_id.termination_requested_person:
                partner_ids.append(contract_id.termination_requested_person.partner_id.id)

            if contract_id.first_level_approved_by:
                partner_ids.append(contract_id.first_level_approved_by.partner_id.id)

            if contract_id.final_level_approved_by:
                partner_ids.append(contract_id.final_level_approved_by.partner_id.id)
            
            email = 'saif@shafar.ae'
            partner = self.env['res.partner'].search([('email', '=', email)], limit=1)
            if partner:
                partner_ids.append(partner.id)

            template = self.env.ref('ribs_real_estate.contract_closing_notification_template').sudo()

            ctx = {
                'default_model': self._name,
                'default_email_from': self.env.company.email,
                'default_partner_ids': partner_ids,
                'default_res_ids': [contract_id.id],
                'default_use_template': True,
                'default_template_id': template.id,
                'default_attachment_ids': all_attachments,

                'invoice_name': invoice.name if invoice else "No Invoice",
                'invoice_amount': self.penalty_amount if self.if_penalty else f"0 {currency_symbol}",
                'description': description,
                'has_penalty': self.if_penalty,  
            }

            return {
                'type': 'ir.actions.act_window',
                'res_model': 'mail.compose.message',
                'view_mode': 'form',
                'target': 'new',
                'context': ctx,
            }
            
    def closure_first_approval(self):
        self.ensure_one()
        if (self.env.user not in self.first_level_approval_requested_to
            and not self.env.user.has_group('base.group_system')):
            raise ValidationError('You do not have permission to approve this request.')

        context = {
            'default_contract_id': self.id,
            'default_termination_requested_person':self.termination_requested_person.id,
            'default_closing_reason':self.closing_reason,
            'default_closing_date':self.closing_date,
            'default_termination_type':self.termination_type,
            'default_first_level_approval_requested_to':[(6, 0, self.first_level_approval_requested_to.ids)],
            'default_final_level_approval_requested_to':[(6, 0, self.final_level_approval_requested_to.ids)],
            'default_if_penalty':self.if_penalty,
            'default_penalty_amount':self.penalty_amount,
        }
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'contract.closure.approval.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': context
        }

    @api.depends('start_date', 'month', 'rent_unit', 'payment_term', 'duration_type',
                 'duration_end_date', 'is_by_date')
    def _compute_end_date(self):
        for rec in self:
            if rec.is_by_date:
                rec.end_date = rec.duration_end_date
                continue
            end_date = None
            if rec.duration_type == 'by_duration' and rec.start_date:
                if rec.rent_unit == "Day":
                    delta = relativedelta(days=rec.month)
                elif rec.rent_unit == "Year" or rec.payment_term == "year":
                    delta = relativedelta(months=rec.month)
                elif rec.payment_term == "daily":
                    delta = relativedelta(days=rec.month)
                else:
                    delta = relativedelta(months=rec.month)
                end_date = rec.start_date + delta - relativedelta(days=1)
            if rec.duration_type == 'by_date' and rec.duration_end_date:
                end_date = rec.duration_end_date
            rec.end_date = end_date

class ContractAdditionalTermLine(models.Model):
    """One line of the contract's Additional Terms, numbered in order and
    printed in the Contract Agreement report the same way."""
    _name = 'contract.additional.term.line'
    _description = 'Contract Additional Term Line'
    _order = 'sequence, id'

    contract_id = fields.Many2one(
        'tenancy.details', string="Contract", required=True, ondelete='cascade')
    sequence = fields.Integer(string="No.", default=10)
    description = fields.Char(string="Description")
