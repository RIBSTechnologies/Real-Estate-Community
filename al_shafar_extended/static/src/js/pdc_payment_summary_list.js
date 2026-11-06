/** @odoo-module **/

import { listView } from "@web/views/list/list_view";
import { NotificationPlugin } from "@web/core/notifications/notification_plugin";
import { ListRenderer } from "@web/views/list/list_renderer";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { Component, proxy, usePlugin, useProps, xml } from "@odoo/owl";

// ── PdcPaymentSummaryPanel (inline inside table row) ───────────────────────
export class PdcPaymentSummaryPanel extends Component {

    props = useProps();
    setup() {
        this.orm = useService("orm");
        this.notification = usePlugin(NotificationPlugin);
        this.busy = proxy({ id: null });
    }

    async onReturn(pdcId, ev) {
        ev.stopPropagation();
        this.busy.id = pdcId;
        try {
            await this.orm.call("pdc.wizard", "action_returned", [[pdcId]]);
            this.notification.add("PDC cheque marked as returned.", { type: "success" });
            await this.props.onReload();
        } catch (e) { this.notification.add(e.data?.message || "Failed to return this PDC cheque.", { type: "danger" }); }
        finally { this.busy.id = null; }
    }

    static template = xml`
<div class="pdcps-panel">
    <div class="pdcps-panel-header">
        <span class="pdcps-panel-title">
            <i class="fa fa-money me-2"/>PDC Cheque Payments
            <span t-if="this.props.contractName" class="pdcps-contract-name ms-2">— <t t-out="this.props.contractName"/></span>
        </span>
        <div class="d-flex align-items-center gap-2">
            <span t-if="!this.props.loading" class="pdcps-panel-count"><t t-out="this.props.cheques.length"/> records</span>
            <button class="btn btn-sm btn-close pdcps-close-btn" t-on-click="() => this.props.onClose()"/>
        </div>
    </div>
    <div t-if="this.props.loading" class="pdcps-loading-wrap"><i class="fa fa-spinner fa-spin me-2"/>Loading…</div>
    <div t-else="" class="pdcps-table-wrap">
        <table class="pdcps-table">
            <thead><tr>
                <th>#</th><th>Beneficiary Bank</th><th>Partner</th><th>Amount</th>
                <th>Cheque No.</th><th>Payment Date</th><th>Due Date</th>
                <th>Remitter Bank</th><th>Reference</th><th>Actions</th><th>Status</th>
            </tr></thead>
            <tbody>
                <t t-foreach="this.props.cheques" t-as="pdc" t-key="pdc.id">
                    <tr t-att-class="pdc.state==='returned'?'pdcps-row-returned':pdc.state==='registered'?'pdcps-row-registered':''">
                        <td class="pdcps-td-seq"><t t-out="pdc_index+1"/></td>
                        <td><t t-out="pdc.journal_id and pdc.journal_id[1] or '—'"/></td>
                        <td><t t-out="pdc.partner_id and pdc.partner_id[1] or '—'"/></td>
                        <td class="pdcps-td-amount"><t t-out="this.props.formatAmount(pdc.payment_amount)"/> <span class="pdcps-currency"><t t-out="pdc.currency_id and pdc.currency_id[1] or ''"/></span></td>
                        <td><t t-out="pdc.cheque_number or '—'"/></td>
                        <td><t t-out="this.props.formatDate(pdc.payment_date)"/></td>
                        <td><t t-out="this.props.formatDate(pdc.due_date)"/></td>
                        <td><t t-out="pdc.remitter_bank or '—'"/></td>
                        <td><t t-out="pdc.reference or '—'"/></td>
                        <td class="text-center pdcps-action-cell">
                            <t t-if="pdc.state === 'registered'">
                                <i t-if="this.busy.id === pdc.id" class="fa fa-spinner fa-spin text-muted"/>
                                <button t-else="" class="btn btn-sm pdcps-btn-return" title="Return this PDC cheque" t-on-click="(ev) => this.onReturn(pdc.id, ev)"><i class="fa fa-undo me-1"/>Return</button>
                            </t>
                            <t t-elif="pdc.state === 'returned'"><i class="fa fa-check-circle text-success" title="Returned"/></t>
                            <t t-else="">—</t>
                        </td>
                        <td><span t-att-class="this.props.stateBadgeClass(pdc.state)" t-out="this.props.stateLabel(pdc.state)"/></td>
                    </tr>
                </t>
            </tbody>
            <tfoot>
                <tr class="pdcps-total-row">
                    <td colspan="3" class="text-end fw-semibold">Total</td>
                    <td class="pdcps-td-amount fw-bold"><t t-out="this.props.formatAmount(this.props.cheques.reduce((s,p)=>s+(p.payment_amount||0),0))"/></td>
                    <td colspan="6"/>
                </tr>
            </tfoot>
        </table>
    </div>
</div>`;
}

// ── Renderer ───────────────────────────────────────────────────────────────
export class PdcPaymentSummaryListRenderer extends ListRenderer {
    static rowsTemplate = "al_shafar_extended.PdcPaymentSummaryListRenderer.Rows";
    static recordRowTemplate = "al_shafar_extended.PdcPaymentSummaryListRenderer.RecordRow";

    setup() {
        super.setup();
        this.expandPanel = proxy({ recordId: null, contractId: null, contractName: "", cheques: [], loading: false });
        this.orm = useService("orm");
    }

