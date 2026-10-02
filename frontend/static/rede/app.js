const state = {
    dashboard: null,
    auditEvents: [],
    charts: {},
    largeChart: null,
    countdown: 30,
    currentFormImageUrl: "",
    draggedServiceId: null,
    dragStartOrder: [],
    suppressNextCardClick: false,
    savingOrder: false,
    toastTimer: null,
    currentDetailsServiceId: null,
    notificationSettings: null,
    notificationSubscriptions: [],
    notificationServices: [],
};

const ui = {
    addServiceButton: document.getElementById("add-service-button"),
    notificationSettingsButton: document.getElementById("notification-settings-button"),
    overviewGrid: document.getElementById("overview-grid"),
    servicesGrid: document.getElementById("services-grid"),
    servicesCaption: document.getElementById("services-caption"),
    auditPanel: document.getElementById("audit-panel"),
    auditCaption: document.getElementById("audit-caption"),
    nextUpdateTimer: document.getElementById("next-update-timer"),
    lastGlobalUpdate: document.getElementById("last-global-update"),
    systemBanner: document.getElementById("system-banner"),
    systemBannerTitle: document.getElementById("system-banner-title"),
    systemBannerMessage: document.getElementById("system-banner-message"),
    toastRegion: document.getElementById("toast-region"),
    detailsModal: document.getElementById("detailsModal"),
    detailsName: document.getElementById("detailsName"),
    detailsHost: document.getElementById("detailsHost"),
    detailsMetrics: document.getElementById("detailsMetrics"),
    switchDetails: document.getElementById("switchDetails"),
    detailsStatusLabel: document.getElementById("detailsStatusLabel"),
    detailsThresholdLabel: document.getElementById("detailsThresholdLabel"),
    largeChartCanvas: document.getElementById("largeChart"),
    closeDetailsButton: document.getElementById("close-details-button"),
    addModal: document.getElementById("addModal"),
    modalTitle: document.getElementById("modalTitle"),
    editServiceId: document.getElementById("editServiceId"),
    serviceName: document.getElementById("serviceName"),
    serviceKind: document.getElementById("serviceKind"),
    serviceHost: document.getElementById("serviceHost"),
    serviceThreshold: document.getElementById("serviceThreshold"),
    snmpCommunity: document.getElementById("snmpCommunity"),
    snmpCommunityField: document.getElementById("snmpCommunityField"),
    snmpPort: document.getElementById("snmpPort"),
    snmpPortField: document.getElementById("snmpPortField"),
    serviceImageFile: document.getElementById("serviceImageFile"),
    serviceImageHint: document.getElementById("serviceImageHint"),
    closeFormButton: document.getElementById("close-form-button"),
    cancelFormButton: document.getElementById("cancel-form-button"),
    saveServiceButton: document.getElementById("save-service-button"),
    notificationModal: document.getElementById("notificationModal"),
    notificationEnabled: document.getElementById("notificationEnabled"),
    notificationRecipient: document.getElementById("notificationRecipient"),
    notificationRecipientList: document.getElementById("notificationRecipientList"),
    addNotificationRecipientButton: document.getElementById("add-notification-recipient"),
    smtpStatus: document.getElementById("smtpStatus"),
    notificationThreshold: document.getElementById("notificationThreshold"),
    closeNotificationButton: document.getElementById("close-notification-button"),
    cancelNotificationButton: document.getElementById("cancel-notification-button"),
    saveNotificationButton: document.getElementById("save-notification-button"),
};

function escapeHtml(value) {
    return String(value ?? "")
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;")
        .replaceAll("'", "&#39;");
}

function formatLatency(value) {
    return typeof value === "number" ? `${value.toFixed(1)} ms` : "Sem resposta";
}

function formatMetricValue(value, fallback = "--") {
    return typeof value === "number" ? `${Math.round(value)} ms` : fallback;
}

function formatCompactLatency(value) {
    return typeof value === "number" ? `${Math.round(value)} ms` : "--";
}

function formatPercent(value) {
    return typeof value === "number" ? `${value.toFixed(1)}%` : "--";
}

function isHttpService(service) {
    return service?.checkType === "http";
}

function formatHttpStatus(service) {
    return typeof service?.httpStatusCode === "number" ? String(service.httpStatusCode) : "Sem resposta";
}

function formatHttpResult(service) {
    if (!service?.lastUpdate) {
        return "--";
    }
    if (service.online) {
        return "OK";
    }
    return typeof service.httpStatusCode === "number" ? "HTTP falhou" : "Rede falhou";
}

function formatDateTime(value) {
    if (!value) return "Sem medições ainda";
    return new Date(value).toLocaleString("pt-BR");
}

function formatAuditDuration(event) {
    let seconds = event.duration_seconds;
    if (event.ongoing && event.started_at) {
        seconds = Math.max(0, Math.floor((Date.now() - new Date(event.started_at).getTime()) / 1000));
    }
    if (typeof seconds !== "number") return "--";

    const days = Math.floor(seconds / 86400);
    const hours = Math.floor((seconds % 86400) / 3600);
    const minutes = Math.floor((seconds % 3600) / 60);
    const remainingSeconds = seconds % 60;
    if (days) return `${days}d ${hours}h ${minutes}min`;
    if (hours) return `${hours}h ${minutes}min`;
    if (minutes) return `${minutes}min ${remainingSeconds}s`;
    return `${remainingSeconds}s`;
}

function getAuditTypeMeta() {
    return { label: "Queda", className: "audit-type-outage" };
}

