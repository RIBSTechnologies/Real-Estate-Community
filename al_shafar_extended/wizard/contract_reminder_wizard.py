# -*- coding: utf-8 -*-
"""Manual "Send Contract Renewal Reminder" wizard.

ribs_real_estate already has an automated version of this (the "Contract
Renwal Reminder" cron -> tenancy.details.send_contract_renewal_reminder(),
using the ribs_real_estate.contract_renewal_reminder_template email), but it
only ever fires on its own schedule for whichever contracts happen to be at
exactly 140/120/100/90 days left, with no way to review who it's about to
email before it goes out.

This wizard is the on-demand version: select one or more contracts from the
Contracts list, click the "Send Renewal Reminder" button, and review/edit
the proposed rent change for each one - same Amount/Percentage, Duration,
From/To Date, Current & New Rent fields as the existing single-contract
"Update Contract Details" wizard (contract.update.register) - before
confirming Send (which is also the moment the real contract.update.register
record for each contract is actually created or updated - never before
that), or Cancel to back out without changing anything.

Unlike that other wizard, this one has no Increase/Decrease choice at all -
a renewal reminder is always a rent INCREASE (per request). If a contract
already has a pending register that was set to "decrease" via the other,
single-contract wizard, action_send() below leaves that untouched (omits
the key from its write()) rather than silently flipping it back to
increase just because this wizard also resent the reminder.
"""

from datetime import timedelta

from dateutil.relativedelta import relativedelta

from odoo import api, fields, models, _
from odoo.exceptions import UserError


