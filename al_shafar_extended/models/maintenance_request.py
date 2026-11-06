# -*- coding: utf-8 -*-

from odoo import Command, _, api, fields, models
from odoo.exceptions import ValidationError

# Button-driven repair workflow (see MaintenanceRequest.action_attend_site and
# friends below). These 9 maintenance.stage records already exist in the
# database (created by hand, like "Handover" before them) - matched by NAME
# here rather than id, since only the original core module's own 4 stages
# (New Request/In Progress/Repaired/Scrap) have a fixed id/xmlid; the 5 added
# on top of those (Site Visit, both Outsource ones, Parts Required, Handover)
# do not.
STAGE_IN_PROGRESS = 'In Progress'
STAGE_SITE_VISIT = 'Site Visit'
STAGE_OUTSOURCE_REQUIRED = 'Outsource Support Required'
STAGE_OUTSOURCE_NOT_REQUIRED = 'Outsource Support Not Required'
STAGE_PARTS_REQUIRED = 'Parts Required'
STAGE_REPAIRED = 'Repaired'
STAGE_HANDOVER = 'Handover'
STAGE_SCRAP = 'Scrap'

OUTSOURCE_STAGES = (STAGE_OUTSOURCE_REQUIRED, STAGE_OUTSOURCE_NOT_REQUIRED)
# Stages from which "Repaired"/"Scrap" are both reachable.
REPAIR_OR_SCRAP_SOURCE_STAGES = OUTSOURCE_STAGES + (STAGE_PARTS_REQUIRED,)


class MaintenanceAssignmentRule(models.Model):
    _name = 'maintenance.assignment.rule'
    _description = 'Maintenance Auto-Assignment Rule'
    _order = 'sequence, id'

    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    building_id = fields.Many2one('property.project', string='Building', required=True)
    maintenance_type_id = fields.Many2one(
        'product.template', string='Service Category',
        domain=[('is_maintenance', '=', True)],
        help="Leave empty to apply this rule to all service categories in the building.")
    technician_id = fields.Many2one('res.users', string='Technician', required=True)


class MaintenanceConditionLine(models.Model):
    _inherit = 'maintenance.condition.line'

    move_in_status = fields.Selection(default='ok')
    # How many of the item the unit has (e.g. 3 doors, 2 wardrobes).
    count = fields.Integer(string='Count', default=1)


