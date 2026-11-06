# -*- coding: utf-8 -*-
"""Make `contract_wiz_action` pass an explicit, deterministic context so the
draft lookup always finds the right slot (and so `default_get` of the wizard
receives active_model / active_id even if the web client does not inject them).

Loaded AFTER property_details.py in models/__init__.py.
"""

from odoo import models


class PropertyDetailsDraft(models.Model):
    _inherit = "property.details"

    def contract_wiz_action(self):
        action = super().contract_wiz_action()
        if isinstance(action, dict) and action.get("res_model") == "contract.wizard":
            context = dict(action.get("context") or self.env.context)
            context.update({
                "active_model": "property.details",
                "active_id": self.id,
                "active_ids": self.ids,
                "ribs_property_id": self.id,
            })
            action["context"] = context

            try:
                draft = self.env["contract.draft"]._find_draft(self.id, False)
                if draft and not context.get("ribs_skip_draft"):
                    action["name"] = "Contract (Draft Restored)"
            except Exception:
                pass
        return action

    def action_open_contract_drafts(self):
        """Smart-button helper: list the drafts saved on this property."""
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": "Saved Contract Drafts",
            "res_model": "contract.draft",
            "view_mode": "list,form",
            "domain": [("property_id", "=", self.id), ("state", "=", "draft")],
            "context": {"create": False},
        }
