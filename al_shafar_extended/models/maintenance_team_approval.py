# -*- coding: utf-8 -*-

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

from .maintenance_request import STAGE_HANDOVER, STAGE_SCRAP

APPROVAL_LOCKED_STAGES = (STAGE_HANDOVER, STAGE_SCRAP)


class MaintenanceTeamApproval(models.Model):
    """One maintenance team's go / no-go on a move-in handover (Pre-Handover
    Inspection Form -> Team Approval). A team is cleared when it chose
    Proceed, or Don't Proceed with remarks explaining why."""
    _name = 'maintenance.team.approval'
    _description = 'Maintenance Handover Team Approval'
    _order = 'id'

    request_id = fields.Many2one('maintenance.request', string='Maintenance Request',
                                 required=True, ondelete='cascade', index=True)
    team_id = fields.Many2one('maintenance.team', string='Team', required=True)
    decision = fields.Selection([
        ('pending', 'Pending'),
        ('proceed', 'Proceed'),
        ('not_proceed', "Don't Proceed"),
    ], string='Decision', default='pending', required=True, readonly=True)
    remarks = fields.Text(string='Remarks')
    decided_by = fields.Many2one('res.users', string='Decided By', readonly=True)
    decided_on = fields.Datetime(string='Decided On', readonly=True)
    is_cleared = fields.Boolean(string='Cleared', compute='_compute_is_cleared')

    _request_team_unique = models.Constraint(
        'unique(request_id, team_id)',
        'Each team can only approve a request once.',
    )

    @api.depends('decision', 'remarks')
    def _compute_is_cleared(self):
        for line in self:
            line.is_cleared = line.decision == 'proceed' or (
                line.decision == 'not_proceed' and bool((line.remarks or '').strip()))

    def _set_decision(self, decision):
        for line in self:
            line.request_id._check_team_approval_editable()
            line.write({'decision': decision, 'decided_by': self.env.uid, 'decided_on': fields.Datetime.now()})
            line.request_id.message_post(body=_(
                "%(team)s: %(decision)s", team=line.team_id.display_name,
                decision=dict(line._fields['decision']._description_selection(self.env))[decision]))

    def action_proceed(self):
        self._set_decision('proceed')

    def action_not_proceed(self):
        self._set_decision('not_proceed')


class MaintenanceRequestTeamApproval(models.Model):
    """Move-in requests list every maintenance team for approval; Handover
    is only reachable once each team is cleared (see write)."""
    _inherit = 'maintenance.request'

    team_approval_ids = fields.One2many('maintenance.team.approval', 'request_id', string='Team Approval')
    team_approval_locked = fields.Boolean(compute='_compute_team_approval_locked')

    @api.depends('stage_id')
    def _compute_team_approval_locked(self):
        for request in self:
            request.team_approval_locked = (request.stage_id.name or '').strip() in APPROVAL_LOCKED_STAGES

    def _check_team_approval_editable(self):
        if self.team_approval_locked:
            raise ValidationError(_("Team approval can no longer be changed at this stage."))

    def _approval_teams(self):
        self.ensure_one()
        company = self.company_id or self.env.company
        return self.env['maintenance.team'].search(
            ['|', ('company_id', '=', False), ('company_id', '=', company.id)])

    def _missing_team_approval_commands(self):
        missing = self._approval_teams() - self.team_approval_ids.team_id
        return [(0, 0, {'team_id': team.id}) for team in missing]

    def action_load_team_approvals(self):
        """Add any maintenance team not on the list yet (e.g. created later)."""
        for request in self:
            request._check_team_approval_editable()
            commands = request._missing_team_approval_commands()
            if commands:
                request.team_approval_ids = commands

    @api.model_create_multi
    def create(self, vals_list):
        requests = super().create(vals_list)
        for request in requests.filtered(lambda r: r.mr_for == 'move_in' and not r.team_approval_ids):
            request.team_approval_ids = request._missing_team_approval_commands()
        return requests

    @api.onchange('mr_for')
    def _onchange_mr_for_team_approvals(self):
        if self.mr_for == 'move_in' and not self.team_approval_ids:
            self.team_approval_ids = self._missing_team_approval_commands()

    def _team_approval_blockers(self):
        """Teams holding up the handover: undecided (or not listed at all), or
        Don't Proceed without remarks."""
        self.ensure_one()
        lines = self.team_approval_ids
        blockers = [_("%s: no decision yet", team.display_name)
                    for team in self._approval_teams() - lines.team_id]
        for line in lines.filtered(lambda l: not l.is_cleared):
            if line.decision == 'pending':
                blockers.append(_("%s: no decision yet", line.team_id.display_name))
            else:
                blockers.append(_("%s: Don't Proceed without remarks", line.team_id.display_name))
        return blockers

    def write(self, vals):
        if vals.get('stage_id'):
            stage = self.env['maintenance.stage'].browse(vals['stage_id'])
            if (stage.name or '').strip() == STAGE_HANDOVER:
                for request in self.filtered(lambda r: r.mr_for == 'move_in' and r.stage_id != stage):
                    blockers = request._team_approval_blockers()
                    if blockers:
                        raise ValidationError(_(
                            "%(request)s cannot move to Handover until every team approves "
                            "(Proceed, or Don't Proceed with remarks):\n%(blockers)s",
                            request=request.display_name, blockers='\n'.join('- ' + b for b in blockers)))
        return super().write(vals)
