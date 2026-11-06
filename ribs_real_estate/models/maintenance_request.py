from odoo import fields, models, api, _
from datetime import datetime, timedelta
import logging
_logger = logging.getLogger(__name__)
import urllib.parse


class MaintenanceRequest(models.Model):
    _inherit = 'maintenance.request'

    attachment_ids = fields.Many2many('ir.attachment', string='Attachments', readonly=False, store=True)
    due_date_only = fields.Date(string="Due Date")
    due_time_only = fields.Char(string="Due Time")
    exceeded_time = fields.Char(string="Exceeded Time")

    # Pre-handover property details
    building_id_parent = fields.Many2one('property.project', string='Building')
    property_id = fields.Many2one('property.details', string='Unit',domain="[('property_project_id', '=', building_id_parent)]")
    project_id = fields.Many2one(related='rent_contract_id.property_project_id', string='Buildings')
    property = fields.Many2one(related='rent_contract_id.property_id', string='Property')
    property_type = fields.Selection(related='rent_contract_id.property_type', string='Unit Type')
    total_area = fields.Float(related='rent_contract_id.property_id.total_area', string='Area')
    measure_unit = fields.Selection(related='rent_contract_id.property_id.measure_unit',string='Measure Unit')
    tenant_id = fields.Many2one(related='rent_contract_id', string='Tenancy')
    contract_start_date = fields.Date(related='rent_contract_id.start_date',string="Contract Start Date")
    move_in_ids = fields.One2many(
        'maintenance.condition.line', 'request_id',
        domain=[('item.item_for', '=', 'move_in')])
    cleaning_done = fields.Boolean(string="Cleaning completed")
    repairs_done = fields.Boolean(string="All repairs completed")
    safety_checks = fields.Boolean(string="Safety checks done")
    ready_for_handover = fields.Boolean(string="Unit is ready for handover")
    unit_key = fields.Integer(string="Unit Key")
    access_card = fields.Integer(string="Access/ Remote/ Parking Card")
    dewa_security_deposit = fields.Boolean(string="Dewa Security Deposit")

    # Move-out property and tenant details
    partner_id = fields.Many2one(related='rent_contract_id.tenancy_id', string='Tenant Name')
    contract_end_date = fields.Date(related='rent_contract_id.end_date',string="Move-Out Date")
    forwarding_contact = fields.Char(related='rent_contract_id.customer_email', string='Forwarding Contact')
    forwarding_email = fields.Char(related='rent_contract_id.customer_email', string='Forwarding Email')
    inspection_team = fields.Many2many('hr.employee', string='Inspection Team')
    electricity = fields.Char(related='rent_contract_id.property_id.dewa_number', string='Electricity (DEWA)')
    water = fields.Char(string='Water')
    chiller = fields.Char(string='Chiller')
    attach_photo = fields.Boolean(string="Attach Photos")
    bill_attachment = fields.Many2many('ir.attachment','bill_attachment_rel', string='Image')
    move_out_ids = fields.One2many(
        'maintenance.condition.line', 'request_id',
         store=True)
    damage_description = fields.Char(string='Damage Description')
    estimated_cost = fields.Float(string='Estimated Cost')
    chargeable_to_tenant = fields.Boolean(string='Chargeable to Tenant')
    note = fields.Text(string='Notes')

    key_card_remote_id = fields.Selection([('received', 'Received'),('not_received', 'Not received')], string='Key Returned')
    parking_card_remote_id = fields.Selection([('received', 'Received'),('not_received', 'Not received')], string='Parking Tags Returned')
    access_cards_returned_id = fields.Selection([('received', 'Received'),('not_received', 'Not received')], string='Access Cards Returned')
    missing_items = fields.Text(string='Missing Items')
    key_qty = fields.Integer(default=0)
    access_cards_qty = fields.Integer(default=0)
    parking_tags_qty = fields.Integer(default=0)

    outstanding_rent_id = fields.Selection([('received', 'Received'),('not_received', 'Not received')], string='Outstanding Rent')
    outstanding_utilities_id = fields.Selection([('received', 'Received'), ('not_received', 'Not received')], string='Outstanding Utilities')
    damages_chargeable_id = fields.Selection([('received', 'Received'), ('not_received', 'Not received')], string='Damages Chargeable')
    move_out_ready_id = fields.Selection([('yes', 'Yes'), ('no', 'No')], string='Move Out Ready')
    mr_for = fields.Selection([('move_in', 'Move-in'),('move_out', 'Move-out'),('others', 'Others')], default='others', string='MR For')
    client_preferred_time = fields.Datetime('Tenant Preferred Time')

    mr_created_person_id = fields.Many2one('res.users', string="Tenant Name")
    customer_id = fields.Many2one( 'res.partner',  string="Customer",  compute="_compute_customer_id", store=True, readonly=False,)

    @api.depends('rent_contract_id')
    def _compute_customer_id(self):
        for rec in self:
            rec.customer_id = rec.rent_contract_id.tenancy_id if rec.rent_contract_id else False
    
    
    def get_mr_url(self):
        self.ensure_one()
        base_url = self.env['ir.config_parameter'].sudo().get_str('web.base.url', False)
        action = self.env.ref('maintenance.hr_equipment_request_action', raise_if_not_found=False)
        action_id = action.id if action else None

        if action_id:
            return (
                f"{base_url}/web#action={action_id}"
                f"&model=maintenance.request"
                f"&view_type=list"
                f"&domain=[('property_id','=',{self.property_id.id})]"
            )
        else:
            return (
                f"{base_url}/web#model=maintenance.request"
                f"&view_type=list"
                f"&domain=[('property_id','=',{self.property_id.id})]"
            )

    @api.model_create_multi
    def create(self, vals_list):
        record = super().create(vals_list)

        if record.mr_created_person_id: 
            if record.property_id:
                company_secretary_email = self.env.company.company_secretary.work_email
                manager_email = record.property_id.property_manager.work_email

                email_list = [email for email in [company_secretary_email] if email]
                email_to = ','.join(email_list)

                count = self.search_count([('property_id', '=', record.property_id.id)])
                default_maintenance_count = int(self.env['ir.config_parameter'].sudo().get_str('ribs_real_estate.maintenance_count', False))
                            
                if count > default_maintenance_count:
                    template = self.env.ref('ribs_real_estate.email_template_recurring_complaints')
                    if email_to and template:
                        ctx_others = dict(self.env.context, custom_regards=record.property_id.property_manager.name)
                        template.with_context(ctx_others).send_mail(
                            record.id,
                            email_values={'email_from': self.env.company.email, 'email_to': email_to},
                            force_send=True
                        )

                    if manager_email and template:
                        ctx_manager = dict(self.env.context, custom_regards=self.env.company.name)
                        template.with_context(ctx_manager).send_mail(
                            record.id,
                            email_values={'email_from': self.env.company.email, 'email_to': manager_email},
                            force_send=True
                        )
        if record.rent_contract_id:
            record.property_id = record.rent_contract_id.property_id
            record.building_id_parent = record.property_id.property_project_id
        return record

    def get_request_url(self):
        self.ensure_one()
        return f"/web#id={self.id}&model=maintenance.request&view_type=form"

    def check_priority_requests(self):
        template = self.env.ref('ribs_real_estate.maintenance_overdue_email_template', raise_if_not_found=False)

        for request in self.search([]):
            company_secretary_email = self.env.company.company_secretary.work_email
            manager_email = request.property_id.property_manager.work_email

            email_list = [email for email in [company_secretary_email] if email]
            email_to = ','.join(email_list)

            if request.priority in ['1', '2', '3']:
                hours = {'1': 72, '2': 48, '3': 24}[request.priority]
                due_time = request.create_date + timedelta(hours=hours)

                request.due_date_only = due_time.date()
                request.due_time_only = due_time.strftime('%I:%M %p')

                if datetime.now() > due_time:
                    delta = datetime.now() - due_time
                    days, remainder = divmod(delta.total_seconds(), 86400)
                    hours, remainder = divmod(remainder, 3600)
                    minutes, _ = divmod(remainder, 60)
                    request.exceeded_time = f"{int(days)}d {int(hours)}h {int(minutes)}m"
                else:
                    request.exceeded_time = "0d 0h 0m"

                if datetime.now() >= due_time:
                    if email_to and template:
                        ctx_others = dict(self.env.context, custom_regards=request.property_id.property_manager.name)
                        template.with_context(ctx_others).send_mail(
                            request.id,
                            email_values={'email_from': self.env.company.email, 'email_to': email_to},
                            force_send=True
                        )

                    if manager_email and template:
                        ctx_manager = dict(self.env.context, custom_regards=self.env.company.name)
                        template.with_context(ctx_manager).send_mail(
                            request.id,
                            email_values={'email_from': self.env.company.email, 'email_to': manager_email},
                            force_send=True
                        )

        return True

    def write(self, vals):
        # Disable automatic chatter emails
        res = super(
            MaintenanceRequest,
            self.with_context(mail_notrack=True, tracking_disable=True)
        ).write(vals)

        for rec in self:
            if (
                    rec.mr_created_person_id
                    and rec.mr_created_person_id.login != "__system__"
                    and vals.get('stage_id') == 3
            ):
                template = rec.env.ref(
                    'ribs_real_estate.mr_completed_feedback',
                    raise_if_not_found=False
                )

                leasing_group = self.env.ref('rental_management.property_rental_manager')
                leasing_team_emails = leasing_group.all_user_ids.mapped('email')
                tenancy_email = rec.rent_contract_id.tenancy_id.email
                maintenance_emails = rec.property_id.maintenance_person_ids.mapped('work_email')

                email_list = [
                    email for email in
                    [tenancy_email, *leasing_team_emails, *maintenance_emails]
                    if email
                ]

                if template and email_list:
                    template.send_mail(
                        rec.id,
                        force_send=True,
                        email_values={
                            'email_from': rec.env.company.email,
                            'email_to': ','.join(email_list),
                        }
                    )

        return res

    @api.onchange('rent_contract_id')
    def _onchange_rent_contract_id(self):
        if self.rent_contract_id:
            self.property_id = self.rent_contract_id.property_id
            self.building_id_parent = self.rent_contract_id.property_project_id

class MaintenanceConditionLine(models.Model):
    _name = "maintenance.condition.line"
    _description = "Maintenance Condition Line"

    request_id = fields.Many2one('maintenance.request', string='Request')
    # item = fields.Char(string="Item")
    item = fields.Many2one('maintenance.condition.line.item',string="Item")
    move_in_status = fields.Selection([('ok', 'OK'), ('not_ok', 'Not OK'), ('not_applicable', 'N/A')], string="Status",
                              default='not_ok')
    move_out_status = fields.Selection([('good','Good'), ('fair', 'Fair'),('poor','Poor')], string="Condition",default='poor')
    notes = fields.Text(string="Notes / Required Action")
    move_out_notes = fields.Text(string="Notes")
    chargeable = fields.Boolean(string="Chargeable")

class MaintenanceConditionLineItem(models.Model):
    _name = "maintenance.condition.line.item"
    _description = "Maintenance Condition Line Item"

    name = fields.Char(string="Name")
    item_for = fields.Selection([('move_in', 'Move-in'),('maintenance_request', 'Maintenance Request'),('move_out', 'Move Out')])



