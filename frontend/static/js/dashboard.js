function obterCaminhoApp(caminho) {
    const prefixo = window.location.pathname.startsWith("/print") ? "/print" : "";
    return `${prefixo}${caminho}`;
}

// Cria a estrutura HTML para uma coluna de impressora, usando o nome da impressora para gerar IDs unicos para os elementos
function criarColunaImpressora(nomeImpressora) {
    return `
        <div class="printer-column" data-printer-id="${nomeImpressora}">
            <div class="card printer-header-card">
                <div class="card-header">
                    <h2 class="printer-title">
                        <span class="printer-title-icon" aria-hidden="true">🖨️</span>
                        <span id="nome_${nomeImpressora}"></span>
                    </h2>
                    <div class="status offline" id="status_${nomeImpressora}">OFFLINE</div>
                </div>
                <details class="printer-image-dropdown">
                    <summary class="printer-image-dropdown-toggle">
                        <span class="printer-image-dropdown-title">Imagem e informacoes</span>
                        <span class="printer-image-dropdown-hint">ver detalhes</span>
                    </summary>
                    <div class="printer-image-layout">
                        <div class="printer-image">
                            <img id="imagem_${nomeImpressora}" src="${obterCaminhoApp("/assets/printers/oki")}" alt="Impressora">
                        </div>
                        <div class="printer-image-info">
                            <h3>Informacoes</h3>
                            <div class="info">
                                <p><strong>IP:</strong> <span id="ip_${nomeImpressora}"></span></p>
                                <p><strong>MAC:</strong> <span id="mac_${nomeImpressora}"></span></p>
                                <p><strong>N Serie:</strong> <span id="serial_${nomeImpressora}"></span></p>
                                <p><strong>Modelo:</strong> <span id="modelo_${nomeImpressora}"></span></p>
                                <p><strong>Asset Number:</strong> <span id="asset_number_${nomeImpressora}"></span></p>
                                <p><strong>Localizacao:</strong> <span id="location_${nomeImpressora}"></span></p>
                                <p><strong>Uptime:</strong> <span id="uptime_${nomeImpressora}"></span></p>
                            </div>
                        </div>
                    </div>
                </details>
            </div>

            <div class="printer-details-row">
                <div class="printer-info-stack">
                    <div class="card card-recursos">
                        <h3>Recursos</h3>
                        <div class="info recursos-layout">
                            <div class="recursos-grid">
                                <div class="recursos-coluna recursos-principais">
                                    <p class="recurso-item"><strong>Impressoes</strong> <span id="impressoes_${nomeImpressora}"></span></p>
                                    <p class="recurso-item"><strong>Copias</strong> <span id="copias_${nomeImpressora}"></span></p>
                                    <p class="recurso-item"><strong>Scanner</strong> <span id="scanner_${nomeImpressora}"></span></p>
                                    <p class="recurso-item"><strong>Total</strong> <span id="total_impressoes_${nomeImpressora}"></span></p>
                                </div>
                                <div class="recursos-coluna recursos-indices">
                                    <div class="indice-card indice-hoje">
                                        <span class="indice-label">Hoje</span>
                                        <strong class="indice-valor" id="impressoes_dia_${nomeImpressora}"></strong>
                                    </div>
                                    <div class="indice-card indice-mes">
                                        <span class="indice-label">Mes</span>
                                        <strong class="indice-valor" id="impressoes_mes_${nomeImpressora}"></strong>
                                    </div>
                                    <div class="indice-card indice-toner">
                                        <span class="indice-label">Toner</span>
                                        <strong class="indice-valor" id="toner_${nomeImpressora}"></strong>
                                    </div>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    `;
}

function obterImagemPorModelo(modelo) {
    const modeloNormalizado = String(modelo || "").toLowerCase();

    if (modeloNormalizado.includes("epson")) {
        return {
            src: obterCaminhoApp("/assets/printers/epson"),
            alt: "Impressora Epson",
        };
    }

    if (modeloNormalizado.includes("oki")) {
        return {
            src: obterCaminhoApp("/assets/printers/oki"),
            alt: "Impressora OKI",
        };
    }

    return {
        src: obterCaminhoApp("/assets/printers/oki"),
        alt: "Impressora",
    };
}

