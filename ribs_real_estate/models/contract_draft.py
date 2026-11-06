# -*- coding: utf-8 -*-
"""Persistent auto-saved draft for the Contract Wizard.

`contract.wizard` is a TransientModel opened in a dialog, so anything typed in
it lives only in the browser until a button is pressed.  If the user closes the
dialog (or navigates away) everything is lost.

This model keeps a JSON snapshot of the wizard form for each
(user, property, contract) combination.  A small JS patch pushes the snapshot
every few seconds while the dialog is open, and `contract.wizard.default_get`
restores it the next time the same wizard is opened.
"""

import json
import logging

from odoo import Command, _, api, fields, models

_logger = logging.getLogger(__name__)

# Never store / never restore these
SKIP_FIELDS = {
    "id",
    "display_name",
    "create_uid",
    "create_date",
    "write_uid",
    "write_date",
    "__last_update",
    "company_id",
    "currency_id",
    "ribs_draft_id",
    "ribs_draft_restored",
}

# If none of these carry a value we consider the wizard "untouched" and do not
# create a draft (avoids junk rows when a user just opens and closes the popup).
MEANINGFUL_FIELDS = (
    "customer_id",
    "start_date",
    "end_date",
    "duration_id",
    "payment_term",
    "deposit_amount",
    "note",
    "lead_id",
    "broker_id",
    "added_service_ids",
    "agreement_template_id",
    "is_by_date",
    "discount_value",
    "unit_ids",
)


