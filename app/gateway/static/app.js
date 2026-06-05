document.addEventListener("DOMContentLoaded", () => {
    // Éléments du DOM
    const loginContainer = document.getElementById("login-container");
    const appContainer = document.getElementById("app-container");
    const loginForm = document.getElementById("login-form");
    const submissionForm = document.getElementById("submission-form");
    
    // Auth displays
    const userDisplayName = document.getElementById("user-display-name");
    const userDisplayRole = document.getElementById("user-display-role");
    const navAuditLogs = document.getElementById("nav-audit-logs");
    const btnLogout = document.getElementById("btn-logout");

    // Stat numbers
    const statTotal = document.getElementById("stat-total");
    const statHigh = document.getElementById("stat-high");
    const statMedium = document.getElementById("stat-medium");
    const statLow = document.getElementById("stat-low");

    // Health statuses
    const healthGateway = document.getElementById("health-gateway");
    const healthAuth = document.getElementById("health-auth");
    const healthAnalysis = document.getElementById("health-analysis");
    const healthAudit = document.getElementById("health-audit");
    
    // Recent alerts
    const recentAlertsList = document.getElementById("dashboard-recent-alerts");

    // Modal
    const detailModal = document.getElementById("detail-modal");
    const modalContent = document.getElementById("modal-content");
    const btnCloseModal = document.querySelector(".btn-close-modal");

    // API URL configurations
    const API_BASE = "http://127.0.0.1:8000/api";

    // État de l'application
    let currentUser = {
        token: localStorage.getItem("token"),
        username: localStorage.getItem("username"),
        role: localStorage.getItem("role")
    };

    // --- Notifications Toast ---
    function showToast(message, type = "success") {
        const container = document.getElementById("toast-container");
        const toast = document.createElement("div");
        toast.className = `toast ${type}`;
        
        let icon = "fa-circle-check";
        if (type === "warning") icon = "fa-triangle-exclamation";
        if (type === "error") icon = "fa-circle-xmark";
        
        toast.innerHTML = `<i class="fa-solid ${icon}"></i> <span>${message}</span>`;
        container.appendChild(toast);
        
        // Force reflow
        toast.offsetHeight;
        
        setTimeout(() => toast.classList.add("show"), 10);
        
        setTimeout(() => {
            toast.classList.remove("show");
            setTimeout(() => toast.remove(), 300);
        }, 3500);
    }

    // --- Gestion de la session ---
    function checkSession() {
        if (currentUser.token) {
            loginContainer.classList.add("hidden");
            appContainer.classList.remove("hidden");
            
            userDisplayName.textContent = currentUser.username;
            userDisplayRole.textContent = currentUser.role.toUpperCase();
            
            if (currentUser.role === "administrateur") {
                navAuditLogs.classList.remove("hidden");
            } else {
                navAuditLogs.classList.add("hidden");
            }
            
            // Initialiser les données de la vue active
            fetchHealthCheck();
            fetchDashboardData();
            fetchHistoryData();
        } else {
            loginContainer.classList.remove("hidden");
            appContainer.classList.add("hidden");
        }
    }

    // Connexion
    loginForm.addEventListener("submit", async (e) => {
        e.preventDefault();
        const username = document.getElementById("username").value.trim();
        const password = document.getElementById("password").value;

        try {
            const response = await fetch(`${API_BASE}/auth/login`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ username, password })
            });

            if (!response.ok) {
                const data = await response.json();
                throw new Error(data.detail || "Échec de l'authentification");
            }

            const data = await response.json();
            localStorage.setItem("token", data.token);
            localStorage.setItem("username", data.username);
            localStorage.setItem("role", data.role);
            
            currentUser = {
                token: data.token,
                username: data.username,
                role: data.role
            };
            
            showToast("Connexion réussie");
            checkSession();
        } catch (error) {
            showToast(error.message, "error");
        }
    });

    // Déconnexion
    btnLogout.addEventListener("click", () => {
        localStorage.clear();
        currentUser = { token: null, username: null, role: null };
        showToast("Déconnecté");
        checkSession();
    });

    // --- Gestion des onglets ---
    const navItems = document.querySelectorAll(".nav-item");
    const tabPanels = document.querySelectorAll(".tab-panel");
    const tabTitle = document.getElementById("tab-title");
    const tabSubtitle = document.getElementById("tab-subtitle");

    navItems.forEach(item => {
        item.addEventListener("click", () => {
            const targetTab = item.getAttribute("data-tab");
            
            // Activer le bouton de nav
            navItems.forEach(nav => nav.classList.remove("active"));
            item.classList.add("active");
            
            // Activer le panel d'onglet
            tabPanels.forEach(panel => panel.classList.remove("active"));
            document.getElementById(targetTab).classList.add("active");

            // Changer les textes du header
            if (targetTab === "dashboard-tab") {
                tabTitle.textContent = "Vue d'ensemble";
                tabSubtitle.textContent = "Tableau de bord de qualification et de monitoring";
                fetchDashboardData();
            } else if (targetTab === "submission-tab") {
                tabTitle.textContent = "Analyser un e-mail";
                tabSubtitle.textContent = "Soumission sécurisée d'un signalement suspect";
            } else if (targetTab === "history-tab") {
                tabTitle.textContent = "Historique";
                tabSubtitle.textContent = "Liste complète des alertes archivées";
                fetchHistoryData();
            } else if (targetTab === "audit-tab") {
                tabTitle.textContent = "Journaux d'audit";
                tabSubtitle.textContent = "Logs de sécurité et traçabilité des opérations sensibles";
                fetchAuditLogs();
            }
        });
    });

    // --- Appels API & Chargement des Données ---

    // Récupérer l'état des services
    async function fetchHealthCheck() {
        try {
            const res = await fetch(`${API_BASE}/health`);
            if (res.ok) {
                const data = await res.json();
                updateHealthBadge(healthGateway, data.gateway);
                updateHealthBadge(healthAuth, data.auth_service);
                updateHealthBadge(healthAnalysis, data.analysis_service);
                updateHealthBadge(healthAudit, data.audit_service);
            }
        } catch (e) {
            logger.error(e);
        }
    }

    function updateHealthBadge(element, status) {
        element.className = "badge " + (status === "UP" ? "badge-success" : "badge-danger");
        element.textContent = status === "UP" ? "En ligne" : "Hors ligne";
    }

    // Récupérer les statistiques du Dashboard
    async function fetchDashboardData() {
        try {
            const res = await fetch(`${API_BASE}/submissions`, {
                headers: { "Authorization": `Bearer ${currentUser.token}` }
            });
            if (!res.ok) return;

            const list = await res.json();
            
            // Calculs
            const total = list.length;
            const high = list.filter(s => s.risk_level === "ÉLEVÉ").length;
            const medium = list.filter(s => s.risk_level === "MOYEN").length;
            const low = list.filter(s => s.risk_level === "FAIBLE").length;

            statTotal.textContent = total;
            statHigh.textContent = high;
            statMedium.textContent = medium;
            statLow.textContent = low;

            // Remplir les alertes récentes
            recentAlertsList.innerHTML = "";
            const recent = list.slice(0, 5);
            if (recent.length === 0) {
                recentAlertsList.innerHTML = `<p class="empty-state">Aucun signalement suspect disponible.</p>`;
            } else {
                recent.forEach(item => {
                    const date = new Date(item.date_submission).toLocaleDateString("fr-FR", {hour: '2-digit', minute:'2-digit'});
                    const div = document.createElement("div");
                    div.className = `alert-item ${item.risk_level}`;
                    div.innerHTML = `
                        <div>
                            <h5>${escapeHtml(item.subject)}</h5>
                            <p>${escapeHtml(item.sender)} • ${date}</p>
                        </div>
                        <span class="badge ${getBadgeClass(item.risk_level)}">${item.risk_level} (${item.score}%)</span>
                    `;
                    recentAlertsList.appendChild(div);
                });
            }

        } catch (error) {
            showToast("Erreur lors de la récupération des statistiques", "error");
        }
    }

    // Récupérer l'historique
    async function fetchHistoryData() {
        const keyword = document.getElementById("search-keyword").value;
        const risk = document.getElementById("filter-risk").value;
        
        let url = `${API_BASE}/submissions?`;
        if (keyword) url += `keyword=${encodeURIComponent(keyword)}&`;
        if (risk) url += `risk_level=${encodeURIComponent(risk)}&`;

        try {
            const res = await fetch(url, {
                headers: { "Authorization": `Bearer ${currentUser.token}` }
            });
            if (!res.ok) return;
            const data = await res.json();

            const tbody = document.getElementById("history-table-body");
            tbody.innerHTML = "";

            if (data.length === 0) {
                tbody.innerHTML = `<tr><td colspan="7" class="empty-state">Aucun signalement correspondant trouvé.</td></tr>`;
                return;
            }

            data.forEach(item => {
                const date = new Date(item.date_submission).toLocaleDateString("fr-FR", {hour: '2-digit', minute:'2-digit'});
                const tr = document.createElement("tr");
                tr.innerHTML = `
                    <td>${date}</td>
                    <td><strong style="font-weight:600">${escapeHtml(item.sender)}</strong></td>
                    <td>${escapeHtml(item.subject)}</td>
                    <td><span class="badge ${getBadgeClass(item.risk_level)}">${item.risk_level}</span></td>
                    <td><strong>${item.score}/100</strong></td>
                    <td>${escapeHtml(item.user_submitted)}</td>
                    <td><button class="btn btn-secondary btn-sm btn-details" data-id="${item.id}"><i class="fa-solid fa-eye"></i> Inspecter</button></td>
                `;
                tbody.appendChild(tr);
            });

            // Attacher les écouteurs sur les boutons inspecter
            document.querySelectorAll(".btn-details").forEach(btn => {
                btn.addEventListener("click", () => showSubmissionDetail(btn.getAttribute("data-id")));
            });

        } catch (error) {
            showToast("Erreur lors du chargement de l'historique", "error");
        }
    }

    // Rechercher et filtrer
    document.getElementById("btn-apply-filters").addEventListener("click", fetchHistoryData);

    // Récupérer les logs d'audit
    async function fetchAuditLogs() {
        try {
            const res = await fetch(`${API_BASE}/audit/logs?limit=50`, {
                headers: { "Authorization": `Bearer ${currentUser.token}` }
            });
            if (res.status === 403) {
                showToast("Accès refusé. Rôle administrateur requis !", "error");
                return;
            }
            if (!res.ok) return;
            const logs = await res.json();

            const tbody = document.getElementById("audit-table-body");
            tbody.innerHTML = "";

            if (logs.length === 0) {
                tbody.innerHTML = `<tr><td colspan="6" class="empty-state">Aucun log d'audit disponible.</td></tr>`;
                return;
            }

            logs.forEach(log => {
                const date = new Date(log.timestamp).toLocaleDateString("fr-FR", {hour: '2-digit', minute:'2-digit', second: '2-digit'});
                const tr = document.createElement("tr");
                tr.innerHTML = `
                    <td>${date}</td>
                    <td><span class="badge-role">${escapeHtml(log.service)}</span></td>
                    <td><strong>${escapeHtml(log.event_type)}</strong></td>
                    <td><span class="badge ${getSeverityClass(log.severity)}">${log.severity}</span></td>
                    <td style="max-width:300px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;">${escapeHtml(log.message)}</td>
                    <td>${log.user_id ? escapeHtml(log.user_id) : '-'}</td>
                `;
                tbody.appendChild(tr);
            });
        } catch (error) {
            showToast("Erreur lors de la récupération des logs d'audit", "error");
        }
    }

    document.getElementById("btn-refresh-audit").addEventListener("click", fetchAuditLogs);

    // --- Soumission d'un e-mail ---
    submissionForm.addEventListener("submit", async (e) => {
        e.preventDefault();
        
        const sender = document.getElementById("sender-input").value.trim();
        const subject = document.getElementById("subject-input").value.trim();
        const urlsText = document.getElementById("urls-input").value.trim();
        const has_attachment = document.getElementById("attachment-input").checked;
        const content = document.getElementById("content-input").value.trim();

        const urls = urlsText ? urlsText.split("\n").map(u => u.trim()).filter(u => u.length > 0) : [];

        // UI Reset
        const placeholder = document.getElementById("analysis-result-placeholder");
        const resultCard = document.getElementById("analysis-result-card");
        const scoreDisplay = document.getElementById("result-score");
        const badge = document.getElementById("result-badge");
        const justificationsUl = document.getElementById("result-justifications");
        const fallbackAlert = document.getElementById("fallback-alert");

        placeholder.classList.remove("hidden");
        resultCard.classList.add("hidden");
        fallbackAlert.classList.add("hidden");

        try {
            const response = await fetch(`${API_BASE}/submissions`, {
                method: "POST",
                headers: { 
                    "Content-Type": "application/json",
                    "Authorization": `Bearer ${currentUser.token}`
                },
                body: JSON.stringify({ sender, subject, urls, has_attachment, content })
            });

            if (!response.ok) {
                const errData = await response.json();
                throw new Error(errData.detail || "Erreur de traitement");
            }

            const data = await response.json();

            // Remplir l'UI des résultats
            placeholder.classList.add("hidden");
            resultCard.classList.remove("hidden");

            scoreDisplay.textContent = data.score;
            
            badge.className = `result-risk-badge ${data.risk_level}`;
            badge.textContent = data.risk_level;

            justificationsUl.innerHTML = "";
            data.justifications.forEach(j => {
                const li = document.createElement("li");
                li.textContent = j;
                justificationsUl.appendChild(li);
            });

            if (data.fallback_used) {
                fallbackAlert.classList.remove("hidden");
            }

            showToast("Analyse de phishing terminée avec succès !");
            
            // Effacer le formulaire
            submissionForm.reset();
        } catch (error) {
            showToast(error.message, "error");
        }
    });

    // --- Modal Détails ---
    async function showSubmissionDetail(id) {
        try {
            const res = await fetch(`${API_BASE}/submissions/${id}`, {
                headers: { "Authorization": `Bearer ${currentUser.token}` }
            });
            if (!res.ok) return;
            const data = await res.json();

            const date = new Date(data.date_submission).toLocaleDateString("fr-FR", {hour: '2-digit', minute:'2-digit'});
            
            modalContent.innerHTML = `
                <div style="display:flex; justify-content:space-between; align-items:center; border-bottom:1px solid var(--border-color); padding-bottom:10px;">
                    <div>
                        <h4 style="font-size:1.1rem; font-weight:600;">Expéditeur : ${escapeHtml(data.sender)}</h4>
                        <p style="color:var(--text-secondary); font-size:0.85rem;">Date : ${date} • Soumis par : ${escapeHtml(data.user_submitted)}</p>
                    </div>
                    <span class="badge ${getBadgeClass(data.risk_level)}" style="font-size:0.9rem;">${data.risk_level} (${data.score}/100)</span>
                </div>
                <div>
                    <h5 style="font-weight:600; margin-bottom:5px;">Objet :</h5>
                    <p style="background:rgba(255,255,255,0.02); padding:10px; border-radius:6px; font-weight:500;">${escapeHtml(data.subject)}</p>
                </div>
                <div>
                    <h5 style="font-weight:600; margin-bottom:5px;">Pièce Jointe :</h5>
                    <p>${data.has_attachment ? '<span class="badge badge-danger"><i class="fa-solid fa-paperclip"></i> Oui</span>' : '<span class="badge badge-success">Non</span>'}</p>
                </div>
                <div>
                    <h5 style="font-weight:600; margin-bottom:5px;">Liens extraits :</h5>
                    ${data.urls.length > 0 ? `<ul style="list-style:inside; padding-left:10px;">${data.urls.map(u => `<li><a href="${escapeHtml(u)}" target="_blank" style="color:var(--primary);">${escapeHtml(u)}</a></li>`).join('')}</ul>` : '<p style="color:var(--text-secondary); font-size:0.85rem;">Aucun lien détecté</p>'}
                </div>
                <div>
                    <h5 style="font-weight:600; margin-bottom:5px;">Justifications du score :</h5>
                    <ul class="justifications-list">
                        ${data.justifications.map(j => `<li>${escapeHtml(j)}</li>`).join('')}
                    </ul>
                </div>
                <div>
                    <h5 style="font-weight:600; margin-bottom:5px;">Contenu de l'e-mail :</h5>
                    <div style="background:rgba(0,0,0,0.2); padding:15px; border-radius:8px; max-height:200px; overflow-y:auto; font-family:monospace; font-size:0.85rem; white-space:pre-wrap;">${escapeHtml(data.content)}</div>
                </div>
            `;

            detailModal.classList.remove("hidden");
        } catch (error) {
            showToast("Erreur lors du chargement des détails", "error");
        }
    }

    btnCloseModal.addEventListener("click", () => detailModal.classList.add("hidden"));
    detailModal.addEventListener("click", (e) => {
        if (e.target === detailModal) detailModal.classList.add("hidden");
    });

    // --- Helpers ---
    function getBadgeClass(risk) {
        if (risk === "ÉLEVÉ") return "badge-danger";
        if (risk === "MOYEN") return "badge-warning";
        return "badge-success";
    }

    function getSeverityClass(severity) {
        if (severity === "CRITICAL") return "badge-danger";
        if (severity === "WARNING") return "badge-warning";
        return "badge-success";
    }

    function escapeHtml(text) {
        if (!text) return "";
        const map = {
            '&': '&amp;',
            '<': '&lt;',
            '>': '&gt;',
            '"': '&quot;',
            "'": '&#039;'
        };
        return text.replace(/[&<>"']/g, function(m) { return map[m]; });
    }

    // Démarrer l'application
    checkSession();
});
