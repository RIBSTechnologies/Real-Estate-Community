from odoo import models, fields

class ContractPaymentSummary(models.Model):
    _name = 'contract.payment.summary'
    _description = 'Contract Payment Summary'
    _auto = False  

    contract_id = fields.Many2one(
        'tenancy.details',
        string='Contract',
        readonly=True
    )
    contract_start_date = fields.Date(
        related='contract_id.start_date'
    )
    contract_end_date = fields.Date(
        related='contract_id.end_date'
    )
    tenancy_id = fields.Many2one(
        'res.partner',
        related='contract_id.tenancy_id',
        readonly=True,
        string='Tenant Name'
    )
    phone = fields.Char(
        related='tenancy_id.phone',
        string='Phone',
        readonly=True
    )
    currency_id = fields.Many2one(
        'res.currency',
        readonly=True
    )
    contract_total_value = fields.Monetary(
        string='Contract Value',
        readonly=True
    )
    total_paid = fields.Monetary(
        string='Total Paid',
        readonly=True
    )
    remaining_to_pay = fields.Monetary(
        string='Remaining',
        readonly=True
    )
    payment_month = fields.Date(
    string="Payment Month",
    readonly=True
    )

    payment_day = fields.Date(
        string="Payment Day",
        readonly=True
    )

    contract_responsible = fields.Many2one(
        'res.users',
        string='Responsible',
        readonly=True
    )

    is_mail_sent = fields.Boolean(
    string="Mail Sent",
    readonly=True
    )

    def init(self):
        self.env.cr.execute("""
            DROP VIEW IF EXISTS contract_payment_summary CASCADE;
            CREATE VIEW contract_payment_summary AS (
                SELECT
                    MIN(cp.id) AS id,
                    cp.contract_id,
                    td.responsible_id AS contract_responsible,
                    rc.currency_id AS currency_id,

                    date_trunc('month', cp.create_date)::date AS payment_month,
                    cp.create_date::date AS payment_day,

                    td.total_contract_value AS contract_total_value,
                    COALESCE(SUM(cp.amount), 0) AS total_paid,
                    (td.total_contract_value - COALESCE(SUM(cp.amount), 0)) AS remaining_to_pay, 
                    BOOL_OR(cp.is_mail_sent) AS is_mail_sent

                FROM contract_payments cp
                JOIN tenancy_details td ON td.id = cp.contract_id
                JOIN res_company rc ON rc.id = td.company_id

                GROUP BY
                    cp.contract_id,
                    td.responsible_id,
                    rc.currency_id,
                    td.total_contract_value,
                    payment_month,
                    payment_day
            )
        """)



    def action_open_contract_payments(self):
        self.ensure_one()

        payment = self.env['contract.payments'].search(
            [('contract_id', '=', self.contract_id.id)],
            order='id desc',
            limit=1
        )

        if not payment:
            return {
                'type': 'ir.actions.act_window',
                'name': 'No Payments',
                'res_model': 'contract.payments',
                'view_mode': 'form',
                'target': 'new',
                'context': {'create': False},
                'domain': [('contract_id', '=', self.contract_id.id)]
            }

        return {
            'type': 'ir.actions.act_window',
            'name': 'Contract Payment',
            'res_model': 'contract.payments',
            'view_mode': 'form',
            'res_id': payment.id, 
            'context': {
                'create': False,
                'edit': False,
            },
            'domain': [('contract_id', '=', self.contract_id.id)]
        }