class MaintenanceRequest(models.Model):
    _inherit = 'maintenance.request'

    is_new_request_stage = fields.Boolean(compute='_compute_is_new_request_stage')
    is_repaired_stage = fields.Boolean(compute='_compute_is_repaired_stage')

    # Button/section visibility flags for the Site Visit -> Outsource ->
    # Parts Required -> Repaired/Scrap workflow below. is_parts_required_reached
    # (unlike the others, an exact-stage match) stays True from Parts Required
    # onward - Repaired/Handover/Scrap included - so the Included Products
    # page it gates doesn't vanish again once the request moves past it.
    is_in_progress_stage = fields.Boolean(compute='_compute_workflow_stage_flags')
    is_site_visit_stage = fields.Boolean(compute='_compute_workflow_stage_flags')
    is_outsource_decision_stage = fields.Boolean(compute='_compute_workflow_stage_flags')
    is_parts_required_stage = fields.Boolean(compute='_compute_workflow_stage_flags')
    is_parts_required_reached = fields.Boolean(compute='_compute_workflow_stage_flags')

    tenant_resolution_confirmation = fields.Selection([
        ('pending', 'Pending'),
        ('confirmed', 'Resolved'),
        ('rejected', 'Not Resolved'),
    ], string='Tenant Resolution Confirmation', default='pending', copy=False)
    tenant_rating = fields.Selection([
        ('1', '1 - Poor'),
        ('2', '2 - Fair'),
        ('3', '3 - Good'),
        ('4', '4 - Very Good'),
        ('5', '5 - Excellent'),
    ], string='Tenant Rating', copy=False)
    tenant_rating_comment = fields.Text(string='Tenant Feedback', copy=False)
    tenant_rating_value = fields.Integer(
        string='Tenant Rating (Value)', compute='_compute_tenant_rating_value', store=True)
    closed_date = fields.Datetime(string='Closed Date', copy=False)
    reopen_count = fields.Integer(string='Reopen Count', default=0, copy=False)

    ticket_type = fields.Selection([
        ('handover', 'Handover'),
        ('tenant', 'Tenant / Customer Ticket'),
        ('direct', 'Directly Created'),
    ], string='Ticket Type', compute='_compute_ticket_type', store=True, index=True)

    @api.depends('mr_for', 'mr_created_person_id.share')
    def _compute_ticket_type(self):
        """Handover: move-in / move-out requests. Tenant / Customer Ticket:
        raised by the tenant from the Odoo customer portal (created by a
        portal user). Everything else was created directly by staff in the
        backend."""
        for request in self:
            if request.mr_for in ('move_in', 'move_out'):
                request.ticket_type = 'handover'
            elif request.mr_created_person_id.share:
                request.ticket_type = 'tenant'
            else:
                request.ticket_type = 'direct'

    @api.depends('tenant_rating')
    def _compute_tenant_rating_value(self):
        for request in self:
            request.tenant_rating_value = int(request.tenant_rating) if request.tenant_rating else 0

    @api.depends('stage_id')
    def _compute_is_new_request_stage(self):
        first_stage = self.env['maintenance.stage'].search([], order='sequence asc, id asc', limit=1)
        for request in self:
            request.is_new_request_stage = bool(first_stage) and request.stage_id.id == first_stage.id

    @api.depends('stage_id')
    def _compute_is_repaired_stage(self):
        # Stage id 3 ("Repaired") — matches the same hardcoded check ribs_real_estate
        # already uses in its write() override to trigger the completion feedback email.
        for request in self:
            request.is_repaired_stage = request.stage_id.id == 3

    @api.model
    def _get_stage_by_name(self, name):
        return self.env['maintenance.stage'].search([('name', '=', name)], limit=1)

    def _move_to_stage(self, stage_name):
        """Shared body of every action_* transition below: look the target
        stage up by name (never a hardcoded id) and write it. Raises rather
        than silently no-op-ing if that stage record doesn't exist, since a
        wrong/typo'd name here would otherwise fail invisibly."""
        self.ensure_one()
        stage = self._get_stage_by_name(stage_name)
        if not stage:
            raise ValidationError(_(
                "Maintenance stage '%s' was not found. Please create it under "
                "Maintenance > Configuration > Stages.") % stage_name)
        self.stage_id = stage.id

    def _check_stage_is_one_of(self, allowed_names):
        if (self.stage_id.name or '').strip() not in allowed_names:
            raise ValidationError(_("You cannot perform this action from the current stage."))

    @api.depends('stage_id')
    def _compute_workflow_stage_flags(self):
        parts_required_stage = self._get_stage_by_name(STAGE_PARTS_REQUIRED)
        for request in self:
            name = (request.stage_id.name or '').strip()
            request.is_in_progress_stage = name == STAGE_IN_PROGRESS
            request.is_site_visit_stage = name == STAGE_SITE_VISIT
            request.is_outsource_decision_stage = name in OUTSOURCE_STAGES
            request.is_parts_required_stage = name == STAGE_PARTS_REQUIRED
            request.is_parts_required_reached = bool(
                parts_required_stage and request.stage_id
                and request.stage_id.sequence >= parts_required_stage.sequence
            )

    def action_attend_site(self):
        self.ensure_one()
        self._check_stage_is_one_of((STAGE_IN_PROGRESS,))
        self._move_to_stage(STAGE_SITE_VISIT)

    def action_outsource_required(self):
        self.ensure_one()
        self._check_stage_is_one_of((STAGE_SITE_VISIT,))
        self._move_to_stage(STAGE_OUTSOURCE_REQUIRED)

    def action_outsource_not_required(self):
        self.ensure_one()
        self._check_stage_is_one_of((STAGE_SITE_VISIT,))
        self._move_to_stage(STAGE_OUTSOURCE_NOT_REQUIRED)

    def action_parts_required(self):
        self.ensure_one()
        self._check_stage_is_one_of(OUTSOURCE_STAGES)
        self._move_to_stage(STAGE_PARTS_REQUIRED)

    def action_repaired(self):
        self.ensure_one()
        self._check_stage_is_one_of(REPAIR_OR_SCRAP_SOURCE_STAGES)
        self._move_to_stage(STAGE_REPAIRED)

    def action_scrap(self):
        self.ensure_one()
        self._check_stage_is_one_of(REPAIR_OR_SCRAP_SOURCE_STAGES)
        self._move_to_stage(STAGE_SCRAP)

    def action_handover(self):
        """Repaired -> Handover has no dedicated button in the original
        spec, but Handover is (per that same spec) also excluded from the
        statusbar's now-restricted clickable stages - without this, a
        repaired request could never actually reach Handover at all. Kept
        as its own explicit, validated transition for consistency with
        every other stage change here, rather than leaving it as the one
        remaining bare statusbar click-through."""
        self.ensure_one()
        self._check_stage_is_one_of((STAGE_REPAIRED,))
        self._move_to_stage(STAGE_HANDOVER)

    def write(self, vals):
        if vals.get('stage_id') == 3:
            vals = dict(vals, tenant_resolution_confirmation='pending')
        return super().write(vals)

    def action_tenant_feedback(self, resolved, rating=False, comment=False):
        self.ensure_one()
        if not self.is_repaired_stage or self.tenant_resolution_confirmation != 'pending':
            return
        if resolved:
            values = {'tenant_resolution_confirmation': 'confirmed', 'closed_date': fields.Datetime.now()}
            if rating:
                values['tenant_rating'] = rating
            if comment:
                values['tenant_rating_comment'] = comment
            self.write(values)
            self.message_post(body=_("Tenant confirmed the issue is resolved."))
        else:
            # Stage id 2 ("In Progress") — reopen so the technician sees it back in their queue.
            self.write({
                'tenant_resolution_confirmation': 'rejected',
                'reopen_count': self.reopen_count + 1,
                'stage_id': 2,
            })
            if comment:
                self.tenant_rating_comment = comment
            self.message_post(body=_("Tenant reported the issue is NOT resolved — ticket reopened."))

    @api.model
    def _find_assignment_rule(self, building_id, maintenance_type_id):
        if not building_id:
            return self.env['maintenance.assignment.rule']
        domain = [('building_id', '=', building_id)]
        rule = self.env['maintenance.assignment.rule']
        if maintenance_type_id:
            rule = self.env['maintenance.assignment.rule'].search(
                domain + [('maintenance_type_id', '=', maintenance_type_id)], order='sequence', limit=1)
        if not rule:
            rule = self.env['maintenance.assignment.rule'].search(
                domain + [('maintenance_type_id', '=', False)], order='sequence', limit=1)
        return rule

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get('user_ids') and vals.get('building_id_parent'):
                rule = self._find_assignment_rule(vals.get('building_id_parent'), vals.get('maintenance_type_id'))
                if rule:
                    vals['user_ids'] = [Command.link(rule.technician_id.id)]
        return super().create(vals_list)

    @api.onchange('building_id_parent', 'maintenance_type_id')
    def _onchange_auto_assign_technician(self):
        if self.building_id_parent and not self.user_ids:
            rule = self._find_assignment_rule(self.building_id_parent.id, self.maintenance_type_id.id)
            if rule:
                self.user_ids = rule.technician_id

    @api.onchange('mr_for')
    def _onchange_mr_for_default_move_in_items(self):
        if self.mr_for == 'move_in' and not self.move_in_ids:
            items = self.env['maintenance.condition.line.item'].search([('item_for', '=', 'move_in')])
            self.move_in_ids = [
                (0, 0, {'item': item.id, 'move_in_status': 'ok'})
                for item in items
            ]

    def action_refresh_move_in_condition_lines(self):
        for request in self:
            existing_items = request.move_in_ids.item
            items = self.env['maintenance.condition.line.item'].search([('item_for', '=', 'move_in')])
            missing_items = items - existing_items
            if missing_items:
                request.move_in_ids = [
                    (0, 0, {'item': item.id, 'move_in_status': 'ok'})
                    for item in missing_items
                ]


