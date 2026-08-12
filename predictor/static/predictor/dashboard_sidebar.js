
(function () {
    const storageKey = "predictneedSidebarCollapsed";

    function appliquerEtat(reduit) {
        document.body.classList.toggle("pn-sidebar-collapsed", reduit);

        const button = document.getElementById("pnSidebarCollapse");

        if (!button) {
            return;
        }

        const icon = button.querySelector("i");

        if (reduit) {
            button.setAttribute("aria-label", "Ouvrir le menu");
            button.setAttribute("title", "Ouvrir le menu");

            if (icon) {
                icon.className = "bi bi-chevron-right";
            }
        } else {
            button.setAttribute("aria-label", "Réduire le menu");
            button.setAttribute("title", "Réduire le menu");

            if (icon) {
                icon.className = "bi bi-chevron-left";
            }
        }
    }

    document.addEventListener("DOMContentLoaded", function () {
        let reduit = false;

        try {
            reduit = localStorage.getItem(storageKey) === "1";
        } catch (error) {
            reduit = false;
        }

        appliquerEtat(reduit);

        const button = document.getElementById("pnSidebarCollapse");

        if (button) {
            button.addEventListener("click", function () {
                const nouvelEtat =
                    !document.body.classList.contains("pn-sidebar-collapsed");

                appliquerEtat(nouvelEtat);

                try {
                    localStorage.setItem(
                        storageKey,
                        nouvelEtat ? "1" : "0"
                    );
                } catch (error) {
                    // Le dashboard reste fonctionnel même sans localStorage.
                }
            });
        }
    });
})();