function renderAuditEvents(serviceId = state.currentDetailsServiceId) {
    if (!serviceId) return;

    const currentTableWrap = ui.auditPanel.querySelector(".audit-table-wrap");
    const previousScrollTop = currentTableWrap?.scrollTop || 0;
    const previousScrollLeft = currentTableWrap?.scrollLeft || 0;
    const service = state.dashboard?.services.find((item) => String(item.id) === String(serviceId));
    const events = state.auditEvents.filter((event) => String(event.service_id) === String(serviceId));
    const ongoingCount = events.filter((event) => event.ongoing).length;
    ui.auditCaption.textContent = `${events.length} eventos registrados | ${ongoingCount} em andamento`;

    if (!events.length) {
        ui.auditPanel.innerHTML = `
            <div class="audit-empty">
                <span>Nenhum incidente registrado</span>
                <p>${escapeHtml(service?.name || "Este serviço")} não possui quedas registradas.</p>
            </div>
        `;
        return;
    }

    ui.auditPanel.innerHTML = `
        <div class="audit-table-wrap">
            <table class="audit-table">
                <thead>
                    <tr>
                        <th>Sistema</th>
                        <th>Evento</th>
                        <th>Início</th>
                        <th>Término</th>
                        <th>Duração</th>
                        <th>Métricas</th>
                        <th>Situação</th>
                    </tr>
                </thead>
                <tbody>
                    ${events.map((event) => {
                        const type = getAuditTypeMeta(event);
                        const metrics = `Perda: ${formatPercent(event.packet_loss_pct)}`;
                        return `
                            <tr>
                                <td data-label="Sistema">
                                    <strong>${escapeHtml(event.service_name)}</strong>
                                    <small>${escapeHtml(event.service_host)}</small>
                                </td>
                                <td data-label="Evento"><span class="audit-type ${type.className}">${type.label}</span></td>
                                <td data-label="Início">${formatDateTime(event.started_at)}</td>
                                <td data-label="Término">${event.ongoing ? "--" : formatDateTime(event.ended_at)}</td>
                                <td data-label="Duração">${formatAuditDuration(event)}</td>
                                <td data-label="Métricas">${metrics}</td>
                                <td data-label="Situação">
                                    <span class="audit-state ${event.ongoing ? "audit-state-open" : "audit-state-closed"}">
                                        ${event.ongoing ? "Em andamento" : "Encerrado"}
                                    </span>
                                </td>
                            </tr>
                        `;
                    }).join("")}
                </tbody>
            </table>
        </div>
    `;

    const updatedTableWrap = ui.auditPanel.querySelector(".audit-table-wrap");
    updatedTableWrap.scrollTop = previousScrollTop;
    updatedTableWrap.scrollLeft = previousScrollLeft;
}

function renderAuditError(error) {
    ui.auditCaption.textContent = "Auditoria indisponível";
    ui.auditPanel.innerHTML = `
        <div class="audit-empty audit-empty-error">
            <span>Não foi possível carregar os eventos</span>
            <p>${escapeHtml(describeError(error, "Tente novamente na próxima atualização."))}</p>
        </div>
    `;
}

async function fetchAuditEvents() {
    try {
        state.auditEvents = await requestJson("/api/rede/audit");
        renderAuditEvents(state.currentDetailsServiceId);
    } catch (error) {
        console.error(error);
        renderAuditError(error);
    }
}

function getServiceState(service) {
    if (!service.lastUpdate) {
        return "pending";
    }
    if (service.status === "offline") {
        return "failed";
    }
    return service.status;
}

function getStatusMeta(service) {
    const stateName = typeof service === "string" ? service : getServiceState(service);
    const httpService = typeof service === "object" && isHttpService(service);

    if (stateName === "pending") {
        return {
            label: "Sem dados",
            showAlert: true,
            chipClass: "status-unknown",
            accentClass: "accent-unknown",
        };
    }
    if (stateName === "failed") {
        return {
            label: httpService ? "HTTP falhou" : "Ping falhou",
            showAlert: true,
            chipClass: "status-offline",
            accentClass: "accent-offline",
        };
    }
    if (stateName === "offline") {
        return {
            label: "Offline",
            showAlert: true,
            chipClass: "status-offline",
            accentClass: "accent-offline",
        };
    }
    if (stateName === "degraded") {
        return {
            label: "Degradado",
            showAlert: true,
            chipClass: "status-degraded",
            accentClass: "accent-degraded",
        };
    }
    return {
        label: "Online",
        showAlert: false,
        chipClass: "status-online",
        accentClass: "accent-online",
    };
}

function describeError(error, fallback) {
    if (error instanceof TypeError) {
        return "Servidor indisponível. Verifique se o backend está ativo.";
    }
    return error?.message || fallback;
}

function showToast(message, type = "error") {
    if (!ui.toastRegion) return;

    window.clearTimeout(state.toastTimer);
    ui.toastRegion.innerHTML = `
        <div class="toast toast-${type}">
            <strong>${type === "success" ? "Tudo certo" : "Atenção"}</strong>
            <span>${escapeHtml(message)}</span>
        </div>
    `;
    state.toastTimer = window.setTimeout(() => {
        ui.toastRegion.innerHTML = "";
    }, 4200);
}

function showSystemBanner(title, message) {
    ui.systemBannerTitle.textContent = title;
    ui.systemBannerMessage.textContent = message;
    ui.systemBanner.hidden = false;
}

function hideSystemBanner() {
    ui.systemBanner.hidden = true;
}

