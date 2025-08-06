/**
 * Deployment management JavaScript functionality
 */

class DeploymentManager {
    constructor() {
        this.statusUpdateInterval = null;
        this.isAutoRefreshEnabled = true;
        this.currentBatchId = null;
        this.websocketConnection = null;
        
        this.init();
    }
    
    init() {
        this.bindEventListeners();
        this.initializeStatusUpdates();
        this.setupFeatherIcons();
    }
    
    bindEventListeners() {
        // File upload validation
        const fileInput = document.getElementById('yaml_file');
        if (fileInput) {
            fileInput.addEventListener('change', this.handleFileChange.bind(this));
        }
        
        // Form validation
        const uploadForm = document.getElementById('uploadForm');
        if (uploadForm) {
            uploadForm.addEventListener('submit', this.handleFormSubmit.bind(this));
        }
        
        // Validation button
        const validateBtn = document.getElementById('validateBtn');
        if (validateBtn) {
            validateBtn.addEventListener('click', this.validateYAML.bind(this));
        }
        
        // Auto-refresh toggle
        const autoRefreshToggle = document.getElementById('autoRefreshToggle');
        if (autoRefreshToggle) {
            autoRefreshToggle.addEventListener('change', this.toggleAutoRefresh.bind(this));
        }
        
        // Manual refresh button
        const refreshBtn = document.getElementById('refreshBtn');
        if (refreshBtn) {
            refreshBtn.addEventListener('click', this.manualRefresh.bind(this));
        }
        
        // Rollback buttons
        document.addEventListener('click', (e) => {
            if (e.target.matches('.rollback-btn') || e.target.closest('.rollback-btn')) {
                e.preventDefault();
                const batchId = e.target.dataset.batchId || e.target.closest('.rollback-btn').dataset.batchId;
                this.confirmRollback(batchId);
            }
        });
    }
    
    setupFeatherIcons() {
        // Initialize feather icons
        if (typeof feather !== 'undefined') {
            feather.replace();
        }
    }
    
    handleFileChange(event) {
        const file = event.target.files[0];
        const validateBtn = document.getElementById('validateBtn');
        const deployBtn = document.getElementById('deployBtn');
        const validationResults = document.getElementById('validationResults');
        
        if (file) {
            // Reset validation state
            this.resetValidationState();
            
            // Enable validation button
            if (validateBtn) {
                validateBtn.disabled = false;
            }
            
            // Disable deploy button until validation
            if (deployBtn) {
                deployBtn.disabled = true;
            }
            
            // Hide previous validation results
            if (validationResults) {
                validationResults.style.display = 'none';
            }
            
            // Check file size
            const maxSize = 16 * 1024 * 1024; // 16MB
            if (file.size > maxSize) {
                this.showError('File size exceeds 16MB limit. Please select a smaller file.');
                event.target.value = '';
                return;
            }
            
            // Check file extension
            const allowedExtensions = ['.yaml', '.yml'];
            const fileExtension = file.name.toLowerCase().substring(file.name.lastIndexOf('.'));
            if (!allowedExtensions.includes(fileExtension)) {
                this.showError('Please select a valid YAML file (.yaml or .yml extension).');
                event.target.value = '';
                return;
            }
        } else {
            // No file selected
            if (validateBtn) {
                validateBtn.disabled = true;
            }
            if (deployBtn) {
                deployBtn.disabled = true;
            }
        }
    }
    
    async validateYAML() {
        const fileInput = document.getElementById('yaml_file');
        const validateBtn = document.getElementById('validateBtn');
        const deployBtn = document.getElementById('deployBtn');
        const validationResults = document.getElementById('validationResults');
        const validationContent = document.getElementById('validationContent');
        
        if (!fileInput.files.length) {
            this.showError('Please select a YAML file first.');
            return;
        }
        
        const file = fileInput.files[0];
        const formData = new FormData();
        formData.append('yaml_file', file);
        
        // Update button state
        validateBtn.disabled = true;
        const originalText = validateBtn.innerHTML;
        validateBtn.innerHTML = '<i data-feather="loader" class="me-2"></i>Validating...';
        this.setupFeatherIcons();
        
        try {
            const response = await fetch('/validate-yaml', {
                method: 'POST',
                body: formData
            });
            
            const data = await response.json();
            
            if (data.valid) {
                // Validation successful
                validationContent.innerHTML = `
                    <div class="d-flex justify-content-between align-items-center mb-2">
                        <span><strong>✓ YAML is valid</strong></span>
                        <span class="badge bg-success">Valid</span>
                    </div>
                    <div class="row">
                        <div class="col-md-6">
                            <small class="text-muted">Deployments: <strong>${data.deployment_count}</strong></small>
                        </div>
                        <div class="col-md-6">
                            <small class="text-muted">Pillars: <strong>${data.pillars.join(', ')}</strong></small>
                        </div>
                    </div>
                `;
                validationResults.className = 'mb-4 alert alert-success';
                
                // Enable deploy button
                deployBtn.disabled = false;
                deployBtn.classList.remove('btn-secondary');
                deployBtn.classList.add('btn-primary');
                
                this.isValidated = true;
            } else {
                // Validation failed
                validationContent.innerHTML = `
                    <div class="d-flex justify-content-between align-items-center mb-2">
                        <span><strong>✗ YAML validation failed</strong></span>
                        <span class="badge bg-danger">Invalid</span>
                    </div>
                    <div class="text-danger">
                        <strong>Error:</strong> ${this.escapeHtml(data.error)}
                    </div>
                `;
                validationResults.className = 'mb-4 alert alert-danger';
                
                // Keep deploy button disabled
                deployBtn.disabled = true;
                deployBtn.classList.remove('btn-primary');
                deployBtn.classList.add('btn-secondary');
                
                this.isValidated = false;
            }
            
            validationResults.style.display = 'block';
            
        } catch (error) {
            console.error('Validation error:', error);
            this.showValidationError('Unable to validate YAML file. Please try again.');
            this.isValidated = false;
        } finally {
            // Restore button state
            validateBtn.disabled = false;
            validateBtn.innerHTML = originalText;
            this.setupFeatherIcons();
        }
    }
    
