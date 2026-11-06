# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import ValidationError


class TenancyDetails(models.Model):
    _inherit = 'tenancy.details'

    def action_open_contract_reminder_wizard(self):
        """Opens the "Send Contract Renewal Reminder" wizard (wizard/
        contract_reminder_wizard.py) for the contracts selected in the
        Contracts list - bound to a <header> button there (views/
        tenancy_details_inherit_views.xml) rather than the list's Action
        menu, so it's a standalone button next to "New" instead of hidden
        in the gear dropdown.

        Creates the wizard (and its lines) server-side via
        create_for_contracts() and opens it by res_id, rather than letting
        the web client create it on the form's first save via
        default_get() - see that method's docstring for why."""
        wizard = self.env['contract.reminder.wizard'].create_for_contracts(self)
        return {
            'type': 'ir.actions.act_window',
            'name': _('Send Contract Renewal Reminder'),
            'res_model': 'contract.reminder.wizard',
            'res_id': wizard.id,
            'view_mode': 'form',
            'target': 'new',
        }

    def _get_invoice_qty_price(self):
        """ribs_real_estate prices each recurring installment (and the
        active-contract Full Payment invoice) off total_rent_year - the
        UNIT'S FULL YEARLY RENT - instead of this contract's contract_value
        (which is correctly prorated to its actual duration). For a contract
        shorter than a year (e.g. 6 months on a 10,000/year unit), that
        overcharges every installment by the ratio of a year to the actual
        duration. Same method, but priced from contract_value."""
        duration_months = self.duration_id.month
        total_amount = self.contract_value
        term = self.payment_term

        if not duration_months:
            raise ValidationError(_("Contract duration is missing."))

        term_month_map = {
            'monthly': 1,
            'every_two_months': 2,
            'every_four_months': 4,
            'quarterly': 3,
            'half_year': 6,
            'year': 12,
        }

        if term == 'full_payment':
            return 1, round(total_amount, 2)

        if term == 'daily':
            if self.is_by_date:
                if not self.start_date or not self.end_date:
                    raise ValidationError(_("Please set the contract start and end dates."))
                duration_days = (self.end_date - self.start_date).days + 1
            else:
                duration_days = self.duration_id.month

            if not duration_days:
                raise ValidationError(_("Contract duration is missing."))

            return duration_days, round(total_amount / duration_days, 2)

        term_months = term_month_map[term]
        qty = duration_months // term_months
        price = round(total_amount / qty, 2)
        return qty, price

    settlement_method = fields.Selection([
        ('full_month', 'Full Month (Charge full month when started)'),
        ('prorated', 'Prorated by Days'),
        ('no_refund_after_month_starts', 'No Refund After Month Starts')
    ], string="Settlement Policy", default=lambda self: self.env.company.settlement_method or 'full_month',
       help="Policy used for calculating prepaid contract refunds on early termination.")

    termination_date = fields.Date(string="Termination Date", tracking=True)
    termination_reason = fields.Char(string="Termination Reason", tracking=True)
    termination_remarks = fields.Text(string="Termination Remarks")
    refund_method = fields.Selection([
        ('credit_note', 'Credit Note (Customer Refund Invoice)'),
        ('customer_refund', 'Direct Customer Payment Refund'),
        ('wallet_credit', 'Wallet / Customer Credit Balance Entry'),
    ], string="Refund Method", default='credit_note',
       help="Method used to refund the prepaid unused amount on early termination.")

    refund_amount = fields.Monetary(string="Calculated Refund Amount", currency_field='currency_id', tracking=True)
    refunded_amount = fields.Monetary(string="Refunded Amount", compute='_compute_tenancy_financial_summary', store=False, currency_field='currency_id')
    balance_refund = fields.Monetary(string="Balance Refund", compute='_compute_tenancy_financial_summary', store=False, currency_field='currency_id')
    refund_status = fields.Selection([
        ('no_refund', 'No Refund'),
        ('pending', 'Pending'),
        ('refunded', 'Refunded'),
        ('partially_refunded', 'Partially Refunded')
    ], string="Refund Status", default='no_refund', compute='_compute_tenancy_financial_summary', store=False, tracking=True)

    total_paid_amount = fields.Monetary(string="Total Amount Paid", compute='_compute_tenancy_financial_summary', store=False, currency_field='currency_id')
    total_utilized_amount = fields.Monetary(string="Amount Utilized", compute='_compute_tenancy_financial_summary', store=False, currency_field='currency_id')

    # ── Detailed Refund Components & Statuses ────────────────────────────────
    prorate_days = fields.Integer(string="Prorate Days", default=0)
    tax_refundable = fields.Boolean(string="Tax Refundable Option", help="Checked = Tax Not Refundable; Unchecked = Tax Refundable")

    invoice_refund_amount = fields.Monetary(string="Invoice Refund Amount", currency_field='currency_id', tracking=True)
    tax_refund_amount = fields.Monetary(string="Tax Refund Amount", currency_field='currency_id', tracking=True)
    deposit_refund_amount = fields.Monetary(string="Security Deposit Refund Amount", currency_field='currency_id', tracking=True)
    total_refund_amount = fields.Monetary(string="Total Refund Amount", currency_field='currency_id', tracking=True)

    invoice_refund_status = fields.Selection([
        ('pending', 'Pending'),
        ('partially_refunded', 'Partially Refunded'),
        ('refunded', 'Refunded'),
    ], string="Invoice Refund Status", default='pending', compute='_compute_detailed_refund_statuses', store=False, tracking=True)

    tax_refund_status = fields.Selection([
        ('pending', 'Pending'),
        ('refunded', 'Refunded'),
        ('not_applicable', 'Not Applicable'),
    ], string="Tax Refund Status", default='not_applicable', compute='_compute_detailed_refund_statuses', store=False, tracking=True)

    deposit_refund_status = fields.Selection([
        ('pending', 'Pending'),
        ('partially_refunded', 'Partially Refunded'),
        ('refunded', 'Refunded'),
    ], string="Security Deposit Refund Status", default='pending', compute='_compute_detailed_refund_statuses', store=False, tracking=True)

    overall_refund_status = fields.Selection([
        ('no_refund', 'No Refund'),
        ('pending', 'Pending'),
        ('partially_refunded', 'Partially Refunded'),
        ('fully_refunded', 'Fully Refunded'),
    ], string="Overall Refund Status", default='no_refund', compute='_compute_detailed_refund_statuses', store=False, tracking=True)

    # ── Smart Button Counts ──────────────────────────────────────────────────
    invoice_refund_count = fields.Integer(string="Invoice Refunds Count", compute='_compute_refund_counts')
    tax_refund_count = fields.Integer(string="Tax Refunds Count", compute='_compute_refund_counts')
    deposit_refund_count = fields.Integer(string="Deposit Refunds Count", compute='_compute_refund_counts')
    refund_summary_count = fields.Integer(string="Total Refund Entries Count", compute='_compute_refund_counts')
    registered_pdc_count = fields.Integer(string="Registered PDC Count", compute='_compute_registered_pdc_count')
    returned_pdc_count = fields.Integer(string="Returned PDC Count", compute='_compute_returned_pdc_count')

    # The renewal link is only ever stored in ONE direction: renewing a
    # contract (ribs_real_estate's contract_wizard.contract_action / OCA
    # group_multi_contracts.py, both on "confirm renewal") sets
    # new_contract_id on the OLD contract to point at the freshly created
    # one - there's no field going the other way (extend_from on the new
    # contract is only a plain Char of the old one's tenancy_seq, not a
    # relation). This is just that link read backwards, for a smart button
    # on the new contract pointing back to where it came from.
    original_contract_id = fields.Many2one(
        'tenancy.details', string="Original Contract", compute='_compute_original_contract_id')

    @api.depends('rent_invoice_ids', 'contract_type', 'termination_date', 'refund_amount',
                 'invoice_refund_amount', 'tax_refund_amount', 'deposit_refund_amount', 'total_refund_amount')
    def _compute_tenancy_financial_summary(self):
        AccountMove = self.env['account.move']
        AccountPayment = self.env['account.payment']
        for rec in self:
            total_paid = 0.0
            if hasattr(rec, 'rent_invoice_ids') and rec.rent_invoice_ids:
                paid_inv = rec.rent_invoice_ids.filtered(lambda r: r.rent_invoice_id and r.rent_invoice_id.state == 'posted')
                total_paid = sum(r.amount for r in paid_inv if r.rent_invoice_id.payment_state in ('paid', 'in_payment'))
            
            if not total_paid and hasattr(rec, 'contract_payment_ids') and rec.contract_payment_ids:
                rec_payments = rec.contract_payment_ids.filtered(lambda p: p.payments_received == 'received')
                total_paid = sum(p.amount for p in rec_payments)

            if not total_paid and rec.contract_value:
                total_paid = rec.contract_value

            rec.total_paid_amount = total_paid

            term_date = rec.termination_date or rec.end_date or fields.Date.today()
            dur_months = rec.duration_id.month if (hasattr(rec, 'duration_id') and rec.duration_id) else 12
            monthly_rent = (rec.total_rent_year / 12.0) if (hasattr(rec, 'total_rent_year') and rec.total_rent_year) else ((rec.contract_value / max(dur_months or 1, 1)) if rec.contract_value else 0.0)

            if rec.start_date and rec.end_date and monthly_rent:
                util_amt, calc_refund = rec.calculate_tenancy_utilized_and_refund(
                    termination_date=term_date,
                    settlement_method=rec.settlement_method or 'full_month',
                    paid_amount=total_paid,
                    monthly_rent=monthly_rent
                )
                rec.total_utilized_amount = util_amt
                if not rec.refund_amount and rec.contract_type in ('terminated', 'pre_terminated'):
                    rec.refund_amount = calc_refund
            else:
                rec.total_utilized_amount = 0.0

            # Sum refunded amount from credit notes & refund moves
            seq = rec.tenancy_seq or ''
            domain = [
                ('state', '=', 'posted'),
                ('move_type', 'in', ('out_refund', 'entry')),
            ]
            if seq:
                domain.append('|')
                domain.append(('tenancy_id', '=', rec.id))
                domain.append('|')
                domain.append(('ref', 'ilike', seq))
                domain.append(('narration', 'ilike', seq))
            else:
                domain.append(('tenancy_id', '=', rec.id))

            posted_refunds = AccountMove.search(domain)
            credit_note_total = sum(rf.amount_total for rf in posted_refunds)

            posted_payments = AccountPayment.search([
                ('state', '=', 'posted'),
                ('payment_type', '=', 'outbound'),
                ('memo', 'ilike', seq if seq else '__no_match__'),
            ])
            payment_total = sum(p.amount for p in posted_payments)

            rec.refunded_amount = credit_note_total + payment_total
            rec.balance_refund = max((rec.total_refund_amount or rec.refund_amount) - rec.refunded_amount, 0.0)

            target_refund = rec.total_refund_amount or rec.refund_amount
            if target_refund <= 0:
                rec.refund_status = 'no_refund'
            elif rec.refunded_amount >= target_refund:
                rec.refund_status = 'refunded'
            elif rec.refunded_amount > 0:
                rec.refund_status = 'partially_refunded'
            else:
                rec.refund_status = 'pending'

    @api.depends('invoice_refund_amount', 'tax_refund_amount', 'deposit_refund_amount', 'total_refund_amount', 'contract_type')
    def _compute_detailed_refund_statuses(self):
        AccountMove = self.env['account.move']
        for rec in self:
            if rec.contract_type not in ('terminated', 'pre_terminated', 'close') and rec.total_refund_amount <= 0:
                rec.invoice_refund_status = 'pending'
                rec.tax_refund_status = 'not_applicable'
                rec.deposit_refund_status = 'pending'
                rec.overall_refund_status = 'no_refund'
                continue

            seq = rec.tenancy_seq or ''
            domain = [('state', '=', 'posted')]
            if seq:
                domain.append('|')
                domain.append(('tenancy_id', '=', rec.id))
                domain.append('|')
                domain.append(('ref', 'ilike', seq))
                domain.append(('narration', 'ilike', seq))
            else:
                domain.append(('tenancy_id', '=', rec.id))

            moves = AccountMove.search(domain)

            # Invoice refund moves
            inv_moves = moves.filtered(lambda m: m.refund_component_type == 'invoice' or 'Invoice Refund' in (m.ref or '') or 'Invoice Refund' in (m.narration or ''))
            posted_inv_amt = sum(m.amount_total for m in inv_moves)
            if rec.invoice_refund_amount <= 0:
                rec.invoice_refund_status = 'refunded'
            elif posted_inv_amt >= (rec.invoice_refund_amount - 0.01):
                rec.invoice_refund_status = 'refunded'
            elif posted_inv_amt > 0:
                rec.invoice_refund_status = 'partially_refunded'
            else:
                rec.invoice_refund_status = 'pending'

            # Tax refund moves
            tax_moves = moves.filtered(lambda m: m.refund_component_type == 'tax' or 'Tax Refund' in (m.ref or '') or 'Tax Refund' in (m.narration or ''))
            posted_tax_amt = sum(m.amount_total for m in tax_moves)
            if rec.tax_refund_amount <= 0 or rec.tax_refundable:
                rec.tax_refund_status = 'not_applicable'
            elif posted_tax_amt >= (rec.tax_refund_amount - 0.01):
                rec.tax_refund_status = 'refunded'
            elif posted_tax_amt > 0:
                rec.tax_refund_status = 'refunded'
            else:
                rec.tax_refund_status = 'pending'

            # Deposit refund moves
            dep_moves = moves.filtered(lambda m: m.refund_component_type == 'deposit' or 'Deposit Refund' in (m.ref or '') or 'Deposit Refund' in (m.narration or ''))
            posted_dep_amt = sum(m.amount_total for m in dep_moves)
            if rec.deposit_refund_amount <= 0:
                rec.deposit_refund_status = 'refunded'
            elif posted_dep_amt >= (rec.deposit_refund_amount - 0.01):
                rec.deposit_refund_status = 'refunded'
            elif posted_dep_amt > 0:
                rec.deposit_refund_status = 'partially_refunded'
            else:
                rec.deposit_refund_status = 'pending'

            # Overall Status
            all_posted_amt = posted_inv_amt + posted_tax_amt + posted_dep_amt
            if rec.total_refund_amount <= 0:
                rec.overall_refund_status = 'no_refund'
            elif all_posted_amt >= (rec.total_refund_amount - 0.01):
                rec.overall_refund_status = 'fully_refunded'
            elif all_posted_amt > 0:
                rec.overall_refund_status = 'partially_refunded'
            else:
                rec.overall_refund_status = 'pending'

    def _compute_refund_counts(self):
        AccountMove = self.env['account.move']
        for rec in self:
            moves = AccountMove.search([('tenancy_id', '=', rec.id)])
            rec.invoice_refund_count = len(moves.filtered(lambda m: m.refund_component_type == 'invoice'))
            rec.tax_refund_count = len(moves.filtered(lambda m: m.refund_component_type == 'tax'))
            rec.deposit_refund_count = len(moves.filtered(lambda m: m.refund_component_type == 'deposit'))
            rec.refund_summary_count = len(moves.filtered(lambda m: m.refund_component_type in ('invoice', 'tax', 'deposit')))

    def action_view_invoice_refunds(self):
        self.ensure_one()
        action = self.env.ref('account.action_move_out_refund_type').read()[0]
        action['domain'] = [('tenancy_id', '=', self.id), ('refund_component_type', '=', 'invoice')]
        action['context'] = {'default_tenancy_id': self.id, 'default_move_type': 'out_refund', 'default_refund_component_type': 'invoice'}
        return action

    def action_view_tax_refunds(self):
        self.ensure_one()
        action = self.env.ref('account.action_move_out_refund_type').read()[0]
        action['domain'] = [('tenancy_id', '=', self.id), ('refund_component_type', '=', 'tax')]
        action['context'] = {'default_tenancy_id': self.id, 'default_move_type': 'out_refund', 'default_refund_component_type': 'tax'}
        return action

    def action_view_deposit_refunds(self):
        self.ensure_one()
        action = self.env.ref('account.action_move_journal_line').read()[0]
        action['domain'] = [('tenancy_id', '=', self.id), ('refund_component_type', '=', 'deposit')]
        action['context'] = {'default_tenancy_id': self.id, 'default_refund_component_type': 'deposit'}
        return action

    def action_view_refund_summary(self):
        self.ensure_one()
        action = self.env.ref('account.action_move_journal_line').read()[0]
        action['domain'] = [('tenancy_id', '=', self.id), ('refund_component_type', 'in', ('invoice', 'tax', 'deposit'))]
        action['context'] = {'default_tenancy_id': self.id}
        return action

    def _compute_registered_pdc_count(self):
        PdcWizard = self.env['pdc.wizard']
        for rec in self:
            rec.registered_pdc_count = PdcWizard.search_count([
                ('tenancy_id', '=', rec.id),
                ('state', '=', 'registered'),
            ])

    def action_view_registered_pdc(self):
        """Registered PDC cheques for this contract only. Tick rows and use
        the existing 'Return The Checks' list action (sh_pdc) to return
        them - no separate return screen needed here."""
        self.ensure_one()
        action = self.env.ref('sh_pdc.sh_pdc_payment_menu_action').read()[0]
        action['domain'] = [('tenancy_id', '=', self.id), ('state', '=', 'registered')]
        action['context'] = {}
        return action

    def _compute_returned_pdc_count(self):
        PdcWizard = self.env['pdc.wizard']
        for rec in self:
            rec.returned_pdc_count = PdcWizard.search_count([
                ('tenancy_id', '=', rec.id),
                ('state', '=', 'returned'),
            ])

    def action_view_returned_pdc(self):
        """Returned PDC cheques for this contract only."""
        self.ensure_one()
        action = self.env.ref('sh_pdc.sh_pdc_payment_menu_action').read()[0]
        action['domain'] = [('tenancy_id', '=', self.id), ('state', '=', 'returned')]
        action['context'] = {}
        return action

    @api.depends('new_contract_id')
    def _compute_original_contract_id(self):
        """No dependency actually lives on rec itself - this is a REVERSE
        lookup (which OTHER contract has new_contract_id == rec.id) - so
        there's nothing on rec's own field graph to truly depend on.
        Depending on new_contract_id (present on every record via the same
        field, just normally empty on a freshly-renewed contract) is only
        here to satisfy the ORM's "a compute method must depend on
        something" requirement; it's recomputed on every read regardless."""
        for rec in self:
            rec.original_contract_id = self.search([('new_contract_id', '=', rec.id)], limit=1)

    def action_view_original_contract(self):
        """Smart button target - opens the contract this one was renewed
        from (original_contract_id above)."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Original Contract'),
            'res_model': 'tenancy.details',
            'res_id': self.original_contract_id.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def calculate_tenancy_utilized_and_refund(self, termination_date, settlement_method='full_month', paid_amount=0.0, monthly_rent=0.0):
        self.ensure_one()
        if not self.start_date or not self.end_date or not monthly_rent:
            return 0.0, 0.0

        term_d = min(max(termination_date, self.start_date), self.end_date)
        start_d = self.start_date
        utilized_amount = 0.0

        import calendar
        from dateutil.relativedelta import relativedelta
        current_m = start_d.replace(day=1)
        end_m = self.end_date.replace(day=1)

        if settlement_method == 'prorated':
            while current_m <= end_m:
                _, last_day = calendar.monthrange(current_m.year, current_m.month)
                month_start = current_m
                month_end = current_m.replace(day=last_day)
                if term_d >= month_end:
                    utilized_amount += monthly_rent
                elif term_d < month_start:
                    pass
                else:
                    days_in_month = last_day
                    days_used = (term_d - month_start).days + 1
                    utilized_amount += (days_used / float(days_in_month)) * monthly_rent
                current_m += relativedelta(months=1)

        elif settlement_method in ('full_month', 'no_refund_after_month_starts'):
            while current_m <= end_m:
                _, last_day = calendar.monthrange(current_m.year, current_m.month)
                month_start = current_m
                if term_d >= month_start:
                    utilized_amount += monthly_rent
                current_m += relativedelta(months=1)

        contract_tot = self.contract_value or getattr(self, 'total_contract_value', 0.0) or (monthly_rent * 12)
        utilized_amount = min(utilized_amount, contract_tot)
        refundable = max(paid_amount - utilized_amount, 0.0)
        return round(utilized_amount, 2), round(refundable, 2)

    def action_contract_close(self):
        """
        Pre-Close Validation Flow:
          1. Check all contract invoices — any Amount Due > 0 → show validation details.
          2. Check all related cheques (PDC lines) — any NOT in Done/Deposited → show details.
          3. All clear → open Close Contract wizard.
        """
        self.ensure_one()

        # ── STEP 1: Invoice Check (must be Posted AND Amount Due = 0) ────────
        # Fetch ALL customer invoices linked to this contract
        all_invoices = self.env['account.move'].search([
            ('tenancy_id', '=', self.id),
            ('move_type', '=', 'out_invoice'),
        ])

        problem_invoices = []
        for inv in all_invoices:
            if inv.state != 'posted':
                problem_invoices.append(
                    f"• {inv.name or '(Draft)'} — "
                    f"Status: {inv.state.capitalize()} "
                    f"(must be Posted)"
                )
            elif inv.amount_residual > 0.01:
                problem_invoices.append(
                    f"• {inv.name} — "
                    f"Amount Due: {inv.currency_id.symbol}{inv.amount_residual:,.2f} "
                    f"(must be 0.00)"
                )

        if problem_invoices:
            raise ValidationError(_(
                "All contract invoices must be Posted and fully paid (Amount Due = 0) "
                "before closing the contract.\n\n"
                "The following invoices need attention:\n\n"
                + "\n".join(problem_invoices)
            ))

        # ── STEP 2: Cheque / PDC Status Check ───────────────────────────────
        SAFE_STATES = {'done', 'deposited', 'registered'}
        bad_cheques = []
        for payment_line in self.contract_payment_ids:
            pdc = payment_line.payment_pdc_id
            if pdc and pdc.state not in SAFE_STATES:
                bad_cheques.append(
                    f"• Cheque {payment_line.cheque_num or pdc.display_name} — "
                    f"Amount: {payment_line.currency_id.symbol}{payment_line.amount:,.2f} "
                    f"| Status: {dict(pdc._fields['state'].selection).get(pdc.state, pdc.state)}"
                )

        if bad_cheques:
            msg = (
                "The following cheques are not yet Posted/Done.\n"
                "Please ensure all cheques are cleared before closing the contract:\n\n"
                + "\n".join(bad_cheques)
            )
            raise ValidationError(_(msg))

        # ── STEP 3: All Checks Passed → Open Close Contract Wizard ──────────
        is_early = self.days_left > 0
        closing_date = fields.Date.today() if is_early else self.end_date

        return {
            'name': _('Close Contract'),
            'type': 'ir.actions.act_window',
            'view_mode': 'form',
            'res_model': 'contract.closing.wizard',
            'target': 'new',
            'context': {
                'default_contract_id': self.id,
                'default_termination_type': 'early' if is_early else 'normal',
                'default_closing_date': closing_date,
            },
        }

    # ── Security Deposit Refund on approved closure ─────────────────────────
    # closure_final_approval() (ribs_real_estate) is where a "Release
    # Contract" closure actually gets finalized once approved — it sets
    # contract_type to 'terminated' directly and never goes through the
    # Close Contract wizard's action_close_contract/close_contract_approval
    # at all. The wizard-side deposit-refund logic (ContractClosingWizard
    # Extended) never runs on this path, so it needs the same "refund the
    # deposit as a credit note" behaviour added here too.
    def _create_deposit_refund_credit_note(self):
        """Refund the security deposit in full (minus a penalty, if any)
        via a credit note, for a normal (non-early) closure. Returns the
        created account.move, or False if there is nothing to refund."""
        self.ensure_one()
        if not self.is_any_deposit or not self.deposit_amount:
            return False

        existing = self.env['account.move'].search([
            ('tenancy_id', '=', self.id),
            ('refund_component_type', '=', 'deposit'),
        ], limit=1)
        if existing:
            return existing

        penalty = round(self.penalty_amount or 0.0, 2) if self.if_penalty else 0.0
        deposit_amount = self.deposit_amount or 0.0
        net_refund = max(round(deposit_amount - penalty, 2), 0.0)
        if net_refund <= 0:
            return False

        company = self.company_id or self.env.company
        account = self.deposit_item_id.property_account_income_id if self.deposit_item_id else False
        if not account:
            account = self.env['account.account'].search([
                ('account_type', '=', 'liability_current'),
                ('name', 'ilike', 'deposit'),
                ('company_ids', 'in', [company.id]),
            ], limit=1)

        ref_name = self.tenancy_seq or self.display_name
        dep_move = self.env['account.move'].sudo().create({
            'move_type': 'out_refund',
            'partner_id': self.tenancy_id.id,
            'invoice_date': self.closing_date or fields.Date.today(),
            'date': self.closing_date or fields.Date.today(),
            'company_id': company.id,
            'tenancy_id': self.id,
            'refund_component_type': 'deposit',
            'ref': _("Security Deposit Refund – %s", ref_name),
            'narration': _("Security Deposit Refund for Contract %s", ref_name),
            'invoice_line_ids': [(0, 0, {
                'name': _("Security Deposit Refund"),
                'quantity': 1.0,
                'price_unit': net_refund,
                'account_id': account.id if account else False,
            })],
        })
        self.write({
            'deposit_refund_amount': deposit_amount,
            'total_refund_amount': deposit_amount,
            'refund_amount': net_refund,
        })
        return dep_move

    def closure_final_approval(self):
        self.ensure_one()
        if (self.env.user not in self.final_level_approval_requested_to
                and not self.env.user.has_group('base.group_system')):
            raise ValidationError(_("You do not have permission to approve this request."))
        if self.termination_type != 'early':
            self._create_deposit_refund_credit_note()
        return super().closure_final_approval()

    # Bucket definitions for the "Expiring Soon Contracts" dashboard
    # section (rent_contract_dashboard.xml, patched by
    # quick_menu_navbar-style JS in al_shafar_extended). Each entry is
    # (dashboard data key, extra domain applied on top of
    # contract_type = 'expiring_soon'); ordered soonest-to-expire first.
    # Boundaries are upper-bound-inclusive so every contract lands in
    # exactly one bucket (e.g. a contract with exactly 90 days left counts
    # under "60-90", not "90-100").
    _EXPIRING_SOON_DAY_BUCKETS = [
        ('expiring_0_60', [('days_left', '<=', 60)]),
        ('expiring_60_90', [('days_left', '>', 60), ('days_left', '<=', 90)]),
        ('expiring_90_100', [('days_left', '>', 90), ('days_left', '<=', 100)]),
        ('expiring_100_120', [('days_left', '>', 100), ('days_left', '<=', 120)]),
        ('expiring_120_140', [('days_left', '>', 120), ('days_left', '<=', 140)]),
        ('expiring_140_160', [('days_left', '>', 140), ('days_left', '<=', 160)]),
        ('expiring_160_plus', [('days_left', '>', 160)]),
    ]

    @api.model
    def retrieve_contract_list_dashboard_data(self):
        """Extends the base dashboard data (rental_management) with:
        - total_contract_count: grand total across every contract, shown
          as a tile before "Draft" in the Status section.
        - expiring_*_count: contract_type='expiring_soon' contracts
          bucketed by days_left, replacing the Payment Terms section in
          the "Expiring Soon Contracts" view of the same dashboard.
        Existing keys/behavior from the base method are untouched."""
        data = super().retrieve_contract_list_dashboard_data()
        tenancy_obj = self.env['tenancy.details'].sudo()

        data['total_contract_count'] = tenancy_obj.search_count([])

        expiring_soon_domain = [('contract_type', '=', 'expiring_soon')]
        for key, extra_domain in self._EXPIRING_SOON_DAY_BUCKETS:
            data[f'{key}_count'] = tenancy_obj.search_count(expiring_soon_domain + extra_domain)

        return data

    def _compute_breakdown(self):
        """Hotfix for a crash in ribs_real_estate's own _compute_breakdown
        (models/tenancy_details.py): it does
        `monthly_rent * rec.get_payment_term_qty()`, and
        get_payment_term_qty() returns None (dict .get() with no match)
        for any record whose payment_term isn't set at all (e.g. an
        incomplete/legacy contract) - `float * None` then raises
        TypeError, which breaks reading/loading that record everywhere:
        list views, kanban, the dashboard, any web_read touching it.

        total_value_breakdown is a plain (non-stored) compute field used
        only for a display summary, so recomputing it record-by-record
        and falling back to '' for whichever single record can't be
        computed is safe and doesn't change the result for every other,
        valid record - it only stops one bad record from taking the
        whole read down with it.

        This does NOT touch get_payment_term_qty() itself, which is also
        used in real invoice/activation calculations elsewhere
        (action_active_contract and others) - patching its return value
        would risk silently wrong amounts there. This fix is scoped
        strictly to this one display-only compute.
        """
        for rec in self:
            try:
                super(TenancyDetails, rec)._compute_breakdown()
            except TypeError:
                rec.total_value_breakdown = ''

    def _prepare_unit_invoice_lines(self, tenancy, period="monthly", months=0, full_term=False):
        """Hotfix for action_active_contract (ribs_real_estate/models/
        tenancy_details.py) silently posting a deposit-only invoice.

        action_active_contract takes the multi-unit branch (calling this
        method) whenever self.unit_ids is set, on the assumption that
        it's a genuine multi-unit contract with a matching
        group.multi.contract.line record per unit (only ever created by
        the Multi Unit Contract wizard). An imported contract can end up
        with is_multi_contract/unit_ids set without ever going through
        that wizard - in that case the base method's
        `if not multi_line: continue` skips every unit and returns [],
        and action_active_contract posts an invoice with only the
        deposit line - the rent line never gets built at all (this is
        exactly what happened on T/41834 and T/41835).

        If the base method comes back empty, fall back to the same
        qty/price single line the normal (non-multi-unit) branch of
        action_active_contract would have built, so the rent doesn't
        silently vanish off the invoice. This does not fix the
        underlying data - is_multi_contract/unit_ids should not be set
        on these records in the first place - it only stops that bad
        data from producing a broken invoice.
        """
        invoice_lines = super()._prepare_unit_invoice_lines(
            tenancy, period=period, months=months, full_term=full_term)
        if invoice_lines:
            return invoice_lines

        qty, unit_price = self._get_invoice_qty_price()
        return [(0, 0, {
            'product_id': self.installment_item_id.id,
            'quantity': qty,
            'name': f"Invoice Amount for {qty} Installment(s)",
            'tax_ids': self.tax_ids.ids if self.instalment_tax else False,
            'price_unit': unit_price,
        })]

    def action_send_active_contract(self):
        """ribs_real_estate's action_send_active_contract creates one
        pdc.wizard per PDC-journal payment line (contract_payment_ids)
        but never sets pdc.wizard.tenancy_id at creation - that field
        (al_shafar_extended/models/pdc_wizard.py) is a stored COMPUTE
        that only resolves once the cheque is later registered and
        linked to an invoice (see its own docstring). Right after
        activation, before registration, it's genuinely empty by design
        - so anything filtering pdc.wizard by tenancy_id (e.g. the "PDC
        Cheque Payments" panel, static/src/js/pdc_payment_summary_list.js)
        shows 0 records even though the cheque exists and is correctly
        linked via partner_id/contract_payment_ids.payment_pdc_id.

        Seed tenancy_id immediately here via direct SQL - the same
        `_sql_set` pattern already used in analytic_setup.py for the same
        "computed field needs an immediate value" situation - so the
        cheque is visible right away. This does not fight the existing
        compute: if the cheque is later registered and invoice_id/
        invoice_ids change, _compute_tenancy_id runs again and resolves
        the same tenancy (or corrects it, if that logic ever disagrees) -
        this only fills the gap before that happens.
        """
        result = super().action_send_active_contract()
        pdc_records = self.contract_payment_ids.mapped('payment_pdc_id').filtered(
            lambda p: p.id and not p.tenancy_id)
        if pdc_records:
            self.env.cr.execute(
                "UPDATE pdc_wizard SET tenancy_id = %s WHERE id IN %s",
                (self.id, tuple(pdc_records.ids))
            )
            pdc_records.invalidate_recordset(['tenancy_id'])
        return result

    def contract_payment_pdc(self):
        """"Generate Payments" (ribs_real_estate.contract_payment_pdc)
        already reads the Building's 3 required bank accounts
        (rent_bank_account_id, vat_sec_bank_account_id,
        security_bank_account_id) to use as the "Beneficiary Bank" on
        each generated payment line, but never validated they're
        actually set first - an unmapped Building silently produced
        payment lines with a blank Beneficiary Bank instead of stopping.

        Validate upfront, before any of that runs, mirroring the exact
        same check property.details.contract_wiz_action already
        performs for creating a new contract in the first place - same
        3 fields, same message, so both entry points behave
        consistently."""
        self.ensure_one()
        property_id = self._get_property_queryset()
        building = property_id.property_project_id
        if (not building.rent_bank_account_id
                or not building.vat_sec_bank_account_id
                or not building.security_bank_account_id):
            raise ValidationError(_(
                'Please update bank account details in the Building in order to proceed.'))
        return super().contract_payment_pdc()


    def action_active_contract(self):
        """ribs_real_estate's activation only builds periodic installment
        invoices; Full Payment contracts are now created as draft too, so
        on activation build their single invoice here - rent for the full
        contract value, deposit and every added service (e.g. Ejari)."""
        if self.payment_term != 'full_payment':
            return super().action_active_contract()
        if self.is_any_broker:
            self.action_broker_invoice()
        invoice = self._create_full_payment_invoice()
        self.action_send_active_contract()
        self.write({
            'contract_type': 'running_contract',
            'active_contract_state': True,
            'last_invoice_payment_date': invoice.invoice_date,
            'type': 'automatic',
        })

    def _get_full_payment_rent_lines(self):
        """One rent line per unit on a combined multi-unit contract (each
        unit's own product, so its unit analytic is mapped), else a single
        line with the installment item. The contract value is shared
        across units in proportion to their duration amounts."""
        tax_ids = self.tax_ids.ids if self.instalment_tax else False
        rent_total = self.contract_value or 0.0
        units = self.unit_ids
        if len(units) <= 1:
            return [(0, 0, {
                'product_id': self.installment_item_id.id,
                'name': _("Full Payment of %s", self._get_property_name()),
                'quantity': 1,
                'price_unit': rent_total,
                'tax_ids': tax_ids,
            })]
        weights = {}
        for unit in units:
            line = self.env['group.multi.contract.line'].search(
                [('property_id', '=', unit.id)], order='id desc', limit=1)
            weights[unit] = line.amount_based_on_duration if line else (unit.price_yearly or 0.0)
        weight_total = sum(weights.values())
        lines = []
        for unit in units:
            share = (weights[unit] / weight_total) if weight_total else 1.0 / len(units)
            lines.append((0, 0, {
                'product_id': (unit.default_product_id or self.installment_item_id).id,
                'name': _("Full Payment of %s", unit.name),
                'quantity': 1,
                'price_unit': round(rent_total * share, 2),
                'tax_ids': tax_ids,
            }))
        return lines

    def _create_full_payment_invoice(self):
        """Full Payment is one invoice: rent + deposit + added services,
        whatever the services' Merge / Separate option says."""
        self.ensure_one()
        invoice_lines = self._get_full_payment_rent_lines()
        if self.is_any_deposit and self.deposit_amount:
            invoice_lines.append((0, 0, {
                'product_id': self.deposit_item_id.id,
                'name': _("Deposit of %s", self._get_property_name()),
                'quantity': 1,
                'price_unit': self.deposit_amount,
                'tax_ids': self.tax_ids.ids if self.deposit_tax else False,
            }))
        invoice_lines += [(0, 0, {
            'product_id': line.service_id.id,
            'name': line.service_id.name,
            'quantity': 1,
            'price_unit': line.price,
        }) for line in self.added_service_ids]
        invoice = self.env['account.move'].sudo().create({
            'partner_id': self.tenancy_id.id,
            'move_type': 'out_invoice',
            'invoice_date': self.invoice_start_date,
            'invoice_line_ids': invoice_lines,
            'tenancy_id': self.id,
        })
        invoice_post_type = self.env['ir.config_parameter'].sudo().get_str(
            'rental_management.invoice_post_type', False)
        if invoice_post_type == 'automatically':
            invoice.action_post()
        description = "Full Payment Of Rent" + (" + Deposit" if self.is_any_deposit else "")
        if self.added_service_ids:
            description += " + Extra Services"
        self.env['rent.invoice'].sudo().create({
            'tenancy_id': self.id,
            'type': 'full_rent',
            'invoice_date': self.invoice_start_date,
            'amount': invoice.amount_total,
            'description': description,
            'rent_invoice_id': invoice.id,
            'rent_amount': invoice.amount_total,
        })
        return invoice
