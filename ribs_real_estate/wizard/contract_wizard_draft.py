# -*- coding: utf-8 -*-
"""Draft persistence layer on top of `contract.wizard`.

Loaded AFTER `contract_wizard.py` in wizard/__init__.py so that the overrides
below sit first in the MRO and can safely call super().
"""

import logging

from odoo import _, api, fields, models

_logger = logging.getLogger(__name__)


class ContractWizardDraft(models.TransientModel):
    _inherit = "contract.wizard"

    ribs_draft_id = fields.Many2one(
        "contract.draft", string="Restored Draft", readonly=True)
    ribs_draft_restored = fields.Boolean(
        string="Draft Restored", readonly=True)

    # ------------------------------------------------------------------
    # Context helpers
    # ------------------------------------------------------------------
    @api.model
    def _ribs_draft_keys(self, context=None):
        """Return (property_id, contract_id) identifying the draft slot."""
        ctx = context if context is not None else self.env.context
        active_model = ctx.get("active_model")
        active_id = ctx.get("active_id")

        property_id = ctx.get("ribs_property_id") or False
        if not property_id and active_model == "property.details":
            property_id = active_id

        contract_id = ctx.get("active_contract_id") or False
        if not contract_id and active_model == "tenancy.details":
            contract_id = active_id

        return property_id or False, contract_id or False

    def _ribs_own_keys(self):
        """Same as above but able to fall back on the values in the record."""
        property_id, contract_id = self._ribs_draft_keys()
        if not property_id and self.property_id:
            property_id = self.property_id.id
        return property_id, contract_id

    # ------------------------------------------------------------------
    # Restore
    # ------------------------------------------------------------------
    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        if self.env.context.get("ribs_skip_draft"):
            return res
        try:
            property_id, contract_id = self._ribs_draft_keys()
            draft = self.env["contract.draft"]._find_draft(
                property_id, contract_id)
            if draft:
                res.update(draft.get_restore_values(fields_list))
                if not fields_list or "ribs_draft_id" in fields_list:
                    res["ribs_draft_id"] = draft.id
                if not fields_list or "ribs_draft_restored" in fields_list:
                    res["ribs_draft_restored"] = True
        except Exception:  # noqa: BLE001 - never block the wizard from opening
            _logger.exception("contract.wizard: draft restore failed")
        return res

    # ------------------------------------------------------------------
    # Clear
    # ------------------------------------------------------------------
    def _ribs_drop_draft(self):
        """Delete the draft tied to this wizard."""
        for wizard in self:
            try:
                draft = wizard.ribs_draft_id
                if not draft:
                    property_id, contract_id = wizard._ribs_own_keys()
                    draft = self.env["contract.draft"]._find_draft(
                        property_id, contract_id)
                if draft:
                    draft.sudo().unlink()
            except Exception:
                pass

    def action_clear_draft(self):
        """Throw the saved draft away and reopen an empty wizard."""
        self.ensure_one()
        property_id, contract_id = self._ribs_own_keys()
        self._ribs_drop_draft()

        context = dict(self.env.context, ribs_skip_draft=True)
        if property_id:
            context.update(active_model="property.details",
                           active_id=property_id,
                           ribs_property_id=property_id)
        if contract_id:
            context.update(active_contract_id=contract_id)
        return {
            "type": "ir.actions.act_window",
            "name": _("Contract"),
            "res_model": "contract.wizard",
            "view_mode": "form",
            "target": "new",
            "context": context,
        }

    # ------------------------------------------------------------------
    # Contract created -> draft is no longer needed
    # ------------------------------------------------------------------
    def contract_action(self):
        result = super().contract_action()
        try:
            self._ribs_drop_draft()
        except Exception:  # noqa: BLE001
            _logger.exception("contract.wizard: could not clear draft")
        return result
