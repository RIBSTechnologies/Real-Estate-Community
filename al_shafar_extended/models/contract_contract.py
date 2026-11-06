# -*- coding: utf-8 -*-

from datetime import datetime, date
from dateutil.relativedelta import relativedelta
import calendar

from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError


class ContractContract(models.Model):
    _name = 'contract.contract'
    _description = 'Customer Contract'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'id desc'

    name = fields.Char(
        string="Contract Reference",
        required=True,
        copy=False,
        readonly=True,
        default=lambda self: _('New')
    )
    partner_id = fields.Many2one(
        'res.partner',
        string="Customer / Partner",
        required=True,
        tracking=True,
        index=True
    )
    start_date = fields.Date(
        string="Contract Start Date",
        required=True,
        tracking=True
    )
    end_date = fields.Date(
        string="Contract End Date",
        required=True,
        tracking=True
    )
    monthly_rent = fields.Monetary(
        string="Monthly Rate / Rent",
        required=True,
        tracking=True,
        currency_field='currency_id'
    )
    total_contract_value = fields.Monetary(
        string="Total Contract Value",
        compute='_compute_total_contract_value',
        store=True,
        currency_field='currency_id'
    )

    company_id = fields.Many2one(
        'res.company',
        string="Company",
        required=True,
        default=lambda self: self.env.company
    )
    currency_id = fields.Many2one(
        'res.currency',
        string="Currency",
        related='company_id.currency_id',
        readonly=True
    )

    state = fields.Selection([
        ('draft', 'Draft'),
        ('in_progress', 'In Progress'),
        ('terminated', 'Terminated'),
        ('closed', 'Closed')
    ], string="Contract Status", default='in_progress', tracking=True, required=True)

    settlement_method = fields.Selection([
        ('full_month', 'Full Month (Charge full month when started)'),
        ('prorated', 'Prorated by Days'),
        ('no_refund_after_month_starts', 'No Refund After Month Starts')
    ], string="Settlement Method", default=lambda self: self.env.company.settlement_method or 'full_month',
       help="Policy used for calculating prepaid contract refunds on early termination.")

    # Termination Details
    termination_date = fields.Date(string="Termination Date", tracking=True)
    termination_reason = fields.Char(string="Termination Reason", tracking=True)
    termination_remarks = fields.Text(string="Termination Remarks")

    # Linked Documents
    invoice_ids = fields.One2many(
        'account.move',
        'contract_id',
        string="Invoices & Credit Notes"
    )
    move_count = fields.Integer(string="Invoice Count", compute='_compute_move_counts')
    refund_count = fields.Integer(string="Refund Count", compute='_compute_move_counts')

    # Financial & Refund Tracking Fields (Requirement 7)
    total_paid_amount = fields.Monetary(
        string="Total Amount Paid",
        compute='_compute_financial_summary',
        store=True,
        currency_field='currency_id'
    )
    total_utilized_amount = fields.Monetary(
        string="Amount Utilized",
        compute='_compute_financial_summary',
        store=True,
        currency_field='currency_id'
    )
    refund_amount = fields.Monetary(
        string="Calculated Refund Amount",
        tracking=True,
        currency_field='currency_id'
    )
    refunded_amount = fields.Monetary(
        string="Refunded Amount",
        compute='_compute_financial_summary',
        store=True,
        currency_field='currency_id'
    )
    balance_refund = fields.Monetary(
        string="Balance Refund",
        compute='_compute_financial_summary',
        store=True,
        currency_field='currency_id'
    )
    refund_status = fields.Selection([
        ('no_refund', 'No Refund'),
        ('pending', 'Pending'),
        ('refunded', 'Refunded'),
        ('partially_refunded', 'Partially Refunded')
    ], string="Refund Status", default='no_refund', compute='_compute_financial_summary', store=True, tracking=True)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code('contract.contract') or _('New')
        return super(ContractContract, self).create(vals_list)

    @api.depends('start_date', 'end_date', 'monthly_rent')
    def _compute_total_contract_value(self):
        for rec in self:
            if rec.start_date and rec.end_date and rec.monthly_rent:
                # Calculate approximate total months or exact duration
                d1 = rec.start_date
                d2 = rec.end_date
                months = (d2.year - d1.year) * 12 + (d2.month - d1.month) + 1
                rec.total_contract_value = max(months, 1) * rec.monthly_rent
            else:
                rec.total_contract_value = 0.0

    @api.depends('invoice_ids', 'invoice_ids.state', 'invoice_ids.move_type')
    def _compute_move_counts(self):
        for rec in self:
            rec.move_count = len(rec.invoice_ids.filtered(lambda m: m.move_type in ('out_invoice', 'out_receipt')))
            rec.refund_count = len(rec.invoice_ids.filtered(lambda m: m.move_type == 'out_refund'))

    @api.depends('invoice_ids', 'invoice_ids.state', 'invoice_ids.amount_total',
                 'state', 'termination_date', 'refund_amount')
    def _compute_financial_summary(self):
        for rec in self:
            # 1. Total Paid Amount from posted customer invoices/receipts
            posted_invoices = rec.invoice_ids.filtered(lambda m: m.state == 'posted' and m.move_type in ('out_invoice', 'entry', 'out_receipt'))
            # Paid amount: total minus residual
            total_paid = sum(inv.amount_total - inv.amount_residual for inv in posted_invoices)

            # Also check direct customer payments linked to contract or partner
            rec.total_paid_amount = total_paid

            # 2. Utilized Amount calculation
            term_date = rec.termination_date or rec.end_date or fields.Date.today()
            if rec.start_date and rec.end_date and rec.monthly_rent:
                util_amt, calc_refund = rec.calculate_utilized_and_refund(
                    termination_date=term_date,
                    settlement_method=rec.settlement_method or 'full_month',
                    paid_amount=total_paid
                )
                rec.total_utilized_amount = util_amt
                if not rec.refund_amount and rec.state == 'terminated':
                    rec.refund_amount = calc_refund
            else:
                rec.total_utilized_amount = 0.0

            # 3. Actually Refunded Amount — credit notes + outbound payments
            posted_refunds = rec.invoice_ids.filtered(lambda m: m.state == 'posted' and m.move_type == 'out_refund')
            credit_note_total = sum(rf.amount_total for rf in posted_refunds)

            posted_payments = self.env['account.payment'].search([
                ('state', '=', 'posted'),
                ('payment_type', '=', 'outbound'),
                ('partner_id', '=', rec.partner_id.id),
                ('memo', 'ilike', rec.name if rec.name and rec.name != 'New' else '__no_match__'),
            ])
            payment_total = sum(p.amount for p in posted_payments)
            rec.refunded_amount = credit_note_total + payment_total

            # 4. Balance Refund
            rec.balance_refund = max(rec.refund_amount - rec.refunded_amount, 0.0)

            # 5. Refund Status
            if rec.refund_amount <= 0:
                rec.refund_status = 'no_refund'
            elif rec.refunded_amount >= rec.refund_amount:
                rec.refund_status = 'refunded'
            elif rec.refunded_amount > 0 and rec.refunded_amount < rec.refund_amount:
                rec.refund_status = 'partially_refunded'
            else:
                rec.refund_status = 'pending'

    def calculate_utilized_and_refund(self, termination_date, settlement_method='full_month', paid_amount=None):
        """
        Calculates the utilized (earned) service amount and the refundable unused advance.

        Scenario Example:
        Start Date: 01/08/2026, End Date: 31/10/2026, Rent: 10,000/mo. Total Paid: 30,000
        Term Date: 15/09/2026

        If 'full_month': August (10k) + September (10k) = 20,000 utilized. Refund = 30,000 - 20,000 = 10,000.
        If 'prorated': August (10k) + September 15 days (5k) = 15,000 utilized. Refund = 30,000 - 15,000 = 15,000.
        """
        self.ensure_one()
        if not self.start_date or not self.end_date or not self.monthly_rent:
            return 0.0, 0.0

        total_paid = paid_amount if paid_amount is not None else self.total_paid_amount

        # Restrict termination date within contract bounds for calculation logic
        term_d = min(max(termination_date, self.start_date), self.end_date)
        start_d = self.start_date

        utilized_amount = 0.0

        if settlement_method == 'prorated':
            # Daily prorated calculation
            current_m = start_d.replace(day=1)
            end_m = self.end_date.replace(day=1)

            while current_m <= end_m:
                # Get start and end of this month
                _, last_day = calendar.monthrange(current_m.year, current_m.month)
                month_start = current_m
                month_end = current_m.replace(day=last_day)

                if term_d >= month_end:
                    # Full month consumed
                    utilized_amount += self.monthly_rent
                elif term_d < month_start:
                    # Month not started at all (future month)
                    pass
                else:
                    # Month in progress on termination date
                    days_in_month = last_day
                    days_used = (term_d - month_start).days + 1
                    month_charge = (days_used / float(days_in_month)) * self.monthly_rent
                    utilized_amount += month_charge

                current_m += relativedelta(months=1)

        elif settlement_method in ('full_month', 'no_refund_after_month_starts'):
            # Full month charged if month has started
            current_m = start_d.replace(day=1)
            end_m = self.end_date.replace(day=1)

            while current_m <= end_m:
                _, last_day = calendar.monthrange(current_m.year, current_m.month)
                month_start = current_m
                month_end = current_m.replace(day=last_day)

                if term_d >= month_start:
                    # Month started or fully passed -> charge full month
                    utilized_amount += self.monthly_rent
                current_m += relativedelta(months=1)

        # Cap utilized amount at total contract value
        utilized_amount = min(utilized_amount, self.total_contract_value)

        # Refundable amount is unused advance paid
        refundable = max(total_paid - utilized_amount, 0.0)

        return round(utilized_amount, 2), round(refundable, 2)

    def action_open_termination_wizard(self):
        """Open the Contract Termination Wizard."""
        self.ensure_one()
        if self.state == 'terminated':
            raise UserError(_("This contract is already terminated."))

        return {
            'name': _('Terminate Contract & Process Refund'),
            'type': 'ir.actions.act_window',
            'res_model': 'contract.termination.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_contract_id': self.id,
                'default_termination_date': fields.Date.today(),
                'default_settlement_method': self.settlement_method or self.env.company.settlement_method or 'full_month',
            }
        }

    def action_view_invoices(self):
        """Smart button action to view linked customer invoices."""
        self.ensure_one()
        invoices = self.invoice_ids.filtered(lambda m: m.move_type in ('out_invoice', 'out_receipt'))
        action = self.env.ref('account.action_move_out_invoice_type').read()[0]
        if len(invoices) == 1:
            action['views'] = [(self.env.ref('account.view_move_form').id, 'form')]
            action['res_id'] = invoices.id
        else:
            action['domain'] = [('id', 'in', invoices.ids)]
        return action

    def action_view_refunds(self):
        """Smart button action to view linked credit notes / refund entries."""
        self.ensure_one()
        refunds = self.invoice_ids.filtered(lambda m: m.move_type == 'out_refund')
        action = self.env.ref('account.action_move_out_refund_type').read()[0]
        if len(refunds) == 1:
            action['views'] = [(self.env.ref('account.view_move_form').id, 'form')]
            action['res_id'] = refunds.id
        else:
            action['domain'] = [('id', 'in', refunds.ids)]
        return action
