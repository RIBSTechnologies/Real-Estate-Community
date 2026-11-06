/** @odoo-module **/

import { listView } from "@web/views/list/list_view";
import { NotificationPlugin } from "@web/core/notifications/notification_plugin";
import { ListRenderer } from "@web/views/list/list_renderer";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { Component, proxy, usePlugin, useProps, xml } from "@odoo/owl";

// ── PaymentSummaryPanel (inline inside table row) ──────────────────────────
export class PaymentSummaryPanel extends Component {

    props = useProps();
    setup() {
        this.orm = useService("orm");
        this.actionService = useService("action");
        this.notification = usePlugin(NotificationPlugin);
        this.busy = proxy({ id: null });
    }

    async onAddComment(payId, ev) {
        ev.stopPropagation();
        this.busy.id = payId;
        try {
            const action = await this.orm.call("contract.payments", "action_open_add_comment_wizard", [[payId]]);
            await this.actionService.doAction(action, { onClose: () => this.props.onReload() });
        } catch (e) { this.notification.add(e.data?.message || "Failed to open comment wizard.", { type: "danger" }); }
        finally { this.busy.id = null; }
    }

    async onLineReceived(payId, ev) {
        ev.stopPropagation();
        this.busy.id = payId;
        try {
            await this.orm.call("contract.payments", "line_received", [[payId]]);
            this.notification.add("Payment marked as received.", { type: "success" });
            await this.props.onReload();
        } catch (e) { this.notification.add(e.data?.message || "Failed to confirm payment.", { type: "danger" }); }
        finally { this.busy.id = null; }
    }

    static template = xml`
<div class="ps-panel">
    <div class="ps-panel-header">
        <span class="ps-panel-title">
            <i class="fa fa-credit-card me-2"/>Payment Details
            <span t-if="this.props.contractName" class="ps-contract-name ms-2">— <t t-out="this.props.contractName"/></span>
        </span>
        <div class="d-flex align-items-center gap-2">
            <span t-if="!this.props.loading" class="ps-panel-count"><t t-out="this.props.payments.length"/> records</span>
            <button class="btn btn-sm btn-close ps-close-btn" t-on-click="() => this.props.onClose()"/>
        </div>
    </div>
    <div t-if="this.props.loading" class="ps-loading-wrap"><i class="fa fa-spinner fa-spin me-2"/>Loading…</div>
    <div t-else="" class="ps-table-wrap">
        <table class="ps-table">
            <thead><tr>
                <th>#</th><th>Type</th><th>Beneficiary</th><th>Amount</th>
                <th>Cheque No.</th><th>Date</th><th>Remitter</th><th>Reference</th>
                <th>Payment</th><th>Finance</th><th>Actions</th><th>Status</th>
            </tr></thead>
            <tbody>
                <t t-foreach="this.props.payments" t-as="pay" t-key="pay.id">
                    <tr t-att-class="pay.line_payment_received==='received'?'ps-row-received':pay.line_payment_received==='not_received'?'ps-row-rejected':''">
                        <td class="ps-td-seq"><t t-out="pay_index+1"/></td>
                        <td><span t-att-class="this.props.paymentTypeBadgeClass(pay.payment_type)" t-out="this.props.paymentTypeLabel(pay.payment_type)"/></td>
                        <td><t t-out="pay.journal_id and pay.journal_id[1] or '—'"/></td>
                        <td class="ps-td-amount"><t t-out="this.props.formatAmount(pay.amount)"/> <span class="ps-currency"><t t-out="pay.currency_id and pay.currency_id[1] or ''"/></span></td>
                        <td><t t-out="pay.cheque_num or '—'"/></td>
                        <td><t t-out="this.props.formatDate(pay.chq_due_date)"/></td>
                        <td><t t-out="pay.remitter_bank_id and pay.remitter_bank_id[1] or '—'"/></td>
                        <td><t t-out="pay.ref or '—'"/></td>
                        <td>
                            <t t-if="pay.payment_account_id"><span class="ps-link-badge"><i class="fa fa-file-text-o me-1"/><t t-out="pay.payment_account_id[1]"/></span></t>
                            <t t-elif="pay.payment_pdc_id"><span class="ps-link-badge ps-pdc"><i class="fa fa-clock-o me-1"/><t t-out="pay.payment_pdc_id[1]"/></span></t>
                            <t t-else="">—</t>
                        </td>
                        <td><t t-out="pay.financial_person_id and pay.financial_person_id[1] or '—'"/></td>
                        <td class="text-center ps-action-cell">
                            <t t-if="pay.line_payment_received !== 'received'">
                                <i t-if="this.busy.id === pay.id" class="fa fa-spinner fa-spin text-muted"/>
                                <t t-else="">
                                    <button class="btn btn-sm ps-btn-comment" title="Add Comment" t-on-click="(ev) => this.onAddComment(pay.id, ev)"><i class="fa fa-comment"/></button>
                                    <button class="btn btn-sm ps-btn-confirm ms-1" title="Receive and Confirm" t-on-click="(ev) => this.onLineReceived(pay.id, ev)"><i class="fa fa-check-circle"/></button>
                                </t>
                            </t>
                            <t t-else=""><i class="fa fa-check-circle text-success" title="Received"/></t>
                        </td>
                        <td><span t-att-class="this.props.statusBadgeClass(pay.line_payment_received)" t-out="this.props.statusLabel(pay.line_payment_received)"/></td>
                    </tr>
                    <tr t-if="pay.rejected_reason or pay.leasing_reason" class="ps-comment-row">
                        <td class="ps-td-seq"/><td colspan="11" class="ps-comment-cell">
                            <t t-if="pay.rejected_reason"><span class="ps-comment-label ps-finance"><i class="fa fa-comment me-1"/>Finance: </span><t t-out="pay.rejected_reason"/></t>
                            <t t-if="pay.leasing_reason"><span class="ps-comment-label ps-leasing ms-3"><i class="fa fa-comment-o me-1"/>Leasing: </span><t t-out="pay.leasing_reason"/></t>
                        </td>
                    </tr>
                </t>
            </tbody>
            <tfoot>
                <tr class="ps-total-row">
                    <td colspan="3" class="text-end fw-semibold">Total</td>
                    <td class="ps-td-amount fw-bold"><t t-out="this.props.formatAmount(this.props.payments.reduce((s,p)=>s+(p.amount||0),0))"/></td>
                    <td colspan="8"/>
                </tr>
            </tfoot>
        </table>
    </div>
</div>`;
}