    handleFormSubmit(event) {
        if (!this.isValidated) {
            event.preventDefault();
            this.showError('Please validate your YAML file before deployment.');
            return false;
        }
        
        // Update submit button state
        const submitBtn = event.target.querySelector('button[type="submit"]');
        if (submitBtn) {
            submitBtn.disabled = true;
            submitBtn.innerHTML = '<i data-feather="loader" class="me-2"></i>Deploying...';
            this.setupFeatherIcons();
        }
        
        return true;
    }
    
    initializeStatusUpdates() {
        // Check if we're on a status page
        const pathParts = window.location.pathname.split('/');
        if (pathParts[1] === 'status' && pathParts[2]) {
            this.currentBatchId = pathParts[2];
            this.startStatusUpdates();
        }
    }
    
    startStatusUpdates() {
        if (!this.currentBatchId || !this.isAutoRefreshEnabled) {
            return;
        }
        
        // Start periodic updates
        this.statusUpdateInterval = setInterval(() => {
            this.updateDeploymentStatus();
        }, 15000); // Update every 15 seconds
        
        // Initial update
        this.updateDeploymentStatus();
    }
    
    stopStatusUpdates() {
        if (this.statusUpdateInterval) {
            clearInterval(this.statusUpdateInterval);
            this.statusUpdateInterval = null;
        }
    }
    
    async updateDeploymentStatus() {
        if (!this.currentBatchId) {
            return;
        }
        
        try {
            const response = await fetch(`/api/status/${this.currentBatchId}`);
            const data = await response.json();
            
            // Update batch status if changed
            this.updateBatchStatus(data);
            
            // Update individual deployment statuses
            this.updateDeploymentRows(data.deployments);
            
            // If batch is complete, stop updates
            if (['success', 'failed', 'rollback'].includes(data.batch_status)) {
                this.stopStatusUpdates();
            }
            
        } catch (error) {
            console.error('Error fetching status updates:', error);
        }
    }
    
    updateBatchStatus(data) {
        // Update progress bar
        const progressBar = document.querySelector('.progress');
        if (progressBar && data.total_deployments > 0) {
            const successRate = (data.successful_deployments / data.total_deployments * 100);
            const failedRate = (data.failed_deployments / data.total_deployments * 100);
            const processingRate = 100 - successRate - failedRate;
            
            const successBar = progressBar.querySelector('.bg-success');
            const failedBar = progressBar.querySelector('.bg-danger');
            const processingBar = progressBar.querySelector('.bg-warning');
            
            if (successBar) successBar.style.width = `${successRate}%`;
            if (failedBar) failedBar.style.width = `${failedRate}%`;
            if (processingBar) processingBar.style.width = `${processingRate}%`;
        }
        
        // Update status counts
        const successCount = document.querySelector('.success-count');
        const failedCount = document.querySelector('.failed-count');
        
        if (successCount) successCount.textContent = data.successful_deployments;
        if (failedCount) failedCount.textContent = data.failed_deployments;
    }
    
