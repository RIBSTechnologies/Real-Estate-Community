# -*- coding: utf-8 -*-
# Part of Softhealer Technologies.
from odoo import api, fields, models


class AccountInvoice(models.Model):
    _inherit = "account.move"

    is_boolean = fields.Boolean(compute="compute_is_boolean")

    def compute_is_boolean(self):
        for rec in self:
            rec.is_boolean = False
            if rec.pdc_payment_ids.filtered(lambda x: x.state in ['registered', 'deposited']):
                rec.is_boolean = True

    def open_pdc_payment(self):
        [action] = self.env.ref('sh_pdc.sh_pdc_payment_menu_action').read()
        action['domain'] = [('id', 'in', self.pdc_payment_ids.ids)]
        return action

    def _compute_pdc_payment(self):
        for rec in self:
            rec.pdc_payment_count = len(self.pdc_payment_ids)

    pdc_id = fields.Many2one('pdc.wizard')
    pdc_payment_ids = fields.Many2many(
        'pdc.wizard', compute='_compute_pdc_payment_invoice', store=True)
    pdc_payment_count = fields.Integer(
        "Pdc payment count", compute='_compute_pdc_payment', store=True)
    total_pdc_payment = fields.Monetary("Total ", compute='_compute_total_pdc', store=True)
    total_pdc_pending = fields.Monetary(
        "Total Pending", compute='_compute_total_pdc', store=True)
    total_pdc_cancel = fields.Monetary(
        "Total Cancel", compute='_compute_total_pdc', store=True)
    total_pdc_received = fields.Monetary(
        "Total Received", compute='_compute_total_pdc', store=True)

    sh_pdc_status = fields.Selection([('draft', 'Draft'), ('registered', 'Registered'), ('returned', 'Returned'), ('hold','On Hold'),
                              ('deposited', 'Deposited'), ('bounced', 'Bounced'), ('done', 'Done'), ('cancel', 'Cancelled')], string="PDC Status",compute='_compute_latest_pdc_payment_status',store=True,search='_search_latest_pdc_payment_status')

    @api.depends('pdc_payment_ids.state')
    def _compute_latest_pdc_payment_status(self):
        for rec in self:
            rec.sh_pdc_status = False
            if rec.pdc_payment_ids:
                rec.sh_pdc_status = rec.pdc_payment_ids[-1].state

    def _search_latest_pdc_payment_status(self, operator, value):

        results = []
        moves = self.env['account.move'].search([])
        if operator == '>':
            for rec in moves:
                pdc_payment_ids = self.env['pdc.wizard'].search([('id','in',rec.pdc_payment_ids.ids)])
                if pdc_payment_ids:
                    results.extend(pdc_payment_ids.ids)

            return [('id', 'in', results)]
        elif operator == '=':

            pdc_payment_ids = self.env['pdc.wizard'].search([('id','not in',moves.mapped('pdc_payment_ids').ids)])
            if pdc_payment_ids:
                results.extend(pdc_payment_ids.ids)

            return [('id', 'in', results)]

    @api.depends('pdc_payment_ids.state')
    def _compute_total_pdc(self):
        for rec in self:
            rec.total_pdc_payment = 0.0
            rec.total_pdc_pending = 0.0
            rec.total_pdc_cancel = 0.0
            rec.total_pdc_received = 0.0
            if rec.pdc_payment_ids:
                for pdc_payment in rec.pdc_payment_ids:
                    if pdc_payment.state in ('done'):
                        rec.total_pdc_received += pdc_payment.payment_amount
                    elif pdc_payment.state in ('cancel'):
                        rec.total_pdc_cancel += pdc_payment.payment_amount
                    else:
                        rec.total_pdc_pending += pdc_payment.payment_amount
            rec.total_pdc_payment = rec.total_pdc_pending + \
                rec.total_pdc_received + rec.total_pdc_cancel

    def _compute_pdc_payment_invoice(self):
        self.pdc_payment_ids = False
        for move in self:
            pdcs = self.env["pdc.wizard"].search([
                '|', ('invoice_id', '=', move.id), ('invoice_ids.id', '=', move.id)
            ])
            if pdcs:
                move.pdc_payment_ids = [(6, 0, pdcs.ids)]



    # def js_assign_outstanding_line(self, line_id):
    #     res = super().js_assign_outstanding_line(line_id)
    #     for invoice in self:
    #         line = self.env['account.move.line'].browse(line_id)
    #         payment_move = line.move_id
    #         pdc = line.pdc_id
    #         if pdc:
    #             pdc.invoice_ids = [(4, invoice.id)]
    #             invoice._compute_latest_pdc_payment_status()

    #     return res


    def js_assign_outstanding_line(self, line_id):
        res = super().js_assign_outstanding_line(line_id)
        for invoice in self:
            line = self.env['account.move.line'].browse(line_id)
            payment_move = line.move_id
            pdc = payment_move.pdc_id
            if pdc:
                pdc.invoice_ids = [(4, invoice.id)]
                invoice._compute_latest_pdc_payment_status()

        return res



    def action_update_latest_pdc_status(self):
        for rec in self:
            rec.sh_pdc_status = False
            if rec.pdc_payment_ids:
                rec.sh_pdc_status = rec.pdc_payment_ids[-1].state