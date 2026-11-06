# -*- coding: utf-8 -*-
import datetime
from dateutil.relativedelta import relativedelta
from odoo import fields, api, models, _
from odoo.exceptions import ValidationError, UserError
import traceback
import base64
import calendar


class ActiveContract(models.Model):
    _inherit = 'active.contract'

    def action_monthly_month_active(self):
        """Monthly payment term active contract"""
        invoice_post_type = self.env["ir.config_parameter"].sudo().get_str("rental_management.invoice_post_type", False)

        invoice_date = self.contract_id.invoice_start_date + relativedelta(months=1)

        if self.contract_id.is_maintenance_service and self.contract_id.maintenance_service_invoice == 'separate':
            self._process_separate_invoices(days=1, maintenance=True)

        if self.contract_id.is_extra_service and self.contract_id.extra_service_invoice == 'separate':
            self._process_separate_invoices(days=1, utility=True)

        for i in range(self.contract_id.month):
            invoice_lines = []  
            service_amount = 0.0  

            if self.contract_id.unit_ids:
                print('yesss')
                invoice_lines += self._prepare_unit_invoice_lines(
                    period="monthly",
                )
            else:
                print('elseee')
                invoice_lines.append((0, 0, self._prepare_invoice_line(type='installment')))

            if self.contract_id.is_any_deposit and i == 0:
                invoice_lines.append((0, 0, self._prepare_invoice_line(type='deposit')))

            if self.contract_id.is_maintenance_service and self.contract_id.maintenance_service_invoice == 'merge':
                invoice_lines.append((0, 0, self._prepare_invoice_line(type='maintenance')))

            if self.contract_id.is_extra_service and self.contract_id.extra_service_invoice == 'merge':
                invoice_lines += self._prepare_service_invoice_line(qty=1)
                service_amount = sum(self.contract_id.extra_services_ids.mapped('price'))

            if self.contract_id.is_added_services and self.contract_id.added_service_ids and self.contract_id.added_service_invoice == 'merge':
                for line in self.contract_id.added_service_ids:
                    invoice_lines.append((0, 0, {
                        "product_id": line.service_id.id,
                        "name": line.service_id.name,
                        "quantity": 1,
                        "price_unit": line.price
                    }))

            if (
                self.contract_id.is_added_services
                and self.contract_id.added_service_ids
                and self.contract_id.added_service_invoice == "separate"
                and i == 0):
                for line in self.contract_id.added_service_ids:
                    invoice_lines.append((0, 0, {
                        "product_id": line.service_id.id,
                        "name": line.service_id.name,
                        "quantity": 1,
                        "price_unit": line.price,
                        # "account_id": self.contract_id.property_project_id.invoice_creation_id.id,
                    }))
                # self._process_separate_added_services()

            invoice_id = self.env["account.move"].sudo().create({
                "partner_id": self.contract_id.tenancy_id.id,
                "move_type": "out_invoice",
                "invoice_date": self.contract_id.invoice_start_date,
                "invoice_line_ids": invoice_lines,
                "tenancy_id": self.contract_id.id,
                "invoice_date_due":invoice_date,
            })

            # if invoice_post_type == "automatically":
            # invoice_id.action_post()

            description = ""
            if i == 0:
                description = "First Rent" + (" + Deposit" if self.contract_id.is_any_deposit else "")
            else:
                description = f"Installment of {self.contract_id.property_id.name}"

            self.env["rent.invoice"].create({
                "tenancy_id": self.contract_id.id,
                "type": "rent",
                "invoice_date": invoice_date,
                "description": description,
                "rent_invoice_id": invoice_id.id,
                "amount": invoice_id.amount_total,
                "rent_amount": self.contract_id.total_rent,
                "service_amount": service_amount,
            })

            invoice_date = invoice_date + relativedelta(months=1)


    def action_quarterly_month_active(self):
        """Quarterly payment term active contract"""
        invoice_post_type = self.env["ir.config_parameter"].sudo().get_str(
            "rental_management.invoice_post_type", False
        )
        service_amount = 0.0
        active_id = self.env.context.get("active_id")
        tenancy_id = self.env["tenancy.details"].browse(active_id)

        yearly_rent = tenancy_id.total_rent_year or 0.0
        quarterly_rent = yearly_rent / 4 

        full_quarter = self.contract_id.month // 3
        reminder_quarter = self.contract_id.month % 3
        invoice_date = self.contract_id.invoice_start_date + relativedelta(months=3)

        if self.contract_id.is_maintenance_service and self.contract_id.maintenance_service_invoice == "separate":
            pass
        if self.contract_id.is_extra_service and self.contract_id.extra_service_invoice == "separate":
            pass

        if full_quarter >= 1:
            for i in range(full_quarter):
                invoice_lines = []

                invoice_name = (
                    "First Quarter Invoice of " + tenancy_id.property_id.name
                    if i == 0
                    else "Installment of " + tenancy_id.property_id.name
                )
                if tenancy_id.unit_ids:
                    invoice_lines += self._prepare_unit_invoice_lines(tenancy_id,period="quarterly")
                else:
                    record = {
                        "product_id": tenancy_id.installment_item_id.id,
                        "name": invoice_name,
                        "quantity": 1,
                        "price_unit": quarterly_rent,
                        "tax_ids": (
                            tenancy_id.tax_ids.ids
                            if tenancy_id.instalment_tax
                            else False
                        ),
                        # "account_id": self.contract_id.property_project_id.invoice_creation_id.id,
                    }
                    invoice_lines.append((0, 0, record))

                if i == 0 and tenancy_id.is_any_deposit:
                    invoice_lines.append(
                        (0, 0, self._prepare_invoice_line(type="deposit"))
                    )

                if tenancy_id.is_maintenance_service and self.contract_id.maintenance_service_invoice == "merge":
                    invoice_lines.append(
                        (0, 0, {
                            "product_id": tenancy_id.maintenance_item_id.id,
                            "name": "Maintenance of " + tenancy_id.property_id.name,
                            "quantity": 3,
                            "price_unit": tenancy_id.total_maintenance,
                            "tax_ids": (
                                tenancy_id.tax_ids.ids
                                if tenancy_id.instalment_tax
                                else False
                            ),
                            # "account_id": self.contract_id.property_project_id.invoice_creation_id.id,
                        })
                    )

                if tenancy_id.is_extra_service and self.contract_id.extra_service_invoice == "merge":
                    for line in tenancy_id.extra_services_ids:
                        if line.service_type == "once":
                            service_amount += line.price
                            qty = 1
                            price_unit = line.price
                        else:  # monthly
                            service_amount += line.price * 3
                            qty = 3
                            price_unit = line.price

                        service_invoice_record = {
                            "product_id": line.service_id.id,
                            "name": f"Service Type: {'Once' if line.service_type == 'once' else 'Recurring'}\nService: {line.service_id.name}",
                            "quantity": qty,
                            "price_unit": price_unit,
                            "tax_ids": (
                                tenancy_id.tax_ids.ids
                                if tenancy_id.service_tax
                                else False
                            ),
                            # "account_id": self.contract_id.property_project_id.invoice_creation_id.id,
                        }
                        invoice_lines.append((0, 0, service_invoice_record))

                if (
                    self.contract_id.is_added_services
                    and self.contract_id.added_service_ids
                    and self.contract_id.added_service_invoice == "merge"
                ):
                    for line in self.contract_id.added_service_ids:
                        invoice_lines.append((0, 0, {
                            "product_id": line.service_id.id,
                            "name": line.service_id.name,
                            "quantity": 1,
                            "price_unit": line.price,
                            # "account_id": self.contract_id.property_project_id.invoice_creation_id.id,
                        }))

                if (
                    self.contract_id.is_added_services
                    and self.contract_id.added_service_ids
                    and self.contract_id.added_service_invoice == "separate"
                    and i == 0):
                    for line in self.contract_id.added_service_ids:
                        invoice_lines.append((0, 0, {
                            "product_id": line.service_id.id,
                            "name": line.service_id.name,
                            "quantity": 1,
                            "price_unit": line.price,
                            # "account_id": self.contract_id.property_project_id.invoice_creation_id.id,
                        }))

                data = {
                    "partner_id": tenancy_id.tenancy_id.id,
                    "move_type": "out_invoice",
                    "invoice_date": tenancy_id.invoice_start_date,
                    "invoice_line_ids": invoice_lines,
                    "invoice_date_due":invoice_date,
                }
                invoice_id = self.env["account.move"].sudo().create(data)
                invoice_id.tenancy_id = tenancy_id.id

                # if invoice_post_type == "automatically":
                # invoice_id.action_post()

                self.env["rent.invoice"].create({
                    "tenancy_id": tenancy_id.id,
                    "type": "rent",
                    "invoice_date": invoice_date,
                    "description": invoice_name,
                    "rent_invoice_id": invoice_id.id,
                    "amount": invoice_id.amount_total,
                    "rent_amount": quarterly_rent,
                    "service_amount": service_amount,
                })

                invoice_date += relativedelta(months=3)

        if reminder_quarter > 0:
            invoice_lines = []
            invoice_name = "Installment of " + tenancy_id.property_id.name
            reminder_rent = (yearly_rent / 12) * reminder_quarter

            if tenancy_id.unit_ids:
                invoice_lines += self._prepare_unit_invoice_lines(
                    tenancy_id,
                    period="custom",
                    months=reminder_quarter
                )
            else:
                record = {
                    "product_id": tenancy_id.installment_item_id.id,
                    "name": invoice_name,
                    "quantity": 1,
                    "price_unit": reminder_rent,
                    "tax_ids": (
                        tenancy_id.tax_ids.ids
                        if tenancy_id.instalment_tax
                        else False
                    ),
                    # "account_id": self.contract_id.property_project_id.invoice_creation_id.id,
                }
                invoice_lines.append((0, 0, record))

            data = {
                "partner_id": tenancy_id.tenancy_id.id,
                "move_type": "out_invoice",
                "invoice_date": tenancy_id.invoice_start_date,
                "invoice_line_ids": invoice_lines,
                "invoice_date_due": invoice_date,
            }
            reminder_invoice = self.env["account.move"].sudo().create(data)
            reminder_invoice.tenancy_id = tenancy_id.id

            # if invoice_post_type == "automatically":
            # reminder_invoice.action_post()

            self.env["rent.invoice"].create({
                "tenancy_id": tenancy_id.id,
                "type": "rent",
                "invoice_date": invoice_date,
                "description": invoice_name,
                "rent_invoice_id": reminder_invoice.id,
                "amount":reminder_rent,
                "rent_amount":reminder_rent,
                "remain": reminder_quarter,
            })


    def action_half_year_month_active(self):
        """Half-yearly payment term active contract"""
        invoice_post_type = self.env["ir.config_parameter"].sudo().get_str(
            "rental_management.invoice_post_type", False
        )
        service_amount = 0.0
        invoice_lines = []
        full_half_years = self.contract_id.month // 6
        remaining_months = self.contract_id.month % 6
        next_invoice_date = self.contract_id.invoice_start_date + relativedelta(months=6)

        if full_half_years >= 1:
            for installment_index in range(full_half_years):
                invoice_lines = []

                invoice_name = (
                    "First Half-Year Invoice of " + self.contract_id.property_id.name
                    if installment_index == 0
                    else "Installment of " + self.contract_id.property_id.name
                )

                # --- Rent Line (use yearly rent / 2 for half-yearly) ---
                rent_invoice_line = {
                    "product_id": self.contract_id.installment_item_id.id,
                    "name": invoice_name,
                    "quantity": 1,
                    "price_unit": self.contract_id.total_rent_year / 2,
                    "tax_ids": (
                        self.contract_id.tax_ids.ids
                        if self.contract_id.instalment_tax
                        else False
                    ),
                    # "account_id": self.contract_id.property_project_id.invoice_creation_id.id,
                }
                invoice_lines.append((0, 0, rent_invoice_line))

                # --- Deposit line (only first invoice) ---
                if installment_index == 0 and self.contract_id.is_any_deposit:
                    invoice_lines.append(
                        (0, 0, self._prepare_invoice_line(type="deposit"))
                    )

                # --- Maintenance and Extra Services (merged) ---
                service_amount += self._append_merged_service_lines(
                    self.contract_id, invoice_lines
                )

                # --- Added Services (merge) ---
                if (
                    self.contract_id.is_added_services
                    and self.contract_id.added_service_ids
                    and self.contract_id.added_service_invoice == "merge"
                ):
                    for line in self.contract_id.added_service_ids:
                        invoice_lines.append(
                            (0, 0, {
                                "product_id": line.service_id.id,
                                "name": line.service_id.name,
                                "quantity": 1,
                                "price_unit": line.price,
                                # "account_id": self.contract_id.property_project_id.invoice_creation_id.id,
                            })
                        )

                # --- Added Services (separate, but added to first invoice line) ---
                if (
                    self.contract_id.is_added_services
                    and self.contract_id.added_service_ids
                    and self.contract_id.added_service_invoice == "separate"
                    and installment_index == 0
                ):
                    for line in self.contract_id.added_service_ids:
                        invoice_lines.append(
                            (0, 0, {
                                "product_id": line.service_id.id,
                                "name": f"Added Service: {line.service_id.name}",
                                "quantity": 1,
                                "price_unit": line.price,
                                # "account_id": self.contract_id.property_project_id.invoice_creation_id.id,
                            })
                        )

                # --- Create the invoice ---
                invoice_vals = {
                    "partner_id": self.contract_id.tenancy_id.id,
                    "move_type": "out_invoice",
                    "invoice_date": self.contract_id.invoice_start_date,
                    "invoice_line_ids": invoice_lines,
                    "invoice_date_due": next_invoice_date,
                }
                invoice = self.env["account.move"].sudo().create(invoice_vals)
                invoice.tenancy_id = self.contract_id.id
                # invoice.action_post()

                # --- Rent Invoice Record ---
                self.env["rent.invoice"].create({
                    "tenancy_id": self.contract_id.id,
                    "type": "rent",
                    "invoice_date": self.contract_id.invoice_start_date,
                    "description": (
                        "First Half-Year Rent"
                        + (" + Deposit" if installment_index == 0 and self.contract_id.is_any_deposit else "")
                        if installment_index == 0
                        else "Installment of " + self.contract_id.property_id.name
                    ),
                    "rent_invoice_id": invoice.id,
                    "amount": invoice.amount_total,
                    "rent_amount": self.contract_id.total_rent_year / 2,
                    "service_amount": service_amount,
                })

                next_invoice_date += relativedelta(months=6)

        # --- Handle Remaining Months ---
        if remaining_months > 0:
            invoice_lines = []
            invoice_name = "Installment of " + self.contract_id.property_id.name
            record = {
                "product_id": self.contract_id.installment_item_id.id,
                "name": invoice_name,
                "quantity": 1,
                "price_unit": (self.contract_id.total_rent_year / 12) * remaining_months,
                "tax_ids": (
                    self.contract_id.tax_ids.ids
                    if self.contract_id.instalment_tax
                    else False
                ),
                # "account_id": self.contract_id.property_project_id.invoice_creation_id.id,
            }
            invoice_lines.append((0, 0, record))

            reminder_invoice = self.env["account.move"].sudo().create({
                "partner_id": self.contract_id.tenancy_id.id,
                "move_type": "out_invoice",
                "invoice_date": self.contract_id.invoice_start_date,
                "invoice_line_ids": invoice_lines,
                "invoice_date_due": next_invoice_date,
            })
            reminder_invoice.tenancy_id = self.contract_id.id
            # reminder_invoice.action_post()

            self.env["rent.invoice"].create({
                "tenancy_id": self.contract_id.id,
                "type": "rent",
                "invoice_date": next_invoice_date,
                "description": invoice_name,
                "rent_invoice_id": reminder_invoice.id,
                "amount": (self.contract_id.total_rent_year / 12) * remaining_months,
                "rent_amount": (self.contract_id.total_rent_year / 12) * remaining_months,
                "remain": remaining_months,
            })


    def action_yearly_year(self):
        """Yearly Payment Term - Active Contract"""
        invoice_post_type = (
            self.env["ir.config_parameter"]
            .sudo()
            .get_str("rental_management.invoice_post_type", False)
        )
        service_amount = 0.0
        active_id = self.env.context.get("active_id")
        tenancy_id = self.env["tenancy.details"].browse(active_id)
        invoice_lines = []
        total_months = tenancy_id.month
        years = total_months // 12
        invoice_date = tenancy_id.invoice_start_date + relativedelta(months=12)

        # Separate maintenance or extra services (if any)
        if (
            self.contract_id.is_maintenance_service
            and self.contract_id.maintenance_service_invoice == "separate"
        ):
            self._process_separate_invoices(days=1, maintenance=True)

        if (
            self.contract_id.is_extra_service
            and self.contract_id.extra_service_invoice == "separate"
        ):
            self._process_separate_invoices(days=1, utility=True)

        for i in range(years):
            invoice_lines = []

            # --- RENT LINE (Use total_rent_year) ---
            invoice_lines.append(
                (0, 0, {
                    "product_id": tenancy_id.installment_item_id.id,
                    "name": "First Year Invoice of " + tenancy_id.property_id.name if i == 0 else "Installment of " + tenancy_id.property_id.name,
                    "quantity": 1,
                    "price_unit": self.contract_id.total_rent_year,
                    "tax_ids": (
                        tenancy_id.tax_ids.ids if tenancy_id.instalment_tax else False
                    ),
                    # "account_id": self.contract_id.property_project_id.invoice_creation_id.id,
                })
            )

            # --- SECURITY DEPOSIT (only first invoice) ---
            if i == 0 and tenancy_id.is_any_deposit:
                invoice_lines.append(
                    (0, 0, self._prepare_invoice_line(type="deposit"))
                )

            # --- MAINTENANCE SERVICE (merged) ---
            if (
                tenancy_id.is_maintenance_service
                and self.contract_id.maintenance_service_invoice == "merge"
            ):
                invoice_lines.append(
                    (0, 0, self._prepare_invoice_line(type="maintenance"))
                )

            # --- EXTRA SERVICES (merged) ---
            if (
                tenancy_id.is_extra_service
                and self.contract_id.extra_service_invoice == "merge"
            ):
                for line in tenancy_id.extra_services_ids:
                    if line.service_type == "once":
                        qty = 1
                        price_unit = line.price
                    else:
                        qty = 12
                        price_unit = line.price
                    service_amount += price_unit * qty
                    invoice_lines.append(
                        (0, 0, {
                            "product_id": line.service_id.id,
                            "name": f"Service Type: {'Once' if line.service_type == 'once' else 'Recurring'}\nService: {line.service_id.name}",
                            "quantity": qty,
                            "price_unit": price_unit,
                            "tax_ids": (
                                tenancy_id.tax_ids.ids
                                if tenancy_id.service_tax
                                else False
                            ),
                            # "account_id": self.contract_id.property_project_id.invoice_creation_id.id,
                        })
                    )

            # --- ADDED SERVICES (merged) ---
            if (
                self.contract_id.is_added_services
                and self.contract_id.added_service_ids
                and self.contract_id.added_service_invoice == "merge"
            ):
                for line in self.contract_id.added_service_ids:
                    invoice_lines.append(
                        (0, 0, {
                            "product_id": line.service_id.id,
                            "name": line.service_id.name,
                            "quantity": 1,
                            "price_unit": line.price,
                            # "account_id": self.contract_id.property_project_id.invoice_creation_id.id,
                        })
                    )

            # --- ADDED SERVICES (separate, but add to first invoice only) ---
            if (
                i == 0
                and self.contract_id.is_added_services
                and self.contract_id.added_service_ids
                and self.contract_id.added_service_invoice == "separate"
            ):
                for line in self.contract_id.added_service_ids:
                    invoice_lines.append(
                        (0, 0, {
                            "product_id": line.service_id.id,
                            "name": f"Added Service: {line.service_id.name}",
                            "quantity": 1,
                            "price_unit": line.price,
                            # "account_id": self.contract_id.property_project_id.invoice_creation_id.id,
                        })
                    )

            # --- CREATE INVOICE ---
            invoice_id = self.env["account.move"].sudo().create({
                "partner_id": tenancy_id.tenancy_id.id,
                "move_type": "out_invoice",
                "invoice_date": tenancy_id.invoice_start_date,
                "invoice_line_ids": invoice_lines,
                "tenancy_id": self.contract_id.id,
            })

            # if invoice_post_type == "automatically":
            #     invoice_id.action_post()

            # --- CREATE RENT RECORD ---
            rent_invoice_vals = {
                "tenancy_id": tenancy_id.id,
                "type": "rent",
                "invoice_date": tenancy_id.invoice_start_date,
                "description": (
                    "First Rent"
                    + (" + Deposit" if i == 0 and tenancy_id.is_any_deposit else "")
                    if i == 0
                    else "Installment of " + tenancy_id.property_id.name
                ),
                "rent_invoice_id": invoice_id.id,
                "amount": invoice_id.amount_total,
                "rent_amount": self.contract_id.total_rent_year,
                "service_amount": service_amount,
            }

            self.env["rent.invoice"].create(rent_invoice_vals)
            invoice_date += relativedelta(months=12)

    def action_every_two_months_active(self):
        service_amount = 0.0
        active_id = self.env.context.get("active_id")
        tenancy_id = self.env["tenancy.details"].browse(active_id)

        yearly_rent = tenancy_id.total_rent_year or 0.0
        bimonthly_rent = (yearly_rent / 12) * 2  

        # number of full 2-month periods
        full_periods = self.contract_id.month // 2
        # remaining months (0 or 1)
        remaining_months = self.contract_id.month % 2

        invoice_date = self.contract_id.invoice_start_date + relativedelta(months=2)

        # MAIN LOOP — full 2-month invoices
        if full_periods >= 1:
            for i in range(full_periods):

                invoice_lines = []

                invoice_name = (
                    "First Bi-Monthly Invoice of " + tenancy_id.property_id.name
                    if i == 0
                    else "Installment of " + tenancy_id.property_id.name
                )

                # RENT line
                record = {
                    "product_id": tenancy_id.installment_item_id.id,
                    "name": invoice_name,
                    "quantity": 1,
                    "price_unit": bimonthly_rent,
                    "tax_ids": (
                        tenancy_id.tax_ids.ids
                        if tenancy_id.instalment_tax
                        else False
                    ),
                    # "account_id": self.contract_id.property_project_id.invoice_creation_id.id,
                }
                invoice_lines.append((0, 0, record))

                # DEPOSIT (only on first invoice)
                if i == 0 and tenancy_id.is_any_deposit:
                    invoice_lines.append(
                        (0, 0, self._prepare_invoice_line(type="deposit"))
                    )

                # MAINTENANCE (merge into same invoice)
                if tenancy_id.is_maintenance_service and self.contract_id.maintenance_service_invoice == "merge":
                    invoice_lines.append(
                        (0, 0, {
                            "product_id": tenancy_id.maintenance_item_id.id,
                            "name": "Maintenance of " + tenancy_id.property_id.name,
                            "quantity": 2,
                            "price_unit": tenancy_id.total_maintenance,
                            "tax_ids": (
                                tenancy_id.tax_ids.ids
                                if tenancy_id.instalment_tax
                                else False
                            ),
                            # "account_id": self.contract_id.property_project_id.invoice_creation_id.id,
                        })
                    )

                # EXTRA SERVICES (merged)
                if tenancy_id.is_extra_service and self.contract_id.extra_service_invoice == "merge":
                    for line in tenancy_id.extra_services_ids:
                        if line.service_type == "once":
                            qty = 1
                            price_unit = line.price
                            service_amount += line.price
                        else:  # recurring monthly
                            qty = 2
                            price_unit = line.price
                            service_amount += line.price * 2

                        service_invoice_record = {
                            "product_id": line.service_id.id,
                            "name": f"Service Type: {'Once' if line.service_type == 'once' else 'Recurring'}\nService: {line.service_id.name}",
                            "quantity": qty,
                            "price_unit": price_unit,
                            "tax_ids": (
                                tenancy_id.tax_ids.ids
                                if tenancy_id.service_tax
                                else False
                            ),
                            # "account_id": self.contract_id.property_project_id.invoice_creation_id.id,
                        }
                        invoice_lines.append((0, 0, service_invoice_record))

                # ADDED SERVICES (merge)
                if (
                    self.contract_id.is_added_services
                    and self.contract_id.added_service_ids
                    and self.contract_id.added_service_invoice == "merge"
                ):
                    for line in self.contract_id.added_service_ids:
                        invoice_lines.append((0, 0, {
                            "product_id": line.service_id.id,
                            "name": line.service_id.name,
                            "quantity": 1,
                            "price_unit": line.price,
                            # "account_id": self.contract_id.property_project_id.invoice_creation_id.id,
                        }))

                # ADDED SERVICES (separate only on first invoice)
                if (
                    self.contract_id.is_added_services
                    and self.contract_id.added_service_ids
                    and self.contract_id.added_service_invoice == "separate"
                    and i == 0
                ):
                    for line in self.contract_id.added_service_ids:
                        invoice_lines.append((0, 0, {
                            "product_id": line.service_id.id,
                            "name": line.service_id.name,
                            "quantity": 1,
                            "price_unit": line.price,
                            # "account_id": self.contract_id.property_project_id.invoice_creation_id.id,
                        }))

                # CREATE INVOICE
                data = {
                    "partner_id": tenancy_id.tenancy_id.id,
                    "move_type": "out_invoice",
                    "invoice_date": tenancy_id.invoice_start_date,
                    "invoice_line_ids": invoice_lines,
                    "invoice_date_due": invoice_date,
                }
                invoice_id = self.env["account.move"].sudo().create(data)
                invoice_id.tenancy_id = tenancy_id.id

                invoice_id.action_post()

                # RENT INVOICE RECORD
                self.env["rent.invoice"].create({
                    "tenancy_id": tenancy_id.id,
                    "type": "rent",
                    "invoice_date": invoice_date,
                    "description": invoice_name,
                    "rent_invoice_id": invoice_id.id,
                    "amount": invoice_id.amount_total,
                    "rent_amount": bimonthly_rent,
                    "service_amount": service_amount,
                })

                invoice_date += relativedelta(months=2)

        # -------------------------------------
        # REMAINING MONTHS (1 month left)
        # -------------------------------------
        if remaining_months > 0:
            invoice_lines = []
            invoice_name = "Installment of " + tenancy_id.property_id.name
            reminder_rent = (yearly_rent / 12) * remaining_months

            record = {
                "product_id": tenancy_id.installment_item_id.id,
                "name": invoice_name,
                "quantity": 1,
                "price_unit": reminder_rent,
                "tax_ids": (
                    tenancy_id.tax_ids.ids
                    if tenancy_id.instalment_tax
                    else False
                ),
                # "account_id": self.contract_id.property_project_id.invoice_creation_id.id,
            }
            invoice_lines.append((0, 0, record))

            data = {
                "partner_id": tenancy_id.tenancy_id.id,
                "move_type": "out_invoice",
                "invoice_date": tenancy_id.invoice_start_date,
                "invoice_line_ids": invoice_lines,
                "invoice_date_due": invoice_date,
            }
            reminder_invoice = self.env["account.move"].sudo().create(data)
            reminder_invoice.tenancy_id = tenancy_id.id

            reminder_invoice.action_post()

            self.env["rent.invoice"].create({
                "tenancy_id": tenancy_id.id,
                "type": "rent",
                "invoice_date": invoice_date,
                "description": invoice_name,
                "rent_invoice_id": reminder_invoice.id,
                "amount": reminder_rent,
                "rent_amount": reminder_rent,
                "remain": remaining_months,
            })


    
    def action_every_four_months_active(self):
        service_amount = 0.0
        active_id = self.env.context.get("active_id")
        tenancy_id = self.env["tenancy.details"].browse(active_id)

        yearly_rent = tenancy_id.total_rent_year or 0.0
        four_month_rent = (yearly_rent / 12) * 4  

        full_periods = self.contract_id.month // 4
        remaining_months = self.contract_id.month % 4

        invoice_date = self.contract_id.invoice_start_date + relativedelta(months=4)

        # MAIN LOOP — full 4-month invoices
        if full_periods >= 1:
            for i in range(full_periods):
                invoice_lines = []

                invoice_name = (
                    "First 4-Month Invoice of " + tenancy_id.property_id.name
                    if i == 0
                    else "Installment of " + tenancy_id.property_id.name
                )

                # RENT LINE
                record = {
                    "product_id": tenancy_id.installment_item_id.id,
                    "name": invoice_name,
                    "quantity": 1,
                    "price_unit": four_month_rent,
                    "tax_ids": (
                        tenancy_id.tax_ids.ids
                        if tenancy_id.instalment_tax
                        else False
                    ),
                    # "account_id": self.contract_id.property_project_id.invoice_creation_id.id,
                }
                invoice_lines.append((0, 0, record))

                # DEPOSIT only on first invoice
                if i == 0 and tenancy_id.is_any_deposit:
                    invoice_lines.append(
                        (0, 0, self._prepare_invoice_line(type="deposit"))
                    )

                # MAINTENANCE (merge)
                if tenancy_id.is_maintenance_service and self.contract_id.maintenance_service_invoice == "merge":
                    invoice_lines.append(
                        (0, 0, {
                            "product_id": tenancy_id.maintenance_item_id.id,
                            "name": "Maintenance of " + tenancy_id.property_id.name,
                            "quantity": 4,
                            "price_unit": tenancy_id.total_maintenance,
                            "tax_ids": (
                                tenancy_id.tax_ids.ids
                                if tenancy_id.instalment_tax
                                else False
                            ),
                            # "account_id": self.contract_id.property_project_id.invoice_creation_id.id,
                        })
                    )

                # EXTRA SERVICES (merge)
                if tenancy_id.is_extra_service and self.contract_id.extra_service_invoice == "merge":
                    for line in tenancy_id.extra_services_ids:
                        if line.service_type == "once":
                            qty = 1
                            price_unit = line.price
                            service_amount += line.price
                        else:  # monthly recurring
                            qty = 4
                            price_unit = line.price
                            service_amount += line.price * 4

                        service_invoice_record = {
                            "product_id": line.service_id.id,
                            "name": f"Service Type: {'Once' if line.service_type == 'once' else 'Recurring'}\nService: {line.service_id.name}",
                            "quantity": qty,
                            "price_unit": price_unit,
                            "tax_ids": (
                                tenancy_id.tax_ids.ids
                                if tenancy_id.service_tax
                                else False
                            ),
                            # "account_id": self.contract_id.property_project_id.invoice_creation_id.id,
                        }
                        invoice_lines.append((0, 0, service_invoice_record))

                # ADDED SERVICES (merge)
                if (
                    self.contract_id.is_added_services
                    and self.contract_id.added_service_ids
                    and self.contract_id.added_service_invoice == "merge"
                ):
                    for line in self.contract_id.added_service_ids:
                        invoice_lines.append((0, 0, {
                            "product_id": line.service_id.id,
                            "name": line.service_id.name,
                            "quantity": 1,
                            "price_unit": line.price,
                            # "account_id": self.contract_id.property_project_id.invoice_creation_id.id,
                        }))

                # ADDED SERVICES (separate — only first invoice)
                if (
                    self.contract_id.is_added_services
                    and self.contract_id.added_service_ids
                    and self.contract_id.added_service_invoice == "separate"
                    and i == 0
                ):
                    for line in self.contract_id.added_service_ids:
                        invoice_lines.append((0, 0, {
                            "product_id": line.service_id.id,
                            "name": line.service_id.name,
                            "quantity": 1,
                            "price_unit": line.price,
                            # "account_id": self.contract_id.property_project_id.invoice_creation_id.id,
                        }))

                # CREATE THE INVOICE
                data = {
                    "partner_id": tenancy_id.tenancy_id.id,
                    "move_type": "out_invoice",
                    "invoice_date": tenancy_id.invoice_start_date,
                    "invoice_line_ids": invoice_lines,
                    "invoice_date_due": invoice_date,
                }
                invoice_id = self.env["account.move"].sudo().create(data)
                invoice_id.tenancy_id = tenancy_id.id

                # invoice_id.action_post()

                # RENT-INVOICE RECORD
                self.env["rent.invoice"].create({
                    "tenancy_id": tenancy_id.id,
                    "type": "rent",
                    "invoice_date": invoice_date,
                    "description": invoice_name,
                    "rent_invoice_id": invoice_id.id,
                    "amount": invoice_id.amount_total,
                    "rent_amount": four_month_rent,
                    "service_amount": service_amount,
                })

                invoice_date += relativedelta(months=4)

        # -------------------------------------
        # REMAINING MONTHS (1–3 months left)
        # -------------------------------------
        if remaining_months > 0:
            invoice_lines = []
            invoice_name = "Installment of " + tenancy_id.property_id.name
            reminder_rent = (yearly_rent / 12) * remaining_months

            record = {
                "product_id": tenancy_id.installment_item_id.id,
                "name": invoice_name,
                "quantity": 1,
                "price_unit": reminder_rent,
                "tax_ids": (
                    tenancy_id.tax_ids.ids
                    if tenancy_id.instalment_tax
                    else False
                ),
                # "account_id": self.contract_id.property_project_id.invoice_creation_id.id,
            }
            invoice_lines.append((0, 0, record))

            data = {
                "partner_id": tenancy_id.tenancy_id.id,
                "move_type": "out_invoice",
                "invoice_date": tenancy_id.invoice_start_date,
                "invoice_line_ids": invoice_lines,
                "invoice_date_due": invoice_date,
            }
            reminder_invoice = self.env["account.move"].sudo().create(data)
            reminder_invoice.tenancy_id = tenancy_id.id

            # reminder_invoice.action_post()

            self.env["rent.invoice"].create({
                "tenancy_id": tenancy_id.id,
                "type": "rent",
                "invoice_date": invoice_date,
                "description": invoice_name,
                "rent_invoice_id": reminder_invoice.id,
                "amount": reminder_rent,
                "rent_amount": reminder_rent,
                "remain": remaining_months,
            })


    def _process_rent_installment_day(self):
        """Process Rent Installment: Rent Unit Day"""
        self.contract_id.rent_invoice_ids.unlink()
        config_obj = self.env['ir.config_parameter'].sudo()
        invoice_post_type = config_obj.get_str(
            "rental_management.invoice_post_type", False)
        total_days = (self.contract_id.total_days
                      if self.contract_id.duration_type == 'by_date'
                      else self.contract_id.month)
        installment_count, full_installment_days, reminder_installment_days = self.get_contract_installment_count(
            total_days=total_days)
        invoice_date = self.contract_id.invoice_start_date
        last_invoice_date = None
        if installment_count > 0:
            for i in range(installment_count):
                description = (f"Installment : {invoice_date} to"
                               f" {invoice_date + relativedelta(days=(full_installment_days - 1))}")
                self.env["rent.invoice"].create({
                    "tenancy_id": self.contract_id.id,
                    "type": "rent",
                    "invoice_date": invoice_date,
                    "description": (description
                                    if self.contract_id.payment_term != 'daily'
                                    else f"Installment {invoice_date}"),
                    "amount": self.contract_id.total_rent * full_installment_days,
                    "rent_amount": self.contract_id.total_rent * full_installment_days,
                    "service_days": full_installment_days
                })
                last_invoice_date = invoice_date + relativedelta(days=(full_installment_days - 1))
                invoice_date += relativedelta(days=(full_installment_days))
        if reminder_installment_days > 0:
            reminder_invoice_date = self.contract_id.invoice_start_date if installment_count == 0 else last_invoice_date
            description = f"Installment : {reminder_invoice_date} to {self.contract_id.end_date}"
            self.env["rent.invoice"].create({
                "tenancy_id": self.contract_id.id,
                "type": "rent",
                "invoice_date": reminder_invoice_date,
                "description": (description
                                if self.contract_id.payment_term != 'daily'
                                else f"Installment {reminder_invoice_date}"),
                "amount": self.contract_id.total_rent * reminder_installment_days,
                "rent_amount": self.contract_id.total_rent * reminder_installment_days,
                "service_days": reminder_installment_days
            })
        first_rent_invoice_line_id = self.contract_id.rent_invoice_ids[0]
        invoice_lines = [(0, 0, {
            "product_id": self.contract_id.installment_item_id.id,
            "name": first_rent_invoice_line_id.description,
            "quantity": 1,
            "price_unit": first_rent_invoice_line_id.amount,
            "tax_ids": self.contract_id.tax_ids.ids if self.contract_id.instalment_tax else False,
        })]
        if self.contract_id.is_any_deposit:
            invoice_lines.append(
                (0, 0, self._prepare_invoice_line(type='deposit')))
            first_rent_invoice_line_id.description = f"{first_rent_invoice_line_id.description} + Deposit"
        if self.contract_id.is_maintenance_service and self.contract_id.maintenance_service_invoice == 'merge':
            maintenance_amount = 0.0
            if self.contract_id.maintenance_rent_type == 'once':
                maintenance_amount = self.contract_id.total_maintenance
            else:
                if installment_count > 0:
                    maintenance_amount = self.contract_id.total_maintenance * full_installment_days
                else:
                    maintenance_amount = self.contract_id.total_maintenance * reminder_installment_days
            invoice_lines.append((0, 0, {
                "product_id": self.contract_id.maintenance_item_id.id,
                "name": f"Maintenance of {self.contract_id.property_id.name}",
                "price_unit": maintenance_amount,
                "quantity": 1,
                "tax_ids": False
            }))
        if self.contract_id.is_extra_service and self.contract_id.extra_service_invoice == 'merge':
            for line in self.contract_id.extra_services_ids:
                service_type = 'Once' if line.service_type == 'once' else "Recurring"
                service_amount = 0.0
                if line.service_type == 'once':
                    service_amount = line.price
                else:
                    if installment_count > 0:
                        service_amount = line.price * full_installment_days
                    else:
                        service_amount = line.price * reminder_installment_days
                invoice_lines.append((0, 0, {
                    "product_id": line.service_id.id,
                    "name": f"Service Type : {service_type} - {line.service_id.name}",
                    "quantity": 1,
                    "price_unit": service_amount,
                    "tax_ids": self.contract_id.tax_ids.ids if self.contract_id.service_tax else False
                }))
        if (self.contract_id.is_added_services
                and self.contract_id.added_service_ids
                and self.contract_id.added_service_invoice == 'merge'):
            for line in self.contract_id.added_service_ids:
                invoice_lines.append((0, 0, {
                    "product_id": line.service_id.id,
                    "name": line.service_id.name,
                    "quantity": 1,
                    "price_unit": line.price,
                }))
        if (self.contract_id.is_added_services
                and self.contract_id.added_service_ids
                and self.contract_id.added_service_invoice == 'separate'):
            self._process_separate_added_services()
        # Create First Invoice
        invoice_id = self.env['account.move'].sudo().create({
            "partner_id": self.contract_id.tenancy_id.id,
            "move_type": "out_invoice",
            "invoice_date": self.contract_id.invoice_start_date,
            "invoice_line_ids": invoice_lines,
            "tenancy_id": self.contract_id.id
        })
        # if invoice_post_type == "automatically":
        #     invoice_id.action_post()
        first_rent_invoice_line_id.amount = invoice_id.amount_total
        first_rent_invoice_line_id.rent_invoice_id = invoice_id.id
        # Separate Invoice : Maintenance and Service
        if self.contract_id.is_maintenance_service and self.contract_id.maintenance_service_invoice == 'separate':
            self._process_separate_invoices(days=(
                full_installment_days if full_installment_days != 0 else reminder_installment_days),
                maintenance=True)
        if self.contract_id.is_extra_service and self.contract_id.extra_service_invoice == 'separate':
            self._process_separate_invoices(days=(
                full_installment_days if full_installment_days != 0 else reminder_installment_days),
                utility=True)

    def _prepare_invoice_line(self, type, unit=False):
        """Prepare Invoice Line"""

        type_mapping = {
            'installment': {
                "product_id": self.contract_id.installment_item_id.id,
                "name": f"First Invoice of {self.contract_id.property_id.name}",
                "price_unit": self.contract_id.total_rent,
                "tax_ids": self.contract_id.tax_ids.ids if self.contract_id.instalment_tax else False,
            },
            'deposit': {
                "product_id": self.contract_id.deposit_item_id.id,
                "name": f"Deposit of {self.contract_id.property_id.name}",
                "price_unit": self.contract_id.deposit_amount,
                "tax_ids": self.contract_id.tax_ids.ids if self.contract_id.deposit_tax else False,
            },
            'maintenance': {
                "product_id": self.contract_id.maintenance_item_id.id,
                "name": f"Maintenance of {self.contract_id.property_id.name}",
                "price_unit": self.contract_id.total_maintenance,
            }
        }

        if type in type_mapping:
            invoice_line = type_mapping[type]
            invoice_line.update({"quantity": 1})
            return invoice_line

    def _prepare_unit_invoice_lines(self, tenancy, period="monthly", months=0):
        print('callinggg')
        invoice_lines = []

        for unit in tenancy.unit_ids:
            multi_line = self.env["group.multi.contract.line"].search(
                [
                    ("contract_id", "=", tenancy.id),
                    ("property_id", "=", unit.id),
                ],
                order="id desc",
                limit=1,
            )

            if not multi_line:
                continue

            value = multi_line.total_rent_year - multi_line.discount_amount
            print(unit,'valuevalue')
            print(value,'valuevalue')
            if tenancy.payment_term == "daily" or tenancy.is_by_date:
                current_year = fields.Date.today().year
                days = 366 if calendar.isleap(current_year) else 365

                if period == "custom":
                    price = (value / days) * months
                else:
                    price = value
            else:
                if period == "monthly":
                    price = value / 12
                elif period == "quarterly":
                    price = value / 4
                elif period == "half_yearly":
                    price = value / 2
                elif period == "yearly":
                    price = value
                elif period == "custom":
                    price = (value / 12) * months
                else:
                    price = value

            invoice_lines.append((0, 0, {
                "product_id": unit.default_product_id.id,
                "name": f"{unit.name} - {tenancy.property_id.name}",
                "quantity": 1,
                "price_unit": price,
                "tax_ids": tenancy.tax_ids.ids if tenancy.instalment_tax else False,
            }))

        return invoice_lines

    def _prepare_installment(self):
        """Prepare installment for rent manual installment type"""
        if self.contract_id.rent_unit == "Month":
            if self.contract_id.payment_term == "monthly":
                self.action_monthly_month_active()
            if self.contract_id.payment_term == "quarterly":
                self.action_quarterly_month_active()
            if self.contract_id.payment_term == "half_year":
                self.action_half_year_month_active()
            if self.contract_id.payment_term == "every_two_months":
                self.action_every_two_months_active()
            if self.contract_id.payment_term == "every_four_months":
                self.action_every_four_months_active()
            if self.contract_id.payment_term == "year":
                self.action_yearly_year()
        if self.contract_id.rent_unit == "Day":
            self._process_rent_installment_day()
        if self.contract_id.is_any_broker:
            self.contract_id.action_broker_invoice()

    def check_current_active_contract_status(self):
        """Overlap check for single-unit contracts only. Multi-contracts
        are intentionally exempted here (per business request) - a
        multi-contract is allowed to activate even if one of its units
        overlaps another running contract, so we skip the check entirely
        when is_multi_contract is set."""
        active_id = self.env.context.get("active_id")
        tenancy_id = self.env["tenancy.details"].browse(active_id)

        if tenancy_id.is_multi_contract:
            return ""

        property_ids = [tenancy_id.property_id.id]
        if not property_ids:
            return ""

        contracts = self.env["tenancy.details"].search([
            ("start_date", "<=", tenancy_id.end_date),
            ("end_date", ">", tenancy_id.start_date),
            ("property_id", "in", property_ids),
            ("contract_type", "=", "running_contract"),
            ("id", "!=", tenancy_id.id),
        ])
        if contracts:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'type': 'info',
                    'title': "Another active contract already exists for the selected period. Please choose a different contract period.",
                    'sticky': False,
                }
            }
        return ""

    def _batch_render_pdf(self, report_ref, res_ids):
        """Render a QWeb PDF report for several records in one call.

        PERF: the previous code called `_render_qweb_pdf` once per record,
        and each call spawns its own wkhtmltopdf process (~1-3s fixed
        start-up cost). Odoo can render many records in a single
        wkhtmltopdf invocation and split the result back per record via
        `_render_qweb_pdf_prepare_streams`; we use that when available so
        N invoices cost one subprocess instead of N. If that API is not
        available (older report config), we transparently fall back to
        the original one-call-per-record behaviour so results are always
        correct either way.

        Returns {res_id: pdf_bytes} - same content as before, just fewer
        renderer invocations to get it.
        """
        if not res_ids:
            return {}
        IrActionsReport = self.env['ir.actions.report']
        if hasattr(IrActionsReport, '_render_qweb_pdf_prepare_streams'):
            try:
                streams = IrActionsReport._render_qweb_pdf_prepare_streams(
                    report_ref, data={}, res_ids=res_ids)
                collected = streams.get('collected_streams', streams)
                pdf_by_id = {}
                for res_id in res_ids:
                    entry = collected.get(res_id)
                    if not entry:
                        continue
                    stream = entry.get('stream') if isinstance(entry, dict) else entry
                    stream.seek(0)
                    pdf_by_id[res_id] = stream.read()
                if len(pdf_by_id) == len(res_ids):
                    return pdf_by_id
            except Exception:
                pass
        # Fallback: previous per-record rendering, unchanged.
        return {
            res_id: IrActionsReport._render_qweb_pdf(report_ref, [res_id])[0]
            for res_id in res_ids
        }

    def _trigger_mail_queue(self):
        """Wake the mail cron immediately instead of letting the queued
        mail wait for its next scheduled poll.

        PERF: paired with `force_send=False` below. The email still gets
        sent within moments (by the cron worker) instead of over the
        interactive request thread, so the user is not blocked waiting on
        an SMTP round-trip, while delivery stays effectively immediate.
        """
        cron = self.env.ref('mail.ir_cron_mail_scheduler_action', raise_if_not_found=False)
        if cron:
            cron.sudo()._trigger()

    def action_create_contract(self):
        try:
            active_contract_check = self.check_current_active_contract_status()
            if active_contract_check:
                message = active_contract_check
                if isinstance(message, dict):
                    message = message.get('params', {}).get('title') or str(message)
                raise ValidationError(message)

            active_id = self.env.context.get("active_id")
            tenancy_id = self.env["tenancy.details"].browse(active_id)
            # Raise a warning if the payment term does not evenly divide the selected duration
            if self.type == "automatic":
                duration_months = tenancy_id.duration_id.month
                term = tenancy_id.payment_term
                term_month_map = {
                    'monthly': 1,
                    'every_two_months': 2,
                    'every_four_months': 4,
                    'quarterly': 3,
                    'half_year': 6,
                    'year': 12,
                }
                # Get months for the selected term
                term_months = term_month_map.get(term)
                print(duration_months,term_months,'duration_monthsduration_months')
                # Decimal
                # if term_months and duration_months % term_months != 0:
                #     payment_term_label = dict(
                #         tenancy_id._fields['payment_term'].selection
                #     ).get(term)
                #     return {
                #         'type': 'ir.actions.client',
                #         'tag': 'display_notification',
                #         'params': {
                #             'title': f"Payment Term: {payment_term_label}",
                #             'message':(
                #                 "The selected payment term does not fully align with the contract duration. "
                #             ),
                #             'type': 'warning',
                #             'sticky': False,
                #         }
                #     }
                tenancy_id.action_active_contract()

            if self.type == "manual":
                self._prepare_installment()
                self._process_post_installment()

            base_url = self.env['ir.config_parameter'].sudo().get_str('web.base.url', False)
            action = self.env.ref(
                "ribs_real_estate.action_contract_payments",
                raise_if_not_found=False
            )

            record_url = (
                f"{base_url}/web#action={action.id}&model=contract.payments&view_type=list"
                if action else
                f"{base_url}/web#model=contract.payments&view_type=list"
            )

            finance_template = self.env.ref(
                'ribs_real_estate.active_contract_mail_template_for_finance',
                raise_if_not_found=False
            )

            email_values = {}
            # PERF: rendered once here and reused below if the same
            # 'tenancy_pdc_details_report_html' report is needed again for
            # the "Draft Payment.pdf" attachment, instead of rendering it
            # twice for the same tenancy_id.
            pdc_report_pdf = None

            if finance_template:
                finance_group = self.env.ref(
                    'ribs_real_estate.property_rental_accountant',
                    raise_if_not_found=False
                )

                if finance_group:
                    emails = finance_group.all_user_ids.mapped('partner_id.email')
                    email_values['email_to'] = ",".join(filter(None, emails))

                force_collect = self.env['ir.config_parameter'].sudo().get_str(
                    'ribs_real_estate.force_collect_payments', False
                ) == 'True'

                attachment_ids = []

                if force_collect:
                    report = self.env.ref(
                        'ribs_real_estate.tenancy_pdc_details_report_html',
                        raise_if_not_found=False
                    )

                    if report:
                        pdc_report_pdf, _ = report.sudo()._render_qweb_pdf(
                            'ribs_real_estate.tenancy_pdc_details_report_html',
                            res_ids=[tenancy_id.id]
                        )

                        attachment = self.env['ir.attachment'].create({
                            'name': 'Payment Details.pdf',
                            'type': 'binary',
                            'raw': pdc_report_pdf,
                            'res_model': 'tenancy.details',
                            'res_id': tenancy_id.id,
                            'mimetype': 'application/pdf',
                        })

                        attachment_ids.append(attachment.id)

                if attachment_ids:
                    email_values['attachment_ids'] = [(6, 0, attachment_ids)]

                # PERF: queue instead of blocking on an SMTP round-trip;
                # _trigger_mail_queue() wakes the mail cron right away so
                # delivery stays effectively immediate.
                finance_template.with_context(
                    record_url=record_url
                ).sudo().send_mail(
                    tenancy_id.id,
                    email_values=email_values,
                    force_send=False
                )
                self._trigger_mail_queue()

            main_template = self.env.ref(
                'rental_management.active_contract_mail_template',
                raise_if_not_found=False
            )

            attachment_ids = []

            invoice_document = self.env.ref(
                'ribs_real_estate.doc_wp_draft_invoice',
                raise_if_not_found=False
            )

            contract_document = self.env.ref(
                'ribs_real_estate.doc_wp_signed_tenancy_contract',
                raise_if_not_found=False
            )

            # PERF: fetch every account.move for this contract ONCE and
            # reuse it both for the draft-invoice attachments below and for
            # the deferred-date update further down (previously two
            # separate searches on the same table for the same
            # tenancy_id).
            all_moves = self.env['account.move'].sudo().search([
                ('tenancy_id', '=', tenancy_id.id),
            ])
            invoices = all_moves.filtered(
                lambda m: m.move_type == 'out_invoice' and m.state == 'draft')

            # PERF: one batched render call for all draft invoices instead
            # of one wkhtmltopdf process per invoice (see
            # `_batch_render_pdf`), then one multi-record create() instead
            # of N single inserts. Same attachments (name, content, model,
            # linkage) as before.
            invoice_pdfs = self._batch_render_pdf('account.report_invoice', invoices.ids)
            invoice_attachment_vals = [{
                'name': 'Draft Invoice.pdf',
                'type': 'binary',
                'raw': invoice_pdfs[invoice.id],
                'res_model': 'tenancy.details',
                'res_id': tenancy_id.id,
                'mimetype': 'application/pdf',
            } for invoice in invoices if invoice.id in invoice_pdfs]
            if invoice_attachment_vals:
                new_invoice_attachments = self.env['ir.attachment'].create(invoice_attachment_vals)
                attachment_ids.extend(new_invoice_attachments.ids)

            if invoice_document and attachment_ids:
                self.env['contract.documents'].sudo().create({
                    'contract_id': tenancy_id.id,
                    'document_id': invoice_document.id,
                    'attachments': [(6, 0, attachment_ids)],
                    'include_in_email': True,
                })

            report = self.env.ref(
                'rental_management.tenancy_details_report_id',
                raise_if_not_found=False
            )

            if report:
                # Render PDF
                pdf_content, _ = report.sudo()._render_qweb_pdf(
                    report.report_name,
                    res_ids=[tenancy_id.id]
                )

                # Create attachment
                attachment = self.env['ir.attachment'].create({
                    'name': f'Contract Agreement.pdf',
                    'type': 'binary',
                    'raw': pdf_content,
                    'res_model': 'tenancy.details',
                    'res_id': tenancy_id.id,
                    'mimetype': 'application/pdf',
                })

                attachment_ids.append(attachment.id)

                if contract_document:
                    self.env['contract.documents'].sudo().create({
                        'contract_id': tenancy_id.id,
                        'document_id': contract_document.id,
                        'attachments': [(6, 0, [attachment.id])],
                        'include_in_email': True,
                    })

            if force_collect:
                report = self.env.ref(
                    'ribs_real_estate.tenancy_pdc_details_report_html',
                    raise_if_not_found=False
                )

                payment_document = self.env.ref(
                    'ribs_real_estate.doc_wp_rent_payment_receipt',
                    raise_if_not_found=False
                )

                if report:
                    # PERF: reuse the PDF already rendered above for the
                    # finance email instead of rendering the same report
                    # for the same tenancy_id a second time.
                    pdf = pdc_report_pdf if pdc_report_pdf is not None else report.sudo()._render_qweb_pdf(
                        'ribs_real_estate.tenancy_pdc_details_report_html',
                        res_ids=[tenancy_id.id]
                    )[0]

                    attachment = self.env['ir.attachment'].create({
                        'name': 'Draft Payment.pdf',
                        'type': 'binary',
                        'raw': pdf,
                        'res_model': 'tenancy.details',
                        'res_id': tenancy_id.id,
                        'mimetype': 'application/pdf',
                    })

                    attachment_ids.append(attachment.id)

                    if payment_document:
                        self.env['contract.documents'].sudo().create({
                            'contract_id': tenancy_id.id,
                            'document_id': payment_document.id,
                            'attachments': [(6, 0, [attachment.id])],
                            'include_in_email': True,
                        })

            if main_template:
                # PERF: queue instead of blocking on an SMTP round-trip;
                # _trigger_mail_queue() wakes the mail cron right away so
                # delivery stays effectively immediate.
                main_template.with_context(
                    record_url=f"/web#id={tenancy_id.id}&model=tenancy.details&view_type=form"
                ).sudo().send_mail(
                    tenancy_id.id,
                    email_values={
                        'attachment_ids': [(6, 0, attachment_ids)]
                    } if attachment_ids else {},
                    force_send=False
                )
                self._trigger_mail_queue()

            # For deferred dates and installment line update from SKIT -- Start
            auto_apply_contract_period = tenancy_id.company_id.auto_apply_contract_period
            # PERF: reuse the recordset fetched once above instead of
            # re-querying account.move for the same tenancy_id again.
            move_id = all_moves
            if move_id and auto_apply_contract_period:
                # Update start / end dates in ALL lines
                move_id.invoice_line_ids[:-1].write({
                    'deferred_start_date': tenancy_id.start_date,
                    'deferred_end_date': tenancy_id.end_date,
                })
    
                # Update installment line name (Commercial / Residential)
                partner = move_id.partner_id
                product_name = "Property Payment Commercial" if partner.is_company else "Property Payment Residential"
                installment_product_id = tenancy_id.installment_item_id.id
    
                # Update only the installment product line
                line = move_id.invoice_line_ids.filtered(
                    lambda l: l.product_id.id == installment_product_id
                )
                if line:
                    line.name = product_name
    
            # Create Journal Entry if enabled
            if tenancy_id.company_id.contract_posting:
                tenancy_id._create_contract_journal_entry(tenancy_id)
            # For deferred dates and installment line update from SKIT -- End

        except (ValidationError, UserError):
            raise
        except Exception:
            tb = traceback.format_exc()
            raise ValidationError("Error while activating contract:\n%s" % tb)
