# -*- coding: utf-8 -*-
"""
al_shafar_extended – Settlement Breakdown Lines (INVOICE-LINE level)
=====================================================================
Refund is computed per INVOICE LINE (account.move.line), because a single
invoice can carry several lines posting to different accounts (e.g. Rental
Income vs Ejari-Payable vs Security Deposit). Each line is independently:
  • selectable,
  • time-apportioned against the contract start date and the closing date,
  • refunded to ITS OWN account (kept separate in the journal items).

KEY CHANGE (v2)
---------------
`refund_amount` is now a COMPUTED-EDITABLE field. It is derived live from
  contract start date  →  line coverage period  →  closing date
using the wizard's Settlement Method, so the refund is never the full invoice
value unless the tenant genuinely consumed nothing. The user can still type an
override; it is recalculated whenever any driver changes.

Models:
  1. contract.settlement.invoice     – one editable row per invoice LINE
  2. contract.settlement.line        – account-wise refund component (derived)
  3. contract.settlement.journalitem – read-only debit/credit preview
"""

from odoo import models, fields, api, _
from dateutil.relativedelta import relativedelta


COMPONENT_SELECTION = [
    ('invoice', 'Invoice Refund'),
    ('tax', 'Tax Refund'),
    ('deposit', 'Security Deposit Refund'),
]

LINE_TYPE_SELECTION = [
    ('rent', 'Rent / Recurring Service'),
    ('deposit', 'Security Deposit'),
    ('other', 'One-time Charge'),
]


def month_span(d_from, d_to):
    """Number of calendar months touched by the inclusive range [d_from, d_to]."""
    if not d_from or not d_to or d_to < d_from:
        return 0
    return (d_to.year - d_from.year) * 12 + (d_to.month - d_from.month) + 1


def days360(d_from, d_to):
    """Inclusive day count from d_from to d_to under the 30/360 lease
    proration convention: every calendar month counts as exactly 30 days,
    regardless of its real length (28-31). E.g. a contract starting Aug 1,
    closed Aug 16, refunds 30 - 16 = 14 days, not August's real 31 - 16 = 15
    calendar days. Matches the flat daily-rate formula (monthly_rent / 30)
    used elsewhere in this wizard for the same Settlement Method."""
    if not d_from or not d_to or d_to < d_from:
        return 0
    months = (d_to.year - d_from.year) * 12 + (d_to.month - d_from.month)
    day_from = min(d_from.day, 30)
    day_to = min(d_to.day, 30)
    if d_to.day < d_from.day:
        months -= 1
        day_to += 30
    return months * 30 + (day_to - day_from) + 1


