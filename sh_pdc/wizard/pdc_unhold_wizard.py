from odoo import fields, models, _
from odoo.exceptions import ValidationError



class PDCUnholdWizard(models.TransientModel):
    _name = "pdc.unhold.wizard"
    _description = "PDC Unhold Wizard"

    pdc_id = fields.Many2one("pdc.wizard", required=True)
    payment_date = fields.Date(required=True)
    due_date = fields.Date(required=True)

    def action_confirm(self):
        self.ensure_one()

        today = fields.Date.context_today(self)

        if self.payment_date < today:
            raise ValidationError(
                _("Payment Date cannot be earlier than today.")
            )

        if self.due_date < self.payment_date:
            raise ValidationError(
                _("Due Date cannot be earlier than the Payment Date.")
            )

        self.pdc_id.write({
            "payment_date": self.payment_date,
            "due_date": self.due_date,
            "state": "registered", 
        })

        return {"type": "ir.actions.act_window_close"}