class ContractReminderWizard(models.TransientModel):
    _name = 'contract.reminder.wizard'
    _description = 'Send Contract Renewal Reminder'

    contract_ids = fields.Many2many('tenancy.details', string='Contracts')
    line_ids = fields.One2many(
        'contract.reminder.wizard.line', 'wizard_id', string='Contracts to Notify')

    # "Apply to all" controls, shown above the line_ids list. Not saved
    # anywhere of their own accord - _onchange_bulk_apply below just copies
    # whichever of these changed onto every line the instant it changes,
    # the same fields/names as the line model so the copy is a plain 1:1
    # field-by-field mirror. Default matches the line model's own default
    # (percentage) so it always holds a concrete value to apply.
    currency_id = fields.Many2one(
        'res.currency', default=lambda self: self.env.company.currency_id.id)
    bulk_amount_or_percentage = fields.Selection([
        ('amount', 'Amount'),
        ('percentage', 'Percentage'),
    ], string='Amount/Percentage', default='percentage')
    bulk_percentage = fields.Float(string='Percentage %')
    bulk_amount = fields.Monetary(string='Amount', currency_field='currency_id')

    @api.onchange('bulk_amount_or_percentage', 'bulk_percentage', 'bulk_amount')
    def _onchange_bulk_apply(self):
        """Mirror the "Apply to all" fields onto every line - each line's
        own new_rent_monthly/annually is a plain compute (see
        ContractReminderWizardLine._compute_new_rent) that depends on
        exactly these fields, so it recalculates for every row on its own
        the instant this runs; nothing needs recomputing by hand here."""
        for line in self.line_ids:
            line.amount_or_percentage = self.bulk_amount_or_percentage
            if self.bulk_amount_or_percentage == 'amount':
                line.amount = self.bulk_amount
            else:
                line.percentage = self.bulk_percentage

    @api.model
    def create_for_contracts(self, contracts):
        """Builds and CREATES the wizard (and its lines) directly, server-
        side, right now - instead of returning (0,0,{...}) commands from
        default_get for the web client to create later on its own first
        save. That client round-trip proved unreliable in practice: no
        combination of readonly/onchange changes stopped it from silently
        dropping contract_id (and other fields) from this line model's
        very first create(), always failing the same not-null violation.
        Creating everything here means the form the user sees is already
        a fully-valid, already-persisted record from the very start.

        Crucially, this only ever READS from an existing contract.update.
        register if one is already pending for a contract - it never
        creates or writes to one. contract.update.register._compute_rents()
        writes new_rent_monthly back onto the contract and, more
        importantly, mutates the real unit's price_yearly the instant any
        of its percentage/amount/increase_or_decrease fields are set - so
        touching a real register just to populate this review screen would
        silently change live rent prices before the user ever clicks Send.
        Proposed defaults for contracts with no pending register are
        therefore computed here in plain Python (mirroring tenancy.details.
        update_contract_request()'s own math), never persisted. The real
        register is only created/updated in action_send(), for whichever
        lines are actually sent.
        """
        lines = []
        for contract in contracts:
            register = self.env['contract.update.register'].search(
                [('contract_id', '=', contract.id)], order='id desc', limit=1)
            if register:
                vals = {
                    'update_register_id': register.id,
                    'amount_or_percentage': register.amount_or_percentage,
                    'percentage': register.percentage,
                    'amount': register.amount,
                    'duration_id': register.duration_id.id,
                    'from_date': register.from_date,
                    'to_date': register.to_date,
                }
            else:
                vals = {'update_register_id': False}
                vals.update(self._default_increment_vals(contract))
            vals.update({
                'contract_id': contract.id,
                'current_rent_monthly': contract.total_rent or 0.0,
                'current_rent_annually': contract.total_rent_year or 0.0,
                'selected': bool(contract.tenancy_id.email),
            })
            lines.append((0, 0, vals))
        return self.create({
            'contract_ids': [(6, 0, contracts.ids)],
            'line_ids': lines,
        })

    @api.model
    def _default_increment_vals(self, contract):
        """Proposed amount_or_percentage/percentage/amount/duration_id/
        from_date/to_date for a contract with no pending update.register
        yet - same Building "Rent Increment" settings and to_date math as
        tenancy.details.update_contract_request(), computed here as plain
        numbers (nothing created or written)."""
        project = contract.property_project_id
        increment_type = project.building_contract_increment or 'percentage'
        to_date = False
        if contract.duration_id and contract.end_date:
            duration = contract.duration_id
            if duration.rent_unit == 'Day':
                to_date = contract.end_date + relativedelta(days=duration.month) - timedelta(days=1)
            elif duration.rent_unit == 'Month':
                to_date = contract.end_date + relativedelta(months=duration.month) - timedelta(days=1)
            elif duration.rent_unit == 'Year':
                to_date = contract.end_date + relativedelta(years=duration.month) - timedelta(days=1)
        return {
            'amount_or_percentage': increment_type,
            'percentage': project.contract_increment_percentage if increment_type == 'percentage' else 0.0,
            'amount': project.contract_increment_amount if increment_type == 'amount' else 0.0,
            'duration_id': contract.duration_id.id if contract.duration_id else False,
            'from_date': contract.end_date + timedelta(days=1) if contract.end_date else False,
            'to_date': to_date,
        }

    def action_send(self):
        self.ensure_one()
        template = self.env.ref(
            'ribs_real_estate.contract_renewal_reminder_template', raise_if_not_found=False)
        if not template:
            raise UserError(_(
                "The 'Contract Renewal Reminder' email template could not be found."))

        to_send = self.line_ids.filtered('selected')
        sent, skipped_no_email = 0, 0

        for line in to_send:
            contract = line.contract_id
            register_vals = {
                'amount_or_percentage': line.amount_or_percentage,
                'amount': line.amount,
                'percentage': line.percentage,
                'duration_id': line.duration_id.id,
                'from_date': line.from_date,
                'to_date': line.to_date,
            }
            # The real contract.update.register is only ever touched here,
            # at Send time - never while the wizard is just being reviewed.
            if line.update_register_id:
                # increase_or_decrease deliberately left out of this write:
                # this wizard has no UI for it, so an existing register's
                # value (e.g. a "decrease" set via the other, single-contract
                # wizard) is left exactly as it was rather than being reset.
                line.update_register_id.write(register_vals)
                register = line.update_register_id
            else:
                register_vals.update({
                    'contract_id': contract.id,
                    'name': contract.tenancy_seq or '/',
                    # A renewal reminder is always a rent increase.
                    'increase_or_decrease': 'increase',
                })
                register = self.env['contract.update.register'].create(register_vals)
                contract.new_contract_sent = True

            email_to = contract.tenancy_id.email
            if not email_to:
                skipped_no_email += 1
                continue
            template.with_context(
                days_left=line.days_left,
                update_rec=register,
            ).send_mail(
                contract.id,
                email_values={
                    'email_from': self.env.company.email,
                    'email_to': email_to,
                },
                force_send=True,
            )
            sent += 1

        message = _("%s reminder email(s) sent.") % sent
        if skipped_no_email:
            message += _(" %s skipped (no email on file).") % skipped_no_email

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'type': 'success' if sent else 'warning',
                'title': _('Contract Renewal Reminder'),
                'message': message,
                'sticky': False,
                # Closes the wizard right after showing the toast, instead
                # of leaving it open on screen after Send.
                'next': {'type': 'ir.actions.act_window_close'},
            },
        }

    def action_cancel(self):
        return {'type': 'ir.actions.act_window_close'}