class MaintenanceProductLine(models.Model):
    _inherit = 'maintenance.product.line'

    # rental_management declares this as Integer, which rejects fractional
    # quantities (e.g. 0.25 of a gas cylinder). Same precision as the invoice/
    # bill line it is copied into.
    quantity = fields.Float(string="Quantity", default=1.0, digits='Product Unit')
    # Which Included Products sub-tab the line belongs to (see
    # maintenance_stock.MaintenanceRequestStock): Invoice -> customer invoice,
    # Vendor Bill -> RFQ -> PO -> Receipt -> Bill, Internal Transfer -> stock move.
    line_type = fields.Selection([
        ('invoice', 'Invoice'),
        ('bill', 'Vendor Bill'),
        ('transfer', 'Internal Transfer'),
    ], string='Type', default='invoice', required=True)
    # The invoice / bill this line was put on - Create Invoice / Create Bill
    # only pick up lines that aren't on one yet, so lines added later (until
    # Handover) are billed on their own document without repeating earlier ones.
    invoice_id = fields.Many2one('account.move', string='Invoice', readonly=True, copy=False)
    bill_id = fields.Many2one('account.move', string='Bill', readonly=True, copy=False)
    purchase_line_id = fields.Many2one('purchase.order.line', string='RFQ Line', readonly=True, copy=False)
    purchase_order_id = fields.Many2one(related='purchase_line_id.order_id', string='RFQ / PO')
    purchase_state = fields.Selection(related='purchase_line_id.order_id.state', string='PO Status')
    qty_received = fields.Float(related='purchase_line_id.qty_received', string='Received')
    qty_invoiced = fields.Float(related='purchase_line_id.qty_invoiced', string='Billed')
    picking_id = fields.Many2one('stock.picking', string='Transfer', readonly=True, copy=False)
    picking_state = fields.Selection(related='picking_id.state', string='Transfer Status')
    is_billed = fields.Boolean(compute='_compute_is_billed')

    @api.depends('invoice_id.state', 'bill_id.state', 'purchase_line_id.order_id.state', 'picking_id.state')
    def _compute_is_billed(self):
        for line in self:
            line.is_billed = any(
                move and move.state != 'cancel' for move in (line.invoice_id, line.bill_id)
            ) or not line._pending_purchase() or not line._pending_transfer()

    def _pending(self, link_field):
        """Lines not yet on an invoice ('invoice_id') / bill ('bill_id') -
        a cancelled document frees its lines to be put on a new one."""
        return self.filtered(lambda line: not line[link_field] or line[link_field].state == 'cancel')

    def _pending_purchase(self):
        """Lines not yet on an RFQ - a cancelled RFQ/PO frees them again."""
        return self.filtered(lambda line: not line.purchase_line_id
                             or line.purchase_line_id.order_id.state == 'cancel')

    def _pending_transfer(self):
        """Lines not yet on an internal transfer - a cancelled one frees them again."""
        return self.filtered(lambda line: not line.picking_id or line.picking_id.state == 'cancel')

    @api.onchange('product_id')
    def _onchange_product_get_details(self):
        # Vendor Bill lines are purchased: cost price and purchase taxes, not
        # the sales price/taxes core fills in.
        super()._onchange_product_get_details()
        for line in self.filtered(lambda line: line.line_type == 'bill'):
            line.price_unit = line.product_id.standard_price
            line.tax_ids = line.product_id.supplier_taxes_id

    @api.ondelete(at_uninstall=False)
    def _unlink_except_billed(self):
        if any(line.is_billed for line in self):
            raise ValidationError(_(
                "You cannot delete a product line that is already on an invoice, bill, RFQ or transfer. "
                "Cancel that document first."))
