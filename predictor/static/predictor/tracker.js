(function () {
    const script = document.currentScript;

    const apiKey = script.getAttribute("data-api-key");
    const apiUrl = script.getAttribute("data-api-url") || "/api/track/";
    const leadUrl = script.getAttribute("data-lead-url") || "/api/lead/";
    const debugMode = script.getAttribute("data-debug") === "true";

    if (!apiKey) {
        console.warn("PredictNeed IA : clé API manquante.");
        return;
    }

    function getSessionId() {
        let sessionId = localStorage.getItem("predictneed_session_id");

        if (!sessionId) {
            if (crypto.randomUUID) {
                sessionId = crypto.randomUUID();
            } else {
                sessionId = "session_" + Date.now() + "_" + Math.random().toString(36).substring(2);
            }

            if (!debugMode) {
                localStorage.setItem("predictneed_lead_sent", "true");
            }
        }

        return sessionId;
    }

    const sessionId = getSessionId();
    const startTime = Date.now();

    function shouldShowOffer(resultat) {
        if (!resultat) return false;

        if (debugMode) {
            return true;
        }

        const leadAlreadySent = localStorage.getItem("predictneed_lead_sent");
        const popupAlreadyShown = sessionStorage.getItem("predictneed_popup_shown");

        if (leadAlreadySent || popupAlreadyShown) {
            return false;
        }

        return resultat.intention === "Forte" || Number(resultat.score) >= 6;
    }

    function showOfferPopup(resultat) {
        const existingPopup = document.getElementById("predictneed-popup");

        if (existingPopup) {
            existingPopup.classList.remove("minimized");
            return;
        }

        if (!debugMode) {
            sessionStorage.setItem("predictneed_popup_shown", "true");
        }

        const popup = document.createElement("div");
        popup.id = "predictneed-popup";

        popup.innerHTML = `
            <button class="predictneed-launcher" type="button">
                <span class="predictneed-launcher-icon">💬</span>
                <span>Offre personnalisée</span>
            </button>

            <div class="predictneed-popup-box">
                <button class="predictneed-close" type="button">×</button>

                <h3>Une offre peut vous intéresser</h3>

                <p>
                    Vous semblez intéressé par nos services.
                    Laissez vos coordonnées pour recevoir une proposition personnalisée.
                </p>

                <form id="predictneed-lead-form">
                    <input type="text" name="nom" placeholder="Votre nom">

                    <input type="email" name="email" placeholder="Votre email">

                    <input type="text" name="telephone" placeholder="Votre téléphone">

                    <textarea name="message" placeholder="Votre message">Je souhaite recevoir une offre personnalisée.</textarea>

                    <label class="predictneed-consent">
                        <input type="checkbox" name="consentement" required>
                        <span>J’accepte d’être contacté au sujet de ma demande.</span>
                    </label>

                    <button type="submit">Recevoir l’offre</button>
                </form>

                <p class="predictneed-small">
                    Profil détecté : ${resultat.profil || "Visiteur intéressé"}
                </p>
            </div>
        `;

        const style = document.createElement("style");
        style.innerHTML = `
            #predictneed-popup {
                position: fixed;
                right: 24px;
                bottom: 24px;
                z-index: 999999;
                width: 380px;
                max-width: calc(100% - 40px);
                font-family: Arial, sans-serif;
            }

            #predictneed-popup.minimized {
                width: auto;
            }

            .predictneed-launcher {
                display: none;
                align-items: center;
                gap: 10px;
                border: none;
                border-radius: 999px;
                padding: 14px 18px;
                background: linear-gradient(90deg, #38bdf8, #22d3ee);
                color: #0f172a;
                font-weight: bold;
                box-shadow: 0 14px 40px rgba(0, 0, 0, 0.35);
                cursor: pointer;
            }

            .predictneed-launcher-icon {
                width: 28px;
                height: 28px;
                display: inline-flex;
                align-items: center;
                justify-content: center;
                border-radius: 50%;
                background: rgba(15, 23, 42, 0.15);
            }

            #predictneed-popup.minimized .predictneed-launcher {
                display: flex;
            }

            #predictneed-popup.minimized .predictneed-popup-box {
                display: none;
            }

            .predictneed-popup-box {
                position: relative;
                background: linear-gradient(135deg, #0f172a, #1e3a8a);
                color: white;
                padding: 24px;
                border-radius: 18px;
                box-shadow: 0 20px 60px rgba(0, 0, 0, 0.35);
                border: 1px solid rgba(56, 189, 248, 0.45);
                box-sizing: border-box;
            }

            .predictneed-popup-box h3 {
                margin: 0 0 10px;
                font-size: 22px;
                color: #67e8f9;
            }

            .predictneed-popup-box p {
                margin: 0 0 16px;
                font-size: 14px;
                line-height: 1.5;
                color: #e2e8f0;
            }

            .predictneed-close {
                position: absolute;
                top: 10px;
                right: 12px;
                background: transparent;
                color: white;
                border: none;
                font-size: 26px;
                cursor: pointer;
            }

            #predictneed-lead-form {
                display: grid;
                gap: 10px;
            }

            #predictneed-lead-form input,
            #predictneed-lead-form textarea {
                width: 100%;
                box-sizing: border-box;
                border: none;
                border-radius: 10px;
                padding: 11px;
                font-size: 14px;
            }

            #predictneed-lead-form textarea {
                min-height: 70px;
                resize: vertical;
            }

            .predictneed-consent {
                display: grid;
                grid-template-columns: 18px 1fr;
                gap: 10px;
                align-items: flex-start;
                width: 100%;
                box-sizing: border-box;
                font-size: 12px;
                line-height: 1.4;
                color: #e2e8f0;
                white-space: normal;
                overflow-wrap: break-word;
            }

            .predictneed-consent input {
                width: 16px !important;
                height: 16px;
                margin: 2px 0 0 0;
            }

            .predictneed-consent span {
                display: block;
                min-width: 0;
            }

            #predictneed-lead-form button {
                border: none;
                border-radius: 999px;
                padding: 12px 18px;
                background: #38bdf8;
                color: #0f172a;
                font-weight: bold;
                cursor: pointer;
            }

            .predictneed-small {
                margin-top: 12px !important;
                font-size: 12px !important;
                color: #bae6fd !important;
            }
        `;

        document.head.appendChild(style);
        document.body.appendChild(popup);

        const closeButton = popup.querySelector(".predictneed-close");
        const launcherButton = popup.querySelector(".predictneed-launcher");
        const form = document.getElementById("predictneed-lead-form");

        closeButton.addEventListener("click", function (event) {
            event.preventDefault();
            event.stopPropagation();
            popup.classList.add("minimized");
        });

        launcherButton.addEventListener("click", function (event) {
            event.preventDefault();
            event.stopPropagation();
            popup.classList.remove("minimized");
        });
        
        form.addEventListener("submit", function (event) {
            event.preventDefault();

            const formData = new FormData(form);

            const nom = formData.get("nom");
            const email = formData.get("email");
            const telephone = formData.get("telephone");
            const message = formData.get("message");
            const consentement = formData.get("consentement") === "on";

            if (!email && !telephone) {
                alert("Veuillez renseigner au moins un email ou un téléphone.");
                return;
            }

            fetch(leadUrl, {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                },
                body: JSON.stringify({
                    api_key: apiKey,
                    session_id: sessionId,
                    nom: nom,
                    email: email,
                    telephone: telephone,
                    message: message,
                    consentement: consentement,
                    page: window.location.pathname,
                }),
            })
                .then(function (response) {
                    return response.json();
                })
                .then(function (data) {
                    if (data.success) {
                        if (!debugMode) {
                            localStorage.setItem("predictneed_lead_sent", "true");
                        }

                        popup.querySelector(".predictneed-popup-box").innerHTML = `
                            <h3>Merci !</h3>
                            <p>
                                Votre demande a bien été envoyée.
                                Un professionnel pourra vous recontacter.
                            </p>
                        `;

                        popup.querySelector(".predictneed-launcher span:last-child").textContent = "Demande envoyée";

                        setTimeout(function () {
                            popup.classList.add("minimized");
                        }, 2500);
                    } else {
                        alert(data.error || "Erreur lors de l’envoi du contact.");
                    }
                })
                .catch(function (error) {
                    console.warn("PredictNeed IA : erreur lead", error);
                    alert("Une erreur est survenue.");
                });
        });
    }

    function sendEvent(typeEvenement, page, valeur) {
        fetch(apiUrl, {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
            },
            body: JSON.stringify({
                api_key: apiKey,
                session_id: sessionId,
                type_evenement: typeEvenement,
                page: page,
                valeur: valeur,
            }),
        })
            .then(function (response) {
                return response.json();
            })
            .then(function (data) {
                if (data.success && shouldShowOffer(data)) {
                    showOfferPopup(data);
                }
            })
            .catch(function (error) {
                console.warn("PredictNeed IA : erreur tracking", error);
            });
    }

    sendEvent(
        "page_vue",
        window.location.pathname,
        document.title
    );

    document.addEventListener("click", function (event) {
        if (event.target.closest("#predictneed-popup")) {
            return;
        }

        const elementClique = event.target.closest("a, button");

        if (elementClique) {
            const texte = elementClique.innerText || elementClique.href || "clic";

            sendEvent(
                "clic",
                window.location.pathname,
                texte
            );
        }
    });

    let dernierTempsEnvoye = 0;

    function envoyerTempsPasse() {
        const tempsTotal = Math.round((Date.now() - startTime) / 1000);
        const difference = tempsTotal - dernierTempsEnvoye;

        if (difference >= 10) {
            dernierTempsEnvoye = tempsTotal;

            sendEvent(
                "temps",
                window.location.pathname,
                difference + " secondes"
            );
        }
    }

    setInterval(envoyerTempsPasse, 10000);

    window.addEventListener("beforeunload", function () {
        const tempsPasse = Math.round((Date.now() - startTime) / 1000);

        const data = {
            api_key: apiKey,
            session_id: sessionId,
            type_evenement: "temps",
            page: window.location.pathname,
            valeur: tempsPasse + " secondes",
        };

        const blob = new Blob(
            [JSON.stringify(data)],
            { type: "application/json" }
        );

        navigator.sendBeacon(apiUrl, blob);
    });
})();