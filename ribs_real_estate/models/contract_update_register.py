from odoo.exceptions import ValidationError
from odoo import api, fields, models, _
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta



class DewaRegister(models.Model):
    _name = 'contract.update.register'
    _rec_name = 'name'
    _inherit = ['portal.mixin',
                'mail.alias.mixin.optional',
                'mail.thread',
                'mail.activity.mixin',
                ]
    _description = "Contract Update Register"


    contract_id = fields.Many2one('tenancy.details', string='Contract', readonly=True)
    project_id = fields.Many2one(related='contract_id.property_project_id', string='Contract', readonly=True)
    name = fields.Char(related='contract_id.tenancy_seq', string='Contract Name', readonly=True)
    increase_or_decrease = fields.Selection([
        ('increase', 'Increase'),
        ('decrease', 'Decrease')
    ], default='increase', string='Increase/Decrease', required=True, tracking=True)
    amount_or_percentage = fields.Selection([
        ('amount', 'Amount'),
        ('percentage', 'Percentage')
    ], default='percentage', string='Amount or Percentage', required=True, tracking=True)
    amount = fields.Monetary('Amount', tracking=True)
    percentage = fields.Float(string='Percentage %', tracking=True)
    duration_id = fields.Many2one('contract.duration', string='Duration', tracking=True, compute='_compute_duration_id', store=True, readonly=False)
    from_date = fields.Date(string='From Date', required=True, tracking=True)
    to_date = fields.Date(string='To Date', required=True)
    company_id = fields.Many2one('res.company',
                                 string='Company',
                                 default=lambda self: self.env.company)
    currency_id = fields.Many2one('res.currency',
                                  related='company_id.currency_id',
                                  string='Currency ')
    current_rent_monthly = fields.Float(string='Current Rent/Month', compute="_compute_rents", store=True)
    current_rent_annually = fields.Float(string='Current Rent/Year', compute="_compute_rents", store=True)
    new_rent_monthly = fields.Float(string='New Rent/Month', compute="_compute_rents", store=True)
    new_rent_annually = fields.Float(string='New Rent/Year', compute="_compute_rents", store=True)
    status = fields.Selection([
        ('waiting_for_approval', 'Waiting For Approval'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
    ], default='waiting_for_approval', string='Status', tracking=True)

    @api.depends('percentage', 'increase_or_decrease', 'amount', 'amount_or_percentage', 'contract_id.total_rent_year')
    def _compute_rents(self):
        for rec in self:
            current_rent_year = rec.contract_id.total_rent_year or 0.0
            rec.current_rent_annually = current_rent_year
            rec.current_rent_monthly = current_rent_year / 12 if current_rent_year else 0.0

            new_rent_yearly = 0.0
            new_rent_monthly = 0.0

            if rec.amount_or_percentage == 'percentage' and rec.percentage:
                if rec.increase_or_decrease == 'increase':
                    new_rent_yearly = current_rent_year + (current_rent_year * rec.percentage / 100)
                elif rec.increase_or_decrease == 'decrease':
                    new_rent_yearly = current_rent_year - (current_rent_year * rec.percentage / 100)

            elif rec.amount_or_percentage == 'amount' and rec.amount:
                if rec.increase_or_decrease == 'increase':
                    new_rent_yearly = current_rent_year + rec.amount
                elif rec.increase_or_decrease == 'decrease':
                    new_rent_yearly = current_rent_year - rec.amount

            rec.new_rent_annually = new_rent_yearly
            rec.new_rent_monthly = new_rent_yearly / 12 if new_rent_yearly else 0.0
            if rec.new_rent_monthly:
                tenancy = self.env['tenancy.details'].search([('id', '=', rec.contract_id.id)], limit=1)
                tenancy.write({'new_rent_monthly': rec.new_rent_monthly})
                tenancy.property_id.price_yearly = rec.new_rent_annually



    def send_new_contract_details(self):
        self.ensure_one()

        template = self.env.ref('ribs_real_estate.send_updated_contract').sudo()

        ctx = {
            'default_model': self._name,
            'default_email_from': self.env.company.email,
            'default_res_ids': [self.id],
            'default_use_template': True,
            'default_template_id': template.id,
            'default_composition_mode': 'comment',
            'default_partner_ids': [self.contract_id.tenancy_id.id],
            'force_email': True,
        }

        action = {
            'type': 'ir.actions.act_window',
            'res_model': 'mail.compose.message',
            'view_mode': 'form',
            'view_id': False,
            'target': 'new',
            'context': ctx,
        }
        self.contract_id.sudo().new_contract_sent = True
        return self._get_action_with_base_document_layout_configurator(action)

    def _get_action_with_base_document_layout_configurator(self, report_action):
        if (
            self.env.is_admin()
            and not self.env.company.external_report_layout_id
            and not self.env.context.get('discard_logo_check')
        ):
            report_action = self.env['ir.actions.report']._action_configure_external_report_layout(
                report_action,
                "account.action_base_document_layout_configurator",
            )
            self.contract_id.new_contract_sent = True
        return report_action


    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            contract_id = vals.get('contract_id')
            if contract_id:
                self.search([('contract_id', '=', contract_id)]).unlink()

        return super(DewaRegister, self).create(vals_list)

    @api.onchange('duration_id','from_date')
    def _onchange_duration_id(self):
        if self.duration_id:
            if self.duration_id.rent_unit == 'Day':
                self.to_date = self.from_date + relativedelta(days=self.duration_id.month) - timedelta(days=1)
            elif self.duration_id.rent_unit == 'Month':
                self.to_date = self.from_date + relativedelta(months=self.duration_id.month) - timedelta(days=1)
            elif self.duration_id.rent_unit == 'Year':
                self.to_date = self.from_date + relativedelta(years=self.duration_id.month) - timedelta(days=1)

    def _check_admin_access(self):
        param = self.env['ir.config_parameter'].sudo().get_str(
            'ribs_real_estate.authorized_users_ids', ''
        )
        authorized_ids = [int(x) for x in param.split(',') if x]
        if self.env.user.id not in authorized_ids:
            raise ValidationError("You are not allowed to perform this action.")

    def action_approve(self):
        self._check_admin_access()
        self.write({'status': 'approved'})

    def action_reject(self):
        self._check_admin_access()
        self.write({'status': 'rejected'})

    def send_mail(self):
        for rec in self:
            if rec.status != 'approved':
                raise ValidationError("You cannot send mail for unapproved requests.")

            template = self.env.ref('ribs_real_estate.send_updated_contract')
            if template:
                template.send_mail(rec.id)
                if rec.contract_id:
                    rec.contract_id.sudo().new_contract_sent = True

    def action_approve_and_mail(self):
        self._check_admin_access()
        self.write({'status': 'approved'})
        
        template = self.env.ref('ribs_real_estate.send_updated_contract')
        for rec in self:
            if template:
                template.send_mail(rec.id)
                if rec.contract_id:
                    rec.contract_id.sudo().new_contract_sent = True

    def _get_selection_display(self, field_name, value):
        field = self._fields.get(field_name)
        if not field or not field.selection:
            return value

        return dict(field.selection).get(value, value)

    def write(self, vals):
        tracked_fields = {
            'increase_or_decrease',
            'amount_or_percentage',
            'amount',
            'percentage'
        }

        changed_fields = tracked_fields.intersection(vals.keys())
        if not changed_fields:
            return super().write(vals)
        param = self.env['ir.config_parameter'].sudo().get_str(
            'ribs_real_estate.authorized_users_ids', ''
        )
        authorized_ids = [int(x) for x in param.split(',') if x]
        current_user_id = self.env.user.id

        old_values = {}
        for rec in self:
            old_values[rec.id] = {
                'increase_or_decrease': rec._get_selection_display(
                    'increase_or_decrease', rec.increase_or_decrease
                ),
                'amount_or_percentage': rec._get_selection_display(
                    'amount_or_percentage', rec.amount_or_percentage
                ),
                'amount': rec.amount,
                'percentage': rec.percentage,
            }

        res = super().write(vals)

        if current_user_id not in authorized_ids:
            for rec in self:
                new_values = {
                    'increase_or_decrease': rec._get_selection_display(
                        'increase_or_decrease', rec.increase_or_decrease
                    ),
                    'amount_or_percentage': rec._get_selection_display(
                        'amount_or_percentage', rec.amount_or_percentage
                    ),
                    'amount': rec.amount,
                    'percentage': rec.percentage,
                }

                rec.status = 'waiting_for_approval'
                rec.authorized_users_mail(
                    old_value=old_values[rec.id],
                    new_value=new_values,
                    changed_fields={f: True for f in changed_fields}
                )

        return res

    def authorized_users_mail(self, old_value, new_value, changed_fields):
        param = self.env['ir.config_parameter'].sudo().get_str(
            'ribs_real_estate.authorized_users_ids', ''
        )
        authorized_ids = [int(x) for x in param.split(',') if x]

        base_url = self.env['ir.config_parameter'].sudo().get_str('web.base.url', False)
        action = self.env.ref(
            "ribs_real_estate.waiting_approve_update_contract",
            raise_if_not_found=False
        )

        record_url = (
            f"{base_url}/odoo/action-{action.id}/{self.id}"
            if action else
            f"{base_url}/odoo/contract.update.register/{self.id}"
        )

        template = self.env.ref(
            'ribs_real_estate.mail_template_renew_contract_approval'
        )

        emails = self.env['res.users'].browse(authorized_ids).mapped('email')
        emails = [e for e in emails if e]

        if emails:
                template.with_context(
                    old_value=old_value,
                    new_value=new_value,
                    changed_fields=changed_fields,
                    record_url=record_url,
                ).sudo().send_mail(
                    self.id,
                    email_values={'email_to': ','.join(emails)},
                    force_send=True,
                )

    @api.depends('from_date', 'to_date')
    def _compute_duration_id(self):
        for rec in self:
            if not rec.from_date or not rec.to_date:
                continue

            if rec.to_date < rec.from_date:
                continue

            diff = relativedelta(rec.to_date + timedelta(days=1), rec.from_date)

            duration_parts = []
            if diff.years:
                duration_parts.append(f"{diff.years} Year")
            if diff.months:
                duration_parts.append(f"{diff.months} Month")
            if diff.days:
                duration_parts.append(f"{diff.days} Day")

            duration_name = " ".join(duration_parts)
            total_days = (rec.to_date - rec.from_date).days + 1

            duration = rec.env['contract.duration'].search([
                ('duration', '=', duration_name),
                ('rent_unit', '=', 'Day'),
            ], limit=1)

            if not duration:
                duration = rec.env['contract.duration'].create({
                    'duration': duration_name,
                    'month': total_days,
                    'rent_unit': 'Day',
                })

            rec.duration_id = duration.id