// Atualiza o status de uma impressora (online/offline) e ajusta a classe CSS para refletir a cor correta
function atualizarStatus(statusEl, online) {
    if (!statusEl) {
        return;
    }

    statusEl.innerText = online ? "ONLINE" : "OFFLINE";
    statusEl.className = online ? "status online" : "status offline";
}

function formatarNumeroPainel(valor) {
    if (valor === null || valor === undefined || valor === "") {
        return "N/A";
    }

    if (typeof valor === "number") {
        return new Intl.NumberFormat("pt-BR").format(valor);
    }

    const numero = Number(valor);
    if (!Number.isNaN(numero) && String(valor).trim() !== "") {
        return new Intl.NumberFormat("pt-BR").format(numero);
    }

    return valor;
}

function escaparHtml(valor) {
    return String(valor ?? "")
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;");
}

function extrairPercentualToner(valor) {
    if (valor === null || valor === undefined || valor === "") {
        return null;
    }

    const texto = String(valor).replace(",", ".").trim();
    const match = texto.match(/-?\d+(\.\d+)?/);

    if (!match) {
        return null;
    }

    const percentual = Number(match[0]);
    return Number.isFinite(percentual) ? percentual : null;
}

function obterClasseNivelToner(percentual) {
    if (percentual === null) {
        return "toner-desconhecido";
    }

    if (percentual <= 10) {
        return "toner-critico";
    }

    if (percentual <= 25) {
        return "toner-baixo";
    }

    if (percentual <= 50) {
        return "toner-atencao";
    }

    return "toner-ok";
}

function obterMetaAlertaToner(percentual) {
    if (percentual === null) {
        return {
            classe: "toner-desconhecido",
            rotulo: "Sem leitura",
            prioridade: 4,
        };
    }

    if (percentual <= 10) {
        return {
            classe: "toner-critico",
            rotulo: "Critico",
            prioridade: 1,
        };
    }

    if (percentual <= 25) {
        return {
            classe: "toner-baixo",
            rotulo: "Baixo",
            prioridade: 2,
        };
    }

    if (percentual <= 50) {
        return {
            classe: "toner-atencao",
            rotulo: "Atencao",
            prioridade: 3,
        };
    }

    return {
        classe: "toner-ok",
        rotulo: "Normal",
        prioridade: 5,
    };
}

function obterAlertasToner(impressoras) {
    return Object.entries(impressoras)
        .map(([nomeImpressora, dados]) => {
            const percentual = extrairPercentualToner(dados.toner);
            const meta = obterMetaAlertaToner(percentual);
            const tonerTexto = dados.toner === null || dados.toner === undefined || dados.toner === ""
                ? "N/A"
                : String(dados.toner);

            return {
                id: nomeImpressora,
                nome: formatarTituloImpressora(dados.nome || nomeImpressora),
                toner: tonerTexto,
                percentual,
                online: Boolean(dados.online),
                ...meta,
            };
        })
        .filter((alerta) => alerta.classe !== "toner-ok")
        .sort((a, b) => {
            if (a.prioridade !== b.prioridade) {
                return a.prioridade - b.prioridade;
            }

            const percentualA = a.percentual === null ? Number.POSITIVE_INFINITY : a.percentual;
            const percentualB = b.percentual === null ? Number.POSITIVE_INFINITY : b.percentual;

            if (percentualA !== percentualB) {
                return percentualA - percentualB;
            }

            return a.nome.localeCompare(b.nome, "pt-BR");
        });
}