async function requestJson(url, options) {
    const response = await fetch(url, options);
    if (!response.ok) {
        const payload = await response.json().catch(() => ({ error: "Erro de requisição." }));
        throw new Error(payload.error || `Falha em ${url}`);
    }
    return response.json();
}

function updateTimerLabel() {
    ui.nextUpdateTimer.textContent = `Próxima atualização em ${state.countdown}s`;
}

function renderHeroMeta() {
    const { meta, summary } = state.dashboard;
    ui.lastGlobalUpdate.textContent = `Última atualização: ${formatDateTime(meta.lastUpdate)}`;
    ui.servicesCaption.textContent =
        `${summary.total} serviços monitorados | ${summary.offline} offline | ${summary.degraded} degradados`;
    updateTimerLabel();
}

function renderOverview() {
    const { summary } = state.dashboard;
    const cards = [
        {
            title: "Serviços monitorados",
            value: summary.total,
            tone: "tone-neutral",
        },
        {
            title: "Saudáveis",
            value: `${summary.online}/${summary.total}`,
            tone: "tone-good",
        },
        {
            title: "Latência média",
            value: summary.avgLatencyMs != null ? `${summary.avgLatencyMs.toFixed(1)} ms` : "--",
            tone: "tone-latency",
        },
        {
            title: "Estabilidade média",
            value: summary.avgStabilityPct != null ? `${summary.avgStabilityPct.toFixed(1)}%` : "--",
            tone: "tone-stability",
        },
    ];

    ui.overviewGrid.innerHTML = cards.map((card) => `
        <article class="overview-card panel ${card.tone}">
            <span>${card.title}</span>
            <strong>${card.value}</strong>
        </article>
    `).join("");
}

function destroyMiniCharts() {
    Object.values(state.charts).forEach((chart) => chart.destroy());
    state.charts = {};
}

function getCurrentGridOrder() {
    return Array.from(ui.servicesGrid.querySelectorAll(".service-card"))
        .map((card) => card.dataset.serviceId)
        .filter(Boolean);
}

function renderServiceCard(service) {
    const statusMeta = getStatusMeta(service);
    const hasMeasurements = Boolean(service.lastUpdate);
    const initials = service.name
        .split(" ")
        .map((part) => part[0] || "")
        .join("")
        .slice(0, 2)
        .toUpperCase();
    const hasImage = Boolean(service.imageUrl);

    return `
        <article
            class="service-card panel ${statusMeta.accentClass}"
            data-action="open-details"
            data-service-id="${service.id}"
            draggable="true"
        >
            <div class="service-card-header">
                <div class="service-title-block">
                    <h3>${escapeHtml(service.name)}${service.kind === "switch" ? ' <small title="Coleta SNMPv2c">SNMP</small>' : ""}</h3>
                    <span class="status-chip ${statusMeta.chipClass}">
                        ${statusMeta.label}
                        ${statusMeta.showAlert ? `<span class="status-alert" aria-label="Requer atenção">!</span>` : ""}
                    </span>
                </div>

                <div class="service-actions">
                    <button
                        class="icon-button subtle"
                        type="button"
                        data-action="edit-service"
                        data-service-id="${service.id}"
                        aria-label="Editar ${escapeHtml(service.name)}"
                        title="Editar serviço"
                    >
                        <svg viewBox="0 0 24 24" aria-hidden="true" focusable="false">
                            <path d="M12 20h9" />
                            <path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4Z" />
                        </svg>
                    </button>
                    <button
                        class="icon-button subtle danger"
                        type="button"
                        data-action="remove-service"
                        data-service-id="${service.id}"
                        aria-label="Remover ${escapeHtml(service.name)}"
                        title="Remover serviço"
                    >
                        <svg viewBox="0 0 24 24" aria-hidden="true" focusable="false">
                            <path d="M3 6h18" />
                            <path d="M8 6V4h8v2" />
                            <path d="M19 6l-1 14H6L5 6" />
                            <path d="M10 11v5" />
                            <path d="M14 11v5" />
                        </svg>
                    </button>
                </div>
            </div>

            <div class="service-avatar-panel">
                <div class="service-avatar ${hasImage ? "has-image" : ""}" data-service-avatar="${service.id}">
                    ${hasImage ? `<img src="${escapeHtml(service.imageUrl)}" alt="${escapeHtml(service.name)}">` : ""}
                    <span class="service-avatar-fallback">${escapeHtml(initials)}</span>
                </div>
            </div>

            <div class="service-chart">
                ${hasMeasurements ? `<canvas id="chart-${service.id}"></canvas>` : `<div class="chart-empty">Sem histórico para exibir</div>`}
            </div>

            <div class="metrics-grid metrics-grid-compact">
                <div class="metric-box">
                    <span>${isHttpService(service) ? "Resposta" : "Latência"}</span>
                    <strong>${formatMetricValue(service.avgLatencyMs, hasMeasurements ? "Sem resposta" : "--")}</strong>
                </div>
                <div class="metric-box">
                    <span>${isHttpService(service) ? "HTTP" : "Jitter"}</span>
                    <strong>${isHttpService(service) ? formatHttpStatus(service) : formatMetricValue(service.jitterMs)}</strong>
                </div>
                <div class="metric-box">
                    <span>Limiar</span>
                    <strong>${formatCompactLatency(service.threshold)}</strong>
                </div>
                <div class="metric-box">
                    <span>${isHttpService(service) ? "Resultado" : "Perda"}</span>
                    <strong>${isHttpService(service) ? formatHttpResult(service) : formatPercent(service.packetLossPct)}</strong>
                </div>
            </div>
        </article>
    `;
}

