# -*- coding: utf-8 -*-

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

from .maintenance_request import STAGE_HANDOVER, STAGE_SCRAP

# Included Products stay editable (add lines, raise more invoices/bills) until
# the request reaches one of these stages.
PRODUCTS_LOCKED_STAGES = (STAGE_HANDOVER, STAGE_SCRAP)


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    maintenance_request_id = fields.Many2one(
        'maintenance.request', string='Maintenance Request', index='btree_not_null', copy=False)
    maintenance_move_id = fields.Many2one(
        'account.move', string='Maintenance Invoice/Bill', index='btree_not_null', copy=False)

    def _create_backorder(self, *args, **kwargs):
        # A partial delivery's backorder stays linked, so the invoice keeps
        # waiting for it (and the smart buttons still count it).
        backorders = super()._create_backorder(*args, **kwargs)
        for backorder in backorders:
            origin = backorder.backorder_id
            if origin.maintenance_request_id or origin.maintenance_move_id:
                backorder.write({
                    'maintenance_request_id': origin.maintenance_request_id.id,
                    'maintenance_move_id': origin.maintenance_move_id.id,
                })
        return backorders


class AccountMoveMaintenanceStock(models.Model):
    """Customer invoice / vendor bill raised from a maintenance request
    (Included Products -> Create Invoice / Create Bill) gets a button to raise
    its stock document: "Create Delivery Order" on the invoice (parts leave
    the warehouse), "Create Receipt" on the bill (parts come in). Only Goods
    lines move stock. The picking is confirmed (the delivery also reserved)
    but left for the warehouse to validate, like any other Odoo picking.
    Invoices/bills not created from maintenance never show the button.

    A maintenance customer invoice with goods lines can only be confirmed
    once its Delivery Order is validated (see _post). Other invoices are not
    affected.
    """
    _inherit = 'account.move'

    maintenance_picking_ids = fields.One2many(
        'stock.picking', 'maintenance_move_id', string='Maintenance Transfers')
    maintenance_picking_count = fields.Integer(compute='_compute_maintenance_picking_count')
    can_create_maintenance_picking = fields.Boolean(compute='_compute_maintenance_picking_count')
    maintenance_delivery_pending = fields.Boolean(compute='_compute_maintenance_picking_count')

    @api.depends('maintenance_picking_ids.state', 'maintenance_request_id', 'move_type', 'state',
                 'invoice_line_ids.purchase_line_id')
    def _compute_maintenance_picking_count(self):
        for move in self:
            # sudo: accounting users without Inventory rights still see the button state
            pickings = move.sudo().maintenance_picking_ids.filtered(lambda p: p.state != 'cancel')
            move.maintenance_picking_count = len(pickings)
            move.can_create_maintenance_picking = bool(
                move.maintenance_request_id
                and move.move_type in ('out_invoice', 'in_invoice')
                and move.state != 'cancel'
                and not pickings
                # a bill from a maintenance RFQ/PO already has the PO's receipt
                and not move.invoice_line_ids.purchase_line_id
            )
            move.maintenance_delivery_pending = move.state == 'draft' and move._maintenance_delivery_pending()

    def _maintenance_goods_lines(self):
        return self.invoice_line_ids.filtered(
            lambda line: line.display_type == 'product'
            and line.product_id.type == 'consu'
            and line.quantity > 0)

    def _maintenance_delivery_pending(self):
        """True for a maintenance customer invoice with goods whose Delivery
        Order is missing or not validated yet."""
        self.ensure_one()
        if not (self.maintenance_request_id and self.move_type == 'out_invoice'
                and self._maintenance_goods_lines()):
            return False
        deliveries = self.sudo().maintenance_picking_ids.filtered(
            lambda p: p.picking_type_code == 'outgoing' and p.state != 'cancel')
        return not deliveries or any(p.state != 'done' for p in deliveries)

    def _post(self, soft=True):
        pending = self.filtered(lambda move: move._maintenance_delivery_pending())
        if pending:
            raise UserError(_(
                "Invoice %s was created from a maintenance request: create and validate its "
                "Delivery Order before confirming it.", ', '.join(pending.mapped('display_name'))))
        return super()._post(soft=soft)

    def action_create_maintenance_picking(self):
        self.ensure_one()
        if not self.can_create_maintenance_picking:
            raise UserError(_("A transfer already exists for this document, or it was not created from a maintenance request."))
        picking_type_code = 'outgoing' if self.move_type == 'out_invoice' else 'incoming'
        lines = self._maintenance_goods_lines()
        if not lines:
            raise UserError(_("There are no goods products on this document to transfer."))

        company = self.company_id
        warehouse = self.env['stock.warehouse'].sudo().search([('company_id', '=', company.id)], limit=1)
        picking_type = warehouse.out_type_id if picking_type_code == 'outgoing' else warehouse.in_type_id
        if not picking_type:
            raise UserError(_("No warehouse with a %(type)s operation type is configured for company %(company)s.",
                              type=_('Delivery') if picking_type_code == 'outgoing' else _('Receipt'),
                              company=company.name))

        partner = self.partner_id
        if picking_type_code == 'outgoing':
            location = picking_type.default_location_src_id
            location_dest = partner.property_stock_customer or self.env.ref('stock.stock_location_customers')
        else:
            location = partner.property_stock_supplier or self.env.ref('stock.stock_location_suppliers')
            location_dest = picking_type.default_location_dest_id

        move_vals = [
            (0, 0, _stock_move_vals(self.env, line.product_id, line.quantity,
                                    line.product_uom_id or line.product_id.uom_id, line.name,
                                    location, location_dest, company))
            for line in lines
        ]

        picking = self.env['stock.picking'].sudo().create({
            'picking_type_id': picking_type.id,
            'partner_id': partner.id,
            'location_id': location.id,
            'location_dest_id': location_dest.id,
            'origin': ' - '.join(filter(None, [self.name, self.maintenance_request_id.name])),
            'company_id': company.id,
            'maintenance_request_id': self.maintenance_request_id.id,
            'maintenance_move_id': self.id,
            'move_ids': move_vals,
        })
        picking.action_confirm()
        if picking_type_code == 'outgoing':
            picking.action_assign()
        return self.action_view_maintenance_pickings()

    def action_view_maintenance_pickings(self):
        self.ensure_one()
        pickings = self.sudo().maintenance_picking_ids
        return _picking_action(pickings, _('Delivery Orders') if self.move_type == 'out_invoice' else _('Receipts'))


