# -*- coding: utf-8 -*-
"""
al_shafar_extended – Contract Closing Wizard Extension
=======================================================
Inherits `contract.closing.wizard` (ribs_real_estate) and injects:
  • Prorated Days calculation & deduction
  • Tax Refundable option & tax refund calculation
  • Security Deposit refund calculation & separation
  • Generation of 3 separate refund accounting entries (Invoice, Tax, Deposit)
  • Full audit trail recording in `contract.termination.audit`
  • Comprehensive validation rules (duplicate prevention, refund caps, non-negative checks)
"""

import calendar as cal_module
from dateutil.relativedelta import relativedelta

from odoo import models, fields, api, _
from odoo.exceptions import ValidationError, UserError

from .settlement_line import month_span


class ContractClosingWizardExtended(models.TransientModel):
    _inherit = 'contract.closing.wizard'

    # ── Basic Information ────────────────────────────────────────────────────
    customer_id = fields.Many2one(
        'res.partner',
        string="Customer",
        compute='_compute_customer_id',
        store=True,
        readonly=True
    )

    termination_reason_ext = fields.Selection([
        ('early_exit', 'Early Exit by Tenant / Customer'),
        ('mutual_agreement', 'Mutual Agreement'),
        ('breach_of_contract', 'Breach of Contract Terms'),
        ('relocation', 'Relocation / Property Handover'),
        ('other', 'Other Reason'),
    ], string="Termination Reason", default='early_exit')

    settlement_method = fields.Selection([
        ('full_month', 'Full Month'),
        ('prorated', 'Prorated by Days'),
        ('no_refund', 'No Refund'),
    ], string="Settlement Method",
       default=lambda self: self.env.company.settlement_method or 'full_month',
       help="Policy used for calculating prepaid contract refunds on early termination.")

    prorate_days = fields.Integer(
        string="Prorate Days",
        default=0,
        help="Number of days to prorate/deduct from refundable amount when Settlement Method is Prorated by Days."
    )

    tax_refundable = fields.Boolean(
        string="Tax Refundable",
        default=False,
        help="Checked = Tax is NOT refundable (exclude tax from refund). Unchecked = Tax IS refundable (include tax in refund calculation)."
    )

    refund_method = fields.Selection([
        ('credit_note', 'Credit Note (Customer Refund Invoice)'),
        ('customer_refund', 'Direct Customer Payment Refund'),
        ('wallet_credit', 'Wallet / Customer Credit Balance Entry'),
    ], string="Refund Method", default='credit_note')

    # ── Read-only Settlement Summary Fields ──────────────────────────────────
    currency_id = fields.Many2one(
        'res.currency',
        string="Currency",
        compute='_compute_settlement_currency',
        store=False,
    )

    contract_amount = fields.Monetary(
        string="Contract Amount",
        compute='_compute_settlement_summary',
        currency_field='currency_id',
        readonly=True,
    )

    amount_already_paid = fields.Monetary(
        string="Amount Already Paid",
        compute='_compute_settlement_summary',
        currency_field='currency_id',
        readonly=True,
    )

    amount_utilized = fields.Monetary(
        string="Amount Utilized",
        compute='_compute_settlement_summary',
        currency_field='currency_id',
        readonly=True,
    )

    settlement_amount = fields.Monetary(
        string="Settlement Amount",
        compute='_compute_settlement_summary',
        currency_field='currency_id',
        readonly=True,
    )

    prorated_amount = fields.Monetary(
        string="Prorated Amount",
        compute='_compute_settlement_summary',
        currency_field='currency_id',
        readonly=True,
    )

    remaining_refund_amount = fields.Monetary(
        string="Remaining Refund Amount",
        compute='_compute_settlement_summary',
        currency_field='currency_id',
        readonly=True,
    )

    invoice_refund_amount = fields.Monetary(
        string="Invoice Refund Amount",
        compute='_compute_settlement_summary',
        currency_field='currency_id',
        readonly=True,
    )

    tax_refund_amount = fields.Monetary(
        string="Tax Refund Amount",
        compute='_compute_settlement_summary',
        currency_field='currency_id',
        readonly=True,
    )

    deposit_refund_amount = fields.Monetary(
        string="Security Deposit Refund Amount",
        compute='_compute_settlement_summary',
        currency_field='currency_id',
        readonly=True,
    )

    total_refund_amount = fields.Monetary(
        string="Total Refund Amount",
        compute='_compute_settlement_summary',
        currency_field='currency_id',
        readonly=True,
    )

    penalty_deduction = fields.Monetary(
        string="Penalty Deduction",
        compute='_compute_settlement_summary',
        currency_field='currency_id',
        readonly=True,
        help="Penalty amount deducted from the gross refund. Reflected as a negative line in the credit note."
    )

    net_refund_amount = fields.Monetary(
        string="Net Refund After Penalty",
        compute='_compute_settlement_summary',
        currency_field='currency_id',
        readonly=True,
    )

    # ── Occupancy / apportionment summary (drives the breakdown card) ───────
    total_period_days = fields.Integer(
        string="Billed Days",
        compute='_compute_settlement_summary',
        readonly=True,
        help="Total number of days covered by the selected invoice lines.")

    occupied_days = fields.Integer(
        string="Occupied Days",
        compute='_compute_settlement_summary',
        readonly=True,
        help="Days from the contract start date up to and including the closing date.")

    refundable_days = fields.Integer(
        string="Refundable Days",
        compute='_compute_settlement_summary',
        readonly=True,
        help="Unused days after the closing date — the basis of the refund.")

    remarks_ext = fields.Text(string="Settlement Remarks / Notes")

    # ── Invoice Selection (above summary) ───────────────────────────────────
    # The contract's invoices. The user ticks which ones to refund; each
    # selected invoice is day-prorated against the termination date, and the
    # whole settlement summary is driven ONLY by the selected invoices.
    invoice_selection_ids = fields.One2many(
        'contract.settlement.invoice',
        'wizard_id',
        string="Invoices to Refund",
    )
    use_invoice_selection = fields.Boolean(
        string="Refund by Selected Invoices",
        default=True,
        help="When on, the refund is computed only from the invoices ticked "
             "below, each day-prorated. When off, the legacy contract-level "
             "calculation is used.",
    )

    # ── Account-wise Component Breakdown (editable) ─────────────────────────
    # One editable line per refund component. The user selects the GL account
    # (debit) and the customer account (credit) for each component. These lines
    # are recomputed whenever the settlement inputs change, but the accounts the
    # user picks are PRESERVED across recomputes (keyed on component_type).
    settlement_line_ids = fields.One2many(
        'contract.settlement.line',
        'wizard_id',
        string="Settlement Components",
    )

    # ── Journal-Items-wise Preview (read-only) ──────────────────────────────
    # Derived live from settlement_line_ids: exactly the debit/credit lines that
    # will be posted, split account-wise, so the user sees the double entry
    # before executing the termination.
    settlement_journalitem_ids = fields.One2many(
        'contract.settlement.journalitem',
        'wizard_id',
        string="Journal Items Preview",
        compute='_compute_settlement_journalitems',
        store=False,
        readonly=True,
    )
    preview_total_debit = fields.Monetary(
        string="Total Debit",
        compute='_compute_settlement_journalitems',
        currency_field='currency_id',
    )
    preview_total_credit = fields.Monetary(
        string="Total Credit",
        compute='_compute_settlement_journalitems',
        currency_field='currency_id',
    )
    preview_balanced = fields.Boolean(
        string="Balanced",
        compute='_compute_settlement_journalitems',
    )

    # ── Customer & Currency Computations ────────────────────────────────────
    @api.depends('contract_id')
    def _compute_customer_id(self):
        for rec in self:
            contract = rec._get_target_contract()
            rec.customer_id = contract.tenancy_id.id if (contract and hasattr(contract, 'tenancy_id')) else False

    @api.depends('contract_id')
    def _compute_settlement_currency(self):
        for rec in self:
            contract = rec._get_target_contract()
            rec.currency_id = (
                contract.currency_id
                if contract and contract.currency_id
                else self.env.company.currency_id
            )

    def _get_target_contract(self):
        self.ensure_one()
        if self.contract_id:
            return self.contract_id
        ctx_id = self.env.context.get('default_contract_id')
        if ctx_id:
            return self.env['tenancy.details'].browse(ctx_id)
        return False

    # ── Live Settlement Summary Calculation ─────────────────────────────────
    @api.depends('contract_id', 'closing_date', 'settlement_method', 'prorate_days',
                 'tax_refundable', 'termination_type', 'use_invoice_selection',
                 'if_penalty', 'penalty_amount',
                 'invoice_selection_ids', 'invoice_selection_ids.selected',
                 'invoice_selection_ids.line_type',
                 'invoice_selection_ids.refund_amount',
                 'invoice_selection_ids.refund_tax_amount',
                 'invoice_selection_ids.refund_total',
                 'invoice_selection_ids.period_days',
                 'invoice_selection_ids.used_days',
                 'invoice_selection_ids.refund_days',
                 'invoice_selection_ids.amount', 'invoice_selection_ids.vat_amount')
    def _compute_settlement_summary(self):
        for rec in self:
            contract = rec._get_target_contract()
            if not contract or not rec.closing_date:
                rec.contract_amount = 0.0
                rec.amount_already_paid = 0.0
                rec.amount_utilized = 0.0
                rec.settlement_amount = 0.0
                rec.prorated_amount = 0.0
                rec.remaining_refund_amount = 0.0
                rec.invoice_refund_amount = 0.0
                rec.tax_refund_amount = 0.0
                rec.deposit_refund_amount = 0.0
                rec.total_refund_amount = 0.0
                rec.penalty_deduction = 0.0
                rec.net_refund_amount = 0.0
                rec.total_period_days = 0
                rec.occupied_days = 0
                rec.refundable_days = 0
                continue

            if rec.termination_type == 'normal':
                # Full term completed: no rent/tax refund is due (the tenant
                # used the whole contract), but any security deposit is still
                # returned — in full, minus a penalty if one applies.
                deposit_ref = 0.0
                if getattr(contract, 'is_any_deposit', False):
                    deposit_ref = getattr(contract, 'deposit_amount', 0.0) or 0.0
                pen_ded = round(rec.penalty_amount or 0.0, 2) if rec.if_penalty else 0.0
                net_ref = max(round(deposit_ref - pen_ded, 2), 0.0)

                rec.contract_amount = (
                    getattr(contract, 'contract_value', 0.0)
                    or getattr(contract, 'total_contract_value', 0.0)
                    or getattr(contract, 'total_rent_year', 0.0)
                )
                rec.amount_already_paid = 0.0
                rec.amount_utilized = 0.0
                rec.settlement_amount = deposit_ref
                rec.prorated_amount = 0.0
                rec.remaining_refund_amount = net_ref
                rec.invoice_refund_amount = 0.0
                rec.tax_refund_amount = 0.0
                rec.deposit_refund_amount = deposit_ref
                rec.total_refund_amount = deposit_ref
                rec.penalty_deduction = pen_ded
                rec.net_refund_amount = net_ref
                rec.total_period_days = 0
                rec.occupied_days = 0
                rec.refundable_days = 0
                continue

            if rec.termination_type != 'early':
                rec.contract_amount = 0.0
                rec.amount_already_paid = 0.0
                rec.amount_utilized = 0.0
                rec.settlement_amount = 0.0
                rec.prorated_amount = 0.0
                rec.remaining_refund_amount = 0.0
                rec.invoice_refund_amount = 0.0
                rec.tax_refund_amount = 0.0
                rec.deposit_refund_amount = 0.0
                rec.total_refund_amount = 0.0
                rec.penalty_deduction = 0.0
                rec.net_refund_amount = 0.0
                rec.total_period_days = 0
                rec.occupied_days = 0
                rec.refundable_days = 0
                continue

            # 1. Contract Total Amount
            contract_tot = (
                contract.contract_value
                or getattr(contract, 'total_contract_value', 0.0)
                or getattr(contract, 'total_rent_year', 0.0)
            )

            # 2. Derive Paid Amount
            paid_amount = 0.0
            if hasattr(contract, 'rent_invoice_ids') and contract.rent_invoice_ids:
                paid_inv = contract.rent_invoice_ids.filtered(
                    lambda r: r.rent_invoice_id and r.rent_invoice_id.state == 'posted'
                )
                paid_amount = sum(
                    r.amount for r in paid_inv
                    if r.rent_invoice_id.payment_state in ('paid', 'in_payment')
                )
            if not paid_amount and hasattr(contract, 'contract_payment_ids') and contract.contract_payment_ids:
                rec_payments = contract.contract_payment_ids.filtered(
                    lambda p: p.payments_received == 'received'
                )
                paid_amount = sum(p.amount for p in rec_payments)
            if not paid_amount:
                paid_amount = contract_tot

            # ── INVOICE-LINE-DRIVEN PATH ────────────────────────────────────
            # Paid / utilised / refund come ONLY from the selected invoice
            # LINES, each already day-prorated (untaxed + VAT) on the line.
            #
            # IMPORTANT: During onchange() calls the browser does NOT send back
            # readonly field values (amount, vat_amount, product_label, name).
            # We therefore re-fetch these from the linked move_line_id whenever
            # they appear to be missing/zero so calculations stay accurate.
            all_invs = rec.invoice_selection_ids
            if rec.use_invoice_selection and all_invs:
                # "Amount Paid" = everything billed on the contract, whether or
                # not the user ticked it. Only the REFUND follows the ticks.
                billed_total = sum(all_invs.mapped('total_amount')) \
                    or (sum(all_invs.mapped('amount')) + sum(all_invs.mapped('vat_amount')))
                paid_amount = billed_total or paid_amount

                selected_invs = all_invs.filtered('selected')
                if selected_invs:
                    # ── Split by line type ──────────────────────────────────
                    deposit_invs = selected_invs.filtered(lambda l: l.line_type == 'deposit')
                    rental_invs = selected_invs - deposit_invs

                    # Refunds are already time-apportioned on each line against
                    # the contract start date, the line's coverage period and
                    # the closing date — see contract.settlement.invoice.
                    inv_ref = round(sum(rental_invs.mapped('refund_amount')), 2)
                    dep_ref = round(sum(deposit_invs.mapped('refund_amount')), 2)
                    tax_ref = 0.0 if rec.tax_refundable else round(
                        sum(rental_invs.mapped('refund_tax_amount')), 2)

                    # ── Occupancy day roll-up (rent lines only) ─────────────
                    rent_all = all_invs.filtered(lambda l: l.line_type == 'rent')
                    rec.total_period_days = max(rent_all.mapped('period_days') or [0])
                    rec.occupied_days = max(rent_all.mapped('used_days') or [0])
                    rec.refundable_days = max(rent_all.mapped('refund_days') or [0])

                    # Day-based proration is already applied per invoice line
                    # above (refund_amount, apportioned in contract.settlement
                    # .invoice._apportion_vals). Prorate Days/prorated_amount
                    # is not applied here too - that would deduct the same
                    # unused-days value a second time.
                    prorated_deduction = 0.0

                    if rec.settlement_method == 'no_refund':
                        inv_ref = tax_ref = dep_ref = 0.0

                    gross_ref = round(inv_ref + tax_ref + dep_ref, 2)
                    pen_ded = round(rec.penalty_amount or 0.0, 2) if rec.if_penalty else 0.0
                    net_ref = max(round(gross_ref - pen_ded, 2), 0.0)
                    # What the tenant actually consumed = billed − refunded.
                    utilized_amt = max(round(paid_amount - gross_ref, 2), 0.0)

                    rec.contract_amount = contract_tot
                    rec.amount_already_paid = paid_amount
                    rec.amount_utilized = utilized_amt
                    rec.settlement_amount = inv_ref + dep_ref
                    rec.prorated_amount = prorated_deduction
                    rec.remaining_refund_amount = net_ref
                    rec.invoice_refund_amount = inv_ref
                    rec.tax_refund_amount = tax_ref
                    rec.deposit_refund_amount = dep_ref
                    rec.total_refund_amount = gross_ref
                    rec.penalty_deduction = pen_ded
                    rec.net_refund_amount = net_ref
                    continue

            if rec.use_invoice_selection:
                # use_invoice_selection is on but no lines selected → zeros
                rec.contract_amount = contract_tot
                rec.amount_already_paid = paid_amount
                rec.amount_utilized = paid_amount
                rec.settlement_amount = 0.0
                rec.prorated_amount = 0.0
                rec.remaining_refund_amount = 0.0
                rec.invoice_refund_amount = 0.0
                rec.tax_refund_amount = 0.0
                rec.deposit_refund_amount = 0.0
                rec.total_refund_amount = 0.0
                rec.penalty_deduction = 0.0
                rec.net_refund_amount = 0.0
                rec.total_period_days = 0
                rec.occupied_days = 0
                rec.refundable_days = 0
                continue

            # ── LEGACY CONTRACT-LEVEL PATH ──────────────────────────────────
            # 3. Derive Monthly and Daily Rent Rate
            dur_months = (
                contract.duration_id.month
                if (hasattr(contract, 'duration_id') and contract.duration_id)
                else 12
            )
            monthly_rent = (
                (contract.total_rent_year / 12.0)
                if (hasattr(contract, 'total_rent_year') and contract.total_rent_year)
                else ((contract_tot / max(dur_months or 1, 1)) if contract_tot else 0.0)
            )
            daily_rent = monthly_rent / 30.0 if monthly_rent else 0.0

            # Day-based proration is applied inside _calculate_utilized_and_refund
            # below via settlement_method. Prorate Days is not applied again
            # here - that would deduct the same unused-days value twice.
            prorated_deduction = 0.0

            # 5. Utilized Service Amount
            utilized_amt, calc_refund = rec._calculate_utilized_and_refund(
                contract=contract,
                termination_date=rec.closing_date,
                settlement_method=rec.settlement_method or 'full_month',
                paid_amount=paid_amount,
                monthly_rent=monthly_rent,
            )

            if rec.settlement_method == 'no_refund':
                calc_refund = 0.0
                utilized_amt = paid_amount

            settlement_amt = max(calc_refund - prorated_deduction, 0.0)
            remaining_refund = settlement_amt

            # 6. Tax Refund Calculation
            tax_rate = 0.0
            if hasattr(contract, 'tax_ids') and contract.tax_ids:
                tax_rate = sum(contract.tax_ids.mapped('amount'))
            elif hasattr(contract, 'service_tax') and contract.service_tax:
                tax_rate = 5.0  # Standard UAE VAT default fallback

            if rec.tax_refundable:
                # Checked = Tax NOT refundable
                tax_ref = 0.0
                inv_ref = remaining_refund
            else:
                # Unchecked = Tax IS refundable
                tax_ref = round(remaining_refund * (tax_rate / 100.0), 2) if tax_rate > 0 else 0.0
                inv_ref = remaining_refund

            # 7. Security Deposit Refund Calculation
            deposit_ref = 0.0
            if hasattr(contract, 'is_any_deposit') and contract.is_any_deposit:
                deposit_ref = getattr(contract, 'deposit_amount', 0.0)

            total_ref = inv_ref + tax_ref + deposit_ref

            pen_ded = round(rec.penalty_amount or 0.0, 2) if rec.if_penalty else 0.0
            net_ref = max(total_ref - pen_ded, 0.0)

            rec.contract_amount = contract_tot
            rec.amount_already_paid = paid_amount
            rec.amount_utilized = utilized_amt
            rec.settlement_amount = settlement_amt
            rec.prorated_amount = prorated_deduction
            rec.remaining_refund_amount = net_ref
            rec.invoice_refund_amount = inv_ref
            rec.tax_refund_amount = tax_ref
            rec.deposit_refund_amount = deposit_ref
            rec.total_refund_amount = total_ref
            rec.penalty_deduction = pen_ded
            rec.net_refund_amount = net_ref

            # Contract-level occupancy days
            if contract.start_date and contract.end_date:
                term_d = min(max(rec.closing_date, contract.start_date), contract.end_date)
                rec.total_period_days = (contract.end_date - contract.start_date).days + 1
                rec.occupied_days = (term_d - contract.start_date).days + 1
                rec.refundable_days = max(rec.total_period_days - rec.occupied_days, 0)
            else:
                rec.total_period_days = 0
                rec.occupied_days = 0
                rec.refundable_days = 0

    # ── Default GL Account Resolver (shared by preview & posting) ───────────
    def _resolve_component_account(self, contract, component_type):
        """Return the default GL (debit-side) account for a refund component.

        Centralised so the on-screen preview and the actual posting use the
        SAME account logic. Falls back gracefully when nothing specific is
        configured.
        """
        Account = self.env['account.account']
        company = (contract.company_id if contract else False) or self.env.company

        income_account = Account.search([
            ('account_type', 'in', ('income', 'income_other', 'asset_prepayments')),
            ('company_ids', 'in', [company.id]),
        ], limit=1) or Account.search([
            ('account_type', 'in', ('income', 'income_other')),
        ], limit=1)

        if component_type == 'invoice':
            return income_account

        if component_type == 'tax':
            return Account.search([
                ('account_type', '=', 'liability_current'),
                ('name', 'ilike', 'tax'),
                ('company_ids', 'in', [company.id]),
            ], limit=1) or income_account

        if component_type == 'deposit':
            dep = getattr(contract.deposit_item_id, 'property_account_income_id', False) \
                if (contract and hasattr(contract, 'deposit_item_id')) else False
            if not dep:
                dep = Account.search([
                    ('account_type', '=', 'liability_current'),
                    ('name', 'ilike', 'deposit'),
                    ('company_ids', 'in', [company.id]),
                ], limit=1) or income_account
            return dep

        return income_account

    def _resolve_receivable_account(self, contract):
        """Default customer (credit-side) account = partner receivable."""
        partner = contract.tenancy_id if (contract and hasattr(contract, 'tenancy_id')) else False
        if partner and partner.property_account_receivable_id:
            return partner.property_account_receivable_id
        Account = self.env['account.account']
        company = (contract.company_id if contract else False) or self.env.company
        return Account.search([
            ('account_type', '=', 'asset_receivable'),
            ('company_ids', 'in', [company.id]),
        ], limit=1)

    # ── Coverage-period resolution (THE proration driver) ───────────────────
    # A line's refund is only as correct as the period it is measured against.
    # The old code assumed every invoice covered exactly one month, so a
    # half-yearly or yearly invoice was never apportioned and the full value
    # came back as refundable. This resolves the real window instead.
    PAYMENT_TERM_MONTHS = (
        ('half_year', 6), ('half-year', 6), ('halfyear', 6), ('semi', 6),
        ('quarter', 3), ('three_month', 3),
        ('month', 1),
        ('year', 12), ('annual', 12), ('full', 12),
    )

    def _payment_term_months(self, contract):
        """How many months one rent invoice covers, from the contract's terms."""
        raw = ''
        for fname in ('payment_term', 'payment_terms', 'rent_type', 'invoice_frequency',
                      'payment_frequency', 'rent_payment_term'):
            val = getattr(contract, fname, False)
            if val:
                raw = str(getattr(val, 'name', val) or '').strip().lower()
                if raw:
                    break
        if raw:
            normalised = raw.replace(' ', '_')
            for keyword, months in self.PAYMENT_TERM_MONTHS:
                if keyword in normalised:
                    return months
        # Fall back to the contract duration (e.g. one invoice for the term)
        dur = getattr(contract, 'duration_id', False)
        if dur and getattr(dur, 'month', 0):
            return int(dur.month)
        return 12

    def _implied_months_from_amount(self, contract, move_line):
        """How many months of rent does this line's VALUE represent?

        More trustworthy than the payment-term label: a contract may be flagged
        'Half Year' while the tenant actually paid a single full-year invoice.
        The money says what the invoice really covers.
        """
        total_months = 0
        dur = getattr(contract, 'duration_id', False)
        if dur and getattr(dur, 'month', 0):
            total_months = int(dur.month)
        c_start = getattr(contract, 'start_date', False)
        c_end = getattr(contract, 'end_date', False)
        if not total_months and c_start and c_end:
            total_months = month_span(c_start, c_end)
        if not total_months:
            return 0

        contract_tot = (
            getattr(contract, 'contract_value', 0.0)
            or getattr(contract, 'total_contract_value', 0.0)
            or getattr(contract, 'total_rent_year', 0.0)
        )
        if not contract_tot:
            return 0

        monthly = contract_tot / float(total_months)
        subtotal = move_line.price_subtotal or 0.0
        if monthly <= 0 or subtotal <= 0:
            return 0

        implied = int(round(subtotal / monthly))
        return implied if 1 <= implied <= total_months else 0

    def _resolve_line_period(self, contract, move, move_line):
        """Return (date_from, date_to) — the window this invoice line paid for.

        Resolution order, most trustworthy first:
          1. Odoo's native deferred revenue dates on the invoice line
          2. The ribs_real_estate rent schedule row linked to this invoice
          3. Derived from the contract's payment term, anchored on the invoice
          4. The whole contract window
        """
        # 1. Native deferred revenue period
        d_from = getattr(move_line, 'deferred_start_date', False)
        d_to = getattr(move_line, 'deferred_end_date', False)
        if d_from and d_to and d_to >= d_from:
            return d_from, d_to

        # 2. Rent schedule row that produced this invoice
        if hasattr(contract, 'rent_invoice_ids'):
            for sched in contract.rent_invoice_ids:
                linked = getattr(sched, 'rent_invoice_id', False)
                if not linked or linked.id != move.id:
                    continue
                s = getattr(sched, 'start_date', False) or getattr(sched, 'date_from', False) \
                    or getattr(sched, 'from_date', False)
                e = getattr(sched, 'end_date', False) or getattr(sched, 'date_to', False) \
                    or getattr(sched, 'to_date', False)
                if s and e and e >= s:
                    return s, e
                if s and not e:
                    months = self._payment_term_months(contract)
                    return s, s + relativedelta(months=months) - relativedelta(days=1)

        # 3. Derive from the payment term, anchored on the invoice date
        base = move.invoice_date or move.date or getattr(contract, 'start_date', False)
        c_start = getattr(contract, 'start_date', False)
        c_end = getattr(contract, 'end_date', False)
        if base and c_start and base < c_start:
            base = c_start
        if base:
            months = (self._implied_months_from_amount(contract, move_line)
                      or self._payment_term_months(contract))
            d_from = base
            d_to = base + relativedelta(months=months) - relativedelta(days=1)
            if c_end and d_to > c_end:
                d_to = c_end
            if d_to >= d_from:
                return d_from, d_to

        # 4. Whole contract window
        if c_start and c_end:
            return c_start, c_end
        return False, False

    # ── Invoice-line classification ─────────────────────────────────────────
    DEPOSIT_KEYWORDS = ('deposit', 'security')
    ONE_TIME_KEYWORDS = ('ejari', 'admin', 'registration', 'brokerage', 'agency',
                         'commission', 'one_time', 'one-time', 'onetime',
                         'penalty', 'fine', 'setup', 'stamp')

    def _classify_line(self, move_line):
        """Rent (apportioned) vs Deposit (full) vs One-time charge (not refunded)."""
        blob = ' '.join(filter(None, [
            (move_line.account_id.name or ''),
            (move_line.product_id.display_name or ''),
            (move_line.name or ''),
        ])).lower()
        if any(k in blob for k in self.DEPOSIT_KEYWORDS):
            return 'deposit'
        if any(k in blob for k in self.ONE_TIME_KEYWORDS):
            return 'other'
        return 'rent'

    @staticmethod
    def _is_deposit_account(account):
        """Return True if this GL account is a security-deposit account.

        Uses keyword-only detection: only accounts explicitly named with the
        word 'deposit' qualify.  Broad liability-type checks are intentionally
        avoided because Ejari, Payable, and other liability accounts would
        otherwise be mis-classified, causing their VAT to be excluded from the
        tax-refund calculation.
        """
        if not account:
            return False
        return 'deposit' in (account.name or '').lower()

    # ── Populate Selectable Invoice LINES from the Contract ─────────────────
    @api.onchange('contract_id', 'termination_type')
    def _onchange_populate_invoice_selection(self):
        Move = self.env['account.move']
        for rec in self:
            contract = rec._get_target_contract()
            if not contract or rec.termination_type != 'early':
                rec.invoice_selection_ids = [(5, 0, 0)]
                continue

            # Preserve prior ticks / edited periods / type overrides,
            # keyed on the move line.
            prior = {
                l.move_line_id.id: (l.selected, l.date_from, l.date_to,
                                    l.refund_amount, l.line_type)
                for l in rec.invoice_selection_ids if l.move_line_id
            }

            # Collect the contract's customer invoices from all potential links
            moves = Move.browse()
            if hasattr(contract, 'rent_invoice_ids'):
                for r in contract.rent_invoice_ids:
                    m = getattr(r, 'rent_invoice_id', False)
                    if m:
                        moves |= m
            moves |= Move.search([
                ('tenancy_id', '=', contract.id),
                ('move_type', '=', 'out_invoice'),
            ])
            for f in ('extra_service_invoice', 'maintenance_service_invoice', 'added_service_invoice'):
                val = getattr(contract, f, False)
                if val and hasattr(val, '_name') and val._name == 'account.move':
                    moves |= val
            partner_id = contract.tenancy_id.id if (hasattr(contract, 'tenancy_id') and contract.tenancy_id) else False
            if partner_id and not moves:
                moves |= Move.search([
                    ('partner_id', '=', partner_id),
                    ('move_type', '=', 'out_invoice'),
                ])
            moves = moves.filtered(lambda m: m.state == 'posted' and m.move_type == 'out_invoice')

            c_start = getattr(contract, 'start_date', False)
            c_end = getattr(contract, 'end_date', False)

            commands = [(5, 0, 0)]
            for move in moves:
                for ml in move.invoice_line_ids:
                    if ml.display_type and ml.display_type != 'product':
                        continue
                    keep = prior.get(ml.id)

                    # Real coverage window — honours the contract payment term
                    # instead of assuming every invoice covers one month.
                    d_from, d_to = rec._resolve_line_period(contract, move, ml)
                    line_type = rec._classify_line(ml)

                    # One-time charges (Ejari, admin, registration) are not
                    # refundable on early exit, so they start unticked. The
                    # user can still tick them to refund in full.
                    default_selected = (
                        move.payment_state in ('paid', 'in_payment')
                        and line_type != 'other'
                    )

                    vals = {
                        'move_id': move.id,
                        'move_line_id': ml.id,
                        'line_type': keep[4] if keep else line_type,
                        'contract_start': c_start,
                        'contract_end': c_end,
                        'date_from': (keep[1] if keep else d_from) or d_from,
                        'date_to': (keep[2] if keep else d_to) or d_to,
                        'selected': keep[0] if keep else default_selected,
                    }
                    # refund_amount is deliberately NOT seeded here — it is a
                    # computed field derived from contract start → period →
                    # closing date. Seeding it with the full subtotal is exactly
                    # what made the breakdown show the full invoice value.
                    commands.append((0, 0, vals))
            rec.invoice_selection_ids = commands

    # ── Server-side hydration (the button-click safety net) ─────────────────
    SUMMARY_FIELDS = [
        'contract_amount', 'amount_already_paid', 'amount_utilized',
        'settlement_amount', 'prorated_amount', 'remaining_refund_amount',
        'invoice_refund_amount', 'tax_refund_amount', 'deposit_refund_amount',
        'total_refund_amount', 'penalty_deduction', 'net_refund_amount',
        'total_period_days', 'occupied_days', 'refundable_days',
    ]

    def _hydrate_invoice_lines(self, contract):
        """Rebuild every value the credit note depends on, from the source.

        On a button click the web client only posts the columns present in the
        list view, and readonly / computed columns can arrive as zero or blank.
        Fields absent from the view entirely (contract_start, contract_end)
        arrive as False. Anything derived from that stale data would produce an
        empty credit note, so each line is re-read from its account.move.line
        and written back explicitly before the settlement is built.
        """
        self.ensure_one()
        c_start = getattr(contract, 'start_date', False)
        c_end = getattr(contract, 'end_date', False)
        orphans = self.env['contract.settlement.invoice']

        for line in self.invoice_selection_ids:
            ml = line.move_line_id
            if not ml:
                # No source link → nothing can be rebuilt. Collect rather than
                # skip, so this surfaces instead of becoming a 0.00 refund.
                if line.selected:
                    orphans |= line
                continue
            move = ml.move_id
            subtotal = ml.price_subtotal
            if not subtotal:
                subtotal = abs(ml.price_total or 0.0) or abs(ml.balance or 0.0) \
                    or abs((ml.credit or 0.0) - (ml.debit or 0.0)) \
                    or (ml.quantity or 0.0) * (ml.price_unit or 0.0)
            vals = {
                'move_id': move.id,
                'name': move.name or move.ref or '',
                'product_label': ml.product_id.display_name or ml.name or '',
                'invoice_date': move.invoice_date or move.date,
                'payment_state': move.payment_state or '',
                'account_id': ml.account_id.id,
                'analytic_distribution': ml.analytic_distribution or False,
                'tax_label': ', '.join(ml.tax_ids.mapped('name')),
                'tax_ids': [(6, 0, ml.tax_ids.ids)],
                'quantity': ml.quantity,
                'price_unit': ml.price_unit,
                'amount': subtotal,
                'vat_amount': max((ml.price_total or 0.0) - (ml.price_subtotal or 0.0), 0.0),
                'contract_start': c_start,
                'contract_end': c_end,
            }
            # Reclassify unless the user picked the type by hand — `line_type`
            # has a default of 'rent', so a value arriving here is not proof
            # that anyone chose it.
            if not line.type_override:
                vals['line_type'] = self._classify_line(ml)
            if not line.date_from or not line.date_to:
                d_from, d_to = self._resolve_line_period(contract, move, ml)
                vals['date_from'] = d_from
                vals['date_to'] = d_to
            line.write(vals)

        if orphans:
            raise UserError(_(
                "%(count)s selected invoice line(s) lost their link to the "
                "source invoice, so the refund cannot be calculated.\n\n"
                "Close this dialog and reopen Close Contract. If it repeats, "
                "upgrade the module (-u al_shafar_extended) so the wizard view "
                "carries the invoice-line reference.",
                count=len(orphans)))

        # Re-apportion against the closing date actually submitted.
        self.invoice_selection_ids.force_recompute_refund()
        self.invalidate_recordset(self.SUMMARY_FIELDS)

    def _recompute_line_refunds(self):
        """Live (in-form) refresh — used by the onchange path only."""
        for rec in self:
            lines = rec.invoice_selection_ids
            if lines:
                lines._compute_proration()
                lines._compute_refund_amounts()
                lines._compute_refund_total()

    @api.onchange('closing_date', 'settlement_method', 'tax_refundable',
                  'termination_type')
    def _onchange_recompute_line_refunds(self):
        self._recompute_line_refunds()

    # ── Component Breakdown Lines (account-wise, per invoice line) ──────────
    @api.onchange('contract_id', 'closing_date', 'settlement_method',
                  'tax_refundable', 'termination_type', 'use_invoice_selection',
                  'if_penalty', 'penalty_amount',
                  'invoice_selection_ids', 'invoice_refund_amount',
                  'tax_refund_amount', 'deposit_refund_amount')
    def _onchange_populate_settlement_lines(self):
        for rec in self:
            contract = rec._get_target_contract()
            if not contract or rec.termination_type not in ('early', 'normal'):
                rec.settlement_line_ids = [(5, 0, 0)]
                continue

            partner = contract.tenancy_id if hasattr(contract, 'tenancy_id') else False
            receivable = rec._resolve_receivable_account(contract)
            recv_id = receivable.id if receivable else False
            commands = [(5, 0, 0)]
            seq = 0

            selected = rec.invoice_selection_ids.filtered('selected')
            if rec.use_invoice_selection and selected:
                # One refund component PER invoice line → separate accounts.
                # Detect deposit lines so they use component_type='deposit'.
                tax_account = rec._resolve_component_account(contract, 'tax')
                for inv in selected:
                    is_dep = (inv.line_type == 'deposit')
                    comp_type = 'deposit' if is_dep else 'invoice'
                    if inv.refund_amount:
                        seq += 10
                        label = _("Deposit Refund: %s (%s)") if is_dep else _("Refund: %s (%s)")
                        commands.append((0, 0, {
                            'sequence': seq,
                            'component_type': comp_type,
                            'name': label % (inv.product_label or '', inv.name or ''),
                            'account_id': inv.account_id.id,
                            'receivable_account_id': recv_id,
                            'analytic_distribution': inv.analytic_distribution or False,
                            'amount': inv.refund_amount,
                            'partner_id': partner.id if partner else False,
                        }))
                    # VAT only on rental (non-deposit) lines — already
                    # apportioned on the line itself.
                    if not is_dep and inv.refund_tax_amount and not rec.tax_refundable:
                        seq += 10
                        commands.append((0, 0, {
                            'sequence': seq,
                            'component_type': 'tax',
                            'name': _("VAT Refund: %s (%s)") % (inv.product_label or '', inv.name or ''),
                            'account_id': tax_account.id if tax_account else False,
                            'receivable_account_id': recv_id,
                            'analytic_distribution': inv.analytic_distribution or False,
                            'amount': round(inv.refund_tax_amount, 2),
                            'partner_id': partner.id if partner else False,
                        }))
                if rec.if_penalty and rec.penalty_deduction > 0:
                    pen_account = rec._resolve_component_account(contract, 'invoice')
                    seq += 10
                    commands.append((0, 0, {
                        'sequence': seq,
                        'component_type': 'invoice',
                        'name': _("Penalty Deduction"),
                        'account_id': pen_account.id if pen_account else False,
                        'receivable_account_id': recv_id,
                        'amount': -rec.penalty_deduction,
                        'partner_id': partner.id if partner else False,
                    }))
                rec.settlement_line_ids = commands
                continue

            # Legacy fallback: one line per aggregate component
            components = [
                ('invoice', _("Invoice Service Refund"), rec.invoice_refund_amount),
                ('tax',     _("Tax / VAT Refund"),        rec.tax_refund_amount),
                ('deposit', _("Security Deposit Refund"), rec.deposit_refund_amount),
            ]
            for ctype, label, amount in components:
                if not amount or amount <= 0:
                    continue
                if ctype == 'tax' and rec.tax_refundable:
                    continue
                acct = rec._resolve_component_account(contract, ctype)
                seq += 10
                commands.append((0, 0, {
                    'sequence': seq,
                    'component_type': ctype,
                    'name': label,
                    'account_id': acct.id if acct else False,
                    'receivable_account_id': recv_id,
                    'amount': amount,
                    'partner_id': partner.id if partner else False,
                }))
            rec.settlement_line_ids = commands

    # ── Journal Items Preview (read-only double entry) ──────────────────────
    @api.depends('settlement_line_ids', 'settlement_line_ids.account_id',
                 'settlement_line_ids.receivable_account_id',
                 'settlement_line_ids.amount')
    def _compute_settlement_journalitems(self):
        for rec in self:
            commands = [(5, 0, 0)]
            total_debit = 0.0
            total_credit = 0.0
            for line in rec.settlement_line_ids:
                if not line.amount:
                    continue
                clabel = dict(self.env['contract.settlement.line']._fields['component_type'].selection).get(line.component_type, '')
                # Debit leg — GL account
                commands.append((0, 0, {
                    'component_type': line.component_type,
                    'name': _("%s — reverse", clabel),
                    'account_id': line.account_id.id if line.account_id else False,
                    'partner_id': line.partner_id.id if line.partner_id else False,
                    'debit': line.amount,
                    'credit': 0.0,
                }))
                # Credit leg — customer receivable / refund payable
                commands.append((0, 0, {
                    'component_type': line.component_type,
                    'name': _("%s — customer refund", clabel),
                    'account_id': line.receivable_account_id.id if line.receivable_account_id else False,
                    'partner_id': line.partner_id.id if line.partner_id else False,
                    'debit': 0.0,
                    'credit': line.amount,
                }))
                total_debit += line.amount
                total_credit += line.amount
            rec.settlement_journalitem_ids = commands
            rec.preview_total_debit = total_debit
            rec.preview_total_credit = total_credit
            rec.preview_balanced = rec.currency_id.is_zero(total_debit - total_credit) \
                if rec.currency_id else (round(total_debit - total_credit, 2) == 0.0)

    # ── Core Calculation Helper ─────────────────────────────────────────────
    def _calculate_utilized_and_refund(
        self, contract, termination_date, settlement_method, paid_amount, monthly_rent
    ):
        if not contract.start_date or not contract.end_date or not monthly_rent:
            return 0.0, 0.0

        term_d = min(max(termination_date, contract.start_date), contract.end_date)
        utilized_amount = 0.0
        current_m = contract.start_date.replace(day=1)
        end_m = contract.end_date.replace(day=1)

        if settlement_method == 'prorated':
            while current_m <= end_m:
                _, last_day = cal_module.monthrange(current_m.year, current_m.month)
                month_start = current_m
                month_end = current_m.replace(day=last_day)
                if term_d >= month_end:
                    utilized_amount += monthly_rent
                elif term_d < month_start:
                    pass
                else:
                    days_used = (term_d - month_start).days + 1
                    utilized_amount += (days_used / float(last_day)) * monthly_rent
                current_m += relativedelta(months=1)
        else:
            # full_month or no_refund
            while current_m <= end_m:
                if term_d >= current_m:
                    utilized_amount += monthly_rent
                current_m += relativedelta(months=1)

        contract_tot = (
            contract.contract_value
            or getattr(contract, 'total_contract_value', 0.0)
            or (monthly_rent * 12)
        )
        utilized_amount = min(utilized_amount, contract_tot)
        refundable = max(paid_amount - utilized_amount, 0.0)
        return round(utilized_amount, 2), round(refundable, 2)

    # ── Closure-type vs. contract-end validation ─────────────────────────────
    def _check_closure_requires_contract_end(self, contract):
        """'Release Contract' (normal closure) only makes sense once the
        contract has actually reached its end date. If the selected closing
        date is still before that, the contract hasn't ended yet, so only
        'Termination' (early exit) is a valid choice."""
        end_date = getattr(contract, 'end_date_copy', False) or getattr(contract, 'end_date', False)
        if end_date and self.closing_date and self.termination_type == 'normal' \
                and self.closing_date < end_date:
            raise ValidationError(_(
                "This contract ends on %(end)s. The closing date you selected "
                "(%(close)s) is before that, so the contract has not ended yet — "
                "only 'Termination' is allowed, not 'Release Contract'.",
                end=end_date, close=self.closing_date))

    @api.onchange('closing_date', 'termination_type')
    def _onchange_enforce_termination_type(self):
        contract = self._get_target_contract()
        if not contract or not self.closing_date or self.termination_type != 'normal':
            return
        end_date = getattr(contract, 'end_date_copy', False) or getattr(contract, 'end_date', False)
        if end_date and self.closing_date < end_date:
            self.termination_type = 'early'
            return {
                'warning': {
                    'title': _("Contract Has Not Ended"),
                    'message': _(
                        "This contract ends on %(end)s. Since the closing date "
                        "you selected is before that, only 'Termination' (early "
                        "exit) is allowed — 'Release Contract' can only be used "
                        "once the contract has actually reached its end date."
                    ) % {'end': end_date},
                }
            }

    # ── Validation Rules (Requirement 9) ───────────────────────────────────
    def _validate_termination_and_refund(self, contract):
        """Validate termination constraints prior to execution."""
        # 1. Prevent duplicate termination processing
        if contract.contract_type in ('terminated', 'pre_terminated', 'close'):
            raise ValidationError(_("Contract '%s' has already been terminated.") % contract.display_name)

        existing_audit = self.env['contract.termination.audit'].search([('contract_id', '=', contract.id)], limit=1)
        if existing_audit:
            raise ValidationError(_("Termination settlement audit already exists for contract '%s'. Duplicate termination processing is blocked.") % contract.display_name)

        # 2. Prevent duplicate refund generation
        existing_refund_moves = self.env['account.move'].search([
            ('tenancy_id', '=', contract.id),
            ('refund_component_type', 'in', ('invoice', 'tax', 'deposit'))
        ], limit=1)
        if existing_refund_moves:
            raise ValidationError(_("Refund transactions already exist for contract '%s'. Cannot generate duplicate refunds.") % contract.display_name)

        # 3. Ensure refund never exceeds the invoiced total of the SELECTED
        #    invoice lines (invoice/account side). Computed fresh here so a stale
        #    computed field cannot block a valid refund.
        #
        #    FALLBACK: When invoice lines are present but their amounts are all
        #    zero (e.g. draft/un-stored invoices), we silently switch to the
        #    legacy contract-level cap check to avoid a false "0.00" block.
        sel = self.invoice_selection_ids.filtered('selected') if self.use_invoice_selection else False
        invoiced_total = sum(sel.mapped('total_amount')) if sel else 0.0
        if sel and not invoiced_total:
            invoiced_total = sum(sel.mapped('amount')) + sum(sel.mapped('vat_amount'))
        use_line_validation = bool(sel) and invoiced_total > 0.01

        if use_line_validation:
            refund_total = sum(sel.mapped('refund_amount'))
            if not self.tax_refundable:
                refund_total += sum(sel.mapped('refund_tax_amount'))
            if refund_total > (invoiced_total + 0.01):
                raise ValidationError(_(
                    "Total refund amount (%(total).2f) cannot exceed the invoiced "
                    "total of the selected lines (%(max).2f).",
                    total=refund_total, max=invoiced_total))
        else:
            # Legacy / fallback: cap against paid amount
            allowed_max_refund = self.amount_already_paid + self.deposit_refund_amount
            # When amount_already_paid is also 0 (computed), derive from contract
            if allowed_max_refund < 0.01:
                contract_tot = (
                    getattr(contract, 'contract_value', 0.0)
                    or getattr(contract, 'total_contract_value', 0.0)
                    or getattr(contract, 'total_rent_year', 0.0)
                )
                allowed_max_refund = contract_tot
            if self.total_refund_amount > (allowed_max_refund + 0.01):
                raise ValidationError(_(
                    "Total refund amount (%(total).2f) cannot exceed total amount received (%(max).2f).",
                    total=self.total_refund_amount, max=allowed_max_refund))

        # 4. Security deposit balance check
        contract_deposit = getattr(contract, 'deposit_amount', 0.0)
        if self.deposit_refund_amount > (contract_deposit + 0.01):
            raise ValidationError(_("Security deposit refund amount (%(dep).2f) exceeds contract security deposit balance (%(bal).2f).",
                                  dep=self.deposit_refund_amount, bal=contract_deposit))

        # 5. Prevent negative settlement amounts
        if self.settlement_amount < 0 or self.invoice_refund_amount < 0 or self.tax_refund_amount < 0 or self.deposit_refund_amount < 0:
            raise ValidationError(_("Settlement and refund amounts cannot be negative."))

    # ── Separate Refund Generation Logic (Requirement 4 & 5) ─────────────
    def _generate_separate_refund_entries(self, contract):
        """
        Generates 3 independent refund accounting entries:
          A. Invoice Refund Credit Note
          B. Tax Refund Credit Note / Entry
          C. Security Deposit Refund Entry

        FALLBACK: When invoice lines have zero amounts (e.g. draft invoices
        without stored subtotals), a direct credit note is created using the
        wizard's computed `total_refund_amount` against a resolved income account.
        """
        AccountMove = self.env['account.move']
        company = contract.company_id or self.env.company
        partner_id = contract.tenancy_id.id if hasattr(contract, 'tenancy_id') and contract.tenancy_id else False
        ref_name = contract.tenancy_seq or contract.display_name
        close_d = self.closing_date or fields.Date.today()

        def _lines_for(ctype, default_ctype=None):
            """Build invoice_line_ids from the account-wise component lines of a
            given type, so each invoice line refunds to its OWN account with its
            own analytic distribution."""
            vals = []
            for cl in self.settlement_line_ids.filtered(lambda l: l.component_type == ctype):
                if not cl.amount or cl.amount <= 0:
                    continue
                acct = cl.account_id or self._resolve_component_account(contract, default_ctype or ctype)
                line = {
                    'name': cl.name or _("Refund – %(ref)s", ref=ref_name),
                    'quantity': 1.0,
                    'price_unit': cl.amount,
                    'account_id': acct.id if acct else False,
                }
                if cl.analytic_distribution:
                    line['analytic_distribution'] = cl.analytic_distribution
                vals.append((0, 0, line))
            return vals

        def _base_move(ctype, ref, narration):
            return {
                'move_type': 'out_refund',
                'partner_id': partner_id,
                'invoice_date': close_d,
                'date': close_d,
                'company_id': company.id,
                'tenancy_id': contract.id,
                'refund_component_type': ctype,
                'ref': ref,
                'narration': narration,
            }

        inv_move = tax_move = dep_move = False

        selected = self.invoice_selection_ids.filtered(
            lambda l: l.selected and (l.refund_total or 0.0) > 0.0)

        # ── Never fail silently ─────────────────────────────────────────────
        # If the user ticked lines and expects money back, an empty credit note
        # is a bug, not an outcome. Surface it with the numbers that caused it.
        if self.use_invoice_selection and not selected:
            ticked = self.invoice_selection_ids.filtered('selected')
            if ticked and self.settlement_method != 'no_refund':
                diag = "\n".join(
                    " • %s — billed %.2f, occupied %s/%s days, refund %.2f" % (
                        (l.product_label or l.name
                         or (l.move_line_id.name if l.move_line_id else '')
                         or (l.account_id.display_name if l.account_id else '')
                         or _("unidentified line")),
                        l.total_amount or 0.0, l.used_days, l.period_days,
                        l.refund_total or 0.0)
                    for l in ticked)
                raise UserError(_(
                    "No refundable amount could be calculated, so no credit note "
                    "was created.\n\n"
                    "%(lines)s\n\n"
                    "This usually means the closing date (%(close)s) falls at or "
                    "after the end of every selected line's coverage period, so "
                    "nothing is left unused. Open the ⚙ column picker on the "
                    "invoice lines and check 'Period From' / 'Period To'.",
                    lines=diag, close=close_d))

        # ── SEPARATE REFUND MOVES (Invoice / Tax / Deposit) ─────────────────
        # ── A. Invoice Refund (one line per component line/account) ─────────
        inv_lines = _lines_for('invoice')
        if inv_lines:
            inv_vals = _base_move(
                'invoice',
                _("Invoice Refund – Terminated Contract %(ref)s", ref=ref_name),
                _("Invoice Service Refund for Terminated Contract %(ref)s", ref=ref_name))
            inv_vals['invoice_line_ids'] = inv_lines
            inv_move = AccountMove.sudo().create(inv_vals)

        # ── B. Tax / VAT Refund ─────────────────────────────────────────────
        if not self.tax_refundable:
            tax_lines = _lines_for('tax')
            if tax_lines:
                tax_vals = _base_move(
                    'tax',
                    _("Tax Refund – Terminated Contract %(ref)s", ref=ref_name),
                    _("GST/VAT Tax Refund for Terminated Contract %(ref)s", ref=ref_name))
                tax_vals['invoice_line_ids'] = tax_lines
                tax_move = AccountMove.sudo().create(tax_vals)

        # ── C. Security Deposit Refund ──────────────────────────────────────
        dep_lines = _lines_for('deposit')
        if dep_lines:
            dep_vals = _base_move(
                'deposit',
                _("Security Deposit Refund – Terminated Contract %(ref)s", ref=ref_name),
                _("Security Deposit Refund for Terminated Contract %(ref)s", ref=ref_name))
            dep_vals['invoice_line_ids'] = dep_lines
            dep_move = AccountMove.sudo().create(dep_vals)

        return inv_move, tax_move, dep_move

    # ── Audit Trail Creation (Requirement 8) ──────────────────────────────
    def _create_audit_trail_record(self, contract, inv_move, tax_move, dep_move):
        """Create audit log record in contract.termination.audit."""
        reason_label = dict(
            self._fields['termination_reason_ext'].selection
        ).get(self.termination_reason_ext, self.termination_reason_ext or '')

        audit_vals = {
            'contract_id': contract.id,
            'customer_id': contract.tenancy_id.id if hasattr(contract, 'tenancy_id') and contract.tenancy_id else False,
            'termination_date': self.closing_date or fields.Date.today(),
            'termination_reason': reason_label,
            'settlement_method': self.settlement_method or 'full_month',
            'prorate_days': self.prorate_days or 0,
            'tax_refundable': self.tax_refundable,
            'contract_amount': self.contract_amount,
            'amount_already_paid': self.amount_already_paid,
            'amount_utilized': self.amount_utilized,
            'settlement_amount': self.settlement_amount,
            'prorated_amount': self.prorated_amount,
            'remaining_refund_amount': self.remaining_refund_amount,
            'invoice_refund_amount': self.invoice_refund_amount,
            'tax_refund_amount': self.tax_refund_amount,
            'deposit_refund_amount': self.deposit_refund_amount,
            'total_refund_amount': self.total_refund_amount,
            'user_id': self.env.user.id,
            'execution_datetime': fields.Datetime.now(),
            'invoice_refund_move_id': inv_move.id if inv_move else False,
            'tax_refund_move_id': tax_move.id if tax_move else False,
            'deposit_refund_move_id': dep_move.id if dep_move else False,
        }
        audit_rec = self.env['contract.termination.audit'].create(audit_vals)

        # Log chatter message
        if hasattr(contract, 'message_post'):
            contract.message_post(
                body=_("<b>Contract Termination Settlement Executed</b><br/>"
                       "<b>Termination Date:</b> %s<br/>"
                       "<b>Settlement Method:</b> %s (Prorate Days: %s)<br/>"
                       "<b>Tax Refundable:</b> %s<br/>"
                       "<b>Invoice Refund:</b> %.2f | <b>Tax Refund:</b> %.2f | <b>Deposit Refund:</b> %.2f<br/>"
                       "<b>Total Refund Amount:</b> %.2f AED") % (
                    self.closing_date,
                    dict(self._fields['settlement_method'].selection).get(self.settlement_method, ''),
                    self.prorate_days,
                    "Not Refundable" if self.tax_refundable else "Refundable",
                    self.invoice_refund_amount,
                    self.tax_refund_amount,
                    self.deposit_refund_amount,
                    self.total_refund_amount
                )
            )
        return audit_rec

    # ── Wizard Actions Override ─────────────────────────────────────────────
    def _ensure_invoice_lines_populated(self, contract):
        """
        onchange handlers never fire on button clicks — the server starts with a
        fresh wizard record that has empty One2many lines.  This helper explicitly
        re-runs the population logic so that validation and credit-note generation
        have the correct invoice lines available.
        """
        if not self.invoice_selection_ids:
            self._onchange_populate_invoice_selection()
        # Re-read every line from its source move line and re-apportion against
        # the closing date actually submitted. Never trust the round-trip.
        self._hydrate_invoice_lines(contract)
        # Always rebuild — the component lines must reflect the refreshed
        # refunds, not whatever was rendered before the user changed a date.
        self._onchange_populate_settlement_lines()

    def close_contract_approval(self):
        contract = self._get_target_contract()
        if contract:
            self._check_closure_requires_contract_end(contract)
        if contract and self.termination_type in ('early', 'normal'):
            # Re-populate transient lines that onchange didn't set on button click
            self._ensure_invoice_lines_populated(contract)

            self._validate_termination_and_refund(contract)

            reason_label = dict(
                self._fields['termination_reason_ext'].selection
            ).get(self.termination_reason_ext, '')

            inv_move, tax_move, dep_move = self._generate_separate_refund_entries(contract)
            self._create_audit_trail_record(contract, inv_move, tax_move, dep_move)

            contract.write({
                'settlement_method': self.settlement_method or 'full_month',
                'refund_method': self.refund_method or 'credit_note',
                'termination_date': self.closing_date,
                'termination_reason': reason_label,
                'termination_remarks': self.remarks_ext or '',
                'prorate_days': self.prorate_days,
                'tax_refundable': self.tax_refundable,
                'refund_amount': self.remaining_refund_amount,
                'invoice_refund_amount': self.invoice_refund_amount,
                'tax_refund_amount': self.tax_refund_amount,
                'deposit_refund_amount': self.deposit_refund_amount,
                'total_refund_amount': self.total_refund_amount,
            })

        return super().close_contract_approval()

    def action_close_contract(self):
        contract = self._get_target_contract()
        if contract:
            self._check_closure_requires_contract_end(contract)

        result = super().action_close_contract()
        if not contract:
            return result

        if self.termination_type in ('early', 'normal'):
            # Re-populate transient lines that onchange didn't set on button click
            self._ensure_invoice_lines_populated(contract)

            self._validate_termination_and_refund(contract)

            reason_label = dict(
                self._fields['termination_reason_ext'].selection
            ).get(self.termination_reason_ext, '')

            inv_move, tax_move, dep_move = self._generate_separate_refund_entries(contract)
            self._create_audit_trail_record(contract, inv_move, tax_move, dep_move)

            contract.write({
                'settlement_method': self.settlement_method or 'full_month',
                'refund_method': self.refund_method or 'credit_note',
                'termination_date': self.closing_date,
                'termination_reason': reason_label,
                'termination_remarks': self.remarks_ext or '',
                'prorate_days': self.prorate_days,
                'tax_refundable': self.tax_refundable,
                'refund_amount': self.remaining_refund_amount,
                'invoice_refund_amount': self.invoice_refund_amount,
                'tax_refund_amount': self.tax_refund_amount,
                'deposit_refund_amount': self.deposit_refund_amount,
                'total_refund_amount': self.total_refund_amount,
            })

        return result
