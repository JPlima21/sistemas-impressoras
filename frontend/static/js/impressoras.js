function formatarTexto(valor, fallback = "N/A") {
    const texto = String(valor ?? "").trim();
    return texto || fallback;
}

function escaparHtml(valor) {
    return String(valor ?? "")
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#39;");
}

function formatarMoeda(valor) {
    return new Intl.NumberFormat("pt-BR", {
        style: "currency",
        currency: "BRL",
    }).format(Number(valor || 0));
}

function obterRotuloToken(tokenTipo) {
    if (tokenTipo === "colorida") {
        return "Colorida";
    }

    if (tokenTipo === "nenhum") {
        return "Sem token";
    }

    return "Preto e branco";
}

function formatarToken(impressora) {
    const tipo = obterRotuloToken(impressora.token_tipo);
    return `${tipo} (${formatarMoeda(impressora.token_valor)})`;
}

function atualizarResumo(impressoras) {
    const total = impressoras.length;
    const online = impressoras.filter((item) => item.online).length;
    const offline = total - online;

    const totalEl = document.getElementById("total-impressoras");
    const onlineEl = document.getElementById("total-online");
    const offlineEl = document.getElementById("total-offline");

    if (totalEl) totalEl.innerText = total;
    if (onlineEl) onlineEl.innerText = online;
    if (offlineEl) offlineEl.innerText = offline;
}

function renderizarListaImpressoras(impressoras) {
    const container = document.getElementById("lista-impressoras");

    if (!container) {
        return;
    }

    if (!impressoras.length) {
        container.innerHTML = `<p class="inventory-empty">Nenhuma impressora cadastrada.</p>`;
        return;
    }

    const cards = [...impressoras]
        .sort((a, b) => String(a.nome || a.id).localeCompare(String(b.nome || b.id), "pt-BR"))
        .map((impressora) => `
            <article class="inventory-card">
                <h3>${escaparHtml(formatarTexto(impressora.nome, impressora.id))}</h3>
                <div class="inventory-meta">
                    <span class="inventory-badge ${impressora.online ? "online" : "offline"}">
                        ${impressora.online ? "Online" : "Offline"}
                    </span>
                    <span class="inventory-badge">${escaparHtml(formatarTexto(impressora.id))}</span>
                </div>
                <div class="inventory-details">
                    <p><strong>IP:</strong> ${escaparHtml(formatarTexto(impressora.ip))}</p>
                    <p><strong>Community:</strong> Protegida</p>
                    <p><strong>Token:</strong> ${escaparHtml(formatarToken(impressora))}</p>
                    <p><strong>Modelo:</strong> ${escaparHtml(formatarTexto(impressora.modelo))}</p>
                    <p><strong>Localizacao:</strong> ${escaparHtml(formatarTexto(impressora.location))}</p>
                </div>
                <div class="inventory-actions">
                    <button type="button" class="button-danger" data-delete-printer="${escaparHtml(impressora.id)}">
                        Excluir
                    </button>
                </div>
            </article>
        `)
        .join("");

    container.innerHTML = cards;
}

function definirFeedback(mensagem, tipo = "") {
    const el = document.getElementById("form-feedback");

    if (!el) {
        return;
    }

    el.innerText = mensagem || "";
    el.className = "form-feedback";

    if (tipo) {
        el.classList.add(`is-${tipo}`);
    }
}

async function carregarImpressoras() {
    const resposta = await fetch("/api/impressoras");

    if (!resposta.ok) {
        throw new Error(`Nao foi possivel carregar impressoras. HTTP ${resposta.status}`);
    }

    const impressoras = await resposta.json();
    atualizarResumo(impressoras);
    renderizarListaImpressoras(impressoras);
    return impressoras;
}

async function salvarNovaImpressora(event) {
    event.preventDefault();

    const form = document.getElementById("form-impressora");
    const botao = document.getElementById("submit-impressora");

    if (!form || !botao) {
        return;
    }

    const formData = new FormData(form);
    const payload = {
        ip: String(formData.get("ip") || "").trim(),
        community: String(formData.get("community") || "").trim(),
        id: String(formData.get("id") || "").trim(),
        token_tipo: String(formData.get("token_tipo") || "pb").trim(),
    };

    definirFeedback("");
    botao.disabled = true;

    try {
        const resposta = await fetch("/api/impressoras", {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
            },
            body: JSON.stringify(payload),
        });
        const dados = await resposta.json();

        if (!resposta.ok) {
            throw new Error(dados.erro || "Nao foi possivel adicionar a impressora.");
        }

        form.reset();
        const tokenInput = document.getElementById("printer-token");
        if (tokenInput) {
            tokenInput.value = "pb";
        }

        definirFeedback(dados.mensagem || "Impressora adicionada com sucesso.", "success");
        await carregarImpressoras();
    } catch (error) {
        definirFeedback(error.message || "Erro ao adicionar a impressora.", "error");
    } finally {
        botao.disabled = false;
    }
}

async function excluirImpressora(impressoraId) {
    const nome = String(impressoraId || "").trim();
    if (!nome) {
        return;
    }

    const confirmou = window.confirm(`Deseja excluir a impressora "${nome}"?`);
    if (!confirmou) {
        return;
    }

    definirFeedback("");

    try {
        const resposta = await fetch(`/api/impressoras/${encodeURIComponent(nome)}/excluir`, {
            method: "POST",
        });
        const dados = await resposta.json().catch(() => ({}));

        if (!resposta.ok) {
            throw new Error(dados.erro || "Nao foi possivel excluir a impressora.");
        }

        definirFeedback(dados.mensagem || "Impressora excluida com sucesso.", "success");
        await carregarImpressoras();
    } catch (error) {
        definirFeedback(error.message || "Erro ao excluir a impressora.", "error");
    }
}

async function inicializarPagina() {
    try {
        await carregarImpressoras();
    } catch (error) {
        definirFeedback("Nao foi possivel carregar a lista de impressoras.", "error");
        renderizarListaImpressoras([]);
    }

    const form = document.getElementById("form-impressora");
    if (form && !form.dataset.bound) {
        form.addEventListener("submit", salvarNovaImpressora);
        form.dataset.bound = "true";
    }

    const lista = document.getElementById("lista-impressoras");
    if (lista && !lista.dataset.bound) {
        lista.addEventListener("click", (event) => {
            const botao = event.target.closest("[data-delete-printer]");
            if (!botao) {
                return;
            }

            excluirImpressora(botao.dataset.deletePrinter);
        });
        lista.dataset.bound = "true";
    }
}

inicializarPagina();