function createMiniChart(service, points) {
    const canvas = document.getElementById(`chart-${service.id}`);
    if (!canvas) return;

    const ctx = canvas.getContext("2d");
    if (!points.length) return;

    const color = service.status === "offline"
        ? "#f97316"
        : service.status === "degraded"
            ? "#f59e0b"
            : "#22c55e";

    state.charts[service.id] = new Chart(ctx, {
        type: "line",
        data: {
            labels: points.map((point) => point.timestamp),
            datasets: [{
                data: points.map((point) => point.latencyMs),
                borderColor: color,
                backgroundColor: `${color}22`,
                fill: true,
                borderWidth: 2,
                pointRadius: 0,
                tension: 0.35,
                spanGaps: true,
            }],
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            animation: false,
            plugins: {
                legend: { display: false },
                tooltip: { enabled: false },
            },
            scales: {
                x: { display: false },
                y: { display: false, beginAtZero: true },
            },
        },
    });
}

function renderServices() {
    const { services, history } = state.dashboard;
    destroyMiniCharts();

    if (!services.length) {
        ui.servicesGrid.innerHTML = `
            <article class="empty-state panel empty-state-info">
                <span>Nenhum dado</span>
                <h3>Nenhum serviço cadastrado</h3>
                <p>Adicione um host para começar a acompanhar latência, perda e estabilidade.</p>
            </article>
        `;
        return;
    }

    ui.servicesGrid.innerHTML = services.map(renderServiceCard).join("");
    bindAvatarFallbacks();
    services.forEach((service) => createMiniChart(service, history[service.id] || []));
}

async function persistServiceOrder() {
    const serviceIds = getCurrentGridOrder();
    state.savingOrder = true;

    try {
        await requestJson("/api/rede/services/reorder", {
            method: "PUT",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ serviceIds }),
        });
        await fetchDashboard();
    } catch (error) {
        console.error(error);
        showToast(describeError(error, "Não foi possível salvar a nova ordem dos cards."));
        await fetchDashboard().catch(() => undefined);
    } finally {
        state.savingOrder = false;
    }
}

function bindAvatarFallbacks() {
    ui.servicesGrid.querySelectorAll(".service-avatar.has-image img").forEach((image) => {
        image.addEventListener("error", () => {
            image.parentElement.classList.remove("has-image");
            image.remove();
        }, { once: true });
    });
}

function renderLargeChart(service, points) {
    const ctx = ui.largeChartCanvas.getContext("2d");

    if (state.largeChart) {
        state.largeChart.destroy();
    }

    state.largeChart = new Chart(ctx, {
        type: "line",
        data: {
            labels: points.map((point) =>
                new Date(point.timestamp).toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" })
            ),
            datasets: [
                {
                    label: isHttpService(service) ? "Tempo de resposta" : "Latência média",
                    data: points.map((point) => point.latencyMs),
                    borderColor: "#2563eb",
                    backgroundColor: "rgba(37, 99, 235, 0.12)",
                    fill: true,
                    tension: 0.35,
                    borderWidth: 2,
                    pointRadius: 2,
                    spanGaps: true,
                },
                {
                    label: "Limiar",
                    data: points.map(() => service.threshold),
                    borderColor: "#f97316",
                    borderDash: [6, 6],
                    borderWidth: 1.5,
                    pointRadius: 0,
                    spanGaps: true,
                },
            ],
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            interaction: { mode: "index", intersect: false },
            plugins: {
                legend: {
                    labels: {
                        color: "#dbe7ff",
                        usePointStyle: true,
                        pointStyle: "circle",
                    },
                },
            },
            scales: {
                x: {
                    ticks: { color: "#94a3b8" },
                    grid: { color: "rgba(148, 163, 184, 0.12)" },
                },
                y: {
                    beginAtZero: true,
                    ticks: { color: "#94a3b8" },
                    grid: { color: "rgba(148, 163, 184, 0.12)" },
                },
            },
        },
    });
}

function openDetails(serviceId) {
    const service = state.dashboard.services.find((item) => item.id === serviceId);
    if (!service) return;

    const history = state.dashboard.history[serviceId] || [];
    const statusMeta = getStatusMeta(service);

    ui.detailsName.textContent = service.name;
    ui.detailsHost.textContent = service.host;
    ui.detailsStatusLabel.textContent = `${statusMeta.label} | última leitura ${formatDateTime(service.lastUpdate)}`;
    ui.detailsThresholdLabel.textContent = `Limiar: ${formatCompactLatency(service.threshold)}`;
    ui.detailsMetrics.innerHTML = `
        <article class="detail-metric panel">
            <span>${isHttpService(service) ? "Tempo de resposta" : "Latência média"}</span>
            <strong>${formatLatency(service.avgLatencyMs)}</strong>
        </article>
        <article class="detail-metric panel">
            <span>${isHttpService(service) ? "Código HTTP" : "Jitter"}</span>
            <strong>${isHttpService(service) ? formatHttpStatus(service) : formatLatency(service.jitterMs)}</strong>
        </article>
        <article class="detail-metric panel">
            <span>${isHttpService(service) ? "Resultado" : "Perda de pacotes"}</span>
            <strong>${isHttpService(service) ? formatHttpResult(service) : formatPercent(service.packetLossPct)}</strong>
        </article>
        <article class="detail-metric panel">
            <span>Estabilidade</span>
            <strong>${formatPercent(service.stabilityPct)}</strong>
        </article>
    `;

    ui.switchDetails.hidden = service.kind !== "switch";
    if (service.kind === "switch") {
        ui.switchDetails.textContent = "Carregando dados SNMP...";
        loadSwitchDetails(serviceId);
    }

    state.currentDetailsServiceId = serviceId;
    renderAuditEvents(serviceId);
    renderLargeChart(service, history);
    ui.detailsModal.style.display = "flex";
}