    isRowExpanded(record) { return this.expandPanel.recordId === record.id; }

    async onClickExpandRow(record, ev) {
        ev.stopPropagation();
        if (this.expandPanel.recordId === record.id) { this.closePanel(); return; }
        const contractId = record.data.contract_id?.id;
        const contractName = record.data.contract_id?.display_name || "";
        // Fallback partner display for cheque lines that have no pdc.wizard
        // yet (see _loadChequesByContractId) - contract.payment.summary
        // already carries the tenant's name as tenancy_id.
        const partnerName = record.data.tenancy_id?.display_name || "";
        this.expandPanel.recordId = record.id;
        this.expandPanel.contractId = contractId;
        this.expandPanel.contractName = contractName;
        this.expandPanel.partnerName = partnerName;
        this.expandPanel.cheques = [];
        this.expandPanel.loading = true;
        await this._loadChequesByContractId(contractId);
    }

    closePanel() { this.expandPanel.recordId = null; this.expandPanel.cheques = []; }

    async reloadPanel() {
        if (!this.expandPanel.recordId) return;
        this.expandPanel.loading = true;
        await this._loadChequesByContractId(this.expandPanel.contractId);
    }

    async _loadChequesByContractId(contractId) {
        if (!contractId) { this.expandPanel.loading = false; return; }
        try {
            // "PDC Cheque Payments" should show every Cheque-type payment
            // line for this contract (contract.payments, payment_type ==
            // 'cheque') - the same reliable source Payment Details/Contract
            // Payment Summary already uses - not only the ones that already
            // have a pdc.wizard record. action_send_active_contract only
            // creates a pdc.wizard when the line's journal is flagged
            // "Is PDC Journal"; a Cheque line on a journal that isn't (yet)
            // flagged that way becomes a plain draft account.payment
            // instead, and was invisible here entirely before this change.
            const lines = await this.orm.searchRead(
                "contract.payments",
                [["contract_id", "=", contractId], ["payment_type", "=", "cheque"]],
                ["journal_id", "amount", "cheque_num", "chq_due_date",
                    "remitter_bank_id", "remitter_bank", "ref", "currency_id", "payment_pdc_id"],
                { order: "chq_due_date asc" }
            );
            const pdcIds = lines.map((l) => l.payment_pdc_id && l.payment_pdc_id[0]).filter(Boolean);
            const pdcById = {};
            if (pdcIds.length) {
                const pdcRecords = await this.orm.searchRead(
                    "pdc.wizard",
                    [["id", "in", pdcIds]],
                    ["partner_id", "payment_amount", "cheque_number", "payment_date",
                        "due_date", "remitter_bank", "reference", "state", "currency_id"]
                );
                for (const pdc of pdcRecords) pdcById[pdc.id] = pdc;
            }
            const fallbackPartner = this.expandPanel.partnerName
                ? [0, this.expandPanel.partnerName] : false;
            // A real pdc.wizard record wins when one exists (it has the
            // up-to-date state/registration data); otherwise fall back to
            // the contract.payments line itself with state 'draft' - it
            // hasn't been through PDC registration at all yet, same as
            // the "Draft Payment" label already shown in Payment Details.
            this.expandPanel.cheques = lines.map((line) => {
                const pdcId = line.payment_pdc_id && line.payment_pdc_id[0];
                if (pdcId && pdcById[pdcId]) {
                    return { id: pdcId, journal_id: line.journal_id, ...pdcById[pdcId] };
                }
                return {
                    id: `cp-${line.id}`,
                    journal_id: line.journal_id,
                    partner_id: fallbackPartner,
                    payment_amount: line.amount,
                    cheque_number: line.cheque_num,
                    payment_date: line.chq_due_date,
                    due_date: line.chq_due_date,
                    remitter_bank: (line.remitter_bank_id && line.remitter_bank_id[1]) || line.remitter_bank,
                    reference: line.ref,
                    state: "draft",
                    currency_id: line.currency_id,
                };
            });
        } catch (e) { console.error("PDC PS load error", e); }
        this.expandPanel.loading = false;
    }

    stateLabel(s) {
        return {
            draft: "Draft", registered: "Registered", returned: "Returned",
            hold: "Hold", deposited: "Deposited", bounced: "Bounced",
            done: "Done", cancel: "Cancelled",
        }[s] || s || "—";
    }
    stateBadgeClass(s) {
        return "pdcps-badge " + ({
            draft: "badge-pdcps-draft", registered: "badge-pdcps-registered",
            returned: "badge-pdcps-returned", bounced: "badge-pdcps-bounced",
            deposited: "badge-pdcps-deposited", done: "badge-pdcps-done",
        }[s] || "badge-pdcps-default");
    }
    formatAmount(a) { return new Intl.NumberFormat(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(a || 0); }
    formatDate(d) { try { return d ? new Date(d).toLocaleDateString("en-GB", { day: "2-digit", month: "short", year: "numeric" }) : "—"; } catch { return d; } }
}

PdcPaymentSummaryListRenderer.template = "al_shafar_extended.PdcPaymentSummaryListRenderer";
PdcPaymentSummaryListRenderer.components = { ...ListRenderer.components, PdcPaymentSummaryPanel };

registry.category("views").add("pdc_payment_summary_list", { ...listView, Renderer: PdcPaymentSummaryListRenderer });
