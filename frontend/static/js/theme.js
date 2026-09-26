(() => {
    "use strict";
    const key = "printer-interface-theme";
    let theme = "light";
    try {
        if (localStorage.getItem(key) === "dark") theme = "dark";
    } catch (_) { /* O tema continua funcionando sem armazenamento. */ }
    document.documentElement.dataset.theme = theme;

    document.addEventListener("DOMContentLoaded", () => {
        const button = document.querySelector("[data-theme-toggle]");
        if (!button) return;
        const update = () => {
            const dark = document.documentElement.dataset.theme === "dark";
            button.setAttribute("aria-pressed", String(dark));
            button.setAttribute("aria-label", dark ? "Ativar tema claro" : "Ativar tema escuro");
            button.textContent = dark ? "☀ Tema claro" : "☾ Tema escuro";
        };
        button.addEventListener("click", () => {
            const next = document.documentElement.dataset.theme === "dark" ? "light" : "dark";
            document.documentElement.dataset.theme = next;
            try { localStorage.setItem(key, next); } catch (_) { /* Preferência apenas nesta página. */ }
            update();
        });
        window.addEventListener("storage", (event) => {
            if (event.key !== key) return;
            document.documentElement.dataset.theme = event.newValue === "dark" ? "dark" : "light";
            update();
        });
        update();
    });
})();
