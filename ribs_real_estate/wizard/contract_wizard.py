from odoo import fields, models, api, _
from dateutil.relativedelta import relativedelta
from odoo.exceptions import ValidationError
from datetime import date, timedelta
import calendar
from odoo.tools.float_utils import float_compare
from odoo import Command
import logging
_logger = logging.getLogger(__name__)



class ContractWizard(models.TransientModel):
    """Property Rent Contract Creation"""
    _inherit = "contract.wizard"

    total_rent_year = fields.Monetary(string="Total Rent (Yearly)", required=True)
    contract_value = fields.Monetary(string="Contract Value", help="Total value of the contract", 
                    readonly=True, compute="_compute_contract_value")

    grace_period_value = fields.Integer(string="Grace Period")
    grace_period_unit = fields.Selection([
        ('days', 'Days'),
        ('month', 'Month'),
        ('year', 'Year'),
    ], string="Grace Period Unit", default='days')
    grace_period_start_date = fields.Date(string="Grace Start Date", readonly=True)
    grace_period_end_date = fields.Date(string="Grace End Date", readonly=True)
    deposit_amount = fields.Monetary(string="Security Deposit")
    payment_term = fields.Selection(selection_add=[("every_two_months", "Every Two Months"),
                                     ("every_four_months", "Every Four Months")])
                                    
    # payment_type = fields.Selection([('cash','Cash'),('cdc','CDC'),('cheque','Cheque')],default='cash')
    # company_id = fields.Many2one('res.company',
    #                             string='Company',
    #                             default=lambda self: self.env.company)
    # currency_id = fields.Many2one('res.currency',
    #                             related='company_id.currency_id',
    #                             string='Currency')
    # amount = fields.Monetary('Amount')
    # chq_due_date = fields.Date('Due Date')
    # ref = fields.Char('Reference')
    # attachment_ids = fields.Binary('Attachments')

    # Updated Contract Details in the contract wizard table
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
    usable_area = fields.Float(related="property_id.usable_area", string="Usable Area", readonly=True)

    property_type = fields.Selection(related="property_id.type", string="Property Type", readonly=True)

    # Commercial-only: Rent = Rate x Size, independent of the generic area_wise pricing above.
    commercial_size = fields.Float(string="Unit Size")
    commercial_rate = fields.Monetary(string="Rate")

    @api.onchange('property_id')
    def _onchange_property_id_commercial_size(self):
        if self.property_id:
            self.commercial_size = self.property_id.unit_size

    @api.onchange('commercial_size', 'commercial_rate', 'property_id')
    def _onchange_commercial_rent(self):
        if self.property_id.type == 'commercial' and self.commercial_size and self.commercial_rate:
            self.total_rent_year = self.commercial_size * self.commercial_rate
    is_by_date = fields.Boolean(string="By Date")
    duration = fields.Char(string="Duration")
    is_from_existing_contract = fields.Boolean(default=False)

    #For Discount
    inital_rent_year = fields.Float(related='property_id.price_yearly', string="Initial Rent (Yearly)", readonly=True)
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

    discount_value = fields.Float()

    discount_applied = fields.Boolean(string="Discount Applied")

    tax_id = fields.Many2one("account.tax", string="Tax")

    discount_amount = fields.Monetary(
        compute="_compute_totals",
        store=True
    )

    tax_amount = fields.Monetary(
        compute="_compute_totals",
        store=True
    )

    @api.depends(
        "total_rent_year",
        "discount_applied",
        "discount_type",
        "discount_value",
        "tax_id",
        "tax_id.amount",
    )
    def _compute_totals(self):
        for rec in self:
            rent = rec.total_rent_year or 0.0

            discount = 0.0
            if rec.discount_applied and rec.discount_value:
                if rec.discount_type == "percent":
                    discount = rent * rec.discount_value / 100.0
                else:
                    discount = min(rec.discount_value, rent)

            rent_after_discount = rent - discount

            tax = 0.0
            if rec.tax_id:
                tax = rent_after_discount * rec.tax_id.amount / 100.0

            rec.discount_amount = discount
            rec.tax_amount = tax
            rec.overall_discount = discount
            rec.overall_total = rent_after_discount + tax


    def action_apply_discount(self):
        self.ensure_one()

        rent = self.total_rent_year

        if not self.discount_applied:
            if self.discount_type == "percent":
                discount = rent * self.discount_value / 100.0
            else:
                discount = min(self.discount_value, rent)

            self.write({
                "discount_applied": True,
                "total_rent_year": rent - discount,
            })

        return {
            "type": "ir.actions.act_window",
            "res_model": "contract.wizard",
            "res_id": self.id,
            "view_mode": "form",
            "target": "new",
        }

    def action_clear_discount(self):
        self.write({
            "discount_applied": False,
            "total_rent_year": self.property_id.price_yearly,

        })

        return {
            "type": "ir.actions.act_window",
            "res_model": "contract.wizard",
            "res_id": self.id,
            "view_mode": "form",
            "target": "new",
        }

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
            "price_unit": self.contract_value,
            "tax_ids": self.tax_ids.ids if self.instalment_tax else False,
            # "account_id": self.property_id.property_project_id.invoice_creation_id.id,
        }
        service_invoice_line.append((0, 0, full_payment_record))
        if self.is_any_deposit:
            deposit_record = {
                "product_id": self.deposit_item_id.id,
                "name": "Deposit of " + self.property_id.name,
                "quantity": 1,
                "price_unit": self.deposit_amount,
                "tax_ids": self.tax_ids.ids if self.deposit_tax else False,
                # "account_id": self.property_id.property_project_id.account_security_deposit_id.id,
            }
            service_invoice_line.append((0, 0, deposit_record))
        if self.is_any_maintenance and self.maintenance_service_invoice == 'merge':
            service_invoice_line.append((0, 0, {
                "product_id": self.maintenance_item_id.id,
                "name": "Maintenance of " + self.property_id.name,
                "quantity": 1,
                "price_unit": (
                    self.total_maintenance
                    if self.maintenance_rent_type == "once"
                    else self.total_maintenance * self.duration_id.month
                ),
                # "account_id": self.property_id.property_project_id.invoice_creation_id.id,
            }))
        if self.property_id.is_extra_service and self.extra_service_invoice == 'merge':
            for line in self.property_id.extra_service_ids:
                if line.service_type == "once":
                    desc = "Service Type : Once" + "\n" "Service : " + str(
                        line.service_id.name
                    )
                if line.service_type == "monthly":
                    desc = "Service Type : Recurring" + "\n" "Service : " + str(
                        line.service_id.name
                    )
                service_invoice_line.append((0, 0, {
                    "product_id": line.service_id.id,
                    "name": desc,
                    "quantity": (
                        1 if line.service_type == "once" else self.duration_id.month
                    ),
                    "price_unit": line.price,
                    "tax_ids": self.tax_ids.ids if self.service_tax else False,
                    # "account_id": self.property_id.property_project_id.invoice_creation_id.id,
                }))
        if self.is_added_services and self.added_service_ids and self.added_service_invoice == 'merge':
            for line in self.added_service_ids:
                service_invoice_line.append((0, 0, {
                    "product_id": line.service_id.id,
                    "name": line.service_id.name,
                    "quantity": 1,
                    "price_unit": line.price,
                    # "account_id": self.property_id.property_project_id.invoice_creation_id.id,
                }))
        if self.is_added_services and self.added_service_ids and self.added_service_invoice == 'separate':
            for line in self.added_service_ids:
                service_invoice_line.append((0, 0, {
                    "product_id": line.service_id.id,
                    "name": line.service_id.name,
                    "quantity": 1,
                    "price_unit": line.price,
                    # "account_id": self.contract_id.property_project_id.invoice_creation_id.id,
                }))
        invoice_id = self.env["account.move"].sudo().create({
            "partner_id": self.customer_id.id,
            "move_type": "out_invoice",
            "invoice_date": contract_id.invoice_start_date,
            "invoice_line_ids": service_invoice_line,
            'tenancy_id': contract_id.id
        })
        # if invoice_post_type == "automatically":
        #     invoice_id.action_post()
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
        if self.is_any_maintenance and self.maintenance_service_invoice == 'separate':
            self._process_separate_invoices(
                contract_id=contract_id, maintenance=True)
        if self.is_extra_service and self.extra_service_invoice == 'separate':
            self._process_separate_invoices(
                contract_id=contract_id, utility=True)
        contract_id.action_send_active_contract()
        
    
    def _process_separate_added_services(self, contract_id):
        invoice_lines = []
        for data in contract_id.added_service_ids:
            invoice_lines.append((0, 0, {"product_id": data.service_id.id,
                                         "name": data.service_id.name,
                                         "quantity": 1,
                                         "price_unit": data.price}))
        if invoice_lines:
            invoice_id = self.env['account.move'].sudo().create({
                "partner_id": self.customer_id.id,
                "move_type": "out_invoice",
                "invoice_date": contract_id.invoice_start_date,
                "invoice_line_ids": invoice_lines,
                "tenancy_id": contract_id.id,
                # "account_id": self.property_id.property_project_id.invoice_creation_id.id,
            })
            contract_id.added_service_ids.write({'invoice_id': invoice_id.id})


    def _process_separate_invoices(self, contract_id, maintenance=None, utility=None):
        """Process Utility and Maintenance Separate Invoices"""
        if self.rent_unit == 'Day':
            qty = (self.end_date - self.start_date).days + 1
        else:
            qty = self.duration_id.month
        if maintenance:
            maintenance_invoice_id = self.env['account.move'].create({
                "partner_id": self.customer_id.id,
                "move_type": "out_invoice",
                "invoice_date": contract_id.invoice_start_date,
                "tenancy_id": contract_id.id,
                "invoice_line_ids": [(0, 0, {
                    "product_id": self.maintenance_item_id.id,
                    "name": "Maintenance of " + self.property_id.name,
                    "quantity": 1 if self.property_id.maintenance_rent_type == 'once' else qty,
                    "price_unit": self.total_maintenance,
                    # "account_id": self.property_id.property_project_id.invoice_creation_id.id,
                })],
            })
            self.env['rent.invoice'].create({
                "tenancy_id": contract_id.id,
                "type": "maintenance",
                "invoice_date": contract_id.invoice_start_date,
                "amount": maintenance_invoice_id.amount_total,
                "description": "Maintenance of " + self.property_id.name,
                "rent_invoice_id": maintenance_invoice_id.id})
        if utility:
            service_invoice_lines = []
            for line in self.property_id.extra_service_ids:
                service_type = 'Once' if line.service_type == 'once' else "Recurring"
                service_invoice_lines.append((0, 0, {
                    "product_id": line.service_id.id,
                    "name": f"Service Type : {service_type} - {line.service_id.name}",
                    "quantity": 1 if line.service_type == 'once' else qty,
                    "price_unit": line.price,
                    "tax_ids": self.tax_ids.ids if self.service_tax else False,
                    # "account_id": self.property_id.property_project_id.invoice_creation_id.id,
                }))
            service_invoice_id = self.env['account.move'].create({
                "partner_id": self.customer_id.id,
                "move_type": "out_invoice",
                "invoice_date": contract_id.invoice_start_date,
                "tenancy_id": contract_id.id,
                "invoice_line_ids": service_invoice_lines,
            })
            self.env['rent.invoice'].create({
                "tenancy_id": contract_id.id,
                "type": "other",
                "invoice_date": contract_id.invoice_start_date,
                "amount": service_invoice_id.amount_total,
                "description": "Utility Services",
                "rent_invoice_id": service_invoice_id.id})
            
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
            # "account_id": self.property_id.property_project_id.invoice_creation_id.id,
        })]
        if self.is_any_deposit:
            invoice_lines.append((0, 0, {
                "product_id": self.deposit_item_id.id,
                "name": "Deposit of " + self.property_id.name,
                "quantity": 1,
                "price_unit": self.deposit_amount,
                "tax_ids": self.tax_ids.ids if self.deposit_tax else False,
                # "account_id": self.property_id.property_project_id.account_security_deposit_id.id,
            }))
        if self.is_any_maintenance and self.maintenance_service_invoice == 'merge':
            invoice_lines.append((0, 0, {
                "product_id": self.maintenance_item_id.id,
                "name": "Maintenance of " + self.property_id.name,
                "quantity": 1 if self.property_id.maintenance_rent_type == 'once' else (
                        delta.days + 1),
                "price_unit": self.total_maintenance,
                # "account_id": self.property_id.property_project_id.invoice_creation_id.id,
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
                    # "account_id": self.property_id.property_project_id.invoice_creation_id.id,

                }))
        if self.is_added_services and self.added_service_ids and self.added_service_invoice == 'merge':
            for line in self.added_service_ids:
                invoice_lines.append((0, 0, {
                    "product_id": line.service_id.id,
                    "name": line.service_id.name,
                    "quantity": 1,
                    "price_unit": line.price,
                    "tax_ids": False,
                    # "account_id": self.property_id.property_project_id.invoice_creation_id.id,
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


    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        contract_id = self.env.context.get('active_contract_id')
        active_model = self.env.context.get("active_model")
        active_id = self.env.context.get("active_id")
        # contract_id = contract_id or active_id
        ejari_template = self.env.ref(
            'ribs_real_estate.product_template_ejari_registration'
        )
        registration_template = self.env.ref(
            'ribs_real_estate.product_template_registration_charges_ejari'
        )

        ejari_product = ejari_template.product_variant_id
        registration_product = registration_template.product_variant_id
        residential_product = self.env.ref(
            "rental_management.property_product_1",
            raise_if_not_found=False,
        )
        commercial_product = self.env.ref(
            "rental_management.property_product_5",
            raise_if_not_found=False,
        )

        _logger.info("contracttt", contract_id)
        if contract_id:
            tenancy = self.env["tenancy.details"].browse(contract_id)

            res.update({
                "deposit_amount": 0.0,
                "is_any_deposit": False,
                "tax_ids": [(6, 0, tenancy.property_id.tax_id.ids)],
                "tax_id": tenancy.property_id.tax_id[:1].id if tenancy.property_id.tax_id else False,

                # Discount defaults
                "discount_applied": False,
                "discount_type": "percent",
                "discount_value": 0.0,
            })
            # Always prefill from the contract being renewed first, so
            # Rent/Contract Value are never blank/0 just because no
            # rent-increase request (contract.update.register) has been
            # sent/approved yet for this particular contract.
            res['property_id'] = tenancy.property_id.id
            res['customer_id'] = tenancy.tenancy_id.id
            res['payment_term'] = tenancy.payment_term
            res['duration_id'] = tenancy.duration_id.id
            res['rent_unit'] = 'Month'
            res['duration_type'] = 'by_duration'
            res['start_date'] = (
                tenancy.end_date + timedelta(days=1)
                if tenancy.end_date else tenancy.start_date
            )
            res['total_rent_year'] = tenancy.total_rent_year
            res['total_rent'] = (tenancy.total_rent_year / 12) if tenancy.total_rent_year else 0.0
            res['is_by_date'] = tenancy.is_by_date if tenancy.is_by_date else False
            res['is_from_existing_contract'] = True

            new_contract = self.env['contract.update.register'].search(
                [('contract_id', '=', contract_id)],
                order='id desc',
                limit=1
            )
            today = date.today()
            days_in_month = calendar.monthrange(today.year, today.month)[1]

            if new_contract:
                # A rent-increase request has been prepared - its proposed
                # terms take precedence over the contract's current ones.
                res['duration_type'] = 'by_duration'
                res['rent_unit'] = 'Month'
                res['start_date'] = new_contract.from_date
                res['duration_end_date'] = new_contract.to_date
                res['total_rent'] = new_contract.new_rent_monthly
                res['duration_id'] = new_contract.duration_id.id
                # res['total_rent'] = new_contract.new_rent_monthly / days_in_month if days_in_month else 0
                res['total_rent_year'] = new_contract.new_rent_annually
                res['is_by_date'] = new_contract.contract_id.is_by_date
                res['is_from_existing_contract'] = True
                res['payment_term'] = new_contract.contract_id.payment_term

        res['is_added_services'] = True
        res['added_service_ids'] = [
            Command.create({
                'service_id': ejari_product.id,
                'price': ejari_product.list_price,
            }),
            # Command.create({
            #     'service_id': registration_product.id,
            #     'price': registration_product.list_price,
            # }),
        ]

        if 'instalment_tax' in fields_list:
            res['instalment_tax'] = True
        terms_html_obj = self.env['default.terms.conditions'].search([], limit=1)
        if terms_html_obj.terms_html:
            res['term_condition'] = terms_html_obj.terms_html
        if active_model == "property.details":
            property_id = self.env["property.details"].browse(active_id)
            if property_id.type == "residential":
                res["installment_item_id"] = residential_product.id if residential_product else False
            else:
                res["installment_item_id"] = commercial_product.id if commercial_product else False


            #For Discount
            res.update({
                "total_rent_year": property_id.price_yearly,
                "deposit_amount": property_id.deposit_amount or 0.0,

                "discount_applied": False,
                "discount_type": "percent",
                "discount_value": 0.0,
                "tax_id": property_id.tax_id.id if property_id.tax_id else False,
            })

            res['tax_ids'] = [(6, 0, property_id.tax_id.ids)]
            res['total_rent_year'] = property_id.price_yearly
            res['contract_value'] = property_id.price_yearly * 1
            if property_id.deposit_amount:
                res['deposit_amount'] = property_id.deposit_amount
                res['is_any_deposit'] = bool(res['deposit_amount'])
        return res

    def contract_action(self):
        """Process rent contract"""
        existing_contract_id = self.env.context.get('active_contract_id')
        active_model = self.env.context.get("active_model")
        active_id = self.env.context.get("active_id")
        self.customer_id.user_type = "customer"

        print(existing_contract_id,'existing_contract_id')
        param = self.env['ir.config_parameter'].sudo().get_str(
            'ribs_real_estate.authorized_users_ids', ''
        )
        authorized_ids = [int(x) for x in param.split(',') if x]
        # if float_compare(self.total_rent_year or 0.0, 0.0, precision_digits=2) <= 0:
        #     raise ValidationError("Total Rent must be greater than zero.")
        if self.grace_period_start_date and self.grace_period_end_date:
            if self.grace_period_end_date < self.grace_period_start_date:
                raise ValidationError("Grace End Date should be greater than Grace Start Date")

        if existing_contract_id:
            print(existing_contract_id,type(existing_contract_id),'existing_contract_id')
            tenancy_id = self.env["tenancy.details"].browse(existing_contract_id)
            tenancy_id.contract_type = "close_contract"
            tenancy_id.close_contract_state = True
        if self.is_contract_extend and self.is_rent_increment:
            self.action_process_rent_increment()

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
        if self.property_id.is_extra_service:
            for data in self.property_id.extra_service_ids:
                service_line.append((0, 0, {
                    "service_id": data.service_id.id,
                    "service_type": data.service_type,
                    "from_contract": True,
                    "price": data.price,
                }))
        if service_line:
            record["extra_services_ids"] = service_line
            record['extra_service_invoice'] = self.extra_service_invoice
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
            contract_id.total_rent_year = self.total_rent_year
            contract_id.grace_period_value = self.grace_period_value
            contract_id.grace_period_unit = self.grace_period_unit
            contract_id.commercial_size = self.commercial_size
            contract_id.commercial_rate = self.commercial_rate
            # grace_period_start_date/end_date are computed+stored on tenancy.details
            # itself from start_date + grace_period_value/unit - no need to copy here.
            if self.is_by_date:
                contract_id.write({"end_date": self.duration_end_date})
            # if self.total_rent_year != self.property_id.price_yearly and self.env.user.id not in authorized_ids:
            #     contract_id.contract_type = "waiting"
            contract_id._onchange_agreement_template_id()
            if contract_id.is_any_broker:
                contract_id.action_broker_invoice()
            # Full Payment Invoice
            if self.duration_type == 'by_duration':
                self.action_create_full_payment_invoice(
                    contract_id=contract_id)
            if self.duration_type == 'by_date':
                self._process_by_dated_full_payment(contract_id=contract_id)
            self.customer_id.is_tenancy = True
            self.property_id.write({"stage": "on_lease"})
            if existing_contract_id:
                old_tenancy_id = self.env["tenancy.details"].browse(existing_contract_id)
                old_tenancy_id.extended = True
                old_tenancy_id.extend_ref = contract_id.tenancy_seq
                old_tenancy_id.new_contract_id = contract_id.id
                contract_id.is_extended = True
                contract_id.extend_from = old_tenancy_id.tenancy_seq
            contract_id.contract_payment_pdc()
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
            if self.is_by_date:
                contract_id.write({"end_date": self.duration_end_date})
            contract_id.total_rent_year = self.total_rent_year
            contract_id.grace_period_value = self.grace_period_value
            contract_id.grace_period_unit = self.grace_period_unit
            contract_id.commercial_size = self.commercial_size
            contract_id.commercial_rate = self.commercial_rate
            # grace_period_start_date/end_date are computed+stored on tenancy.details
            # itself from start_date + grace_period_value/unit - no need to copy here.
            # if self.total_rent_year != self.property_id.price_yearly and self.env.user.id not in authorized_ids:
            #     contract_id.contract_type = "waiting"
            contract_id._onchange_agreement_template_id()
            self.customer_id.is_tenancy = True
            self.property_id.write({"stage": "on_lease"})
            if existing_contract_id:
                old_tenancy_id = self.env["tenancy.details"].browse(existing_contract_id)
                old_tenancy_id.extended = True
                old_tenancy_id.extend_ref = contract_id.tenancy_seq
                old_tenancy_id.new_contract_id = contract_id.id
                contract_id.is_extended = True
                contract_id.extend_from = old_tenancy_id.tenancy_seq
            contract_id.contract_payment_pdc()
            return {
                "type": "ir.actions.act_window",
                "name": "Contract",
                "res_model": "tenancy.details",
                "res_id": contract_id.id,
                "view_mode": "form,list",
                "target": "current",
            }


    def _get_invoice_qty_and_price(self, payment_term, start_date, end_date, total_amount):
        """
        Returns (invoice_qty, unit_price)
        """
        # Total contract duration
        total_months = (
            (end_date.year - start_date.year) * 12
            + (end_date.month - start_date.month)
        )
    
        total_days = (end_date - start_date).days + 1
    
        if payment_term == 'daily':
            invoice_qty = total_days
            unit_price = total_amount / invoice_qty
    
        elif payment_term == 'monthly':
            invoice_qty = total_months
            unit_price = total_amount / invoice_qty
    
        elif payment_term == 'every_2_months':
            if total_months % 2 != 0:
                raise ValidationError(
                    "The selected payment term does not fully align with the contract duration."
                )
            invoice_qty = total_months // 2
            unit_price = total_amount / invoice_qty
    
        elif payment_term == 'every_4_months':
            raise ValidationError(
                "The selected payment term does not fully align with the contract duration."
            )
    
        elif payment_term == 'quarterly':
            raise ValidationError(
                "The selected payment term does not fully align with the contract duration."
            )
    
        elif payment_term == 'half_year':
            invoice_qty = 1
            unit_price = total_amount
    
        elif payment_term == 'yearly':
            if total_months < 12:
                raise ValidationError(
                    "Yearly payment term requires at least 12 months duration."
                )
            invoice_qty = total_months // 12
            unit_price = total_amount / invoice_qty
    
        elif payment_term == 'full_payment':
            invoice_qty = 1
            unit_price = total_amount
    
        else:
            raise ValidationError("Invalid payment term selected.")
    
        return invoice_qty, unit_price


    @api.onchange('customer_id')
    def _onchange_customer_phone(self):
        """Auto-fill phone from selected customer."""
        if self.customer_id:
            self.customer_phone = self.customer_id.phone or False

    @api.onchange('total_rent_year')
    def _onchange_total_rent(self):
        self.total_rent = self.total_rent_year / 12

    @api.depends('duration_id', 'total_rent_year')
    def _compute_contract_value(self):
        for record in self:
            months = record.duration_id.month or 0
            total_rent_year = record.total_rent_year or 0
            if record.payment_term == 'daily' or record.is_by_date:
                current_year = fields.Date.today().year
                days = 365
                if calendar.isleap(current_year):
                    days = 366
                record.contract_value = (total_rent_year / days)* months
            else:
                record.contract_value = total_rent_year * (months / 12)

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
                elif rec.rent_unit == "Year":
                    end_date = (rec.start_date
                                + relativedelta(years=rec.duration_id.month)
                                - relativedelta(days=1))
                else:
                    if rec.payment_term == "year":
                        end_date = (rec.start_date
                                    + relativedelta(months=rec.duration_id.month)
                                    - relativedelta(days=1))
                    elif rec.payment_term == "daily":
                        end_date = (rec.start_date
                                    + relativedelta(days=rec.duration_id.month)
                                    - relativedelta(days=1))
                    else:
                        end_date = (rec.start_date
                                    + relativedelta(months=rec.duration_id.month)
                                    - relativedelta(days=1))
            if rec.duration_type == "by_date":
                end_date = rec.duration_end_date
            rec.end_date = end_date

    @api.onchange('chq_due_date')
    def _onchange_chq_due_date(self):
        if self.chq_due_date and self.chq_due_date < fields.Date.today():
            raise ValidationError("Due date cannot be in the past.")

    # @api.onchange('total_rent')
    # def _onchange_total_rent(self):
    #     if self.total_rent:
    #         self.total_rent_year = self.total_rent * 12

    # @api.onchange('grace_period_start_date')
    # def onchange_grace_period_start_date(self):
    #     print('callinggg')
    #     print('callinggg', self.grace_period_start_date,date.today())
    #     if self.grace_period_start_date and self.grace_period_start_date < date.today():
    #         self.grace_period_start_date = False
    #         raise ValidationError(_("Grace period start date cannot be in the past."))
    
    # @api.onchange('start_date')
    # def onchange_start_date(self):
    #     if self.start_date and self.start_date < date.today():
    #         self.start_date = None
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

    @api.onchange('is_by_date')
    def _onchange_is_by_date(self):
        if self.is_from_existing_contract:
            self.is_from_existing_contract = False
            return
        if self.is_by_date:
            self.payment_term = 'daily'
        else:
            self.payment_term = None

    @api.onchange('start_date', 'end_date')
    def _onchange_end_date(self):
        if self.is_by_date and self.start_date and self.end_date:
            self.days = (self.end_date - self.start_date).days + 1
            self.action_generate_duration()
            self._calculate_contract_value()

    @api.onchange('start_date', 'days')
    def _onchange_days(self):
        if self.is_by_date and self.start_date and self.days:
            self.end_date = self.start_date + timedelta(days=self.days - 1)
            self.action_generate_duration()
            self._calculate_contract_value()

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
