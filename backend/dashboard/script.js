// State
let currentRole = 'citizen'; // 'citizen' or 'admin'
let currentUserId = 'dev_citizen';
const API_BASE = 'http://localhost:8000/api';

// DOM Elements
const tabs = document.querySelectorAll('.nav-links li');
const tabContents = document.querySelectorAll('.tab-content');
const roleBtn = document.getElementById('toggle-role-btn');
const roleText = document.getElementById('current-role');

// Upload Elements
const dropZone = document.getElementById('drop-zone');
const fileInput = document.getElementById('image-input');
const previewContainer = document.getElementById('image-preview');
const previewImg = previewContainer.querySelector('img');
const removeBtn = document.getElementById('remove-image');
const uploadForm = document.getElementById('upload-form');
const submitBtn = document.getElementById('submit-btn');

// Initialization
document.addEventListener('DOMContentLoaded', () => {
    // Check API health
    fetch(`${API_BASE}/health`)
        .then(res => res.json())
        .then(data => {
            const statusEl = document.getElementById('system-status');
            if (data.model_loaded) {
                statusEl.innerHTML = '<span class="status-dot"></span> System Online (AI Active)';
            } else {
                statusEl.innerHTML = '<span class="status-dot" style="background:var(--warning)"></span> System Online (Demo Mode)';
            }
        })
        .catch(err => {
            document.getElementById('system-status').innerHTML = '<span class="status-dot" style="background:var(--danger)"></span> Offline';
        });

    loadCitizenData();
});

// Tab Switching
tabs.forEach(tab => {
    tab.addEventListener('click', () => {
        const target = tab.dataset.tab;
        
        // Hide all
        tabs.forEach(t => t.classList.remove('active'));
        tabContents.forEach(c => c.classList.remove('active'));
        
        // Show target
        tab.classList.add('active');
        document.getElementById(`tab-${target}`).classList.add('active');
        
        // Load data based on tab
        if (target === 'citizen-history') loadCitizenData();
        if (target === 'municipal-dashboard') loadMunicipalData();
    });
});

// Role Toggle (Dev mode feature)
roleBtn.addEventListener('click', () => {
    if (currentRole === 'citizen') {
        currentRole = 'admin';
        currentUserId = 'dev_admin';
        roleText.innerText = 'Admin / Municipal';
        roleBtn.innerText = 'Switch to Citizen';
        tabs[2].click(); // Go to municipal tab
    } else {
        currentRole = 'citizen';
        currentUserId = 'dev_citizen';
        roleText.innerText = 'Citizen';
        roleBtn.innerText = 'Switch to Admin';
        tabs[0].click(); // Go to upload tab
    }
});

// Helper: API Fetch with auth
async function apiFetch(endpoint, options = {}) {
    const headers = {
        'X-Dev-User': currentUserId,
        ...options.headers
    };
    const res = await fetch(`${API_BASE}${endpoint}`, { ...options, headers });
    if (!res.ok) throw new Error(await res.text());
    return res.json();
}

// ─── UPLOAD HANDLING ──────────────────────────────────────────────

dropZone.addEventListener('click', () => fileInput.click());
dropZone.addEventListener('dragover', e => { e.preventDefault(); dropZone.classList.add('dragover'); });
dropZone.addEventListener('dragleave', () => dropZone.classList.remove('dragover'));
dropZone.addEventListener('drop', e => {
    e.preventDefault();
    dropZone.classList.remove('dragover');
    if (e.dataTransfer.files.length) handleFile(e.dataTransfer.files[0]);
});
fileInput.addEventListener('change', e => {
    if (e.target.files.length) handleFile(e.target.files[0]);
});

function handleFile(file) {
    if (!file.type.startsWith('image/')) {
        alert('Please select an image file');
        return;
    }
    const reader = new FileReader();
    reader.onload = e => {
        previewImg.src = e.target.result;
        previewContainer.classList.remove('hidden');
        submitBtn.disabled = false;
    };
    reader.readAsDataURL(file);
}