function formatSwitchStatus(status) {
    return status === 1 ? "Ativa" : status === 2 ? "Inativa" : status === 3 ? "Em teste" : "Desconhecido";
}

function formatSwitchCounter(value) {
    return typeof value === "number" ? new Intl.NumberFormat("pt-BR").format(value) : "--";
}

async function loadSwitchDetails(serviceId) {
    try {
        const snapshot = await requestJson(`/api/rede/services/${serviceId}/switch`);
        if (state.currentDetailsServiceId !== serviceId) return;
        if (!snapshot) {
            ui.switchDetails.textContent = "Aguardando a primeira coleta SNMP.";
            return;
        }
        if (snapshot.error) {
            ui.switchDetails.textContent = `Falha na coleta SNMP: ${snapshot.error}`;
            return;
        }
        const system = snapshot.system || {};
        const ports = snapshot.interfaces || [];
        ui.switchDetails.innerHTML = `
            <h4>Switch · última coleta ${escapeHtml(formatDateTime(snapshot.collectedAt))}</h4>
            <div class="switch-system">
                <span>Nome: <strong>${escapeHtml(system.name || "--")}</strong></span>
                <span>Localização: <strong>${escapeHtml(system.location || "--")}</strong></span>
                <span>Uptime: <strong>${system.uptimeTicks == null ? "--" : escapeHtml((system.uptimeTicks / 8640000).toFixed(1)) + " dias"}</strong></span>
                <span>Descrição: <strong>${escapeHtml(system.description || "--")}</strong></span>
            </div>
            <div class="switch-table-wrap"><table class="switch-table">
                <thead><tr><th>Interface</th><th>Estado</th><th>Admin.</th><th>Entrada (octetos)</th><th>Saída (octetos)</th><th>Erros entrada</th><th>Erros saída</th></tr></thead>
                <tbody>${ports.map((port) => `
                    <tr><td>${escapeHtml(port.name)}</td>
                    <td class="${port.operStatus === 1 ? "switch-port-up" : "switch-port-down"}">${formatSwitchStatus(port.operStatus)}</td>
                    <td>${formatSwitchStatus(port.adminStatus)}</td>
                    <td>${formatSwitchCounter(port.inOctets)}</td><td>${formatSwitchCounter(port.outOctets)}</td>
                    <td>${formatSwitchCounter(port.inErrors)}</td><td>${formatSwitchCounter(port.outErrors)}</td></tr>
                `).join("")}</tbody>
            </table></div>
            ${ports.length ? "" : "<p>Nenhuma interface retornada pelo switch.</p>"}
        `;
    } catch (error) {
        if (state.currentDetailsServiceId === serviceId) {
            ui.switchDetails.textContent = describeError(error, "Não foi possível carregar os dados SNMP.");
        }
    }
}

function closeDetails() {
    ui.detailsModal.style.display = "none";
    state.currentDetailsServiceId = null;
}

function updateImageHint() {
    const hasSelectedFile = Boolean(ui.serviceImageFile.files && ui.serviceImageFile.files.length);
    const hasStoredImage = Boolean(state.currentFormImageUrl);

    if (hasSelectedFile) {
        ui.serviceImageHint.textContent = "Nova imagem selecionada para este serviço.";
        return;
    }

    if (hasStoredImage) {
        ui.serviceImageHint.textContent = "Nenhum novo arquivo selecionado. A imagem atual será mantida.";
        return;
    }

    ui.serviceImageHint.textContent = "Selecione uma imagem local para substituir o avatar.";
}

function readImageFileAsDataUrl(file) {
    return new Promise((resolve, reject) => {
        const reader = new FileReader();
        reader.onload = () => resolve(typeof reader.result === "string" ? reader.result : "");
        reader.onerror = () => reject(new Error("Falha ao ler a imagem selecionada."));
        reader.readAsDataURL(file);
    });
}

function openCreateModal() {
    ui.modalTitle.textContent = "Adicionar serviço";
    ui.editServiceId.value = "";
    ui.serviceName.value = "";
    ui.serviceKind.value = "service";
    ui.serviceHost.value = "";
    ui.serviceThreshold.value = "100";
    ui.snmpCommunity.value = "";
    ui.snmpPort.value = "161";
    updateSwitchFields();
    ui.serviceImageFile.value = "";
    state.currentFormImageUrl = "";
    updateImageHint();
    ui.addModal.style.display = "flex";
}

function openEditModal(serviceId) {
    const service = state.dashboard.services.find((item) => item.id === serviceId);
    if (!service) return;

    ui.modalTitle.textContent = "Editar serviço";
    ui.editServiceId.value = serviceId;
    ui.serviceName.value = service.name;
    ui.serviceKind.value = service.kind === "switch" ? "switch" : "service";
    ui.serviceHost.value = service.host;
    ui.serviceThreshold.value = service.threshold ?? 100;
    ui.snmpCommunity.value = "";
    ui.snmpPort.value = String(service.snmpPort || 161);
    updateSwitchFields();
    ui.serviceImageFile.value = "";
    state.currentFormImageUrl = service.imageUrl ?? "";
    updateImageHint();
    ui.addModal.style.display = "flex";
}

