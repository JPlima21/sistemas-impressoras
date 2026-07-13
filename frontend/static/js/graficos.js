const SVG_NS = "http://www.w3.org/2000/svg";
const chartColorPalette = [
    "#38bdf8",
    "#34d399",
    "#f59e0b",
    "#f87171",
    "#a78bfa",
    "#fb7185",
    "#22c55e",
    "#60a5fa",
    "#f97316",
    "#14b8a6",
];
const graficosState = {
    impressoras: [],
    historico: [],
    historicoDiario: new Map(),
    historicoDiarioCompleto: new Map(),
    historicoMensal: new Map(),
    impressoesUsuarios: [],
    eventosImpressoesUsuarios: [],
    impressoesUsuariosPorMes: new Map(),
    usuarioDetalhesAtual: "",
    eventosDetalhesUsuario: [],
    impressoraDetalhesAtual: null,
    usuariosDetalhesImpressora: [],
    dadosDetalhesImpressora: {},
    periodoDetalhesImpressora: { inicio: "", fim: "" },
    periodoDetalhesUsuario: { inicio: "", fim: "" },
    periodoLinhaHistorico: "dia",
    datasSalvamentoPorData: new Map(),
    rotulosImpressoras: new Map(),
    abaAtiva: "painel-grafico-dia",
};
let resizeTimeoutId = null;