removeBtn.addEventListener('click', e => {
    e.stopPropagation();
    fileInput.value = '';
    previewImg.src = '';
    previewContainer.classList.add('hidden');
    submitBtn.disabled = true;
    document.getElementById('result-section').classList.add('hidden');
});

uploadForm.addEventListener('submit', async e => {
    e.preventDefault();
    if (!fileInput.files[0]) return;

    submitBtn.disabled = true;
    submitBtn.innerHTML = '<i class="fa-solid fa-circle-notch fa-spin"></i> Analyzing...';

    const formData = new FormData();
    formData.append('image', fileInput.files[0]);
    formData.append('latitude', '0.0'); // Mock GPS
    formData.append('longitude', '0.0');
    formData.append('address', document.getElementById('location').value);
    formData.append('xai_mode', document.getElementById('xai-mode').value);
    formData.append('description', document.getElementById('description').value);

    try {
        const res = await apiFetch('/reports/submit', {
            method: 'POST',
            body: formData
        });

        showResults(res);
    } catch (err) {
        alert('Upload failed: ' + err.message);
    } finally {
        submitBtn.disabled = false;
        submitBtn.innerHTML = '<i class="fa-solid fa-paper-plane"></i> Submit Another';
    }
});

function showResults(data) {
    document.getElementById('result-section').classList.remove('hidden');
    document.getElementById('res-class').innerText = data.primary_class.replace('_', ' ');
    document.getElementById('res-conf').innerText = (data.confidence * 100).toFixed(1) + '%';
    
    const sevEl = document.getElementById('res-sev');
    sevEl.innerText = data.severity;
    sevEl.style.color = data.severity === 'HIGH' ? 'var(--danger)' : (data.severity === 'MEDIUM' ? 'var(--warning)' : 'var(--success)');

    document.getElementById('res-xai-method').innerText = data.xai_method.toUpperCase();
    
    // Check if XAI is still generating (background task for ZooLime)
    const imgEl = document.getElementById('res-xai-img');
    const loadingEl = document.getElementById('xai-loading');
    
    if (data.xai_method === 'zoolime' && data.severity === 'HIGH') {
        // ZooLime runs in background
        imgEl.src = previewImg.src; // Show original for now
        loadingEl.classList.remove('hidden');
        // Poll for completion
        pollReportStatus(data.report_id);
    } else {
        // Fetch report details to get the gradcam URL
        apiFetch(`/reports/${data.report_id}`).then(report => {
            loadingEl.classList.add('hidden');
            imgEl.src = 'http://localhost:8000' + (report.gradcam_url || report.image_url);
        });
    }
}

async function pollReportStatus(reportId) {
    const int = setInterval(async () => {
        try {
            const r = await apiFetch(`/reports/${reportId}`);
            if (r.zoolime_url) {
                document.getElementById('xai-loading').classList.add('hidden');
                document.getElementById('res-xai-img').src = 'http://localhost:8000' + r.zoolime_url;
                clearInterval(int);
            }
        } catch (e) { clearInterval(int); }
    }, 5000);
}

// ─── CITIZEN TAB ─────────────────────────────────────────────────