def _stock_move_vals(env, product, quantity, uom, name, location, location_dest, company):
    vals = {
        'product_id': product.id,
        'product_uom_qty': quantity,
        'uom_id': uom.id,
        'location_id': location.id,
        'location_dest_id': location_dest.id,
        'company_id': company.id,
    }
    if 'name' in env['stock.move']._fields:
        vals['name'] = name or product.display_name
    return vals


def _picking_action(pickings, name):
    action = {
        'name': name,
        'type': 'ir.actions.act_window',
        'res_model': 'stock.picking',
        'context': {'create': False},
        'target': 'current',
    }
    if len(pickings) == 1:
        action.update(view_mode='form', res_id=pickings.id)
    else:
        action.update(view_mode='list,form', domain=[('id', 'in', pickings.ids)])
    return action


class PurchaseOrderMaintenance(models.Model):
    """RFQ raised from a maintenance request's Vendor Bill tab. The request
    link is passed on to the PO's receipt and vendor bill, so the request's
    Receipt / Vendor Bills smart buttons pick them up."""
    _inherit = 'purchase.order'

    maintenance_request_id = fields.Many2one(
        'maintenance.request', string='Maintenance Request', index='btree_not_null', copy=False, readonly=True)

    def _prepare_invoice(self):
        vals = super()._prepare_invoice()
        if self.maintenance_request_id:
            vals['maintenance_request_id'] = self.maintenance_request_id.id
        return vals

    def _prepare_picking(self):
        vals = super()._prepare_picking()
        if self.maintenance_request_id:
            vals['maintenance_request_id'] = self.maintenance_request_id.id
        return vals


