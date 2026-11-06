from odoo import models, fields, api, _
from odoo.exceptions import ValidationError
from datetime import date
import base64
from odoo.tools import html_escape



class ContractClosingWizard(models.TransientModel):
    _name = 'contract.closing.wizard'
    _description = 'Wizard to Close Contract'

    has_major_issue = fields.Boolean('Has Major Issue', default=False)
    contract_id = fields.Many2one('tenancy.details', string="Contract", required=True)
    get_first_approval_from = fields.Many2many(
        'res.users',
        'contract_closing_first_approval_rel',  
        'wizard_id',                            
        'user_id',                              
        string="Get First Level Approval From",
        required=True)

    get_first_approval_from_ids = fields.Many2many(
        'res.users',
        'contract_closing_first_approval_rel1',  
        'wizard_id',                            
        'user_id',                              
        string="Get First Level Approval From", compute="_compute_get_first_approval_from_ids")

    get_final_approval_from = fields.Many2many(
        'res.users',
        'contract_closing_final_approval_rel',  
        'wizard_id',
        'user_id',
        string="Get Final Approval From", required=True, readonly=True, store=True
    )

    closing_reason = fields.Text(string="Closing Reason", required=True)
    closing_date = fields.Date(string="Closing Date", required=True)
    if_penalty = fields.Boolean(string='''Do you want to add a penalty for this action? This will generate a new invoice under the contract ''', default=False, required=True)
    penalty_amount = fields.Float(string="Penalty Amount", default=0.0, required=True)
    termination_type = fields.Selection([
        ('normal', 'Release Contract'),
        ('early', 'Termination'),
    ], string="Termination Type", default='normal', required=True)

    @api.onchange('closing_date')
    def onchange_closing_date(self):
        if not self.closing_date:
            return
        contract_id = self.env['tenancy.details'].browse(self.env.context.get('default_contract_id'))
        # Closing on or after the contract's end date is fine (e.g. releasing
        # it a bit late) — only closing before it even started is invalid.
        # Closing *before* the end date is allowed too, but only as a
        # Termination (early exit), not a normal Release — see
        # ContractClosingWizardExtended._check_closure_requires_contract_end.
        if self.closing_date < contract_id.start_date:
            self.closing_date = False
            return {
                'warning': {
                    'title': 'Invalid Closing Date',
                    'message': 'Closing date cannot be before the contract start date.',
                }
            }

    @api.depends('has_major_issue')
    def _compute_get_first_approval_from_ids(self):
        User = self.env['res.users']

        for rec in self:
            rec.get_first_approval_from_ids = None
            domain = [
                ('all_group_ids', 'in', [
                    rec.env.ref('base.group_erp_manager').id,
                    rec.env.ref('base.group_system').id,
                    rec.env.ref('ribs_real_estate.property_rental_accountant').id,
                ])
            ]

            if rec.get_final_approval_from:
                domain.append(('id', 'not in', rec.get_final_approval_from.ids))
            rec.get_first_approval_from_ids = User.search(domain)
   
    def action_close_contract(self):
        self.ensure_one()

        contract_id = self.env['tenancy.details'].browse(self.env.context.get('default_contract_id'))
        if not contract_id:
            raise ValidationError(_("No contract found to close."))

        invoice = False
        attachment_penalty = False
        all_attachments = []
        description = f"Contract Closing Charges for {contract_id.tenancy_seq}"
        currency_symbol = contract_id.currency_id.symbol or ""


        if self.if_penalty:
            product = self.env['product.product'].search([('name', '=', 'Contract Closing Charges')], limit=1)
            if not product:
                product = self.env['product.product'].create({'name': 'Contract Closing Charges'})

            invoice_line_vals = [(0, 0, {
                'product_id': product.id,
                'quantity': 1,
                'name': description,
                'price_unit': self.penalty_amount,
            })]

            invoice = self.env['account.move'].sudo().create({
                'partner_id': contract_id.tenancy_id.id,
                'move_type': 'out_invoice',
                'invoice_date': date.today(),
                'invoice_line_ids': invoice_line_vals,
                'tenancy_id': contract_id.id,
            })
            invoice.action_post()

            rent_invoice = self.env['rent.invoice'].create({
                'tenancy_id': contract_id.id,
                'customer_id': contract_id.tenancy_id.id,
                'type': 'penalty',
                'rent_invoice_id': invoice.id,
                'description': description,
                'amount': self.penalty_amount,
                'invoice_date': date.today(),
            })

            contract_id.write({
                'rent_invoice_ids': [(4, rent_invoice.id)],
            })

            pdf_content, _ = self.env['ir.actions.report']._render_qweb_pdf(
                'account.account_invoices', [invoice.id]
            )
            pdf_raw = pdf_content

            attachment_penalty = self.env['ir.attachment'].create({
                'name': f"{invoice.name or 'Invoice'}.pdf",
                'type': 'binary',
                'raw': pdf_raw,
                'res_model': 'tenancy.details',
                'res_id': contract_id.id,
                'mimetype': 'application/pdf',
            })

            all_attachments.append(attachment_penalty.id)

        if self.termination_type == 'early':
            contract_state = 'pre_terminated'
        else:
            contract_state = 'terminated'
        contract_id.write({
            'contract_type': contract_state,
            'close_contract_state': True,
            'terminate_date': self.closing_date,
        })
        contract_id.property_id.write({
            'stage': 'available',
        })

        template = self.env.ref('ribs_real_estate.contract_closing_notification_template').sudo()

        ctx = {
            'default_model': self._name,
            'default_email_from': self.env.company.email,
            'default_partner_ids': [contract_id.tenancy_id.id],
            'default_res_ids': [contract_id.id],
            'default_use_template': True,
            'default_template_id': template.id,
            'default_attachment_ids': all_attachments,

            'invoice_name': invoice.name if invoice else "No Invoice",
            'invoice_amount': self.penalty_amount if self.if_penalty else f"0 {currency_symbol}",
            'description': description,
            'has_penalty': self.if_penalty,  
        }

        return {
            'type': 'ir.actions.act_window',
            'res_model': 'mail.compose.message',
            'view_mode': 'form',
            'target': 'new',
            'context': ctx,
        }

    def close_contract_approval(self):
        if self.has_major_issue:
            users = self.env['res.users'].search([
                ('all_group_ids', 'in', [
                    self.env.ref('base.group_erp_manager').id,
                    self.env.ref('base.group_system').id,
                ])
            ])
        if self.if_penalty and self.penalty_amount < 1:
            raise ValidationError('Please enter valid penalty amount')
        contract = self.env['tenancy.details'].browse(self.env.context.get('default_contract_id'))
        if not contract:
            raise ValidationError(_("No contract found to close."))
        else:
            vals = ({
                'termination_requested_person': self.env.user.id,
                'closing_reason': self.closing_reason,
                'closing_date': self.closing_date,
                'termination_type': self.termination_type,
                # 'first_level_approval_requested_to': [(6, 0, self.get_first_approval_from.ids)],
                'if_penalty': self.if_penalty,
                'penalty_amount': self.penalty_amount,
            })
            if self.has_major_issue:
                vals.update({
                    'first_level_approval_requested_to': [(6, 0, self.get_first_approval_from.ids)],
                    'final_level_approval_requested_to': [(6, 0, users.ids)],
                    'contract_type': 'closure_pending_approval',
                })
                template_xmlid = 'ribs_real_estate.mail_template_contract_closure_first_approval_'
                recipients = self.get_first_approval_from
            else:
                vals.update({
                    'contract_type': 'closure_final_approval',
                    'final_level_approval_requested_to': [(6, 0, self.get_first_approval_from.ids)],
                })
                template_xmlid = 'ribs_real_estate.mail_template_contract_closure_final_approval_'
                recipients = self.get_first_approval_from

            contract.write(vals)

            base_url = self.env['ir.config_parameter'].sudo().get_str('web.base.url', False)
            record_url = (
                f"{base_url}/web#id={contract.id}"
                f"&model=tenancy.details"
                f"&view_type=form"
            )

            template = self.env.ref(template_xmlid, raise_if_not_found=False)
            if template:
                partners = recipients.mapped('partner_id')
                partners_without_email = partners.filtered(lambda p: not p.email)

                if partners_without_email:
                    raise ValidationError(
                        "The following approvers do not have an email configured:\n%s"
                        % ', '.join(partners_without_email.mapped('name'))
                    )

                emails = ','.join(partners.mapped('email'))

                template.with_context(request_url=record_url).send_mail(
                    contract.id,
                    force_send=True,
                    email_values={
                        'email_from': self.env.company.email,
                        'email_to': emails,
                    }
                )
            return {'type': 'ir.actions.act_window_close'}

    @api.onchange('has_major_issue')
    def onchange_has_major_issue(self):
        if self.has_major_issue:
            users = self.env['res.users'].search([
                ('all_group_ids', 'in', [
                    self.env.ref('base.group_erp_manager').id,
                    self.env.ref('base.group_system').id,
                ])
            ])
            self.get_final_approval_from = [(6, 0, users.ids)]
        else:
            self.get_final_approval_from = None