class ContractSettlementInvoice(models.TransientModel):
    _name = 'contract.settlement.invoice'
    _description = 'Selectable Invoice LINE for Refund (time-apportioned)'
    _order = 'move_id, id'

    wizard_id = fields.Many2one(
        'contract.closing.wizard', string="Settlement Wizard",
        required=True, ondelete='cascade', index=True,
    )
    selected = fields.Boolean(
        string="Refund?", default=True,
        help="Tick to include this invoice line in the refund. Only selected "
             "lines are apportioned and refunded — each to its own account.",
    )

    # ── Source link ─────────────────────────────────────────────────────────
    move_line_id = fields.Many2one('account.move.line', string="Invoice Line")
    move_id = fields.Many2one('account.move', string="Invoice",
                              compute='_compute_from_move_line', store=True, readonly=False)

    # ── Descriptive fields (self-healing from the source move line) ─────────
    # These are computed-stored so a browser onchange round-trip that drops
    # readonly values can never zero them out.
    name = fields.Char(string="Invoice", compute='_compute_from_move_line',
                       store=True, readonly=False)
    product_label = fields.Char(string="Product / Description",
                                compute='_compute_from_move_line', store=True, readonly=False)
    invoice_date = fields.Date(string="Invoice Date",
                               compute='_compute_from_move_line', store=True, readonly=False)
    payment_state = fields.Char(string="Payment Status",
                                compute='_compute_from_move_line', store=True, readonly=False)
    account_id = fields.Many2one('account.account', string="Account",
                                 compute='_compute_from_move_line', store=True, readonly=False)
    analytic_distribution = fields.Json(string="Analytic Distribution",
                                        compute='_compute_from_move_line', store=True, readonly=False)
    tax_label = fields.Char(string="Tax", compute='_compute_from_move_line',
                            store=True, readonly=False)
    tax_ids = fields.Many2many('account.tax', string="Tax Records",
                               compute='_compute_from_move_line', store=True, readonly=False)
    quantity = fields.Float(string="Qty", compute='_compute_from_move_line',
                            store=True, readonly=False)
    price_unit = fields.Float(string="Unit Price", compute='_compute_from_move_line',
                              store=True, readonly=False)

    amount = fields.Monetary(string="Untaxed", currency_field='currency_id',
                             compute='_compute_from_move_line', store=True, readonly=False,
                             help="Untaxed line amount (subtotal).")
    vat_amount = fields.Monetary(string="VAT", currency_field='currency_id',
                                 compute='_compute_from_move_line', store=True, readonly=False)
    total_amount = fields.Monetary(
        string="Total Amount", currency_field='currency_id',
        compute='_compute_total_amount', store=True,
        help="Untaxed + VAT — what this invoice line was actually billed for.")

    # ── Classification: drives HOW the line is refunded ─────────────────────
    line_type = fields.Selection(
        LINE_TYPE_SELECTION, string="Line Type", default='rent', required=True,
        help="Rent / Recurring Service → apportioned by time.\n"
             "Security Deposit → refunded in full (not time-based).\n"
             "One-time Charge (Ejari, admin, registration) → not refunded "
             "unless you tick it, then refunded in full.")

    # ── Contract window snapshot (so line computes need no cross-record hop) ─
    contract_start = fields.Date(string="Contract Start")
    contract_end = fields.Date(string="Contract End")

    # ── Coverage period this line paid for (editable — proration driver) ────
    date_from = fields.Date(string="Period From")
    date_to = fields.Date(string="Period To")

    # ── Time apportionment results ──────────────────────────────────────────
    # readonly=False so the server-side recompute can write() them directly.
    period_days = fields.Integer(string="Period Days", compute='_compute_proration',
                                 store=True, readonly=False)
    used_days = fields.Integer(string="Occupied Days", compute='_compute_proration',
                               store=True, readonly=False)
    refund_days = fields.Integer(string="Refundable Days", compute='_compute_proration',
                                 store=True, readonly=False)
    refund_ratio = fields.Float(string="Refund Ratio", digits=(16, 6),
                                compute='_compute_proration', store=True, readonly=False)

    manual_override = fields.Boolean(
        string="Manually Adjusted", default=False, copy=False,
        help="Set automatically when you type a refund amount that differs "
             "from the calculated one. Protects your value from being "
             "overwritten when the settlement is submitted.")

    type_override = fields.Boolean(
        string="Line Type Set Manually", default=False, copy=False,
        help="Set automatically when you change the Line Type, so the "
             "server-side reclassification does not undo your choice.")

    @api.onchange('line_type')
    def _onchange_line_type_override(self):
        for rec in self:
            rec.type_override = True

    # ── ACTUAL refund (computed live, user-overridable) ─────────────────────
    refund_amount = fields.Monetary(
        string="Refund (Untaxed)", currency_field='currency_id',
        compute='_compute_refund_amounts', store=True, readonly=False,
        help="Untaxed amount refunded for this line, to its own account. "
             "Auto-calculated from the contract start date, this line's "
             "coverage period and the closing date. You may override it; it "
             "recalculates whenever any of those change.")
    refund_tax_amount = fields.Monetary(
        string="Refund (VAT)", currency_field='currency_id',
        compute='_compute_refund_amounts', store=True, readonly=False)
    refund_total = fields.Monetary(
        string="Refund Amount", currency_field='currency_id',
        compute='_compute_refund_total', store=True)

    analytic_label = fields.Char(string="Analytic", compute='_compute_analytic_label', store=False)
    currency_id = fields.Many2one('res.currency', related='wizard_id.currency_id', readonly=True)

    @api.depends('analytic_distribution')
    def _compute_analytic_label(self):
        AA = self.env['account.analytic.account']
        for rec in self:
            names = []
            for key in (rec.analytic_distribution or {}).keys():
                for aid in str(key).split(','):
                    aid = aid.strip()
                    if aid.isdigit():
                        acc = AA.browse(int(aid))
                        if acc.exists():
                            names.append(acc.name)
            rec.analytic_label = ', '.join(names)

    # ── Self-healing source values ──────────────────────────────────────────
    @api.depends('move_line_id')
    def _compute_from_move_line(self):
        for rec in self:
            ml = rec.move_line_id
            if not ml:
                continue
            move = ml.move_id
            subtotal = ml.price_subtotal
            if not subtotal:
                subtotal = abs(ml.price_total or 0.0) or abs(ml.balance or 0.0) \
                    or abs((ml.credit or 0.0) - (ml.debit or 0.0)) \
                    or (ml.quantity or 0.0) * (ml.price_unit or 0.0)
            rec.move_id = move.id
            rec.name = move.name or move.ref or ''
            rec.product_label = ml.product_id.display_name or ml.name or ''
            rec.invoice_date = move.invoice_date or move.date
            rec.payment_state = move.payment_state or ''
            rec.account_id = ml.account_id.id
            rec.analytic_distribution = ml.analytic_distribution or False
            rec.tax_label = ', '.join(ml.tax_ids.mapped('name'))
            rec.tax_ids = [(6, 0, ml.tax_ids.ids)]
            rec.quantity = ml.quantity
            rec.price_unit = ml.price_unit
            rec.amount = subtotal
            rec.vat_amount = max((ml.price_total or 0.0) - (ml.price_subtotal or 0.0), 0.0)

    @api.depends('amount', 'vat_amount')
    def _compute_total_amount(self):
        for rec in self:
            rec.total_amount = (rec.amount or 0.0) + (rec.vat_amount or 0.0)

    # ── Apportionment engine (plain python — never depends on ORM triggers) ─
    # Both the on-screen compute AND the server-side button path go through
    # these two methods, so what the user sees is exactly what gets posted.
    def _apportion_vals(self):
        """Day / month apportionment for this line, as a plain dict."""
        self.ensure_one()
        method = self.wizard_id.settlement_method or 'full_month'
        term_d = self.wizard_id.closing_date
        out = {'period_days': 0, 'used_days': 0, 'refund_days': 0, 'refund_ratio': 0.0}

        # Non time-based lines: a deposit is fully refundable; a one-time
        # charge is refunded in full only when the user explicitly ticks it.
        if self.line_type in ('deposit', 'other'):
            out['refund_ratio'] = 1.0 if (self.selected and method != 'no_refund') else 0.0
            return out

        d_from, d_to = self.date_from, self.date_to
        if not d_from or not d_to or d_to < d_from:
            # Period unknown → cannot apportion; fall back to the full value
            # rather than silently refunding nothing.
            out['refund_ratio'] = 1.0 if (self.selected and method != 'no_refund') else 0.0
            return out

        # Clamp the billed period to the real contract window so a line
        # invoiced before the contract started is not counted as occupied.
        eff_from = max(d_from, self.contract_start) if self.contract_start else d_from
        eff_to = min(d_to, self.contract_end) if self.contract_end else d_to
        if eff_to < eff_from:
            eff_from, eff_to = d_from, d_to

        period_days = (eff_to - eff_from).days + 1
        out['period_days'] = period_days

        if not self.selected or method == 'no_refund':
            out['used_days'] = period_days
            return out

        if method == 'full_month':
            # The calendar month containing the closing date is charged in
            # full; every month strictly after it is refunded.
            total_m = month_span(eff_from, eff_to)
            if not term_d or term_d < eff_from:
                used_m = 0
            elif term_d >= eff_to:
                used_m = total_m
            else:
                used_m = month_span(eff_from, term_d)
            used_m = max(0, min(used_m, total_m))
            ratio = (float(total_m - used_m) / total_m) if total_m else 0.0
            refund_days = int(round(period_days * ratio))
            used = period_days - refund_days
        else:
            # 'prorated' — 30/360 lease convention (see days360): every
            # month is treated as exactly 30 days, so this overrides the
            # real-calendar-days 'period_days' set above for this method.
            # month_span (not days360) sizes the period itself, so a 28-day
            # February still counts as a uniform 30-day period, not 28.
            period_days = 30 * month_span(eff_from, eff_to)
            out['period_days'] = period_days
            if not term_d or term_d < eff_from:
                used = 0
            elif term_d >= eff_to:
                used = period_days
            else:
                used = days360(eff_from, term_d)
            used = max(0, min(used, period_days))
            refund_days = period_days - used
            ratio = (float(refund_days) / period_days) if period_days else 0.0

        out.update(used_days=used, refund_days=refund_days, refund_ratio=ratio)
        return out

    def _refund_vals(self):
        """Apportionment + money, as a dict ready for write()."""
        self.ensure_one()
        vals = self._apportion_vals()
        if not self.selected or self.wizard_id.settlement_method == 'no_refund':
            vals['refund_amount'] = 0.0
            vals['refund_tax_amount'] = 0.0
            return vals
        ratio = vals['refund_ratio'] or 0.0
        vals['refund_amount'] = round((self.amount or 0.0) * ratio, 2)
        vals['refund_tax_amount'] = (
            0.0 if self.wizard_id.tax_refundable
            else round((self.vat_amount or 0.0) * ratio, 2)
        )
        return vals

    def force_recompute_refund(self, respect_override=True):
        """Hard server-side recompute via write().

        On a button click the web client only posts the columns present in the
        list view, and computed columns can come back as zero. Relying on the
        compute to re-fire is therefore not safe — this writes the values
        explicitly so the credit note is always built from real numbers.
        """
        for rec in self:
            vals = rec._refund_vals()
            if respect_override and rec.manual_override:
                vals.pop('refund_amount', None)
                vals.pop('refund_tax_amount', None)
            rec.write(vals)

    # ── Live UI computes (delegate to the same engine) ──────────────────────
    @api.depends('selected', 'line_type', 'date_from', 'date_to',
                 'contract_start', 'contract_end',
                 'wizard_id.closing_date', 'wizard_id.settlement_method')
    def _compute_proration(self):
        for rec in self:
            for key, val in rec._apportion_vals().items():
                rec[key] = val

    @api.depends('refund_ratio', 'amount', 'vat_amount', 'selected', 'line_type',
                 'wizard_id.tax_refundable', 'wizard_id.settlement_method')
    def _compute_refund_amounts(self):
        for rec in self:
            vals = rec._refund_vals()
            rec.refund_amount = vals['refund_amount']
            rec.refund_tax_amount = vals['refund_tax_amount']

    @api.depends('refund_amount', 'refund_tax_amount')
    def _compute_refund_total(self):
        for rec in self:
            rec.refund_total = (rec.refund_amount or 0.0) + (rec.refund_tax_amount or 0.0)

    @api.onchange('refund_amount', 'refund_tax_amount')
    def _onchange_refund_amount_clamp(self):
        """Cap a manual override at what the line was billed, and remember that
        the user set it so a later server-side recompute does not wipe it."""
        for rec in self:
            warn = None
            if rec.refund_amount and rec.refund_amount > (rec.amount or 0.0) + 0.01:
                rec.refund_amount = rec.amount or 0.0
                warn = rec.amount or 0.0
            if rec.refund_tax_amount and rec.refund_tax_amount > (rec.vat_amount or 0.0) + 0.01:
                rec.refund_tax_amount = rec.vat_amount or 0.0

            # Only flag a genuine override — not the value the engine itself
            # just produced — otherwise every date change would freeze the line.
            auto = rec._refund_vals()
            if (abs((rec.refund_amount or 0.0) - auto['refund_amount']) > 0.01
                    or abs((rec.refund_tax_amount or 0.0) - auto['refund_tax_amount']) > 0.01):
                rec.manual_override = True

            if warn is not None:
                return {
                    'warning': {
                        'title': _("Refund amount capped"),
                        'message': _(
                            "This invoice line was only billed %(cap).2f untaxed. "
                            "The refund has been capped to that value.", cap=warn),
                    }
                }

    @staticmethod
    def default_period_to(date_from):
        """Legacy helper kept for backward compatibility.

        The real coverage window is now resolved by
        `contract.closing.wizard._resolve_line_period()`, which honours the
        contract's payment term instead of blindly assuming one month.
        """
        if not date_from:
            return False
        return date_from + relativedelta(months=1) - relativedelta(days=1)