class MaintenanceRequestStock(models.Model):
    """Included Products, split into three sub-tabs by line type:

    - Invoice: Create Invoice -> customer invoice (-> its Delivery Order).
    - Vendor Bill: Create RFQ -> purchase.order, then the native purchase
      flow: Confirm (PO) -> Receipt -> Vendor Bill. Receipt and bill carry the
      request (PurchaseOrderMaintenance), so the smart buttons capture them.
    - Internal Transfer: Create Internal Transfer -> internal stock.picking.

    Core locked the whole tab as soon as one document existed. Here it stays
    editable until Handover/Scrap: new lines can be added at any point and
    each Create button only takes the lines of its tab not yet on a document.
    Lines already on one are locked row by row (maintenance.product.line.is_billed)."""
    _inherit = 'maintenance.request'

    invoice_product_ids = fields.One2many(
        'maintenance.product.line', 'maintenance_id', string='Invoice Products',
        domain=[('line_type', '=', 'invoice')])
    bill_product_ids = fields.One2many(
        'maintenance.product.line', 'maintenance_id', string='Vendor Bill Products',
        domain=[('line_type', '=', 'bill')])
    transfer_product_ids = fields.One2many(
        'maintenance.product.line', 'maintenance_id', string='Internal Transfer Products',
        domain=[('line_type', '=', 'transfer')])
    bill_untaxed_amount = fields.Monetary(string='Total Untaxed Amount', compute='_compute_total_untaxed_amount')
    transfer_location_id = fields.Many2one(
        'stock.location', string='Source Location', domain=[('usage', '=', 'internal')],
        help="Leave empty to use the warehouse's internal transfer default.")
    transfer_location_dest_id = fields.Many2one(
        'stock.location', string='Destination Location', domain=[('usage', '=', 'internal')],
        help="Leave empty to use the warehouse's internal transfer default.")

    products_locked = fields.Boolean(compute='_compute_products_locked')
    can_create_invoice = fields.Boolean(compute='_compute_products_locked')
    can_create_rfq = fields.Boolean(compute='_compute_products_locked')
    can_create_transfer = fields.Boolean(compute='_compute_products_locked')
    # Payment Type is the tab switch: Invoice -> customer + Invoice tab, Bill ->
    # vendor + Vendor Bill tab, Internal Transfer -> Internal Transfer tab. One
    # request can go through all three; it only picks what is shown.
    payment_type = fields.Selection(selection_add=[('transfer', 'Internal Transfer')],
                                    ondelete={'transfer': 'set null'})
    # Not used any more - kept because views stored by earlier versions still
    # reference them, and the upgrade fails view validation without them.
    can_create_bill = fields.Boolean(compute='_compute_products_locked')
    payment_from_locked = fields.Boolean(compute='_compute_products_locked')

    @api.depends('maintenance_product_ids.price_subtotal', 'maintenance_product_ids.line_type')
    def _compute_total_untaxed_amount(self):
        # Core summed every line; each tab now shows its own total.
        for request in self:
            lines = request.maintenance_product_ids
            request.total_untaxed_amount = sum(
                lines.filtered(lambda line: line.line_type == 'invoice').mapped('price_subtotal'))
            request.bill_untaxed_amount = sum(
                lines.filtered(lambda line: line.line_type == 'bill').mapped('price_subtotal'))

    @api.depends('stage_id', 'maintenance_product_ids.line_type', 'maintenance_product_ids.invoice_id.state',
                 'maintenance_product_ids.purchase_line_id.order_id.state',
                 'maintenance_product_ids.picking_id.state')
    def _compute_products_locked(self):
        for request in self:
            locked = (request.stage_id.name or '').strip() in PRODUCTS_LOCKED_STAGES
            request.products_locked = request.payment_from_locked = locked
            request.can_create_invoice = not locked and bool(
                request._lines_of_type('invoice')._pending('invoice_id'))
            request.can_create_rfq = request.can_create_bill = not locked and bool(
                request._lines_of_type('bill')._pending_purchase())
            request.can_create_transfer = not locked and bool(
                request._lines_of_type('transfer')._pending_transfer())

    def _lines_of_type(self, line_type):
        return self.maintenance_product_ids.filtered(lambda line: line.line_type == line_type)

    def _check_products_editable(self):
        if self.products_locked:
            raise ValidationError(_("Included products can no longer be processed at this stage."))

    def action_crete_invoice(self):
        """Replaces rental_management's action_crete_invoice body: same
        document, but only for the Invoice tab lines not yet invoiced."""
        self.ensure_one()
        self._check_products_editable()
        lines = self._lines_of_type('invoice')._pending('invoice_id')
        if not lines:
            raise ValidationError(_("Add products on the Invoice tab to create an invoice."))
        partner = self.customer_id
        if not partner:
            raise ValidationError(_("Select the customer to create the invoice."))
        move = self.env['account.move'].sudo().create({
            'move_type': 'out_invoice',
            'partner_id': partner.id,
            'invoice_date': fields.Date.today(),
            'maintenance_request_id': self.id,
            'invoice_line_ids': [(0, 0, {
                'product_id': line.product_id.id,
                'name': line.description,
                'quantity': line.quantity,
                'price_unit': line.price_unit,
                'tax_ids': line.tax_ids.ids,
            }) for line in lines],
        })
        invoice_post_type = self.env['ir.config_parameter'].sudo().get_str(
            'rental_management.invoice_post_type', False)
        if invoice_post_type == 'automatically' and not move._maintenance_delivery_pending():
            move.action_post()
        lines.write({'invoice_id': move.id})
        self.write({'invoice_id': move.id, 'invoice_state': True, 'total': move.amount_total})
        return {
            'type': 'ir.actions.act_window',
            'name': _('Invoice'),
            'res_model': 'account.move',
            'res_id': move.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def action_crete_bill(self):
        """Vendor bills now come out of the purchase flow (RFQ -> PO ->
        Receipt -> Bill) instead of being created directly."""
        return self.action_create_rfq()

    def action_create_rfq(self):
        self.ensure_one()
        self._check_products_editable()
        lines = self._lines_of_type('bill')._pending_purchase()
        if not lines:
            raise ValidationError(_("Add products on the Vendor Bill tab to create an RFQ."))
        if lines.filtered(lambda line: not line.product_id):
            raise ValidationError(_("Every Vendor Bill line needs a product to create an RFQ."))
        if not self.vendor_id:
            raise ValidationError(_("Select the vendor to create the RFQ."))
        order = self.env['purchase.order'].sudo().create({
            'partner_id': self.vendor_id.id,
            'company_id': self.company_id.id or self.env.company.id,
            'origin': self.name,
            'maintenance_request_id': self.id,
        })
        for line in lines:
            line.purchase_line_id = self.env['purchase.order.line'].sudo().create({
                'order_id': order.id,
                'product_id': line.product_id.id,
                'name': line.description or line.product_id.display_name,
                'product_qty': line.quantity,
                'uom_id': line.product_id.uom_id.id,
                'price_unit': line.price_unit,
                'tax_ids': [(6, 0, line.tax_ids.ids)],
            })
        return self._purchase_action(order)

    def action_create_internal_transfer(self):
        self.ensure_one()
        self._check_products_editable()
        lines = self._lines_of_type('transfer')._pending_transfer()
        if not lines:
            raise ValidationError(_("Add products on the Internal Transfer tab to create a transfer."))
        not_goods = lines.filtered(lambda line: line.product_id.type != 'consu' or line.quantity <= 0)
        if not_goods:
            raise ValidationError(_("Only goods products with a positive quantity can be transferred: %s",
                                    ', '.join(line.description or line.product_id.display_name or '?'
                                              for line in not_goods)))
        company = self.company_id or self.env.company
        warehouse = self.env['stock.warehouse'].sudo().search([('company_id', '=', company.id)], limit=1)
        picking_type = warehouse.int_type_id
        if not picking_type:
            raise UserError(_("No warehouse with an Internal Transfer operation type is configured for company %s.",
                              company.name))
        location = self.transfer_location_id or picking_type.default_location_src_id
        location_dest = self.transfer_location_dest_id or picking_type.default_location_dest_id
        if not location or not location_dest:
            raise ValidationError(_("Set the source and destination locations on the Internal Transfer tab."))
        if location == location_dest:
            raise ValidationError(_("Source and destination locations must be different."))
        picking = self.env['stock.picking'].sudo().create({
            'picking_type_id': picking_type.id,
            'location_id': location.id,
            'location_dest_id': location_dest.id,
            'origin': self.name,
            'company_id': company.id,
            'maintenance_request_id': self.id,
            'move_ids': [
                (0, 0, _stock_move_vals(self.env, line.product_id, line.quantity, line.product_id.uom_id,
                                        line.description, location, location_dest, company))
                for line in lines
            ],
        })
        picking.action_confirm()
        picking.action_assign()
        lines.write({'picking_id': picking.id})
        return _picking_action(picking, _('Internal Transfer'))

    picking_ids = fields.One2many('stock.picking', 'maintenance_request_id', string='Transfers')
    delivery_count = fields.Integer(string='Deliveries', compute='_compute_picking_counts')
    receipt_count = fields.Integer(string='Receipts', compute='_compute_picking_counts')
    internal_transfer_count = fields.Integer(string='Internal Transfers', compute='_compute_picking_counts')
    purchase_order_ids = fields.One2many('purchase.order', 'maintenance_request_id', string='RFQs / Purchase Orders')
    purchase_order_count = fields.Integer(string='Purchases', compute='_compute_purchase_order_count')
    invoice_total = fields.Monetary(string='Invoiced', compute='_compute_move_totals')
    bill_total = fields.Monetary(string='Billed', compute='_compute_move_totals')

    @api.depends('picking_ids.picking_type_code')
    def _compute_picking_counts(self):
        for request in self:
            # sudo: maintenance users without Inventory rights still see the counts
            codes = request.sudo().picking_ids.mapped('picking_type_code')
            request.delivery_count = codes.count('outgoing')
            request.receipt_count = codes.count('incoming')
            request.internal_transfer_count = codes.count('internal')

    @api.depends('purchase_order_ids')
    def _compute_purchase_order_count(self):
        for request in self:
            # sudo: maintenance users without Purchase rights still see the count
            request.purchase_order_count = len(request.sudo().purchase_order_ids)

    def _maintenance_moves(self, move_type):
        self.ensure_one()
        return self.env['account.move'].sudo().search([
            ('maintenance_request_id', '=', self.id),
            ('move_type', '=', move_type),
        ])

    def _compute_move_totals(self):
        for request in self:
            if not request.id:
                request.invoice_total = request.bill_total = 0.0
                continue
            request.invoice_total = sum(request._maintenance_moves('out_invoice').mapped('amount_total'))
            request.bill_total = sum(request._maintenance_moves('in_invoice').mapped('amount_total'))

    def _action_view_maintenance_moves(self, move_type, name):
        moves = self._maintenance_moves(move_type)
        action = {
            'name': name,
            'type': 'ir.actions.act_window',
            'res_model': 'account.move',
            'context': {'create': False, 'default_move_type': move_type},
            'target': 'current',
        }
        if len(moves) == 1:
            action.update(view_mode='form', res_id=moves.id)
        else:
            action.update(view_mode='list,form', domain=[('id', 'in', moves.ids)])
        return action

    def action_view_invoice(self):
        """Customer invoices only (core showed invoices and bills together)."""
        return self._action_view_maintenance_moves('out_invoice', _('Invoices'))

    def action_view_bills(self):
        """Vendor bills only (core showed invoices and bills together)."""
        return self._action_view_maintenance_moves('in_invoice', _('Vendor Bills'))

    def action_view_deliveries(self):
        pickings = self.sudo().picking_ids.filtered(lambda p: p.picking_type_code == 'outgoing')
        return _picking_action(pickings, _('Delivery Orders'))

    def action_view_receipts(self):
        pickings = self.sudo().picking_ids.filtered(lambda p: p.picking_type_code == 'incoming')
        return _picking_action(pickings, _('Receipts'))

    def action_view_internal_transfers(self):
        pickings = self.sudo().picking_ids.filtered(lambda p: p.picking_type_code == 'internal')
        return _picking_action(pickings, _('Internal Transfers'))

    def _purchase_action(self, orders):
        action = {
            'name': _('Requests for Quotation'),
            'type': 'ir.actions.act_window',
            'res_model': 'purchase.order',
            'context': {'create': False},
            'target': 'current',
        }
        if len(orders) == 1:
            action.update(view_mode='form', res_id=orders.id)
        else:
            action.update(view_mode='list,form', domain=[('id', 'in', orders.ids)])
        return action

    def action_view_purchase_orders(self):
        self.ensure_one()
        return self._purchase_action(self.sudo().purchase_order_ids)