function updateSwitchFields() {
    const isSwitch = ui.serviceKind.value === "switch";
    ui.snmpCommunityField.hidden = !isSwitch;
    ui.snmpPortField.hidden = !isSwitch;
    ui.serviceHost.placeholder = isSwitch ? "Ex: 192.168.0.10" : "Ex: https://meuservico.com ou 192.168.0.1";
}

function closeFormModal() {
    ui.addModal.style.display = "none";
}

function renderNotificationRecipients() {
    if (!state.notificationSubscriptions.length) {
        ui.notificationRecipientList.innerHTML = `
            <span class="notification-recipient-empty">Nenhum destinatário adicionado.</span>
        `;
        return;
    }

    ui.notificationRecipientList.innerHTML = state.notificationSubscriptions
        .map((subscription, index) => {
            const selected = new Set(subscription.serviceIds);
            const allSelected = state.notificationServices.length > 0
                && selected.size === state.notificationServices.length;
            return `
            <article class="notification-subscription-card">
                <div class="notification-subscription-header">
                    <strong>${escapeHtml(subscription.email)}</strong>
                    <button
                        class="notification-remove-recipient"
                        type="button"
                        data-remove-subscription="${index}"
                        aria-label="Remover ${escapeHtml(subscription.email)}"
                    >Remover</button>
                </div>
                <label class="notification-toggle notification-toggle-compact">
                    <input
                        type="checkbox"
                        data-select-all-subscription="${index}"
                        ${allSelected ? "checked" : ""}
                    >
                    <span>Todas as aplicações</span>
                </label>
                <div class="notification-service-list">
                    ${state.notificationServices.map((service) => `
                        <label class="notification-service-option">
                            <input
                                type="checkbox"
                                value="${escapeHtml(service.id)}"
                                data-subscription-service="${index}"
                                ${selected.has(service.id) ? "checked" : ""}
                            >
                            <span>${escapeHtml(service.name)}</span>
                        </label>
                    `).join("")}
                </div>
            </article>
            `;
        })
        .join("");

    state.notificationSubscriptions.forEach((subscription, index) => {
        const selectAll = ui.notificationRecipientList.querySelector(
            `[data-select-all-subscription="${index}"]`
        );
        if (!selectAll) return;
        const selectedCount = subscription.serviceIds.length;
        selectAll.indeterminate =
            selectedCount > 0 && selectedCount < state.notificationServices.length;
    });
}

function addNotificationRecipient() {
    const recipient = ui.notificationRecipient.value.trim();
    if (!recipient) return true;

    if (!ui.notificationRecipient.checkValidity()) {
        ui.notificationRecipient.reportValidity();
        return false;
    }
    if (state.notificationSubscriptions.length >= 50) {
        showToast("É permitido adicionar no máximo 50 destinatários.");
        return false;
    }
    const alreadyAdded = state.notificationSubscriptions.some(
        (item) => item.email.toLowerCase() === recipient.toLowerCase()
    );
    if (alreadyAdded) {
        showToast("Esse destinatário já foi adicionado.");
        return false;
    }

    state.notificationSubscriptions.push({
        email: recipient,
        serviceIds: state.notificationServices.map((service) => service.id),
    });
    ui.notificationRecipient.value = "";
    renderNotificationRecipients();
    ui.notificationRecipient.focus();
    return true;
}

async function openNotificationModal() {
    ui.notificationModal.style.display = "flex";
    ui.notificationModal.setAttribute("aria-hidden", "false");
    ui.saveNotificationButton.disabled = true;
    ui.smtpStatus.textContent = "Verificando...";
    ui.smtpStatus.className = "smtp-status-neutral";
    ui.notificationThreshold.textContent = "";

    try {
        const [settings, services] = await Promise.all([
            requestJson("/api/rede/settings/notifications"),
            requestJson("/api/rede/services"),
        ]);
        state.notificationSettings = settings;
        ui.notificationEnabled.checked = Boolean(settings.enabled);
        state.notificationServices = services;
        const fallbackServiceIds = Array.isArray(settings.serviceIds)
            ? settings.serviceIds
            : services.map((service) => service.id);
        state.notificationSubscriptions = Array.isArray(settings.subscriptions)
            ? settings.subscriptions.map((subscription) => ({
                email: subscription.email,
                serviceIds: [...subscription.serviceIds],
            }))
            : (settings.recipients || (settings.recipient ? [settings.recipient] : []))
                .map((email) => ({ email, serviceIds: [...fallbackServiceIds] }));
        ui.notificationRecipient.value = "";
        renderNotificationRecipients();
        ui.smtpStatus.textContent = settings.smtpConfigured
            ? "SMTP configurado"
            : "SMTP não configurado";
        ui.smtpStatus.className = settings.smtpConfigured
            ? "smtp-status-success"
            : "smtp-status-error";
        ui.notificationThreshold.textContent =
            `O alerta será enviado após ${settings.outageThresholdMinutes} minutos offline.`;
        ui.saveNotificationButton.disabled = false;
        ui.notificationRecipient.focus();
    } catch (error) {
        ui.smtpStatus.textContent = "Falha ao consultar o servidor";
        ui.smtpStatus.className = "smtp-status-error";
        showToast(describeError(error, "Não foi possível carregar as configurações."));
    }
}

function closeNotificationModal() {
    ui.notificationModal.style.display = "none";
    ui.notificationModal.setAttribute("aria-hidden", "true");
    ui.notificationSettingsButton.focus();
}

