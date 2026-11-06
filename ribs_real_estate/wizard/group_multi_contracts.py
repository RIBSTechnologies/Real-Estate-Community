# -*- coding: utf-8 -*-
# Copyright 2020-Today TechKhedut.
# Part of TechKhedut. See LICENSE file for full copyright and licensing details.
from odoo import fields, models, api, _
from dateutil.relativedelta import relativedelta
from odoo.exceptions import ValidationError
import calendar
from datetime import date, timedelta
import logging
_logger = logging.getLogger(__name__)
from odoo import Command



class ContractWizard(models.Model):
    """Property Rent Contract Creation"""
    _name = "group.multi.contracts"
    _description = "Create Contract of rent in property"

    # Company & Currency
    currency_id = fields.Many2one("res.currency", string="Currency",
                                  related="company_id.currency_id")
    company_id = fields.Many2one("res.company", string="Company",
                                 default=lambda self: self.env.company)

    # Customer Details
    customer_id = fields.Many2one("res.partner", string="Customer",
                                  domain=[("user_type", "=", "customer")], required=True)
    customer_phone = fields.Char(related="customer_id.phone",
                                 store=True,
                                 readonly=False)
    customer_email = fields.Char(related="customer_id.email",
                                 store=True,
                                 readonly=False)

    # Property Details
    property_id = fields.Many2one("property.project", string="Buidling")
    unit_ids = fields.Many2many("property.details", string="Units",
                                domain="[('property_project_id','=',property_id),('stage','in',('available','on_lease'))]")
    rent_unit = fields.Selection([("Day", "Day"),
                                  ("Month", "Month"), ("Year", "Year")],
                                 default="Month",
                                 string="Rent Unit")
    total_rent_year = fields.Monetary(string="Total Rent (Yearly)", required=True, store=True)
    contract_value = fields.Monetary(string="Contract Value", help="Total value of the contract", 
                    readonly=True, compute="_compute_contract_value")

    # Deposit
    is_any_deposit = fields.Boolean(string="Deposit")
    deposit_amount = fields.Monetary(string="Security Deposit")


 
    # Contract Detail
    payment_term = fields.Selection([("monthly", "Monthly"),
                                     ("full_payment", "Full Payment"),
                                     ("quarterly", "Quarterly"),
                                     ('half_year', 'Half Year'),
                                     ("year", "Yearly"),
                                     ("daily", "Daily"),
                                     ("every_two_months", "Every Two Months"),
                                     ("every_four_months", "Every Four Months")], string="Payment Term")
    duration_ids = fields.Many2many("contract.duration", string="Durations",
                                    compute="compute_durations")
    duration_id = fields.Many2one("contract.duration", string="Duration",
                                  domain="[('id','in',duration_ids)]")
    start_date = fields.Date(string="Start Date")
    end_date = fields.Date(string="End Date", compute="_compute_end_date", store=True) 
    total_days = fields.Integer(compute="_compute_total_days")
    duration_type = fields.Selection([('by_duration', 'By Duration'),
                                      ('by_date', 'By Date')], default='by_duration')
    duration_end_date = fields.Date()


    # Leads
    from_inquiry = fields.Boolean("From Enquiry")
    lead_id = fields.Many2one("crm.lead", string="Enquiry",
                              domain="[('property_id','=',property_id)]")
    note = fields.Text(string="Note", translate=True)

    # Agreement
    agreement = fields.Html(string="Agreement")
    agreement_template_id = fields.Many2one("agreement.template", string="Agreement Template",
                                            domain="[('company_id','=',company_id)]")

    # Instalment Item
    installment_item_id = fields.Many2one(
        "product.product", string="Installment Item")
    deposit_item_id = fields.Many2one("product.product", string="Deposit Item")
    broker_item_id = fields.Many2one("product.product", string="Broker Item")
    maintenance_item_id = fields.Many2one(
        "product.product", string="Maintenance Item")

    # Taxes
    instalment_tax = fields.Boolean(string="Taxes on Installment ?")
    deposit_tax = fields.Boolean(string="Taxes on Deposit ?")
    service_tax = fields.Boolean(string="Taxes on Services ?")
    tax_ids = fields.Many2many("account.tax", string="Taxes")

    # Terms & Conditions
    term_condition = fields.Html(string="Term and Condition")

    # Multi contract period
    is_contract_available = fields.Boolean(
        compute="_compute_is_contract_available")
    contract_desc = fields.Text(compute="_compute_is_contract_available",
                                string="Draft Contract")

    # Available Payment Term
    available_payment_term = fields.Char(
        compute="_compute_available_payment_term")

    is_from_existing_contract = fields.Boolean(default=False)
    is_multi_contract = fields.Boolean(string="Is Multi Contract", default=False)
    is_by_date = fields.Boolean(string="By Date")
    duration = fields.Char(string="Duration")
    days = fields.Integer(string="Days", default=1)
    grace_period_value = fields.Integer(string="Grace Period")
    grace_period_unit = fields.Selection([
        ('days', 'Days'),
        ('month', 'Month'),
        ('year', 'Year'),
    ], string="Grace Period Unit", default='days')
    grace_period_start_date = fields.Date(string="Grace Period Start Date", readonly=True, help="The date when the grace period starts.")
    grace_period_end_date = fields.Date(string="Grace Period End Date", readonly=True, help="The date when the grace period ends.")

    
    # Broker Details
    # is_any_broker = fields.Boolean(string="Any Broker?")
    # broker_id = fields.Many2one("res.partner", string="Broker",
    #                             domain=[("user_type", "=", "broker")])
    # rent_type = fields.Selection([("once", "First Month"), ("e_rent", "All Month")],
    #                              string="Brokerage Type")
    # commission_type = fields.Selection([("f", "Fix"), ("p", "Percentage")],
    #                                    string="Commission Type")
    # commission_from = fields.Selection([("customer", "Customer"), ("landlord", "Landlord",)],
    #                                    string="Commission From", )
    # broker_commission = fields.Monetary(string="Commission")
    # broker_commission_percentage = fields.Float(string="Percentage")

    # Utility Services
    # is_extra_service = fields.Boolean(related="property_id.is_extra_service",
    #                                   string="Any Extra Services")
    # extra_service_ids = fields.One2many(
    #     related="property_id.extra_service_ids")
    # services = fields.Text(string="Utility Services",
    #                        compute="_compute_services", translate=True)
    # extra_service_invoice = fields.Selection([('merge', 'Merge With Installment'),
    #                                           ('separate', 'Separate')], default='merge', readonly=True)

    # Added Services
    is_added_services = fields.Boolean(string="Is Extra Services")
    added_service_ids = fields.One2many(comodel_name='contract.service.line',
                                        inverse_name='rent_contract_id_1')
    added_service_invoice = fields.Selection([('merge', 'Merge With Installment'),
                                              ('separate', 'Separate')], default='separate')

    # # Maintenance
    # is_any_maintenance = fields.Boolean(string="Any Maintenance",
    #                                     related="property_id.is_maintenance_service")
    # maintenance_rent_type = fields.Selection(
    #     related="property_id.maintenance_rent_type")
    # total_maintenance = fields.Monetary(
    #     related="property_id.total_maintenance")
    # maintenance_service_invoice = fields.Selection([('merge', 'Merge With Installment'),
    #                                                 ('separate', 'Separate')], default='merge')


    unit_line_ids = fields.One2many(
        "group.multi.contract.line",
        "contract_id",
        string="Units"
    )

    overall_total = fields.Float(
    compute="_compute_totals",
    store=True
    )

    overall_discount = fields.Float(
        compute="_compute_totals",
        store=True
    )

    discount_type = fields.Selection([
    ("percent", "Percentage"),
    ("fixed", "Fixed Amount"),
    ], default="percent")

    selected = fields.Boolean(string="Select")

    discount_value = fields.Float()

    apply_to_all = fields.Boolean(string="Apply to All")

    is_by_date = fields.Boolean(string="By Date")

    last_update_id = fields.Many2one(
        'contract.update.register',
        string="Latest Contract Update",
        compute='_compute_last_update',
        readonly=True,
        store=True,
    )

    update_increase_or_decrease = fields.Selection(
        related='last_update_id.increase_or_decrease',
        readonly=True
    )
    update_amount_or_percentage = fields.Selection(
        related='last_update_id.amount_or_percentage',
        readonly=True
    )
    update_amount = fields.Monetary(
        related='last_update_id.amount',
        readonly=True
    )
    update_percentage = fields.Float(
        related='last_update_id.percentage',
        readonly=True
    )
    update_from_date = fields.Date(
        related='last_update_id.from_date',
        readonly=True
    )
    update_to_date = fields.Date(
        related='last_update_id.to_date',
        readonly=True
    )
    update_new_rent_monthly = fields.Float(
        related='last_update_id.new_rent_monthly',
        readonly=True
    )
    update_new_rent_annually = fields.Float(
        related='last_update_id.new_rent_annually',
        readonly=True
    )
    
    @api.depends(
    "unit_line_ids.total",
    "unit_line_ids.discount_amount",
    "unit_ids",
    "unit_ids.price_yearly",
    )
    def _compute_totals(self):
        for rec in self:
            rec.overall_total = sum(rec.unit_line_ids.mapped("total"))
            rec.overall_discount = sum(rec.unit_line_ids.mapped("discount_amount"))

            if rec.overall_discount:
                rec.total_rent_year = rec.overall_total
            else:
                rec.total_rent_year = sum(rec.unit_ids.mapped("price_yearly"))

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        contract_id = self.env.context.get('active_contract_id')
        active_model = self.env.context.get("active_model")
        active_id = self.env.context.get("active_id")
        ejari_registration = self.env.ref('ribs_real_estate.product_template_ejari_registration')
        _logger.warning(ejari_registration,'ejari_registrationejari_registration')
        # registration_charges = self.env.ref('ribs_real_estate.product_template_registration_charges_ejari')
        default_deposit_prod = self.env.ref("rental_management.property_product_2")
        default_deposit_item = default_deposit_prod.product_variant_id
        _logger.warning("default_deposit_prod: %s", default_deposit_prod)
        _logger.warning("default_deposit_item: %s", default_deposit_item)
        if contract_id:
            contract_obj = self.env['tenancy.details'].browse(contract_id)
            new_contract = self.env['contract.update.register'].search(
                [('contract_id', '=', contract_id)],
                order='id desc',
                limit=1
            )

            # Always prefill from the contract being renewed first, so the
            # wizard is never blank even when no rent-increase request
            # (contract.update.register) has been sent/approved yet.
            res['is_multi_contract'] = contract_obj.is_multi_contract
            res['customer_id'] = contract_obj.tenancy_id.id
            res['property_id'] = contract_obj.property_project_id.id
            res['unit_ids'] = [(6, 0, (
                contract_obj.unit_ids.ids if contract_obj.is_multi_contract
                else contract_obj.property_id.ids
            ))]
            res['payment_term'] = contract_obj.payment_term
            res['is_by_date'] = contract_obj.is_by_date if contract_obj.is_by_date else False
            res['is_from_existing_contract'] = True
            res['duration_type'] = contract_obj.duration_type or 'by_duration'
            res['rent_unit'] = 'Month'
            res['start_date'] = (
                contract_obj.end_date + timedelta(days=1)
                if contract_obj.end_date else contract_obj.start_date
            )
            res['duration_id'] = contract_obj.duration_id.id
            res['total_rent_year'] = contract_obj.total_rent_year

            if new_contract:
                # A rent-increase request has been prepared - its proposed
                # terms take precedence over the contract's current ones.
                res['duration_type'] = 'by_duration'
                res['rent_unit'] = 'Month'
                res['start_date'] = new_contract.from_date
                res['duration_end_date'] = new_contract.to_date
                res['duration_id'] = new_contract.duration_id.id
                res['total_rent_year'] = new_contract.new_rent_annually
                res['is_by_date'] = new_contract.contract_id.is_by_date if new_contract.contract_id.is_by_date else False
                res['is_from_existing_contract'] = True
                res['payment_term'] = new_contract.contract_id.payment_term

                res['is_multi_contract'] = self.env.context.get('is_multi_contract')
                res['customer_id'] = new_contract.contract_id.tenancy_id
                res['property_id'] = new_contract.contract_id.property_project_id
                res['unit_ids'] = [(6, 0, contract_obj.unit_ids.ids)]

        res['is_added_services'] = True
        res['added_service_ids'] = [
            Command.create({
                'service_id': ejari_registration.product_variant_id.id,
                'price': ejari_registration.list_price,
            }),
            # Command.create({
            #     'service_id': registration_charges.id,
            #     'price': registration_charges.list_price,
            # }),
        ]
        res["deposit_item_id"] = default_deposit_item.id

        # res['customer_id'] = 11598
        # res['property_id'] = 278
        # units = self.env['property.details'].browse([51991, 52145, 52589])
        # res['unit_ids'] = [(6, 0, units.ids)]
        # res['start_date'] = date.today()
        # res['payment_term'] = 'quarterly'
        # res['duration_id'] = 1
        # res['instalment_tax'] = False
            

        terms_html_obj = self.env['default.terms.conditions'].search([], limit=1)
        if terms_html_obj.terms_html:
            res['term_condition'] = terms_html_obj.terms_html
        if 'instalment_tax' in fields_list:
            res['instalment_tax'] = True
        # if active_model == "property.details":
        #     property_id = self.env["property.details"].browse(active_id)
        #     res['total_rent_year'] = property_id.price_yearly
        #     res['contract_value'] = property_id.price_yearly * 1
        #     if property_id.deposit_amount:
        #         res['deposit_amount'] = property_id.deposit_amount
        #         res['is_any_deposit'] = bool(res['deposit_amount'])
        elif active_model == "tenancy.details":
            res['deposit_amount'] = None
            res['is_any_deposit'] = False
        return res

    @api.depends('instalment_tax')
    def _compute_last_update(self):
        active_model = self.env.context.get("active_model")
        for wizard in self:
            last_update_id  = self.env['contract.update.register'].search(
                [('contract_id', '=', self.env.context.get('active_contract_id'))],
                order='to_date desc',
                limit=1
            ) 
            wizard.last_update_id = last_update_id if active_model == "tenancy.details" and last_update_id else False 

    @api.depends('duration_id.month', 'total_rent_year','end_date')
    def _compute_contract_value(self):
        for record in self:
            months = record.duration_id.month or 0
            total_rent_year = record.total_rent_year or 0
            current_year = fields.Date.today().year
            days = 365
            if calendar.isleap(current_year):
                days = 366
            if record.payment_term == 'daily':
                record.contract_value = (total_rent_year / days)* months
            elif record.is_by_date:
                start_date = record.start_date
                end_date = record.end_date

                if not start_date or not end_date:
                    record.contract_value = 0
                    continue

                days = (end_date - start_date).days + 1

                days_in_year = 366 if calendar.isleap(start_date.year) else 365

                record.contract_value = (total_rent_year / days_in_year) * days
            else:
                record.contract_value = total_rent_year * (months / 12)

    @api.depends("rent_unit")
    def _compute_available_payment_term(self):
        """Get available payment term"""
        for rec in self:
            available_payment_term = None
            if rec.rent_unit == "Month":
                available_payment_term = "Available Payment Term  : Monthly, Quarterly, Half year, Full Payment"
            elif rec.rent_unit == "Year":
                available_payment_term = "Available Payment Term  : Yearly, Full Payment"
            elif rec.rent_unit == "Day":
                available_payment_term = "Available Payment Term  : Monthly, Quarterly, Half Year, Yearly, Daily, Full Payment"
            rec.available_payment_term = available_payment_term

    @api.depends("start_date",
            "duration_id",
            "duration_id.month",
            "payment_term",
            "rent_unit",
            "duration_type",
            "duration_end_date")
    def _compute_end_date(self):
        """Compute end date"""
        for rec in self:
            end_date = None
            if rec.is_by_date:
                rec.end_date = rec.duration_end_date
                continue
            if (rec.duration_type == 'by_duration'
                    and rec.duration_id
                    and rec.payment_term
                    and rec.rent_unit
                    and rec.start_date):
                if rec.rent_unit == "Day":
                    end_date = (rec.start_date
                                + relativedelta(days=rec.duration_id.month)
                                - relativedelta(days=1))
                elif rec.rent_unit == "Month":
                    end_date = (rec.start_date
                                + relativedelta(months=rec.duration_id.month)
                                - relativedelta(days=1))
                else:
                    if rec.payment_term == "year":
                        end_date = (rec.start_date
                                    + relativedelta(months=rec.duration_id.month)
                                    - relativedelta(days=1))
                    else:
                        end_date = (rec.start_date
                                    + relativedelta(months=rec.duration_id.month)
                                    - relativedelta(days=1))
            if rec.duration_type == "by_date":
                end_date = rec.duration_end_date
            rec.end_date = end_date

    @api.onchange('is_by_date')
    def _onchange_is_by_date(self):
        # if self.is_from_existing_contract:
        #     self.is_from_existing_contract = False
        #     return
        if self.is_by_date:
            self.payment_term = 'daily'
        else:
            self.payment_term = None

    @api.onchange('end_date')
    def _onchange_end_date(self):
        if self.is_by_date and  self.end_date:
            self.action_generate_duration()
            # self._calculate_contract_value()

    # @api.onchange('grace_period_start_date')
    # def onchange_grace_period_start_date(self):
    #     if self.grace_period_start_date and self.grace_period_start_date < date.today():
    #         raise ValidationError(_("Grace period start date cannot be in the past."))
    
    # @api.onchange('start_date')
    # def onchange_start_date(self):
    #     if self.start_date and self.start_date < date.today():
    #         raise ValidationError(_("Start date cannot be in the past."))

    @api.onchange('start_date', 'grace_period_value', 'grace_period_unit')
    def _onchange_grace_period_dates(self):
        """Grace End Date is always the day before the contract starts;
        Grace Start Date is that same point minus the Grace Period value/unit,
        so both are always derived backward from Start Date, never typed by hand."""
        if self.start_date and self.grace_period_value:
            if self.grace_period_unit == 'month':
                delta = relativedelta(months=self.grace_period_value)
            elif self.grace_period_unit == 'year':
                delta = relativedelta(years=self.grace_period_value)
            else:
                delta = relativedelta(days=self.grace_period_value)
            self.grace_period_end_date = self.start_date - timedelta(days=1)
            self.grace_period_start_date = self.start_date - delta
        else:
            self.grace_period_start_date = False
            self.grace_period_end_date = False

    def action_generate_duration(self):
        self.ensure_one()

        start_date = self.start_date
        end_date = self.end_date or self.duration_end_date

        if not start_date or not end_date:
            return

        if end_date < start_date:
            raise ValidationError("End Date must be greater than Start Date.")

        diff = relativedelta(end_date + timedelta(days=1), start_date)

        duration_parts = []
        if diff.years:
            duration_parts.append(f"{diff.years} Year")
        if diff.months:
            duration_parts.append(f"{diff.months} Month")
        if diff.days:
            duration_parts.append(f"{diff.days} Day")

        self.duration = " ".join(duration_parts)

    def _calculate_contract_value(self):
        print('funcc caliing')
        self.ensure_one()

        end_date = self.end_date or self.duration_end_date
        start_date = self.start_date

        if not start_date or not end_date:
            self.contract_value = 0.0
            return

        total_amount = 0.0
        current_date = start_date

        while current_date <= end_date:
            current_year = current_date.year
            year_end = date(current_year, 12, 31)
            period_end = min(year_end, end_date)
            days_in_period = (period_end - current_date).days + 1
            days_in_year = 366 if calendar.isleap(current_year) else 365
            daily_rent = self.total_rent_year / days_in_year
            total_amount += daily_rent * days_in_period
            current_date = period_end + timedelta(days=1)

        self.contract_value = total_amount

    @api.depends('start_date', 'end_date')
    def _compute_total_days(self):
        """Compute total days"""
        for rec in self:
            total_days = 0
            if rec.start_date and rec.end_date:
                rec.days = (rec.end_date - rec.start_date).days + 1
                total_days = (rec.end_date - rec.start_date).days + 1
            rec.total_days = total_days if total_days >= 0 else 0

    @api.onchange('start_date', 'days')
    def _onchange_days(self):
        if self.is_by_date and self.start_date and self.days:
            self.end_date = self.start_date + timedelta(days=self.days - 1)
            self.action_generate_duration()
            # self._calculate_contract_value()

    @api.depends("payment_term", "rent_unit")
    def compute_durations(self):
        """Compute duration bases on rent unit"""
        for rec in self:
            duration_record = self.env["contract.duration"].sudo()
            ids = []
            if rec.rent_unit == "Day":
                domain = [("rent_unit", "=", "Day")]
                ids = duration_record.search(domain).mapped("id")
            if rec.rent_unit == "Year":
                # domain = [("rent_unit", "=", "Year")]
                domain = [("rent_unit", "=", "Month")]
                ids = duration_record.search(domain).mapped("id")
            if rec.rent_unit == "Month":
                if rec.payment_term == "quarterly":
                    domain = [("month", ">=", 3), ("rent_unit", "=", "Month")]
                    ids = duration_record.search(domain).mapped("id")
                elif rec.payment_term == 'every_two_months':
                    domain = [('month', '>=', 2), ('rent_unit', '=', 'Month')]
                    ids = duration_record.search(domain).mapped("id")
                elif rec.payment_term == 'every_four_months':
                    domain = [('month', '>=', 4), ('rent_unit', '=', 'Month')]
                    ids = duration_record.search(domain).mapped("id")
                elif rec.payment_term == "half_year":
                    domain = [("month", ">=", 6), ("rent_unit", "=", "Month")]
                    ids = duration_record.search(domain).mapped("id")
                elif rec.payment_term == "year":
                    domain = [("rent_unit", "=", "Month")]
                    ids = duration_record.search(domain).mapped("id")
                else:
                    domain = [("month", ">", 0), ("rent_unit", "=", "Month")]
                    ids = duration_record.search(domain).mapped("id")
            if rec.rent_unit == "Month" and rec.payment_term == 'daily':
                domain = [('rent_unit', '=', 'Day')]
                ids = duration_record.search(domain).mapped("id")

            rec.duration_ids = ids

    @api.onchange("unit_ids")
    def _onchange_unit_ids(self):
        for rec in self:
            total_rent = 0.0
            total_deposit = 0.0

            # Keep only existing lines whose units are still selected
            kept_lines = rec.unit_line_ids.filtered(
                lambda l: l.property_id in rec.unit_ids
            )

            # Existing property ids
            existing_property_ids = kept_lines.mapped("property_id").ids

            commands = [(4, line.id) for line in kept_lines if line.id]

            for unit in rec.unit_ids:
                total_rent += unit.price_yearly
                total_deposit += unit.deposit_amount

                if unit.id not in existing_property_ids:
                    commands.append((0, 0, {
                        "property_id": unit.id,
                        "total_rent_year": unit.price_yearly,
                        "deposit_amount": unit.deposit_amount,
                        "tax_id": unit.tax_id.id if unit.tax_id else False,
                    }))

            rec.unit_line_ids = [(5, 0, 0)] + commands

            rec.total_rent_year = total_rent
            rec.deposit_amount = total_deposit
            rec.is_any_deposit = bool(total_deposit)

            taxes = rec.unit_ids.mapped("tax_id")
            rec.tax_ids = [(6, 0, taxes.ids)]
            rec.instalment_tax = bool(taxes)

    @api.depends("start_date", "end_date", "property_id")
    def _compute_is_contract_available(self):
        """Check Contract Period Available between start date and end date."""
        for rec in self:
            availability = False
            desc = ""
            if rec.start_date and rec.end_date:
                date_domain = [
                    ("start_date", "<=", rec.end_date),
                    ("end_date", ">", rec.start_date),
                ]
                domain = [("contract_type", "not in",
                           ["expire_contract", "cancel_contract", "close_contract"],),
                          ("property_id", "=", rec.property_id.id),
                          ]
                rent_record = self.env["tenancy.details"].sudo().search(date_domain + domain)
                draft_contract_record = rent_record.filtered(
                    lambda line: line.contract_type == "new_contract"
                )
                if draft_contract_record:
                    for data in draft_contract_record:
                        desc = (desc
                                + f"{data.tenancy_seq} : {data.start_date} to {data.end_date}"
                                + "\n")
                if not rent_record.filtered(lambda line: line.id not in draft_contract_record.ids):
                    availability = True

            rec.is_contract_available = availability
            rec.contract_desc = desc
            if rec.unit_line_ids:
                rec.unit_line_ids._compute_total()
    
    def contract_action(self):
        """Process rent contract"""
        active_model = self.env.context.get("active_model")
        active_id = self.env.context.get("active_id")
        self.customer_id.user_type = "customer"
        if active_model == "tenancy.details":
            tenancy_id = self.env["tenancy.details"].browse(active_id)
            tenancy_id.contract_type = "close_contract"
            tenancy_id.close_contract_state = True

        if self.is_by_date:
            if not self.duration_end_date and self.end_date:
                self.duration_end_date = self.end_date
            elif not self.end_date and self.duration_end_date:
                self.end_date = self.duration_end_date

            if not self.duration_end_date:
                raise ValidationError("Please set an End Date before creating the contract.")

            self.action_generate_duration()
            duration_rec = self._get_or_create_duration()
            self.duration_id = duration_rec.id

        record = self.get_contract_info()
        # Utilities
        service_line = []
        # if self.property_id.is_extra_service:
        #     for data in self.property_id.extra_service_ids:
        #         service_line.append((0, 0, {
        #             "service_id": data.service_id.id,
        #             "service_type": data.service_type,
        #             "from_contract": True,
        #             "price": data.price,
        #         }))
        # if service_line:
        #     record["extra_services_ids"] = service_line
        #     record['extra_service_invoice'] = self.extra_service_invoice
        # Extra Services
        if self.is_added_services and self.added_service_ids:
            record['is_added_services'] = self.is_added_services
            record['added_service_ids'] = [(0, 0, {'service_id': data.service_id.id,
                                                'price': data.price}) for data in
                                        self.added_service_ids]
            record['added_service_invoice'] = self.added_service_invoice
        # Payment Term : Full Payment
        if self.payment_term == "full_payment":
            record["last_invoice_payment_date"] = fields.Date.today()
            record["active_contract_state"] = True
            record["contract_type"] = "running_contract"
            contract_id = self.env["tenancy.details"].create(record)
            contract_id._onchange_agreement_template_id()
            contract_id.contract_payment_pdc()
            if self.is_by_date:
                contract_id.write({"end_date": self.duration_end_date})
            # if contract_id.is_any_broker:
            #     contract_id.action_broker_invoice()
            # Full Payment Invoice
            if self.duration_type == 'by_duration':
                self.action_create_full_payment_invoice(
                    contract_id=contract_id)
            if self.duration_type == 'by_date':
                self._process_by_dated_full_payment(contract_id=contract_id)
            self.customer_id.is_tenancy = True
            self.unit_ids.write({"stage": "on_lease"})
            # self.property_id.write({"stage": "on_lease"})
            if active_model == "tenancy.details":
                old_tenancy_id = self.env["tenancy.details"].browse(active_id)
                old_tenancy_id.extended = True
                old_tenancy_id.extend_ref = contract_id.tenancy_seq
                old_tenancy_id.new_contract_id = contract_id.id
                contract_id.is_extended = True
                contract_id.extend_from = old_tenancy_id.tenancy_seq
            return {
                "type": "ir.actions.act_window",
                "name": "Contract",
                "res_model": "tenancy.details",
                "res_id": contract_id.id,
                "view_mode": "form,list",
                "target": "current",
            }
        if self.rent_unit == "Year" and self.payment_term not in [
            "year",
            "full_payment",
        ]:
            message = {
                "type": "ir.actions.client",
                "tag": "display_notification",
                "params": {
                    "type": "info",
                    "title": (
                        "For Rent unit Year, please select a payment term: either 'Yearly' or 'Full Payment'."
                    ),
                    "sticky": False,
                },
            }
            return message
        if self.rent_unit == "Month" and self.payment_term in ["yearly"]:
            message = {
                "type": "ir.actions.client",
                "tag": "display_notification",
                "params": {
                    "type": "info",
                    "title": (_("For Rent unit Month, please select a payment"
                                " term: either 'Monthly', 'Quarterly', or 'Full Payment'.")),
                    "sticky": False,
                },
            }
            return message
        # Payment Term : Monthly Quarterly, Year, Daily
        if self.payment_term != "full_payment":
            record["contract_type"] = "new_contract"
            contract_id = self.env["tenancy.details"].create(record)
            contract_id._onchange_agreement_template_id()
            contract_id.contract_payment_pdc()
            if self.is_by_date:
                contract_id.write({"end_date": self.duration_end_date})
            self.customer_id.is_tenancy = True
            self.unit_ids.write({"stage": "on_lease"})
            if active_model == "tenancy.details":
                old_tenancy_id = self.env["tenancy.details"].browse(active_id)
                old_tenancy_id.extended = True
                old_tenancy_id.extend_ref = contract_id.tenancy_seq
                old_tenancy_id.new_contract_id = contract_id.id
                contract_id.is_extended = True
                contract_id.extend_from = old_tenancy_id.tenancy_seq
            return {
                "type": "ir.actions.act_window",
                "name": "Contract",
                "res_model": "tenancy.details",
                "res_id": contract_id.id,
                "view_mode": "form,list",
                "target": "current",
            }       

    def _get_or_create_duration(self):
        self.ensure_one()

        end_date = self.end_date or self.duration_end_date
        start_date = self.start_date

        if not start_date or not end_date:
            raise ValidationError("Start Date and End Date are required to generate duration.")

        if not self.duration:
            raise ValidationError("Duration name is not set. Please select dates first.")

        total_days = (end_date - start_date).days + 1

        duration = self.env['contract.duration'].search([
            ('duration', '=', self.duration),
            ('rent_unit', '=', 'Day'),
        ], limit=1)

        if not duration:
            duration = self.env['contract.duration'].create({
                'duration': self.duration,
                'month': total_days,
                'rent_unit': 'Day',
            })

        return duration 

    def get_contract_info(self):
        """Prepare contract data"""
        data = {
            # Customer
            "tenancy_id": self.customer_id.id,
            # Property
            "property_project_id": self.unit_ids[0].property_project_id.id,
            "unit_ids": self.unit_ids,
            "total_rent_year": self.total_rent_year,
            "final_rent_unit": self.rent_unit,
            "property_landlord_id": self.property_id.landlord_id.id,
            # Contract Details
            'duration_type': self.duration_type,
            'duration_end_date': self.duration_end_date,
            "duration_id": self.duration_id.id,
            "start_date": self.start_date,
            "invoice_start_date": self.start_date,
            "payment_term": self.payment_term,
            # Deposit
            "is_any_deposit": self.is_any_deposit,
            "deposit_amount": self.deposit_amount,
            # agreement
            "agreement": self.agreement,
            "agreement_template_id": self.agreement_template_id.id,
            # Installment Item
            "installment_item_id": self.installment_item_id.id,
            "broker_item_id": self.broker_item_id.id,
            "deposit_item_id": self.deposit_item_id.id,
            "maintenance_item_id": self.maintenance_item_id.id,
            # Taxes
            "tax_ids": self.tax_ids.ids,
            "instalment_tax": self.instalment_tax,
            "service_tax": self.service_tax,
            "deposit_tax": self.deposit_tax,
            # Terms Conditions
            "term_condition": self.term_condition,
            # Maintenance
            # "maintenance_service_invoice": self.maintenance_service_invoice,
            # Passing Multi Contract Period Info
            "is_multi_contract": True,        
            "is_by_date":self.is_by_date,
            "end_date": self.end_date,
        }
        return data

    # Agreement
    @api.onchange("agreement_template_id")
    def _onchange_agreement_template_id(self):
        """Get agreement bases on agreement template"""
        for rec in self:
            rec.agreement = rec.agreement_template_id.agreement

    def action_create_full_payment_invoice(self, contract_id):
        """Process full payment contract & invoice"""
        invoice_post_type = self.env["ir.config_parameter"].sudo(
        ).get_str("rental_management.invoice_post_type", False)
        service_invoice_line = []
        desc = ""
        full_payment_record = {
            "product_id": self.installment_item_id.id,
            "name": "Full Payment of " + self.property_id.name,
            "quantity": 1,
            "price_unit": self.get_total_rent() * self.duration_id.month,
            "tax_ids": self.tax_ids.ids if self.instalment_tax else False,
        }
        service_invoice_line.append((0, 0, full_payment_record))
        if self.is_any_deposit:
            deposit_record = {
                "product_id": self.deposit_item_id.id,
                "name": "Deposit of " + self.property_id.name,
                "quantity": 1,
                "price_unit": self.deposit_amount,
                "tax_ids": self.tax_ids.ids if self.deposit_tax else False,
            }
            service_invoice_line.append((0, 0, deposit_record))
        # if self.is_any_maintenance and self.maintenance_service_invoice == 'merge':
        #     service_invoice_line.append((0, 0, {
        #         "product_id": self.maintenance_item_id.id,
        #         "name": "Maintenance of " + self.property_id.name,
        #         "quantity": 1,
        #         "price_unit": (
        #             self.total_maintenance
        #             if self.maintenance_rent_type == "once"
        #             else self.total_maintenance * self.duration_id.month
        #         ),
        #     }))
        # if self.property_id.is_extra_service and self.extra_service_invoice == 'merge':
        #     for line in self.property_id.extra_service_ids:
        #         if line.service_type == "once":
        #             desc = "Service Type : Once" + "\n" "Service : " + str(
        #                 line.service_id.name
        #             )
        #         if line.service_type == "monthly":
        #             desc = "Service Type : Recurring" + "\n" "Service : " + str(
        #                 line.service_id.name
        #             )
        #         service_invoice_line.append((0, 0, {
        #             "product_id": line.service_id.id,
        #             "name": desc,
        #             "quantity": (
        #                 1 if line.service_type == "once" else self.duration_id.month
        #             ),
        #             "price_unit": line.price,
        #             "tax_ids": self.tax_ids.ids if self.service_tax else False,
        #         }))
        if self.is_added_services and self.added_service_ids and self.added_service_invoice == 'merge':
            for line in self.added_service_ids:
                service_invoice_line.append((0, 0, {
                    "product_id": line.service_id.id,
                    "name": line.service_id.name,
                    "quantity": 1,
                    "price_unit": line.price,
                }))
        if self.is_added_services and self.added_service_ids and self.added_service_invoice == 'separate':
            self._process_separate_added_services(contract_id=contract_id)
        invoice_id = self.env["account.move"].sudo().create({
            "partner_id": self.customer_id.id,
            "move_type": "out_invoice",
            "invoice_date": contract_id.invoice_start_date,
            "invoice_line_ids": service_invoice_line,
            'tenancy_id': contract_id.id
        })
        if invoice_post_type == "automatically":
            invoice_id.action_post()
        #  Rent Invoice Entry
        self.env["rent.invoice"].create({
            "tenancy_id": contract_id.id,
            "type": "full_rent",
            "invoice_date": contract_id.invoice_start_date,
            "amount": invoice_id.amount_total,
            "description": "Full Payment Of Rent" + (" + Deposit" if self.is_any_deposit else ""),
            "rent_invoice_id": invoice_id.id,
            "rent_amount": invoice_id.amount_total,
        })
        # if self.is_any_maintenance and self.maintenance_service_invoice == 'separate':
        #     self._process_separate_invoices(
        #         contract_id=contract_id, maintenance=True)
        # if self.is_extra_service and self.extra_service_invoice == 'separate':
        #     self._process_separate_invoices(
        #         contract_id=contract_id, utility=True)
        contract_id.action_send_active_contract()

    def _process_by_dated_full_payment(self, contract_id):
        """Process full payment for 'By Date'"""
        """By Dated : Full Payment Rent Invoice"""
        invoice_post_type = self.env["ir.config_parameter"].sudo(
        ).get_str("rental_management.invoice_post_type", False)
        delta = self.duration_end_date - self.start_date
        invoice_lines = [(0, 0, {
            'product_id': self.installment_item_id.id,
            "name": f"Full Payment : {self.start_date} to {self.duration_end_date}",
            "quantity": 1,
            "price_unit": self.get_total_rent() * (delta.days + 1),
            "tax_ids": self.tax_ids.ids if self.instalment_tax else False,
        })]
        if self.is_any_deposit:
            invoice_lines.append((0, 0, {
                "product_id": self.deposit_item_id.id,
                "name": "Deposit of " + self.property_id.name,
                "quantity": 1,
                "price_unit": self.deposit_amount,
                "tax_ids": self.tax_ids.ids if self.deposit_tax else False,
            }))
        if self.is_any_maintenance and self.maintenance_service_invoice == 'merge':
            invoice_lines.append((0, 0, {
                "product_id": self.maintenance_item_id.id,
                "name": "Maintenance of " + self.property_id.name,
                "quantity": 1 if self.property_id.maintenance_rent_type == 'once' else (
                        delta.days + 1),
                "price_unit": self.total_maintenance,
            }))
        if self.is_extra_service and self.extra_service_invoice == 'merge':
            for line in self.property_id.extra_service_ids:
                service_type = 'Once' if line.service_type == 'once' else "Recurring"
                invoice_lines.append((0, 0, {
                    "product_id": line.service_id.id,
                    "name": f"Service Type : {service_type} - {line.service_id.name}",
                    "quantity": 1 if line.service_type == "once" else (delta.days + 1),
                    "price_unit": line.price,
                    "tax_ids": self.tax_ids.ids if self.service_tax else False,
                }))
        if self.is_added_services and self.added_service_ids and self.added_service_invoice == 'merge':
            for line in self.added_service_ids:
                invoice_lines.append((0, 0, {
                    "product_id": line.service_id.id,
                    "name": line.service_id.name,
                    "quantity": 1,
                    "price_unit": line.price,
                    "tax_ids": False,
                }))
        if self.is_added_services and self.added_service_ids and self.added_service_invoice == 'separate':
            self._process_separate_added_services(contract_id=contract_id)
        invoice_id = self.env['account.move'].sudo().create({
            "partner_id": self.customer_id.id,
            "move_type": "out_invoice",
            "invoice_date": contract_id.invoice_start_date,
            "invoice_line_ids": invoice_lines,
            "tenancy_id": contract_id.id
        })
        if invoice_post_type == "automatically":
            invoice_id.action_post()
        self.env['rent.invoice'].sudo().create({
            "tenancy_id": contract_id.id,
            "type": "full_rent",
            "invoice_date": contract_id.invoice_start_date,
            "amount": invoice_id.amount_total,
            "description": "Full Payment Of Rent" + (" + Deposit" if self.is_any_deposit else ""),
            "rent_invoice_id": invoice_id.id,
            "rent_amount": invoice_id.amount_total, })
        if self.is_any_maintenance and self.maintenance_service_invoice == 'separate':
            self._process_separate_invoices(
                contract_id=contract_id, maintenance=True)
        if self.is_extra_service and self.extra_service_invoice == 'separate':
            self._process_separate_invoices(
                contract_id=contract_id, utility=True)
        contract_id.action_send_active_contract()

    @api.onchange('is_any_deposit')
    def _onchange_is_any_deposit(self):
        if self.is_any_deposit == False:
            self.deposit_amount = 0
    
    @api.onchange("property_id")
    def onchange_property_id(self):
        for rec in self:
            # Clear selected units
            if not rec.is_from_existing_contract:
                rec.unit_ids = [(5, 0, 0)]

                rec.unit_line_ids = [(5, 0, 0)]

                rec.total_rent_year = 0.0
                rec.deposit_amount = 0.0
                rec.is_any_deposit = False

    def action_select_all(self):
        self.unit_line_ids.write({"selected": True})
        return self._reopen_wizard()

    def action_unselect_all(self):
        self.unit_line_ids.write({
            "selected": False,
            "discount_applied": False,
            "discount_type": False,
            "discount_value": 0.0,
            "amount_based_on_duration": 0.0,
        })
        return self._reopen_wizard()

    def _reopen_wizard(self):
        return {
            "type": "ir.actions.act_window",
            "name": "Multi Contract",
            "res_model": "group.multi.contracts",
            "res_id": self.id,
            "view_mode": "form",
            "view_id": self.env.ref(
                "ribs_real_estate.group_multi_contracts_form_view"
            ).id,
            "target": "new",
        }

    def action_apply_discount(self):
        self.ensure_one()
        lines = self.unit_line_ids.filtered("selected")

        if not lines:
            raise ValidationError("Select at least one unit")

        for line in lines:
            line.discount_applied = True
            line.discount_type = self.discount_type
            line.discount_value = self.discount_value
        lines._compute_total()

        return {
            "type": "ir.actions.act_window",
            "name": "Multi Contract",
            "res_model": "group.multi.contracts",
            "res_id": self.id,
            "view_mode": "form",
            "view_id": self.env.ref(
                "ribs_real_estate.group_multi_contracts_form_view"
            ).id,
            "target": "new",
        }


class ContractServiceLineNew(models.TransientModel):
    """Contract Service Lines"""
    _inherit = "contract.service.line"

    rent_contract_id_1 = fields.Many2one(comodel_name="group.multi.contracts")