// ── Renderer ───────────────────────────────────────────────────────────────
export class PaymentSummaryListRenderer extends ListRenderer {
    static rowsTemplate = "ribs_real_estate.PaymentSummaryListRenderer.Rows";
    static recordRowTemplate = "ribs_real_estate.PaymentSummaryListRenderer.RecordRow";

    setup() {
        super.setup();
        this.expandPanel = proxy({ recordId: null, contractId: null, contractName: "", payments: [], loading: false });
        this.orm = useService("orm");
    }

    isRowExpanded(record) { return this.expandPanel.recordId === record.id; }

    async onClickExpandRow(record, ev) {
        ev.stopPropagation();
        if (this.expandPanel.recordId === record.id) { this.closePanel(); return; }
        const contractId = record.data.contract_id?.id;
        const contractName = record.data.contract_id?.display_name || "";
        this.expandPanel.recordId = record.id;
        this.expandPanel.contractId = contractId;
        this.expandPanel.contractName = contractName;
        this.expandPanel.payments = [];
        this.expandPanel.loading = true;
        await this._loadPaymentsByIds(contractId ? [contractId] : []);
    }

    closePanel() { this.expandPanel.recordId = null; this.expandPanel.payments = []; }

    async reloadPanel() {
        if (!this.expandPanel.recordId) return;
        this.expandPanel.loading = true;
        const ids = this.expandPanel.contractId ? [this.expandPanel.contractId] : [];
        await this._loadPaymentsByIds(ids);
    }

    async _loadPaymentsByIds(ids) {
        if (!ids.length) { this.expandPanel.loading = false; return; }
        try {
            this.expandPanel.payments = await this.orm.searchRead(
                "contract.payments",
                ids.length === 1 ? [["contract_id", "=", ids[0]]] : [["contract_id", "in", ids]],
                ["contract_id", "payment_type", "journal_id", "amount", "cheque_num", "chq_due_date",
                    "remitter_bank_id", "ref", "line_payment_received", "payment_account_id", "payment_pdc_id",
                    "rejected_reason", "leasing_reason", "currency_id", "financial_person_id"],
                { order: "chq_due_date asc" }
            );
        } catch (e) { console.error("PS load error", e); }
        this.expandPanel.loading = false;
    }

    paymentTypeLabel(t) { return { bank: "Bank Transfer", cheque: "Cheque", cash: "Cash" }[t] || t || "—"; }
    paymentTypeBadgeClass(t) { return "ps-badge " + ({ bank: "badge-ps-bank", cheque: "badge-ps-cheque", cash: "badge-ps-cash" }[t] || "badge-ps-default"); }
    statusLabel(s) { return { received: "Received", not_received: "Not Received", waiting_for_approval: "Waiting for Approval" }[s] || s || "—"; }
    statusBadgeClass(s) { return "ps-badge " + ({ received: "badge-ps-received", not_received: "badge-ps-not-received", waiting_for_approval: "badge-ps-waiting" }[s] || "badge-ps-default"); }
    formatAmount(a) { return new Intl.NumberFormat(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(a || 0); }
    formatDate(d) { try { return d ? new Date(d).toLocaleDateString("en-GB", { day: "2-digit", month: "short", year: "numeric" }) : "—"; } catch { return d; } }
}

PaymentSummaryListRenderer.template = "ribs_real_estate.PaymentSummaryListRenderer";
PaymentSummaryListRenderer.components = { ...ListRenderer.components, PaymentSummaryPanel };

registry.category("views").add("payment_summary_list", { ...listView, Renderer: PaymentSummaryListRenderer });