class ContractDraft(models.Model):
    _name = "contract.draft"
    _description = "Contract Wizard Auto-saved Draft"
    _order = "write_date desc"

    property_id = fields.Many2one(
        "property.details", string="Property", ondelete="cascade", index=True)
    contract_id = fields.Many2one(
        "tenancy.details", string="Contract", ondelete="cascade", index=True)
    user_id = fields.Many2one(
        "res.users", string="User", required=True, index=True,
        default=lambda self: self.env.user, ondelete="cascade")
    payload = fields.Text(string="Saved Data", default="{}")
    state = fields.Selection(
        [("draft", "Draft"), ("done", "Used")], default="draft", index=True)

    # ------------------------------------------------------------------
    # Lookup helpers
    # ------------------------------------------------------------------
    @api.model
    def _draft_domain(self, property_id=False, contract_id=False):
        return [
            ("user_id", "=", self.env.uid),
            ("state", "=", "draft"),
            ("property_id", "=", int(property_id) if property_id else False),
            ("contract_id", "=", int(contract_id) if contract_id else False),
        ]

    @api.model
    def _find_draft(self, property_id=False, contract_id=False):
        """Return the current user's open draft (empty recordset if none)."""
        return self.sudo().search(
            self._draft_domain(property_id, contract_id), limit=1)

    # ------------------------------------------------------------------
    # Called from JS (contract_wizard_autosave.js)
    # ------------------------------------------------------------------
    @api.model
    def store_draft(self, payload, property_id=False, contract_id=False):
        """Create / update the draft snapshot.  Never raises: an autosave
        failure must never break the user's screen."""
        try:
            payload = payload or {}
            if not isinstance(payload, dict) or not self._is_meaningful(payload):
                return False
            property_id = int(property_id) if property_id else False
            contract_id = int(contract_id) if contract_id else False
            body = json.dumps(payload, default=str)
            draft = self._find_draft(property_id, contract_id)
            if draft:
                draft.sudo().write({"payload": body})
            else:
                draft = self.sudo().create({
                    "payload": body,
                    "property_id": property_id,
                    "contract_id": contract_id,
                    "user_id": self.env.uid,
                })
            return draft.id
        except Exception:  # noqa: BLE001 - autosave must stay silent
            _logger.exception("contract.draft: autosave failed")
            return False

    @api.model
    def _is_meaningful(self, payload):
        for name in MEANINGFUL_FIELDS:
            value = payload.get(name)
            if isinstance(value, (list, tuple)):
                if value:
                    return True
            elif value:
                return True
        return False

    @api.model
    def drop_draft(self, property_id=False, contract_id=False):
        draft = self._find_draft(property_id, contract_id)
        if draft:
            draft.sudo().unlink()
            return True
        return False

    # ------------------------------------------------------------------
    # Restore
    # ------------------------------------------------------------------
    def _is_restorable(self, field):
        if not field or field.name in SKIP_FIELDS:
            return False
        if not field.store:
            return False
        if field.related:
            return False
        if field.compute and not field.inverse:
            return False
        if field.type in ("binary", "reference"):
            return False
        return True

    def _clean_m2o(self, field, value):
        if not isinstance(value, int) or not value:
            return False
        record = self.env[field.comodel_name].sudo().browse(value).exists()
        return record.id if record else False

    def _clean_ids(self, field, value):
        ids = [i for i in (value or []) if isinstance(i, int)]
        if not ids:
            return []
        return self.env[field.comodel_name].sudo().browse(ids).exists().ids

    def _clean_line(self, comodel, inverse_name, line):
        vals = {}
        if not isinstance(line, dict):
            return vals
        for key, value in line.items():
            if key == inverse_name or key in SKIP_FIELDS:
                continue
            sub = comodel._fields.get(key)
            if not self._is_restorable(sub) or sub.type in ("one2many", "binary"):
                continue
            if sub.type == "many2one":
                vals[key] = self._clean_m2o(sub, value)
            elif sub.type == "many2many":
                vals[key] = [Command.set(self._clean_ids(sub, value))]
            else:
                vals[key] = value if value is not None else False
        return vals

    def get_restore_values(self, fields_list=None):
        """Return a dict usable inside `default_get` of contract.wizard."""
        self.ensure_one()
        wizard = self.env["contract.wizard"]
        try:
            payload = json.loads(self.payload or "{}")
        except (ValueError, TypeError):
            _logger.warning("contract.draft %s: unreadable payload", self.id)
            return {}

        values = {}
        for name, value in payload.items():
            field = wizard._fields.get(name)
            if not self._is_restorable(field):
                continue
            if fields_list and name not in fields_list:
                continue
            if field.type in ("monetary", "float", "integer") and not value:
                # A falsy amount in an autosaved snapshot almost always means
                # the wizard hadn't finished loading its real default yet
                # when this was captured (e.g. rent still 0 before the
                # contract's own rent was computed) - never let a stale 0
                # clobber a fresh, correct default (contract_wizard.py's
                # default_get / the base rental_management one) with a blank
                # Rent/Contract Value on a random subset of contracts.
                continue
            try:
                if field.type == "many2one":
                    values[name] = self._clean_m2o(field, value)
                elif field.type == "many2many":
                    values[name] = [Command.set(self._clean_ids(field, value))]
                elif field.type == "one2many":
                    comodel = self.env[field.comodel_name]
                    lines = []
                    for line in (value or []):
                        line_vals = self._clean_line(
                            comodel, field.inverse_name, line)
                        if line_vals:
                            lines.append(Command.create(line_vals))
                    values[name] = lines
                else:
                    values[name] = value if value is not None else False
            except Exception:  # noqa: BLE001 - one bad field must not kill the restore
                _logger.exception(
                    "contract.draft %s: could not restore field %s", self.id, name)
        return values

    # ------------------------------------------------------------------
    # Housekeeping
    # ------------------------------------------------------------------
    @api.autovacuum
    def _gc_contract_drafts(self):
        """Remove used drafts and anything abandoned for more than 30 days."""
        limit_date = fields.Datetime.subtract(fields.Datetime.now(), days=30)
        stale = self.sudo().search([
            "|", ("state", "=", "done"), ("write_date", "<", limit_date),
        ])
        if stale:
            stale.unlink()

    def action_open_wizard(self):
        """Open the wizard back on the saved draft (used from the list view)."""
        self.ensure_one()
        if self.property_id:
            return self.property_id.contract_wiz_action()
        return {
            "type": "ir.actions.act_window",
            "name": _("Contract"),
            "res_model": "contract.wizard",
            "view_mode": "form",
            "target": "new",
            "context": dict(self.env.context,
                            active_contract_id=self.contract_id.id),
        }