async function saveNotificationSettings() {
    const enabled = ui.notificationEnabled.checked;
    if (ui.notificationRecipient.value.trim() && !addNotificationRecipient()) {
        return;
    }
    const subscriptions = state.notificationSubscriptions.map((subscription) => ({
        email: subscription.email,
        serviceIds: [...subscription.serviceIds],
    }));

    if (enabled && !subscriptions.length) {
        showToast("Informe pelo menos um e-mail destinatário.");
        ui.notificationRecipient.focus();
        return;
    }
    const subscriptionWithoutServices = subscriptions.find(
        (subscription) => !subscription.serviceIds.length
    );
    if (enabled && subscriptionWithoutServices) {
        showToast(`Selecione pelo menos uma aplicação para ${subscriptionWithoutServices.email}.`);
        return;
    }
    if (enabled && !state.notificationSettings?.smtpConfigured) {
        showToast("Configure o SMTP no servidor antes de ativar as notificações.");
        return;
    }

    ui.saveNotificationButton.disabled = true;
    ui.saveNotificationButton.textContent = "Salvando...";

    try {
        const settings = await requestJson("/api/rede/settings/notifications", {
            method: "PUT",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ enabled, subscriptions }),
        });
        state.notificationSettings = settings;
        showToast("Configurações de notificação atualizadas.", "success");
        closeNotificationModal();
    } catch (error) {
        showToast(describeError(error, "Não foi possível salvar as configurações."));
    } finally {
        ui.saveNotificationButton.disabled = false;
        ui.saveNotificationButton.textContent = "Salvar";
    }
}

async function saveService() {
    let imageUrl = state.currentFormImageUrl;
    const selectedFile = ui.serviceImageFile.files && ui.serviceImageFile.files[0];

    if (selectedFile) {
        imageUrl = await readImageFileAsDataUrl(selectedFile);
    }

    const payload = {
        name: ui.serviceName.value.trim(),
        kind: ui.serviceKind.value,
        host: ui.serviceHost.value.trim(),
        threshold: Number(ui.serviceThreshold.value),
        imageUrl,
    };
    if (payload.kind === "switch") {
        payload.snmpCommunity = ui.snmpCommunity.value.trim();
        payload.snmpPort = Number(ui.snmpPort.value);
        if (!ui.editServiceId.value && !payload.snmpCommunity) {
            showToast("Informe a community SNMP do switch.");
            return;
        }
    }

    if (!payload.name || !payload.host) {
        showToast("Preencha nome e host do serviço.");
        return;
    }

    const serviceId = ui.editServiceId.value;
    ui.saveServiceButton.disabled = true;

    try {
        await requestJson(serviceId ? `/api/rede/services/${serviceId}` : "/api/rede/services", {
            method: serviceId ? "PUT" : "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload),
        });

        closeFormModal();
        showToast(serviceId ? "Serviço atualizado." : "Serviço adicionado.", "success");
        await fetchDashboard();
    } catch (error) {
        console.error(error);
        showToast(describeError(error, "Não foi possível salvar o serviço."));
    } finally {
        ui.saveServiceButton.disabled = false;
    }
}

async function removeService(serviceId) {
    if (!confirm("Deseja remover este serviço do monitoramento?")) {
        return;
    }

    try {
        await requestJson(`/api/rede/services/${serviceId}`, { method: "DELETE" });
        showToast("Serviço removido.", "success");
        await fetchDashboard();
    } catch (error) {
        console.error(error);
        showToast(describeError(error, "Não foi possível remover o serviço."));
    }
}

function handleGridDragStart(event) {
    const card = event.target.closest(".service-card");
    if (!card || event.target.closest("button")) {
        event.preventDefault();
        return;
    }

    state.draggedServiceId = card.dataset.serviceId;
    state.dragStartOrder = getCurrentGridOrder();
    event.dataTransfer.effectAllowed = "move";
    event.dataTransfer.setData("text/plain", state.draggedServiceId);
    card.classList.add("is-dragging");
    ui.servicesGrid.classList.add("is-sorting");
}

function handleGridDragOver(event) {
    if (!state.draggedServiceId) {
        return;
    }

    event.preventDefault();

    const draggingCard = ui.servicesGrid.querySelector(".service-card.is-dragging");
    const targetCard = event.target.closest(".service-card");
    if (!draggingCard || !targetCard || draggingCard === targetCard) {
        return;
    }

    const targetRect = targetCard.getBoundingClientRect();
    const draggingRect = draggingCard.getBoundingClientRect();
    const sameRow = Math.abs(targetRect.top - draggingRect.top) < targetRect.height / 2;
    const insertAfter = sameRow
        ? event.clientX > targetRect.left + targetRect.width / 2
        : event.clientY > targetRect.top + targetRect.height / 2;

    if (insertAfter) {
        targetCard.insertAdjacentElement("afterend", draggingCard);
    } else {
        targetCard.insertAdjacentElement("beforebegin", draggingCard);
    }
}

function handleGridDrop(event) {
    if (state.draggedServiceId) {
        event.preventDefault();
    }
}

async function handleGridDragEnd(event) {
    const card = event.target.closest(".service-card");
    if (card) {
        card.classList.remove("is-dragging");
    }

    ui.servicesGrid.classList.remove("is-sorting");

    if (!state.draggedServiceId) {
        return;
    }

    const nextOrder = getCurrentGridOrder();
    const changed = nextOrder.join("|") !== state.dragStartOrder.join("|");
    state.draggedServiceId = null;
    state.dragStartOrder = [];

    if (!changed || state.savingOrder) {
        return;
    }

    state.suppressNextCardClick = true;
    await persistServiceOrder();
}