function formatarNumero(valor) {
    return new Intl.NumberFormat("pt-BR").format(Number(valor || 0));
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

function obterSiglaToken(tokenTipo) {
    if (tokenTipo === "colorida") {
        return "Color";
    }

    if (tokenTipo === "nenhum") {
        return "Sem token";
    }

    return "P_B";
}

function obterValorPadraoToken(tokenTipo) {
    if (tokenTipo === "colorida") {
        return 0.5;
    }

    if (tokenTipo === "nenhum") {
        return 0;
    }

    return 0.04;
}

function obterDataAtualIso() {
    const agora = new Date();
    const ano = String(agora.getFullYear());
    const mes = String(agora.getMonth() + 1).padStart(2, "0");
    const dia = String(agora.getDate()).padStart(2, "0");
    return `${ano}-${mes}-${dia}`;
}

function obterMesAtualIso() {
    return obterDataAtualIso().slice(0, 7);
}

function formatarDataIso(valor) {
    const [ano, mes, dia] = String(valor || "").split("-");

    if (!ano || !mes || !dia) {
        return String(valor || "");
    }

    return `${dia}/${mes}/${ano}`;
}

function formatarDataFiltroHistorico(valor) {
    const dataFormatada = formatarDataIso(valor);
    const datasSalvamento = graficosState.datasSalvamentoPorData.get(valor) || [];

    if (!datasSalvamento.length || datasSalvamento.includes(valor)) {
        return dataFormatada;
    }

    return `${dataFormatada} (salvo em ${datasSalvamento.map(formatarDataIso).join(", ")})`;
}

function formatarMesIso(valor) {
    const [ano, mes] = String(valor || "").split("-");

    if (!ano || !mes) {
        return String(valor || "");
    }

    return new Intl.DateTimeFormat("pt-BR", {
        month: "long",
        year: "numeric",
    }).format(new Date(Number(ano), Number(mes) - 1, 1));
}


function normalizarDataIso(valor) {
    if (!valor) {
        return "";
    }

    const texto = String(valor).trim();
    const isoMatch = texto.match(/(\d{4})-(\d{2})-(\d{2})/);

    if (isoMatch) {
        return `${isoMatch[1]}-${isoMatch[2]}-${isoMatch[3]}`;
    }

    const brMatch = texto.match(/(\d{2})\/(\d{2})\/(\d{4})/);

    if (brMatch) {
        return `${brMatch[3]}-${brMatch[2]}-${brMatch[1]}`;
    }

    const data = new Date(texto);

    if (!Number.isNaN(data.getTime())) {
        const ano = String(data.getUTCFullYear());
        const mes = String(data.getUTCMonth() + 1).padStart(2, "0");
        const dia = String(data.getUTCDate()).padStart(2, "0");
        return `${ano}-${mes}-${dia}`;
    }

    return "";
}

function escaparHtml(valor) {
    return String(valor ?? "")
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;");
}

function normalizarTextoBusca(valor) {
    return String(valor || "")
        .trim()
        .toLocaleLowerCase("pt-BR")
        .normalize("NFD")
        .replace(/[\u0300-\u036f]/g, "");
}

function normalizarListaApi(payload, chaveObjeto = "") {
    if (Array.isArray(payload)) {
        return payload;
    }

    if (payload && Array.isArray(payload[chaveObjeto])) {
        return payload[chaveObjeto];
    }

    if (payload && chaveObjeto && payload[chaveObjeto] && typeof payload[chaveObjeto] === "object") {
        return normalizarListaApi(payload[chaveObjeto]);
    }

    if (payload && typeof payload === "object") {
        return Object.entries(payload).map(([id, dados]) => ({
            id,
            ...(dados && typeof dados === "object" ? dados : {}),
        }));
    }

    return [];
}

function normalizarImpressora(item) {
    const id = obterIdentificadorImpressora(item);
    const nome = obterRotuloImpressora(item) || id || "Impressora";

    return {
        ...item,
        id,
        nome,
        online: Boolean(item?.online),
        total_impressoes: Number(item?.total_impressoes || 0),
        impressoes_dia: Number(item?.impressoes_dia || 0),
        impressoes_mes: Number(item?.impressoes_mes || 0),
        token_tipo: item?.token_tipo || "pb",
        token_valor: Number(item?.token_valor ?? obterValorPadraoToken(item?.token_tipo)),
    };
}

function normalizarHistorico(registros) {
    return registros
        .map((registro) => ({
            ...registro,
            impressora: String(registro?.impressora || registro?.id || "").trim(),
            impressora_nome: obterRotuloImpressora(registro),
            data: normalizarDataIso(registro?.data),
            data_salvamento: normalizarDataIso(registro?.data_salvamento || registro?.timestamp_salvo),
            impressoes_total_dia: Number(
                registro?.impressoes_total_dia || registro?.impressoes_total || 0,
            ),
            motivo: registro?.motivo || "",
            timestamp_salvo: registro?.timestamp_salvo || "",
        }))
        .filter((registro) => registro.impressora && registro.data);
}

function normalizarResumoUsuario(registro) {
    return {
        usuario: String(registro?.usuario || "").trim(),
        nome: String(registro?.usuario || "").trim(),
        total_paginas: Number(registro?.total_paginas || 0),
        total_trabalhos: Number(registro?.total_trabalhos || 0),
        primeira_impressao: registro?.primeira_impressao || "",
        ultima_impressao: registro?.ultima_impressao || "",
    };
}

function normalizarImpressaoUsuario(registro) {
    return {
        servidor: String(registro?.servidor || "").trim(),
        record_id: registro?.record_id || "",
        event_id: registro?.event_id || "",
        data_hora: registro?.data_hora || "",
        usuario: String(registro?.usuario || "").trim(),
        impressora: String(registro?.impressora || "").trim(),
        documento: String(registro?.documento || "").trim(),
        paginas: Number(registro?.paginas || 0),
        computador: String(registro?.computador || "").trim(),
        job_id: String(registro?.job_id || "").trim(),
        porta: String(registro?.porta || "").trim(),
        tamanho_bytes: registro?.tamanho_bytes || "",
    };
}

async function buscarJson(url) {
    const response = await fetch(url);

    if (!response.ok) {
        throw new Error(`${url} retornou HTTP ${response.status}`);
    }

    return response.json();
}

async function buscarJsonComFallback(urls) {
    const erros = [];

    for (const url of urls) {
        try {
            return await buscarJson(url);
        } catch (error) {
            erros.push(error.message);
        }
    }

    throw new Error(erros.join(" | "));
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

function obterIdentificadorImpressora(item) {
    return String(item?.id || item?.impressora || item?.nome || "").trim();
}

function obterRotuloImpressora(item) {
    return String(item?.impressora_nome || item?.nome || item?.id || item?.impressora || "").trim();
}

function construirMapaRotulosImpressoras(impressoras, historico) {
    const rotulos = new Map();

    historico.forEach((registro) => {
        const id = obterIdentificadorImpressora(registro);
        const rotulo = obterRotuloImpressora(registro);

        if (id) {
            rotulos.set(id, rotulo || id);
        }
    });

    impressoras.forEach((item) => {
        const id = obterIdentificadorImpressora(item);
        const rotulo = obterRotuloImpressora(item);

        if (id) {
            rotulos.set(id, rotulo || id);
        }
    });

    return rotulos;
}

function ordenarItensGraficoPorValor(itens, campoValor) {
    return [...itens].sort((a, b) => {
        const diferencaValor = Number(b[campoValor] || 0) - Number(a[campoValor] || 0);

        if (diferencaValor !== 0) {
            return diferencaValor;
        }

        return String(a.nome || a.id).localeCompare(String(b.nome || b.id), "pt-BR");
    });
}

function criarSvgBase(host, alturaMinima = 360, larguraMinima = 720) {
    host.innerHTML = "";
    const largura = Math.max(host.clientWidth || larguraMinima, larguraMinima);
    const altura = alturaMinima;
    const svg = document.createElementNS(SVG_NS, "svg");
    svg.setAttribute("viewBox", `0 0 ${largura} ${altura}`);
    svg.setAttribute("class", "svg-chart");
    svg.setAttribute("preserveAspectRatio", "xMidYMid meet");
    host.appendChild(svg);
    return { svg, largura, altura };
}

function adicionarTextoSvg(svg, x, y, texto, className, anchor = "middle") {
    const el = document.createElementNS(SVG_NS, "text");
    el.setAttribute("x", x);
    el.setAttribute("y", y);
    el.setAttribute("text-anchor", anchor);
    el.setAttribute("class", className);
    el.textContent = texto;
    svg.appendChild(el);
    return el;
}

function adicionarTituloTooltip(elemento, texto) {
    const title = document.createElementNS(SVG_NS, "title");
    title.textContent = texto;
    elemento.appendChild(title);
}

function vincularAcaoItemSvg(elemento, item, opcoes = {}) {
    if (typeof opcoes.onItemClick !== "function") {
        return;
    }

    elemento.classList.add("svg-bar-clickable");
    elemento.setAttribute("role", "button");
    elemento.setAttribute("tabindex", "0");
    elemento.setAttribute("aria-label", `Ver jobs de ${item.nome || item.usuario || item.id}`);
    elemento.addEventListener("click", () => opcoes.onItemClick(item));
    elemento.addEventListener("keydown", (event) => {
        if (event.key === "Enter" || event.key === " ") {
            event.preventDefault();
            opcoes.onItemClick(item);
        }
    });
}

function desenharGradeY(svg, area, maxValue, steps = 5) {
    const safeMax = Math.max(maxValue, 1);

    for (let i = 0; i <= steps; i += 1) {
        const ratio = i / steps;
        const y = area.y + area.height - ratio * area.height;
        const valor = Math.round(safeMax * ratio);

        const linha = document.createElementNS(SVG_NS, "line");
        linha.setAttribute("x1", area.x);
        linha.setAttribute("x2", area.x + area.width);
        linha.setAttribute("y1", y);
        linha.setAttribute("y2", y);
        linha.setAttribute("class", "svg-grid-line");
        svg.appendChild(linha);

        adicionarTextoSvg(svg, area.x - 10, y + 4, formatarNumero(valor), "svg-axis-label", "end");
    }
}

function renderizarGraficoColunas(hostId, tituloVazio, itens, campoValor, corPrimaria, opcoes = {}) {
    const host = document.getElementById(hostId);

    if (!host) {
        return;
    }

    if (!itens.length) {
        host.innerHTML = `<p class="chart-loading">${tituloVazio}</p>`;
        return;
    }

    const dados = ordenarItensGraficoPorValor(itens, campoValor);
    const larguraMinima = Math.max(760, dados.length * 108);
    const { svg, largura, altura } = criarSvgBase(host, 460, larguraMinima);
    const area = { x: 72, y: 24, width: largura - 96, height: 250 };
    const maxValue = Math.max(...dados.map((item) => Number(item[campoValor] || 0)), 0);
    const passo = area.width / dados.length;
    const larguraBarra = Math.min(42, passo * 0.55);

    desenharGradeY(svg, area, maxValue, 5);

    const eixoX = document.createElementNS(SVG_NS, "line");
    eixoX.setAttribute("x1", area.x);
    eixoX.setAttribute("x2", area.x + area.width);
    eixoX.setAttribute("y1", area.y + area.height);
    eixoX.setAttribute("y2", area.y + area.height);
    eixoX.setAttribute("class", "svg-axis-line");
    svg.appendChild(eixoX);

    dados.forEach((item, index) => {
        const valor = Number(item[campoValor] || 0);
        const xCentro = area.x + passo * index + passo / 2;
        const alturaBarra = maxValue > 0 ? (valor / maxValue) * area.height : 0;
        const yBarra = area.y + area.height - alturaBarra;
        const fill = item.online === false ? "#64748b" : corPrimaria;

        const rect = document.createElementNS(SVG_NS, "rect");
        rect.setAttribute("x", xCentro - larguraBarra / 2);
        rect.setAttribute("y", yBarra);
        rect.setAttribute("width", larguraBarra);
        rect.setAttribute("height", Math.max(alturaBarra, 2));
        rect.setAttribute("rx", "10");
        rect.setAttribute("class", "svg-bar");
        rect.setAttribute("fill", fill);
        const valorToken = calcularValorToken(item, campoValor);
        const tokenRotulo = obterRotuloToken(item.token_tipo);
        const textoTooltip = opcoes.mostrarToken === false
            ? `${item.nome}: ${formatarNumero(valor)} paginas | Trabalhos: ${formatarNumero(item.total_trabalhos || 0)}`
            : `${item.nome}: ${formatarNumero(valor)} impressoes | ${tokenRotulo} ${formatarMoeda(item.token_valor)} | Total ${formatarMoeda(valorToken)}`;
        adicionarTituloTooltip(rect, textoTooltip);
        vincularAcaoItemSvg(rect, item, opcoes);
        svg.appendChild(rect);

        const yLabel = Math.max(yBarra - 22, 16);
        adicionarTextoSvg(
            svg,
            xCentro,
            yLabel,
            formatarNumero(valor),
            "svg-value-label",
        );

        if (opcoes.mostrarToken !== false) {
            adicionarTextoSvg(
                svg,
                xCentro,
                yLabel + 14,
                formatarMoeda(valorToken),
                "svg-token-label",
            );
        }

        const labelX = adicionarTextoSvg(
            svg,
            xCentro,
            area.y + area.height + 34,
            item.nome,
            "svg-axis-label svg-axis-label-x",
            "end",
        );
        labelX.setAttribute("transform", `rotate(-45 ${xCentro} ${area.y + area.height + 34})`);
        if (typeof opcoes.onItemClick === "function") {
            labelX.classList.add("svg-label-clickable");
        }
        adicionarTituloTooltip(labelX, item.nome);
        vincularAcaoItemSvg(labelX, item, opcoes);
    });
}

function construirMapaHistoricoDiario(registros) {
    const mapa = new Map();

    registros.forEach((registro) => {
        const data = String(registro.data || "").slice(0, 10);
        const impressora = String(registro.impressora || "").trim();
        const valor = Number(registro.impressoes_total_dia || 0);

        if (!data || !impressora) {
            return;
        }

        if (!mapa.has(data)) {
            mapa.set(data, new Map());
        }

        const valorAtual = mapa.get(data).get(impressora) ?? 0;
        mapa.get(data).set(impressora, Math.max(valorAtual, valor));
    });

    return mapa;
}

function construirMapaDatasSalvamentoPorData(registros) {
    const mapa = new Map();

    registros.forEach((registro) => {
        if (!registro.data || !registro.data_salvamento) {
            return;
        }

        if (!mapa.has(registro.data)) {
            mapa.set(registro.data, new Set());
        }

        mapa.get(registro.data).add(registro.data_salvamento);
    });

    return new Map(
        [...mapa.entries()].map(([data, datasSalvamento]) => [
            data,
            [...datasSalvamento].sort().reverse(),
        ]),
    );
}

function construirMapaHistoricoDiarioCompleto(mapaHistoricoDiario, impressoras) {
    const mapaCompleto = new Map(
        [...mapaHistoricoDiario.entries()].map(([data, valoresDia]) => [data, new Map(valoresDia)]),
    );
    const dataAtual = obterDataAtualIso();
    const valoresHoje = new Map(mapaCompleto.get(dataAtual) || []);
    const todasImpressoras = new Set();

    mapaCompleto.forEach((valoresDia) => {
        [...valoresDia.keys()].forEach((impressoraId) => {
            if (impressoraId) {
                todasImpressoras.add(impressoraId);
            }
        });
    });

    impressoras.forEach((item) => {
        const impressoraId = obterIdentificadorImpressora(item);

        if (!impressoraId) {
            return;
        }

        todasImpressoras.add(impressoraId);
        valoresHoje.set(impressoraId, Number(item.impressoes_dia || 0));
    });

    if (valoresHoje.size) {
        mapaCompleto.set(dataAtual, valoresHoje);
    }

    [...mapaCompleto.entries()].forEach(([data, valoresDia]) => {
        const valoresNormalizados = new Map(valoresDia);

        todasImpressoras.forEach((impressoraId) => {
            if (!valoresNormalizados.has(impressoraId)) {
                valoresNormalizados.set(impressoraId, 0);
            }
        });

        mapaCompleto.set(data, valoresNormalizados);
    });

    return mapaCompleto;
}

function construirMapaHistoricoMensal(mapaHistoricoDiario) {
    const mapaMensal = new Map();

    [...mapaHistoricoDiario.entries()].forEach(([data, valoresDia]) => {
        const mes = String(data).slice(0, 7);

        if (!mes) {
            return;
        }

        if (!mapaMensal.has(mes)) {
            mapaMensal.set(mes, new Map());
        }

        [...valoresDia.entries()].forEach(([impressora, valor]) => {
            const acumulado = mapaMensal.get(mes).get(impressora) ?? 0;
            mapaMensal.get(mes).set(impressora, acumulado + Number(valor || 0));
        });
    });

    return mapaMensal;
}

function construirResumoUsuariosPorMes(eventos) {
    const mapaMensal = new Map();

    eventos.forEach((evento) => {
        const usuario = String(evento?.usuario || "").trim();
        const data = normalizarDataIso(evento?.data_hora);
        const mes = data.slice(0, 7);

        if (!usuario || !mes) {
            return;
        }

        if (!mapaMensal.has(mes)) {
            mapaMensal.set(mes, new Map());
        }

        const resumoAtual = mapaMensal.get(mes).get(usuario) || {
            usuario,
            nome: usuario,
            total_paginas: 0,
            total_trabalhos: 0,
        };

        resumoAtual.total_paginas += Number(evento?.paginas || 0);
        resumoAtual.total_trabalhos += 1;
        mapaMensal.get(mes).set(usuario, resumoAtual);
    });

    return new Map(
        [...mapaMensal.entries()].map(([mes, usuarios]) => [mes, [...usuarios.values()]]),
    );
}

function obterHoraEvento(dataHora) {
    const match = String(dataHora || "").match(/\d{4}-\d{2}-\d{2}[ T](\d{2})/);

    return match ? `${match[1]}:00` : "";
}

function obterDiasMes(mesReferencia) {
    const [ano, mes] = String(mesReferencia || "").split("-").map(Number);

    if (!ano || !mes) {
        return [];
    }

    const totalDias = new Date(ano, mes, 0).getDate();
    return Array.from({ length: totalDias }, (_, indice) => (
        `${mesReferencia}-${String(indice + 1).padStart(2, "0")}`
    ));
}

function obterDatasEventosImpressoes(eventos) {
    return [...new Set(
        eventos
            .map((evento) => normalizarDataIso(evento.data_hora))
            .filter(Boolean),
    )].sort().reverse();
}

function obterMesesEventosImpressoes(eventos) {
    return [...new Set(
        eventos
            .map((evento) => normalizarDataIso(evento.data_hora).slice(0, 7))
            .filter(Boolean),
    )].sort().reverse();
}

function construirLinhaEventosDia(eventos, dataSelecionada) {
    const horas = Array.from({ length: 24 }, (_, indice) => `${String(indice).padStart(2, "0")}:00`);
    const incrementosPorHora = new Map(horas.map((hora) => [hora, new Map()]));
    const impressoras = new Set();

    eventos.forEach((evento) => {
        const data = normalizarDataIso(evento.data_hora);
        const hora = obterHoraEvento(evento.data_hora);
        const impressora = String(evento.impressora || "").trim();

        if (data !== dataSelecionada || !hora || !impressora || !incrementosPorHora.has(hora)) {
            return;
        }

        impressoras.add(impressora);
        const valorAtual = incrementosPorHora.get(hora).get(impressora) || 0;
        incrementosPorHora.get(hora).set(impressora, valorAtual + Number(evento.paginas || 0));
    });

    if (!impressoras.size) {
        return new Map();
    }

    const acumulado = new Map();
    return new Map(horas.map((hora) => {
        const valoresHora = new Map();
        const incrementos = incrementosPorHora.get(hora) || new Map();

        impressoras.forEach((impressora) => {
            const total = (acumulado.get(impressora) || 0) + Number(incrementos.get(impressora) || 0);
            acumulado.set(impressora, total);
            valoresHora.set(impressora, total);
        });

        return [hora, valoresHora];
    }));
}

function construirLinhaEventosMes(eventos, mesSelecionado) {
    const dias = obterDiasMes(mesSelecionado);
    const incrementosPorDia = new Map(dias.map((dia) => [dia, new Map()]));
    const impressoras = new Set();

    eventos.forEach((evento) => {
        const data = normalizarDataIso(evento.data_hora);
        const impressora = String(evento.impressora || "").trim();

        if (!data.startsWith(mesSelecionado) || !impressora || !incrementosPorDia.has(data)) {
            return;
        }

        impressoras.add(impressora);
        const valorAtual = incrementosPorDia.get(data).get(impressora) || 0;
        incrementosPorDia.get(data).set(impressora, valorAtual + Number(evento.paginas || 0));
    });

    if (!impressoras.size) {
        return new Map();
    }

    const acumulado = new Map();
    return new Map(dias.map((dia) => {
        const valoresDia = new Map();
        const incrementos = incrementosPorDia.get(dia) || new Map();

        impressoras.forEach((impressora) => {
            const total = (acumulado.get(impressora) || 0) + Number(incrementos.get(impressora) || 0);
            acumulado.set(impressora, total);
            valoresDia.set(impressora, total);
        });

        return [dia, valoresDia];
    }));
}


function agruparMapaPorData(mapaDatas) {
    const mapaImpressoras = new Map();
    const datasOrdenadas = [...mapaDatas.keys()].sort();

    datasOrdenadas.forEach((data) => {
        const valoresDia = mapaDatas.get(data) || new Map();

        [...valoresDia.keys()].forEach((impressora) => {
            if (!mapaImpressoras.has(impressora)) {
                mapaImpressoras.set(
                    impressora,
                    chartColorPalette[mapaImpressoras.size % chartColorPalette.length],
                );
            }
        });
    });

    const impressoras = [...mapaImpressoras.keys()].sort((a, b) => a.localeCompare(b, "pt-BR"));
    return {
        datas: datasOrdenadas,
        impressoras: impressoras.map((id) => ({
            id,
            nome: graficosState.rotulosImpressoras.get(id) || id,
            cor: mapaImpressoras.get(id),
        })),
        valores: mapaDatas,
    };
}

function renderizarGraficoLinhaHistorico(hostId, mapaHistorico, opcoes = {}) {
    const host = document.getElementById(hostId);

    if (!host) {
        return;
    }

    if (!mapaHistorico.size) {
        host.innerHTML = `<p class="chart-loading">${opcoes.tituloVazio || "Nenhum registro historico disponivel."}</p>`;
        return;
    }

    const agrupado = agruparMapaPorData(mapaHistorico);

    if (!agrupado.datas.length || !agrupado.impressoras.length) {
        host.innerHTML = `<p class="chart-loading">${opcoes.tituloVazio || "Nenhum registro historico disponivel."}</p>`;
        return;
    }

    const { svg, largura, altura } = criarSvgBase(host, 420);
    const area = { x: 72, y: 24, width: largura - 96, height: 240 };
    const todosValores = [];

    agrupado.datas.forEach((data) => {
        agrupado.impressoras.forEach(({ id }) => {
            todosValores.push(agrupado.valores.get(data).get(id) ?? 0);
        });
    });

    const maxValue = Math.max(...todosValores, 0);
    desenharGradeY(svg, area, maxValue, 5);

    const eixoX = document.createElementNS(SVG_NS, "line");
    eixoX.setAttribute("x1", area.x);
    eixoX.setAttribute("x2", area.x + area.width);
    eixoX.setAttribute("y1", area.y + area.height);
    eixoX.setAttribute("y2", area.y + area.height);
    eixoX.setAttribute("class", "svg-axis-line");
    svg.appendChild(eixoX);

    const passoX = agrupado.datas.length > 1 ? area.width / (agrupado.datas.length - 1) : 0;
    const formatarRotulo = opcoes.formatarRotulo || ((valor) => valor);
    const formatarTooltip = opcoes.formatarTooltip || formatarRotulo;

    agrupado.impressoras.forEach(({ id, nome, cor }) => {
        const pontos = agrupado.datas.map((data, indice) => {
            const valor = agrupado.valores.get(data).get(id) ?? 0;
            const x = agrupado.datas.length > 1 ? area.x + passoX * indice : area.x + area.width / 2;
            const y = area.y + area.height - ((maxValue > 0 ? valor / maxValue : 0) * area.height);
            return { x, y, valor, data };
        });

        const path = document.createElementNS(SVG_NS, "path");
        const d = pontos
            .map((ponto, indice) => `${indice === 0 ? "M" : "L"} ${ponto.x} ${ponto.y}`)
            .join(" ");
        path.setAttribute("d", d);
        path.setAttribute("fill", "none");
        path.setAttribute("stroke", cor);
        path.setAttribute("stroke-width", "3");
        path.setAttribute("stroke-linejoin", "round");
        path.setAttribute("stroke-linecap", "round");
        svg.appendChild(path);
        adicionarTituloTooltip(path, nome);

        pontos.forEach((ponto) => {
            const circle = document.createElementNS(SVG_NS, "circle");
            circle.setAttribute("cx", ponto.x);
            circle.setAttribute("cy", ponto.y);
            circle.setAttribute("r", "4");
            circle.setAttribute("fill", cor);
            circle.setAttribute("class", "svg-point");
            adicionarTituloTooltip(circle, `${nome} | ${formatarTooltip(ponto.data)}: ${formatarNumero(ponto.valor)}`);
            svg.appendChild(circle);
        });
    });

    agrupado.datas.forEach((data, indice) => {
        const x = agrupado.datas.length > 1 ? area.x + passoX * indice : area.x + area.width / 2;
        adicionarTextoSvg(svg, x, area.y + area.height + 22, formatarRotulo(data), "svg-axis-label svg-axis-label-x");
    });

    const legendX = area.x;
    const legendY = area.y + area.height + 48;
    agrupado.impressoras.forEach(({ nome, cor }, indice) => {
        const itemX = legendX + (indice % 3) * 220;
        const itemY = legendY + Math.floor(indice / 3) * 24;

        const marcador = document.createElementNS(SVG_NS, "rect");
        marcador.setAttribute("x", itemX);
        marcador.setAttribute("y", itemY - 10);
        marcador.setAttribute("width", "14");
        marcador.setAttribute("height", "14");
        marcador.setAttribute("rx", "4");
        marcador.setAttribute("fill", cor);
        svg.appendChild(marcador);

        adicionarTextoSvg(svg, itemX + 22, itemY + 1, nome, "svg-legend-label", "start");
    });
}

function popularFiltroPeriodo(selectId, valores, formatador, valorPadrao) {
    const select = document.getElementById(selectId);

    if (!select) {
        return "";
    }

    const valorAtual = select.value;
    const valorSelecionado = valores.includes(valorAtual)
        ? valorAtual
        : (valores.includes(valorPadrao) ? valorPadrao : (valores[0] || ""));

    select.innerHTML = valores
        .map((valor) => `<option value="${escaparHtml(valor)}">${escaparHtml(formatador(valor))}</option>`)
        .join("");

    select.value = valorSelecionado;
    select.disabled = valores.length <= 1;
    return valorSelecionado;
}

function obterItensHistoricos(mapaValores, campoValor) {
    return [...mapaValores.entries()].map(([id, valor]) => ({
        id,
        nome: graficosState.rotulosImpressoras.get(id) || id,
        [campoValor]: Number(valor || 0),
    })).map(enriquecerItemComToken);
}

function obterTokenImpressora(id) {
    return graficosState.impressoras.find((item) => item.id === id) || {
        token_tipo: "pb",
        token_valor: 0.04,
    };
}

function enriquecerItemComToken(item) {
    const token = obterTokenImpressora(item.id || item.impressora);

    return {
        ...item,
        token_tipo: item.token_tipo || token.token_tipo,
        token_valor: Number(item.token_valor ?? token.token_valor ?? 0),
    };
}

function calcularValorToken(item, campoValor) {
    return Number(item[campoValor] || 0) * Number(item.token_valor || 0);
}

function calcularTotaisToken(itens, campoValor) {
    return itens.reduce(
        (totais, item) => ({
            impressoes: totais.impressoes + Number(item[campoValor] || 0),
            valor: totais.valor + calcularValorToken(item, campoValor),
        }),
        { impressoes: 0, valor: 0 },
    );
}

function calcularTotaisUsuarios(itens) {
    return itens.reduce(
        (totais, item) => ({
            paginas: totais.paginas + Number(item.total_paginas || 0),
            trabalhos: totais.trabalhos + Number(item.total_trabalhos || 0),
        }),
        { paginas: 0, trabalhos: 0 },
    );
}

function obterTopUsuariosPorImpressoes(itens, limite = 10) {
    return [...itens]
        .sort((a, b) => {
            const diferencaPaginas = Number(b.total_paginas || 0) - Number(a.total_paginas || 0);

            if (diferencaPaginas !== 0) {
                return diferencaPaginas;
            }

            return String(a.usuario || a.nome).localeCompare(String(b.usuario || b.nome), "pt-BR");
        })
        .slice(0, limite);
}

function filtrarUsuariosPorPesquisa(itens, termoBusca) {
    const termo = normalizarTextoBusca(termoBusca);

    if (!termo) {
        return itens;
    }

    return itens.filter((item) => normalizarTextoBusca(item.usuario || item.nome).includes(termo));
}

function obterItensRelatorioMensal(mesSelecionado) {
    const mesAtual = obterMesAtualIso();

    if (mesSelecionado === mesAtual) {
        return graficosState.impressoras.map((item) => ({
            id: item.id,
            nome: item.nome,
            impressoes_mes: Number(item.impressoes_mes || 0),
            token_tipo: item.token_tipo,
            token_valor: item.token_valor,
        }));
    }

    return obterItensHistoricos(graficosState.historicoMensal.get(mesSelecionado) || new Map(), "impressoes_mes")
        .map((item) => {
            const token = obterTokenImpressora(item.id);
            return {
                ...item,
                token_tipo: token.token_tipo,
                token_valor: token.token_valor,
            };
        });
}

function obterRegistrosDoMes(mesSelecionado) {
    const registrosFechados = graficosState.historico
        .filter((registro) => String(registro.data || "").startsWith(mesSelecionado))
        .map((registro) => ({
            ...registro,
            origem_relatorio: "fechado",
        }));
    const registrosDiaAtual = mesSelecionado === obterMesAtualIso()
        ? graficosState.impressoras.map((item) => ({
            data: obterDataAtualIso(),
            impressora: item.id,
            impressora_nome: item.nome,
            impressoes_total_dia: Number(item.impressoes_dia || 0),
            token_tipo: item.token_tipo,
            token_valor: item.token_valor,
            motivo: "dia_atual",
            timestamp_salvo: "Em aberto",
            origem_relatorio: "atual",
        }))
        : [];

    return [...registrosFechados, ...registrosDiaAtual]
        .sort((a, b) => {
            const dataComparada = String(b.data || "").localeCompare(String(a.data || ""));
            if (dataComparada !== 0) {
                return dataComparada;
            }

            return String(obterRotuloImpressora(a) || a.impressora)
                .localeCompare(String(obterRotuloImpressora(b) || b.impressora), "pt-BR");
        });
}

function montarLinhasResumoMensal(itens) {
    const itensOrdenados = [...itens].sort((a, b) => Number(b.impressoes_mes || 0) - Number(a.impressoes_mes || 0));

    return itensOrdenados
        .map((item) => `
            <tr>
                <td>${escaparHtml(item.nome || item.id)}</td>
                <td class="number">${formatarMoeda(item.token_valor)}</td>
                <td class="number">${formatarNumero(item.impressoes_mes)}</td>
                <td class="number">${formatarMoeda(Number(item.impressoes_mes || 0) * Number(item.token_valor || 0))}</td>
            </tr>
        `)
        .join("");
}

function montarLinhasRankingUsuarios(usuarios) {
    const totalPaginas = usuarios.reduce((total, item) => total + Number(item.total_paginas || 0), 0);

    if (!usuarios.length) {
        return `<tr><td colspan="6" class="empty">Nenhuma impressao por usuario encontrada no periodo.</td></tr>`;
    }

    return usuarios.slice(0, 10).map((item) => {
        const trabalhos = Number(item.total_trabalhos || 0);
        const paginas = Number(item.total_paginas || 0);
        const media = trabalhos ? paginas / trabalhos : 0;
        const participacao = totalPaginas ? (paginas / totalPaginas) * 100 : 0;

        return `
            <tr>
                <td>${escaparHtml(item.usuario)}</td>
                <td class="number">${formatarNumero(trabalhos)}</td>
                <td class="number">${formatarNumero(paginas)}</td>
                <td class="number">${media.toLocaleString("pt-BR", { minimumFractionDigits: 1, maximumFractionDigits: 1 })}</td>
                <td>${escaparHtml(item.impressora_principal || "Nao identificada")}</td>
                <td class="number">${participacao.toLocaleString("pt-BR", { minimumFractionDigits: 1, maximumFractionDigits: 1 })}%</td>
            </tr>
        `;
    }).join("");
}

async function imprimirRelatorioMensal() {
    const mesSelecionado = document.getElementById("filtro-data-mes")?.value || obterMesAtualIso();
    const itens = obterItensRelatorioMensal(mesSelecionado);
    const totalMes = itens.reduce((total, item) => total + Number(item.impressoes_mes || 0), 0);
    const valorTotalMes = itens.reduce(
        (total, item) => total + Number(item.impressoes_mes || 0) * Number(item.token_valor || 0),
        0,
    );
    const emitidoEm = new Intl.DateTimeFormat("pt-BR", {
        dateStyle: "short",
        timeStyle: "short",
    }).format(new Date());
    const versao = document.querySelector('meta[name="system-version"]')?.content || "desconhecida";
    const relatorioParcial = mesSelecionado === obterMesAtualIso();
    const janela = window.open("", "_blank", "width=1100,height=800");

    if (!janela) {
        alert("Nao foi possivel abrir a janela de impressao.");
        return;
    }

    janela.document.write("<p style='font-family:Arial;padding:24px'>Preparando relatorio mensal...</p>");

    let usuarios = [];
    try {
        const payload = await buscarJson(`/api/relatorios/mensal/usuarios?mes=${encodeURIComponent(mesSelecionado)}`);
        usuarios = normalizarListaApi(payload?.usuarios);
    } catch (error) {
        console.error("Erro ao carregar ranking mensal de usuarios:", error);
    }

    janela.document.open();
    janela.document.write(`
        <!DOCTYPE html>
        <html lang="pt-br">
        <head>
            <meta charset="UTF-8">
            <title>Relatorio mensal de impressoes</title>
            <style>
                @page { size: A4; margin: 15mm; }
                * { box-sizing: border-box; }
                body { margin: 0; color: #0f172a; font-family: Arial, sans-serif; }
                header { display: flex; justify-content: space-between; gap: 24px; border-bottom: 2px solid #0f172a; padding-bottom: 12px; margin-bottom: 18px; }
                h1 { margin: 0 0 4px; font-size: 22px; }
                h2 { margin: 22px 0 10px; font-size: 16px; }
                p { margin: 4px 0; }
                .subtitle, .meta, .note { color: #64748b; font-size: 11px; }
                .meta { text-align: right; }
                .status { display: inline-block; margin: 0 0 16px; padding: 5px 9px; border-radius: 999px; background: #e0f2fe; color: #0369a1; font-size: 10px; font-weight: 700; }
                .kpis { display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px; margin: 16px 0; }
                .kpi { border: 1px solid #cbd5e1; border-top: 3px solid #0ea5e9; padding: 12px; text-align: center; }
                .kpi strong { display: block; font-size: 19px; }
                .kpi span { color: #64748b; font-size: 9px; text-transform: uppercase; }
                table { width: 100%; border-collapse: collapse; font-size: 11px; }
                th, td { border: 1px solid #cbd5e1; padding: 7px 8px; text-align: left; }
                th { background: #0f172a; color: #fff; font-size: 10px; }
                tbody tr:nth-child(even) { background: #f1f5f9; }
                tfoot { background: #e0f2fe; font-weight: 700; }
                .number { text-align: right; }
                .empty { padding: 18px; text-align: center; color: #64748b; }
                .page-break { break-before: page; page-break-before: always; }
                .footer { margin-top: 28px; padding-top: 8px; border-top: 1px solid #cbd5e1; color: #64748b; font-size: 9px; text-align: center; }
                @media print { .page { min-height: 250mm; } }
            </style>
        </head>
        <body>
            <section class="page">
                <header>
                    <div>
                        <h1>Relatorio mensal de impressoes</h1>
                        <p class="subtitle">Resumo de producao e custos por impressora</p>
                    </div>
                    <div class="meta"><b>Competencia</b><br>${escaparHtml(formatarMesIso(mesSelecionado))}<br><br><b>Emitido em</b><br>${escaparHtml(emitidoEm)}</div>
                </header>
                <span class="status">${relatorioParcial ? "RELATORIO PARCIAL" : "MES FECHADO"}</span>
                <div class="kpis">
                    <div class="kpi"><strong>${formatarNumero(totalMes)}</strong><span>Impressoes no mes</span></div>
                    <div class="kpi"><strong>${formatarNumero(itens.length)}</strong><span>Impressoras</span></div>
                    <div class="kpi"><strong>${formatarMoeda(valorTotalMes)}</strong><span>Valor total</span></div>
                </div>
                <h2>Resumo por impressora</h2>
                <table>
                    <thead><tr><th>Impressora</th><th class="number">Valor unitario</th><th class="number">Total de impressoes no mes</th><th class="number">Valor total</th></tr></thead>
                    <tbody>${montarLinhasResumoMensal(itens)}</tbody>
                    <tfoot><tr><td>TOTAL</td><td class="number">-</td><td class="number">${formatarNumero(totalMes)}</td><td class="number">${formatarMoeda(valorTotalMes)}</td></tr></tfoot>
                </table>
                <div class="footer">Monitor de Impressoras • v${escaparHtml(versao)} • Dados do contador mensal das impressoras</div>
            </section>

            <section class="page page-break">
                <header>
                    <div><h1>Detalhamento de utilizacao</h1><p class="subtitle">Dados agrupados por usuario e periodo</p></div>
                    <div class="meta"><b>Competencia</b><br>${escaparHtml(formatarMesIso(mesSelecionado))}</div>
                </header>
                <h2>Ranking de usuarios</h2>
                <table>
                    <thead><tr><th>Usuario</th><th class="number">Trabalhos</th><th class="number">Paginas</th><th class="number">Media/job</th><th>Impressora principal</th><th class="number">Participacao</th></tr></thead>
                    <tbody>${montarLinhasRankingUsuarios(usuarios)}</tbody>
                </table>
                <p class="note">A participacao representa o percentual de paginas do usuario em relacao ao total registrado no periodo.</p>
                <div class="footer">Monitor de Impressoras • v${escaparHtml(versao)} • Ranking limitado aos 10 usuarios com maior volume</div>
            </section>
        </body>
        </html>
    `);
    janela.document.close();
    janela.focus();
    janela.print();
}

function atualizarSubtitulo(hostId, texto) {
    const el = document.getElementById(hostId);

    if (el) {
        el.innerText = texto;
    }
}

function obterPainelGraficoAtivo() {
    return document.getElementById(graficosState.abaAtiva);
}

function alternarAbaGraficos(tabId) {
    graficosState.abaAtiva = tabId;

    document.querySelectorAll(".chart-tab-button").forEach((botao) => {
        const ativo = botao.dataset.tabTarget === tabId;
        botao.classList.toggle("active", ativo);
        botao.setAttribute("aria-selected", ativo ? "true" : "false");
    });

    document.querySelectorAll(".chart-tab-panel").forEach((painel) => {
        const ativo = painel.id === tabId;
        painel.classList.toggle("active", ativo);
        painel.hidden = !ativo;
    });
}

function inicializarAbasGraficos() {
    const botoes = document.querySelectorAll(".chart-tab-button");

    botoes.forEach((botao) => {
        if (botao.dataset.bound) {
            return;
        }

        botao.addEventListener("click", () => {
            alternarAbaGraficos(botao.dataset.tabTarget);
            renderizarGraficosPorPeriodo();
        });
        botao.dataset.bound = "true";
    });
}

function obterFimMesExclusivo(mesReferencia) {
    const [ano, mes] = String(mesReferencia || "").split("-").map(Number);

    if (!ano || !mes) {
        return "";
    }

    const proximoMes = new Date(ano, mes, 1);
    const anoFim = String(proximoMes.getFullYear());
    const mesFim = String(proximoMes.getMonth() + 1).padStart(2, "0");
    return `${anoFim}-${mesFim}-01`;
}

function obterFimDataExclusivo(dataReferencia) {
    const [ano, mes, dia] = String(dataReferencia || "").split("-").map(Number);

    if (!ano || !mes || !dia) {
        return "";
    }

    const dataFim = new Date(ano, mes - 1, dia + 1);
    const anoFim = String(dataFim.getFullYear());
    const mesFim = String(dataFim.getMonth() + 1).padStart(2, "0");
    const diaFim = String(dataFim.getDate()).padStart(2, "0");
    return `${anoFim}-${mesFim}-${diaFim}`;
}

function obterPeriodoDetalhesUsuarioPadrao() {
    const mesSelecionado = document.getElementById("filtro-usuarios-mes")?.value || obterMesAtualIso();

    return {
        inicio: `${mesSelecionado}-01`,
        fim: obterFimMesExclusivo(mesSelecionado),
    };
}

function obterPeriodoDetalhesUsuarioSelecionado() {
    const inicio = document.getElementById("filtro-modal-usuario-data-inicio")?.value || "";
    const fimSelecionado = document.getElementById("filtro-modal-usuario-data-fim")?.value || "";

    return {
        inicio,
        fim: obterFimDataExclusivo(fimSelecionado),
    };
}

function formatarPeriodoDetalhesUsuario(periodo) {
    const inicio = formatarDataIso(periodo.inicio);
    const fimInclusivo = periodo.fim ? formatarDataIso(obterDataAnterior(periodo.fim)) : "";

    if (inicio && fimInclusivo) {
        return `${inicio} a ${fimInclusivo}`;
    }

    return inicio || fimInclusivo || "Periodo nao definido";
}

function obterDataAnterior(dataReferencia) {
    const [ano, mes, dia] = String(dataReferencia || "").split("-").map(Number);

    if (!ano || !mes || !dia) {
        return "";
    }

    const data = new Date(ano, mes - 1, dia - 1);
    const anoAnterior = String(data.getFullYear());
    const mesAnterior = String(data.getMonth() + 1).padStart(2, "0");
    const diaAnterior = String(data.getDate()).padStart(2, "0");
    return `${anoAnterior}-${mesAnterior}-${diaAnterior}`;
}

function preencherFiltrosPeriodoDetalhesUsuario(periodo) {
    const inicio = document.getElementById("filtro-modal-usuario-data-inicio");
    const fim = document.getElementById("filtro-modal-usuario-data-fim");

    if (inicio) {
        inicio.value = periodo.inicio || "";
    }

    if (fim) {
        fim.value = periodo.fim ? obterDataAnterior(periodo.fim) : "";
    }
}

function obterEventosUsuarioLocal(usuario, periodo) {
    return graficosState.eventosImpressoesUsuarios
        .filter((evento) => {
            const data = normalizarDataIso(evento.data_hora);
            return (
                evento.usuario === usuario
                && (!periodo.inicio || data >= periodo.inicio)
                && (!periodo.fim || data < periodo.fim)
            );
        })
        .sort((a, b) => String(b.data_hora || "").localeCompare(String(a.data_hora || "")));
}

async function buscarEventosUsuario(usuario, periodo) {
    const parametros = new URLSearchParams({
        usuario,
        limite: "1000",
    });

    if (periodo.inicio) {
        parametros.set("data_inicio", periodo.inicio);
    }

    if (periodo.fim) {
        parametros.set("data_fim", periodo.fim);
    }

    const payload = await buscarJson(`/api/impressoes-usuarios?${parametros.toString()}`);
    return normalizarListaApi(payload)
        .map(normalizarImpressaoUsuario)
        .filter((evento) => evento.usuario && evento.data_hora);
}

function fecharPopupDetalhesUsuario() {
    const modal = document.getElementById("modal-detalhes-usuario");

    if (modal) {
        modal.hidden = true;
    }
}

function atualizarPopupDetalhesUsuario(usuario, periodo, eventos) {
    const titulo = document.getElementById("titulo-modal-detalhes-usuario");
    const resumo = document.getElementById("resumo-modal-detalhes-usuario");
    const tbody = document.getElementById("tabela-modal-detalhes-usuario");
    const botaoImprimir = document.getElementById("botao-modal-usuario-imprimir");

    if (!titulo || !resumo || !tbody) {
        return;
    }

    const computadores = new Set(eventos.map((evento) => evento.computador).filter(Boolean));
    const impressoras = new Set(eventos.map((evento) => evento.impressora).filter(Boolean));
    const totalPaginas = eventos.reduce((total, evento) => total + Number(evento.paginas || 0), 0);

    graficosState.eventosDetalhesUsuario = eventos;
    if (botaoImprimir) {
        botaoImprimir.disabled = eventos.length === 0;
    }

    titulo.innerText = usuario;
    resumo.innerText = `Periodo: ${formatarPeriodoDetalhesUsuario(periodo)} | Jobs: ${formatarNumero(eventos.length)} | Paginas: ${formatarNumero(totalPaginas)} | Computadores: ${formatarNumero(computadores.size)} | Impressoras: ${formatarNumero(impressoras.size)}`;

    if (!eventos.length) {
        tbody.innerHTML = `
            <tr>
                <td colspan="6" class="chart-loading">Nenhum job encontrado para este usuario no periodo selecionado.</td>
            </tr>
        `;
        return;
    }

    tbody.innerHTML = eventos.map((evento) => `
        <tr>
            <td>${escaparHtml(evento.data_hora)}</td>
            <td>${escaparHtml(evento.computador || "-")}</td>
            <td>${escaparHtml(evento.impressora || "-")}</td>
            <td>${escaparHtml(evento.documento || "-")}</td>
            <td>${formatarNumero(evento.paginas)}</td>
            <td>${escaparHtml(evento.job_id || "-")}</td>
        </tr>
    `).join("");
}

async function carregarDetalhesUsuario(usuario, periodo) {
    const resumo = document.getElementById("resumo-modal-detalhes-usuario");
    const tbody = document.getElementById("tabela-modal-detalhes-usuario");
    const botaoImprimir = document.getElementById("botao-modal-usuario-imprimir");

    if (!resumo || !tbody || !usuario) {
        return;
    }

    graficosState.periodoDetalhesUsuario = periodo;
    graficosState.eventosDetalhesUsuario = [];
    if (botaoImprimir) {
        botaoImprimir.disabled = true;
    }
    resumo.innerText = `Periodo: ${formatarPeriodoDetalhesUsuario(periodo)} | Carregando jobs...`;
    tbody.innerHTML = `
        <tr>
            <td colspan="6" class="chart-loading">Carregando jobs...</td>
        </tr>
    `;

    try {
        const eventos = await buscarEventosUsuario(usuario, periodo);
        atualizarPopupDetalhesUsuario(usuario, periodo, eventos);
    } catch (error) {
        console.error("Erro ao carregar jobs do usuario:", error);
        atualizarPopupDetalhesUsuario(usuario, periodo, obterEventosUsuarioLocal(usuario, periodo));
    }
}

async function abrirPopupDetalhesUsuario(usuario) {
    const modal = document.getElementById("modal-detalhes-usuario");
    const titulo = document.getElementById("titulo-modal-detalhes-usuario");
    const resumo = document.getElementById("resumo-modal-detalhes-usuario");
    const tbody = document.getElementById("tabela-modal-detalhes-usuario");
    const periodo = obterPeriodoDetalhesUsuarioPadrao();

    if (!modal || !titulo || !resumo || !tbody || !usuario) {
        return;
    }

    graficosState.usuarioDetalhesAtual = usuario;
    preencherFiltrosPeriodoDetalhesUsuario(periodo);
    modal.hidden = false;
    titulo.innerText = usuario;
    await carregarDetalhesUsuario(usuario, periodo);
}

function aplicarPeriodoDetalhesUsuario() {
    if (!graficosState.usuarioDetalhesAtual) {
        return;
    }

    const periodo = obterPeriodoDetalhesUsuarioSelecionado();
    carregarDetalhesUsuario(graficosState.usuarioDetalhesAtual, periodo);
}

function imprimirRelatorioIndividualUsuario() {
    const usuario = graficosState.usuarioDetalhesAtual;
    const periodo = graficosState.periodoDetalhesUsuario;
    const eventos = graficosState.eventosDetalhesUsuario;

    if (!usuario || !eventos.length) {
        return;
    }

    const totalPaginas = eventos.reduce((total, evento) => total + Number(evento.paginas || 0), 0);
    const computadores = [...new Set(eventos.map((evento) => evento.computador).filter(Boolean))];
    const impressoras = [...new Set(eventos.map((evento) => evento.impressora).filter(Boolean))];
    const emitidoEm = new Intl.DateTimeFormat("pt-BR", {
        dateStyle: "short",
        timeStyle: "short",
    }).format(new Date());
    const versao = document.querySelector('meta[name="system-version"]')?.content || "desconhecida";
    const janela = window.open("", "_blank", "width=1100,height=800");

    if (!janela) {
        alert("Nao foi possivel abrir a janela de impressao.");
        return;
    }

    const linhas = eventos.map((evento) => `
        <tr>
            <td>${escaparHtml(evento.data_hora)}</td>
            <td>${escaparHtml(evento.computador || "-")}</td>
            <td>${escaparHtml(evento.impressora || "-")}</td>
            <td>${escaparHtml(evento.documento || "-")}</td>
            <td class="number">${formatarNumero(evento.paginas)}</td>
            <td>${escaparHtml(evento.job_id || "-")}</td>
        </tr>
    `).join("");

    janela.document.open();
    janela.document.write(`
        <!DOCTYPE html>
        <html lang="pt-br">
        <head>
            <meta charset="UTF-8">
            <title>Relatorio individual - ${escaparHtml(usuario)}</title>
            <style>
                @page { size: A4 landscape; margin: 12mm; }
                * { box-sizing: border-box; }
                body { margin: 0; color: #0f172a; font-family: Arial, sans-serif; }
                header { display: flex; justify-content: space-between; gap: 24px; border-bottom: 2px solid #0f172a; padding-bottom: 12px; margin-bottom: 16px; }
                h1 { margin: 0 0 4px; font-size: 22px; }
                h2 { margin: 18px 0 9px; font-size: 15px; }
                p { margin: 4px 0; }
                .subtitle, .meta, .details { color: #64748b; font-size: 11px; }
                .meta { text-align: right; }
                .kpis { display: grid; grid-template-columns: repeat(4, 1fr); gap: 10px; margin: 16px 0; }
                .kpi { border: 1px solid #cbd5e1; border-top: 3px solid #0ea5e9; padding: 11px; text-align: center; }
                .kpi strong { display: block; font-size: 18px; }
                .kpi span { color: #64748b; font-size: 9px; text-transform: uppercase; }
                .details { margin: 0 0 14px; line-height: 1.5; }
                table { width: 100%; border-collapse: collapse; font-size: 9px; }
                th, td { border: 1px solid #cbd5e1; padding: 6px; text-align: left; vertical-align: top; }
                th { background: #0f172a; color: #fff; font-size: 9px; }
                tbody tr:nth-child(even) { background: #f1f5f9; }
                .number { text-align: right; }
                .footer { margin-top: 18px; padding-top: 8px; border-top: 1px solid #cbd5e1; color: #64748b; font-size: 9px; text-align: center; }
                tr { break-inside: avoid; page-break-inside: avoid; }
            </style>
        </head>
        <body>
            <header>
                <div>
                    <h1>Relatorio individual de impressoes</h1>
                    <p class="subtitle">Usuario: ${escaparHtml(usuario)}</p>
                </div>
                <div class="meta"><b>Periodo</b><br>${escaparHtml(formatarPeriodoDetalhesUsuario(periodo))}<br><br><b>Emitido em</b><br>${escaparHtml(emitidoEm)}</div>
            </header>
            <div class="kpis">
                <div class="kpi"><strong>${formatarNumero(eventos.length)}</strong><span>Jobs</span></div>
                <div class="kpi"><strong>${formatarNumero(totalPaginas)}</strong><span>Paginas</span></div>
                <div class="kpi"><strong>${formatarNumero(computadores.length)}</strong><span>Computadores</span></div>
                <div class="kpi"><strong>${formatarNumero(impressoras.length)}</strong><span>Impressoras</span></div>
            </div>
            <p class="details"><b>Computadores:</b> ${escaparHtml(computadores.join(", ") || "Nao identificados")}<br><b>Impressoras:</b> ${escaparHtml(impressoras.join(", ") || "Nao identificadas")}</p>
            <h2>Jobs do periodo</h2>
            <table>
                <thead><tr><th>Data/hora</th><th>Computador</th><th>Impressora</th><th>Documento</th><th class="number">Paginas</th><th>Job ID</th></tr></thead>
                <tbody>${linhas}</tbody>
            </table>
            <div class="footer">Monitor de Impressoras | v${escaparHtml(versao)} | Relatorio individual por usuario</div>
        </body>
        </html>
    `);
    janela.document.close();
    janela.focus();
    janela.print();
}

function inicializarPopupDetalhesUsuario() {
    document.querySelectorAll("[data-user-jobs-close]").forEach((elemento) => {
        if (elemento.dataset.bound) {
            return;
        }

        elemento.addEventListener("click", fecharPopupDetalhesUsuario);
        elemento.dataset.bound = "true";
    });

    const botaoAplicar = document.getElementById("botao-modal-usuario-aplicar");
    const botaoImprimir = document.getElementById("botao-modal-usuario-imprimir");

    if (botaoAplicar && !botaoAplicar.dataset.bound) {
        botaoAplicar.addEventListener("click", aplicarPeriodoDetalhesUsuario);
        botaoAplicar.dataset.bound = "true";
    }

    if (botaoImprimir && !botaoImprimir.dataset.bound) {
        botaoImprimir.addEventListener("click", imprimirRelatorioIndividualUsuario);
        botaoImprimir.dataset.bound = "true";
    }

    if (!document.body.dataset.userJobsEscapeBound) {
        document.addEventListener("keydown", (event) => {
            if (event.key === "Escape") {
                fecharPopupDetalhesUsuario();
            }
        });
        document.body.dataset.userJobsEscapeBound = "true";
    }
}

function obterPeriodoDetalhesImpressoraPadrao() {
    if (graficosState.abaAtiva === "painel-grafico-dia") {
        const data = document.getElementById("filtro-data-dia")?.value || obterDataAtualIso();
        return { inicio: data, fim: obterFimDataExclusivo(data) };
    }

    const mes = document.getElementById("filtro-data-mes")?.value || obterMesAtualIso();
    return { inicio: `${mes}-01`, fim: obterFimMesExclusivo(mes) };
}

function preencherFiltrosPeriodoDetalhesImpressora(periodo) {
    const inicio = document.getElementById("filtro-modal-impressora-data-inicio");
    const fim = document.getElementById("filtro-modal-impressora-data-fim");
    if (inicio) inicio.value = periodo.inicio || "";
    if (fim) fim.value = periodo.fim ? obterDataAnterior(periodo.fim) : "";
}

function obterPeriodoDetalhesImpressoraSelecionado() {
    const inicio = document.getElementById("filtro-modal-impressora-data-inicio")?.value || "";
    const fim = document.getElementById("filtro-modal-impressora-data-fim")?.value || "";
    return { inicio, fim: obterFimDataExclusivo(fim) };
}

function fecharPopupUsuariosImpressora() {
    const modal = document.getElementById("modal-usuarios-impressora");
    if (modal) modal.hidden = true;
}

function atualizarPopupUsuariosImpressora(impressora, periodo, usuarios, dadosImpressora = {}) {
    const titulo = document.getElementById("titulo-modal-usuarios-impressora");
    const resumo = document.getElementById("resumo-modal-usuarios-impressora");
    const tbody = document.getElementById("tabela-modal-usuarios-impressora");
    const botaoImprimir = document.getElementById("botao-modal-impressora-imprimir");
    if (!titulo || !resumo || !tbody) return;

    const totalPaginas = usuarios.reduce((total, item) => total + Number(item.total_paginas || 0), 0);
    const totalTrabalhos = usuarios.reduce((total, item) => total + Number(item.total_trabalhos || 0), 0);
    graficosState.usuariosDetalhesImpressora = usuarios;
    graficosState.dadosDetalhesImpressora = dadosImpressora;
    if (botaoImprimir) {
        botaoImprimir.disabled = usuarios.length === 0;
    }

    titulo.innerText = impressora.nome || impressora.id;
    resumo.innerText = `IP: ${dadosImpressora.ip || impressora.ip || "-"} | Periodo: ${formatarPeriodoDetalhesUsuario(periodo)} | Usuarios: ${formatarNumero(usuarios.length)} | Trabalhos: ${formatarNumero(totalTrabalhos)} | Paginas: ${formatarNumero(totalPaginas)}`;

    if (!usuarios.length) {
        tbody.innerHTML = `<tr><td colspan="5" class="chart-loading">Nenhum usuario imprimiu nesta impressora no periodo selecionado.</td></tr>`;
        return;
    }

    tbody.innerHTML = usuarios.map((item) => `
        <tr>
            <td>${escaparHtml(item.usuario || "-")}</td>
            <td>${formatarNumero(item.total_trabalhos)}</td>
            <td>${formatarNumero(item.total_paginas)}</td>
            <td>${escaparHtml(item.primeira_impressao || "-")}</td>
            <td>${escaparHtml(item.ultima_impressao || "-")}</td>
        </tr>
    `).join("");
}

async function carregarUsuariosImpressora(impressora, periodo) {
    const resumo = document.getElementById("resumo-modal-usuarios-impressora");
    const tbody = document.getElementById("tabela-modal-usuarios-impressora");
    const botaoImprimir = document.getElementById("botao-modal-impressora-imprimir");
    if (!resumo || !tbody || !impressora?.id) return;

    graficosState.periodoDetalhesImpressora = periodo;
    graficosState.usuariosDetalhesImpressora = [];
    graficosState.dadosDetalhesImpressora = {};
    if (botaoImprimir) {
        botaoImprimir.disabled = true;
    }

    resumo.innerText = `Periodo: ${formatarPeriodoDetalhesUsuario(periodo)} | Carregando usuarios...`;
    tbody.innerHTML = `<tr><td colspan="5" class="chart-loading">Carregando usuarios...</td></tr>`;

    const parametros = new URLSearchParams();
    if (periodo.inicio) parametros.set("data_inicio", periodo.inicio);
    if (periodo.fim) parametros.set("data_fim", periodo.fim);

    try {
        const payload = await buscarJson(`/api/impressoras/${encodeURIComponent(impressora.id)}/usuarios?${parametros.toString()}`);
        const usuarios = normalizarListaApi(payload?.usuarios).map(normalizarResumoUsuario);
        atualizarPopupUsuariosImpressora(impressora, periodo, usuarios, payload?.impressora || {});
    } catch (error) {
        console.error("Erro ao carregar usuarios da impressora:", error);
        resumo.innerText = "Nao foi possivel carregar os usuarios desta impressora.";
        tbody.innerHTML = `<tr><td colspan="5" class="chart-loading">Falha ao consultar os dados.</td></tr>`;
    }
}

async function abrirPopupUsuariosImpressora(item) {
    const impressora = graficosState.impressoras.find((registro) => registro.id === item.id) || item;
    const modal = document.getElementById("modal-usuarios-impressora");
    if (!modal || !impressora?.id) return;

    const periodo = obterPeriodoDetalhesImpressoraPadrao();
    graficosState.impressoraDetalhesAtual = impressora;
    preencherFiltrosPeriodoDetalhesImpressora(periodo);
    modal.hidden = false;
    await carregarUsuariosImpressora(impressora, periodo);
}

function imprimirRelatorioImpressora() {
    const impressora = graficosState.impressoraDetalhesAtual;
    const periodo = graficosState.periodoDetalhesImpressora;
    const usuarios = graficosState.usuariosDetalhesImpressora;
    const dadosImpressora = graficosState.dadosDetalhesImpressora;

    if (!impressora || !usuarios.length) {
        return;
    }

    const nomeImpressora = impressora.nome || impressora.id;
    const ipImpressora = dadosImpressora.ip || impressora.ip || "-";
    const totalPaginas = usuarios.reduce((total, item) => total + Number(item.total_paginas || 0), 0);
    const totalTrabalhos = usuarios.reduce((total, item) => total + Number(item.total_trabalhos || 0), 0);
    const emitidoEm = new Intl.DateTimeFormat("pt-BR", {
        dateStyle: "short",
        timeStyle: "short",
    }).format(new Date());
    const versao = document.querySelector('meta[name="system-version"]')?.content || "desconhecida";
    const janela = window.open("", "_blank", "width=1100,height=800");

    if (!janela) {
        alert("Nao foi possivel abrir a janela de impressao.");
        return;
    }

    const linhas = usuarios.map((item) => `
        <tr>
            <td>${escaparHtml(item.usuario || "-")}</td>
            <td class="number">${formatarNumero(item.total_trabalhos)}</td>
            <td class="number">${formatarNumero(item.total_paginas)}</td>
            <td>${escaparHtml(item.primeira_impressao || "-")}</td>
            <td>${escaparHtml(item.ultima_impressao || "-")}</td>
        </tr>
    `).join("");

    janela.document.open();
    janela.document.write(`
        <!DOCTYPE html>
        <html lang="pt-br">
        <head>
            <meta charset="UTF-8">
            <title>Relatorio da impressora - ${escaparHtml(nomeImpressora)}</title>
            <style>
                @page { size: A4; margin: 15mm; }
                * { box-sizing: border-box; }
                body { margin: 0; color: #0f172a; font-family: Arial, sans-serif; }
                header { display: flex; justify-content: space-between; gap: 24px; border-bottom: 2px solid #0f172a; padding-bottom: 12px; margin-bottom: 16px; }
                h1 { margin: 0 0 4px; font-size: 22px; }
                h2 { margin: 18px 0 9px; font-size: 15px; }
                p { margin: 4px 0; }
                .subtitle, .meta { color: #64748b; font-size: 11px; }
                .meta { text-align: right; }
                .kpis { display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px; margin: 16px 0; }
                .kpi { border: 1px solid #cbd5e1; border-top: 3px solid #10b981; padding: 11px; text-align: center; }
                .kpi strong { display: block; font-size: 18px; }
                .kpi span { color: #64748b; font-size: 9px; text-transform: uppercase; }
                table { width: 100%; border-collapse: collapse; font-size: 10px; }
                th, td { border: 1px solid #cbd5e1; padding: 7px; text-align: left; vertical-align: top; }
                th { background: #0f172a; color: #fff; font-size: 9px; }
                tbody tr:nth-child(even) { background: #f1f5f9; }
                .number { text-align: right; }
                .footer { margin-top: 18px; padding-top: 8px; border-top: 1px solid #cbd5e1; color: #64748b; font-size: 9px; text-align: center; }
                tr { break-inside: avoid; page-break-inside: avoid; }
            </style>
        </head>
        <body>
            <header>
                <div>
                    <h1>Relatorio de impressoes por impressora</h1>
                    <p class="subtitle">Impressora: ${escaparHtml(nomeImpressora)} | IP: ${escaparHtml(ipImpressora)}</p>
                </div>
                <div class="meta"><b>Periodo</b><br>${escaparHtml(formatarPeriodoDetalhesUsuario(periodo))}<br><br><b>Emitido em</b><br>${escaparHtml(emitidoEm)}</div>
            </header>
            <div class="kpis">
                <div class="kpi"><strong>${formatarNumero(usuarios.length)}</strong><span>Usuarios</span></div>
                <div class="kpi"><strong>${formatarNumero(totalTrabalhos)}</strong><span>Trabalhos</span></div>
                <div class="kpi"><strong>${formatarNumero(totalPaginas)}</strong><span>Paginas</span></div>
            </div>
            <h2>Utilizacao por usuario</h2>
            <table>
                <thead><tr><th>Usuario</th><th class="number">Trabalhos</th><th class="number">Paginas</th><th>Primeira impressao</th><th>Ultima impressao</th></tr></thead>
                <tbody>${linhas}</tbody>
            </table>
            <div class="footer">Monitor de Impressoras | v${escaparHtml(versao)} | Relatorio individual por impressora</div>
        </body>
        </html>
    `);
    janela.document.close();
    janela.focus();
    janela.print();
}

function inicializarPopupUsuariosImpressora() {
    document.querySelectorAll("[data-printer-users-close]").forEach((elemento) => {
        if (!elemento.dataset.bound) {
            elemento.addEventListener("click", fecharPopupUsuariosImpressora);
            elemento.dataset.bound = "true";
        }
    });

    const botao = document.getElementById("botao-modal-impressora-aplicar");
    const botaoImprimir = document.getElementById("botao-modal-impressora-imprimir");
    if (botao && !botao.dataset.bound) {
        botao.addEventListener("click", () => {
            if (graficosState.impressoraDetalhesAtual) {
                carregarUsuariosImpressora(
                    graficosState.impressoraDetalhesAtual,
                    obterPeriodoDetalhesImpressoraSelecionado(),
                );
            }
        });
        botao.dataset.bound = "true";
    }

    if (botaoImprimir && !botaoImprimir.dataset.bound) {
        botaoImprimir.addEventListener("click", imprimirRelatorioImpressora);
        botaoImprimir.dataset.bound = "true";
    }

    if (!document.body.dataset.printerUsersEscapeBound) {
        document.addEventListener("keydown", (event) => {
            if (event.key === "Escape") fecharPopupUsuariosImpressora();
        });
        document.body.dataset.printerUsersEscapeBound = "true";
    }
}

function renderizarGraficosPorPeriodo() {
    const dataSelecionada = document.getElementById("filtro-data-dia")?.value || "";
    const mesSelecionado = document.getElementById("filtro-data-mes")?.value || "";
    const mesUsuariosSelecionado = document.getElementById("filtro-usuarios-mes")?.value || obterMesAtualIso();
    const pesquisaUsuarios = document.getElementById("filtro-usuarios-pesquisa")?.value || "";
    const dataLinhaSelecionada = document.getElementById("filtro-linha-dia")?.value || obterDataAtualIso();
    const mesLinhaSelecionado = document.getElementById("filtro-linha-mes")?.value || obterMesAtualIso();
    const dataAtual = obterDataAtualIso();
    const mesAtual = obterMesAtualIso();
    const valoresDia = graficosState.historicoDiarioCompleto.get(dataSelecionada) || new Map();
    const valoresMes = mesSelecionado === mesAtual
        ? null
        : (graficosState.historicoMensal.get(mesSelecionado) || new Map());

    const itensDia = dataSelecionada === dataAtual
        ? graficosState.impressoras
        : obterItensHistoricos(valoresDia, "impressoes_dia");
    const itensMes = mesSelecionado === mesAtual
        ? graficosState.impressoras
        : obterItensHistoricos(valoresMes, "impressoes_mes");
    const totaisDia = calcularTotaisToken(itensDia, "impressoes_dia");
    const totaisMes = calcularTotaisToken(itensMes, "impressoes_mes");
    const itensUsuarios = graficosState.impressoesUsuariosPorMes.get(mesUsuariosSelecionado)
        || (mesUsuariosSelecionado === obterMesAtualIso() ? graficosState.impressoesUsuarios : []);
    const usuariosFiltrados = filtrarUsuariosPorPesquisa(itensUsuarios, pesquisaUsuarios);
    const topUsuarios = obterTopUsuariosPorImpressoes(usuariosFiltrados);
    const totaisUsuarios = calcularTotaisUsuarios(topUsuarios);

    atualizarSubtitulo(
        "subtitulo-grafico-dia",
        `Periodo: ${formatarDataIso(dataSelecionada)} | Total: ${formatarNumero(totaisDia.impressoes)} impressoes | Valor: ${formatarMoeda(totaisDia.valor)}`,
    );
    atualizarSubtitulo(
        "subtitulo-grafico-mes",
        `Periodo: ${formatarMesIso(mesSelecionado)} | Total: ${formatarNumero(totaisMes.impressoes)} impressoes | Valor: ${formatarMoeda(totaisMes.valor)}`,
    );
    atualizarSubtitulo(
        "subtitulo-grafico-usuarios",
        `${pesquisaUsuarios ? "Busca" : "Top 10"} | Periodo: ${formatarMesIso(mesUsuariosSelecionado)} | Total: ${formatarNumero(totaisUsuarios.paginas)} paginas | Trabalhos: ${formatarNumero(totaisUsuarios.trabalhos)}`,
    );

    if (graficosState.abaAtiva === "painel-grafico-dia") {
        renderizarGraficoColunas(
            "grafico-colunas-dia",
            "Nenhum dado diario disponivel para o periodo selecionado.",
            itensDia,
            "impressoes_dia",
            "#38bdf8",
            { onItemClick: abrirPopupUsuariosImpressora },
        );
    }

    if (graficosState.abaAtiva === "painel-grafico-mes") {
        renderizarGraficoColunas(
            "grafico-colunas-mes",
            "Nenhum dado mensal disponivel para o periodo selecionado.",
            itensMes,
            "impressoes_mes",
            "#34d399",
            { onItemClick: abrirPopupUsuariosImpressora },
        );
    }

    const linhaModo = graficosState.periodoLinhaHistorico;
    const mapaLinha = linhaModo === "mes"
        ? construirLinhaEventosMes(graficosState.eventosImpressoesUsuarios, mesLinhaSelecionado)
        : construirLinhaEventosDia(graficosState.eventosImpressoesUsuarios, dataLinhaSelecionada);
    const tituloLinha = document.getElementById("titulo-grafico-linha");

    if (tituloLinha) {
        tituloLinha.innerText = linhaModo === "mes" ? "Historico por Mes" : "Historico por Dia";
    }

    atualizarSubtitulo(
        "subtitulo-grafico-linha",
        linhaModo === "mes"
            ? `Trajetoria acumulada durante ${formatarMesIso(mesLinhaSelecionado)} por impressora`
            : `Evolucao acumulada em ${formatarDataIso(dataLinhaSelecionada)} por impressora`,
    );
    renderizarGraficoLinhaHistorico(
        "grafico-linha-historico",
        mapaLinha,
        {
            tituloVazio: linhaModo === "mes"
                ? "Nenhum evento de impressao disponivel para o mes selecionado."
                : "Nenhum evento de impressao disponivel para o dia selecionado.",
            formatarRotulo: linhaModo === "mes" ? ((valor) => String(valor).slice(8, 10)) : ((valor) => valor),
            formatarTooltip: linhaModo === "mes" ? formatarDataIso : ((valor) => valor),
        },
    );
    renderizarGraficoUsuarios();
}

function renderizarGraficoUsuarios() {
    const mesSelecionado = document.getElementById("filtro-usuarios-mes")?.value || obterMesAtualIso();
    const pesquisaUsuarios = document.getElementById("filtro-usuarios-pesquisa")?.value || "";
    const itens = graficosState.impressoesUsuariosPorMes.get(mesSelecionado)
        || (mesSelecionado === obterMesAtualIso() ? graficosState.impressoesUsuarios : []);
    const usuariosFiltrados = filtrarUsuariosPorPesquisa(itens, pesquisaUsuarios);
    const topUsuarios = obterTopUsuariosPorImpressoes(usuariosFiltrados);

    renderizarGraficoColunas(
        "grafico-colunas-usuarios",
        "Nenhuma impressao por usuario disponivel para o periodo selecionado.",
        topUsuarios,
        "total_paginas",
        "#14b8a6",
        {
            mostrarToken: false,
            onItemClick: (item) => abrirPopupDetalhesUsuario(item.usuario || item.nome),
        },
    );
}

function alternarModoLinhaHistorico(periodo) {
    graficosState.periodoLinhaHistorico = periodo === "mes" ? "mes" : "dia";

    document.querySelectorAll("[data-line-period]").forEach((botao) => {
        botao.classList.toggle("active", botao.dataset.linePeriod === graficosState.periodoLinhaHistorico);
    });

    const controleDia = document.querySelector('label[for="filtro-linha-dia"]');
    const controleMes = document.querySelector('label[for="filtro-linha-mes"]');

    if (controleDia) {
        controleDia.hidden = graficosState.periodoLinhaHistorico !== "dia";
    }
    if (controleMes) {
        controleMes.hidden = graficosState.periodoLinhaHistorico !== "mes";
    }
}

function inicializarControleLinhaHistorico() {
    document.querySelectorAll("[data-line-period]").forEach((botao) => {
        if (botao.dataset.bound) {
            return;
        }

        botao.addEventListener("click", () => {
            alternarModoLinhaHistorico(botao.dataset.linePeriod);
            renderizarGraficosPorPeriodo();
        });
        botao.dataset.bound = "true";
    });

    alternarModoLinhaHistorico(graficosState.periodoLinhaHistorico);
}

function inicializarFiltrosPeriodo() {
    const datasDisponiveis = [...graficosState.historicoDiarioCompleto.keys()].sort().reverse();
    const mesesDisponiveis = new Set([
        obterMesAtualIso(),
        ...[...graficosState.historicoMensal.keys()],
    ]);
    const mesesOrdenados = [...mesesDisponiveis].sort().reverse();

    const mesesUsuariosDisponiveis = new Set([
        obterMesAtualIso(),
        ...[...graficosState.impressoesUsuariosPorMes.keys()],
    ]);
    const mesesUsuariosOrdenados = [...mesesUsuariosDisponiveis].sort().reverse();
    const datasLinhaDisponiveis = obterDatasEventosImpressoes(graficosState.eventosImpressoesUsuarios);
    const mesesLinhaDisponiveis = obterMesesEventosImpressoes(graficosState.eventosImpressoesUsuarios);

    popularFiltroPeriodo("filtro-data-dia", datasDisponiveis, formatarDataFiltroHistorico, obterDataAtualIso());
    popularFiltroPeriodo("filtro-data-mes", mesesOrdenados, formatarMesIso, obterMesAtualIso());
    popularFiltroPeriodo("filtro-usuarios-mes", mesesUsuariosOrdenados, formatarMesIso, obterMesAtualIso());
    popularFiltroPeriodo("filtro-linha-dia", datasLinhaDisponiveis, formatarDataIso, obterDataAtualIso());
    popularFiltroPeriodo("filtro-linha-mes", mesesLinhaDisponiveis, formatarMesIso, obterMesAtualIso());

    const filtroDia = document.getElementById("filtro-data-dia");
    const filtroMes = document.getElementById("filtro-data-mes");
    const filtroUsuariosMes = document.getElementById("filtro-usuarios-mes");
    const filtroUsuariosPesquisa = document.getElementById("filtro-usuarios-pesquisa");
    const filtroLinhaDia = document.getElementById("filtro-linha-dia");
    const filtroLinhaMes = document.getElementById("filtro-linha-mes");

    if (filtroDia && !filtroDia.dataset.bound) {
        filtroDia.addEventListener("change", renderizarGraficosPorPeriodo);
        filtroDia.dataset.bound = "true";
    }

    if (filtroMes && !filtroMes.dataset.bound) {
        filtroMes.addEventListener("change", renderizarGraficosPorPeriodo);
        filtroMes.dataset.bound = "true";
    }

    if (filtroUsuariosMes && !filtroUsuariosMes.dataset.bound) {
        filtroUsuariosMes.addEventListener("change", renderizarGraficosPorPeriodo);
        filtroUsuariosMes.dataset.bound = "true";
    }

    if (filtroUsuariosPesquisa && !filtroUsuariosPesquisa.dataset.bound) {
        filtroUsuariosPesquisa.addEventListener("input", renderizarGraficosPorPeriodo);
        filtroUsuariosPesquisa.dataset.bound = "true";
    }

    if (filtroLinhaDia && !filtroLinhaDia.dataset.bound) {
        filtroLinhaDia.addEventListener("change", renderizarGraficosPorPeriodo);
        filtroLinhaDia.dataset.bound = "true";
    }

    if (filtroLinhaMes && !filtroLinhaMes.dataset.bound) {
        filtroLinhaMes.addEventListener("change", renderizarGraficosPorPeriodo);
        filtroLinhaMes.dataset.bound = "true";
    }

    const botaoRelatorioMensal = document.getElementById("botao-relatorio-mensal");

    if (botaoRelatorioMensal && !botaoRelatorioMensal.dataset.bound) {
        botaoRelatorioMensal.addEventListener("click", imprimirRelatorioMensal);
        botaoRelatorioMensal.dataset.bound = "true";
    }
}

function preencherTabelaHistorico(registros) {
    const tbody = document.getElementById("tabela-historico-body");

    if (!tbody) {
        return;
    }

    if (!registros.length) {
        tbody.innerHTML = `
            <tr>
                <td colspan="5" class="chart-loading">Nenhum registro historico disponivel.</td>
            </tr>
        `;
        return;
    }

    const linhas = [...registros]
        .sort((a, b) => String(b.timestamp_salvo || "").localeCompare(String(a.timestamp_salvo || "")))
        .slice(0, 100)
        .map((registro) => `
            <tr>
                <td>${escaparHtml(registro.data)}</td>
                <td>${escaparHtml(obterRotuloImpressora(registro) || registro.impressora)}</td>
                <td>${formatarNumero(registro.impressoes_total_dia)}</td>
                <td>${escaparHtml(registro.motivo)}</td>
                <td>${escaparHtml(registro.timestamp_salvo)}</td>
            </tr>
        `)
        .join("");

    tbody.innerHTML = linhas;
}

async function carregarGraficos() {
    const resultadoImpressoras = await Promise.allSettled([
        buscarJsonComFallback(["/api"]),
        buscarJsonComFallback(["/api/historico"]),
        buscarJsonComFallback(["/api/impressoes-usuarios?limite=1000", "/api/impressoes-usuarios/resumo"]),
    ]);
    const [resImpressoras, resHistorico, resUsuarios] = resultadoImpressoras;
    const payloadImpressoras = resImpressoras.status === "fulfilled" ? resImpressoras.value : [];
    const payloadHistorico = resHistorico.status === "fulfilled" ? resHistorico.value : [];
    const payloadUsuarios = resUsuarios.status === "fulfilled" ? resUsuarios.value : [];
    const impressoras = normalizarListaApi(payloadImpressoras, "impressoras")
        .map(normalizarImpressora)
        .filter((item) => item.id);
    const historico = normalizarHistorico(normalizarListaApi(payloadHistorico, "historico"));
    const usuariosNormalizados = normalizarListaApi(payloadUsuarios);
    const eventosUsuarios = usuariosNormalizados
        .map(normalizarImpressaoUsuario)
        .filter((item) => item.usuario && item.data_hora);
    const resumoUsuariosFallback = usuariosNormalizados
        .map(normalizarResumoUsuario)
        .filter((item) => item.usuario);
    const usuariosPorMes = construirResumoUsuariosPorMes(eventosUsuarios);
    const impressoesUsuarios = usuariosPorMes.get(obterMesAtualIso()) || resumoUsuariosFallback;
    const historicoDiario = construirMapaHistoricoDiario(historico);
    const datasSalvamentoPorData = construirMapaDatasSalvamentoPorData(historico);
    const rotulosImpressoras = construirMapaRotulosImpressoras(impressoras, historico);
    const historicoDiarioCompleto = construirMapaHistoricoDiarioCompleto(
        historicoDiario,
        impressoras,
    );

    if (resImpressoras.status === "rejected") {
        console.error("Erro ao carregar impressoras:", resImpressoras.reason);
    }

    if (resHistorico.status === "rejected") {
        console.error("Erro ao carregar historico:", resHistorico.reason);
    }

    if (resUsuarios.status === "rejected") {
        console.error("Erro ao carregar impressoes por usuario:", resUsuarios.reason);
    }

    graficosState.impressoras = impressoras;
    graficosState.historico = historico;
    graficosState.historicoDiario = historicoDiario;
    graficosState.datasSalvamentoPorData = datasSalvamentoPorData;
    graficosState.rotulosImpressoras = rotulosImpressoras;
    graficosState.historicoDiarioCompleto = historicoDiarioCompleto;
    graficosState.historicoMensal = construirMapaHistoricoMensal(historicoDiarioCompleto);
    graficosState.impressoesUsuarios = impressoesUsuarios;
    graficosState.eventosImpressoesUsuarios = eventosUsuarios;
    graficosState.impressoesUsuariosPorMes = usuariosPorMes;

    atualizarResumo(impressoras);
    inicializarAbasGraficos();
    inicializarPopupUsuariosImpressora();
    inicializarControleLinhaHistorico();
    inicializarPopupDetalhesUsuario();
    inicializarFiltrosPeriodo();
    alternarAbaGraficos(graficosState.abaAtiva);
    renderizarGraficosPorPeriodo();
    preencherTabelaHistorico(historico);

    if (resUsuarios.status === "rejected") {
        const host = document.getElementById("grafico-colunas-usuarios");
        if (host) {
            host.innerHTML = `<p class="chart-loading">Nao foi possivel carregar as impressoes por usuario.</p>`;
        }
    }

    if (resImpressoras.status === "rejected") {
        ["grafico-colunas-dia", "grafico-colunas-mes"].forEach((id) => {
            const host = document.getElementById(id);
            if (host) {
                host.innerHTML = `<p class="chart-loading">Nao foi possivel carregar as impressoras.</p>`;
            }
        });
    }
}

window.addEventListener("resize", () => {
    window.clearTimeout(resizeTimeoutId);
    resizeTimeoutId = window.setTimeout(renderizarGraficosPorPeriodo, 120);
});

carregarGraficos();