class ContractSettlementLine(models.TransientModel):
    _name = 'contract.settlement.line'
    _description = 'Contract Settlement Component Line (account-wise)'
    _order = 'sequence, id'

    wizard_id = fields.Many2one(
        'contract.closing.wizard', string="Settlement Wizard",
        required=True, ondelete='cascade', index=True,
    )
    sequence = fields.Integer(default=10)
    component_type = fields.Selection(COMPONENT_SELECTION, string="Component",
                                      required=True, default='invoice')
    name = fields.Char(string="Description", required=True)

    account_id = fields.Many2one('account.account', string="GL Account (Debit)")
    receivable_account_id = fields.Many2one('account.account', string="Customer Account (Credit)")
    analytic_distribution = fields.Json(string="Analytic Distribution")

    amount = fields.Monetary(string="Amount", currency_field='currency_id')
    partner_id = fields.Many2one('res.partner', string="Customer")
    currency_id = fields.Many2one('res.currency', related='wizard_id.currency_id', readonly=True)


class ContractSettlementJournalItem(models.TransientModel):
    _name = 'contract.settlement.journalitem'
    _description = 'Contract Settlement Journal Item Preview'
    _order = 'component_type, id'

    wizard_id = fields.Many2one(
        'contract.closing.wizard', string="Settlement Wizard",
        required=True, ondelete='cascade', index=True,
    )
    component_type = fields.Selection(COMPONENT_SELECTION, string="Component")
    name = fields.Char(string="Label")
    account_id = fields.Many2one('account.account', string="Account")
    partner_id = fields.Many2one('res.partner', string="Partner")
    debit = fields.Monetary(string="Debit", currency_field='currency_id')
    credit = fields.Monetary(string="Credit", currency_field='currency_id')
    currency_id = fields.Many2one('res.currency', related='wizard_id.currency_id', readonly=True)