function atualizarAlertasToner(impressoras) {
    const totalEl = document.getElementById("total-alertas-toner");
    const resumoEl = document.getElementById("resumo-alertas-toner");
    const listaEl = document.getElementById("lista-alertas-toner");

    if (!totalEl || !resumoEl || !listaEl) {
        return;
    }

    const alertas = obterAlertasToner(impressoras);
    const criticos = alertas.filter((alerta) => alerta.classe === "toner-critico").length;
    const baixos = alertas.filter((alerta) => alerta.classe === "toner-baixo").length;
    const atencao = alertas.filter((alerta) => alerta.classe === "toner-atencao").length;
    const semLeitura = alertas.filter((alerta) => alerta.classe === "toner-desconhecido").length;

    totalEl.innerText = alertas.length;
    resumoEl.innerText = alertas.length
        ? `${criticos} critico(s) | ${baixos} baixo(s) | ${atencao} atencao | ${semLeitura} sem leitura`
        : "Todos os niveis de toner estao normais.";

    if (!alertas.length) {
        listaEl.innerHTML = `<p class="toner-alert-empty">Nenhum alerta de toner ativo.</p>`;
        return;
    }

    listaEl.innerHTML = alertas
        .map((alerta) => `
            <div class="toner-alert-item ${alerta.classe}">
                <div class="toner-alert-printer">
                    <strong>${escaparHtml(alerta.nome)}</strong>
                    <span>${alerta.online ? "Online" : "Offline"}</span>
                </div>
                <span class="toner-alert-badge">${escaparHtml(alerta.rotulo)}</span>
                <strong class="toner-alert-value">${escaparHtml(alerta.toner)}</strong>
            </div>
        `)
        .join("");
}

function atualizarIndicadorToner(tonerEl, valor) {
    if (!tonerEl) {
        return;
    }

    const card = tonerEl.closest(".indice-toner");
    const percentual = extrairPercentualToner(valor);
    const texto = valor === null || valor === undefined || valor === "" ? "N/A" : String(valor);

    tonerEl.innerText = texto;

    if (!card) {
        return;
    }

    card.classList.remove(
        "toner-ok",
        "toner-atencao",
        "toner-baixo",
        "toner-critico",
        "toner-desconhecido",
    );
    card.classList.add(obterClasseNivelToner(percentual));
    card.title = percentual === null ? "Nivel de toner indisponivel" : `Nivel de toner: ${texto}`;
}

function formatarTituloImpressora(valor, fallback = "Impressora") {
    const texto = String(valor ?? "").trim();
    if (!texto) {
        return fallback;
    }

    const match = texto.match(/^impressora\s*(.+)$/i);
    if (match && match[1]) {
        return `Impressora ${match[1].trim()}`;
    }

    return texto;
}

// Preenche os campos de uma impressora especifica, usando "N/A" como fallback para dados ausentes
function preencherCampos(nomeImpressora, dataImpressora) {
    const elements = {
        imagem: document.getElementById(`imagem_${nomeImpressora}`),
        nome: document.getElementById(`nome_${nomeImpressora}`),
        ip: document.getElementById(`ip_${nomeImpressora}`),
        mac: document.getElementById(`mac_${nomeImpressora}`),
        serial: document.getElementById(`serial_${nomeImpressora}`),
        modelo: document.getElementById(`modelo_${nomeImpressora}`),
        asset_number: document.getElementById(`asset_number_${nomeImpressora}`),
        location: document.getElementById(`location_${nomeImpressora}`),
        uptime: document.getElementById(`uptime_${nomeImpressora}`),
        total_impressoes: document.getElementById(`total_impressoes_${nomeImpressora}`),
        impressoes: document.getElementById(`impressoes_${nomeImpressora}`),
        copias: document.getElementById(`copias_${nomeImpressora}`),
        impressoes_dia: document.getElementById(`impressoes_dia_${nomeImpressora}`),
        impressoes_mes: document.getElementById(`impressoes_mes_${nomeImpressora}`),
        toner: document.getElementById(`toner_${nomeImpressora}`),
        scanner: document.getElementById(`scanner_${nomeImpressora}`),
    };

    if (elements.nome) {
        elements.nome.innerText = formatarTituloImpressora(
            dataImpressora.nome || nomeImpressora,
        );
    }
    if (elements.imagem) {
        const imagem = obterImagemPorModelo(dataImpressora.modelo);
        elements.imagem.src = imagem.src;
        elements.imagem.alt = imagem.alt;
    }
    if (elements.ip) elements.ip.innerText = dataImpressora.ip || "N/A";
    if (elements.mac) elements.mac.innerText = dataImpressora.mac || "N/A";
    if (elements.serial) elements.serial.innerText = dataImpressora.num_serie || "N/A";
    if (elements.modelo) elements.modelo.innerText = dataImpressora.modelo || "N/A";
    if (elements.asset_number) elements.asset_number.innerText = dataImpressora.asset_number || "N/A";
    if (elements.location) elements.location.innerText = dataImpressora.location || "N/A";
    if (elements.uptime) elements.uptime.innerText = dataImpressora.uptime || "N/A";
    if (elements.total_impressoes) elements.total_impressoes.innerText = formatarNumeroPainel(dataImpressora.total_impressoes);
    if (elements.impressoes) elements.impressoes.innerText = formatarNumeroPainel(dataImpressora.impressoes);
    if (elements.copias) elements.copias.innerText = formatarNumeroPainel(dataImpressora.copias);
    if (elements.impressoes_dia) elements.impressoes_dia.innerText = formatarNumeroPainel(dataImpressora.impressoes_dia);
    if (elements.impressoes_mes) elements.impressoes_mes.innerText = formatarNumeroPainel(dataImpressora.impressoes_mes);
    atualizarIndicadorToner(elements.toner, dataImpressora.toner);
    if (elements.scanner) elements.scanner.innerText = dataImpressora.scanner || "N/A";
}

