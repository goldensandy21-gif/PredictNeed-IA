(function () {
    if (window.PredictNeedIA && window.PredictNeedIA.__trackerLoaded) {
        return;
    }

    window.PredictNeedIA = window.PredictNeedIA || {};
    window.PredictNeedIA.__trackerLoaded = true;

    const script = document.currentScript;

    const apiKey = script.getAttribute("data-api-key");
    const apiUrl = script.getAttribute("data-api-url") || "/api/track/";
    const leadUrl = script.getAttribute("data-lead-url") || "/api/lead/";
    const installUrl =
        script.getAttribute("data-install-url")
        || apiUrl.replace(/\/api\/track\/?$/, "/api/install/");
    const debugMode = script.getAttribute("data-debug") === "true";
    const requireConsent = script.getAttribute("data-require-consent") !== "false";
    const privacyUrl = script.getAttribute("data-privacy-url") || "";
    const cookiesUrl = script.getAttribute("data-cookies-url") || "";
    const retargetingEnabled = script.getAttribute("data-retargeting-enabled") === "true";
    const retargetingConfig = {
        metaPixelId: script.getAttribute("data-meta-pixel-id") || "",
        googleAdsId: script.getAttribute("data-google-ads-id") || "",
        googleAdsConversionLabel: script.getAttribute("data-google-ads-conversion-label") || "",
        tiktokPixelId: script.getAttribute("data-tiktok-pixel-id") || "",
        linkedinPartnerId: script.getAttribute("data-linkedin-partner-id") || "",
        linkedinConversionId: script.getAttribute("data-linkedin-conversion-id") || "",
        pinterestTagId: script.getAttribute("data-pinterest-tag-id") || "",
    };

    const consentStorageKey = "predictneed_consent_v3";
    const sessionStorageKey = "predictneed_session_id";
    const leadSentStorageKey = "predictneed_lead_sent";
    const consentValidityMs = 180 * 24 * 60 * 60 * 1000;

    let sessionId = null;
    let leadSessionId = null;
    let hasStartedTracking = false;
    let elapsedSecondsSent = 0;
    let offerTriggerInitialized = false;
    let offerDelayPassed = false;
    let hasScrolledForOffer = false;
    let offerReopenTimer = null;
    let latestPredictionResult = null;
    let mobileOfferDismissed = false;
    let retargetingPageTracked = false;
    const retargetingState = {
        metaInitialized: false,
        googleInitialized: false,
        tiktokInitialized: false,
        linkedinInitialized: false,
        pinterestInitialized: false,
    };
    const startTime = Date.now();
    const offerPopupInitialDelayMs = 5000;
    const offerPopupReopenDelayMs = 10000;

    if (!apiKey) {
        console.warn("PredictNeed IA : clé API manquante.");
        return;
    }

    function signalInstallation() {
        if (!installUrl) {
            return;
        }

        const separator = installUrl.includes("?") ? "&" : "?";
        const url =
            installUrl
            + separator
            + "api_key="
            + encodeURIComponent(apiKey)
            + "&origin="
            + encodeURIComponent(window.location.origin);

        fetch(url, {
            method: "GET",
            mode: "no-cors",
            cache: "no-store",
            keepalive: true,
        }).catch(function () {
            // La détection technique ne doit jamais bloquer le site client.
        });
    }

    signalInstallation();

    function now() {
        return Date.now();
    }

    function readStoredConsent() {
        if (!requireConsent) {
            return {
                analytics: true,
                offers: true,
                updated_at: now(),
            };
        }

        try {
            const rawConsent = localStorage.getItem(consentStorageKey);

            if (!rawConsent) {
                return null;
            }

            const consent = JSON.parse(rawConsent);

            if (!consent || !consent.updated_at) {
                return null;
            }

            if (now() - Number(consent.updated_at) > consentValidityMs) {
                localStorage.removeItem(consentStorageKey);
                localStorage.removeItem(sessionStorageKey);
                localStorage.removeItem(leadSentStorageKey);
                sessionStorage.removeItem(leadSentStorageKey);
                return null;
            }

            return {
                analytics: consent.analytics === true,
                offers: consent.offers === true,
                updated_at: Number(consent.updated_at),
            };
        } catch (error) {
            localStorage.removeItem(consentStorageKey);
            return null;
        }
    }

    function saveConsent(consent) {
        const normalizedConsent = {
            analytics: consent.analytics === true,
            offers: consent.offers === true,
            updated_at: now(),
        };

        localStorage.setItem(consentStorageKey, JSON.stringify(normalizedConsent));
        return normalizedConsent;
    }

    function hasAnalyticsConsent() {
        const consent = readStoredConsent();
        return consent && consent.analytics === true;
    }

    function hasOfferConsent() {
        const consent = readStoredConsent();
        return consent && consent.analytics === true && consent.offers === true;
    }

    function createSessionId() {
        if (window.crypto && crypto.randomUUID) {
            return crypto.randomUUID();
        }

        return "session_" + Date.now() + "_" + Math.random().toString(36).substring(2);
    }

    function getSessionId() {
        if (sessionId) {
            return sessionId;
        }

        if (requireConsent && !debugMode && !hasAnalyticsConsent()) {
            return null;
        }

        sessionId = sessionStorage.getItem(sessionStorageKey);

        if (!sessionId) {
            sessionId = createSessionId();

            if (!debugMode) {
                sessionStorage.setItem(sessionStorageKey, sessionId);
            }
        }

        return sessionId;
    }

    function getLeadSessionId() {
        const trackingSessionId = getSessionId();

        if (trackingSessionId) {
            return trackingSessionId;
        }

        if (!leadSessionId) {
            leadSessionId = createSessionId();
        }

        return leadSessionId;
    }

    function removeTrackingStorage() {
        sessionId = null;
        hasStartedTracking = false;
        elapsedSecondsSent = 0;
        clearOfferReopenTimer();
        localStorage.removeItem(sessionStorageKey);
        sessionStorage.removeItem(sessionStorageKey);
        localStorage.removeItem(leadSentStorageKey);
        sessionStorage.removeItem(leadSentStorageKey);
    }

    function injectConsentStyles() {
        if (document.getElementById("predictneed-consent-style")) {
            return;
        }

        const style = document.createElement("style");
        style.id = "predictneed-consent-style";
        style.innerHTML = `
            #predictneed-consent-banner,
            #predictneed-consent-panel {
                position: fixed;
                left: 20px;
                right: 20px;
                bottom: 20px;
                z-index: 999998;
                max-width: 760px;
                box-sizing: border-box;
                padding: 18px;
                border: 1px solid rgba(15, 23, 42, 0.18);
                border-radius: 12px;
                background: #ffffff;
                color: #0f172a;
                box-shadow: 0 20px 70px rgba(15, 23, 42, 0.24);
                font-family: Arial, sans-serif;
            }

            #predictneed-consent-panel {
                max-width: 640px;
            }

            .predictneed-consent-title {
                margin: 0 0 8px;
                font-size: 18px;
                line-height: 1.25;
                font-weight: 800;
                color: #0f172a;
            }

            .predictneed-consent-text {
                margin: 0 0 14px;
                color: #334155;
                font-size: 14px;
                line-height: 1.55;
            }

            .predictneed-consent-actions {
                display: flex;
                flex-wrap: wrap;
                gap: 10px;
            }

            .predictneed-consent-actions button,
            .predictneed-cookie-settings {
                min-height: 42px;
                border-radius: 999px;
                padding: 0 16px;
                border: 1px solid #0f172a;
                background: #ffffff;
                color: #0f172a;
                font-weight: 800;
                cursor: pointer;
            }

            .predictneed-consent-actions .primary {
                background: #0f172a;
                color: #ffffff;
            }

            .predictneed-consent-links {
                display: flex;
                flex-wrap: wrap;
                gap: 12px;
                margin-top: 12px;
                font-size: 13px;
            }

            .predictneed-consent-links a {
                color: #075985;
                text-decoration: underline;
            }

            .predictneed-consent-choice {
                display: grid;
                grid-template-columns: 20px 1fr;
                gap: 10px;
                margin: 12px 0;
                color: #334155;
                font-size: 14px;
                line-height: 1.45;
            }

            .predictneed-consent-choice input {
                width: 16px;
                height: 16px;
                margin: 2px 0 0;
            }

            .predictneed-cookie-settings {
                position: fixed;
                left: 16px;
                bottom: 16px;
                z-index: 999997;
                min-height: 38px;
                border-color: rgba(15, 23, 42, 0.3);
                background: #ffffff;
                box-shadow: 0 10px 30px rgba(15, 23, 42, 0.16);
                font-size: 13px;
            }

            @media (max-width: 560px) {
                #predictneed-consent-banner,
                #predictneed-consent-panel {
                    left: 10px;
                    right: 10px;
                    bottom: 10px;
                    padding: 14px;
                }

                .predictneed-consent-actions {
                    display: grid;
                    grid-template-columns: 1fr;
                }

                .predictneed-consent-actions button {
                    width: 100%;
                }
            }
        `;

        document.head.appendChild(style);
    }

    function removeConsentUi() {
        const banner = document.getElementById("predictneed-consent-banner");
        const panel = document.getElementById("predictneed-consent-panel");
        const settingsButton = document.getElementById("predictneed-cookie-settings");

        if (banner) {
            banner.remove();
        }

        if (panel) {
            panel.remove();
        }

        if (settingsButton) {
            settingsButton.remove();
        }
    }

    function renderSettingsButton() {
        if (!requireConsent || document.getElementById("predictneed-cookie-settings")) {
            return;
        }

        injectConsentStyles();

        const button = document.createElement("button");
        button.id = "predictneed-cookie-settings";
        button.className = "predictneed-cookie-settings";
        button.type = "button";
        button.textContent = "Paramètres de confidentialité";

        button.addEventListener("click", function () {
            renderConsentPanel();
        });

        document.body.appendChild(button);
    }

    function appendConsentLink(container, url, label) {
        if (!url) {
            return;
        }

        let parsedUrl = null;

        try {
            parsedUrl = new URL(url, window.location.href);
        } catch (error) {
            return;
        }

        if (parsedUrl.protocol !== "https:" && parsedUrl.protocol !== "http:") {
            return;
        }

        const link = document.createElement("a");
        link.href = parsedUrl.href;
        link.target = "_blank";
        link.rel = "noopener";
        link.textContent = label;
        container.appendChild(link);
    }

    function renderConsentBanner() {
        if (!requireConsent) {
            removeConsentUi();
            return;
        }

        if (document.getElementById("predictneed-consent-banner") || document.getElementById("predictneed-consent-panel")) {
            return;
        }

        injectConsentStyles();

        const banner = document.createElement("div");
        banner.id = "predictneed-consent-banner";
        banner.setAttribute("role", "dialog");
        banner.setAttribute("aria-live", "polite");
        banner.setAttribute("aria-label", "Gestion du consentement PredictNeed IA");

        banner.innerHTML = `
            <p class="predictneed-consent-title">Nous respectons votre confidentialité</p>
            <p class="predictneed-consent-text">
                Nous utilisons des cookies et outils pour mieux comprendre l'utilisation
                du site, améliorer votre expérience et proposer des contenus ou publicités plus pertinents.
                Vous pouvez accepter, refuser ou personnaliser vos choix à tout moment.
            </p>
            <div class="predictneed-consent-actions">
                <button type="button" data-choice="reject">Tout refuser</button>
                <button type="button" data-choice="customize">Personnaliser</button>
                <button type="button" data-choice="accept">Tout accepter</button>
            </div>
            <div class="predictneed-consent-links"></div>
        `;

        const links = banner.querySelector(".predictneed-consent-links");
        appendConsentLink(links, privacyUrl, "Politique de confidentialité");
        appendConsentLink(links, cookiesUrl, "Politique de cookies");

        banner.addEventListener("click", function (event) {
            const button = event.target.closest("button");
            if (!button) {
                return;
            }

            const choice = button.getAttribute("data-choice");

            if (choice === "accept") {
                applyConsent({ analytics: true, offers: true });
            } else if (choice === "reject") {
                applyConsent({ analytics: false, offers: false });
            } else if (choice === "customize") {
                renderConsentPanel();
            }
        });

        document.body.appendChild(banner);
    }

    function renderConsentPanel() {
        removeConsentUi();
        injectConsentStyles();

        const storedConsent = readStoredConsent() || {
            analytics: false,
            offers: false,
        };

        const panel = document.createElement("div");
        panel.id = "predictneed-consent-panel";
        panel.setAttribute("role", "dialog");
        panel.setAttribute("aria-label", "Préférences cookies PredictNeed IA");

        panel.innerHTML = `
            <p class="predictneed-consent-title">Paramètres de confidentialité</p>
            <p class="predictneed-consent-text">
                Choisissez les outils que vous acceptez. Les cookies nécessaires au bon
                fonctionnement du site restent toujours actifs.
            </p>
            <label class="predictneed-consent-choice">
                <input type="checkbox" name="analytics" ${storedConsent.analytics ? "checked" : ""}>
                <span>
                    <strong>Mesure et amélioration de l'expérience</strong><br>
                    Comprendre l'utilisation du site, améliorer les parcours et mesurer
                    l'efficacité des contenus.
                </span>
            </label>
            <label class="predictneed-consent-choice">
                <input type="checkbox" name="offers" ${storedConsent.offers ? "checked" : ""}>
                <span>
                    <strong>Contenus et publicités pertinents</strong><br>
                    Adapter certains messages ou déclencher les pixels publicitaires configurés
                    selon l'intérêt exprimé pendant la navigation.
                </span>
            </label>
            <div class="predictneed-consent-actions">
                <button type="button" data-choice="reject">Tout refuser</button>
                <button type="button" data-choice="save">Enregistrer mes choix</button>
                <button type="button" data-choice="accept">Tout accepter</button>
            </div>
        `;

        panel.addEventListener("click", function (event) {
            const button = event.target.closest("button");
            if (!button) {
                return;
            }

            const choice = button.getAttribute("data-choice");

            if (choice === "accept") {
                applyConsent({ analytics: true, offers: true });
            } else if (choice === "reject") {
                applyConsent({ analytics: false, offers: false });
            } else if (choice === "save") {
                const analytics = panel.querySelector('input[name="analytics"]').checked;
                const offers = panel.querySelector('input[name="offers"]').checked;
                applyConsent({
                    analytics: analytics,
                    offers: analytics && offers,
                });
            }
        });

        document.body.appendChild(panel);
    }

    function applyConsent(consent) {
        const normalizedConsent = saveConsent(consent);

        if (!normalizedConsent.analytics) {
            removeTrackingStorage();
        }

        removeConsentUi();

        initializeOfferTrigger();
        tryShowOfferAfterEngagement();
        trackRetargetingPage();

        if (normalizedConsent.analytics) {
            startTracking();
        }
    }

    window.PredictNeedIA.openConsentPreferences = renderConsentPanel;
    window.PredictNeedIA.acceptAll = function () {
        applyConsent({ analytics: true, offers: true });
    };
    window.PredictNeedIA.rejectAll = function () {
        applyConsent({ analytics: false, offers: false });
    };

    function canShowOfferPopup() {
        if (debugMode) {
            return !document.getElementById("predictneed-popup");
        }

        const leadAlreadySent = localStorage.getItem(leadSentStorageKey) || sessionStorage.getItem(leadSentStorageKey);

        if (leadAlreadySent) {
            return false;
        }

        return true;
    }

    function shouldShowOffer(resultat) {
        if (!resultat) return false;

        if (!canShowOfferPopup()) {
            return false;
        }

        return resultat.intention === "Forte" || Number(resultat.score) >= 6;
    }

    function tryShowOfferAfterEngagement() {
        if (!offerDelayPassed || !canShowOfferPopup()) {
            return;
        }

        showOfferPopup(latestPredictionResult || {
            intention: "Moyenne",
            score: 3,
        });
    }

    function initializeOfferTrigger() {
        if (offerTriggerInitialized) {
            tryShowOfferAfterEngagement();
            return;
        }

        offerTriggerInitialized = true;

        if (window.scrollY > 40) {
            hasScrolledForOffer = true;
        }

        const markScrolled = function () {
            hasScrolledForOffer = true;
            tryShowOfferAfterEngagement();
        };

        window.addEventListener("scroll", markScrolled, { passive: true, once: true });
        window.addEventListener("touchmove", markScrolled, { passive: true, once: true });
        window.addEventListener("wheel", markScrolled, { passive: true, once: true });

        setTimeout(function () {
            offerDelayPassed = true;
            tryShowOfferAfterEngagement();
        }, offerPopupInitialDelayMs);
    }

    function clearOfferReopenTimer() {
        if (offerReopenTimer) {
            clearTimeout(offerReopenTimer);
            offerReopenTimer = null;
        }
    }

    function scheduleOfferPopupReopen() {
        clearOfferReopenTimer();

        if (isMobileOfferExperience() || !canShowOfferPopup()) {
            return;
        }

        offerReopenTimer = setTimeout(function () {
            offerReopenTimer = null;

            if (canShowOfferPopup()) {
                showOfferPopup(latestPredictionResult || {
                    intention: "Moyenne",
                    score: 3,
                });
            }
        }, offerPopupReopenDelayMs);
    }

    function isMobileOfferExperience() {
        if (window.matchMedia && window.matchMedia("(max-width: 767px)").matches) {
            return true;
        }

        return detecterAppareil().est_mobile === true;
    }

    function showOfferPopup(resultat) {
        clearOfferReopenTimer();

        const existingPopup = document.getElementById("predictneed-popup");

        if (existingPopup) {
            if (isMobileOfferExperience() && (mobileOfferDismissed || existingPopup.classList.contains("minimized"))) {
                return;
            }

            existingPopup.classList.remove("minimized");
            return;
        }

        if (isMobileOfferExperience() && mobileOfferDismissed) {
            return;
        }

        const popup = document.createElement("div");
        popup.id = "predictneed-popup";

        popup.innerHTML = `
            <button class="predictneed-launcher" type="button">
                <span class="predictneed-launcher-icon">i</span>
                <span>Écrire un message</span>
            </button>

            <div class="predictneed-popup-box">
                <button class="predictneed-close" type="button">×</button>

                <h3>Bonjour, besoin d'aide ?</h3>

                <p>
                    Écrivez un message ou laissez vos coordonnées.
                    L’équipe pourra vous répondre rapidement.
                </p>

                <form id="predictneed-lead-form">
                    <input type="text" name="nom" placeholder="Votre nom">

                    <input type="email" name="email" placeholder="Votre email">

                    <input type="text" name="telephone" placeholder="Votre téléphone">

                    <textarea name="message" placeholder="Votre message">Bonjour, je souhaite être recontacté.</textarea>

                    <label class="predictneed-consent">
                        <input type="checkbox" name="consentement" required>
                        <span>J'accepte d'être contacté au sujet de ma demande.</span>
                    </label>

                    <button type="submit">Envoyer le message</button>
                </form>

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
                background: #38bdf8;
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
                font-weight: 900;
            }

            #predictneed-popup.minimized .predictneed-launcher {
                display: flex;
            }

            #predictneed-popup.minimized .predictneed-popup-box {
                display: none;
            }

            .predictneed-popup-box {
                position: relative;
                background: #0f172a;
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

            if (isMobileOfferExperience()) {
                mobileOfferDismissed = true;
                clearOfferReopenTimer();
                return;
            }

            scheduleOfferPopupReopen();
        });

        launcherButton.addEventListener("click", function (event) {
            event.preventDefault();
            event.stopPropagation();
            clearOfferReopenTimer();
            mobileOfferDismissed = false;
            popup.classList.remove("minimized");
        });

        form.addEventListener("submit", function (event) {
            event.preventDefault();

            const currentSessionId = getLeadSessionId();
            const formData = new FormData(form);

            const nom = formData.get("nom");
            const email = formData.get("email");
            const telephone = formData.get("telephone");
            const message = formData.get("message");
            const consentement = formData.get("consentement") === "on";
            const infosAppareil = detecterAppareil();
            const infosSource = detecterSource();

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
                    session_id: currentSessionId,
                    nom: nom,
                    email: email,
                    telephone: telephone,
                    message: message,
                    consentement: consentement,
                    page: window.location.pathname,
                    user_agent: navigator.userAgent,
                    referer: document.referrer,
                    appareil: infosAppareil.appareil,
                    navigateur: infosAppareil.navigateur,
                    systeme_exploitation: infosAppareil.systeme_exploitation,
                    source_visite: infosSource.source_visite,
                    utm_source: infosSource.utm_source,
                    utm_medium: infosSource.utm_medium,
                    utm_campaign: infosSource.utm_campaign,
                    utm_content: infosSource.utm_content,
                    utm_term: infosSource.utm_term,
                    utm_id: infosSource.utm_id,
                    click_id_source: infosSource.click_id_source,
                    click_id: infosSource.click_id,
                    landing_page: infosSource.landing_page,
                    est_mobile: infosAppareil.est_mobile,
                    est_tablette: infosAppareil.est_tablette,
                    est_desktop: infosAppareil.est_desktop,
                }),
            })
                .then(function (response) {
                    return response.json();
                })
                .then(function (data) {
                    if (data.success) {
                        trackRetargetingLead();

                        if (!debugMode) {
                            if (hasAnalyticsConsent()) {
                                localStorage.setItem(leadSentStorageKey, "true");
                            } else {
                                sessionStorage.setItem(leadSentStorageKey, "true");
                            }
                        }

                        popup.querySelector(".predictneed-popup-box").innerHTML = `
                            <h3>Merci !</h3>
                            <p>
                                Votre demande a bien été envoyée.
                                Un professionnel pourra vous recontacter.
                            </p>
                        `;

                        popup.querySelector(".predictneed-launcher span:last-child").textContent = "Message envoyé";

                        setTimeout(function () {
                            popup.classList.add("minimized");
                        }, 2500);
                    } else {
                        alert(data.error || "Erreur lors de l'envoi du contact.");
                    }
                })
                .catch(function (error) {
                    console.warn("PredictNeed IA : erreur lead", error);
                    alert("Une erreur est survenue.");
                });
        });
    }

    function detecterAppareil() {
        const largeur = window.innerWidth;
        const userAgentOriginal = navigator.userAgent || "";
        const userAgent = userAgentOriginal.toLowerCase();
        const platform = (navigator.platform || "").toLowerCase();
        const maxTouchPoints = navigator.maxTouchPoints || 0;

        let appareil = "Desktop";
        const isIpadOS = platform === "macintel" && maxTouchPoints > 1;
        const isIphone = /iphone|ipod/.test(userAgent);
        const isIpad = /ipad/.test(userAgent) || isIpadOS;
        const isAndroid = /android/.test(userAgent);
        const isAndroidMobile = isAndroid && /mobile/.test(userAgent);
        const isAndroidTablet = isAndroid && !/mobile/.test(userAgent);

        if (isIpad) {
            appareil = "Tablette iPad";
        } else if (isIphone) {
            appareil = "Mobile iPhone";
        } else if (isAndroidTablet || /tablet/.test(userAgent)) {
            appareil = "Tablette Android";
        } else if (isAndroidMobile || /mobile/.test(userAgent) || largeur < 768) {
            appareil = isAndroid ? "Mobile Android" : "Mobile";
        }

        let navigateur = "Inconnu";

        if (/edgios|edg\//.test(userAgent)) {
            navigateur = isIphone || isIpad ? "Edge iOS" : "Edge";
        } else if (/crios/.test(userAgent)) {
            navigateur = "Chrome iOS";
        } else if (/fxios/.test(userAgent)) {
            navigateur = "Firefox iOS";
        } else if (/samsungbrowser/.test(userAgent)) {
            navigateur = "Samsung Internet";
        } else if (/opr\//.test(userAgent)) {
            navigateur = "Opera";
        } else if (/chrome|chromium/.test(userAgent)) {
            navigateur = "Chrome";
        } else if (userAgent.includes("safari")) {
            navigateur = isIphone || isIpad ? "Safari iOS" : "Safari";
        } else if (userAgent.includes("firefox")) {
            navigateur = "Firefox";
        }

        let systeme = "Inconnu";

        if (isIpad) {
            systeme = "iPadOS";
        } else if (isIphone) {
            systeme = "iOS";
        } else if (isAndroid) {
            systeme = "Android";
        } else if (userAgent.includes("windows")) {
            systeme = "Windows";
        } else if (userAgent.includes("mac")) {
            systeme = "macOS";
        }

        const estTablette = appareil.toLowerCase().includes("tablette");
        const estMobile = appareil.toLowerCase().includes("mobile");

        return {
            appareil: appareil,
            navigateur: navigateur,
            systeme_exploitation: systeme,
            est_mobile: estMobile,
            est_tablette: estTablette,
            est_desktop: !estMobile && !estTablette
        };
    }

    function detecterSource() {
        const params = new URLSearchParams(window.location.search);
        const utmSource = params.get("utm_source");
        const utmMedium = params.get("utm_medium");
        const utmCampaign = params.get("utm_campaign");
        const utmContent = params.get("utm_content");
        const utmTerm = params.get("utm_term");
        const utmId = params.get("utm_id");

        const clickCandidates = [
            ["google_ads", "gclid"],
            ["google_ads", "gbraid"],
            ["google_ads", "wbraid"],
            ["meta_ads", "fbclid"],
            ["tiktok_ads", "ttclid"],
            ["linkedin_ads", "li_fat_id"],
        ];

        let clickIdSource = "";
        let clickId = "";

        for (let index = 0; index < clickCandidates.length; index += 1) {
            const candidate = clickCandidates[index];
            const value = params.get(candidate[1]);

            if (value) {
                clickIdSource = candidate[0];
                clickId = value;
                break;
            }
        }

        let source = "direct";

        if (utmSource) {
            source = utmSource;
        } else if (clickIdSource) {
            source = clickIdSource;
        } else if (document.referrer) {
            try {
                const refererHost = new URL(document.referrer).hostname;

                if (refererHost.includes("google")) {
                    source = "google";
                } else if (
                    refererHost.includes("facebook") ||
                    refererHost.includes("instagram") ||
                    refererHost.includes("linkedin") ||
                    refererHost.includes("tiktok") ||
                    refererHost.includes("x.com") ||
                    refererHost.includes("twitter")
                ) {
                    source = "social";
                } else {
                    source = "referer";
                }
            } catch (error) {
                source = "referer";
            }
        }

        return {
            source_visite: source,
            utm_source: utmSource || "",
            utm_medium: utmMedium || "",
            utm_campaign: utmCampaign || "",
            utm_content: utmContent || "",
            utm_term: utmTerm || "",
            utm_id: utmId || "",
            click_id_source: clickIdSource,
            click_id: clickId,
            landing_page: window.location.pathname,
        };
    }

    function hasRetargetingConnector() {
        return Boolean(
            retargetingConfig.metaPixelId ||
            retargetingConfig.googleAdsId ||
            retargetingConfig.tiktokPixelId ||
            retargetingConfig.linkedinPartnerId ||
            retargetingConfig.pinterestTagId
        );
    }

    function canUseRetargeting() {
        if (!retargetingEnabled || !hasRetargetingConnector()) {
            return false;
        }

        return debugMode || hasOfferConsent();
    }

    function loadExternalScript(id, src) {
        if (document.getElementById(id)) {
            return;
        }

        const scriptElement = document.createElement("script");
        scriptElement.id = id;
        scriptElement.async = true;
        scriptElement.src = src;

        const firstScript = document.getElementsByTagName("script")[0];

        if (firstScript && firstScript.parentNode) {
            firstScript.parentNode.insertBefore(scriptElement, firstScript);
        } else {
            document.head.appendChild(scriptElement);
        }
    }

    function ensureMetaPixel() {
        const pixelId = retargetingConfig.metaPixelId;

        if (!pixelId || retargetingState.metaInitialized) {
            return;
        }

        if (!window.fbq) {
            const fbq = function () {
                if (fbq.callMethod) {
                    fbq.callMethod.apply(fbq, arguments);
                } else {
                    fbq.queue.push(arguments);
                }
            };

            fbq.push = fbq;
            fbq.loaded = true;
            fbq.version = "2.0";
            fbq.queue = [];
            window.fbq = fbq;
            window._fbq = fbq;
            loadExternalScript("predictneed-meta-pixel", "https://connect.facebook.net/en_US/fbevents.js");
        }

        window.fbq("init", pixelId);
        retargetingState.metaInitialized = true;
    }

    function ensureGoogleAdsTag() {
        const adsId = retargetingConfig.googleAdsId;

        if (!adsId || retargetingState.googleInitialized) {
            return;
        }

        window.dataLayer = window.dataLayer || [];

        if (!window.gtag) {
            window.gtag = function () {
                window.dataLayer.push(arguments);
            };
        }

        loadExternalScript(
            "predictneed-google-ads-tag",
            "https://www.googletagmanager.com/gtag/js?id=" + encodeURIComponent(adsId)
        );
        window.gtag("js", new Date());
        window.gtag("config", adsId, { send_page_view: false });
        retargetingState.googleInitialized = true;
    }

    function ensureTikTokPixel() {
        const pixelId = retargetingConfig.tiktokPixelId;

        if (!pixelId || retargetingState.tiktokInitialized) {
            return;
        }

        if (!window.ttq) {
            const ttq = [];
            ttq.methods = [
                "page",
                "track",
                "identify",
                "instances",
                "debug",
                "on",
                "off",
                "once",
                "ready",
                "alias",
                "group",
                "enableCookie",
                "disableCookie",
            ];
            ttq.setAndDefer = function (target, method) {
                target[method] = function () {
                    target.push([method].concat(Array.prototype.slice.call(arguments, 0)));
                };
            };

            for (let index = 0; index < ttq.methods.length; index += 1) {
                ttq.setAndDefer(ttq, ttq.methods[index]);
            }

            ttq.load = function (id) {
                loadExternalScript(
                    "predictneed-tiktok-pixel-" + id,
                    "https://analytics.tiktok.com/i18n/pixel/events.js?sdkid=" + encodeURIComponent(id) + "&lib=ttq"
                );
            };

            window.ttq = ttq;
        }

        window.ttq.load(pixelId);
        retargetingState.tiktokInitialized = true;
    }

    function ensureLinkedInInsight() {
        const partnerId = retargetingConfig.linkedinPartnerId;

        if (!partnerId || retargetingState.linkedinInitialized) {
            return;
        }

        window._linkedin_data_partner_ids = window._linkedin_data_partner_ids || [];

        if (!window._linkedin_data_partner_ids.includes(partnerId)) {
            window._linkedin_data_partner_ids.push(partnerId);
        }

        window._linkedin_partner_id = partnerId;
        loadExternalScript("predictneed-linkedin-insight", "https://snap.licdn.com/li.lms-analytics/insight.min.js");
        retargetingState.linkedinInitialized = true;
    }

    function ensurePinterestTag() {
        const tagId = retargetingConfig.pinterestTagId;

        if (!tagId || retargetingState.pinterestInitialized) {
            return;
        }

        if (!window.pintrk) {
            const pintrk = function () {
                pintrk.queue.push(Array.prototype.slice.call(arguments));
            };

            pintrk.queue = [];
            pintrk.version = "3.0";
            window.pintrk = pintrk;
            loadExternalScript("predictneed-pinterest-tag", "https://s.pinimg.com/ct/core.js");
        }

        window.pintrk("load", tagId);
        retargetingState.pinterestInitialized = true;
    }

    function initializeRetargetingConnectors() {
        if (!canUseRetargeting()) {
            return false;
        }

        ensureMetaPixel();
        ensureGoogleAdsTag();
        ensureTikTokPixel();
        ensureLinkedInInsight();
        ensurePinterestTag();
        return true;
    }

    function getRetargetingPayload() {
        return {
            page_title: document.title,
            page_path: window.location.pathname,
            page_location: window.location.href,
            content_name: document.title,
            content_category: window.location.pathname,
            content_ids: [window.location.pathname],
            content_type: "product",
        };
    }

    function trackRetargetingPage() {
        if (retargetingPageTracked || !initializeRetargetingConnectors()) {
            return;
        }

        const payload = getRetargetingPayload();

        if (retargetingConfig.metaPixelId && window.fbq) {
            window.fbq("track", "PageView");
            window.fbq("track", "ViewContent", {
                content_name: payload.content_name,
                content_category: payload.content_category,
                content_ids: payload.content_ids,
                content_type: payload.content_type,
            });
        }

        if (retargetingConfig.googleAdsId && window.gtag) {
            window.gtag("event", "page_view", {
                send_to: retargetingConfig.googleAdsId,
                page_title: payload.page_title,
                page_path: payload.page_path,
                page_location: payload.page_location,
            });
            window.gtag("event", "view_item", {
                send_to: retargetingConfig.googleAdsId,
                items: [{ item_name: payload.content_name }],
            });
        }

        if (retargetingConfig.tiktokPixelId && window.ttq) {
            window.ttq.page();
            window.ttq.track("ViewContent", {
                content_name: payload.content_name,
                content_type: payload.content_type,
            });
        }

        if (retargetingConfig.pinterestTagId && window.pintrk) {
            window.pintrk("page");
            window.pintrk("track", "pagevisit", {
                property: "PredictNeed IA",
                line_items: [{ product_name: payload.content_name }],
            });
        }

        retargetingPageTracked = true;
    }

    function trackRetargetingLead() {
        if (!initializeRetargetingConnectors()) {
            return;
        }

        const payload = getRetargetingPayload();

        if (retargetingConfig.metaPixelId && window.fbq) {
            window.fbq("track", "Lead", {
                content_name: payload.content_name,
                content_category: payload.content_category,
            });
        }

        if (retargetingConfig.googleAdsId && window.gtag) {
            window.gtag("event", "generate_lead", {
                send_to: retargetingConfig.googleAdsId,
                page_path: payload.page_path,
            });

            if (retargetingConfig.googleAdsConversionLabel) {
                window.gtag("event", "conversion", {
                    send_to: retargetingConfig.googleAdsId + "/" + retargetingConfig.googleAdsConversionLabel,
                });
            }
        }

        if (retargetingConfig.tiktokPixelId && window.ttq) {
            window.ttq.track("SubmitForm", {
                content_name: payload.content_name,
            });
        }

        if (retargetingConfig.linkedinConversionId && window.lintrk) {
            window.lintrk("track", {
                conversion_id: retargetingConfig.linkedinConversionId,
            });
        }

        if (retargetingConfig.pinterestTagId && window.pintrk) {
            window.pintrk("track", "lead", {
                lead_type: "formulaire PredictNeed IA",
            });
        }
    }

    function sendEvent(typeEvenement, page, valeur) {
        const currentSessionId = getSessionId();

        if (!currentSessionId) {
            return;
        }

        const infosAppareil = detecterAppareil();
        const infosSource = detecterSource();

        fetch(apiUrl, {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
            },
            body: JSON.stringify({
                api_key: apiKey,
                session_id: currentSessionId,
                consentement_tracking: true,
                type_evenement: typeEvenement,
                page: page,
                valeur: valeur,
                user_agent: navigator.userAgent,
                referer: document.referrer,
                appareil: infosAppareil.appareil,
                navigateur: infosAppareil.navigateur,
                systeme_exploitation: infosAppareil.systeme_exploitation,
                source_visite: infosSource.source_visite,
                utm_source: infosSource.utm_source,
                utm_medium: infosSource.utm_medium,
                utm_campaign: infosSource.utm_campaign,
                utm_content: infosSource.utm_content,
                utm_term: infosSource.utm_term,
                utm_id: infosSource.utm_id,
                click_id_source: infosSource.click_id_source,
                click_id: infosSource.click_id,
                landing_page: infosSource.landing_page,
                est_mobile: infosAppareil.est_mobile,
                est_tablette: infosAppareil.est_tablette,
                est_desktop: infosAppareil.est_desktop,
            })
        })
            .then(function (response) {
                return response.json();
            })
            .then(function (data) {
                if (data.success) {
                    latestPredictionResult = data;
                    tryShowOfferAfterEngagement();
                }

                if (data.success && shouldShowOffer(data)) {
                    showOfferPopup(data);
                }
            })
            .catch(function (error) {
                console.warn("PredictNeed IA : erreur tracking", error);
            });
    }

    function sendElapsedTime() {
        if (!hasAnalyticsConsent() && !debugMode) {
            return;
        }

        const totalSeconds = Math.round((Date.now() - startTime) / 1000);
        const difference = totalSeconds - elapsedSecondsSent;

        if (difference >= 10) {
            elapsedSecondsSent = totalSeconds;

            sendEvent(
                "temps",
                window.location.pathname,
                difference + " secondes"
            );
        }
    }

    function startTracking() {
        if (hasStartedTracking || (!hasAnalyticsConsent() && !debugMode)) {
            return;
        }

        hasStartedTracking = true;
        initializeOfferTrigger();

        sendEvent(
            "page_vue",
            window.location.pathname,
            document.title
        );
    }

    document.addEventListener("click", function (event) {
        if (!hasStartedTracking || (!hasAnalyticsConsent() && !debugMode)) {
            return;
        }

        if (event.target.closest("#predictneed-popup") || event.target.closest("#predictneed-consent-banner") || event.target.closest("#predictneed-consent-panel")) {
            return;
        }

        const clickedElement = event.target.closest("a, button");

        if (clickedElement) {
            const text = clickedElement.innerText || clickedElement.href || "clic";

            sendEvent(
                "clic",
                window.location.pathname,
                text
            );
        }
    });

    setInterval(sendElapsedTime, 10000);

    window.addEventListener("beforeunload", function () {
        const currentSessionId = getSessionId();

        if (!currentSessionId || (!hasAnalyticsConsent() && !debugMode)) {
            return;
        }

        const elapsed = Math.round((Date.now() - startTime) / 1000);
        const infosAppareil = detecterAppareil();
        const infosSource = detecterSource();

        const data = {
            api_key: apiKey,
            session_id: currentSessionId,
            consentement_tracking: true,
            type_evenement: "temps",
            page: window.location.pathname,
            valeur: elapsed + " secondes",
            user_agent: navigator.userAgent,
            referer: document.referrer,
            appareil: infosAppareil.appareil,
            navigateur: infosAppareil.navigateur,
            systeme_exploitation: infosAppareil.systeme_exploitation,
            source_visite: infosSource.source_visite,
            utm_source: infosSource.utm_source,
            utm_medium: infosSource.utm_medium,
            utm_campaign: infosSource.utm_campaign,
            utm_content: infosSource.utm_content,
            utm_term: infosSource.utm_term,
            utm_id: infosSource.utm_id,
            click_id_source: infosSource.click_id_source,
            click_id: infosSource.click_id,
            landing_page: infosSource.landing_page,
            est_mobile: infosAppareil.est_mobile,
            est_tablette: infosAppareil.est_tablette,
            est_desktop: infosAppareil.est_desktop,
        };

        const blob = new Blob(
            [JSON.stringify(data)],
            { type: "application/json" }
        );

        navigator.sendBeacon(apiUrl, blob);
    });

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", function () {
            renderConsentBanner();
            startTracking();
            initializeOfferTrigger();
            trackRetargetingPage();
        });
    } else {
        renderConsentBanner();
        startTracking();
        initializeOfferTrigger();
        trackRetargetingPage();
    }
})();