function handleServiceGridClick(event) {
    if (state.suppressNextCardClick) {
        state.suppressNextCardClick = false;
        return;
    }

    const editButton = event.target.closest('[data-action="edit-service"]');
    if (editButton) {
        event.stopPropagation();
        openEditModal(editButton.dataset.serviceId);
        return;
    }

    const removeButton = event.target.closest('[data-action="remove-service"]');
    if (removeButton) {
        event.stopPropagation();
        removeService(removeButton.dataset.serviceId);
        return;
    }

    const card = event.target.closest('[data-action="open-details"]');
    if (card) {
        openDetails(card.dataset.serviceId);
    }
}

function bindEvents() {
    ui.addServiceButton.addEventListener("click", openCreateModal);
    ui.serviceKind.addEventListener("change", updateSwitchFields);
    ui.notificationSettingsButton.addEventListener("click", openNotificationModal);
    ui.closeDetailsButton.addEventListener("click", closeDetails);
    ui.closeFormButton.addEventListener("click", closeFormModal);
    ui.cancelFormButton.addEventListener("click", closeFormModal);
    ui.saveServiceButton.addEventListener("click", saveService);
    ui.closeNotificationButton.addEventListener("click", closeNotificationModal);
    ui.cancelNotificationButton.addEventListener("click", closeNotificationModal);
    ui.saveNotificationButton.addEventListener("click", saveNotificationSettings);
    ui.addNotificationRecipientButton.addEventListener("click", addNotificationRecipient);
    ui.notificationRecipient.addEventListener("keydown", (event) => {
        if (event.key === "Enter") {
            event.preventDefault();
            addNotificationRecipient();
        }
    });
    ui.notificationRecipientList.addEventListener("click", (event) => {
        const removeButton = event.target.closest("[data-remove-subscription]");
        if (!removeButton) return;
        state.notificationSubscriptions.splice(
            Number(removeButton.dataset.removeSubscription),
            1
        );
        renderNotificationRecipients();
    });
    ui.notificationRecipientList.addEventListener("change", (event) => {
        const selectAll = event.target.closest("[data-select-all-subscription]");
        if (selectAll) {
            const subscription = state.notificationSubscriptions[
                Number(selectAll.dataset.selectAllSubscription)
            ];
            if (!subscription) return;
            subscription.serviceIds = selectAll.checked
                ? state.notificationServices.map((service) => service.id)
                : [];
            renderNotificationRecipients();
            return;
        }

        const serviceCheckbox = event.target.closest("[data-subscription-service]");
        if (!serviceCheckbox) return;
        const subscription = state.notificationSubscriptions[
            Number(serviceCheckbox.dataset.subscriptionService)
        ];
        if (!subscription) return;

        const selected = new Set(subscription.serviceIds);
        if (serviceCheckbox.checked) {
            selected.add(serviceCheckbox.value);
        } else {
            selected.delete(serviceCheckbox.value);
        }
        subscription.serviceIds = state.notificationServices
            .map((service) => service.id)
            .filter((serviceId) => selected.has(serviceId));
        renderNotificationRecipients();
    });
    ui.serviceImageFile.addEventListener("change", updateImageHint);
    ui.servicesGrid.addEventListener("click", handleServiceGridClick);
    ui.servicesGrid.addEventListener("dragstart", handleGridDragStart);
    ui.servicesGrid.addEventListener("dragover", handleGridDragOver);
    ui.servicesGrid.addEventListener("drop", handleGridDrop);
    ui.servicesGrid.addEventListener("dragend", handleGridDragEnd);

    ui.detailsModal.addEventListener("click", (event) => {
        if (event.target === ui.detailsModal) {
            closeDetails();
        }
    });

    ui.addModal.addEventListener("click", (event) => {
        if (event.target === ui.addModal) {
            closeFormModal();
        }
    });

    ui.notificationModal.addEventListener("click", (event) => {
        if (event.target === ui.notificationModal) {
            closeNotificationModal();
        }
    });
}

async function fetchDashboard() {
    state.dashboard = await requestJson("/api/rede/dashboard");
    state.countdown = state.dashboard.meta?.nextUpdateSeconds || 30;
    hideSystemBanner();
    renderHeroMeta();
    renderOverview();
    renderServices();
    await fetchAuditEvents();
}

function startRefreshLoop() {
    setInterval(async () => {
        state.countdown -= 1;
        if (state.countdown <= 0) {
            try {
                await fetchDashboard();
            } catch (error) {
                console.error(error);
                state.countdown = 5;
                showSystemBanner("Servidor indisponível", describeError(error, "Não foi possível atualizar os dados agora."));
            }
        }
        updateTimerLabel();
    }, 1000);
}

async function bootstrap() {
    bindEvents();
    startRefreshLoop();

    try {
        await fetchDashboard();
    } catch (error) {
        console.error(error);
        showSystemBanner("Servidor indisponível", describeError(error, "Não foi possível carregar o painel."));
        ui.overviewGrid.innerHTML = "";
        ui.servicesGrid.innerHTML = `
            <article class="empty-state panel empty-state-error">
                <span>Falha de conexão</span>
                <h3>Falha ao carregar o painel</h3>
                <p>Verifique se o servidor Python está ativo e tente novamente.</p>
            </article>
        `;
    }
}

bootstrap();
