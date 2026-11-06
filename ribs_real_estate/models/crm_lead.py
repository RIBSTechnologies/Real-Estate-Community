from odoo import models, fields, api


class CrmLeadInherit(models.Model):
    _inherit = 'crm.lead'

    hot_lead_mail_sent = fields.Boolean(string='Hot Lead Mail Sent', default=False)
    offer_mail_sent = fields.Boolean(string='Offer Mail Sent', default=False)

    def get_lead_url(self):
        base_url = self.env['ir.config_parameter'].sudo().get_str('web.base.url', False)
        return f"{base_url}/web#id={self.id}&model=crm.lead&view_type=form"
    
    def send_hot_lead_email(self):
        template = self.env.ref('ribs_real_estate.email_template_send_hot_leads')

        for record in self:
            emails = record.property_id.maintenance_person_ids.mapped('work_email')
            company_secretary_email = self.env.company.company_secretary.work_email

            email_list = [company_secretary_email] + emails
            email_list = [email for email in email_list if email]
            email_to = ','.join(email_list)

            if template:
                email_values = {
                    'email_from': self.env.company.email,
                    'email_to': email_to,
                }
                template.send_mail(record.id, force_send=True, email_values=email_values)
                record.hot_lead_mail_sent = True


    # @api.model_create_multi
    # def create(self, vals_list):
    #     record = super(CrmLeadInherit, self).create(vals_list)
    #     if not record.hot_lead_mail_sent and record.priority == '3':
    #         record.send_hot_lead_email()
    #     return record
    #
    # def write(self, vals):
    #     result = super(CrmLeadInherit, self).write(vals)
    #     for record in self:
    #         if not record.hot_lead_mail_sent and record.priority == '3':
    #             record.send_hot_lead_email()
    #     return result

    def action_set_won_rainbowman(self):
        res = super(CrmLeadInherit, self).action_set_won_rainbowman()
        template = self.env.ref('ribs_real_estate.email_template_user_acknowledged')

        for record in self:
            if not record.offer_mail_sent:
                email_values = {
                    'email_from': record.env.company.email,
                    'email_to': record.partner_id.email,
                    'recipient_ids': [(5, 0, 0)],
                }
                template.send_mail(record.id, email_values=email_values, force_send=True)
                record.offer_mail_sent = True
        return res

    def create_contract(self):
        return {
            'type': 'ir.actions.act_window',
            'name': 'Create Contract',
            'res_model': 'contract.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                        'default_property_id': self.property_id.id, 
                        'default_installment_item_id': self.env.ref('rental_management.property_product_1', raise_if_not_found=False).id,
                        'default_deposit_item_id': self.env.ref('rental_management.property_product_2',raise_if_not_found=False).id,
                        'default_total_rent_year': self.property_id.price_yearly,
                        'default_is_any_deposit': bool(self.property_id.deposit_amount),
                        'default_deposit_amount': self.property_id.deposit_amount,
                    }        
        }
