# -*- coding: utf-8 -*-

from odoo import _, api, fields, models
from odoo.exceptions import UserError


class MaintenancePartLine(models.Model):
    """Parts-procurement line for a maintenance request.

    Requested -> Approved/Rejected is a lightweight internal gate (cost
    approval matrix + warranty check). Once Approved, "Create Purchase
    Request" raises a real purchase.request/purchase.request.line (the OCA
    Purchase Requests app), which then follows its own native workflow:
    Draft -> To Approve -> Approved. From an Approved request line, the
    Purchasing team uses the standard "Purchase Order" wizard already
    provided by that app to generate the RFQ (purchase.order in draft
    state), and from there the normal Odoo Purchase/Inventory flow takes
    over: RFQ -> Confirm (becomes the Purchase Order) -> Receipt (GRN via
    stock.picking) -> Vendor Bill, with native 3-way matching (PO vs
    received qty vs invoiced qty). purchase_order_id/purchase_order_line_id
    here are computed from the request line's linked PO lines, so `po_state`
    always reflects the real document stage once one exists.
    """
    _name = 'maintenance.part.line'
    _description = 'Maintenance Part Procurement Line'
    _order = 'id'

    request_id = fields.Many2one('maintenance.request', string='Maintenance Request',
                                  required=True, ondelete='cascade')
    company_id = fields.Many2one(related='request_id.company_id', store=True)
    currency_id = fields.Many2one(related='company_id.currency_id', store=True)
    product_id = fields.Many2one('product.product', string='Product')
    description = fields.Char(string='Description')
    quantity = fields.Float(string='Quantity', default=1.0)
    estimated_cost = fields.Monetary(string='Estimated Unit Cost')
    vendor_id = fields.Many2one('res.partner', string='Vendor', domain=[('supplier_rank', '>=', 1)])
    state = fields.Selection([
        ('draft', 'Requested'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
        ('po_created', 'In Procurement'),
    ], string='Status', default='draft', copy=False)
    approved_by = fields.Many2one('res.users', string='Approved By', readonly=True, copy=False)
    approved_date = fields.Datetime(string='Approved On', readonly=True, copy=False)
    is_goods_part = fields.Boolean(string='Is Goods', compute='_compute_is_goods_part')
    under_warranty = fields.Boolean(string='Equipment Under Warranty', compute='_compute_under_warranty')

    purchase_request_id = fields.Many2one('purchase.request', string='Purchase Request',
                                           readonly=True, copy=False)
    purchase_request_line_id = fields.Many2one('purchase.request.line', readonly=True, copy=False)
    pr_state = fields.Selection(related='purchase_request_id.state', string='PR Status', readonly=True)

    purchase_order_id = fields.Many2one('purchase.order', string='Purchase Order', readonly=True,
                                         copy=False, store=True, compute='_compute_purchase_order')
    purchase_order_line_id = fields.Many2one('purchase.order.line', readonly=True, copy=False,
                                              store=True, compute='_compute_purchase_order')
    po_state = fields.Selection(related='purchase_order_id.state', string='PO Status', readonly=True)
    po_price_unit = fields.Float(related='purchase_order_line_id.price_unit', string='PO Unit Price', readonly=True)
    qty_received = fields.Float(related='purchase_order_line_id.qty_received', string='Qty Received', readonly=True)
    qty_invoiced = fields.Float(related='purchase_order_line_id.qty_invoiced', string='Qty Invoiced', readonly=True)
    invoice_status = fields.Selection(
        related='purchase_order_id.invoice_status', string='Bill Status', readonly=True)

    @api.depends('purchase_request_line_id.purchase_lines.order_id')
    def _compute_purchase_order(self):
        for line in self:
            po_line = line.purchase_request_line_id.purchase_lines[:1]
            line.purchase_order_line_id = po_line
            line.purchase_order_id = po_line.order_id

    @api.depends('product_id.type')
    def _compute_is_goods_part(self):
        for line in self:
            line.is_goods_part = line.product_id.type == 'consu'

    @api.depends('request_id.equipment_id.warranty_date', 'product_id.type')
    def _compute_under_warranty(self):
        today = fields.Date.today()
        for line in self:
            if not line.is_goods_part:
                # Warranty only applies to a physical Goods part, not services
                # (or a line whose product hasn't been picked yet).
                line.under_warranty = False
                continue
            warranty_date = line.request_id.equipment_id.warranty_date
            line.under_warranty = bool(warranty_date and warranty_date >= today)

    def action_approve(self):
        icp = self.env['ir.config_parameter'].sudo()
        threshold_manager = float(icp.get_str('al_shafar_extended.parts_approval_threshold_manager', '500'))
        threshold_secretary = float(icp.get_str('al_shafar_extended.parts_approval_threshold_secretary', '5000'))
        for line in self:
            amount = line.estimated_cost * line.quantity
            approver = False
            role_label = False
            if amount >= threshold_secretary:
                approver = line.company_id.company_secretary.user_id
                role_label = _("Company Secretary")
            elif amount >= threshold_manager:
                approver = line.request_id.property_id.property_manager.user_id
                role_label = _("Property Manager")

            if approver and self.env.user != approver and not self.env.user.has_group('base.group_system'):
                raise UserError(_("This part line (amount: %.2f) requires %s approval.") % (amount, role_label))

            line.write({
                'state': 'approved',
                'approved_by': self.env.user.id,
                'approved_date': fields.Datetime.now(),
            })

    def action_reject(self):
        self.write({'state': 'rejected'})

    def _get_analytic_distribution(self):
        """Building + Unit analytic accounts of the maintenance request, as a
        single 100% distribution - same Building/Unit tagging account.move
        already auto-applies to invoice lines (see AccountMove.
        _get_four_level_analytic_accounts), so parts procurement rolls up
        into the same per-building/per-unit cost reporting. Also what keeps
        the resulting purchase.request.line/purchase.order.line at a clean
        100% from the start (the 100% check itself is bypassed on purchase
        lines by purchase_extended, see models/analytic_distribution.py).
        """
        self.ensure_one()
        account_ids = [
            self.request_id.building_id_parent.building_account_id.id,
            self.request_id.property_id.unit_account_id.id,
        ]
        account_ids = [account_id for account_id in account_ids if account_id]
        if not account_ids:
            return {}
        key = ",".join(str(account_id) for account_id in account_ids)
        return {key: 100.0}

    def action_create_purchase_request(self):
        for line in self:
            if line.state != 'approved':
                raise UserError(_("Only approved parts can be sent to a Purchase Request."))
            if not line.product_id:
                raise UserError(_("Set a part before creating a purchase request."))
            if line.purchase_request_id:
                raise UserError(_("A purchase request has already been created for this part."))

            purchase_request = self.env['purchase.request'].sudo().create({
                'requested_by': self.env.user.id,
                'company_id': line.company_id.id,
                'origin': line.request_id.name,
                'line_ids': [(0, 0, {
                    'product_id': line.product_id.id,
                    'name': line.description or line.product_id.name,
                    'product_uom_id': line.product_id.uom_id.id,
                    'product_qty': line.quantity,
                    'estimated_cost': line.estimated_cost,
                    'date_required': fields.Date.today(),
                    'analytic_distribution': line._get_analytic_distribution(),
                })],
            })
            line.write({
                'purchase_request_id': purchase_request.id,
                'purchase_request_line_id': purchase_request.line_ids[:1].id,
                'state': 'po_created',
            })

        if len(self) == 1:
            return {
                'type': 'ir.actions.act_window',
                'name': _('Purchase Request'),
                'res_model': 'purchase.request',
                'res_id': self.purchase_request_id.id,
                'view_mode': 'form',
                'target': 'current',
            }

    def action_view_purchase_request(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Purchase Request'),
            'res_model': 'purchase.request',
            'res_id': self.purchase_request_id.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def action_view_purchase_order(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Purchase Order'),
            'res_model': 'purchase.order',
            'res_id': self.purchase_order_id.id,
            'view_mode': 'form',
            'target': 'current',
        }


class MaintenanceRequestPartLines(models.Model):
    _inherit = 'maintenance.request'

    part_line_ids = fields.One2many('maintenance.part.line', 'request_id', string='Parts / Procurement')
    parts_total_untaxed_amount = fields.Monetary(
        string='Parts Total Untaxed Amount', compute='_compute_parts_total_untaxed_amount')

    @api.depends('part_line_ids.estimated_cost', 'part_line_ids.quantity')
    def _compute_parts_total_untaxed_amount(self):
        for request in self:
            request.parts_total_untaxed_amount = sum(
                line.estimated_cost * line.quantity for line in request.part_line_ids)
