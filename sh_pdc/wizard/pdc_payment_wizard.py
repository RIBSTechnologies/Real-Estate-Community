# -*- coding: utf-8 -*-
# Part of Softhealer Technologies.
from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.http import request
from datetime import timedelta, date


class Attachment(models.Model):
    _inherit = 'ir.attachment'

    pdc_id = fields.Many2one('pdc.wizard')


class PDCWizard(models.Model):
    _name = "pdc.wizard"
    _inherit = ['mail.thread', 'mail.activity.mixin', 'portal.mixin']
    _description = "PDC Wizard"

    # pdc only be allowed to delete in draft state
    def unlink(self):

        for rec in self:
            if rec.state != 'draft':
                raise UserError("You can only delete draft state pdc")

        return super().unlink()

    def action_register_check(self):
        active_ids = self.env.context.get('active_ids')
        active_model = self.env.context.get('active_model')
        active_id = self.env.context.get('active_id')
        account_move_model = self.env[active_model].browse(active_id)

        if account_move_model.move_type not in ('out_invoice', 'in_invoice'):
            raise UserError(
                "Only Customer invoice and vendor bills are considered!")

        move_listt = []
        payment_amount = 0.0
        payment_type = ''
        if len(active_ids) > 0:
            account_moves = self.env[active_model].browse(active_ids)
            partners = account_moves.mapped('partner_id')
            if len(set(partners)) != 1:
                raise UserError('Partners must be same')

            states = account_moves.mapped('state')
            if len(set(states)) != 1 or states[0] != 'posted':
                raise UserError(
                    'Only posted invoices/bills are considered for PDC payment!!')

            for account_move in account_moves:
                if account_move.payment_state != 'paid' and account_move.amount_residual != 0.0:
                    payment_amount = payment_amount + account_move.amount_residual
                    move_listt.append(account_move.id)
        if not move_listt:
            raise UserError("Selected invoices/bills are already paid!!")

        if account_moves[0].move_type in ('in_invoice'):
            payment_type = 'send_money'

        if account_moves[0].move_type in ('out_invoice'):
            payment_type = 'receive_money'

        return {
            'name': 'PDC Payment',
            'res_model': 'pdc.wizard',
            'view_mode': 'form',
            'view_id': self.env.ref('sh_pdc.sh_pdc_wizard_form_wizard').id,
            'context': {
                'default_invoice_ids': [(6, 0, move_listt)],
                'default_partner_id': account_move_model.partner_id.id,
                'default_payment_amount': payment_amount,
                'default_payment_type': payment_type
            },
            'target': 'new',
            'type': 'ir.actions.act_window'
        }

    def open_attachments(self):
        [action] = self.env.ref('base.action_attachment').read()

        action['domain'] = [('id', 'in', self.attachment_ids.ids)]
        return action

    def open_journal_items(self):
        [action] = self.env.ref('account.action_account_moves_all').read()
        ids = self.env['account.move.line'].search([('pdc_id', '=', self.id)])
        id_list = []
        for pdc_id in ids:
            id_list.append(pdc_id.id)
        if id_list:
            action['domain'] = [('id', 'in', id_list)]
        else:
            action['domain'] = [('id', '=', False)]
        return action

    def open_journal_entry(self):
        [action] = self.env.ref(
            'sh_pdc.sh_pdc_action_move_journal_line').read()
        ids = self.env['account.move'].search([('pdc_id', '=', self.id)])
        id_list = []
        for pdc_id in ids:
            id_list.append(pdc_id.id)
        action['domain'] = [('id', 'in', id_list)]
        return action

    @api.model
    def default_get(self, fields):
        rec = super().default_get(fields)
        active_ids = self.env.context.get('active_ids')
        active_model = self.env.context.get('active_model')

        # Check for selected invoices ids
        if not active_ids or active_model != 'account.move':
            return rec
        invoices = self.env['account.move'].browse(active_ids)
        if invoices and len(invoices) == 1:
            invoice = invoices[0]
            if invoice.move_type in ('out_invoice', 'out_refund'):
                rec.update({'payment_type': 'receive_money'})
            elif invoice.move_type in ('in_invoice', 'in_refund'):
                rec.update({'payment_type': 'send_money'})

            rec.update({'partner_id': invoice.partner_id.id,
                        'payment_amount': invoice.amount_residual,
                        'invoice_id': invoice.id,
                        'due_date': invoice.invoice_date_due,
                        'memo': invoice.name})

        return rec

    name = fields.Char("Name", default='New', readonly=True, tracking=True)
    # check_amount_in_words = fields.Char(string="Amount in Words",compute='_compute_check_amount_in_words')
    payment_type = fields.Selection([('receive_money', 'Receive Money'), (
        'send_money', 'Send Money')], string="Payment Type", default='receive_money', tracking=True)
    partner_id = fields.Many2one(
        'res.partner', string="Partner", tracking=True)
    phone = fields.Char(string="Phone", tracking=True)
    payment_amount = fields.Monetary("Payment Amount", tracking=True)
    currency_id = fields.Many2one(
        'res.currency', string="Currency", default=lambda self: self.env.company.currency_id, tracking=True)
    reference = fields.Char("Cheque Reference", tracking=True)
    cheque_number = fields.Char("Cheque Number", tracking=True)
    journal_id = fields.Many2one('account.journal', string="Beneficiary Bank", domain=[
                                 ('type', '=', 'bank')], required=True, tracking=True)
    cheque_status = fields.Selection([('draft', 'Draft'), ('deposit', 'Deposit'), (
        'paid', 'Paid')], string="Cheque Status", default='draft', tracking=True)
    payment_date = fields.Date(
        "Payment Date", default=fields.Date.today, required=True, tracking=True)
    due_date = fields.Date("Due Date", required=True, tracking=True)
    memo = fields.Char("Memo", tracking=True)
    agent = fields.Char("Agent", tracking=True)
    bank_id = fields.Many2one('res.bank', string="Remitter Bank", tracking=True)
    remitter_bank = fields.Char(string="Remitter Bank")
    attachment_ids = fields.Many2many(
        'ir.attachment', 'pdc_attachment_rel', string='Cheque Image')
    company_id = fields.Many2one(
        'res.company', string='company', default=lambda self: self.env.company, tracking=True)
    invoice_id = fields.Many2one(
        'account.move', string="Invoice/Bill", tracking=True)
    state = fields.Selection([('draft', 'Draft'), ('registered', 'Registered'), ('returned', 'Returned'), ('hold','On Hold'),
                              ('deposited', 'Deposited'), ('bounced', 'Bounced'), ('done', 'Done'), ('cancel', 'Cancelled')], string="State", default='draft', tracking=True)

    deposited_debit = fields.Many2one('account.move.line')
    deposited_credit = fields.Many2one('account.move.line')

    invoice_ids = fields.Many2many('account.move')
    account_move_ids = fields.Many2many(
        'account.move', compute="compute_account_moves",)
    done_date = fields.Date(string="Done Date", readonly=True, tracking=True)

    @api.depends('payment_type', 'partner_id')
    def compute_account_moves(self):

        self.account_move_ids = False
        domain = [('partner_id', '=', self.partner_id.id), ('payment_state', '!=',
                                                            'paid'), ('amount_residual', '!=', 0.0), ('state', '=', 'posted')]

        if self.payment_type == 'receive_money':
            domain.extend([('move_type', '=', 'out_invoice')])

        else:
            domain.extend([('move_type', '=', 'in_invoice')])

        moves = self.env['account.move'].search(domain)
        self.account_move_ids = moves.ids

    @api.onchange('partner_id')
    def _onchange_partner(self):
        # Auto-fetch phone from partner
        self.phone = self.partner_id.phone or False

        if self.env.company.auto_fill_open_invoice:

            domain = [('partner_id', '=', self.partner_id.id), ('payment_state', '!=',
                                                                'paid'), ('amount_residual', '!=', 0.0), ('state', '=', 'posted')]

            if self.payment_type == 'receive_money':
                domain.extend([('move_type', '=', 'out_invoice')])

            else:
                domain.extend([('move_type', '=', 'in_invoice')])

            moves = self.env['account.move'].search(domain)

            self.invoice_ids = [(6, 0, moves.ids)]

    # Register pdc payment
    def button_register(self):
        listt = []
        if self:

            if self.invoice_id:
                listt.append(self.invoice_id.id)
            if self.invoice_ids:
                listt.extend(self.invoice_ids.ids)

            self.write({
                'invoice_ids': [(6, 0, list(set(listt)))]
            })

            if self.cheque_status == 'draft':
                self.write({'state': 'draft'})

            if self.cheque_status == 'deposit':
                self.action_register()
                self.action_deposited()
                self.write({'state': 'deposited'})

            if self.cheque_status == 'paid':
                self.action_register()
                self.action_deposited()
                self.action_done()
                self.write({'state': 'done'})

    def action_register(self):
        self.check_payment_amount()

        if self.invoice_ids:
            list_amount_residuals = self.invoice_ids.mapped('amount_residual')
            amount = (
                self.currency_id.round(sum(list_amount_residuals))
                if self.currency_id
                else round(sum(list_amount_residuals), 2)
            )

            if self.payment_amount > amount and amount != 0:
                raise UserError(
                    "Payment amount is greater than total invoice/bill amount!!!"
                )

        move = self.env['account.move']
        self.check_payment_amount()

        pdc_account = self.check_pdc_account()
        partner_account = self.get_partner_account()

        # Create Journal Item
        if self.payment_type == 'receive_money':
            move_line_vals_debit = self.get_debit_move_line(pdc_account)
            move_line_vals_credit = self.get_credit_move_line(partner_account)
        else:
            move_line_vals_debit = self.get_debit_move_line(partner_account)
            move_line_vals_credit = self.get_credit_move_line(pdc_account)

        analytic_distribution = self._get_analytic_distribution()

        move_line_vals_debit["analytic_distribution"] = analytic_distribution
        move_line_vals_credit["analytic_distribution"] = analytic_distribution

        move_vals = self.get_move_vals(
            move_line_vals_debit,
            move_line_vals_credit
        )

        existing_move = False

        if self.state == 'bounced':
            existing_move = self.env['account.move'].search([
                ('pdc_id', '=', self.id),
                ('state', '=', 'posted'),
            ], order='id asc', limit=1)

        if existing_move:
            move_id = existing_move
        else:
            move_id = move.create(move_vals)
            move_id.action_post()

        invoice_lines = self.invoice_ids.mapped('line_ids')

        lines_to_reconcile = (invoice_lines | move_id.line_ids).filtered(
            lambda l: (
                l.account_id.id == partner_account
                and not l.reconciled
            )
        )

        if len(lines_to_reconcile) > 1:
            lines_to_reconcile.reconcile()

        self.write({
            'deposited_debit': move_id.line_ids.filtered(lambda x: x.debit > 0),
            'deposited_credit': move_id.line_ids.filtered(lambda x: x.credit > 0),
            'state': 'registered',
        })

    def check_payment_amount(self):
        if self.payment_amount <= 0.0:
            raise UserError("Amount must be greater than zero!")

    def check_pdc_account(self):
        if self.payment_type == 'receive_money':
            if not self.env.company.pdc_customer:
                raise UserError(
                    "Please Set PDC payment account for Customer in Accounting - Settings")
            else:
                return self.env.company.pdc_customer.id

        else:
            if not self.env.company.pdc_vendor:
                raise UserError(
                    "Please Set PDC payment account for Supplier !")
            else:
                return self.env.company.pdc_vendor.id

    # def get_partner_account(self):
    #     if self.payment_type == 'receive_money':
    #         return self.partner_id.property_account_receivable_id.id
    #     else:
    #         return self.partner_id.property_account_payable_id.id
        
    # def check_pdc_account(self):
    #     if self.payment_type == 'receive_money':
    #         if not self.env.company.pdc_customer:
    #             raise UserError("Please set a valid PDC payment account for Customer!")
    #         return self.env.company.pdc_customer.id
    #     else:
    #         if not self.env.company.pdc_vendor:
    #             raise UserError("Please set a valid PDC payment account for Supplier!")
    #         return self.env.company.pdc_vendor.id

    def get_partner_account(self):
        if self.payment_type == 'receive_money':
            account = self.partner_id.property_account_receivable_id
        else:
            account = self.partner_id.property_account_payable_id
        if not account:
            raise UserError("Partner is missing a valid receivable or payable account.")
        return account.id  
    
    def get_bank_account(self):
        if self.payment_type == 'receive_money':
            account = self.journal_id.default_account_id
        if not account:
            raise UserError("Please map default account for the Bank")
        return account.id


    def action_returned(self):
        self.check_payment_amount()

        pdc_account = self.check_pdc_account()
        partner_account = self.get_partner_account()

        original_registration_lines = self.deposited_debit | self.deposited_credit

        # Reverse the registration entry: the amount moves back out of PDC
        # Receivable and onto the partner's normal receivable/payable
        # account, since the cheque is going back to them unused - they
        # owe (or are owed) the money again, same as before it was
        # registered as a PDC.
        if self.payment_type == 'receive_money':
            move_line_vals_debit = self.get_debit_move_line(partner_account)
            move_line_vals_credit = self.get_credit_move_line(pdc_account)
        else:
            move_line_vals_debit = self.get_debit_move_line(pdc_account)
            move_line_vals_credit = self.get_credit_move_line(partner_account)

        if self.memo:
            move_line_vals_debit.update({'name': 'PDC Payment returned: ' + self.memo})
            move_line_vals_credit.update({'name': 'PDC Payment returned: ' + self.memo})
        else:
            move_line_vals_debit.update({'name': 'PDC Payment returned'})
            move_line_vals_credit.update({'name': 'PDC Payment returned'})

        analytic_distribution = self._get_analytic_distribution()
        move_line_vals_debit["analytic_distribution"] = analytic_distribution
        move_line_vals_credit["analytic_distribution"] = analytic_distribution

        move_vals = self.get_move_vals(move_line_vals_debit, move_line_vals_credit)
        return_move = self.env['account.move'].create(move_vals)
        return_move.action_post()

        # Close out the PDC Receivable line for this cheque - reconcile the
        # original registration debit against this reversal's credit (both
        # on the PDC account) so the account nets to zero for it. The new
        # debit on the partner's receivable/payable is left unreconciled on
        # purpose - it's a fresh open item, since the customer's debt is
        # active again.
        lines_to_reconcile = (original_registration_lines | return_move.line_ids).filtered(
            lambda r: r.account_id.id == pdc_account
        )
        if lines_to_reconcile and len(lines_to_reconcile) > 1:
            lines_to_reconcile.reconcile()

        self.write({
            'state': 'returned',
            'deposited_debit': False,
            'deposited_credit': False,
        })

    def get_debit_move_line(self, account):
        if not account:
            raise UserError("Missing debit account for PDC transaction.")
        return {
            'partner_id': self.partner_id.commercial_partner_id.id,
            'pdc_id': self.id,
            'account_id': account,
            'debit': self.payment_amount,
            'ref': self.memo,
            'date': self.payment_date,
            'date_maturity': self.due_date,
        }

    def get_credit_move_line(self, account):
        if not account:
            raise UserError("Missing credit account for PDC transaction.")
        return {
            'partner_id': self.partner_id.commercial_partner_id.id,
            'pdc_id': self.id,
            'account_id': account,
            'credit': self.payment_amount,
            'ref': self.memo,
            'date': self.payment_date,
            'date_maturity': self.due_date,
        }

    # def get_credit_move_line(self, account):
    #     return {
    #         'pdc_id': self.id,
    #         #             'partner_id': self.partner_id.id,
    #         'account_id': account,
    #         'credit': self.payment_amount,
    #         'ref': self.memo,
    #         'date': self.payment_date,
    #         'date_maturity': self.due_date,
    #     }

    # def get_debit_move_line(self, account):
    #     return {
    #         'pdc_id': self.id,
    #         #             'partner_id': self.partner_id.id,
    #         'account_id': account,
    #         'debit': self.payment_amount,
    #         'ref': self.memo,
    #         'date': self.payment_date,
    #         'date_maturity': self.due_date,
    #     }

    def get_move_vals(self, debit_line, credit_line):
        return {
            'pdc_id': self.id,
            'date': self.payment_date,
            'journal_id': self.journal_id.id,
            # 'partner_id': self.partner_id.id,
            'partner_id': self.partner_id.commercial_partner_id.id,
            'ref': self.memo,
            'move_type': 'entry',
            'line_ids': [(0, 0, debit_line),
                         (0, 0, credit_line)],
            'report_ref': (
                f"contract:{self.invoice_id.tenancy_id.tenancy_seq}-"
                f"chq#{getattr(self, 'reference', False)}-"
                f"date:{self.due_date}"  ) if self.invoice_id else False
        }

    def action_deposited(self):
        move = self.env['account.move']

        self.check_payment_amount()  # amount must be positive
        pdc_account = self.check_pdc_account()
        partner_account = self.get_partner_account()
        bank_account = self.get_bank_account()

        # Create Journal Item
        move_line_vals_debit = {}
        move_line_vals_credit = {}
        if self.payment_type == 'receive_money':
            move_line_vals_debit = self.get_debit_move_line(bank_account)
            move_line_vals_credit = self.get_credit_move_line(pdc_account)
        else:
            move_line_vals_debit = self.get_debit_move_line(pdc_account)
            move_line_vals_credit = self.get_credit_move_line(bank_account)

        analytic_distribution = self._get_analytic_distribution()

        move_line_vals_debit["analytic_distribution"] = analytic_distribution
        move_line_vals_credit["analytic_distribution"] = analytic_distribution

        # create move and post it
        move_vals = self.get_move_vals(
            move_line_vals_debit, move_line_vals_credit)

        self.write({
            'state': 'deposited',
        })

        # total_amount_residuals = sum(
        #     self.invoice_ids.mapped('amount_residual'))
        # if self.invoice_ids and total_amount_residuals != 0:
        move_id = move.create(move_vals)
        move_id.action_post()

        self.write({'deposited_debit': move_id.line_ids.filtered(lambda x: x.debit > 0),
                    'deposited_credit': move_id.line_ids.filtered(lambda x: x.credit > 0)})

    def action_bounced(self):
        move = self.env['account.move']

        self.check_payment_amount()  # amount must be positive
        pdc_account = self.check_pdc_account()
        partner_account = self.get_partner_account()
        bank_account = self.get_bank_account()

        original_deposit_lines = self.deposited_debit | self.deposited_credit

        register_partner_lines = self.env['account.move.line'].search([
            ('pdc_id', '=', self.id),
            ('account_id', '=', partner_account),
            ('reconciled', '=', True),
        ])


        for line in register_partner_lines:
            line.remove_move_reconcile()

        # Create Journal Item
        move_line_vals_debit = {}
        move_line_vals_credit = {}

        if self.payment_type == 'receive_money':
            move_line_vals_debit = self.get_debit_move_line(pdc_account)
            move_line_vals_credit = self.get_credit_move_line(bank_account)
        else:
            move_line_vals_debit = self.get_debit_move_line(bank_account)
            move_line_vals_credit = self.get_credit_move_line(pdc_account)

        if self.memo:
            move_line_vals_debit.update({'name': 'PDC Payment bounced :'+self.memo})
            move_line_vals_credit.update({'name': 'PDC Payment bounced :'+self.memo})
        else:
            move_line_vals_debit.update({'name': 'PDC Payment bounced'})
            move_line_vals_credit.update({'name': 'PDC Payment bounced'})

        analytic_distribution = self._get_analytic_distribution()

        move_line_vals_debit["analytic_distribution"] = analytic_distribution
        move_line_vals_credit["analytic_distribution"] = analytic_distribution
        
        # create move and post it
        move_vals = self.get_move_vals(
            move_line_vals_debit, move_line_vals_credit)

        bounce_move = move.create(move_vals)
        bounce_move.action_post()

        lines_to_reconcile = (original_deposit_lines | bounce_move.line_ids).filtered(
            lambda r: r.account_id.id == partner_account
        )
        if lines_to_reconcile and len(lines_to_reconcile) > 1:
            lines_to_reconcile.reconcile()

        self.write({
            'state': 'bounced',
            'deposited_debit': False,
            'deposited_credit': False,
        })



    # def action_bounced(self):
    #         self.check_payment_amount()
    #         pdc_account = self.check_pdc_account()
    #         partner_account = self.get_partner_account()
    #         bank_account = self.journal_id._get_journal_outbound_outstanding_payment_accounts() if self.payment_type == 'receive_money' else self.journal_id._get_journal_inbound_outstanding_payment_accounts()
    #         bank_account = bank_account[0].id if bank_account else False
    #         if self.state == 'done':
    #             pdc_account = bank_account

    #         if self.payment_type == 'receive_money':
    #             debit_line_vals = self._comman_move_line_vals(
    #                 f"PDC Payment Bounce {self.memo or ''} {self.reference or ''}",
    #                 partner_account,
    #                 self.payment_amount,
    #                 True
    #             )
    #             credit_line_vals = self._comman_move_line_vals(
    #                 f"PDC Payment Bounce {self.memo or ''} {self.reference or ''}",
    #                 pdc_account,
    #                 self.payment_amount,
    #                 False
    #             )
    #         else:
    #             debit_line_vals = self._comman_move_line_vals(
    #                 f"PDC Payment Bounce {self.memo or ''} {self.reference or ''}",
    #                 pdc_account,
    #                 self.payment_amount,
    #                 True
    #             )
    #             credit_line_vals = self._comman_move_line_vals(
    #                 f"PDC Payment Bounce {self.memo or ''} {self.reference or ''}",
    #                 partner_account,
    #                 self.payment_amount,
    #                 False
    #             )

    #         move_vals = self.get_move_vals(
    #             debit_line_vals, credit_line_vals)
    #         move_id = self.env['account.move'].create(move_vals)
    #         move_id.action_post()

    #         deposit_move_lines = self.deposit_move_id.line_ids
    #         deposit_move_lines.filtered(lambda x: x.pdc_rec_move_id).mapped(lambda x: x.matched_debit_ids | x.matched_credit_ids).unlink()

    #         (deposit_move_lines | move_id.line_ids).filtered(lambda line: line.account_id.id == partner_account).reconcile()

    #         self.write({'state': 'bounced'})


    def get_reconcilation_domain(self):
        return [
            ('parent_state', '=', 'posted'),
            ('account_type', 'in', self.env['account.payment']._get_valid_payment_account_types()),
            ('reconciled', '=', False),
        ]

    def action_done(self):
        self.ensure_one()
        # move = self.env['account.move']

        # self.check_payment_amount()  # amount must be positive
        # pdc_account = self.check_pdc_account()
        # bank_account = self.journal_id._get_journal_inbound_outstanding_payment_accounts() if self.payment_type == 'receive_money' else self.journal_id._get_journal_outbound_outstanding_payment_accounts()
        # bank_account = bank_account[0].id if bank_account else False

        # pdc_deposit_move_lines = self.deposited_debit | self.deposited_credit

        # domain = self.get_reconcilation_domain()

        # (self.invoice_ids.line_ids | pdc_deposit_move_lines).filtered_domain(domain).reconcile()

        # is_receive_money = self.payment_type == 'receive_money'
        # if is_receive_money:
        #         debit_move_line_vals = self.get_debit_move_line(bank_account)
        #         credit_move_line_vals = self.get_credit_move_line(pdc_account)
        # else:
        #         debit_move_line_vals = self.get_debit_move_line(pdc_account)
        #         credit_move_line_vals = self.get_credit_move_line(bank_account)

        # # create move and post it
        # move_vals = self.get_move_vals(
        #     debit_move_line_vals, credit_move_line_vals)
        # move = self.env['account.move'].create(move_vals)
        # move.action_post()
        # (move.line_ids | pdc_deposit_move_lines).filtered(lambda line: line.account_id.id == pdc_account).reconcile()

        self.write({
            'state': 'done',
            'done_date':date.today(),
            })

    # form view cancel button
    def action_cancel(self):
        self.action_delete_related_moves()
        if self.company_id.pdc_operation_type == 'cancel':
            self.write({'state': 'cancel'})

        elif self.company_id.pdc_operation_type == 'cancel_draft':
            self.write({'state': 'draft'})

        elif self.company_id.pdc_operation_type == 'cancel_delete':
            self.write({'state': 'draft'})
            self.unlink()
            return {'type': 'ir.actions.act_window_close'}

    # multi action methods
    def action_pdc_cancel(self):
        self.action_delete_related_moves()
        self.write({'state': 'cancel'})

    def action_pdc_cancel_draft(self):
        self.action_delete_related_moves()
        self.write({'state': 'draft'})

    def action_pdc_cancel_delete(self):
        self.action_delete_related_moves()
        self.write({'state': 'draft'})
        self.unlink()

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('payment_type') == 'receive_money':
                vals['name'] = self.env['ir.sequence'].next_by_code(
                    'pdc.payment.customer')
            elif vals.get('payment_type') == 'send_money':
                vals['name'] = self.env['ir.sequence'].next_by_code(
                    'pdc.payment.vendor')

        res = super().create(vals_list)
        res.attachment_ids.write({
            'res_id': res.id
        })
        return res

    # ==============================
    #    CRON SCHEDULER CUSTOMER
    # ==============================
    @api.model
    def notify_customer_due_date(self):
        emails = []
        if self.env.company.is_cust_due_notify:
            notify_day_1 = self.env.company.notify_on_1
            notify_day_2 = self.env.company.notify_on_2
            notify_day_3 = self.env.company.notify_on_3
            notify_day_4 = self.env.company.notify_on_4
            notify_day_5 = self.env.company.notify_on_5
            notify_date_1 = False
            notify_date_2 = False
            notify_date_3 = False
            notify_date_4 = False
            notify_date_5 = False
            if notify_day_1:
                notify_date_1 = fields.Date.today() + timedelta(days=int(notify_day_1)*-1)
            if notify_day_2:
                notify_date_2 = fields.Date.today() + timedelta(days=int(notify_day_2)*-1)
            if notify_day_3:
                notify_date_3 = fields.Date.today() + timedelta(days=int(notify_day_3)*-1)
            if notify_day_4:
                notify_date_4 = fields.Date.today() + timedelta(days=int(notify_day_4)*-1)
            if notify_day_5:
                notify_date_5 = fields.Date.today() + timedelta(days=int(notify_day_5)*-1)

            records = self.search([('payment_type', '=', 'receive_money')])
            for user in self.env.company.sh_user_ids:
                if user.partner_id and user.partner_id.email:
                    emails.append(user.partner_id.email)
            email_values = {
                'email_to': ','.join(emails),
            }
            view = self.env.ref("sh_pdc.sh_pdc_payment_form_view",
                                raise_if_not_found=False).sudo()
            view_id = view.id if view else 0
            for record in records:
                if (record.due_date == notify_date_1
                    or record.due_date == notify_date_2
                    or record.due_date == notify_date_3
                    or record.due_date == notify_date_4
                        or record.due_date == notify_date_5):

                    if self.env.company.is_notify_to_customer:
                        # template_download_id = record.env['ir.model.data'].get_object(
                        #     'sh_pdc', 'sh_pdc_company_to_customer_notification_1'
                        #     )
                        template_download_id = self.env.ref(
                            'sh_pdc.sh_pdc_company_to_customer_notification_1')
                        _ = record.env['mail.template'].browse(
                            template_download_id.id
                        ).send_mail(record.id, email_layout_xmlid='mail.mail_notification_light', force_send=True)
                    if self.env.company.is_notify_to_user and self.env.company.sh_user_ids:
                        url = ''
                        base_url = request.env['ir.config_parameter'].sudo(
                        ).get_str('web.base.url', False)
                        url = base_url + "/web#id=" + \
                            str(record.id) + \
                            "&&model=pdc.wizard&view_type=form&view_id=" + \
                            str(view_id)
                        ctx = {
                            "customer_url": url,
                        }
                        # template_download_id = record.env['ir.model.data'].get_object(
                        #     'sh_pdc', 'sh_pdc_company_to_int_user_notification_1'
                        #     )
                        template_download_id = self.env.ref(
                            'sh_pdc.sh_pdc_company_to_int_user_notification_1')
                        _ = request.env['mail.template'].sudo().browse(template_download_id.id).with_context(ctx).send_mail(
                            record.id, email_values=email_values, email_layout_xmlid='mail.mail_notification_light', force_send=True)


    # ==============================
    #    CRON SCHEDULER VENDOR
    # ==============================

    @api.model
    def notify_vendor_due_date(self):
        emails = []
        if self.env.company.is_vendor_due_notify:
            notify_day_1_ven = self.env.company.notify_on_1_vendor
            notify_day_2_ven = self.env.company.notify_on_2_vendor
            notify_day_3_ven = self.env.company.notify_on_3_vendor
            notify_day_4_ven = self.env.company.notify_on_4_vendor
            notify_day_5_ven = self.env.company.notify_on_5_vendor
            notify_date_1_ven = False
            notify_date_2_ven = False
            notify_date_3_ven = False
            notify_date_4_ven = False
            notify_date_5_ven = False
            if notify_day_1_ven:
                notify_date_1_ven = fields.Date.today() + timedelta(days=int(notify_day_1_ven) * -1)
            if notify_day_2_ven:
                notify_date_2_ven = fields.Date.today() + timedelta(days=int(notify_day_2_ven) * -1)
            if notify_day_3_ven:
                notify_date_3_ven = fields.Date.today() + timedelta(days=int(notify_day_3_ven) * -1)
            if notify_day_4_ven:
                notify_date_4_ven = fields.Date.today() + timedelta(days=int(notify_day_4_ven) * -1)
            if notify_day_5_ven:
                notify_date_5_ven = fields.Date.today() + timedelta(days=int(notify_day_5_ven) * -1)

            records = self.search([('payment_type', '=', 'send_money')])
            for user in self.env.company.sh_user_ids_vendor:
                if user.partner_id and user.partner_id.email:
                    emails.append(user.partner_id.email)
            email_values = {
                'email_to': ','.join(emails),
            }
            view = self.env.ref(
                "sh_pdc.sh_pdc_payment_form_view", raise_if_not_found=False)
            view_id = view.id if view else 0
            for record in records:
                if (record.due_date == notify_date_1_ven
                    or record.due_date == notify_date_2_ven
                    or record.due_date == notify_date_3_ven
                    or record.due_date == notify_date_4_ven
                        or record.due_date == notify_date_5_ven):

                    if self.env.company.is_notify_to_vendor:
                        template_download_id = self.env.ref(
                            'sh_pdc.sh_pdc_company_to_customer_notification_1')
                        _ = record.env['mail.template'].browse(
                            template_download_id.id
                        ).send_mail(record.id, email_layout_xmlid='mail.mail_notification_light', force_send=True)
                    if self.env.company.is_notify_to_user_vendor and self.env.company.sh_user_ids_vendor:
                        base_url = self.env['ir.config_parameter'].sudo().get_str('web.base.url', False)
                        url = (
                            base_url + "/web#id=" + str(record.id) +
                            "&&model=pdc.wizard&view_type=form&view_id=" + str(view_id)
                        )
                        ctx = {
                            "customer_url": url,
                        }
                        template_download_id = self.env.ref(
                            'sh_pdc.sh_pdc_company_to_int_user_notification_1')
                        _ = self.env['mail.template'].sudo().browse(
                            template_download_id.id
                        ).with_context(ctx).send_mail(
                            record.id,
                            email_values=email_values,
                            email_layout_xmlid='mail.mail_notification_light',
                            force_send=True,
                        )

    # Multi Action Starts for change the state of PDC check

    def action_set_draft(self):
        self.sudo().write({
            'state': 'draft',
        })

    def action_delete_related_moves(self):

        for model in self:
            move_ids = self.env['account.move'].search(
                [('pdc_id', '=', model.id)])
            for move in move_ids:
                move.button_draft()
                lines = self.env['account.move.line'].search(
                    [('move_id', '=', move.id)])
                lines.unlink()

            model.sudo().write({
                'done_date': False
            })

            for move in move_ids:
                self.env.cr.execute(
                    """ delete from account_move where id =%s""" % (move.id,))

    def action_state_register(self):
        active_ids = self.env.context.get('active_ids')
        active_model = self.env.context.get('active_model')

        if len(active_ids) > 0:
            active_models = self.env[active_model].browse(active_ids)
            states = active_models.mapped('state')

            if len(set(states)) == 1:
                if states[0] == 'draft':
                    for active_model in active_models:
                        active_model.action_register()
                else:
                    raise UserError(
                        "Only Draft state PDC check can switch to Register state!!")
            else:
                raise UserError(
                    "States must be same!!")

    def action_state_return(self):
        active_ids = self.env.context.get('active_ids')
        active_model = self.env.context.get('active_model')

        if len(active_ids) > 0:
            active_models = self.env[active_model].browse(active_ids)
            states = active_models.mapped('state')

            if len(set(states)) == 1:
                if states[0] == 'registered':
                    for active_model in active_models:
                        active_model.action_returned()
                else:
                    raise UserError(
                        "Only Register state PDC check can switch to return state!!")
            else:
                raise UserError(
                    "States must be same!!")

    def action_state_deposit(self):
        active_ids = self.env.context.get('active_ids')
        active_model = self.env.context.get('active_model')

        if len(active_ids) > 0:
            active_models = self.env[active_model].browse(active_ids)
            states = active_models.mapped('state')

            if len(set(states)) == 1:
                if states[0] in ['registered', 'returned', 'bounced']:
                    for active_model in active_models:
                        active_model.action_deposited()
                else:
                    raise UserError(
                        "Only Register,Return and Bounce state PDC check can switch to Deposit state!!")
            else:
                raise UserError(
                    "States must be same!!")

    def action_state_bounce(self):
        active_ids = self.env.context.get('active_ids')
        active_model = self.env.context.get('active_model')

        if len(active_ids) > 0:
            active_models = self.env[active_model].browse(active_ids)
            states = active_models.mapped('state')

            if len(set(states)) == 1:
                if states[0] == 'deposited':
                    for active_model in active_models:
                        active_model.action_bounced()
                else:
                    raise UserError(
                        "Only Deposit state PDC check can switch to Bounce state!!")
            else:
                raise UserError(
                    "States must be same!!")

    def action_state_done(self):
        active_ids = self.env.context.get('active_ids')
        active_model = self.env.context.get('active_model')

        if len(active_ids) > 0:
            active_models = self.env[active_model].browse(active_ids)
            states = active_models.mapped('state')

            if len(set(states)) == 1:
                if states[0] == 'deposited':
                    for active_model in active_models:
                        active_model.action_done()
                else:
                    raise UserError(
                        "Only Deposit state PDC check can switch to Done state!!")
            else:
                raise UserError(
                    "States must be same!!")

    def action_state_cancel(self):
        active_ids = self.env.context.get('active_ids')
        active_model = self.env.context.get('active_model')

        if len(active_ids) > 0:
            active_models = self.env[active_model].browse(active_ids)
            states = active_models.mapped('state')

            if len(set(states)) == 1:
                if states[0] in ['registered', 'returned', 'bounced']:
                    for active_model in active_models:
                        active_model.action_cancel()
                else:
                    raise UserError(
                        "Only Register,Return and Bounce state PDC check can switch to Cancel state!!")
            else:
                raise UserError(
                    "States must be same!!")

    def _get_analytic_distribution(self):
        self.ensure_one()

        if not self.invoice_ids:
            return {}

        # Take the first invoice line that has an analytic distribution
        line = self.invoice_ids.mapped("invoice_line_ids").filtered(
            lambda l: l.analytic_distribution
        )[:1]

        return line.analytic_distribution or {}

    @api.model
    def action_deposit_cheque(self):
        records = self.search([
            ('state', '=', 'registered'),
            ('payment_date', '=', fields.Date.today()),
        ])

        for rec in records:
            rec.action_deposited()
            
    def action_hold(self):
        self.state = "hold"

    def action_unhold(self):
        self.ensure_one()

        return {
            "name": "Unhold PDC",
            "type": "ir.actions.act_window",
            "res_model": "pdc.unhold.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {
                "default_pdc_id": self.id,
                "default_payment_date": self.payment_date,
                "default_due_date": self.due_date,
            },
        }
    