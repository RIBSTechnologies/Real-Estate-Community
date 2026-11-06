from odoo import models, fields, api
from odoo.exceptions import ValidationError
from datetime import date

class ContractClosureApprovalWizard(models.TransientModel):
    _name = 'contract.closure.approval.wizard'
    _description = "Contract Closure Approval"

    contract_id = fields.Many2one(
        'tenancy.details',
        string="Contract",
        required=True,
        readonly=True
    )

    approval_comment = fields.Text(
        string="Approval Comment",
        required=True
    )
    termination_requested_person = fields.Many2one("res.users", string="Requested Person")
    closing_reason = fields.Text(string="Closing Reason")
    closing_date = fields.Date(string="Closing Date")
    termination_type = fields.Selection([
        ('normal', 'Release Contract'),
        ('early', 'Termination'),
    ], string="Termination Type")
    first_level_approval_requested_to = fields.Many2many(
        'res.users',
        'tenancy_first_level_approval_closure_rel',   
        'tenancy_id',
        'user_id',
        string="First Level Approval Requested To"
    )
    final_level_approval_requested_to = fields.Many2many(
        'res.users',
        'tenancy_final_level_approval_closure_rel',   
        'tenancy_id',
        'user_id',
        string="Final Level Approval Requested To"
    )
    if_penalty = fields.Boolean(string="Penalty Applied")
    penalty_amount = fields.Float(string="Penalty Amount")

    @api.onchange('termination_type')
    def onchange_termination_type(self):
        print('calling')
        if self.termination_type == 'normal':
            self.closing_date = self.contract_id.duration_end_date if self.contract_id.duration_end_date else self.contract_id.end_date

    def action_first_level_approve(self):
        self.ensure_one()

        self.contract_id.write({
            'first_level_approval_comment': self.approval_comment,
            'first_level_approved_by': self.env.user.id,
            'first_level_approved_date': date.today(),
            'contract_type': 'closure_final_approval',
        })

        # self.contract_id.message_post(
        #     body="""
        #         <p><b>First Level Closure Approved</b></p>
        #         <p><b>Approved By:</b> %s</p>
        #         <p><b>Comment:</b><br/>%s</p>
        #     """ % (self.env.user.name, self.approval_comment),
        #     message_type='comment',
        #     subtype_xmlid='mail.mt_comment',
        # )
        base_url = self.env['ir.config_parameter'].sudo().get_str('web.base.url', False)
        request_url = (
            f"{base_url}/web#"
            f"id={self.contract_id.id}"
            f"&model=tenancy.details"
            f"&view_type=form"
        )
        template = self.env.ref(
            'ribs_real_estate.mail_template_contract_closure_final_approval_',
            raise_if_not_found=False
        )
        if template:
            partners = self.final_level_approval_requested_to.mapped('partner_id')
            partners_without_email = partners.filtered(lambda p: not p.email)

            if partners_without_email:
                raise ValidationError(
                    "The following approvers do not have an email configured:\n%s"
                    % ', '.join(partners_without_email.mapped('name'))
                )
            emails = ','.join(partners.mapped('email'))

            template.with_context(request_url=request_url).send_mail(self.contract_id.id, force_send=True, 
            email_values={
                'email_from':self.env.company.email,
                'email_to': emails,
            })

        return {'type': 'ir.actions.act_window_close'}

