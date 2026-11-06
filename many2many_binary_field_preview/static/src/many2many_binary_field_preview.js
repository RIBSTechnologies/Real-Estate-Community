/** @odoo-module */
// Odoo 20: attachments are rendered by Many2XBinary (used by Many2ManyBinaryField)
import { Many2XBinary } from "@web/views/fields/many2x_binary/many2x_binary";
import { patch } from "@web/core/utils/patch";
import { useService } from "@web/core/utils/hooks";
import { useFileViewer } from "@web/core/file_viewer/file_viewer_hook";

const Many2ManyBinaryFieldPatch = {
    setup() {
        super.setup(...arguments);
        this.store = useService("mail.store");
        this.fileViewer = useFileViewer();
        this.http = useService("http");
    },

    async onClickPreview(file, files) {
        const attachments = files.map(f => 
            this.store.Attachment.insert({
                id: f.id,
                filename: f.name,
                name: f.name,
                mimetype: f.mimetype,
                extension: f.name.split('.').pop().toLowerCase(),
            })
        );
        
        // Find the current file in attachments
        const currentAttachment = attachments.find(a => a.id === file.id);
        
        // Check if file is PDF or image (handled well by default viewer)
        if (currentAttachment.mimetype === 'application/pdf' || 
            currentAttachment.mimetype.startsWith('image/')) {
            this.fileViewer.open(currentAttachment, attachments);
            return;
        }
        
        // Handle Office documents (DOC, DOCX, XLS, XLSX, etc.)
        if (currentAttachment.mimetype.includes('officedocument') || 
            currentAttachment.mimetype.includes('msword') ||
            currentAttachment.extension.match(/doc|docx|xls|xlsx|ppt|pptx/)) {
            
            const fileUrl = `/web/content/${file.id}?download=true`;
            const fullUrl = `${window.location.origin}${fileUrl}`;
            
            // Use Microsoft Office Online Viewer in an iframe
            const officeViewerUrl = `https://view.officeapps.live.com/op/embed.aspx?src=${encodeURIComponent(fullUrl)}`;
            
            // Check if we're in resume.db mode
            const currentModel = this.props.record.resModel;
            if (currentModel === 'contact.admin' || currentModel === 'resume.db' || currentModel === 'hr.job.api.response' || currentModel === 'hr.applicant' || currentModel === 'custom.wizard.model') {
                // Create modal with iframe
                const dialog = document.createElement('div');
                dialog.className = 'modal fade';
                dialog.id = 'documentViewerModal';
                dialog.setAttribute('tabindex', '-1');
                dialog.setAttribute('role', 'dialog');
                dialog.setAttribute('aria-labelledby', 'documentViewerModalLabel');
                dialog.innerHTML = `
                    <div class="modal-dialog modal-xl" role="document">
                        <div class="modal-content">
                            <div class="modal-header">
                                <h5 class="modal-title" id="documentViewerModalLabel">${currentAttachment.name}</h5>
                                <button type="button" class="close" data-dismiss="modal" aria-label="Close">
                                    <span aria-hidden="true">&times;</span>
                                </button>
                            </div>
                            <div class="modal-body p-0">
                                <iframe src="${officeViewerUrl}" width="100%" height="600px" frameborder="0"></iframe>
                            </div>
                        </div>
                    </div>
                `;
                
                document.body.appendChild(dialog);
                
                // Initialize and show the modal (Bootstrap 5 API; jQuery is not loaded since Odoo 20)
                const modal = Modal.getOrCreateInstance(dialog);
                modal.show();
                
                // Directly remove the modal from DOM when close button is clicked
                dialog.querySelectorAll('.close').forEach((btn) => btn.addEventListener('click', () => {
                    // First hide the modal (this will trigger any Bootstrap cleanup)
                    modal.hide();
                    // Then immediately remove from DOM
                    dialog.remove();
                }));
            } else {
                // For other models, open in new tab as before
                window.open(officeViewerUrl, '_blank');
            }
            return;
        }
        
        // Fallback to default file viewer for other types
        this.fileViewer.open(currentAttachment, attachments);
    }
};

patch(Many2XBinary.prototype, Many2ManyBinaryFieldPatch);