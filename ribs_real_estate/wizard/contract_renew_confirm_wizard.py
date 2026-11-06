from odoo import api, fields, models, _


class ContractRenewConfirmWizard(models.TransientModel):
    _name = 'contract.renew.confirm.wizard'
    _description = 'Contract Renewal Confirmation'

    contract_id = fields.Many2one(
        'tenancy.details',
        string='Contract',
        required=True,
        readonly=True,
    )

    message = fields.Html(
        string='Message',
        readonly=True,
        default=lambda self: _(
            """
            <p>
                <strong>Outstanding Payments Detected</strong>
            </p>
            <p>
                This contract has unpaid invoices associated with it.
                It is recommended to settle all outstanding dues before renewing the contract.
            </p>
            <p>
                <strong>Do you want to proceed with the contract renewal anyway?</strong>
            </p>
            """
        ),
    )

    def action_confirm(self):
        self.ensure_one()
        print(self.contract_id,'contraacc')

        return self.contract_id.renew_contract_confirm()

    def action_cancel(self):
        return {'type': 'ir.actions.act_window_close'}