class ContractReminderWizardLine(models.TransientModel):
    _name = 'contract.reminder.wizard.line'
    _description = 'Send Contract Renewal Reminder - Line'
    _order = 'days_left asc'

    # NONE of the fields below carry readonly=True at the model/Python
    # level, even ones the user shouldn't directly type into (contract_id,
    # update_register_id) - non-editability for those is enforced purely at
    # the VIEW level (readonly="1" as a view attribute). A model-level
    # readonly=True field is excluded from this line's create() payload
    # while it's still a brand-new (never persisted) record, which is what
    # caused the earlier not-null violation on contract_id.
    wizard_id = fields.Many2one(
        'contract.reminder.wizard', required=True, ondelete='cascade')
    contract_id = fields.Many2one('tenancy.details', string='Contract', required=True)
    tenancy_seq = fields.Char(
        related='contract_id.tenancy_seq', string='Contract No', readonly=True)
    customer_id = fields.Many2one(
        related='contract_id.tenancy_id', string='Customer', readonly=True)
    email = fields.Char(related='customer_id.email', string='Email', readonly=True)
    days_left = fields.Integer(
        related='contract_id.days_left', string='Days Left', readonly=True)
    currency_id = fields.Many2one(related='contract_id.currency_id', readonly=True)

    # Set only if a contract.update.register already existed for this
    # contract when the wizard opened - action_send() writes to it instead
    # of creating a new one. Left False (no register at all yet) until Send.
    update_register_id = fields.Many2one('contract.update.register', string='Pending Update')

    # Mirrors contract.update.register's own field set/names exactly
    # (amount_or_percentage, percentage, amount, duration_id, from_date,
    # to_date) so the wizard reads/edits the same concept as the existing
    # single-contract "Update Contract Details" form - just for several
    # contracts' rows at once here. No increase_or_decrease field: a
    # renewal reminder is always a rent increase (see module docstring).
    amount_or_percentage = fields.Selection([
        ('amount', 'Amount'),
        ('percentage', 'Percentage'),
    ], string='Amount/Percentage', default='percentage', required=True)
    percentage = fields.Float(string='Percentage %')
    amount = fields.Monetary(string='Amount', currency_field='currency_id')
    duration_id = fields.Many2one('contract.duration', string='Duration')
    from_date = fields.Date(string='From Date')
    to_date = fields.Date(string='To Date')

    current_rent_monthly = fields.Monetary(
        string='Current Rent/Month', currency_field='currency_id')
    current_rent_annually = fields.Monetary(
        string='Current Rent/Year', currency_field='currency_id')

    # Live preview only (mirrors contract.update.register._compute_rents'
    # own new-rent formula) - a genuine @api.depends compute, not an
    # @api.onchange, and deliberately WITHOUT that method's side effect of
    # writing the result back onto the contract/unit. A compute field is
    # never part of a create()/write() payload (the server always derives
    # it fresh), so there's nothing here for the client to drop, and
    # nothing here mutates anything real until action_send() writes the
    # edited percentage/amount to the real register.
    new_rent_monthly = fields.Monetary(
        string='New Rent/Month', currency_field='currency_id', compute='_compute_new_rent')
    new_rent_annually = fields.Monetary(
        string='New Rent/Year', currency_field='currency_id', compute='_compute_new_rent')

    selected = fields.Boolean(
        string='Send', default=True,
        help="Uncheck to review this contract without emailing it - and "
             "without creating/updating its pending rent change.")

    @api.depends('current_rent_annually', 'percentage', 'amount', 'amount_or_percentage')
    def _compute_new_rent(self):
        for line in self:
            current = line.current_rent_annually or 0.0
            new_rent_yearly = current
            if line.amount_or_percentage == 'percentage' and line.percentage:
                new_rent_yearly = current + (current * line.percentage / 100)
            elif line.amount_or_percentage == 'amount' and line.amount:
                new_rent_yearly = current + line.amount
            line.new_rent_annually = new_rent_yearly
            line.new_rent_monthly = new_rent_yearly / 12 if new_rent_yearly else 0.0
