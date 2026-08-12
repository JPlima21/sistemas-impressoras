"use strict";

function configurarMenuLateralProducao() {
    const sidebar = document.querySelector("#production-sidebar");
    const collapseButton = document.querySelector("#production-sidebar-toggle");
    const mobileButton = document.querySelector("#production-mobile-menu");
    if (!sidebar || !collapseButton || !mobileButton) return;

    const storageKey = "production-sidebar-collapsed";
    const atualizarEstadoRecolhido = (collapsed) => {
        sidebar.classList.toggle("collapsed", collapsed);
        collapseButton.setAttribute("aria-expanded", String(!collapsed));
        collapseButton.setAttribute("aria-label", collapsed ? "Expandir menu lateral" : "Recolher menu lateral");
    };

    const preferenciaRecolhimento = localStorage.getItem(storageKey);
    const iniciarRecolhido = preferenciaRecolhimento === null || preferenciaRecolhimento === "true";
    atualizarEstadoRecolhido(iniciarRecolhido && window.innerWidth > 768);

    collapseButton.addEventListener("click", () => {
        const collapsed = !sidebar.classList.contains("collapsed");
        atualizarEstadoRecolhido(collapsed);
        localStorage.setItem(storageKey, String(collapsed));
    });

    function fecharMenuMobile() {
        sidebar.classList.remove("mobile-open");
        document.body.classList.remove("production-menu-open");
        mobileButton.setAttribute("aria-expanded", "false");
    }

    mobileButton.addEventListener("click", () => {
        const opened = sidebar.classList.toggle("mobile-open");
        document.body.classList.toggle("production-menu-open", opened);
        mobileButton.setAttribute("aria-expanded", String(opened));
    });

    sidebar.querySelectorAll("a").forEach((link) => link.addEventListener("click", fecharMenuMobile));
    document.addEventListener("click", (event) => {
        if (sidebar.classList.contains("mobile-open") && !sidebar.contains(event.target) && !mobileButton.contains(event.target)) fecharMenuMobile();
    });
    document.addEventListener("keydown", (event) => { if (event.key === "Escape") fecharMenuMobile(); });
}

document.addEventListener("DOMContentLoaded", configurarMenuLateralProducao);