async function loadCitizenData() {
    try {
        const data = await apiFetch('/reports/my?page_size=10');
        
        // Update stats
        document.getElementById('cit-total').innerText = data.total;
        document.getElementById('cit-resolved').innerText = data.reports.filter(r => r.status === 'completed').length;
        document.getElementById('cit-tokens').innerText = data.reports.reduce((sum, r) => sum + (r.reward_tokens || 0), 0);

        // Populate table
        const tbody = document.querySelector('#citizen-reports-table tbody');
        tbody.innerHTML = '';
        
        data.reports.forEach(r => {
            const tr = document.createElement('tr');
            tr.innerHTML = `
                <td><img src="http://localhost:8000${r.image_url}" class="thumbnail"></td>
                <td><strong>${r.primary_class.replace('_', ' ')}</strong><br><small>${r.location.address || 'GPS Location'}</small></td>
                <td>${new Date(r.created_at).toLocaleDateString()}</td>
                <td><span class="badge badge-${r.status}">${r.status.toUpperCase()}</span></td>
                <td><span class="badge badge-${r.severity.toLowerCase()}">${r.severity}</span></td>
                <td><button class="btn-secondary btn-small" onclick="viewReport('${r.id}')">View</button></td>
            `;
            tbody.appendChild(tr);
        });
    } catch (err) {
        console.error('Failed to load citizen data', err);
    }
}

// ─── MUNICIPAL TAB ───────────────────────────────────────────────

let classChart, sevChart;

async function loadMunicipalData() {
    if (currentRole !== 'admin') return;
    
    try {
        // Load stats
        const stats = await apiFetch('/municipal/stats');
        renderCharts(stats);

        // Load queue
        const queue = await apiFetch('/municipal/reports?sort_by=priority_score');
        const tbody = document.querySelector('#municipal-queue-table tbody');
        tbody.innerHTML = '';

        queue.reports.forEach(r => {
            const score = r.priority_score.toFixed(1);
            const tr = document.createElement('tr');
            tr.innerHTML = `
                <td><strong style="color: ${score > 70 ? 'var(--danger)' : 'white'}">${score}</strong></td>
                <td>${r.primary_class.replace('_', ' ')}</td>
                <td><span class="badge badge-${r.severity.toLowerCase()}">${r.severity}</span></td>
                <td>${r.location.address || 'Map Point'}</td>
                <td>
                    <select class="status-select" onchange="updateStatus('${r.id}', this.value)">
                        <option value="pending" ${r.status==='pending'?'selected':''}>Pending</option>
                        <option value="in_progress" ${r.status==='in_progress'?'selected':''}>In Progress</option>
                        <option value="completed" ${r.status==='completed'?'selected':''}>Completed</option>
                        <option value="rejected" ${r.status==='rejected'?'selected':''}>Rejected</option>
                    </select>
                </td>
                <td>
                    <button class="btn-secondary btn-small" onclick="viewReport('${r.id}')">Review</button>
                    <a href="http://localhost:8000/api/municipal/reports/${r.id}/pdf" target="_blank" class="btn-secondary btn-small" title="Download PDF"><i class="fa-solid fa-file-pdf"></i></a>
                </td>
            `;
            tbody.appendChild(tr);
        });
    } catch (err) {
        console.error('Failed to load municipal data', err);
    }
}

document.getElementById('refresh-queue').addEventListener('click', loadMunicipalData);

async function updateStatus(id, newStatus) {
    try {
        await apiFetch(`/municipal/reports/${id}`, {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ status: newStatus })
        });
        // Reload citizen data if we switch back
    } catch (e) {
        alert('Failed to update status');
    }
}

function renderCharts(stats) {
    Chart.defaults.color = '#94a3b8';
    Chart.defaults.font.family = 'Outfit';

    const ctxClass = document.getElementById('classChart').getContext('2d');
    if (classChart) classChart.destroy();
    classChart = new Chart(ctxClass, {
        type: 'doughnut',
        data: {
            labels: Object.keys(stats.by_class).map(k => k.replace('_', ' ')),
            datasets: [{
                data: Object.values(stats.by_class),
                backgroundColor: ['#4f46e5', '#10b981', '#f59e0b'],
                borderWidth: 0
            }]
        },
        options: { cutout: '70%', plugins: { legend: { position: 'right' } } }
    });

    const ctxSev = document.getElementById('severityChart').getContext('2d');
    if (sevChart) sevChart.destroy();
    sevChart = new Chart(ctxSev, {
        type: 'bar',
        data: {
            labels: Object.keys(stats.by_severity),
            datasets: [{
                label: 'Reports',
                data: Object.values(stats.by_severity),
                backgroundColor: ['#10b981', '#f59e0b', '#ef4444'],
                borderRadius: 4
            }]
        },
        options: {
            plugins: { legend: { display: false } },
            scales: { y: { beginAtZero: true, grid: { color: 'rgba(255,255,255,0.05)' } }, x: { grid: { display: false } } }
        }
    });
}