    updateDeploymentRows(deployments) {
        deployments.forEach(deployment => {
            const row = document.querySelector(`[data-deployment-id="${deployment.id}"]`);
            if (row) {
                // Update status badge
                const statusBadge = row.querySelector('.status-badge');
                if (statusBadge) {
                    statusBadge.className = `badge bg-${this.getStatusClass(deployment.status)} status-badge`;
                    statusBadge.innerHTML = `
                        <i data-feather="${this.getStatusIcon(deployment.status)}" class="me-1" style="width: 0.8rem; height: 0.8rem;"></i>
                        ${deployment.status.charAt(0).toUpperCase() + deployment.status.slice(1)}
                    `;
                }
                
                // Update timeline item class
                const timelineItem = row.closest('.timeline-item');
                if (timelineItem) {
                    timelineItem.className = `timeline-item ${deployment.status}`;
                }
                
                // Show/hide error message
                const errorAlert = row.querySelector('.alert-danger');
                if (deployment.error_message && !errorAlert) {
                    const errorDiv = document.createElement('div');
                    errorDiv.className = 'row mt-2';
                    errorDiv.innerHTML = `
                        <div class="col-12">
                            <div class="alert alert-danger mb-0">
                                <small>
                                    <i data-feather="alert-circle" class="me-1"></i>
                                    <strong>Error:</strong> ${this.escapeHtml(deployment.error_message)}
                                </small>
                            </div>
                        </div>
                    `;
                    row.querySelector('.card-body').appendChild(errorDiv);
                }
            }
        });
        
        this.setupFeatherIcons();
    }
    
    toggleAutoRefresh() {
        const toggle = document.getElementById('autoRefreshToggle');
        this.isAutoRefreshEnabled = toggle ? toggle.checked : true;
        
        if (this.isAutoRefreshEnabled) {
            this.startStatusUpdates();
        } else {
            this.stopStatusUpdates();
        }
    }
    
    manualRefresh() {
        location.reload();
    }
    
    confirmRollback(batchId) {
        if (confirm('Are you sure you want to rollback this deployment batch? This will cancel any ongoing deployments.')) {
            this.performRollback(batchId);
        }
    }
    
    async performRollback(batchId) {
        try {
            const response = await fetch(`/rollback/${batchId}`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                }
            });
            
            if (response.ok) {
                this.showSuccess('Rollback initiated successfully');
                // Refresh page after a short delay
                setTimeout(() => {
                    location.reload();
                }, 2000);
            } else {
                this.showError('Failed to initiate rollback');
            }
        } catch (error) {
            console.error('Rollback error:', error);
            this.showError('Error initiating rollback');
        }
    }
    
    // Utility methods
    showError(message) {
        this.showAlert(message, 'danger');
    }
    
    showSuccess(message) {
        this.showAlert(message, 'success');
    }
    
    showValidationError(message) {
        const validationResults = document.getElementById('validationResults');
        const validationContent = document.getElementById('validationContent');
        
        if (validationResults && validationContent) {
            validationContent.innerHTML = `
                <div class="text-danger">
                    <strong>Validation Error:</strong> ${this.escapeHtml(message)}
                </div>
            `;
            validationResults.className = 'mb-4 alert alert-danger';
            validationResults.style.display = 'block';
        }
    }
    
    showAlert(message, type) {
        // Create alert element
        const alertDiv = document.createElement('div');
        alertDiv.className = `alert alert-${type} alert-dismissible fade show`;
        alertDiv.innerHTML = `
            <i data-feather="${type === 'danger' ? 'alert-circle' : 'check-circle'}" class="me-2"></i>
            ${this.escapeHtml(message)}
            <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
        `;
        
        // Insert at top of main content
        const container = document.querySelector('.container');
        if (container) {
            container.insertBefore(alertDiv, container.firstChild);
            this.setupFeatherIcons();
            
            // Auto-remove after 5 seconds
            setTimeout(() => {
                if (alertDiv.parentNode) {
                    alertDiv.remove();
                }
            }, 5000);
        }
    }
    
    resetValidationState() {
        this.isValidated = false;
        const deployBtn = document.getElementById('deployBtn');
        if (deployBtn) {
            deployBtn.disabled = true;
            deployBtn.classList.remove('btn-primary');
            deployBtn.classList.add('btn-secondary');
        }
    }
    
    getStatusClass(status) {
        const statusClasses = {
            'pending': 'secondary',
            'processing': 'warning',
            'success': 'success',
            'failed': 'danger',
            'rollback': 'info'
        };
        return statusClasses[status] || 'secondary';
    }
    
    getStatusIcon(status) {
        const statusIcons = {
            'pending': 'clock',
            'processing': 'loader',
            'success': 'check-circle',
            'failed': 'x-circle',
            'rollback': 'rotate-ccw'
        };
        return statusIcons[status] || 'circle';
    }
    
    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }
    
    // Cleanup method
    destroy() {
        this.stopStatusUpdates();
        if (this.websocketConnection) {
            this.websocketConnection.close();
        }
    }
}

// Global deployment manager instance
let deploymentManager;

// Initialize on DOM content loaded
document.addEventListener('DOMContentLoaded', function() {
    deploymentManager = new DeploymentManager();
});

// Cleanup on page unload
window.addEventListener('beforeunload', function() {
    if (deploymentManager) {
        deploymentManager.destroy();
    }
});

// Export for external use
window.DeploymentManager = DeploymentManager;