function atualizarResumo(impressoras) {
    const listaImpressoras = Object.values(impressoras);
    const total = listaImpressoras.length;
    const online = listaImpressoras.filter((dados) => Boolean(dados.online)).length;
    const offline = total - online;

    const totalEl = document.getElementById("total-impressoras");
    const onlineEl = document.getElementById("total-online");
    const offlineEl = document.getElementById("total-offline");

    if (totalEl) totalEl.innerText = total;
    if (onlineEl) onlineEl.innerText = online;
    if (offlineEl) offlineEl.innerText = offline;
}

function ordenarImpressoras(impressoras) {
    return Object.entries(impressoras)
        .sort(([, dadosA], [, dadosB]) => Number(Boolean(dadosB.online)) - Number(Boolean(dadosA.online)))
        .map(([nomeImpressora]) => nomeImpressora);
}

// Mantem o container sincronizado com as impressoras e coloca as online primeiro
function sincronizarContainer(container, impressoras) {
    if (!container.dataset.initialized) {
        container.innerHTML = "";
        container.dataset.initialized = "true";
    }

    const nomesOrdenados = ordenarImpressoras(impressoras);
    const nomesAtuais = new Set(Object.keys(impressoras));

    for (const coluna of container.querySelectorAll(".printer-column")) {
        if (!nomesAtuais.has(coluna.dataset.printerId)) {
            coluna.remove();
        }
    }

    for (const nomeImpressora of nomesOrdenados) {
        let coluna = container.querySelector(`[data-printer-id="${nomeImpressora}"]`);

        if (!coluna) {
            container.insertAdjacentHTML("beforeend", criarColunaImpressora(nomeImpressora));
            coluna = container.querySelector(`[data-printer-id="${nomeImpressora}"]`);
        }

        container.appendChild(coluna);
    }
}

// Funcao principal para atualizar os dados das impressoras
async function atualizar() {
    try {
        const res = await fetch("/api");
        const data = await res.json();
        const impressoras = data.impressoras || {};
        const container = document.getElementById("content-container");

        atualizarResumo(impressoras);
        atualizarAlertasToner(impressoras);
        sincronizarContainer(container, impressoras);

        for (const [nomeImpressora, dataImpressora] of Object.entries(impressoras)) {
            const statusEl = document.getElementById(`status_${nomeImpressora}`);
            atualizarStatus(statusEl, dataImpressora.online);
            preencherCampos(nomeImpressora, dataImpressora);
        }
    } catch (error) {
        console.error("Erro ao buscar dados:", error);
    }
}

// Atualiza a cada 10 segundos
setInterval(atualizar, 10000);
atualizar();
