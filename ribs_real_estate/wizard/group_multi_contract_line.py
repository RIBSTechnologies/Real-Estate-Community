from odoo import models, fields, api
import calendar

class GroupMultiContractLine(models.Model):
    _name = "group.multi.contract.line"
    _description = "Multi Contract Unit Line"

    contract_id = fields.Many2one(
        "group.multi.contracts",
        ondelete="cascade"
    )


    property_id = fields.Many2one(
        "property.details",
        store=True
    )

    total_rent_year = fields.Float(string='Initial Rent/Year')

    deposit_amount = fields.Float()

    tax_id = fields.Many2one("account.tax")

    discount_applied = fields.Boolean()

    discount_type = fields.Selection([
        ("percent", "Percentage"),
        ("fixed", "Fixed Amount")
    ])

    discount_value = fields.Float()

    discount_amount = fields.Float(
        compute="_compute_total",
        store=True
    )

    tax_amount = fields.Float(
        compute="_compute_total",
        store=True
    )

    total = fields.Float(
        compute="_compute_total",
        store=True
    )
    selected = fields.Boolean(string="Select")
    amount_based_on_duration = fields.Float(
        string="Amount Based on Duration",
        compute="_compute_total",
        store=True,
    )

    before_vat = fields.Float(
        string="Before VAT",
        compute="_compute_total",
        store=True,
    )

    def _compute_total(self):
        for line in self:

            yearly_rent = line.total_rent_year or 0.0
            amount_based_on_duration = yearly_rent

            contract = line.contract_id

            if contract:
                current_year = fields.Date.today().year
                days_in_year = 366 if calendar.isleap(current_year) else 365

                if contract.payment_term == "daily":
                    months = contract.duration_id.month or 0
                    amount_based_on_duration = (
                        yearly_rent / days_in_year
                    ) * months

                elif contract.is_by_date:
                    if contract.start_date and contract.end_date:
                        total_days = (
                            contract.end_date - contract.start_date
                        ).days + 1

                        days_in_year = (
                            366 if calendar.isleap(contract.start_date.year)
                            else 365
                        )

                        amount_based_on_duration = (
                            yearly_rent / days_in_year
                        ) * total_days
                    else:
                        amount_based_on_duration = 0.0

                else:
                    months = contract.duration_id.month or 0
                    amount_based_on_duration = (
                        yearly_rent * (months / 12.0)
                    )

            # Store only for reference
            line.amount_based_on_duration = amount_based_on_duration

            # Financial calculations use yearly_rent only
            base_amount = yearly_rent

            if line.discount_applied:
                if line.discount_type == "percent":
                    discount = (
                        base_amount * line.discount_value / 100.0
                    )
                else:
                    discount = line.discount_value
            else:
                discount = 0.0

            before_vat = base_amount - discount

            tax_amount = 0.0
            if line.tax_id:
                tax_amount = (
                    before_vat * line.tax_id.amount / 100.0
                )

            line.discount_amount = discount
            line.before_vat = before_vat
            line.tax_amount = tax_amount
            line.total = before_vat + tax_amount

    @api.onchange("tax_id")
    def _onchange_tax_id(self):
        if self.contract_id:
            taxes = self.contract_id.unit_line_ids.mapped("tax_id")
            self.contract_id.tax_ids = [(5, 0, 0)]
            self.contract_id.tax_ids = [(6, 0, taxes.ids)]
            self.contract_id.instalment_tax = bool(taxes)