// ─── MODAL ───────────────────────────────────────────────────────

const modal = document.getElementById('report-modal');
document.querySelector('.close-modal').addEventListener('click', () => modal.classList.add('hidden'));

async function viewReport(id) {
    try {
        const r = await apiFetch(`/reports/${id}`);
        const inf = r.inference || {};
        
        const xaiUrl = r.zoolime_url || r.gradcam_url || r.image_url;
        
        document.getElementById('modal-title').innerText = `Report Details: ${r.location.address || 'GPS Location'}`;
        document.getElementById('modal-body').innerHTML = `
            <div class="modal-split">
                <div class="modal-img-container">
                    <h4>Original Image</h4>
                    <img src="http://localhost:8000${r.image_url}">
                    <h4>AI Explanation (${inf.xai?.method || 'Grad-CAM'})</h4>
                    <img src="http://localhost:8000${xaiUrl}">
                </div>
                <div>
                    <div class="result-box primary mb-3">
                        <h5>AI Diagnosis</h5>
                        <p style="font-size:20px;font-weight:700">${(inf.primary_class||'').replace('_',' ')} (${(inf.confidence*100||0).toFixed(1)}%)</p>
                    </div>
                    <p><strong>Status:</strong> <span class="badge badge-${r.status}">${r.status.toUpperCase()}</span></p>
                    <p><strong>Severity:</strong> <span class="badge badge-${(inf.severity||'low').toLowerCase()}">${inf.severity||'LOW'}</span></p>
                    <p><strong>Detections:</strong> ${inf.num_detections||0}</p>
                    <p><strong>Date:</strong> ${new Date(r.created_at).toLocaleString()}</p>
                    <p><strong>Notes:</strong> ${r.description || 'None'}</p>
                    
                    ${currentRole === 'admin' ? `
                        <hr>
                        <h4>Municipal Actions</h4>
                        <div class="form-group mt-2">
                            <label>Update Status</label>
                            <select onchange="updateStatus('${r.id}', this.value)">
                                <option value="pending" ${r.status==='pending'?'selected':''}>Pending</option>
                                <option value="in_progress" ${r.status==='in_progress'?'selected':''}>In Progress</option>
                                <option value="completed" ${r.status==='completed'?'selected':''}>Completed</option>
                                <option value="rejected" ${r.status==='rejected'?'selected':''}>Rejected</option>
                            </select>
                        </div>
                        <a href="http://localhost:8000/api/municipal/reports/${r.id}/pdf" target="_blank" class="btn-primary mt-4" style="text-decoration:none; display: inline-block; margin-right: 10px;">
                            <i class="fa-solid fa-file-pdf"></i> Generate PDF Report
                        </a>
                        <button class="btn-secondary mt-4" style="background: var(--danger); border-color: var(--danger); color: white;" onclick="deleteReport('${r.id}')">
                            <i class="fa-solid fa-trash"></i> Delete Report
                        </button>
                    ` : ''}
                </div>
            </div>
        `;
        modal.classList.remove('hidden');
    } catch (e) {
        alert('Could not load report details');
    }
}

async function deleteReport(id) {
    if (!confirm('Are you sure you want to permanently delete this report?')) return;
    try {
        await apiFetch(`/admin/reports/${id}`, {
            method: 'DELETE'
        });
        modal.classList.add('hidden');
        loadMunicipalData();
    } catch (e) {
        alert('Failed to delete report: ' + e.message);
    }
}
