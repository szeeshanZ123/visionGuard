/**
 * VisionGuard AI - Client-Side Inspection Controller (Vanilla ES6+ JavaScript)
 * Communicates with Flask REST API (/api/inspect, /api/health)
 */

document.addEventListener("DOMContentLoaded", () => {
    // CSRF & Authentication State Management (Phase 4.6)
    let currentCsrfToken = document.querySelector('meta[name="csrf-token"]')?.getAttribute("content") || "";
    let currentUser = null; // { id, username, email, role, is_active }

    // Intercept window.fetch to automatically include credentials and X-CSRF-Token on mutating requests
    const originalFetch = window.fetch;
    window.fetch = async function (input, init = {}) {
        const options = Object.assign({}, init);
        const method = (options.method || "GET").toUpperCase();

        if (!options.credentials) {
            options.credentials = "same-origin";
        }

        if (["POST", "PATCH", "PUT", "DELETE"].includes(method) && currentCsrfToken) {
            if (options.headers instanceof Headers) {
                if (!options.headers.has("X-CSRF-Token")) {
                    options.headers.set("X-CSRF-Token", currentCsrfToken);
                }
            } else if (Array.isArray(options.headers)) {
                let hasCsrf = options.headers.some(pair => pair[0].toLowerCase() === "x-csrf-token");
                if (!hasCsrf) options.headers.push(["X-CSRF-Token", currentCsrfToken]);
            } else {
                options.headers = Object.assign({}, options.headers);
                if (!options.headers["X-CSRF-Token"] && !options.headers["x-csrf-token"]) {
                    options.headers["X-CSRF-Token"] = currentCsrfToken;
                }
            }
        }

        const response = await originalFetch(input, options);

        if (response.status === 401) {
            let url = "";
            if (typeof input === "string") {
                url = input;
            } else if (input && input.url) {
                url = input.url;
            }
            // If the 401 is from a protected API rather than auth check/action itself, handle session expiry
            if (!url.includes("/api/auth/login") && !url.includes("/api/auth/status") && !url.includes("/api/auth/setup-admin")) {
                handleSessionExpired();
            }
        } else if (response.status === 403) {
            try {
                const clone = response.clone();
                const errData = await clone.json();
                if (errData && errData.error_code === "CSRF_TOKEN_INVALID") {
                    const statusRes = await originalFetch("/api/auth/status");
                    if (statusRes.ok) {
                        const statusData = await statusRes.json();
                        if (statusData.csrf_token) {
                            currentCsrfToken = statusData.csrf_token;
                        }
                    }
                }
            } catch (_) {}
        }

        return response;
    };

    let isHandlingSessionExpiry = false;

    function setAuthModalMode(mode) {
        const titleElem = document.getElementById("authModalTitle");
        const setupNotice = document.getElementById("setupRequiredNotice");
        const authTabsNav = document.getElementById("authTabsNav");
        const authTabLoginBtn = document.getElementById("authTabLoginBtn");
        const authTabRegisterBtn = document.getElementById("authTabRegisterBtn");
        const loginFrm = document.getElementById("loginForm");
        const registerFrm = document.getElementById("registerForm");
        const setupFrm = document.getElementById("setupAdminForm");
        const loginUser = document.getElementById("loginUsername");
        const registerUser = document.getElementById("registerUsername");
        const setupUser = document.getElementById("setupAdminUsername");

        if (mode === "setup") {
            if (titleElem) titleElem.textContent = "🚀 First-Time Administrator Setup";
            if (authTabsNav) authTabsNav.style.display = "none";
            if (setupNotice) setupNotice.style.display = "flex";
            if (setupFrm) setupFrm.style.display = "block";
            if (loginFrm) loginFrm.style.display = "none";
            if (registerFrm) registerFrm.style.display = "none";
            if (setupUser) setupUser.focus();
        } else if (mode === "register") {
            if (titleElem) titleElem.textContent = "📝 Create Citizen Account";
            if (authTabsNav) authTabsNav.style.display = "flex";
            if (authTabLoginBtn) authTabLoginBtn.classList.remove("active");
            if (authTabRegisterBtn) authTabRegisterBtn.classList.add("active");
            if (setupNotice) setupNotice.style.display = "none";
            if (setupFrm) setupFrm.style.display = "none";
            if (loginFrm) loginFrm.style.display = "none";
            if (registerFrm) registerFrm.style.display = "block";
            if (registerUser) registerUser.focus();
        } else {
            if (titleElem) titleElem.textContent = "🔐 Sign In to VisionGuard AI";
            if (authTabsNav) authTabsNav.style.display = "flex";
            if (authTabLoginBtn) authTabLoginBtn.classList.add("active");
            if (authTabRegisterBtn) authTabRegisterBtn.classList.remove("active");
            if (setupNotice) setupNotice.style.display = "none";
            if (setupFrm) setupFrm.style.display = "none";
            if (loginFrm) loginFrm.style.display = "block";
            if (registerFrm) registerFrm.style.display = "none";
            if (loginUser) loginUser.focus();
        }
    }

    async function openAuthModal(preferredMode) {
        const modal = document.getElementById("authModal");
        if (!modal) return;

        // Show modal immediately for instantaneous visual feedback
        modal.style.display = "flex";

        const errorAlert = document.getElementById("authErrorAlert");
        const loginUser = document.getElementById("loginUsername");
        const loginPass = document.getElementById("loginPassword");
        const registerUser = document.getElementById("registerUsername");
        const registerEmail = document.getElementById("registerEmail");
        const registerPass = document.getElementById("registerPassword");
        const registerPassConfirm = document.getElementById("registerPasswordConfirm");
        const setupUser = document.getElementById("setupAdminUsername");
        const setupEmail = document.getElementById("setupAdminEmail");
        const setupPass = document.getElementById("setupAdminPassword");

        if (errorAlert) {
            errorAlert.style.display = "none";
            errorAlert.textContent = "";
        }
        if (loginUser) loginUser.value = "";
        if (loginPass) loginPass.value = "";
        if (registerUser) registerUser.value = "";
        if (registerEmail) registerEmail.value = "";
        if (registerPass) registerPass.value = "";
        if (registerPassConfirm) registerPassConfirm.value = "";
        if (setupUser) setupUser.value = "";
        if (setupEmail) setupEmail.value = "";
        if (setupPass) setupPass.value = "";

        // Synchronous initial mode selection based on known state
        const initialShowSetup = preferredMode === "setup" || (Boolean(window.__lastRequiresSetup) && preferredMode !== "login" && preferredMode !== "register");
        if (initialShowSetup) {
            setAuthModalMode("setup");
        } else if (preferredMode === "register") {
            setAuthModalMode("register");
        } else {
            setAuthModalMode("login");
        }

        // Fresh check against backend
        let requiresSetup = Boolean(window.__lastRequiresSetup);
        try {
            const res = await fetch("/api/auth/status");
            const data = await res.json();
            if (data.csrf_token) currentCsrfToken = data.csrf_token;
            requiresSetup = Boolean(data.requires_setup);
            window.__lastRequiresSetup = requiresSetup;
        } catch (_) {}

        const showSetup = preferredMode === "setup" || (requiresSetup && preferredMode !== "login" && preferredMode !== "register");
        if (showSetup) {
            setAuthModalMode("setup");
        } else if (preferredMode === "register") {
            setAuthModalMode("register");
        } else {
            setAuthModalMode("login");
        }
    }

    // Expose helpers globally for accessibility and debug
    window.openAuthModal = openAuthModal;
    window.closeAuthModal = closeAuthModal;

    function closeAuthModal() {
        const modal = document.getElementById("authModal");
        if (modal) {
            modal.style.display = "none";
        }
        const errorAlert = document.getElementById("authErrorAlert");
        if (errorAlert) {
            errorAlert.style.display = "none";
            errorAlert.textContent = "";
        }
    }

    function handleSessionExpired(msg = "Your session has expired. Please sign in again.") {
        if (isHandlingSessionExpiry) return;
        isHandlingSessionExpiry = true;

        currentUser = null;
        updateAuthUI({ authenticated: false, requires_setup: false });
        renderGuestDashboard();
        openAuthModal("login");

        const errorAlert = document.getElementById("authErrorAlert");
        if (errorAlert) {
            errorAlert.textContent = msg;
            errorAlert.style.display = "block";
        }

        setTimeout(() => {
            isHandlingSessionExpiry = false;
        }, 1500);
    }

    function bindGuestLoginButtons() {
        document.querySelectorAll(".guest-login-btn").forEach(btn => {
            btn.onclick = (e) => {
                e.preventDefault();
                openAuthModal();
            };
        });
    }

    function renderGuestDashboard() {
        const dashTotal = document.getElementById("dashTotalInspections");
        const dashDefects = document.getElementById("dashTotalDefects");
        const dashOpen = document.getElementById("dashOpenRecords");
        const dashProg = document.getElementById("dashInProgressRecords");
        const dashRes = document.getElementById("dashResolvedRecords");
        const dashOverdue = document.getElementById("dashOverdueCount");
        const dashDueToday = document.getElementById("dashDueTodayCount");
        const dashUpcoming = document.getElementById("dashUpcomingCount");
        const dashResolvedMaint = document.getElementById("dashResolvedMaintCount");
        const dashNoDeadlines = document.getElementById("dashNoDeadlinesCount");
        const maintActionable = document.getElementById("maintenanceActionableBadge");
        const maintBanner = document.getElementById("maintenanceAlertBanner");
        const recordsBadge = document.getElementById("recordsCountBadgeHeader");
        const mapBadge = document.getElementById("mapCountBadgeHeader");
        const defBadge = document.getElementById("dashDefectsTotalBadge");
        const defEmpty = document.getElementById("dashDefectsEmptyState");
        const catBars = document.getElementById("dashCategoryBarsContainer");
        const segOpen = document.getElementById("segmentOpen");
        const segProg = document.getElementById("segmentProgress");
        const segRes = document.getElementById("segmentResolved");
        const legOpenCount = document.getElementById("legendOpenCount");
        const legOpenPct = document.getElementById("legendOpenPct");
        const legProgCount = document.getElementById("legendProgressCount");
        const legProgPct = document.getElementById("legendProgressPct");
        const legResCount = document.getElementById("legendResolvedCount");
        const legResPct = document.getElementById("legendResolvedPct");
        const recentTable = document.getElementById("dashRecentTable");
        const recentEmpty = document.getElementById("dashEmptyState");
        const recentBody = document.getElementById("dashRecentTableBody");

        if (dashTotal) dashTotal.textContent = "0";
        if (dashDefects) dashDefects.textContent = "0";
        if (dashOpen) dashOpen.textContent = "0";
        if (dashProg) dashProg.textContent = "0";
        if (dashRes) dashRes.textContent = "0";

        if (dashOverdue) dashOverdue.textContent = "0";
        if (dashDueToday) dashDueToday.textContent = "0";
        if (dashUpcoming) dashUpcoming.textContent = "0";
        if (dashResolvedMaint) dashResolvedMaint.textContent = "0";
        if (dashNoDeadlines) dashNoDeadlines.textContent = "0";
        if (maintActionable) maintActionable.textContent = "0 Actionable";

        if (maintBanner) maintBanner.style.display = "none";
        if (recordsBadge) recordsBadge.textContent = "0";
        if (mapBadge) mapBadge.textContent = "0";

        if (defBadge) defBadge.textContent = "0 Total Distress Instances";
        if (defEmpty) defEmpty.style.display = "block";
        if (catBars) catBars.style.display = "none";

        if (segOpen) segOpen.style.width = "0%";
        if (segProg) segProg.style.width = "0%";
        if (segRes) segRes.style.width = "0%";
        if (legOpenCount) legOpenCount.textContent = "0";
        if (legOpenPct) legOpenPct.textContent = "0%";
        if (legProgCount) legProgCount.textContent = "0";
        if (legProgPct) legProgPct.textContent = "0%";
        if (legResCount) legResCount.textContent = "0";
        if (legResPct) legResPct.textContent = "0%";

        if (recentTable) recentTable.style.display = "table";
        if (recentEmpty) recentEmpty.style.display = "none";
        if (recentBody) {
            recentBody.innerHTML = `<tr>
                <td colspan="8" style="text-align: center; padding: 2.5rem; color: var(--text-muted);">
                    <div style="font-size: 1.1rem; font-weight: 600; margin-bottom: 0.5rem; color: var(--text-primary);">🔒 Authentication Required</div>
                    <div style="font-size: 0.9rem; margin-bottom: 1.25rem;">Sign in to view recent road inspection telemetry, defect analytics, and maintenance metrics.</div>
                    <button type="button" class="btn btn-sm btn-primary guest-login-btn">🔐 Sign In</button>
                </td>
            </tr>`;
            bindGuestLoginButtons();
        }
    }

    // DOM Elements
    const dbStatusBadge = document.getElementById("dbStatusBadge");
    const modelStatusBadge = document.getElementById("modelStatusBadge");
    const systemNoticeBanner = document.getElementById("systemNoticeBanner");
    const systemNoticeTitle = document.getElementById("systemNoticeTitle");
    const systemNoticeMsg = document.getElementById("systemNoticeMsg");
    const systemNoticeInstructions = document.getElementById("systemNoticeInstructions");

    const guidelinesToggle = document.getElementById("guidelinesToggle");
    const guidelinesBody = document.getElementById("guidelinesBody");

    const dropZone = document.getElementById("dropZone");
    const fileInput = document.getElementById("imageFileInput");
    const browseBtn = document.getElementById("browseBtn");
    const uploadPrompt = document.getElementById("uploadPrompt");
    const previewStrip = document.getElementById("previewStrip");
    const clientPreviewImg = document.getElementById("clientPreviewImg");
    const selectedFileName = document.getElementById("selectedFileName");
    const selectedFileSize = document.getElementById("selectedFileSize");
    const removeFileBtn = document.getElementById("removeFileBtn");

    const confSlider = document.getElementById("confSlider");
    const confValDisplay = document.getElementById("confValDisplay");
    const inspectBtn = document.getElementById("inspectBtn");
    const inspectSpinner = document.getElementById("inspectSpinner");

    const resultsContainer = document.getElementById("resultsContainer");
    const resultsCountBadge = document.getElementById("resultsCountBadge");
    const originalDisplayImg = document.getElementById("originalDisplayImg");
    const annotatedDisplayImg = document.getElementById("annotatedDisplayImg");
    const origDimCaption = document.getElementById("origDimCaption");
    const modelCheckpointCaption = document.getElementById("modelCheckpointCaption");

    const metricDefectCount = document.getElementById("metricDefectCount");
    const metricDefectTypes = document.getElementById("metricDefectTypes");
    const metricTopConf = document.getElementById("metricTopConf");
    const metricModelName = document.getElementById("metricModelName");
    const metricInspectionMode = document.getElementById("metricInspectionMode");
    const metricModeCaption = document.getElementById("metricModeCaption");

    const metaFilename = document.getElementById("metaFilename");
    const metaFormat = document.getElementById("metaFormat");
    const metaDimensions = document.getElementById("metaDimensions");
    const metaAspectRatio = document.getElementById("metaAspectRatio");
    const metaChannels = document.getElementById("metaChannels");
    const metaFileSize = document.getElementById("metaFileSize");

    const detectionsTableBody = document.getElementById("detectionsTableBody");

    // Target Workflow & Domain Elements
    let selectedDomain = "road";
    let lastHealthData = null;
    const domainRoadBtn = document.getElementById("domainRoadBtn");
    const domainHomeBtn = document.getElementById("domainHomeBtn");
    const cameraFileInput = document.getElementById("cameraFileInput");
    const cameraBtn = document.getElementById("cameraBtn");
    const uploadPromptIcon = document.getElementById("uploadPromptIcon");
    const uploadPromptHeading = document.getElementById("uploadPromptHeading");
    const uploadPromptSubtext = document.getElementById("uploadPromptSubtext");
    const guidelinesDistressHeading = document.getElementById("guidelinesDistressHeading");
    const guidelinesDistressClasses = document.getElementById("guidelinesDistressClasses");
    const saveLocationLabel = document.getElementById("saveLocationLabel");
    const resultsDomainBadge = document.getElementById("resultsDomainBadge");
    const originalImageTitle = document.getElementById("originalImageTitle");
    const detectionsTableHeading = document.getElementById("detectionsTableHeading");
    const disclaimerHeading = document.getElementById("disclaimerHeading");
    const disclaimerText = document.getElementById("disclaimerText");

    // Phase 2: Location & Address Elements
    const btnUseCurrentLocation = document.getElementById("btnUseCurrentLocation");
    const btnUseCurrentLocationText = document.getElementById("btnUseCurrentLocationText");
    const locationSpinner = document.getElementById("locationSpinner");
    const btnClearLocation = document.getElementById("btnClearLocation");
    const locationStatusBanner = document.getElementById("locationStatusBanner");
    const locationStatusIcon = document.getElementById("locationStatusIcon");
    const locationStatusText = document.getElementById("locationStatusText");
    const inspLocationRoad = document.getElementById("inspLocationRoad");
    const inspLocationRoadLabel = document.getElementById("inspLocationRoadLabel");
    const inspLocationArea = document.getElementById("inspLocationArea");
    const inspLocationAreaLabel = document.getElementById("inspLocationAreaLabel");
    const inspLocationCity = document.getElementById("inspLocationCity");
    const inspLocationLat = document.getElementById("inspLocationLat");
    const inspLocationLon = document.getElementById("inspLocationLon");
    const inspLocationNotes = document.getElementById("inspLocationNotes");
    const locationCardTitle = document.getElementById("locationCardTitle");
    const locationCardSubtitle = document.getElementById("locationCardSubtitle");
    const confirmedLocationBar = document.getElementById("confirmedLocationBar");
    const confirmedLocationIndicator = document.getElementById("confirmedLocationIndicator");
    const confirmedLocationDisplay = document.getElementById("confirmedLocationDisplay");
    const btnConfirmLocation = document.getElementById("btnConfirmLocation");

    let currentFile = null;

    function updateModelStatusDisplay() {
        if (!lastHealthData) return;
        const isHome = selectedDomain === "home";
        const modelInfo = isHome ? (lastHealthData.home_model || {}) : (lastHealthData.road_model || lastHealthData.model || {});

        if (modelInfo.loaded) {
            modelStatusBadge.textContent = isHome ? "Model: Home YOLOv8 (Loaded)" : "Model: Road YOLOv8n (Loaded)";
            modelStatusBadge.className = "badge badge-success";
            systemNoticeBanner.style.display = "none";
        } else {
            modelStatusBadge.textContent = isHome ? "Model: Home Checkpoint Missing" : "Model: Road Checkpoint Missing";
            modelStatusBadge.className = "badge badge-warning";

            systemNoticeTitle.textContent = isHome 
                ? "Home Defect Model Checkpoint Awaiting Configuration" 
                : "Road Defect Model Checkpoint Awaiting Configuration";
            systemNoticeMsg.textContent = modelInfo.status_message || (isHome ? "Checkpoint 'home_best.pt' not loaded." : "Checkpoint 'best.pt' not loaded.");
            systemNoticeInstructions.textContent = isHome
                ? "Setup Steps:\n1. Download 'home_best.pt' from your Google Drive ('VisionGuard_Artifacts/home_best.pt').\n2. Place the file at: visionGuard/ai/models/home_best.pt\n3. Reload this page or call POST /api/reload-model?domain=home."
                : "Setup Steps:\n1. Download 'best.pt' from your Google Drive ('VisionGuard_Artifacts/best.pt') or Colab export.\n2. Place the file at: visionGuard/ai/models/best.pt\n3. Reload this page or call POST /api/reload-model?domain=road.";
            systemNoticeInstructions.style.display = "block";
            systemNoticeBanner.style.display = "flex";
        }
    }

    function setInspectionDomain(domain) {
        selectedDomain = domain === "home" ? "home" : "road";
        const isHome = selectedDomain === "home";

        if (domainRoadBtn) {
            domainRoadBtn.classList.toggle("active", !isHome);
            domainRoadBtn.setAttribute("aria-pressed", (!isHome).toString());
        }
        if (domainHomeBtn) {
            domainHomeBtn.classList.toggle("active", isHome);
            domainHomeBtn.setAttribute("aria-pressed", isHome.toString());
        }

        if (uploadPromptIcon) uploadPromptIcon.textContent = isHome ? "🏠" : "🛣️";
        if (uploadPromptHeading) {
            uploadPromptHeading.textContent = isHome 
                ? "Drag & Drop home or building image here, or choose an option:" 
                : "Drag & Drop road image here, or choose an option:";
        }
        if (uploadPromptSubtext) {
            uploadPromptSubtext.textContent = isHome
                ? "Supported: JPG, PNG, WEBP • Max Size: 15 MB • Routing to Home Model"
                : "Supported: JPG, PNG, WEBP • Max Size: 15 MB • Routing to Road Model";
        }

        if (guidelinesDistressHeading) {
            guidelinesDistressHeading.textContent = isHome ? "Defect Classes (Home & Building)" : "Distress Classes (Road Surface)";
        }
        if (guidelinesDistressClasses) {
            guidelinesDistressClasses.textContent = isHome
                ? "wall_crack, damp_or_water_damage, peeling_paint_or_plaster, spalling_or_surface_damage"
                : "D00 (Longitudinal), D10 (Transverse), D20 (Alligator), D40 (Pothole)";
        }

        if (saveLocationLabel) {
            saveLocationLabel.innerHTML = isHome
                ? 'Building / Structure / Room <span class="text-muted">(Optional)</span>:'
                : 'Road / Highway / Corridor <span class="text-muted">(Optional)</span>:';
        }
        if (saveRoadNameInput) {
            saveRoadNameInput.placeholder = isHome
                ? "e.g. Block B, Apartment 302, Exterior Facade"
                : "e.g. Western Express Highway, KM 14";
        }
        if (saveAreaInput) {
            saveAreaInput.placeholder = isHome
                ? "e.g. Living Room / 2nd Floor / Basement"
                : "e.g. Bandra West / Sector 4";
        }

        // Phase 2 Location Card Domain Customization
        if (inspLocationRoadLabel) {
            inspLocationRoadLabel.innerHTML = isHome
                ? 'Building / Structure / Room <span class="text-muted">(Optional)</span>:'
                : 'Road / Street / Corridor <span class="text-muted">(Optional)</span>:';
        }
        if (inspLocationRoad) {
            inspLocationRoad.placeholder = isHome
                ? "e.g. Block B, Apartment 302, Exterior Facade"
                : "e.g. Western Express Highway, KM 14";
        }
        if (inspLocationAreaLabel) {
            inspLocationAreaLabel.innerHTML = isHome
                ? 'Floor / Wing / Specific Area <span class="text-muted">(Optional)</span>:'
                : 'Area / Neighborhood / Landmark <span class="text-muted">(Optional)</span>:';
        }
        if (inspLocationArea) {
            inspLocationArea.placeholder = isHome
                ? "e.g. Living Room / 2nd Floor / Basement"
                : "e.g. Bandra West / Sector 4";
        }
        if (locationCardSubtitle) {
            locationCardSubtitle.textContent = isHome
                ? "Pinpoint the building or room where this structural defect was observed."
                : "Pinpoint where this road surface defect was observed so repair teams can navigate to the exact hazard.";
        }
        updateConfirmedLocationDisplay(false);

        updateModelStatusDisplay();
    }

    if (domainRoadBtn) {
        domainRoadBtn.addEventListener("click", () => setInspectionDomain("road"));
    }
    if (domainHomeBtn) {
        domainHomeBtn.addEventListener("click", () => setInspectionDomain("home"));
    }

    // -------------------------------------------------------------------------
    // Phase 2: GPS Location & Manual Address Handlers
    // -------------------------------------------------------------------------
    function showLocationStatus(type, message) {
        if (!locationStatusBanner || !locationStatusText) return;
        locationStatusBanner.className = `location-status-banner status-${type}`;
        if (locationStatusIcon) {
            if (type === "success") locationStatusIcon.textContent = "✅";
            else if (type === "warning") locationStatusIcon.textContent = "⚠️";
            else if (type === "danger") locationStatusIcon.textContent = "❌";
            else locationStatusIcon.textContent = "ℹ️";
        }
        locationStatusText.textContent = message;
        locationStatusBanner.style.display = "flex";
    }

    function hideLocationStatus() {
        if (locationStatusBanner) locationStatusBanner.style.display = "none";
    }

    function updateConfirmedLocationDisplay(wasExplicitlyClicked) {
        if (!confirmedLocationDisplay) return;

        const road = inspLocationRoad ? inspLocationRoad.value.trim() : "";
        const area = inspLocationArea ? inspLocationArea.value.trim() : "";
        const city = inspLocationCity ? inspLocationCity.value.trim() : "";
        const latStr = inspLocationLat ? inspLocationLat.value.trim() : "";
        const lonStr = inspLocationLon ? inspLocationLon.value.trim() : "";
        const notes = inspLocationNotes ? inspLocationNotes.value.trim() : "";

        const hasAnyInput = Boolean(road || area || city || latStr || lonStr || notes);

        if (btnClearLocation) {
            btnClearLocation.style.display = hasAnyInput ? "inline-block" : "none";
        }

        let addressParts = [];
        if (road) addressParts.push(road);
        if (area) addressParts.push(area);
        if (city) addressParts.push(city);
        const addressText = addressParts.join(", ");

        let coordsText = "";
        let hasValidCoords = false;
        if (latStr !== "" || lonStr !== "") {
            const latNum = parseFloat(latStr);
            const lonNum = parseFloat(lonStr);
            if (!isNaN(latNum) && !isNaN(lonNum) && latNum >= -90 && latNum <= 90 && lonNum >= -180 && lonNum <= 180) {
                coordsText = `${latNum.toFixed(4)}, ${lonNum.toFixed(4)}`;
                hasValidCoords = true;
            } else {
                coordsText = "Invalid range (-90 to +90, -180 to +180)";
            }
        }

        if (addressText && hasValidCoords) {
            confirmedLocationDisplay.textContent = `${addressText} • GPS: [${coordsText}]`;
            if (confirmedLocationIndicator) confirmedLocationIndicator.textContent = "📍";
            if (confirmedLocationBar) confirmedLocationBar.classList.add("confirmed-active");
        } else if (addressText) {
            confirmedLocationDisplay.textContent = addressText;
            if (confirmedLocationIndicator) confirmedLocationIndicator.textContent = "📍";
            if (confirmedLocationBar) confirmedLocationBar.classList.add("confirmed-active");
        } else if (hasValidCoords) {
            confirmedLocationDisplay.textContent = `GPS Pin: [${coordsText}] (No manual street address)`;
            if (confirmedLocationIndicator) confirmedLocationIndicator.textContent = "📍";
            if (confirmedLocationBar) confirmedLocationBar.classList.add("confirmed-active");
        } else if (hasAnyInput) {
            confirmedLocationDisplay.textContent = notes ? `Notes: ${notes}` : `Partial location information entered`;
            if (confirmedLocationIndicator) confirmedLocationIndicator.textContent = "📍";
            if (confirmedLocationBar) confirmedLocationBar.classList.add("confirmed-active");
        } else {
            confirmedLocationDisplay.textContent = "No location specified (Inspection will proceed without geotagging)";
            if (confirmedLocationIndicator) confirmedLocationIndicator.textContent = "⚪";
            if (confirmedLocationBar) confirmedLocationBar.classList.remove("confirmed-active");
        }

        if (wasExplicitlyClicked && btnConfirmLocation) {
            btnConfirmLocation.textContent = "✓ Location Confirmed";
            btnConfirmLocation.classList.remove("btn-outline-success");
            btnConfirmLocation.classList.add("btn-success");
            setTimeout(() => {
                btnConfirmLocation.textContent = "✓ Confirm Location";
                btnConfirmLocation.classList.remove("btn-success");
                btnConfirmLocation.classList.add("btn-outline-success");
            }, 2500);
        }
    }

    function clearLocationInputs() {
        if (inspLocationRoad) inspLocationRoad.value = "";
        if (inspLocationArea) inspLocationArea.value = "";
        if (inspLocationCity) inspLocationCity.value = "";
        if (inspLocationLat) inspLocationLat.value = "";
        if (inspLocationLon) inspLocationLon.value = "";
        if (inspLocationNotes) inspLocationNotes.value = "";
        hideLocationStatus();
        if (btnUseCurrentLocationText) btnUseCurrentLocationText.textContent = "Use My Current Location";
        if (locationSpinner) locationSpinner.style.display = "none";
        if (btnUseCurrentLocation) btnUseCurrentLocation.disabled = false;
        updateConfirmedLocationDisplay(false);
    }

    function requestBrowserGeolocation() {
        if (!navigator.geolocation) {
            showLocationStatus("info", "ℹ️ Geolocation is not supported by your current browser. You can enter the street address or building details manually below.");
            return;
        }

        if (locationSpinner) locationSpinner.style.display = "inline-block";
        if (btnUseCurrentLocation) btnUseCurrentLocation.disabled = true;
        if (btnUseCurrentLocationText) btnUseCurrentLocationText.textContent = "Acquiring GPS Position...";
        showLocationStatus("info", "📡 Requesting your current GPS coordinates from the browser...");

        navigator.geolocation.getCurrentPosition(
            (pos) => {
                if (locationSpinner) locationSpinner.style.display = "none";
                if (btnUseCurrentLocation) btnUseCurrentLocation.disabled = false;
                if (btnUseCurrentLocationText) btnUseCurrentLocationText.textContent = "Update GPS Location";

                const lat = pos.coords.latitude;
                const lon = pos.coords.longitude;
                const acc = Math.round(pos.coords.accuracy || 0);

                if (inspLocationLat) inspLocationLat.value = lat.toFixed(6);
                if (inspLocationLon) inspLocationLon.value = lon.toFixed(6);

                showLocationStatus("success", `✅ GPS Coordinates detected with accuracy of ±${acc}m! Latitude and Longitude updated below.`);
                updateConfirmedLocationDisplay(false);
            },
            (err) => {
                if (locationSpinner) locationSpinner.style.display = "none";
                if (btnUseCurrentLocation) btnUseCurrentLocation.disabled = false;
                if (btnUseCurrentLocationText) btnUseCurrentLocationText.textContent = "Use My Current Location";

                switch (err.code) {
                    case err.PERMISSION_DENIED:
                        showLocationStatus("warning", "⚠️ Location permission denied by your browser. You can enter the street address or landmark manually below — inspections are never blocked.");
                        break;
                    case err.POSITION_UNAVAILABLE:
                        showLocationStatus("warning", "⚠️ GPS position is unavailable on your device or network. Please enter the street address or building location manually below.");
                        break;
                    case err.TIMEOUT:
                        showLocationStatus("warning", "⏱️ Geolocation request timed out. Please retry or enter the address manually below.");
                        break;
                    default:
                        showLocationStatus("warning", `⚠️ Location request failed (${err.message || "Unknown error"}). You can enter the location manually below.`);
                        break;
                }
                updateConfirmedLocationDisplay(false);
            },
            {
                enableHighAccuracy: true,
                timeout: 10000,
                maximumAge: 60000,
            }
        );
    }

    if (btnUseCurrentLocation) {
        btnUseCurrentLocation.addEventListener("click", requestBrowserGeolocation);
    }
    if (btnClearLocation) {
        btnClearLocation.addEventListener("click", clearLocationInputs);
    }
    if (btnConfirmLocation) {
        btnConfirmLocation.addEventListener("click", () => updateConfirmedLocationDisplay(true));
    }
    [inspLocationRoad, inspLocationArea, inspLocationCity, inspLocationLat, inspLocationLon, inspLocationNotes].forEach(elem => {
        if (elem) {
            elem.addEventListener("input", () => updateConfirmedLocationDisplay(false));
            elem.addEventListener("change", () => updateConfirmedLocationDisplay(false));
        }
    });

    // 1. Initial Health Check
    async function checkHealth() {
        try {
            const res = await fetch("/api/health");
            const data = await res.json();
            lastHealthData = data;

            // DB status
            if (data.database && data.database.connected) {
                dbStatusBadge.textContent = "Database: Connected";
                dbStatusBadge.className = "badge badge-success";
            } else {
                dbStatusBadge.textContent = "Database: Offline";
                dbStatusBadge.className = "badge badge-danger";
            }

            // Model status display updated for active domain
            updateModelStatusDisplay();
        } catch (err) {
            dbStatusBadge.textContent = "Database: Error";
            dbStatusBadge.className = "badge badge-danger";
            modelStatusBadge.textContent = "Backend: Offline";
            modelStatusBadge.className = "badge badge-danger";
        }
    }

    checkHealth();

    // 2. Guidelines Accordion Toggle
    guidelinesToggle.addEventListener("click", () => {
        const isHidden = guidelinesBody.style.display === "none";
        guidelinesBody.style.display = isHidden ? "block" : "none";
        guidelinesToggle.querySelector(".toggle-indicator").textContent = isHidden ? "▲" : "▼";
    });

    // 3. File Selection & Drag-and-Drop
    browseBtn.addEventListener("click", (e) => {
        e.stopPropagation();
        fileInput.click();
    });

    if (cameraBtn && cameraFileInput) {
        cameraBtn.addEventListener("click", (e) => {
            e.stopPropagation();
            cameraFileInput.click();
        });
        cameraFileInput.addEventListener("change", (e) => {
            if (e.target.files && e.target.files.length > 0) {
                handleFileSelect(e.target.files[0]);
            }
        });
    }

    dropZone.addEventListener("click", () => {
        if (!currentFile) {
            fileInput.click();
        }
    });

    dropZone.addEventListener("dragover", (e) => {
        e.preventDefault();
        dropZone.classList.add("drag-over");
    });

    dropZone.addEventListener("dragleave", () => {
        dropZone.classList.remove("drag-over");
    });

    dropZone.addEventListener("drop", (e) => {
        e.preventDefault();
        dropZone.classList.remove("drag-over");
        if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
            handleFileSelect(e.dataTransfer.files[0]);
        }
    });

    fileInput.addEventListener("change", (e) => {
        if (e.target.files && e.target.files.length > 0) {
            handleFileSelect(e.target.files[0]);
        }
    });

    removeFileBtn.addEventListener("click", (e) => {
        e.stopPropagation();
        clearSelectedFile();
    });

    function formatBytes(bytes) {
        if (bytes < 1024) return bytes + " B";
        const kb = bytes / 1024;
        if (kb < 1024) return kb.toFixed(1) + " KB";
        return (kb / 1024).toFixed(2) + " MB";
    }

    function handleFileSelect(file) {
        const ext = file.name.split(".").pop().toLowerCase();
        const supported = ["jpg", "jpeg", "png", "bmp", "webp"];

        if (!supported.includes(ext)) {
            alert(`Unsupported format '.${ext}'. Please choose a JPG, PNG, or WEBP image.`);
            return;
        }

        const sizeMb = file.size / (1024 * 1024);
        if (sizeMb > 15.0) {
            alert(`File size (${sizeMb.toFixed(2)} MB) exceeds the 15 MB limit.`);
            return;
        }

        currentFile = file;
        selectedFileName.textContent = file.name;
        selectedFileSize.textContent = formatBytes(file.size);

        // Preview thumbnail
        const reader = new FileReader();
        reader.onload = (ev) => {
            clientPreviewImg.src = ev.target.result;
            uploadPrompt.style.display = "none";
            previewStrip.style.display = "flex";
            inspectBtn.disabled = false;
        };
        reader.readAsDataURL(file);
    }

    function clearSelectedFile() {
        currentFile = null;
        fileInput.value = "";
        if (cameraFileInput) cameraFileInput.value = "";
        clientPreviewImg.src = "";
        uploadPrompt.style.display = "block";
        previewStrip.style.display = "none";
        inspectBtn.disabled = true;
        resultsContainer.style.display = "none";
    }

    // 4. Confidence Threshold Slider Synchronization
    function syncSliderDisplay() {
        const val = parseFloat(confSlider.value);
        confValDisplay.textContent = isNaN(val) ? "0.25" : val.toFixed(2);
    }
    // Synchronize immediately on page load in case browser restored previous input state
    syncSliderDisplay();
    confSlider.addEventListener("input", syncSliderDisplay);
    confSlider.addEventListener("change", syncSliderDisplay);

    // 5. Run Inspection Action
    inspectBtn.addEventListener("click", async () => {
        if (!currentUser) {
            openAuthModal();
            return;
        }
        if (!currentFile) return;

        // UI State: Loading
        inspectBtn.disabled = true;
        inspectSpinner.style.display = "inline-block";
        inspectBtn.querySelector(".btn-text").textContent = selectedDomain === "home" 
            ? "Analyzing Building Imagery..." 
            : "Analyzing Road Imagery...";

        const activeThreshold = parseFloat(confSlider.value) || 0.25;
        const modeRadio = document.querySelector('input[name="inspectionMode"]:checked');
        const activeMode = modeRadio ? modeRadio.value : "standard";

        const formData = new FormData();
        formData.append("image", currentFile);
        formData.append("confidence_threshold", activeThreshold.toFixed(2));
        formData.append("inspection_mode", activeMode);
        formData.append("domain", selectedDomain);

        const controller = new AbortController();
        const timeoutId = setTimeout(() => controller.abort(), 60000); // 60s timeout

        let res;
        try {
            res = await fetch("/api/inspect", {
                method: "POST",
                body: formData,
                signal: controller.signal,
            });
        } catch (fetchErr) {
            clearTimeout(timeoutId);
            console.error("Fetch communication failure:", fetchErr);
            if (fetchErr.name === "AbortError") {
                alert("Request timed out: Inference took longer than 60 seconds. Please try again with a smaller image or higher confidence threshold.");
            } else {
                alert(`Network connection error: Unable to reach the VisionGuard AI backend at ${window.location.origin}.\n\nDetails: ${fetchErr.message || "Connection refused"}\n\nPlease verify that 'python app/server.py' is running in your terminal.`);
            }
            return;
        } finally {
            clearTimeout(timeoutId);
            inspectBtn.disabled = false;
            inspectSpinner.style.display = "none";
            inspectBtn.querySelector(".btn-text").textContent = "Run Defect Inspection";
        }

        // Parse response body safely
        let data = null;
        const contentType = res.headers.get("content-type") || "";
        if (contentType.includes("application/json")) {
            try {
                data = await res.json();
            } catch (jsonErr) {
                console.error("Failed to parse JSON response:", jsonErr);
            }
        }

        if (!res.ok) {
            let errorMsg = `Server responded with status HTTP ${res.status}`;
            if (data && data.message) {
                errorMsg = data.message;
            } else {
                try {
                    const rawText = await res.text();
                    if (rawText) errorMsg += `: ${rawText.substring(0, 150)}`;
                } catch (_) {}
            }
            handleApiError(res.status, data, errorMsg);
            return;
        }

        if (!data) {
            alert("Protocol Error: The server returned a 200 OK status without a valid JSON body.");
            return;
        }

        try {
            renderResults(data);
        } catch (renderErr) {
            console.error("UI rendering error:", renderErr);
            alert(`Rendering Error: Failed to display detection findings: ${renderErr.message}`);
        }
    });

    function handleApiError(status, data, message) {
        if (status === 503 || (data && (data.error_code === "MODEL_WEIGHTS_MISSING" || data.error_code === "HOME_MODEL_WEIGHTS_MISSING" || data.error_code === "ROAD_MODEL_WEIGHTS_MISSING"))) {
            systemNoticeTitle.textContent = (data && data.error_code === "HOME_MODEL_WEIGHTS_MISSING")
                ? "Home Model Checkpoint Required (HTTP 503)"
                : "Model Weights Checkpoint Required (HTTP 503)";
            systemNoticeMsg.textContent = (data && data.message) || message;
            systemNoticeInstructions.textContent = (data && data.setup_instructions) || "Place model checkpoint into ai/models/";
            systemNoticeInstructions.style.display = "block";
            systemNoticeBanner.style.display = "flex";
            window.scrollTo({ top: 0, behavior: "smooth" });
        } else {
            alert(`Inspection Failed (HTTP ${status}):\n${message}`);
        }
    }

    function renderResults(data) {
        // Set images
        originalDisplayImg.src = clientPreviewImg.src;
        annotatedDisplayImg.src = data.annotated_image;

        // Domain & Header Customization
        const isHome = (data.domain === "home") || (selectedDomain === "home");
        if (resultsDomainBadge) {
            if (isHome) {
                resultsDomainBadge.textContent = "🏠 Home & Building Defect Inspection";
                resultsDomainBadge.className = "badge badge-domain-home";
            } else {
                resultsDomainBadge.textContent = "🛣️ Road Surface Distress Inspection";
                resultsDomainBadge.className = "badge badge-domain-road";
            }
        }
        if (originalImageTitle) {
            originalImageTitle.textContent = isHome ? "Original Building Image" : "Original Surface Image";
        }
        if (detectionsTableHeading) {
            detectionsTableHeading.textContent = isHome 
                ? "Detected Building Defects (Authentic Model Coordinates)" 
                : "Detected Road Distresses (Authentic Model Coordinates)";
        }
        if (disclaimerHeading) {
            disclaimerHeading.textContent = isHome 
                ? "Structural Engineering Disclaimer & Safety Boundary:" 
                : "Civil Engineering Disclaimer & Safety Boundary:";
        }
        if (data.safety_disclaimer && disclaimerText) {
            disclaimerText.textContent = data.safety_disclaimer;
        }

        // Metadata
        const meta = data.metadata || {};
        origDimCaption.textContent = `${meta.width || "--"} × ${meta.height || "--"} px`;
        metaFilename.textContent = data.filename || "--";
        metaFormat.textContent = meta.format || "--";
        metaDimensions.textContent = `${meta.width || "--"} × ${meta.height || "--"} px`;
        metaAspectRatio.textContent = meta.aspect_ratio || "--";
        metaChannels.textContent = `${meta.channels || "--"} channels (${meta.mode || "--"})`;
        metaFileSize.textContent = meta.file_size_formatted || "--";

        // Model caption
        const modelInfo = data.model_info || {};
        modelCheckpointCaption.textContent = modelInfo.name || (isHome ? "YOLOv8 Home" : "YOLOv8n");
        metricModelName.textContent = modelInfo.name || (isHome ? "YOLOv8 Home" : "YOLOv8 Nano");

        // Inspection Mode Telemetry
        const inspMode = (data.inspection_mode || "standard").toLowerCase();
        if (inspMode === "tiled" || inspMode === "sliced") {
            if (metricInspectionMode) metricInspectionMode.textContent = "Tiled Slicing";
            const sliceCount = data.candidate_summary && data.candidate_summary.slice_count ? `${data.candidate_summary.slice_count} Tiles` : "High-Res";
            if (metricModeCaption) metricModeCaption.textContent = `${sliceCount} (Continuous Coverage)`;
        } else {
            if (metricInspectionMode) metricInspectionMode.textContent = "Standard";
            if (metricModeCaption) metricModeCaption.textContent = "Full-Frame 640px";
        }

        // Defect Counts & Telemetry
        const detections = data.detections || [];
        const defectCount = detections.length;
        const usedThreshold = (typeof data.confidence_threshold === "number")
            ? data.confidence_threshold.toFixed(2)
            : (parseFloat(confSlider.value) || 0.25).toFixed(2);

        resultsCountBadge.textContent = `${defectCount} Defect${defectCount === 1 ? "" : "s"} Detected (Threshold ≥ ${usedThreshold})`;
        resultsCountBadge.className = defectCount > 0 ? "badge badge-warning" : "badge badge-success";

        metricDefectCount.textContent = defectCount;

        if (defectCount > 0) {
            const types = Array.from(new Set(detections.map(d => d.distress_category)));
            metricDefectTypes.textContent = types.join(", ");

            const maxConf = Math.max(...detections.map(d => d.confidence));
            metricTopConf.textContent = (maxConf * 100).toFixed(1) + "%";
        } else {
            metricDefectTypes.textContent = `No defects ≥ ${usedThreshold}`;
            metricTopConf.textContent = "N/A";
        }

        // Detections Table
        detectionsTableBody.innerHTML = "";
        if (defectCount === 0) {
            const emptyRow = document.createElement("tr");
            let suggestionHtml = "";
            const cand = data.candidate_summary;
            if (cand && cand.suggested_threshold && cand.suggested_threshold < parseFloat(usedThreshold)) {
                suggestionHtml = `
                    <div style="margin-top: 1rem; padding: 1rem; background: rgba(59, 130, 246, 0.12); border: 1px solid rgba(59, 130, 246, 0.35); border-radius: 8px; text-align: left; max-width: 620px; margin-left: auto; margin-right: auto;">
                        <strong style="color: #60a5fa; display: flex; align-items: center; gap: 0.5rem; margin-bottom: 0.3rem;">
                            <span>💡</span> Subtle Distress Detected Below Threshold
                        </strong>
                        <p style="font-size: 0.9rem; color: var(--text-secondary); margin: 0.4rem 0 0.8rem 0; line-height: 1.4;">
                            The AI model identified a candidate <strong>${cand.top_raw_class || "Distress"}</strong> with <strong>${(cand.top_raw_confidence * 100).toFixed(1)}% statistical confidence</strong>, but filtered it out because the current threshold is set to <strong>${usedThreshold}</strong>.
                        </p>
                        <button type="button" class="btn btn-secondary btn-sm" id="applySuggestedThresholdBtn" style="cursor: pointer; padding: 0.4rem 0.9rem; font-size: 0.85rem; font-weight: 600;">
                            🔍 Inspect in Tiled Mode at ${cand.suggested_threshold.toFixed(2)} Threshold
                        </button>
                    </div>
                `;
            }

            const zeroDefectMsg = isHome
                ? `✅ No wall cracks, dampness, peeling paint, or spalling detected at confidence threshold ≥ ${usedThreshold}.`
                : `✅ No surface cracks or potholes detected at confidence threshold ≥ ${usedThreshold}.`;

            emptyRow.innerHTML = `
                <td colspan="7" style="text-align: center; color: var(--text-muted); padding: 1.5rem;">
                    <div>${zeroDefectMsg}</div>
                    ${suggestionHtml}
                </td>
            `;
            detectionsTableBody.appendChild(emptyRow);

            const applyBtn = document.getElementById("applySuggestedThresholdBtn");
            if (applyBtn && cand && cand.suggested_threshold) {
                applyBtn.addEventListener("click", () => {
                    confSlider.value = cand.suggested_threshold.toFixed(2);
                    syncSliderDisplay();
                    const tiledRadio = document.querySelector('input[name="inspectionMode"][value="tiled"]');
                    if (tiledRadio) tiledRadio.checked = true;
                    inspectBtn.click();
                });
            }
        } else {
            detections.forEach((det, idx) => {
                const tr = document.createElement("tr");
                const bbox = det.bbox || {};
                const coords = `[${bbox.x1}, ${bbox.y1}, ${bbox.x2}, ${bbox.y2}]`;
                const extent = `${bbox.width} × ${bbox.height} px`;
                const src = det.source || "global";
                const srcBadge = src === "tiled"
                    ? '<span class="badge badge-info" style="font-size: 0.72rem; padding: 2px 6px;">🔬 Tiled</span>'
                    : '<span class="badge badge-secondary" style="font-size: 0.72rem; padding: 2px 6px;">⚡ Full-Frame</span>';

                tr.innerHTML = `
                    <td><strong>${idx + 1}</strong></td>
                    <td><span class="badge badge-info">${det.distress_category}</span></td>
                    <td><code>${det.class_name}</code></td>
                    <td><strong>${(det.confidence * 100).toFixed(1)}%</strong></td>
                    <td>${srcBadge}</td>
                    <td><code>${coords}</code></td>
                    <td>${extent}</td>
                `;
                detectionsTableBody.appendChild(tr);
            });
        }

        // Store last inspection for database persistence
        lastInspectionResult = data;

        // Reset Save Inspection Card
        const saveRoadNameInput = document.getElementById("saveRoadNameInput");
        const saveAreaInput = document.getElementById("saveAreaInput");
        const saveCityInput = document.getElementById("saveCityInput");
        const saveLatInput = document.getElementById("saveLatInput");
        const saveLonInput = document.getElementById("saveLonInput");
        const saveNotesInput = document.getElementById("saveNotesInput");
        const saveStatusSelect = document.getElementById("saveStatusSelect");
        const saveInspectionBtn = document.getElementById("saveInspectionBtn");
        const saveSpinner = document.getElementById("saveSpinner");
        const saveFeedback = document.getElementById("saveFeedback");
        const saveCardStatusBadge = document.getElementById("saveCardStatusBadge");

        if (saveRoadNameInput) saveRoadNameInput.value = inspLocationRoad ? inspLocationRoad.value.trim() : "";
        if (saveAreaInput) saveAreaInput.value = inspLocationArea ? inspLocationArea.value.trim() : "";
        if (saveCityInput) saveCityInput.value = inspLocationCity ? inspLocationCity.value.trim() : "";
        if (saveLatInput) saveLatInput.value = inspLocationLat ? inspLocationLat.value.trim() : "";
        if (saveLonInput) saveLonInput.value = inspLocationLon ? inspLocationLon.value.trim() : "";
        if (saveNotesInput) saveNotesInput.value = inspLocationNotes ? inspLocationNotes.value.trim() : "";
        if (saveStatusSelect) saveStatusSelect.value = "Open";
        if (saveInspectionBtn) {
            saveInspectionBtn.disabled = false;
            saveInspectionBtn.querySelector(".btn-text").textContent = "Save Inspection Record";
        }
        if (saveSpinner) saveSpinner.style.display = "none";
        if (saveFeedback) saveFeedback.style.display = "none";
        if (saveCardStatusBadge) {
            saveCardStatusBadge.textContent = "Ready to Save";
            saveCardStatusBadge.className = "badge badge-info";
        }
        isSaving = false;

        // Show container and scroll
        resultsContainer.style.display = "flex";
        resultsContainer.scrollIntoView({ behavior: "smooth", block: "start" });
    }

    // -------------------------------------------------------------------------
    // 6. Inspection Records Feature: Tab Navigation, Persistence & Status Lifecycle
    // -------------------------------------------------------------------------
    let lastInspectionResult = null;
    let isSaving = false;
    let currentDetailId = null;

    const tabDashboardBtn = document.getElementById("tabDashboardBtn");
    const tabNewInspectionBtn = document.getElementById("tabNewInspectionBtn");
    const tabRecordsBtn = document.getElementById("tabRecordsBtn");
    const tabMapBtn = document.getElementById("tabMapBtn");
    const tabReportsBtn = document.getElementById("tabReportsBtn");
    const tabQueueBtn = document.getElementById("tabQueueBtn");
    const tabUsersBtn = document.getElementById("tabUsersBtn");
    const dashboardSection = document.getElementById("dashboardSection");
    const newInspectionSection = document.getElementById("newInspectionSection");
    const recordsSection = document.getElementById("recordsSection");
    const recordDetailSection = document.getElementById("recordDetailSection");
    const mapSection = document.getElementById("mapSection");
    const reportsSection = document.getElementById("reportsSection");
    const queueSection = document.getElementById("queueSection");
    const usersSection = document.getElementById("usersSection");
    const recordsCountBadgeHeader = document.getElementById("recordsCountBadgeHeader");
    const mapCountBadgeHeader = document.getElementById("mapCountBadgeHeader");
    const queueCountBadgeHeader = document.getElementById("queueCountBadgeHeader");

    // Phase 4.7 & Phase 5: Maintenance Work Queue & Task Assignment Elements
    const queueSubtitle = document.getElementById("queueSubtitle");
    const queueDomainFilter = document.getElementById("queueDomainFilter");
    const queueSortFilter = document.getElementById("queueSortFilter");
    const queueAssigneeFilterWrap = document.getElementById("queueAssigneeFilterWrap");
    const queueAssigneeFilter = document.getElementById("queueAssigneeFilter");
    const queueStatusFilter = document.getElementById("queueStatusFilter");
    const queueUrgencyFilter = document.getElementById("queueUrgencyFilter");
    const queueCategoryFilter = document.getElementById("queueCategoryFilter");
    const queueSearchInput = document.getElementById("queueSearchInput");
    const resetQueueFiltersBtn = document.getElementById("resetQueueFiltersBtn");
    const refreshQueueBtn = document.getElementById("refreshQueueBtn");
    const queueTotalCount = document.getElementById("queueTotalCount");
    const queuePendingCount = document.getElementById("queuePendingCount");
    const queueOverdueCount = document.getElementById("queueOverdueCount");
    const queueCompletedCount = document.getElementById("queueCompletedCount");
    const queueTable = document.getElementById("queueTable");
    const queueTableBody = document.getElementById("queueTableBody");
    const queueEmptyState = document.getElementById("queueEmptyState");
    const queueEmptyText = document.getElementById("queueEmptyText");
    const queueEmptyResetBtn = document.getElementById("queueEmptyResetBtn");
    const queueErrorState = document.getElementById("queueErrorState");
    const queueErrorText = document.getElementById("queueErrorText");
    const queueRetryBtn = document.getElementById("queueRetryBtn");

    const detailAssignmentCard = document.getElementById("detailAssignmentCard");
    const detailAssignmentStatusBadge = document.getElementById("detailAssignmentStatusBadge");
    const detailAssigneeDisplay = document.getElementById("detailAssigneeDisplay");
    const detailAssigneeActiveDisplay = document.getElementById("detailAssigneeActiveDisplay");
    const detailAssignedByDisplay = document.getElementById("detailAssignedByDisplay");
    const detailAssignedAtDisplay = document.getElementById("detailAssignedAtDisplay");
    const detailAssignmentUpdatedDisplay = document.getElementById("detailAssignmentUpdatedDisplay");
    const detailAssignmentInstructionsDisplay = document.getElementById("detailAssignmentInstructionsDisplay");
    const detailAssignmentAdminActions = document.getElementById("detailAssignmentAdminActions");
    const openAssignTaskModalBtn = document.getElementById("openAssignTaskModalBtn");
    const cancelAssignmentBtn = document.getElementById("cancelAssignmentBtn");
    const detailAssignmentFeedback = document.getElementById("detailAssignmentFeedback");
    const detailAssignmentHistoryWrap = document.getElementById("detailAssignmentHistoryWrap");
    const detailAssignmentEventsCountBadge = document.getElementById("detailAssignmentEventsCountBadge");
    const detailAssignmentHistoryList = document.getElementById("detailAssignmentHistoryList");

    const assignTaskModal = document.getElementById("assignTaskModal");
    const assignTaskModalTitle = document.getElementById("assignTaskModalTitle");
    const closeAssignTaskModalBtn = document.getElementById("closeAssignTaskModalBtn");
    const cancelAssignTaskModalBtn = document.getElementById("cancelAssignTaskModalBtn");
    const assignTaskErrorAlert = document.getElementById("assignTaskErrorAlert");
    const assignTaskForm = document.getElementById("assignTaskForm");
    const assignTaskInspectionId = document.getElementById("assignTaskInspectionId");
    const assigneeSelect = document.getElementById("assigneeSelect");
    const assignInstructionsInput = document.getElementById("assignInstructionsInput");
    const saveAssignTaskBtn = document.getElementById("saveAssignTaskBtn");

    // Header Auth Controls (Phase 4.6)
    const authGuestControls = document.getElementById("authGuestControls");
    const authUserControls = document.getElementById("authUserControls");
    const currentUserBadge = document.getElementById("currentUserBadge");
    const openAuthModalBtn = document.getElementById("openAuthModalBtn");
    const logoutBtn = document.getElementById("logoutBtn");

    // Auth Modal Controls
    const authModal = document.getElementById("authModal");
    const authModalTitle = document.getElementById("authModalTitle");
    const closeAuthModalBtn = document.getElementById("closeAuthModalBtn");
    const cancelAuthBtn = document.getElementById("cancelAuthBtn");
    const setupRequiredNotice = document.getElementById("setupRequiredNotice");
    const authErrorAlert = document.getElementById("authErrorAlert");
    const loginForm = document.getElementById("loginForm");
    const loginUsername = document.getElementById("loginUsername");
    const loginPassword = document.getElementById("loginPassword");
    const setupAdminForm = document.getElementById("setupAdminForm");
    const setupAdminUsername = document.getElementById("setupAdminUsername");
    const setupAdminEmail = document.getElementById("setupAdminEmail");
    const setupAdminPassword = document.getElementById("setupAdminPassword");

    // User Management Controls (Admin Only)
    const createUserModal = document.getElementById("createUserModal");
    const createUserModalBtn = document.getElementById("createUserModalBtn");
    const closeCreateUserModalBtn = document.getElementById("closeCreateUserModalBtn");
    const cancelCreateUserBtn = document.getElementById("cancelCreateUserBtn");
    const createUserErrorAlert = document.getElementById("createUserErrorAlert");
    const createUserForm = document.getElementById("createUserForm");
    const newUsername = document.getElementById("newUsername");
    const newUserEmail = document.getElementById("newUserEmail");
    const newUserRole = document.getElementById("newUserRole");
    const newUserPassword = document.getElementById("newUserPassword");
    const newUserActive = document.getElementById("newUserActive");
    const refreshUsersBtn = document.getElementById("refreshUsersBtn");
    const usersTableBody = document.getElementById("usersTableBody");

    const refreshDashboardBtn = document.getElementById("refreshDashboardBtn");
    const dashStartInspectionBtn = document.getElementById("dashStartInspectionBtn");
    const dashViewAllRecordsBtn = document.getElementById("dashViewAllRecordsBtn");
    const dashEmptyNewInspectionBtn = document.getElementById("dashEmptyNewInspectionBtn");

    const dashTotalInspections = document.getElementById("dashTotalInspections");
    const dashTotalDefects = document.getElementById("dashTotalDefects");
    const dashOpenRecords = document.getElementById("dashOpenRecords");
    const dashInProgressRecords = document.getElementById("dashInProgressRecords");
    const dashResolvedRecords = document.getElementById("dashResolvedRecords");

    const dashDefectsTotalBadge = document.getElementById("dashDefectsTotalBadge");
    const dashCategoryBarsContainer = document.getElementById("dashCategoryBarsContainer");
    const dashDefectsEmptyState = document.getElementById("dashDefectsEmptyState");

    const statCatLongitudinal = document.getElementById("statCatLongitudinal");
    const barCatLongitudinal = document.getElementById("barCatLongitudinal");
    const statCatTransverse = document.getElementById("statCatTransverse");
    const barCatTransverse = document.getElementById("barCatTransverse");
    const statCatAlligator = document.getElementById("statCatAlligator");
    const barCatAlligator = document.getElementById("barCatAlligator");
    const statCatPothole = document.getElementById("statCatPothole");
    const barCatPothole = document.getElementById("barCatPothole");

    const segmentOpen = document.getElementById("segmentOpen");
    const segmentProgress = document.getElementById("segmentProgress");
    const segmentResolved = document.getElementById("segmentResolved");
    const legendOpenCount = document.getElementById("legendOpenCount");
    const legendOpenPct = document.getElementById("legendOpenPct");
    const legendProgressCount = document.getElementById("legendProgressCount");
    const legendProgressPct = document.getElementById("legendProgressPct");
    const legendResolvedCount = document.getElementById("legendResolvedCount");
    const legendResolvedPct = document.getElementById("legendResolvedPct");

    const dashRecentTable = document.getElementById("dashRecentTable");
    const dashRecentTableBody = document.getElementById("dashRecentTableBody");
    const dashEmptyState = document.getElementById("dashEmptyState");

    const saveInspectionBtn = document.getElementById("saveInspectionBtn");
    const saveSpinner = document.getElementById("saveSpinner");
    const saveFeedback = document.getElementById("saveFeedback");
    const saveCardStatusBadge = document.getElementById("saveCardStatusBadge");
    const saveRoadNameInput = document.getElementById("saveRoadNameInput");
    const saveTargetDateInput = document.getElementById("saveTargetDateInput");
    const saveAreaInput = document.getElementById("saveAreaInput");
    const saveCityInput = document.getElementById("saveCityInput");
    const saveLatInput = document.getElementById("saveLatInput");
    const saveLonInput = document.getElementById("saveLonInput");
    const saveNotesInput = document.getElementById("saveNotesInput");
    const saveStatusSelect = document.getElementById("saveStatusSelect");

    // Phase 4.4: Maintenance Deadlines, Alerts & Activity Log Elements
    const maintenanceAlertBanner = document.getElementById("maintenanceAlertBanner");
    const maintenanceAlertTitle = document.getElementById("maintenanceAlertTitle");
    const maintenanceAlertMsg = document.getElementById("maintenanceAlertMsg");
    const maintenanceAlertCountBadge = document.getElementById("maintenanceAlertCountBadge");
    const viewOverdueRecordsBtn = document.getElementById("viewOverdueRecordsBtn");
    const viewDueTodayRecordsBtn = document.getElementById("viewDueTodayRecordsBtn");
    const maintenanceActionableBadge = document.getElementById("maintenanceActionableBadge");
    const dashOverdueCount = document.getElementById("dashOverdueCount");
    const dashDueTodayCount = document.getElementById("dashDueTodayCount");
    const dashUpcomingCount = document.getElementById("dashUpcomingCount");
    const dashResolvedMaintCount = document.getElementById("dashResolvedMaintCount");
    const dashNoDeadlinesCount = document.getElementById("dashNoDeadlinesCount");
    const deadlineBoxOverdue = document.getElementById("deadlineBoxOverdue");
    const deadlineBoxToday = document.getElementById("deadlineBoxToday");
    const deadlineBoxUpcoming = document.getElementById("deadlineBoxUpcoming");
    const deadlineBoxResolved = document.getElementById("deadlineBoxResolved");
    const deadlineBoxNone = document.getElementById("deadlineBoxNone");

    const recordsStatusFilter = document.getElementById("recordsStatusFilter");
    const recordsCategoryFilter = document.getElementById("recordsCategoryFilter");
    const recordsDeadlineFilter = document.getElementById("recordsDeadlineFilter");
    const recordsSearchInput = document.getElementById("recordsSearchInput");
    const resetRecordsFiltersBtn = document.getElementById("resetRecordsFiltersBtn");
    const refreshRecordsBtn = document.getElementById("refreshRecordsBtn");
    const recordsTable = document.getElementById("recordsTable");
    const recordsTableBody = document.getElementById("recordsTableBody");
    const recordsEmptyState = document.getElementById("recordsEmptyState");

    const statTotalInspections = document.getElementById("statTotalInspections");
    const statOpenInspections = document.getElementById("statOpenInspections");
    const statActiveInspections = document.getElementById("statActiveInspections");
    const statResolvedInspections = document.getElementById("statResolvedInspections");

    const backToRecordsBtn = document.getElementById("backToRecordsBtn");
    const detailRecordIdHeader = document.getElementById("detailRecordIdHeader");
    const detailCurrentStatusBadge = document.getElementById("detailCurrentStatusBadge");
    const detailStatusSelect = document.getElementById("detailStatusSelect");
    const detailTargetDateInput = document.getElementById("detailTargetDateInput");
    const detailStatusNotes = document.getElementById("detailStatusNotes");
    const updateStatusBtn = document.getElementById("updateStatusBtn");
    const updateStatusSpinner = document.getElementById("updateStatusSpinner");
    const detailStatusFeedback = document.getElementById("detailStatusFeedback");

    const detailDeadlineCard = document.getElementById("detailDeadlineCard");
    const detailDeadlineBadge = document.getElementById("detailDeadlineBadge");
    const detailTargetDateDisplay = document.getElementById("detailTargetDateDisplay");
    const detailUrgencyDisplay = document.getElementById("detailUrgencyDisplay");
    const detailRemainingDisplay = document.getElementById("detailRemainingDisplay");

    const detailActivityCard = document.getElementById("detailActivityCard");
    const detailActivityCountBadge = document.getElementById("detailActivityCountBadge");
    const detailActivityTableBody = document.getElementById("detailActivityTableBody");
    const detailActivityEmptyState = document.getElementById("detailActivityEmptyState");

    const detailOriginalImg = document.getElementById("detailOriginalImg");
    const detailAnnotatedImg = document.getElementById("detailAnnotatedImg");
    const detailRoadName = document.getElementById("detailRoadName");
    const detailLocationNotes = document.getElementById("detailLocationNotes");
    const detailDefectCount = document.getElementById("detailDefectCount");
    const detailDefectTypes = document.getElementById("detailDefectTypes");
    const detailTopConf = document.getElementById("detailTopConf");
    const detailTimestamp = document.getElementById("detailTimestamp");
    const detailInspectionMode = document.getElementById("detailInspectionMode");
    const detailDetectionsTableBody = document.getElementById("detailDetectionsTableBody");

    const detailGpsBadge = document.getElementById("detailGpsBadge");
    const detailLocRoad = document.getElementById("detailLocRoad");
    const detailLocArea = document.getElementById("detailLocArea");
    const detailLocCity = document.getElementById("detailLocCity");
    const detailLocCoords = document.getElementById("detailLocCoords");
    const detailLocNotes = document.getElementById("detailLocNotes");

    // Defect Map DOM Elements (Phase 4.2 & 4.4)
    const mapTelemetryBadge = document.getElementById("mapTelemetryBadge");
    const refreshMapBtn = document.getElementById("refreshMapBtn");
    const mapDomainFilter = document.getElementById("mapDomainFilter");
    const mapCategoryFilter = document.getElementById("mapCategoryFilter");
    const mapStatusFilter = document.getElementById("mapStatusFilter");
    const mapDeadlineFilter = document.getElementById("mapDeadlineFilter");
    const mapSearchInput = document.getElementById("mapSearchInput");
    const resetMapFiltersBtn = document.getElementById("resetMapFiltersBtn");
    const mapErrorBanner = document.getElementById("mapErrorBanner");
    const mapErrorMsg = document.getElementById("mapErrorMsg");
    const mapEmptyState = document.getElementById("mapEmptyState");
    const mapEmptyNewInspBtn = document.getElementById("mapEmptyNewInspBtn");
    const mapEmptyViewRecordsBtn = document.getElementById("mapEmptyViewRecordsBtn");
    const mapLayoutWrapper = document.getElementById("mapLayoutWrapper");
    const legendCountD00 = document.getElementById("legendCountD00");
    const legendCountD10 = document.getElementById("legendCountD10");
    const legendCountD20 = document.getElementById("legendCountD20");
    const legendCountD40 = document.getElementById("legendCountD40");
    const legendCountWall = document.getElementById("legendCountWall");
    const legendCountDamp = document.getElementById("legendCountDamp");
    const legendCountPeel = document.getElementById("legendCountPeel");
    const legendCountSpall = document.getElementById("legendCountSpall");
    const legendCountSound = document.getElementById("legendCountSound");

    // Phase 4.5: Reports & Data Exports DOM Elements
    const exportPdfBtn = document.getElementById("exportPdfBtn");
    const exportCsvBtn = document.getElementById("exportCsvBtn");
    const printReportBtn = document.getElementById("printReportBtn");
    const reportStartDate = document.getElementById("reportStartDate");
    const reportEndDate = document.getElementById("reportEndDate");
    const reportCategoryFilter = document.getElementById("reportCategoryFilter");
    const reportStatusFilter = document.getElementById("reportStatusFilter");
    const reportDeadlineFilter = document.getElementById("reportDeadlineFilter");
    const reportCityFilter = document.getElementById("reportCityFilter");
    const reportAreaFilter = document.getElementById("reportAreaFilter");
    const reportSearchInput = document.getElementById("reportSearchInput");
    const generateReportBtn = document.getElementById("generateReportBtn");
    const resetReportFiltersBtn = document.getElementById("resetReportFiltersBtn");
    const reportResetFromEmptyBtn = document.getElementById("reportResetFromEmptyBtn");
    const reportSpinner = document.getElementById("reportSpinner");
    const reportMatchingBadge = document.getElementById("reportMatchingBadge");
    const reportErrorBanner = document.getElementById("reportErrorBanner");
    const reportErrorMsg = document.getElementById("reportErrorMsg");
    const reportEmptyState = document.getElementById("reportEmptyState");
    const reportPreviewContainer = document.getElementById("reportPreviewContainer");

    const prevGeneratedAt = document.getElementById("prevGeneratedAt");
    const prevReferenceDate = document.getElementById("prevReferenceDate");
    const prevRecordCount = document.getElementById("prevRecordCount");
    const prevFilterText = document.getElementById("prevFilterText");
    const prevTotalInspections = document.getElementById("prevTotalInspections");
    const prevTotalDefects = document.getElementById("prevTotalDefects");
    const prevActiveOrders = document.getElementById("prevActiveOrders");
    const prevOverdueRepairs = document.getElementById("prevOverdueRepairs");
    const prevCategoryTableBody = document.getElementById("prevCategoryTableBody");
    const prevComplianceTableBody = document.getElementById("prevComplianceTableBody");
    const prevTableBadge = document.getElementById("prevTableBadge");
    const prevRecordsTableBody = document.getElementById("prevRecordsTableBody");

    // Leaflet Map State
    let defectMapInstance = null;
    let markersLayerGroup = null;
    let cachedMapRecords = [];

    // Safe HTML Escaping for Popups and Labels
    function escapeHtml(str) {
        if (!str) return "";
        return String(str)
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;")
            .replace(/'/g, "&#039;");
    }

    // Coordinate validation strictly adhering to Phase 4.2 specs:
    // Only accept genuine numbers: -90 <= lat <= 90 and -180 <= lon <= 180.
    // Never fabricate coordinates or default missing GPS.
    function isValidCoordinate(lat, lon) {
        if (lat === null || lat === undefined || lon === null || lon === undefined) {
            return false;
        }
        if (typeof lat === "string" && lat.trim() === "") return false;
        if (typeof lon === "string" && lon.trim() === "") return false;
        const numLat = parseFloat(lat);
        const numLon = parseFloat(lon);
        if (isNaN(numLat) || isNaN(numLon)) {
            return false;
        }
        if (numLat < -90 || numLat > 90 || numLon < -180 || numLon > 180) {
            return false;
        }
        return true;
    }

    // Determine pin style and defect category classification
    function getMarkerConfig(rec) {
        if (!rec.defect_count || rec.defect_count === 0) {
            return {
                category: "Sound",
                code: "OK",
                pinClass: "pin-sound",
                label: "Sound Surface (0 Defects)",
                color: "#10b981"
            };
        }
        const defType = (rec.defect_type || "").toLowerCase();
        if (defType.includes("pothole") || defType.includes("d40")) {
            return {
                category: "Pothole",
                code: "D40",
                pinClass: "pin-d40",
                label: "Pothole (D40)",
                color: "#ef4444"
            };
        } else if (defType.includes("alligator") || defType.includes("d20")) {
            return {
                category: "Alligator",
                code: "D20",
                pinClass: "pin-d20",
                label: "Alligator Crack (D20)",
                color: "#f59e0b"
            };
        } else if (defType.includes("transverse") || defType.includes("d10")) {
            return {
                category: "Transverse",
                code: "D10",
                pinClass: "pin-d10",
                label: "Transverse Crack (D10)",
                color: "#a855f7"
            };
        } else if (defType.includes("wall_crack") || defType.includes("wall crack") || defType.includes("wall")) {
            return {
                category: "Wall Crack",
                code: "WALL",
                pinClass: "pin-wall",
                label: "Wall Crack",
                color: "#f97316"
            };
        } else if (defType.includes("damp") || defType.includes("water")) {
            return {
                category: "Dampness",
                code: "DAMP",
                pinClass: "pin-damp",
                label: "Dampness / Water Damage",
                color: "#06b6d4"
            };
        } else if (defType.includes("peel") || defType.includes("paint") || defType.includes("plaster")) {
            return {
                category: "Peeling Paint",
                code: "PEEL",
                pinClass: "pin-peel",
                label: "Peeling Paint / Plaster",
                color: "#eab308"
            };
        } else if (defType.includes("spall")) {
            return {
                category: "Spalling",
                code: "SPALL",
                pinClass: "pin-spall",
                label: "Spalling / Surface Damage",
                color: "#ec4899"
            };
        } else if (rec.inspection_type === "home") {
            return {
                category: "Wall Crack",
                code: "WALL",
                pinClass: "pin-wall",
                label: "Building Defect",
                color: "#f97316"
            };
        } else {
            return {
                category: "Longitudinal",
                code: "D00",
                pinClass: "pin-d00",
                label: "Longitudinal Crack (D00)",
                color: "#3b82f6"
            };
        }
    }

    // Build rich popup HTML according to Phase 4.2 requirements
    function buildMapPopup(rec, markerCfg) {
        const road = rec.road_name ? rec.road_name.trim() : "Unspecified Road";
        const area = rec.area ? rec.area.trim() : "";
        const city = rec.city ? rec.city.trim() : "";
        const subLoc = [area, city].filter(Boolean).join(", ");
        const latStr = Number(rec.latitude).toFixed(5);
        const lonStr = Number(rec.longitude).toFixed(5);
        const statusClass = getStatusBadgeClass(rec.status);
        const countDisplay = rec.defect_count > 0 
            ? `${rec.defect_count} Defect${rec.defect_count === 1 ? "" : "s"}` 
            : "Sound Surface (0 Defects)";
        const catDisplay = rec.defect_count > 0 ? (rec.defect_type || markerCfg.label) : "Sound Surface";

        return `
            <div class="map-popup-card">
                <div class="map-popup-header">
                    <div class="map-popup-location">
                        <strong>#${rec.id} • ${escapeHtml(road)}</strong>
                        ${subLoc ? `<div class="sub-location">📍 ${escapeHtml(subLoc)}</div>` : ""}
                    </div>
                    <span class="${statusClass}" style="font-size: 0.72rem; padding: 2px 7px;">${escapeHtml(rec.status)}</span>
                </div>
                <div class="map-popup-coords">GPS: ${latStr}°, ${lonStr}°</div>
                <div style="margin-bottom: 0.4rem;">
                    ${getDeadlineBadge(rec)}
                </div>
                <div class="map-popup-metrics">
                    <div class="metric-mini">
                        <span class="label">Defects</span>
                        <strong>${countDisplay}</strong>
                    </div>
                    <div class="metric-mini">
                        <span class="label">Class</span>
                        <strong title="${escapeHtml(catDisplay)}">${escapeHtml(catDisplay)}</strong>
                    </div>
                </div>
                ${rec.location_notes ? `<div style="font-size: 0.75rem; color: var(--text-muted); margin-bottom: 0.4rem; max-height: 40px; overflow: hidden; text-overflow: ellipsis;">📝 ${escapeHtml(rec.location_notes)}</div>` : ""}
                <div class="map-popup-actions">
                    <button type="button" class="btn btn-secondary btn-sm" onclick="window.openRecordDetailFromMap(${rec.id}); return false;" style="width: 100%; font-size: 0.8rem; padding: 0.35rem 0.5rem;">
                        👁️ View Full Inspection Details →
                    </button>
                </div>
            </div>
        `;
    }

    // Expose detail opener to window scope so Leaflet popup HTML onclick reliably fires
    window.openRecordDetailFromMap = function(id) {
        openRecordDetail(id);
    };

    // Helper: Format location display for table rows
    function formatLocationDisplay(rec) {
        const road = rec.road_name ? rec.road_name.trim() : "";
        const area = rec.area ? rec.area.trim() : "";
        const city = rec.city ? rec.city.trim() : "";

        let html = "";
        const isHome = rec.inspection_type === "home";
        const domainBadge = isHome 
            ? '<span class="badge badge-domain-home" style="margin-right: 4px; font-size: 0.7rem; padding: 2px 6px;">🏠 Home</span> ' 
            : '<span class="badge badge-domain-road" style="margin-right: 4px; font-size: 0.7rem; padding: 2px 6px;">🛣️ Road</span> ';

        if (road) {
            html += `<strong>${road}</strong>`;
            const sub = [];
            if (area) sub.push(area);
            if (city) sub.push(city);
            if (sub.length > 0) {
                html += `<div style="font-size: 0.78rem; color: var(--text-secondary); margin-top: 2px;">${sub.join(", ")}</div>`;
            }
        } else if (area || city) {
            const sub = [];
            if (area) sub.push(area);
            if (city) sub.push(city);
            html += `<strong>${sub.join(", ")}</strong>`;
        } else {
            html += '<span style="color: var(--text-muted); font-style: italic;">Unspecified Location</span>';
        }

        if (rec.latitude !== null && rec.latitude !== undefined && rec.longitude !== null && rec.longitude !== undefined) {
            const latStr = Number(rec.latitude).toFixed(4);
            const lonStr = Number(rec.longitude).toFixed(4);
            html += `<div class="geo-tag-pill" title="GPS: ${rec.latitude}, ${rec.longitude}">📍 ${latStr}, ${lonStr}</div>`;
        }
        return domainBadge + html;
    }

    // Helper: Map status to badge class
    function getStatusBadgeClass(status) {
        switch (status) {
            case "Open": return "badge badge-status-open";
            case "In Progress": return "badge badge-status-in-progress";
            case "Under Review": return "badge badge-status-review";
            case "Assigned": return "badge badge-status-assigned";
            case "Repair in Progress": return "badge badge-status-repair";
            case "Resolved": return "badge badge-status-resolved";
            case "Reopened": return "badge badge-status-reopened";
            default: return "badge badge-secondary";
        }
    }

    // Helper: Map maintenance deadline urgency to badge HTML (Phase 4.4)
    function getDeadlineBadge(rec) {
        const urgency = rec.maintenance_urgency || (rec.status === "Resolved" ? "resolved" : "no_deadline");
        const label = rec.maintenance_label || (rec.target_repair_date ? rec.target_repair_date : "No Target Date");
        
        switch (urgency) {
            case "overdue":
                return `<span class="badge badge-deadline-overdue" title="Overdue by ${Math.abs(rec.days_remaining || 0)} day(s)">⚠️ ${escapeHtml(label)}</span>`;
            case "due_today":
                return `<span class="badge badge-deadline-today" title="Deadline is today">🔔 ${escapeHtml(label)}</span>`;
            case "upcoming":
                return `<span class="badge badge-deadline-upcoming" title="Target: ${escapeHtml(rec.target_repair_date || '')}">📅 ${escapeHtml(label)}</span>`;
            case "resolved":
                return `<span class="badge badge-deadline-resolved" title="Remediation completed">✅ ${escapeHtml(label)}</span>`;
            default:
                return `<span class="badge badge-deadline-none">⚪ No Target Date</span>`;
        }
    }

    // Helper: Render chronological activity history table
    function renderActivityHistory(activities) {
        if (!detailActivityTableBody) return;
        detailActivityTableBody.innerHTML = "";

        if (detailActivityCountBadge) {
            detailActivityCountBadge.textContent = `${activities.length} Event${activities.length === 1 ? "" : "s"}`;
        }

        if (!activities || activities.length === 0) {
            if (detailActivityEmptyState) detailActivityEmptyState.style.display = "block";
            return;
        }

        if (detailActivityEmptyState) detailActivityEmptyState.style.display = "none";

        activities.forEach(act => {
            const tr = document.createElement("tr");
            let actionBadge = "";
            switch (act.action_type) {
                case "created":
                    actionBadge = `<span class="activity-action-badge action-created">Created</span>`;
                    break;
                case "status_change":
                    actionBadge = `<span class="activity-action-badge action-status-change">Status</span>`;
                    break;
                case "resolved":
                    actionBadge = `<span class="activity-action-badge action-resolved">Resolved</span>`;
                    break;
                case "reopened":
                    actionBadge = `<span class="activity-action-badge action-reopened">Reopened</span>`;
                    break;
                case "assigned":
                    actionBadge = `<span class="activity-action-badge action-assigned">Assigned</span>`;
                    break;
                case "reassigned":
                    actionBadge = `<span class="activity-action-badge action-reassigned">Reassigned</span>`;
                    break;
                case "assignment_cancelled":
                    actionBadge = `<span class="activity-action-badge action-cancelled">Cancelled</span>`;
                    break;
                case "repair_notes_added":
                    actionBadge = `<span class="activity-action-badge action-repair-notes">Repair Notes</span>`;
                    break;
                case "target_date_change":
                    actionBadge = `<span class="activity-action-badge action-target-date-change">Target Date</span>`;
                    break;
                default:
                    actionBadge = `<span class="activity-action-badge action-update">${escapeHtml(act.action_type)}</span>`;
                    break;
            }

            let statusTransition = "--";
            if (act.previous_status && act.new_status && act.previous_status !== act.new_status) {
                statusTransition = `<span>${escapeHtml(act.previous_status)}</span><span class="transition-arrow">→</span><strong>${escapeHtml(act.new_status)}</strong>`;
            } else if (act.new_status) {
                statusTransition = `<strong>${escapeHtml(act.new_status)}</strong>`;
            }

            let dateTransition = "--";
            if (act.previous_target_date && act.new_target_date && act.previous_target_date !== act.new_target_date) {
                dateTransition = `<span>${escapeHtml(act.previous_target_date)}</span><span class="transition-arrow">→</span><strong>${escapeHtml(act.new_target_date)}</strong>`;
            } else if (act.new_target_date) {
                dateTransition = `<strong>${escapeHtml(act.new_target_date)}</strong>`;
            } else if (act.previous_target_date && !act.new_target_date) {
                dateTransition = `<span style="color: var(--text-muted); text-decoration: line-through;">${escapeHtml(act.previous_target_date)}</span> (Cleared)`;
            }

            const userTag = act.username
                ? `<div style="font-size: 0.72rem; color: var(--text-muted); margin-top: 3px;">👤 ${escapeHtml(act.username)}</div>`
                : '';

            tr.innerHTML = `
                <td><span style="font-size: 0.78rem; color: var(--text-secondary);">${formatDateTime(act.created_at)}</span></td>
                <td>${actionBadge}</td>
                <td>${statusTransition}</td>
                <td>${dateTransition}</td>
                <td><span style="font-size: 0.8rem; color: var(--text-primary);">${escapeHtml(act.notes || "No notes entered")}</span>${userTag}</td>
            `;
            detailActivityTableBody.appendChild(tr);
        });
    }

    // Helper: Format ISO timestamp
    function formatDateTime(dtStr) {
        if (!dtStr) return "--";
        try {
            const dt = new Date(dtStr);
            if (isNaN(dt.getTime())) return dtStr;
            return dt.toLocaleDateString() + " " + dt.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
        } catch (_) {
            return dtStr;
        }
    }

    // View Navigation
    function switchView(viewName) {
        const welcomeLandingSection = document.getElementById("welcomeLandingSection");
        const citizenDashboardSection = document.getElementById("citizenDashboardSection");

        if (viewName === "dashboard") {
            if (tabDashboardBtn) tabDashboardBtn.classList.add("active");
            if (tabNewInspectionBtn) tabNewInspectionBtn.classList.remove("active");
            if (tabRecordsBtn) tabRecordsBtn.classList.remove("active");
            if (tabMapBtn) tabMapBtn.classList.remove("active");
            if (tabReportsBtn) tabReportsBtn.classList.remove("active");
            if (tabQueueBtn) tabQueueBtn.classList.remove("active");
            if (tabUsersBtn) tabUsersBtn.classList.remove("active");

            if (newInspectionSection) newInspectionSection.style.display = "none";
            if (recordsSection) recordsSection.style.display = "none";
            if (recordDetailSection) recordDetailSection.style.display = "none";
            if (mapSection) mapSection.style.display = "none";
            if (reportsSection) reportsSection.style.display = "none";
            if (queueSection) queueSection.style.display = "none";
            if (usersSection) usersSection.style.display = "none";

            if (currentUser && currentUser.role === "citizen") {
                if (welcomeLandingSection) welcomeLandingSection.style.display = "none";
                if (dashboardSection) dashboardSection.style.display = "none";
                if (citizenDashboardSection) citizenDashboardSection.style.display = "block";
                loadCitizenDashboard();
            } else if (!currentUser) {
                if (welcomeLandingSection) welcomeLandingSection.style.display = "block";
                if (dashboardSection) dashboardSection.style.display = "none";
                if (citizenDashboardSection) citizenDashboardSection.style.display = "none";
            } else {
                if (welcomeLandingSection) welcomeLandingSection.style.display = "none";
                if (citizenDashboardSection) citizenDashboardSection.style.display = "none";
                if (dashboardSection) dashboardSection.style.display = "flex";
                loadDashboardStats();
            }
            window.scrollTo({ top: 0, behavior: "smooth" });
        } else if (viewName === "new") {
            if (tabDashboardBtn) tabDashboardBtn.classList.remove("active");
            if (tabNewInspectionBtn) tabNewInspectionBtn.classList.add("active");
            if (tabRecordsBtn) tabRecordsBtn.classList.remove("active");
            if (tabMapBtn) tabMapBtn.classList.remove("active");
            if (tabReportsBtn) tabReportsBtn.classList.remove("active");
            if (tabQueueBtn) tabQueueBtn.classList.remove("active");
            if (tabUsersBtn) tabUsersBtn.classList.remove("active");
            if (welcomeLandingSection) welcomeLandingSection.style.display = "none";
            if (citizenDashboardSection) citizenDashboardSection.style.display = "none";
            if (dashboardSection) dashboardSection.style.display = "none";
            if (newInspectionSection) newInspectionSection.style.display = "block";
            if (recordsSection) recordsSection.style.display = "none";
            if (recordDetailSection) recordDetailSection.style.display = "none";
            if (mapSection) mapSection.style.display = "none";
            if (reportsSection) reportsSection.style.display = "none";
            if (queueSection) queueSection.style.display = "none";
            if (usersSection) usersSection.style.display = "none";
        } else if (viewName === "records") {
            if (tabDashboardBtn) tabDashboardBtn.classList.remove("active");
            if (tabNewInspectionBtn) tabNewInspectionBtn.classList.remove("active");
            if (tabRecordsBtn) tabRecordsBtn.classList.add("active");
            if (tabMapBtn) tabMapBtn.classList.remove("active");
            if (tabReportsBtn) tabReportsBtn.classList.remove("active");
            if (tabQueueBtn) tabQueueBtn.classList.remove("active");
            if (tabUsersBtn) tabUsersBtn.classList.remove("active");
            if (welcomeLandingSection) welcomeLandingSection.style.display = "none";
            if (citizenDashboardSection) citizenDashboardSection.style.display = "none";
            if (dashboardSection) dashboardSection.style.display = "none";
            if (newInspectionSection) newInspectionSection.style.display = "none";
            if (recordsSection) recordsSection.style.display = "flex";
            if (recordDetailSection) recordDetailSection.style.display = "none";
            if (mapSection) mapSection.style.display = "none";
            if (reportsSection) reportsSection.style.display = "none";
            if (queueSection) queueSection.style.display = "none";
            if (usersSection) usersSection.style.display = "none";
            loadRecords();
        } else if (viewName === "map") {
            if (tabDashboardBtn) tabDashboardBtn.classList.remove("active");
            if (tabNewInspectionBtn) tabNewInspectionBtn.classList.remove("active");
            if (tabRecordsBtn) tabRecordsBtn.classList.remove("active");
            if (tabMapBtn) tabMapBtn.classList.add("active");
            if (tabReportsBtn) tabReportsBtn.classList.remove("active");
            if (tabQueueBtn) tabQueueBtn.classList.remove("active");
            if (tabUsersBtn) tabUsersBtn.classList.remove("active");
            if (welcomeLandingSection) welcomeLandingSection.style.display = "none";
            if (citizenDashboardSection) citizenDashboardSection.style.display = "none";
            if (dashboardSection) dashboardSection.style.display = "none";
            if (newInspectionSection) newInspectionSection.style.display = "none";
            if (recordsSection) recordsSection.style.display = "none";
            if (recordDetailSection) recordDetailSection.style.display = "none";
            if (mapSection) mapSection.style.display = "flex";
            if (reportsSection) reportsSection.style.display = "none";
            if (queueSection) queueSection.style.display = "none";
            if (usersSection) usersSection.style.display = "none";
            initDefectMap();
            loadMapRecords();
            window.scrollTo({ top: 0, behavior: "smooth" });
        } else if (viewName === "reports") {
            if (tabDashboardBtn) tabDashboardBtn.classList.remove("active");
            if (tabNewInspectionBtn) tabNewInspectionBtn.classList.remove("active");
            if (tabRecordsBtn) tabRecordsBtn.classList.remove("active");
            if (tabMapBtn) tabMapBtn.classList.remove("active");
            if (tabReportsBtn) tabReportsBtn.classList.add("active");
            if (tabQueueBtn) tabQueueBtn.classList.remove("active");
            if (tabUsersBtn) tabUsersBtn.classList.remove("active");
            if (welcomeLandingSection) welcomeLandingSection.style.display = "none";
            if (citizenDashboardSection) citizenDashboardSection.style.display = "none";
            if (dashboardSection) dashboardSection.style.display = "none";
            if (newInspectionSection) newInspectionSection.style.display = "none";
            if (recordsSection) recordsSection.style.display = "none";
            if (recordDetailSection) recordDetailSection.style.display = "none";
            if (mapSection) mapSection.style.display = "none";
            if (reportsSection) reportsSection.style.display = "flex";
            if (queueSection) queueSection.style.display = "none";
            if (usersSection) usersSection.style.display = "none";
            loadReportPreview();
            window.scrollTo({ top: 0, behavior: "smooth" });
        } else if (viewName === "queue") {
            if (tabDashboardBtn) tabDashboardBtn.classList.remove("active");
            if (tabNewInspectionBtn) tabNewInspectionBtn.classList.remove("active");
            if (tabRecordsBtn) tabRecordsBtn.classList.remove("active");
            if (tabMapBtn) tabMapBtn.classList.remove("active");
            if (tabReportsBtn) tabReportsBtn.classList.remove("active");
            if (tabQueueBtn) tabQueueBtn.classList.add("active");
            if (tabUsersBtn) tabUsersBtn.classList.remove("active");
            if (welcomeLandingSection) welcomeLandingSection.style.display = "none";
            if (citizenDashboardSection) citizenDashboardSection.style.display = "none";
            if (dashboardSection) dashboardSection.style.display = "none";
            if (newInspectionSection) newInspectionSection.style.display = "none";
            if (recordsSection) recordsSection.style.display = "none";
            if (recordDetailSection) recordDetailSection.style.display = "none";
            if (mapSection) mapSection.style.display = "none";
            if (reportsSection) reportsSection.style.display = "none";
            if (queueSection) queueSection.style.display = "flex";
            if (usersSection) usersSection.style.display = "none";
            loadMaintenanceQueue();
            window.scrollTo({ top: 0, behavior: "smooth" });
        } else if (viewName === "users") {
            if (tabDashboardBtn) tabDashboardBtn.classList.remove("active");
            if (tabNewInspectionBtn) tabNewInspectionBtn.classList.remove("active");
            if (tabRecordsBtn) tabRecordsBtn.classList.remove("active");
            if (tabMapBtn) tabMapBtn.classList.remove("active");
            if (tabReportsBtn) tabReportsBtn.classList.remove("active");
            if (tabQueueBtn) tabQueueBtn.classList.remove("active");
            if (tabUsersBtn) tabUsersBtn.classList.add("active");
            if (welcomeLandingSection) welcomeLandingSection.style.display = "none";
            if (citizenDashboardSection) citizenDashboardSection.style.display = "none";
            if (dashboardSection) dashboardSection.style.display = "none";
            if (newInspectionSection) newInspectionSection.style.display = "none";
            if (recordsSection) recordsSection.style.display = "none";
            if (recordDetailSection) recordDetailSection.style.display = "none";
            if (mapSection) mapSection.style.display = "none";
            if (reportsSection) reportsSection.style.display = "none";
            if (queueSection) queueSection.style.display = "none";
            if (usersSection) usersSection.style.display = "block";
            loadUsers();
            window.scrollTo({ top: 0, behavior: "smooth" });
        } else if (viewName === "detail") {
            if (tabDashboardBtn) tabDashboardBtn.classList.remove("active");
            if (tabNewInspectionBtn) tabNewInspectionBtn.classList.remove("active");
            if (tabRecordsBtn) tabRecordsBtn.classList.add("active");
            if (tabMapBtn) tabMapBtn.classList.remove("active");
            if (tabReportsBtn) tabReportsBtn.classList.remove("active");
            if (tabQueueBtn) tabQueueBtn.classList.remove("active");
            if (tabUsersBtn) tabUsersBtn.classList.remove("active");
            if (welcomeLandingSection) welcomeLandingSection.style.display = "none";
            if (citizenDashboardSection) citizenDashboardSection.style.display = "none";
            if (dashboardSection) dashboardSection.style.display = "none";
            if (newInspectionSection) newInspectionSection.style.display = "none";
            if (recordsSection) recordsSection.style.display = "none";
            if (recordDetailSection) recordDetailSection.style.display = "flex";
            if (mapSection) mapSection.style.display = "none";
            if (reportsSection) reportsSection.style.display = "none";
            if (queueSection) queueSection.style.display = "none";
            if (usersSection) usersSection.style.display = "none";

            if (currentUser && currentUser.role === "citizen") {
                if (detailAssignmentCard) detailAssignmentCard.style.display = "none";
                const statusFormRow = document.querySelector(".status-form-row");
                if (statusFormRow) statusFormRow.style.display = "none";
            }
            window.scrollTo({ top: 0, behavior: "smooth" });
        }

        try {
            if (viewName !== "detail" && window.location.hash !== "#" + viewName) {
                history.replaceState(null, "", "#" + viewName);
            }
        } catch (_) {}
    }

    if (tabDashboardBtn) tabDashboardBtn.addEventListener("click", () => switchView("dashboard"));
    if (tabNewInspectionBtn) tabNewInspectionBtn.addEventListener("click", () => switchView("new"));
    if (tabRecordsBtn) tabRecordsBtn.addEventListener("click", () => switchView("records"));
    if (tabMapBtn) tabMapBtn.addEventListener("click", () => switchView("map"));
    if (tabReportsBtn) tabReportsBtn.addEventListener("click", () => switchView("reports"));
    if (tabQueueBtn) tabQueueBtn.addEventListener("click", () => switchView("queue"));
    if (tabUsersBtn) tabUsersBtn.addEventListener("click", () => switchView("users"));
    if (backToRecordsBtn) backToRecordsBtn.addEventListener("click", () => {
        if (currentUser && currentUser.role === "citizen") {
            switchView("dashboard");
        } else {
            switchView("records");
        }
    });
    if (dashStartInspectionBtn) dashStartInspectionBtn.addEventListener("click", () => switchView("new"));
    if (dashEmptyNewInspectionBtn) dashEmptyNewInspectionBtn.addEventListener("click", () => switchView("new"));
    if (dashViewAllRecordsBtn) dashViewAllRecordsBtn.addEventListener("click", () => switchView("records"));
    if (refreshDashboardBtn) refreshDashboardBtn.addEventListener("click", loadDashboardStats);

    // Quick filter handlers for Phase 4.4 Dashboard Deadline Cards & Alert Banner
    function filterRecordsByDeadline(filterVal) {
        if (recordsDeadlineFilter) recordsDeadlineFilter.value = filterVal;
        if (recordsStatusFilter) recordsStatusFilter.value = "";
        if (recordsCategoryFilter) recordsCategoryFilter.value = "";
        if (recordsSearchInput) recordsSearchInput.value = "";
        switchView("records");
        loadRecords();
    }

    if (deadlineBoxOverdue) deadlineBoxOverdue.addEventListener("click", () => filterRecordsByDeadline("overdue"));
    if (deadlineBoxToday) deadlineBoxToday.addEventListener("click", () => filterRecordsByDeadline("due_today"));
    if (deadlineBoxUpcoming) deadlineBoxUpcoming.addEventListener("click", () => filterRecordsByDeadline("upcoming"));
    if (deadlineBoxResolved) deadlineBoxResolved.addEventListener("click", () => filterRecordsByDeadline("resolved"));
    if (deadlineBoxNone) deadlineBoxNone.addEventListener("click", () => filterRecordsByDeadline("no_deadline"));
    if (viewOverdueRecordsBtn) viewOverdueRecordsBtn.addEventListener("click", () => filterRecordsByDeadline("overdue"));
    if (viewDueTodayRecordsBtn) viewDueTodayRecordsBtn.addEventListener("click", () => filterRecordsByDeadline("due_today"));

    // Initialize Leaflet Map
    function initDefectMap() {
        if (typeof L === "undefined") {
            if (mapErrorBanner && mapErrorMsg) {
                mapErrorBanner.style.display = "flex";
                mapErrorMsg.textContent = "Leaflet mapping library is currently unavailable. Please verify network connectivity to load map tiles and scripts.";
            }
            return;
        }

        if (!defectMapInstance) {
            const mapContainer = document.getElementById("defectMap");
            if (!mapContainer) return;

            defectMapInstance = L.map("defectMap", {
                center: [20.5937, 78.9629],
                zoom: 5,
                minZoom: 3,
                maxZoom: 19,
                zoomControl: true,
            });

            const osmTiles = L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
                maxZoom: 19,
                attribution: '&copy; <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener">OpenStreetMap</a> contributors | VisionGuard AI',
            });

            osmTiles.on("tileerror", (err) => {
                console.warn("Leaflet tile error:", err);
                if (mapErrorBanner && mapErrorMsg) {
                    mapErrorBanner.style.display = "flex";
                    mapErrorMsg.textContent = "Some map tiles could not be loaded from OpenStreetMap. Please verify internet connection.";
                }
            });

            osmTiles.addTo(defectMapInstance);
            markersLayerGroup = L.featureGroup().addTo(defectMapInstance);
        }

        setTimeout(() => {
            if (defectMapInstance) {
                defectMapInstance.invalidateSize();
            }
        }, 120);
    }

    // Load Records from Flask API for Defect Map
    async function loadMapRecords() {
        if (!currentUser) {
            if (mapErrorBanner && mapErrorMsg) {
                mapErrorBanner.style.display = "flex";
                mapErrorMsg.innerHTML = `🔒 Authentication Required. Please <button class="btn btn-sm btn-primary guest-login-btn" style="margin-left: 0.5rem;">Sign In</button> to view defect map.`;
                bindGuestLoginButtons();
            }
            return;
        }
        if (mapErrorBanner) mapErrorBanner.style.display = "none";
        try {
            const res = await fetch("/api/inspections?limit=500");
            const data = await res.json();
            if (!res.ok || data.status !== "success") {
                throw new Error(data.message || `Failed to fetch inspections (HTTP ${res.status})`);
            }
            cachedMapRecords = data.inspections || [];
            renderMapMarkers();
        } catch (err) {
            console.error("Map records load error:", err);
            if (mapErrorBanner && mapErrorMsg) {
                mapErrorBanner.style.display = "flex";
                mapErrorMsg.textContent = `Could not load defect records from server: ${err.message}`;
            }
        }
    }

    // Check if record matches category, status, deadline, and keyword filters
    function filterMapRecord(rec, domainFilter, catFilter, statusFilter, deadlineFilter, kwFilter) {
        if (!isValidCoordinate(rec.latitude, rec.longitude)) return false;

        if (domainFilter && domainFilter !== "all") {
            if (domainFilter === "road" && rec.inspection_type === "home") return false;
            if (domainFilter === "home" && rec.inspection_type !== "home") return false;
        }

        if (statusFilter && rec.status !== statusFilter) {
            return false;
        }

        if (deadlineFilter) {
            const urgency = rec.maintenance_urgency || (rec.status === "Resolved" ? "resolved" : "no_deadline");
            if (urgency !== deadlineFilter) {
                return false;
            }
        }

        if (catFilter) {
            const cfg = getMarkerConfig(rec);
            if (catFilter === "Sound") {
                if (cfg.category !== "Sound") return false;
            } else if (catFilter === "Longitudinal") {
                if (cfg.category !== "Longitudinal") return false;
            } else if (catFilter === "Transverse") {
                if (cfg.category !== "Transverse") return false;
            } else if (catFilter === "Alligator") {
                if (cfg.category !== "Alligator") return false;
            } else if (catFilter === "Pothole") {
                if (cfg.category !== "Pothole") return false;
            } else if (catFilter === "Wall Crack") {
                if (cfg.category !== "Wall Crack") return false;
            } else if (catFilter === "Dampness") {
                if (cfg.category !== "Dampness") return false;
            } else if (catFilter === "Peeling Paint") {
                if (cfg.category !== "Peeling Paint") return false;
            } else if (catFilter === "Spalling") {
                if (cfg.category !== "Spalling") return false;
            } else {
                const dt = (rec.defect_type || "").toLowerCase();
                if (!dt.includes(catFilter.toLowerCase()) && cfg.category !== catFilter) return false;
            }
        }

        if (kwFilter) {
            const q = kwFilter.toLowerCase();
            const road = (rec.road_name || "").toLowerCase();
            const area = (rec.area || "").toLowerCase();
            const city = (rec.city || "").toLowerCase();
            const notes = (rec.location_notes || "").toLowerCase();
            const idStr = String(rec.id);
            if (!road.includes(q) && !area.includes(q) && !city.includes(q) && !notes.includes(q) && !idStr.includes(q)) {
                return false;
            }
        }

        return true;
    }

    // Update legend counters based on all valid geotagged records
    function updateMapLegendCounts(geotaggedRecords) {
        let d00 = 0, d10 = 0, d20 = 0, d40 = 0, wall = 0, damp = 0, peel = 0, spall = 0, sound = 0;
        geotaggedRecords.forEach(rec => {
            const cfg = getMarkerConfig(rec);
            if (cfg.category === "Sound") sound++;
            else if (cfg.category === "Pothole") d40++;
            else if (cfg.category === "Alligator") d20++;
            else if (cfg.category === "Transverse") d10++;
            else if (cfg.category === "Wall Crack") wall++;
            else if (cfg.category === "Dampness") damp++;
            else if (cfg.category === "Peeling Paint") peel++;
            else if (cfg.category === "Spalling") spall++;
            else d00++;
        });

        if (legendCountD00) legendCountD00.textContent = `${d00} record${d00 === 1 ? "" : "s"}`;
        if (legendCountD10) legendCountD10.textContent = `${d10} record${d10 === 1 ? "" : "s"}`;
        if (legendCountD20) legendCountD20.textContent = `${d20} record${d20 === 1 ? "" : "s"}`;
        if (legendCountD40) legendCountD40.textContent = `${d40} record${d40 === 1 ? "" : "s"}`;
        if (legendCountWall) legendCountWall.textContent = `${wall} record${wall === 1 ? "" : "s"}`;
        if (legendCountDamp) legendCountDamp.textContent = `${damp} record${damp === 1 ? "" : "s"}`;
        if (legendCountPeel) legendCountPeel.textContent = `${peel} record${peel === 1 ? "" : "s"}`;
        if (legendCountSpall) legendCountSpall.textContent = `${spall} record${spall === 1 ? "" : "s"}`;
        if (legendCountSound) legendCountSound.textContent = `${sound} record${sound === 1 ? "" : "s"}`;
    }

    // Render Markers on Leaflet Map
    function renderMapMarkers() {
        if (!defectMapInstance || !markersLayerGroup) return;

        // Clear existing markers to prevent duplicates
        markersLayerGroup.clearLayers();

        const domainFilter = mapDomainFilter ? mapDomainFilter.value : "all";
        const catFilter = mapCategoryFilter ? mapCategoryFilter.value : "";
        const statusFilter = mapStatusFilter ? mapStatusFilter.value : "";
        const deadlineFilter = mapDeadlineFilter ? mapDeadlineFilter.value : "";
        const kwFilter = mapSearchInput ? mapSearchInput.value.trim() : "";

        // Genuine coordinates only
        const validGeotagged = cachedMapRecords.filter(r => isValidCoordinate(r.latitude, r.longitude));
        const totalGeotagged = validGeotagged.length;

        updateMapLegendCounts(validGeotagged);

        if (totalGeotagged === 0) {
            if (mapEmptyState) mapEmptyState.style.display = "block";
            if (mapLayoutWrapper) mapLayoutWrapper.style.display = "none";
            if (mapTelemetryBadge) mapTelemetryBadge.textContent = "Mapped: 0 / 0";
            if (mapCountBadgeHeader) mapCountBadgeHeader.textContent = "0";
            return;
        }

        if (mapEmptyState) mapEmptyState.style.display = "none";
        if (mapLayoutWrapper) mapLayoutWrapper.style.display = "grid";

        const filtered = validGeotagged.filter(rec => filterMapRecord(rec, domainFilter, catFilter, statusFilter, deadlineFilter, kwFilter));
        const markerList = [];

        filtered.forEach(rec => {
            const markerCfg = getMarkerConfig(rec);
            const lat = parseFloat(rec.latitude);
            const lon = parseFloat(rec.longitude);

            const customIcon = L.divIcon({
                className: "custom-defect-marker",
                html: `<div class="marker-bubble ${markerCfg.pinClass}" title="#${rec.id}: ${escapeHtml(markerCfg.label)}"><span>${markerCfg.code}</span></div>`,
                iconSize: [30, 30],
                iconAnchor: [15, 30],
                popupAnchor: [0, -32],
            });

            const marker = L.marker([lat, lon], { icon: customIcon });
            const popupHtml = buildMapPopup(rec, markerCfg);
            marker.bindPopup(popupHtml, { maxWidth: 300, minWidth: 240 });

            markersLayerGroup.addLayer(marker);
            markerList.push(marker);
        });

        if (mapTelemetryBadge) {
            mapTelemetryBadge.textContent = `Mapped: ${markerList.length} / ${totalGeotagged}`;
        }
        if (mapCountBadgeHeader) {
            mapCountBadgeHeader.textContent = totalGeotagged;
        }

        // Fit map viewport safely
        if (markerList.length === 0) {
            // Keep current view or overview
        } else if (markerList.length === 1) {
            const pos = markerList[0].getLatLng();
            defectMapInstance.setView(pos, 14);
        } else {
            try {
                defectMapInstance.fitBounds(markersLayerGroup.getBounds().pad(0.12), { maxZoom: 16 });
            } catch (_) {}
        }
    }

    // Map Filter Event Listeners
    if (mapDomainFilter) mapDomainFilter.addEventListener("change", renderMapMarkers);
    if (mapCategoryFilter) mapCategoryFilter.addEventListener("change", renderMapMarkers);
    if (mapStatusFilter) mapStatusFilter.addEventListener("change", renderMapMarkers);
    if (mapDeadlineFilter) mapDeadlineFilter.addEventListener("change", renderMapMarkers);
    if (mapSearchInput) mapSearchInput.addEventListener("input", debounce(renderMapMarkers, 250));
    if (resetMapFiltersBtn) {
        resetMapFiltersBtn.addEventListener("click", () => {
            if (mapDomainFilter) mapDomainFilter.value = "all";
            if (mapCategoryFilter) mapCategoryFilter.value = "";
            if (mapStatusFilter) mapStatusFilter.value = "";
            if (mapDeadlineFilter) mapDeadlineFilter.value = "";
            if (mapSearchInput) mapSearchInput.value = "";
            renderMapMarkers();
        });
    }
    if (refreshMapBtn) refreshMapBtn.addEventListener("click", loadMapRecords);
    if (mapEmptyNewInspBtn) mapEmptyNewInspBtn.addEventListener("click", () => switchView("new"));
    if (mapEmptyViewRecordsBtn) mapEmptyViewRecordsBtn.addEventListener("click", () => switchView("records"));

    // Fetch count of geotagged records for header badge
    async function loadMapHeaderCount() {
        if (!currentUser) return;
        try {
            const res = await fetch("/api/inspections?has_coords=true&limit=500");
            const data = await res.json();
            if (data.status === "success" && mapCountBadgeHeader) {
                mapCountBadgeHeader.textContent = data.count || 0;
            }
        } catch (_) {}
    }

    // Initial Count Fetch
    async function loadRecordsHeaderCount() {
        if (!currentUser) return;
        try {
            const res = await fetch("/api/inspections?limit=1");
            const data = await res.json();
            if (data.status === "success" && recordsCountBadgeHeader) {
                const healthRes = await fetch("/api/health");
                const healthData = await healthRes.json();
                const total = (healthData.database && healthData.database.records_count) || data.count || 0;
                recordsCountBadgeHeader.textContent = total;
            }
        } catch (_) {}
        loadMapHeaderCount();
    }

    // Save Inspection Action (with duplicate protection)
    if (saveInspectionBtn) {
        saveInspectionBtn.addEventListener("click", async () => {
            if (!currentUser) {
                openAuthModal();
                return;
            }
            if (!lastInspectionResult || isSaving) return;

            isSaving = true;
            saveInspectionBtn.disabled = true;
            saveSpinner.style.display = "inline-block";
            saveInspectionBtn.querySelector(".btn-text").textContent = "Saving to SQLite...";

            const roadName = saveRoadNameInput ? saveRoadNameInput.value.trim() : "";
            const area = saveAreaInput ? saveAreaInput.value.trim() : "";
            const city = saveCityInput ? saveCityInput.value.trim() : "";
            const latStr = saveLatInput ? saveLatInput.value.trim() : "";
            const lonStr = saveLonInput ? saveLonInput.value.trim() : "";
            const locationNotes = saveNotesInput ? saveNotesInput.value.trim() : "";
            const status = saveStatusSelect ? saveStatusSelect.value : "Open";

            let latVal = null;
            if (latStr !== "") {
                latVal = parseFloat(latStr);
                if (isNaN(latVal) || latVal < -90 || latVal > 90) {
                    alert("Latitude must be a valid number between -90.0 and +90.0 degrees.");
                    isSaving = false;
                    saveInspectionBtn.disabled = false;
                    saveSpinner.style.display = "none";
                    saveInspectionBtn.querySelector(".btn-text").textContent = "Save Inspection Record";
                    return;
                }
            }

            let lonVal = null;
            if (lonStr !== "") {
                lonVal = parseFloat(lonStr);
                if (isNaN(lonVal) || lonVal < -180 || lonVal > 180) {
                    alert("Longitude must be a valid number between -180.0 and +180.0 degrees.");
                    isSaving = false;
                    saveInspectionBtn.disabled = false;
                    saveSpinner.style.display = "none";
                    saveInspectionBtn.querySelector(".btn-text").textContent = "Save Inspection Record";
                    return;
                }
            }

            const targetRepairDate = saveTargetDateInput ? saveTargetDateInput.value.trim() : "";

            const payload = {
                image_name: lastInspectionResult.filename,
                original_image_path: lastInspectionResult.original_file_path || "",
                annotated_image_path: lastInspectionResult.processed_file_path || "",
                road_name: roadName,
                area: area,
                city: city,
                latitude: latVal,
                longitude: lonVal,
                location_notes: locationNotes,
                target_repair_date: targetRepairDate || null,
                inspection_mode: lastInspectionResult.inspection_mode || "standard",
                confidence_threshold: lastInspectionResult.confidence_threshold || 0.25,
                detections: lastInspectionResult.detections || [],
                status: status,
                inspection_type: (lastInspectionResult && lastInspectionResult.domain) || selectedDomain || "road",
            };

            try {
                const res = await fetch("/api/inspections", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify(payload),
                });
                const data = await res.json();

                if (res.status === 409 && data.inspection) {
                    const savedRecord = data.inspection;
                    saveInspectionBtn.querySelector(".btn-text").textContent = `Already Saved as Record #${savedRecord.id}`;
                    saveCardStatusBadge.textContent = `Saved (#${savedRecord.id})`;
                    saveCardStatusBadge.className = "badge badge-info";

                    saveFeedback.innerHTML = `
                        <span style="color: var(--text-secondary); display: inline-flex; align-items: center; gap: 0.4rem; flex-wrap: wrap;">
                            <span>ℹ️</span> ${data.message || "This inspection is already saved."}
                            <button type="button" class="btn btn-secondary btn-sm" id="viewSavedRecordBtn" style="margin-left: 0.5rem; padding: 0.25rem 0.65rem; font-size: 0.8rem;">
                                View in Records History →
                            </button>
                            <button type="button" class="btn btn-outline-warning btn-sm" id="draftComplaintFromSaveBtn" style="margin-left: 0.25rem; padding: 0.25rem 0.65rem; font-size: 0.8rem;">
                                📝 Draft Complaint Notice
                            </button>
                        </span>
                    `;
                    saveFeedback.style.display = "inline-block";

                    const viewBtn = document.getElementById("viewSavedRecordBtn");
                    if (viewBtn) {
                        viewBtn.addEventListener("click", () => {
                            switchView("records");
                            openRecordDetail(savedRecord.id);
                        });
                    }
                    const draftBtn = document.getElementById("draftComplaintFromSaveBtn");
                    if (draftBtn) {
                        draftBtn.addEventListener("click", () => {
                            openComplaintDraftModal(savedRecord.id);
                        });
                    }

                    loadRecordsHeaderCount();
                    return;
                }

                if (!res.ok || data.status !== "success") {
                    throw new Error(data.message || `Save failed (HTTP ${res.status})`);
                }

                const savedRecord = data.inspection;
                saveInspectionBtn.querySelector(".btn-text").textContent = `✅ Saved as Record #${savedRecord.id}`;
                saveCardStatusBadge.textContent = `Saved (#${savedRecord.id})`;
                saveCardStatusBadge.className = "badge badge-success";

                saveFeedback.innerHTML = `
                    <span style="color: var(--success); display: inline-flex; align-items: center; gap: 0.4rem; flex-wrap: wrap;">
                        <span>✓</span> Successfully persisted to database.
                        <button type="button" class="btn btn-secondary btn-sm" id="viewSavedRecordBtn" style="margin-left: 0.5rem; padding: 0.25rem 0.65rem; font-size: 0.8rem;">
                            View in Records History →
                        </button>
                        <button type="button" class="btn btn-outline-warning btn-sm" id="draftComplaintFromSaveBtn" style="margin-left: 0.25rem; padding: 0.25rem 0.65rem; font-size: 0.8rem;">
                            📝 Draft Complaint Notice
                        </button>
                    </span>
                `;
                saveFeedback.style.display = "inline-block";

                const viewBtn = document.getElementById("viewSavedRecordBtn");
                if (viewBtn) {
                    viewBtn.addEventListener("click", () => {
                        switchView("records");
                        openRecordDetail(savedRecord.id);
                    });
                }
                const draftBtn = document.getElementById("draftComplaintFromSaveBtn");
                if (draftBtn) {
                    draftBtn.addEventListener("click", () => {
                        openComplaintDraftModal(savedRecord.id);
                    });
                }

                loadRecordsHeaderCount();
            } catch (err) {
                console.error("Save inspection failed:", err);
                alert(`Error saving inspection record:\n${err.message}`);
                saveInspectionBtn.disabled = false;
                saveInspectionBtn.querySelector(".btn-text").textContent = "Retry Save";
                isSaving = false;
            } finally {
                saveSpinner.style.display = "none";
            }
        });
    }

    // Load Records History
    // Debounce helper for search input
    function debounce(fn, delay) {
        let timer = null;
        return function(...args) {
            clearTimeout(timer);
            timer = setTimeout(() => fn.apply(this, args), delay);
        };
    }

    // Load Dashboard Statistics & Analytics
    async function loadDashboardStats() {
        if (!dashTotalInspections) return;
        if (!currentUser) {
            renderGuestDashboard();
            return;
        }

        try {
            const res = await fetch("/api/dashboard/stats");
            const data = await res.json();
            if (!res.ok || data.status !== "success") {
                throw new Error(data.message || "Failed to load dashboard metrics");
            }

            const stats = data.stats || {};
            const totalInspections = stats.total_inspections || 0;
            const totalDefects = stats.total_defects || 0;
            const openRecords = stats.open_records || 0;
            const inProgressRecords = stats.in_progress_records || 0;
            const resolvedRecords = stats.resolved_records || 0;

            dashTotalInspections.textContent = totalInspections;
            dashTotalDefects.textContent = totalDefects;
            dashOpenRecords.textContent = openRecords;
            dashInProgressRecords.textContent = inProgressRecords;
            dashResolvedRecords.textContent = resolvedRecords;

            // Maintenance Deadlines Breakdown (Phase 4.4)
            const maint = stats.maintenance_summary || {};
            const overdueCount = maint.overdue_count || 0;
            const dueTodayCount = maint.due_today_count || 0;
            const upcomingCount = maint.upcoming_count || 0;
            const resolvedMaintCount = maint.resolved_count || 0;
            const noDeadlineCount = maint.no_deadline_count || 0;
            const actionableCount = maint.actionable_maintenance || 0;

            if (dashOverdueCount) dashOverdueCount.textContent = overdueCount;
            if (dashDueTodayCount) dashDueTodayCount.textContent = dueTodayCount;
            if (dashUpcomingCount) dashUpcomingCount.textContent = upcomingCount;
            if (dashResolvedMaintCount) dashResolvedMaintCount.textContent = resolvedMaintCount;
            if (dashNoDeadlinesCount) dashNoDeadlinesCount.textContent = noDeadlineCount;
            if (maintenanceActionableBadge) maintenanceActionableBadge.textContent = `${actionableCount} Actionable`;

            // Follow-up In-App Notification Alert Banner
            if (maintenanceAlertBanner) {
                if (overdueCount > 0 || dueTodayCount > 0) {
                    maintenanceAlertBanner.style.display = "flex";
                    if (maintenanceAlertCountBadge) {
                        const parts = [];
                        if (overdueCount > 0) parts.push(`${overdueCount} Overdue`);
                        if (dueTodayCount > 0) parts.push(`${dueTodayCount} Due Today`);
                        maintenanceAlertCountBadge.textContent = parts.join(" • ");
                        maintenanceAlertCountBadge.className = overdueCount > 0 ? "badge badge-deadline-overdue" : "badge badge-deadline-today";
                    }
                    if (maintenanceAlertMsg) {
                        let msgText = "";
                        if (overdueCount > 0 && dueTodayCount > 0) {
                            msgText = `Database registry highlights ${overdueCount} unremediated defect repair${overdueCount === 1 ? ' is' : 's are'} past deadline and ${dueTodayCount} repair${dueTodayCount === 1 ? ' is' : 's are'} scheduled for completion today.`;
                        } else if (overdueCount > 0) {
                            msgText = `Database registry highlights ${overdueCount} unremediated defect repair${overdueCount === 1 ? ' is' : 's are'} past scheduled deadline. Immediate follow-up recommended.`;
                        } else {
                            msgText = `Database registry highlights ${dueTodayCount} defect repair${dueTodayCount === 1 ? ' is' : 's are'} due for remediation today.`;
                        }
                        maintenanceAlertMsg.textContent = msgText;
                    }
                } else {
                    maintenanceAlertBanner.style.display = "none";
                }
            }

            if (recordsCountBadgeHeader) recordsCountBadgeHeader.textContent = totalInspections;

            // Defect categories breakdown
            const cats = stats.defect_categories || {};
            const longCount = cats["Longitudinal Crack"] || 0;
            const transCount = cats["Transverse Crack"] || 0;
            const alliCount = cats["Alligator Crack"] || 0;
            const potCount = cats["Pothole"] || 0;

            if (dashDefectsTotalBadge) {
                dashDefectsTotalBadge.textContent = `${totalDefects} Total Distress Instances`;
            }

            if (totalDefects === 0) {
                if (dashDefectsEmptyState) dashDefectsEmptyState.style.display = "block";
                if (dashCategoryBarsContainer) dashCategoryBarsContainer.style.display = "none";
            } else {
                if (dashDefectsEmptyState) dashDefectsEmptyState.style.display = "none";
                if (dashCategoryBarsContainer) dashCategoryBarsContainer.style.display = "flex";

                const longPct = ((longCount / totalDefects) * 100).toFixed(1);
                const transPct = ((transCount / totalDefects) * 100).toFixed(1);
                const alliPct = ((alliCount / totalDefects) * 100).toFixed(1);
                const potPct = ((potCount / totalDefects) * 100).toFixed(1);

                if (statCatLongitudinal) statCatLongitudinal.textContent = `${longCount} (${longPct}%)`;
                if (barCatLongitudinal) barCatLongitudinal.style.width = `${longPct}%`;

                if (statCatTransverse) statCatTransverse.textContent = `${transCount} (${transPct}%)`;
                if (barCatTransverse) barCatTransverse.style.width = `${transPct}%`;

                if (statCatAlligator) statCatAlligator.textContent = `${alliCount} (${alliPct}%)`;
                if (barCatAlligator) barCatAlligator.style.width = `${alliPct}%`;

                if (statCatPothole) statCatPothole.textContent = `${potCount} (${potPct}%)`;
                if (barCatPothole) barCatPothole.style.width = `${potPct}%`;

                // Home / Building Defect Categories Breakdown
                const homeCats = stats.building_defect_categories || {};
                const wallCount = homeCats["Wall Crack"] || 0;
                const dampCount = homeCats["Dampness"] || 0;
                const peelCount = homeCats["Peeling Paint"] || 0;
                const spallCount = homeCats["Spalling"] || 0;
                const totalHomeDefects = wallCount + dampCount + peelCount + spallCount;

                const itemCatWall = document.getElementById("itemCatWall");
                const itemCatDamp = document.getElementById("itemCatDamp");
                const itemCatPeel = document.getElementById("itemCatPeel");
                const itemCatSpall = document.getElementById("itemCatSpall");
                const statCatWall = document.getElementById("statCatWall");
                const barCatWall = document.getElementById("barCatWall");
                const statCatDamp = document.getElementById("statCatDamp");
                const barCatDamp = document.getElementById("barCatDamp");
                const statCatPeel = document.getElementById("statCatPeel");
                const barCatPeel = document.getElementById("barCatPeel");
                const statCatSpall = document.getElementById("statCatSpall");
                const barCatSpall = document.getElementById("barCatSpall");

                if (totalHomeDefects > 0) {
                    if (itemCatWall) itemCatWall.style.display = "block";
                    if (itemCatDamp) itemCatDamp.style.display = "block";
                    if (itemCatPeel) itemCatPeel.style.display = "block";
                    if (itemCatSpall) itemCatSpall.style.display = "block";

                    const wallPct = totalDefects > 0 ? ((wallCount / totalDefects) * 100).toFixed(1) : "0.0";
                    const dampPct = totalDefects > 0 ? ((dampCount / totalDefects) * 100).toFixed(1) : "0.0";
                    const peelPct = totalDefects > 0 ? ((peelCount / totalDefects) * 100).toFixed(1) : "0.0";
                    const spallPct = totalDefects > 0 ? ((spallCount / totalDefects) * 100).toFixed(1) : "0.0";

                    if (statCatWall) statCatWall.textContent = `${wallCount} (${wallPct}%)`;
                    if (barCatWall) barCatWall.style.width = `${wallPct}%`;
                    if (statCatDamp) statCatDamp.textContent = `${dampCount} (${dampPct}%)`;
                    if (barCatDamp) barCatDamp.style.width = `${dampPct}%`;
                    if (statCatPeel) statCatPeel.textContent = `${peelCount} (${peelPct}%)`;
                    if (barCatPeel) barCatPeel.style.width = `${peelPct}%`;
                    if (statCatSpall) statCatSpall.textContent = `${spallCount} (${spallPct}%)`;
                    if (barCatSpall) barCatSpall.style.width = `${spallPct}%`;
                } else {
                    if (itemCatWall) itemCatWall.style.display = "none";
                    if (itemCatDamp) itemCatDamp.style.display = "none";
                    if (itemCatPeel) itemCatPeel.style.display = "none";
                    if (itemCatSpall) itemCatSpall.style.display = "none";
                }
            }

            // Workflow status distribution
            if (totalInspections > 0) {
                const openPct = ((openRecords / totalInspections) * 100).toFixed(1);
                const progPct = ((inProgressRecords / totalInspections) * 100).toFixed(1);
                const resPct = ((resolvedRecords / totalInspections) * 100).toFixed(1);

                if (segmentOpen) segmentOpen.style.width = `${openPct}%`;
                if (segmentProgress) segmentProgress.style.width = `${progPct}%`;
                if (segmentResolved) segmentResolved.style.width = `${resPct}%`;

                if (legendOpenCount) legendOpenCount.textContent = openRecords;
                if (legendOpenPct) legendOpenPct.textContent = `${openPct}%`;
                if (legendProgressCount) legendProgressCount.textContent = inProgressRecords;
                if (legendProgressPct) legendProgressPct.textContent = `${progPct}%`;
                if (legendResolvedCount) legendResolvedCount.textContent = resolvedRecords;
                if (legendResolvedPct) legendResolvedPct.textContent = `${resPct}%`;
            } else {
                if (segmentOpen) segmentOpen.style.width = "0%";
                if (segmentProgress) segmentProgress.style.width = "0%";
                if (segmentResolved) segmentResolved.style.width = "0%";
                if (legendOpenCount) legendOpenCount.textContent = "0";
                if (legendOpenPct) legendOpenPct.textContent = "0%";
                if (legendProgressCount) legendProgressCount.textContent = "0";
                if (legendProgressPct) legendProgressPct.textContent = "0%";
                if (legendResolvedCount) legendResolvedCount.textContent = "0";
                if (legendResolvedPct) legendResolvedPct.textContent = "0%";
            }

            // Recent inspections
            renderRecentTable(stats.recent_inspections || []);
        } catch (err) {
            console.error("Dashboard stats error:", err);
        }
    }

    // Render Recent Inspections Table on Dashboard
    function renderRecentTable(inspections) {
        if (!dashRecentTableBody) return;
        dashRecentTableBody.innerHTML = "";

        if (!inspections || inspections.length === 0) {
            if (dashEmptyState) dashEmptyState.style.display = "block";
            if (dashRecentTable) dashRecentTable.style.display = "none";
            return;
        }

        if (dashEmptyState) dashEmptyState.style.display = "none";
        if (dashRecentTable) dashRecentTable.style.display = "table";

        inspections.forEach(rec => {
            const tr = document.createElement("tr");
            const roadDisplay = formatLocationDisplay(rec);
            const countDisplay = rec.defect_count > 0 
                ? `<span class="badge badge-warning" style="font-weight: 700;">${rec.defect_count} Defect${rec.defect_count === 1 ? "" : "s"}</span>`
                : `<span class="badge badge-success">0 (Sound)</span>`;
            const confDisplay = rec.defect_count > 0 && rec.confidence ? `${(rec.confidence * 100).toFixed(1)}%` : "N/A";
            const statusClass = getStatusBadgeClass(rec.status);

            const deadlineDisplay = getDeadlineBadge(rec);

            tr.innerHTML = `
                <td><strong>#${rec.id}</strong></td>
                <td>${roadDisplay}</td>
                <td><span style="font-size: 0.82rem; color: var(--text-secondary);">${formatDateTime(rec.uploaded_at)}</span></td>
                <td>${countDisplay}</td>
                <td><strong>${confDisplay}</strong></td>
                <td><span class="${statusClass}">${rec.status}</span></td>
                <td>${deadlineDisplay}</td>
                <td>
                    <button type="button" class="btn btn-secondary btn-sm open-recent-btn" data-id="${rec.id}">
                        👁️ View Details
                    </button>
                </td>
            `;
            dashRecentTableBody.appendChild(tr);
        });

        document.querySelectorAll(".open-recent-btn").forEach(btn => {
            btn.addEventListener("click", () => {
                const id = btn.getAttribute("data-id");
                openRecordDetail(id);
            });
        });
    }

    // Load Records History
    async function loadRecords() {
        if (!currentUser) {
            recordsTableBody.innerHTML = `<tr><td colspan="10" style="text-align: center; padding: 2.5rem; color: var(--text-muted);">
                🔒 Authentication Required. Please <button class="btn btn-sm btn-primary guest-login-btn" style="margin-left: 0.5rem;">Sign In</button> to view inspection records.
            </td></tr>`;
            bindGuestLoginButtons();
            return;
        }

        const recordsDomainFilter = document.getElementById("recordsDomainFilter");
        const filterDomain = recordsDomainFilter ? recordsDomainFilter.value : "";
        const filterStatus = recordsStatusFilter ? recordsStatusFilter.value : "";
        const filterCategory = recordsCategoryFilter ? recordsCategoryFilter.value : "";
        const filterDeadline = recordsDeadlineFilter ? recordsDeadlineFilter.value : "";
        const filterSearch = recordsSearchInput ? recordsSearchInput.value.trim() : "";

        recordsTableBody.innerHTML = `<tr><td colspan="10" style="text-align: center; padding: 2rem; color: var(--text-muted);">Loading inspection records...</td></tr>`;

        try {
            const params = new URLSearchParams();
            if (filterDomain) params.append("domain", filterDomain);
            if (filterStatus) params.append("status", filterStatus);
            if (filterCategory) params.append("category", filterCategory);
            if (filterDeadline) params.append("deadline", filterDeadline);
            if (filterSearch) params.append("q", filterSearch);

            const queryString = params.toString();
            const url = queryString ? `/api/inspections?${queryString}` : "/api/inspections";
            const res = await fetch(url);
            const data = await res.json();

            if (!res.ok || data.status !== "success") {
                throw new Error(data.message || "Failed to load inspections");
            }

            const inspections = data.inspections || [];
            renderRecordsTable(inspections);
            updateRecordsStats(inspections);
            loadRecordsHeaderCount();
        } catch (err) {
            console.error("Load records error:", err);
            recordsTableBody.innerHTML = `<tr><td colspan="10" style="text-align: center; color: var(--danger); padding: 1.5rem;">Failed to load records: ${err.message}</td></tr>`;
        }
    }

    const recordsDomainFilterEl = document.getElementById("recordsDomainFilter");
    if (recordsDomainFilterEl) recordsDomainFilterEl.addEventListener("change", loadRecords);
    if (recordsStatusFilter) recordsStatusFilter.addEventListener("change", loadRecords);
    if (recordsCategoryFilter) recordsCategoryFilter.addEventListener("change", loadRecords);
    if (recordsDeadlineFilter) recordsDeadlineFilter.addEventListener("change", loadRecords);
    if (recordsSearchInput) recordsSearchInput.addEventListener("input", debounce(loadRecords, 300));
    if (resetRecordsFiltersBtn) {
        resetRecordsFiltersBtn.addEventListener("click", () => {
            const domFilter = document.getElementById("recordsDomainFilter");
            if (domFilter) domFilter.value = "";
            if (recordsStatusFilter) recordsStatusFilter.value = "";
            if (recordsCategoryFilter) recordsCategoryFilter.value = "";
            if (recordsDeadlineFilter) recordsDeadlineFilter.value = "";
            if (recordsSearchInput) recordsSearchInput.value = "";
            loadRecords();
        });
    }
    if (refreshRecordsBtn) refreshRecordsBtn.addEventListener("click", loadRecords);

    // Update Summary Metric Cards
    function updateRecordsStats(inspections) {
        if (!statTotalInspections) return;
        const total = inspections.length;
        const openCount = inspections.filter(i => i.status === "Open").length;
        const activeCount = inspections.filter(i => i.status === "In Progress" || i.status === "Under Review" || i.status === "Repair in Progress").length;
        const resolvedCount = inspections.filter(i => i.status === "Resolved").length;

        statTotalInspections.textContent = total;
        statOpenInspections.textContent = openCount;
        statActiveInspections.textContent = activeCount;
        statResolvedInspections.textContent = resolvedCount;
    }

    // Render Records Table
    function renderRecordsTable(inspections) {
        recordsTableBody.innerHTML = "";
        if (!inspections || inspections.length === 0) {
            recordsEmptyState.style.display = "block";
            recordsTable.style.display = "none";
            return;
        }

        recordsEmptyState.style.display = "none";
        recordsTable.style.display = "table";

        inspections.forEach(rec => {
            const tr = document.createElement("tr");
            const roadDisplay = formatLocationDisplay(rec);
            const countDisplay = rec.defect_count > 0 
                ? `<span class="badge badge-warning" style="font-weight: 700;">${rec.defect_count} Defect${rec.defect_count === 1 ? "" : "s"}</span>`
                : `<span class="badge badge-success">0 (Sound)</span>`;
            
            const confDisplay = rec.defect_count > 0 && rec.confidence ? `${(rec.confidence * 100).toFixed(1)}%` : "N/A";
            const modeDisplay = (rec.inspection_mode || "standard") === "tiled" ? "🔬 Tiled" : "⚡ Standard";
            const statusClass = getStatusBadgeClass(rec.status);

            const deadlineDisplay = getDeadlineBadge(rec);
            const domainBadge = (rec.inspection_type === "home") 
                ? '<span class="badge" style="background: rgba(168, 85, 247, 0.2); color: #c084fc; font-size: 0.72rem; padding: 2px 6px; display: inline-block; margin-top: 2px;">🏠 Home</span>'
                : '<span class="badge" style="background: rgba(14, 165, 233, 0.2); color: #38bdf8; font-size: 0.72rem; padding: 2px 6px; display: inline-block; margin-top: 2px;">🛣️ Road</span>';

            tr.innerHTML = `
                <td>
                    <strong>#${rec.id}</strong><br>
                    ${domainBadge}
                </td>
                <td><span style="font-size: 0.82rem; color: var(--text-secondary);">${formatDateTime(rec.uploaded_at)}</span></td>
                <td>
                    ${roadDisplay}
                    ${rec.location_notes ? `<div style="font-size: 0.75rem; color: var(--text-muted); max-width: 200px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; margin-top: 2px;">${rec.location_notes}</div>` : ""}
                </td>
                <td>${countDisplay}</td>
                <td><span style="font-size: 0.82rem;">${rec.defect_type || "--"}</span></td>
                <td><strong>${confDisplay}</strong></td>
                <td><span style="font-size: 0.78rem; color: var(--text-secondary);">${modeDisplay}</span></td>
                <td><span class="${statusClass}">${rec.status}</span></td>
                <td>${deadlineDisplay}</td>
                <td>
                    <button type="button" class="btn btn-secondary btn-sm open-record-btn" data-id="${rec.id}">
                        👁️ View Details
                    </button>
                </td>
            `;
            recordsTableBody.appendChild(tr);
        });

        // Bind Open Details clicks
        document.querySelectorAll(".open-record-btn").forEach(btn => {
            btn.addEventListener("click", () => {
                const id = btn.getAttribute("data-id");
                openRecordDetail(id);
            });
        });
    }

    // Open Record Detail View
    async function openRecordDetail(id) {
        if (!currentUser) {
            alert("Authentication required. Please sign in to view inspection details.");
            switchView("dashboard");
            openAuthModal();
            return;
        }

        currentDetailId = id;
        switchView("detail");

        detailRecordIdHeader.textContent = `Inspection Record #${id} — Loading...`;
        detailStatusFeedback.style.display = "none";
        detailDetectionsTableBody.innerHTML = `<tr><td colspan="7" style="text-align: center; padding: 1.5rem; color: var(--text-muted);">Loading inspection telemetry...</td></tr>`;

        try {
            const res = await fetch(`/api/inspections/${id}`);
            const data = await res.json();
            if (!res.ok || data.status !== "success") {
                throw new Error(data.message || `Record #${id} not found.`);
            }

            const rec = data.inspection;

            // Header & Status
            const locTitle = [rec.road_name, rec.area, rec.city].filter(Boolean).join(", ") || rec.image_name;
            detailRecordIdHeader.textContent = `Inspection Record #${rec.id} — ${locTitle}`;
            detailCurrentStatusBadge.textContent = rec.status;
            detailCurrentStatusBadge.className = getStatusBadgeClass(rec.status);
            if (detailStatusSelect) detailStatusSelect.value = rec.status;
            if (detailStatusNotes) detailStatusNotes.value = rec.notes || rec.location_notes || "";

            // Images via safe streaming endpoints
            detailOriginalImg.src = `/api/inspections/${id}/image/original`;
            detailAnnotatedImg.src = `/api/inspections/${id}/image/annotated`;

            // Telemetry
            const locSummary = [rec.road_name, rec.area, rec.city].filter(Boolean).join(", ");
            detailRoadName.textContent = locSummary || "Unspecified Location";
            detailLocationNotes.textContent = rec.location_notes || "No notes entered";
            detailDefectCount.textContent = rec.defect_count;
            detailDefectTypes.textContent = rec.defect_type || "None";
            detailTopConf.textContent = (rec.defect_count > 0 && rec.confidence) ? `${(rec.confidence * 100).toFixed(1)}%` : "N/A";
            detailTimestamp.textContent = formatDateTime(rec.uploaded_at);
            detailInspectionMode.textContent = (rec.inspection_mode === "tiled" ? "Tiled Slicing" : "Standard Full-Frame") + ` (≥ ${rec.confidence_threshold.toFixed(2)})`;

            // Spatial Location Card
            if (detailLocRoad) detailLocRoad.textContent = rec.road_name || "Unspecified";
            if (detailLocArea) detailLocArea.textContent = rec.area || "Not Specified";
            if (detailLocCity) detailLocCity.textContent = rec.city || "Not Specified";
            
            const hasCoords = (rec.latitude !== null && rec.latitude !== undefined && rec.longitude !== null && rec.longitude !== undefined);
            if (detailLocCoords) {
                if (hasCoords) {
                    detailLocCoords.innerHTML = `<strong>${Number(rec.latitude).toFixed(6)}°, ${Number(rec.longitude).toFixed(6)}°</strong>`;
                } else {
                    detailLocCoords.textContent = "Coordinates not recorded";
                }
            }

            if (detailGpsBadge) {
                if (hasCoords) {
                    detailGpsBadge.textContent = "📍 GPS Geotagged";
                    detailGpsBadge.className = "badge gps-badge-active";
                } else {
                    detailGpsBadge.textContent = "GPS: Not Recorded";
                    detailGpsBadge.className = "badge gps-badge-none";
                }
            }

            if (detailLocNotes) detailLocNotes.textContent = rec.location_notes || "No notes entered";

            // Target Repair Date & Deadline Card
            if (detailTargetDateInput) {
                detailTargetDateInput.value = rec.target_repair_date || "";
            }
            if (detailTargetDateDisplay) {
                detailTargetDateDisplay.textContent = rec.target_repair_date || "Not Scheduled";
            }
            if (detailUrgencyDisplay) {
                detailUrgencyDisplay.textContent = rec.maintenance_label || "No Target Date";
            }
            if (detailRemainingDisplay) {
                if (rec.status === "Resolved") {
                    detailRemainingDisplay.textContent = "Remediation Workflow Closed";
                } else if (rec.maintenance_urgency === "overdue") {
                    detailRemainingDisplay.textContent = `Overdue by ${Math.abs(rec.days_remaining || 0)} day(s)`;
                } else if (rec.maintenance_urgency === "due_today") {
                    detailRemainingDisplay.textContent = "Deadline is Today";
                } else if (rec.maintenance_urgency === "upcoming") {
                    detailRemainingDisplay.textContent = `${rec.days_remaining || 0} day(s) remaining`;
                } else {
                    detailRemainingDisplay.textContent = "No target date scheduled";
                }
            }
            if (detailDeadlineBadge) {
                const urg = rec.maintenance_urgency || (rec.status === "Resolved" ? "resolved" : "no_deadline");
                detailDeadlineBadge.textContent = rec.maintenance_label || "No Target Date";
                switch (urg) {
                    case "overdue":
                        detailDeadlineBadge.className = "badge badge-deadline-overdue";
                        break;
                    case "due_today":
                        detailDeadlineBadge.className = "badge badge-deadline-today";
                        break;
                    case "upcoming":
                        detailDeadlineBadge.className = "badge badge-deadline-upcoming";
                        break;
                    case "resolved":
                        detailDeadlineBadge.className = "badge badge-deadline-resolved";
                        break;
                    default:
                        detailDeadlineBadge.className = "badge badge-deadline-none";
                        break;
                }
            }

            // Render Chronological Activity History
            renderActivityHistory(rec.activity_log || []);

            // Phase 4.7: Populate Maintenance Task Assignment Detail Card
            const assignStatus = rec.assignment_status || "unassigned";
            if (detailAssignmentStatusBadge) {
                detailAssignmentStatusBadge.textContent = formatAssignmentStatus(assignStatus);
                detailAssignmentStatusBadge.className = getAssignmentBadgeClass(assignStatus);
            }

            if (detailAssigneeDisplay) {
                if (rec.assigned_to_username) {
                    detailAssigneeDisplay.textContent = rec.assigned_to_username;
                    if (rec.assigned_to_user_active === false) {
                        detailAssigneeActiveDisplay.innerHTML = '<span class="badge badge-warning" style="font-size:0.7rem; padding: 1px 5px;">⚠️ Account Deactivated</span>';
                    } else {
                        detailAssigneeActiveDisplay.innerHTML = '<span class="badge badge-status-active" style="font-size:0.7rem; padding: 1px 5px;">Active Staff</span>';
                    }
                } else {
                    detailAssigneeDisplay.textContent = "Unassigned";
                    detailAssigneeActiveDisplay.textContent = "No technician assigned";
                }
            }

            if (detailAssignedByDisplay) detailAssignedByDisplay.textContent = rec.assigned_by_username || "—";
            if (detailAssignedAtDisplay) detailAssignedAtDisplay.textContent = formatDateTime(rec.assigned_at);
            if (detailAssignmentUpdatedDisplay) detailAssignmentUpdatedDisplay.textContent = formatDateTime(rec.assignment_updated_at || rec.assigned_at);
            if (detailAssignmentInstructionsDisplay) detailAssignmentInstructionsDisplay.textContent = rec.assignment_instructions || "No special instructions provided.";

            // Admin Actions visibility
            const isAdmin = currentUser && currentUser.role === "admin";
            if (detailAssignmentAdminActions) {
                if (isAdmin) {
                    detailAssignmentAdminActions.style.display = "flex";
                    if (assignStatus === "assigned" || assignStatus === "in_progress") {
                        if (cancelAssignmentBtn) cancelAssignmentBtn.style.display = "inline-flex";
                        if (openAssignTaskModalBtn) openAssignTaskModalBtn.innerHTML = "🔄 Reassign Task";
                    } else {
                        if (cancelAssignmentBtn) cancelAssignmentBtn.style.display = "none";
                        if (openAssignTaskModalBtn) openAssignTaskModalBtn.innerHTML = "👤 Assign Task";
                    }
                } else {
                    detailAssignmentAdminActions.style.display = "none";
                }
            }

            // Render assignment history
            renderAssignmentHistory(rec.assignments || []);

            // Detections Table
            const detections = rec.detections || [];
            detailDetectionsTableBody.innerHTML = "";
            if (detections.length === 0) {
                const tr = document.createElement("tr");
                tr.innerHTML = `<td colspan="7" style="text-align: center; color: var(--text-muted); padding: 1.5rem;">✅ No defects detected at confidence threshold ≥ ${rec.confidence_threshold.toFixed(2)}.</td>`;
                detailDetectionsTableBody.appendChild(tr);
            } else {
                detections.forEach((det, idx) => {
                    const tr = document.createElement("tr");
                    const bbox = det.bbox || {};
                    const coords = `[${bbox.x1}, ${bbox.y1}, ${bbox.x2}, ${bbox.y2}]`;
                    const extent = `${bbox.width} × ${bbox.height} px`;
                    const src = det.source || "global";
                    const srcBadge = src === "tiled"
                        ? '<span class="badge badge-info" style="font-size: 0.72rem; padding: 2px 6px;">🔬 Tiled</span>'
                        : '<span class="badge badge-secondary" style="font-size: 0.72rem; padding: 2px 6px;">⚡ Full-Frame</span>';

                    tr.innerHTML = `
                        <td><strong>${idx + 1}</strong></td>
                        <td><span class="badge badge-info">${det.distress_category || det.class_name}</span></td>
                        <td><code>${det.class_name || "D" + det.class_id}</code></td>
                        <td><strong>${((det.confidence || 0) * 100).toFixed(1)}%</strong></td>
                        <td>${srcBadge}</td>
                        <td><code>${coords}</code></td>
                        <td>${extent}</td>
                    `;
                    detailDetectionsTableBody.appendChild(tr);
                });
            }

            // Phase 4: Citizen Read-Only Status & Municipal Disclaimer Handling
            const detailStatusFormRow = document.getElementById("detailStatusFormRow");
            const detailCitizenReadOnlyNotice = document.getElementById("detailCitizenReadOnlyNotice");
            const detailCitizenInspectionStatusBadge = document.getElementById("detailCitizenInspectionStatusBadge");
            const detailAssignmentCard = document.getElementById("detailAssignmentCard");

            if (currentUser && currentUser.role === "citizen") {
                if (detailStatusFormRow) detailStatusFormRow.style.display = "none";
                if (detailCitizenReadOnlyNotice) detailCitizenReadOnlyNotice.style.display = "block";
                if (detailCitizenInspectionStatusBadge) {
                    detailCitizenInspectionStatusBadge.textContent = rec.status || "Open";
                    detailCitizenInspectionStatusBadge.className = `badge ${getStatusBadgeClass(rec.status)}`;
                }
                if (detailAssignmentCard) detailAssignmentCard.style.display = "none";
                if (backToRecordsBtn) backToRecordsBtn.textContent = "← Back to My Reports";
            } else {
                if (detailStatusFormRow) detailStatusFormRow.style.display = "flex";
                if (detailCitizenReadOnlyNotice) detailCitizenReadOnlyNotice.style.display = "none";
                if (detailAssignmentCard) detailAssignmentCard.style.display = "block";
                if (backToRecordsBtn) backToRecordsBtn.textContent = "← Back to Inspection Records";
            }

            // Phase 4: Populate Civic Complaint Draft & Municipal Filing Card
            const detailComplaintStatusBadge = document.getElementById("detailComplaintStatusBadge");
            const detailComplaintStatusDisplay = document.getElementById("detailComplaintStatusDisplay");
            const detailComplaintChannelDisplay = document.getElementById("detailComplaintChannelDisplay");
            const detailComplaintRefDisplay = document.getElementById("detailComplaintRefDisplay");
            const detailComplaintSubmittedAtDisplay = document.getElementById("detailComplaintSubmittedAtDisplay");
            const detailComplaintSubjectDisplay = document.getElementById("detailComplaintSubjectDisplay");
            const detailOpenComplaintDraftBtn = document.getElementById("detailOpenComplaintDraftBtn");

            const cd = rec.complaint_draft;
            const cdStatus = (rec.complaint_status || (cd && cd.status) || "none").toLowerCase();

            if (detailComplaintStatusBadge) {
                detailComplaintStatusBadge.textContent = formatComplaintStatus(cdStatus);
                detailComplaintStatusBadge.className = `badge ${getComplaintBadgeClass(cdStatus)}`;
            }
            if (detailComplaintStatusDisplay) {
                detailComplaintStatusDisplay.textContent = formatComplaintStatus(cdStatus);
            }
            if (detailComplaintChannelDisplay) {
                detailComplaintChannelDisplay.textContent = (cd && cd.submission_channel) || rec.submission_channel || "Not recorded";
            }
            if (detailComplaintRefDisplay) {
                detailComplaintRefDisplay.textContent = (cd && cd.submission_reference) || rec.submission_reference || "None";
            }
            if (detailComplaintSubmittedAtDisplay) {
                const subAt = (cd && cd.submitted_at) || rec.submitted_at;
                detailComplaintSubmittedAtDisplay.textContent = subAt ? formatDateTime(subAt) : "Not submitted";
            }
            if (detailComplaintSubjectDisplay) {
                if (cd && (cd.recipient_agency || cd.subject)) {
                    detailComplaintSubjectDisplay.innerHTML = `<strong>Recipient Authority:</strong> ${escapeHtml(cd.recipient_agency || "Not Specified")}<br><strong>Subject:</strong> ${escapeHtml(cd.subject || "Civic Grievance Notice")}`;
                } else {
                    detailComplaintSubjectDisplay.textContent = "No formal complaint draft created yet. Click 'View / Edit Complaint Draft' to prepare an official municipal grievance letter.";
                }
            }
            if (detailOpenComplaintDraftBtn) {
                detailOpenComplaintDraftBtn.onclick = () => openComplaintDraftModal(rec.id);
            }
        } catch (err) {
            console.error("Open detail error:", err);
            alert(`Failed to load inspection detail:\n${err.message}`);
            if (currentUser && currentUser.role === "citizen") {
                switchView("dashboard");
            } else {
                switchView("records");
            }
        }
    }

    // Status Update Action & Dynamic Notes Requirement (Phase 5)
    if (detailStatusSelect) {
        detailStatusSelect.addEventListener("change", () => {
            const val = detailStatusSelect.value;
            if (val === "Resolved") {
                if (detailStatusNotes) {
                    detailStatusNotes.placeholder = "Required: Enter physical verification evidence, repair actions taken, and findings...";
                }
            } else if (val === "Reopened") {
                if (detailStatusNotes) {
                    detailStatusNotes.placeholder = "Required: Enter reason for reopening inspection report...";
                }
            } else {
                if (detailStatusNotes) {
                    detailStatusNotes.placeholder = "Enter internal repair notes, workflow updates, or progress comments...";
                }
            }
        });
    }

    if (updateStatusBtn) {
        updateStatusBtn.addEventListener("click", async () => {
            if (!currentDetailId) return;

            const newStatus = detailStatusSelect ? detailStatusSelect.value : "";
            const targetRepairDate = detailTargetDateInput ? detailTargetDateInput.value.trim() : "";
            const notes = detailStatusNotes ? detailStatusNotes.value.trim() : "";

            // Client-side validations for required notes
            if (newStatus === "Resolved" && !notes) {
                detailStatusFeedback.innerHTML = `
                    <div class="alert alert-danger alert-sm" style="margin-top: 0.75rem;">
                        <strong>⚠️ Resolution Notes Required:</strong> Please enter verified physical repair evidence and findings before resolving this report.
                    </div>
                `;
                detailStatusFeedback.style.display = "block";
                if (detailStatusNotes) detailStatusNotes.focus();
                return;
            }

            if (newStatus === "Reopened" && !notes) {
                detailStatusFeedback.innerHTML = `
                    <div class="alert alert-danger alert-sm" style="margin-top: 0.75rem;">
                        <strong>⚠️ Reason Required:</strong> Please enter a reason note for reopening this inspection report.
                    </div>
                `;
                detailStatusFeedback.style.display = "block";
                if (detailStatusNotes) detailStatusNotes.focus();
                return;
            }

            updateStatusBtn.disabled = true;
            updateStatusSpinner.style.display = "inline-block";
            detailStatusFeedback.style.display = "none";

            try {
                const res = await fetch(`/api/inspections/${currentDetailId}/status`, {
                    method: "PATCH",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ 
                        status: newStatus, 
                        target_repair_date: targetRepairDate || null,
                        notes: notes 
                    }),
                });
                const data = await res.json();

                if (!res.ok || data.status !== "success") {
                    throw new Error(data.message || `Update failed (HTTP ${res.status})`);
                }

                const updatedRec = data.inspection || {};
                detailCurrentStatusBadge.textContent = newStatus;
                detailCurrentStatusBadge.className = getStatusBadgeClass(newStatus);

                // Update detail deadline views
                if (detailTargetDateDisplay) {
                    detailTargetDateDisplay.textContent = updatedRec.target_repair_date || "Not Scheduled";
                }
                if (detailUrgencyDisplay) {
                    detailUrgencyDisplay.textContent = updatedRec.maintenance_label || "No Target Date";
                }
                if (detailRemainingDisplay) {
                    if (updatedRec.status === "Resolved") {
                        detailRemainingDisplay.textContent = "Remediation Workflow Closed";
                    } else if (updatedRec.maintenance_urgency === "overdue") {
                        detailRemainingDisplay.textContent = `Overdue by ${Math.abs(updatedRec.days_remaining || 0)} day(s)`;
                    } else if (updatedRec.maintenance_urgency === "due_today") {
                        detailRemainingDisplay.textContent = "Deadline is Today";
                    } else if (updatedRec.maintenance_urgency === "upcoming") {
                        detailRemainingDisplay.textContent = `${updatedRec.days_remaining || 0} day(s) remaining`;
                    } else {
                        detailRemainingDisplay.textContent = "No target date scheduled";
                    }
                }
                if (detailDeadlineBadge) {
                    const urg = updatedRec.maintenance_urgency || (updatedRec.status === "Resolved" ? "resolved" : "no_deadline");
                    detailDeadlineBadge.textContent = updatedRec.maintenance_label || "No Target Date";
                    switch (urg) {
                        case "overdue":
                            detailDeadlineBadge.className = "badge badge-deadline-overdue";
                            break;
                        case "due_today":
                            detailDeadlineBadge.className = "badge badge-deadline-today";
                            break;
                        case "upcoming":
                            detailDeadlineBadge.className = "badge badge-deadline-upcoming";
                            break;
                        case "resolved":
                            detailDeadlineBadge.className = "badge badge-deadline-resolved";
                            break;
                        default:
                            detailDeadlineBadge.className = "badge badge-deadline-none";
                            break;
                    }
                }

                // Clear entered notes input for subsequent updates
                if (detailStatusNotes) {
                    detailStatusNotes.value = "";
                }

                // Refresh activity log
                try {
                    const actRes = await fetch(`/api/inspections/${currentDetailId}/activity`);
                    const actData = await actRes.json();
                    if (actData.status === "success") {
                        renderActivityHistory(actData.activities || []);
                    }
                } catch (_) {}

                detailStatusFeedback.innerHTML = `
                    <div class="alert alert-success alert-sm" style="margin-top: 0.75rem;">
                        <strong>✓ Record Updated:</strong> Inspection #${currentDetailId} updated successfully.
                    </div>
                `;
                detailStatusFeedback.style.display = "block";

                loadRecordsHeaderCount();
                loadDashboardStats();
                loadMaintenanceQueue();
            } catch (err) {
                console.error("Status update error:", err);
                detailStatusFeedback.innerHTML = `
                    <div class="alert alert-danger alert-sm" style="margin-top: 0.75rem;">
                        <strong>⚠️ Update Failed:</strong> ${escapeHtml(err.message)}
                    </div>
                `;
                detailStatusFeedback.style.display = "block";
            } finally {
                updateStatusBtn.disabled = false;
                updateStatusSpinner.style.display = "none";
            }
        });
    }

    // -------------------------------------------------------------------------
    // Phase 4.5: Report Generation, PDF / CSV Export & Print Logic
    // -------------------------------------------------------------------------
    function buildReportQueryString() {
        const params = new URLSearchParams();
        const reportDomainFilter = document.getElementById("reportDomainFilter");
        if (reportDomainFilter && reportDomainFilter.value) params.set("domain", reportDomainFilter.value);
        if (reportStartDate && reportStartDate.value) params.set("start_date", reportStartDate.value.trim());
        if (reportEndDate && reportEndDate.value) params.set("end_date", reportEndDate.value.trim());
        if (reportCategoryFilter && reportCategoryFilter.value) params.set("category", reportCategoryFilter.value);
        if (reportStatusFilter && reportStatusFilter.value) params.set("status", reportStatusFilter.value);
        if (reportDeadlineFilter && reportDeadlineFilter.value) params.set("deadline", reportDeadlineFilter.value);
        if (reportCityFilter && reportCityFilter.value.trim()) params.set("city", reportCityFilter.value.trim());
        if (reportAreaFilter && reportAreaFilter.value.trim()) params.set("area", reportAreaFilter.value.trim());
        if (reportSearchInput && reportSearchInput.value.trim()) params.set("q", reportSearchInput.value.trim());
        return params.toString();
    }

    async function loadReportPreview() {
        if (!reportPreviewContainer) return;
        if (!currentUser) {
            if (reportErrorBanner && reportErrorMsg) {
                reportErrorBanner.style.display = "flex";
                reportErrorMsg.innerHTML = `🔒 Authentication Required. Please <button class="btn btn-sm btn-primary guest-login-btn" style="margin-left: 0.5rem;">Sign In</button> to view inspection reports.`;
                bindGuestLoginButtons();
            }
            if (reportSpinner) reportSpinner.style.display = "none";
            if (generateReportBtn) generateReportBtn.disabled = false;
            return;
        }

        if (reportErrorBanner) reportErrorBanner.style.display = "none";
        if (reportSpinner) reportSpinner.style.display = "inline-block";
        if (generateReportBtn) generateReportBtn.disabled = true;

        try {
            const qs = buildReportQueryString();
            const url = qs ? `/api/reports/preview?${qs}` : "/api/reports/preview";
            const res = await fetch(url);
            const data = await res.json();

            if (!res.ok || data.status !== "success") {
                throw new Error(data.message || `Failed to fetch report preview (HTTP ${res.status})`);
            }

            const report = data.report || {};
            const summary = report.summary || {};
            const records = report.records || [];
            const filters = report.applied_filters || {};

            // Update badge
            if (reportMatchingBadge) {
                reportMatchingBadge.textContent = `${summary.total_inspections || 0} Records Matching`;
            }

            // Check for empty dataset
            if (!records || records.length === 0) {
                if (reportEmptyState) reportEmptyState.style.display = "block";
                if (reportPreviewContainer) reportPreviewContainer.style.display = "none";
                return;
            }

            if (reportEmptyState) reportEmptyState.style.display = "none";
            if (reportPreviewContainer) reportPreviewContainer.style.display = "flex";

            // Metadata
            if (prevGeneratedAt) prevGeneratedAt.textContent = report.generated_at || "--";
            if (prevReferenceDate) prevReferenceDate.textContent = report.reference_date || "--";
            if (prevRecordCount) prevRecordCount.textContent = summary.total_inspections || 0;

            // Filter summary text
            if (prevFilterText) {
                const parts = [];
                if (filters.start_date || filters.end_date) {
                    parts.push(`Date: ${filters.start_date || "Start"} to ${filters.end_date || "Present"}`);
                }
                if (filters.category) parts.push(`Category: ${filters.category}`);
                if (filters.status) parts.push(`Status: ${filters.status}`);
                if (filters.deadline) parts.push(`Deadline: ${filters.deadline.replace(/_/g, " ")}`);
                if (filters.city) parts.push(`City: ${filters.city}`);
                if (filters.area) parts.push(`Area: ${filters.area}`);
                if (filters.search_query) parts.push(`Search: "${filters.search_query}"`);
                prevFilterText.textContent = parts.length > 0 ? parts.join(" • ") : "All Saved Records (No constraints applied)";
            }

            // KPIs
            if (prevTotalInspections) prevTotalInspections.textContent = summary.total_inspections || 0;
            if (prevTotalDefects) prevTotalDefects.textContent = summary.total_defects || 0;
            if (prevActiveOrders) prevActiveOrders.textContent = summary.active_unresolved || 0;
            if (prevOverdueRepairs) prevOverdueRepairs.textContent = summary.overdue_count || 0;

            // Category breakdown table
            if (prevCategoryTableBody) {
                prevCategoryTableBody.innerHTML = "";
                const catDist = summary.category_distribution || {};
                const totalDef = summary.total_defects || 0;
                const totalInsp = summary.total_inspections || 0;

                const catList = ["Longitudinal Crack", "Transverse Crack", "Alligator Crack", "Pothole", "Sound Surface"];
                catList.forEach(cname => {
                    const cnt = catDist[cname] || 0;
                    const pct = (totalDef > 0 && cname !== "Sound Surface")
                        ? `${((cnt / totalDef) * 100).toFixed(1)}%`
                        : (totalInsp > 0 && cname === "Sound Surface" ? `${((cnt / totalInsp) * 100).toFixed(1)}%` : "0.0%");

                    const tr = document.createElement("tr");
                    tr.innerHTML = `
                        <td><strong>${escapeHtml(cname)}</strong></td>
                        <td><span class="badge ${cnt > 0 ? 'badge-info' : 'badge-secondary'}">${cnt}</span></td>
                        <td>${pct}</td>
                    `;
                    prevCategoryTableBody.appendChild(tr);
                });
            }

            // Compliance & Workflow table
            if (prevComplianceTableBody) {
                prevComplianceTableBody.innerHTML = "";
                const stDist = summary.status_distribution || {};
                const urgDist = summary.deadline_distribution || {};

                const compRows = [
                    { label: "Open Records", count: stDist.Open || 0, desc: "Awaiting technical review", badgeClass: "badge-info" },
                    { label: "Under Review / Repair", count: (stDist["Repair in Progress"] || 0) + (stDist["Under Review"] || 0), desc: "Active maintenance action", badgeClass: "badge-warning" },
                    { label: "Resolved Records", count: stDist.Resolved || 0, desc: "Remediation closed", badgeClass: "badge-success" },
                    { label: "Overdue Maintenance", count: urgDist.overdue || 0, desc: "Target repair date passed", badgeClass: "badge-danger" },
                    { label: "Due Today / Upcoming", count: (urgDist.due_today || 0) + (urgDist.upcoming || 0), desc: "Scheduled remediation", badgeClass: "badge-primary" },
                ];

                compRows.forEach(item => {
                    const tr = document.createElement("tr");
                    tr.innerHTML = `
                        <td><strong>${escapeHtml(item.label)}</strong></td>
                        <td><span class="badge ${item.badgeClass}">${item.count}</span></td>
                        <td style="color: var(--text-secondary); font-size: 0.8rem;">${escapeHtml(item.desc)}</td>
                    `;
                    prevComplianceTableBody.appendChild(tr);
                });
            }

            // Itemized Records Table
            if (prevTableBadge) {
                prevTableBadge.textContent = `${records.length} Record${records.length === 1 ? '' : 's'}`;
            }

            if (prevRecordsTableBody) {
                prevRecordsTableBody.innerHTML = "";
                records.forEach((r, idx) => {
                    const tr = document.createElement("tr");

                    const locRoad = r.road_name ? `<strong>${escapeHtml(r.road_name)}</strong>` : "<em>Unspecified Road</em>";
                    const subLoc = [r.area, r.city].filter(Boolean).map(escapeHtml).join(", ");
                    const locHtml = subLoc ? `${locRoad}<br/><small style="color: var(--text-muted);">${subLoc}</small>` : locRoad;

                    const gpsHtml = r.has_coords
                        ? `<code style="font-size: 0.75rem;">${escapeHtml(r.coords_display)}</code>`
                        : `<span style="color: var(--text-muted); font-size: 0.75rem;">Not recorded</span>`;

                    const countHtml = r.defect_count > 0
                        ? `<strong class="text-danger">${r.defect_count}</strong>`
                        : `<span class="text-success">0</span>`;

                    const catHtml = `<span style="font-size: 0.8rem;">${escapeHtml(r.defect_type || "None")}</span>`;
                    const confHtml = r.defect_count > 0 ? `<strong>${r.confidence_pct || "N/A"}</strong>` : "N/A";

                    const stClass = getStatusBadgeClass(r.status);
                    const stHtml = `<span class="${stClass}" style="font-size: 0.72rem; padding: 2px 7px;">${escapeHtml(r.status)}</span>`;

                    const dlBadge = getDeadlineBadge(r);
                    const auditHtml = `<span style="font-size: 0.75rem; color: var(--text-secondary);">${escapeHtml(r.latest_activity || "Created")}</span>`;

                    tr.innerHTML = `
                        <td><strong>#${r.id}</strong></td>
                        <td style="white-space: nowrap; font-size: 0.78rem;">${escapeHtml(r.uploaded_at ? r.uploaded_at.substring(0, 10) : "")}</td>
                        <td>${locHtml}</td>
                        <td>${gpsHtml}</td>
                        <td style="text-align: center;">${countHtml}</td>
                        <td>${catHtml}</td>
                        <td style="text-align: center;">${confHtml}</td>
                        <td>${stHtml}</td>
                        <td>${dlBadge}</td>
                        <td>${auditHtml}</td>
                    `;
                    prevRecordsTableBody.appendChild(tr);
                });
            }
        } catch (err) {
            console.error("Load report preview error:", err);
            if (reportErrorBanner && reportErrorMsg) {
                reportErrorBanner.style.display = "flex";
                reportErrorMsg.textContent = `Could not generate report preview: ${err.message}`;
            }
            if (reportEmptyState) reportEmptyState.style.display = "none";
            if (reportPreviewContainer) reportPreviewContainer.style.display = "none";
        } finally {
            if (reportSpinner) reportSpinner.style.display = "none";
            if (generateReportBtn) generateReportBtn.disabled = false;
        }
    }

    if (generateReportBtn) generateReportBtn.addEventListener("click", loadReportPreview);
    if (resetReportFiltersBtn) {
        resetReportFiltersBtn.addEventListener("click", () => {
            const domFilter = document.getElementById("reportDomainFilter");
            if (domFilter) domFilter.value = "";
            if (reportStartDate) reportStartDate.value = "";
            if (reportEndDate) reportEndDate.value = "";
            if (reportCategoryFilter) reportCategoryFilter.value = "";
            if (reportStatusFilter) reportStatusFilter.value = "";
            if (reportDeadlineFilter) reportDeadlineFilter.value = "";
            if (reportCityFilter) reportCityFilter.value = "";
            if (reportAreaFilter) reportAreaFilter.value = "";
            if (reportSearchInput) reportSearchInput.value = "";
            loadReportPreview();
        });
    }
    if (reportResetFromEmptyBtn) {
        reportResetFromEmptyBtn.addEventListener("click", () => {
            if (resetReportFiltersBtn) resetReportFiltersBtn.click();
        });
    }

    if (exportPdfBtn) {
        exportPdfBtn.addEventListener("click", () => {
            const qs = buildReportQueryString();
            window.location.href = qs ? `/api/reports/export/pdf?${qs}` : "/api/reports/export/pdf";
        });
    }

    if (exportCsvBtn) {
        exportCsvBtn.addEventListener("click", () => {
            const qs = buildReportQueryString();
            window.location.href = qs ? `/api/reports/export/csv?${qs}` : "/api/reports/export/csv";
        });
    }

    if (printReportBtn) {
        printReportBtn.addEventListener("click", () => {
            window.print();
        });
    }

    // -------------------------------------------------------------------------
    // Phase 4.6 & Citizen Mode: Authentication & User Management Logic
    // -------------------------------------------------------------------------

    function getRoleBadgeClass(role) {
        switch (String(role || "").toLowerCase()) {
            case "admin": return "badge-role-admin";
            case "inspector": return "badge-role-inspector";
            case "maintenance": return "badge-role-maintenance";
            case "citizen": return "badge-role-citizen";
            default: return "badge-secondary";
        }
    }

    function formatRole(role) {
        switch (String(role || "").toLowerCase()) {
            case "admin": return "Administrator";
            case "inspector": return "Inspector";
            case "maintenance": return "Maintenance Staff";
            case "citizen": return "Citizen";
            default: return role || "Unknown";
        }
    }

    function getComplaintBadgeClass(status) {
        const st = (status || "").toLowerCase();
        if (st === "submitted") return "badge-status-resolved";
        if (st === "ready_to_submit") return "badge-status-active";
        if (st === "draft" || st === "exported") return "badge-warning";
        return "badge-secondary";
    }

    function formatComplaintStatus(status) {
        const st = (status || "").toLowerCase();
        if (st === "submitted") return "✅ Submitted";
        if (st === "ready_to_submit") return "🚀 Ready to Submit";
        if (st === "exported") return "📑 Exported";
        if (st === "draft") return "📝 Draft";
        return "⚪ No Draft";
    }

    let citizenSearchDebounceTimer = null;

    async function loadCitizenDashboard() {
        const tableBody = document.getElementById("citizenReportsTableBody");
        const emptyState = document.getElementById("citizenEmptyReports");
        const noFilteredState = document.getElementById("citizenNoFilteredReports");
        const reportsTable = document.getElementById("citizenReportsTable");
        const totalReportsElem = document.getElementById("citizenTotalReports");
        const openReportsElem = document.getElementById("citizenOpenReports");
        const underReviewReportsElem = document.getElementById("citizenUnderReviewReports");
        const pendingReportsElem = document.getElementById("citizenPendingReports");
        const resolvedReportsElem = document.getElementById("citizenResolvedReports");
        const submittedComplaintsElem = document.getElementById("citizenSubmittedComplaints");
        const countBadge = document.getElementById("citizenReportsCountBadge");

        const searchInput = document.getElementById("citizenSearchInput");
        const categoryFilter = document.getElementById("citizenCategoryFilter");
        const statusFilter = document.getElementById("citizenStatusFilter");
        const complaintStatusFilter = document.getElementById("citizenComplaintStatusFilter");
        const dateFilter = document.getElementById("citizenDateFilter");
        const sortFilter = document.getElementById("citizenSortFilter");

        if (!currentUser || currentUser.role !== "citizen") return;

        if (tableBody) {
            tableBody.innerHTML = `<tr><td colspan="9" class="text-center" style="padding: 2rem; color: var(--text-muted);">Loading your submitted reports...</td></tr>`;
        }

        const searchVal = searchInput ? searchInput.value.trim() : "";
        const catVal = categoryFilter ? categoryFilter.value : "all";
        const stVal = statusFilter ? statusFilter.value : "all";
        const cstVal = complaintStatusFilter ? complaintStatusFilter.value : "all";
        const dateVal = dateFilter ? dateFilter.value.trim() : "";
        const sortVal = sortFilter ? sortFilter.value : "newest";

        const hasActiveFilters = Boolean(searchVal || (catVal && catVal !== "all") || (stVal && stVal !== "all") || (cstVal && cstVal !== "all") || dateVal);

        const params = new URLSearchParams();
        params.set("my_reports", "1");
        params.set("limit", "100");
        if (searchVal) params.set("q", searchVal);
        if (catVal && catVal !== "all") params.set("domain", catVal);
        if (stVal && stVal !== "all") params.set("status", stVal);
        if (cstVal && cstVal !== "all") params.set("complaint_status", cstVal);
        if (dateVal) params.set("date", dateVal);
        params.set("sort_by", sortVal);

        try {
            const res = await fetch(`/api/inspections?${params.toString()}`);
            const data = await res.json();
            if (!res.ok || data.status !== "success") {
                throw new Error(data.message || "Failed to load reports.");
            }

            const reports = data.inspections || [];

            // Update 5 Metric Summary Cards from backend citizen_summary when available
            if (data.citizen_summary) {
                const s = data.citizen_summary;
                if (totalReportsElem) totalReportsElem.textContent = String(s.total ?? 0);
                if (openReportsElem) openReportsElem.textContent = String(s.open ?? 0);
                if (underReviewReportsElem) underReviewReportsElem.textContent = String(s.under_review ?? 0);
                if (pendingReportsElem) pendingReportsElem.textContent = String((s.open ?? 0) + (s.under_review ?? 0));
                if (resolvedReportsElem) resolvedReportsElem.textContent = String(s.resolved ?? 0);
                if (submittedComplaintsElem) submittedComplaintsElem.textContent = String(s.submitted_complaints ?? 0);
            } else {
                let openCnt = 0;
                let underReviewCnt = 0;
                let resolvedCnt = 0;
                let submittedComplaintsCnt = 0;
                reports.forEach(r => {
                    const st = (r.status || "").toLowerCase();
                    if (st === "resolved") resolvedCnt++;
                    else if (st === "under review") underReviewCnt++;
                    else openCnt++;

                    if ((r.complaint_status || "").toLowerCase() === "submitted") {
                        submittedComplaintsCnt++;
                    }
                });
                if (totalReportsElem) totalReportsElem.textContent = String(reports.length);
                if (openReportsElem) openReportsElem.textContent = String(openCnt);
                if (underReviewReportsElem) underReviewReportsElem.textContent = String(underReviewCnt);
                if (pendingReportsElem) pendingReportsElem.textContent = String(openCnt + underReviewCnt);
                if (resolvedReportsElem) resolvedReportsElem.textContent = String(resolvedCnt);
                if (submittedComplaintsElem) submittedComplaintsElem.textContent = String(submittedComplaintsCnt);
            }

            if (countBadge) countBadge.textContent = String(reports.length);

            // Empty state handling
            if (reports.length === 0) {
                if (reportsTable) reportsTable.style.display = "none";
                if (hasActiveFilters) {
                    if (emptyState) emptyState.style.display = "none";
                    if (noFilteredState) noFilteredState.style.display = "block";
                } else {
                    if (emptyState) emptyState.style.display = "block";
                    if (noFilteredState) noFilteredState.style.display = "none";
                }
                return;
            }

            if (emptyState) emptyState.style.display = "none";
            if (noFilteredState) noFilteredState.style.display = "none";
            if (reportsTable) reportsTable.style.display = "table";

            if (tableBody) {
                tableBody.innerHTML = "";
                reports.forEach(r => {
                    const tr = document.createElement("tr");
                    tr.style.cursor = "pointer";
                    tr.title = "Click to inspect full findings, evidence, and complaint status";

                    const domain = (r.domain || r.inspection_type || (r.defect_type && (r.defect_type.includes("Crack") || r.defect_type.includes("Damp") || r.defect_type.includes("Paint") || r.defect_type.includes("Spalling")) ? "home" : "road")).toLowerCase();
                    const domainBadge = domain === "home"
                        ? `<span class="badge badge-home">🏠 Home</span>`
                        : `<span class="badge badge-road">🛣️ Road</span>`;
                    
                    const locSummary = [r.road_name, r.area, r.city].filter(Boolean).join(", ") || (r.latitude ? `${Number(r.latitude).toFixed(4)}, ${Number(r.longitude).toFixed(4)}` : "—");
                    const defectsSummary = r.defect_count > 0 ? `${r.defect_count} defect(s): ${escapeHtml(r.defect_type || "distress")}` : "0 defects detected";
                    const complaintBadge = `<span class="badge ${getComplaintBadgeClass(r.complaint_status)}">${formatComplaintStatus(r.complaint_status)}</span>`;

                    tr.innerHTML = `
                        <td><strong>#${r.id}</strong></td>
                        <td>
                            <img src="/api/inspections/${r.id}/image/annotated" alt="Thumbnail" class="table-thumb" style="width: 48px; height: 48px; object-fit: cover; border-radius: 4px; border: 1px solid var(--border-color);" onerror="this.src='/static/img/placeholder.png'; this.onerror=null;">
                        </td>
                        <td>${domainBadge}</td>
                        <td><div style="font-weight: 500;">${escapeHtml(defectsSummary)}</div></td>
                        <td><small>${escapeHtml(locSummary)}</small></td>
                        <td><span class="badge ${getStatusBadgeClass(r.status)}">${escapeHtml(r.status || "Open")}</span></td>
                        <td>${complaintBadge}</td>
                        <td style="font-size: 0.8rem; color: var(--text-secondary);">${formatDateTime(r.uploaded_at)}</td>
                        <td style="text-align: right; white-space: nowrap;">
                            <button type="button" class="btn btn-xs btn-outline-primary citizen-view-rec-btn" data-id="${r.id}" style="padding: 2px 8px; font-size: 0.78rem; margin-right: 4px;">🔍 View</button>
                            <button type="button" class="btn btn-xs btn-outline-secondary citizen-open-draft-btn" data-id="${r.id}" style="padding: 2px 8px; font-size: 0.78rem;">📝 Draft</button>
                        </td>
                    `;

                    // Row click navigates to report details (unless clicking an action button)
                    tr.addEventListener("click", (e) => {
                        if (!e.target.closest("button") && !e.target.closest("a")) {
                            openRecordDetail(r.id);
                        }
                    });

                    tableBody.appendChild(tr);
                });

                tableBody.querySelectorAll(".citizen-view-rec-btn").forEach(btn => {
                    btn.addEventListener("click", (e) => {
                        e.stopPropagation();
                        const id = btn.getAttribute("data-id");
                        if (id) openRecordDetail(id);
                    });
                });

                tableBody.querySelectorAll(".citizen-open-draft-btn").forEach(btn => {
                    btn.addEventListener("click", (e) => {
                        e.stopPropagation();
                        const id = btn.getAttribute("data-id");
                        if (id) openComplaintDraftModal(id);
                    });
                });
            }
        } catch (err) {
            console.error("Citizen dashboard load error:", err);
            if (tableBody) {
                tableBody.innerHTML = `<tr><td colspan="9" class="text-center text-danger" style="padding: 2rem;">Error loading reports: ${escapeHtml(err.message)}</td></tr>`;
            }
        }
    }

    function resetCitizenFilters() {
        const searchInput = document.getElementById("citizenSearchInput");
        const categoryFilter = document.getElementById("citizenCategoryFilter");
        const statusFilter = document.getElementById("citizenStatusFilter");
        const complaintStatusFilter = document.getElementById("citizenComplaintStatusFilter");
        const dateFilter = document.getElementById("citizenDateFilter");
        const sortFilter = document.getElementById("citizenSortFilter");

        if (searchInput) searchInput.value = "";
        if (categoryFilter) categoryFilter.value = "all";
        if (statusFilter) statusFilter.value = "all";
        if (complaintStatusFilter) complaintStatusFilter.value = "all";
        if (dateFilter) dateFilter.value = "";
        if (sortFilter) sortFilter.value = "newest";
        loadCitizenDashboard();
    }

    async function checkAuthStatus() {
        try {
            const res = await fetch("/api/auth/status");
            const data = await res.json();
            if (data.csrf_token) {
                currentCsrfToken = data.csrf_token;
            }
            currentUser = (data.status === "success" && data.authenticated) ? data.user : null;
            updateAuthUI(data);
        } catch (err) {
            console.error("Auth status check error:", err);
        }
    }

    function updateAuthUI(authData) {
        const isAuth = authData && authData.authenticated && authData.user;
        const requiresSetup = authData && authData.requires_setup;
        const guestBanner = document.getElementById("authGuestBanner");
        const tabDashboardLabel = document.getElementById("tabDashboardLabel");
        const tabNewInspectionLabel = document.getElementById("tabNewInspectionLabel");
        const tabRecordsLabel = document.getElementById("tabRecordsLabel");

        if (isAuth) {
            const u = authData.user;
            if (guestBanner) guestBanner.style.display = "none";
            if (authGuestControls) authGuestControls.style.display = "none";
            if (authUserControls) authUserControls.style.display = "flex";
            if (currentUserBadge) {
                currentUserBadge.innerHTML = `👤 <strong>${escapeHtml(u.username)}</strong> <span class="badge ${getRoleBadgeClass(u.role)}" style="font-size:0.75rem; margin-left:4px;">${escapeHtml(formatRole(u.role))}</span>`;
            }

            // Role-based navigation visibility & labels
            if (u.role === "citizen") {
                if (tabDashboardLabel) tabDashboardLabel.textContent = "My Portal";
                if (tabNewInspectionLabel) tabNewInspectionLabel.textContent = "Report Defect";
                if (tabRecordsLabel) tabRecordsLabel.textContent = "My Reports";

                if (tabUsersBtn) tabUsersBtn.style.display = "none";
                if (tabQueueBtn) tabQueueBtn.style.display = "none";
                if (tabReportsBtn) tabReportsBtn.style.display = "none";
                if (tabNewInspectionBtn) tabNewInspectionBtn.style.display = "inline-flex";
                if (tabRecordsBtn) tabRecordsBtn.style.display = "inline-flex";
                if (tabMapBtn) tabMapBtn.style.display = "inline-flex";

                const citizenGreeting = document.getElementById("citizenGreeting");
                if (citizenGreeting) {
                    citizenGreeting.textContent = `Welcome back, ${escapeHtml(u.username)}!`;
                }

                // If currently on forbidden admin view, redirect to dashboard
                const currentHash = (window.location.hash || "").toLowerCase().replace("#", "").trim();
                if (currentHash === "queue" || currentHash === "reports" || currentHash === "users") {
                    switchView("dashboard");
                }
            } else if (u.role === "admin") {
                if (tabDashboardLabel) tabDashboardLabel.textContent = "Dashboard";
                if (tabNewInspectionLabel) tabNewInspectionLabel.textContent = "New Inspection";
                if (tabRecordsLabel) tabRecordsLabel.textContent = "Records";

                if (tabUsersBtn) tabUsersBtn.style.display = "inline-flex";
                if (tabNewInspectionBtn) tabNewInspectionBtn.style.display = "inline-flex";
                if (tabReportsBtn) tabReportsBtn.style.display = "inline-flex";
                if (tabQueueBtn) tabQueueBtn.style.display = "inline-flex";
                if (queueSubtitle) queueSubtitle.textContent = "All dispatched infrastructure remediation tasks across the maintenance department.";
            } else if (u.role === "inspector") {
                if (tabDashboardLabel) tabDashboardLabel.textContent = "Dashboard";
                if (tabNewInspectionLabel) tabNewInspectionLabel.textContent = "New Inspection";
                if (tabRecordsLabel) tabRecordsLabel.textContent = "Records";

                if (tabUsersBtn) tabUsersBtn.style.display = "none";
                if (tabNewInspectionBtn) tabNewInspectionBtn.style.display = "inline-flex";
                if (tabReportsBtn) tabReportsBtn.style.display = "inline-flex";
                if (tabQueueBtn) tabQueueBtn.style.display = "none";
            } else if (u.role === "maintenance") {
                if (tabDashboardLabel) tabDashboardLabel.textContent = "Dashboard";
                if (tabNewInspectionLabel) tabNewInspectionLabel.textContent = "New Inspection";
                if (tabRecordsLabel) tabRecordsLabel.textContent = "Records";

                if (tabUsersBtn) tabUsersBtn.style.display = "none";
                if (tabNewInspectionBtn) tabNewInspectionBtn.style.display = "none";
                if (tabReportsBtn) tabReportsBtn.style.display = "none";
                if (tabQueueBtn) tabQueueBtn.style.display = "inline-flex";
                if (queueSubtitle) queueSubtitle.textContent = `Actionable infrastructure remediation tasks assigned to ${escapeHtml(u.username)}.`;

                // If currently on forbidden view, redirect to queue
                const currentHash = (window.location.hash || "").toLowerCase().replace("#", "").trim();
                if (currentHash === "new" || currentHash === "reports" || currentHash === "users") {
                    switchView("queue");
                }
            }
        } else {
            const tabDashboardLabel = document.getElementById("tabDashboardLabel");
            const tabNewInspectionLabel = document.getElementById("tabNewInspectionLabel");
            const tabRecordsLabel = document.getElementById("tabRecordsLabel");
            if (tabDashboardLabel) tabDashboardLabel.textContent = "Dashboard";
            if (tabNewInspectionLabel) tabNewInspectionLabel.textContent = "New Inspection";
            if (tabRecordsLabel) tabRecordsLabel.textContent = "Records";

            const guestBannerSignInBtn = document.getElementById("guestBannerSignInBtn");
            const guestBannerTitle = document.getElementById("authGuestBannerTitle");

            if (guestBanner) {
                guestBanner.style.display = "flex";
                const guestBannerMsg = document.getElementById("authGuestBannerMsg");
                if (guestBannerMsg) {
                    if (requiresSetup) {
                        guestBannerMsg.textContent = "First-time setup required: Create an administrator account to begin using VisionGuard AI.";
                    } else {
                        guestBannerMsg.textContent = "Sign in or register a citizen account to access AI inspection workflows, records database, GIS map, and reporting tools.";
                    }
                }
                if (guestBannerTitle) {
                    guestBannerTitle.textContent = requiresSetup
                        ? "First-Time Administrator Setup Required"
                        : "Authentication Required for Full System Access";
                }
                if (guestBannerSignInBtn) {
                    if (requiresSetup) {
                        guestBannerSignInBtn.innerHTML = "🚀 Setup Admin";
                        guestBannerSignInBtn.className = "btn btn-sm btn-warning guest-login-btn";
                    } else {
                        guestBannerSignInBtn.innerHTML = "🔐 Sign In";
                        guestBannerSignInBtn.className = "btn btn-sm btn-primary guest-login-btn";
                    }
                }
            }
            if (authUserControls) authUserControls.style.display = "none";
            if (authGuestControls) authGuestControls.style.display = "flex";
            if (tabUsersBtn) tabUsersBtn.style.display = "none";
            if (tabQueueBtn) tabQueueBtn.style.display = "none";
            if (tabReportsBtn) tabReportsBtn.style.display = "none";

            if (openAuthModalBtn) {
                if (requiresSetup) {
                    openAuthModalBtn.innerHTML = "🚀 Setup Admin";
                    openAuthModalBtn.className = "btn btn-sm btn-warning";
                } else {
                    openAuthModalBtn.innerHTML = "🔐 Sign In / Register";
                    openAuthModalBtn.className = "btn btn-sm btn-primary";
                }
            }
        }
    }

    // Global delegated click listener for all auth modal triggers and modal closers
    document.addEventListener("click", (e) => {
        // Tab switching in Auth Modal (Sign In vs Register)
        const tabTrigger = e.target.closest("#authTabLoginBtn, #authTabRegisterBtn");
        if (tabTrigger) {
            e.preventDefault();
            const mode = tabTrigger.id === "authTabRegisterBtn" ? "register" : "login";
            setAuthModalMode(mode);
            return;
        }

        // Any button that triggers authentication / setup modal
        const authTrigger = e.target.closest("#openAuthModalBtn, #guestBannerSignInBtn, .guest-login-btn, [data-action='open-auth']");
        if (authTrigger) {
            e.preventDefault();
            const preferredMode = authTrigger.getAttribute("data-auth-mode") || null;
            openAuthModal(preferredMode);
            return;
        }

        // Close triggers (✕ button, Cancel button, or elements with .modal-close-btn inside authModal)
        const closeTrigger = e.target.closest("#closeAuthModalBtn, #cancelAuthBtn, #cancelRegisterBtn");
        if (closeTrigger) {
            e.preventDefault();
            closeAuthModal();
            return;
        }

        // Close on backdrop click (clicking outside the modal dialog)
        const modal = document.getElementById("authModal");
        if (modal && e.target === modal) {
            closeAuthModal();
            return;
        }
    });

    document.addEventListener("keydown", (e) => {
        const modal = document.getElementById("authModal");
        if (e.key === "Escape" && modal && modal.style.display === "flex") {
            closeAuthModal();
        }
    });

    if (loginForm) {
        loginForm.addEventListener("submit", async (e) => {
            e.preventDefault();
            if (authErrorAlert) authErrorAlert.style.display = "none";

            const username = loginUsername ? loginUsername.value.trim() : "";
            const password = loginPassword ? loginPassword.value : "";
            if (!username || !password) return;

            const submitBtn = document.getElementById("loginSubmitBtn");
            if (submitBtn) {
                submitBtn.disabled = true;
                submitBtn.textContent = "Signing in...";
            }

            try {
                const res = await fetch("/api/auth/login", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ username, password })
                });
                const data = await res.json();

                if (!res.ok || data.status !== "success") {
                    throw new Error(data.message || "Invalid credentials.");
                }

                if (data.csrf_token) currentCsrfToken = data.csrf_token;
                currentUser = data.user;
                if (authModal) authModal.style.display = "none";
                await checkAuthStatus();

                if (currentUser && currentUser.role === "citizen") {
                    switchView("dashboard");
                    loadCitizenDashboard();
                    return;
                }

                loadDashboardStats();
                loadRecordsHeaderCount();

                // If user is maintenance staff and on forbidden view, redirect to queue
                if (currentUser && currentUser.role === "maintenance") {
                    const hash = (window.location.hash || "").replace("#", "");
                    if (hash === "new" || hash === "reports" || hash === "users") {
                        switchView("queue");
                        return;
                    }
                }

                if (window.location.hash) {
                    checkHashRoute();
                } else {
                    switchView("dashboard");
                }
            } catch (err) {
                if (authErrorAlert) {
                    authErrorAlert.textContent = err.message || "Authentication failed.";
                    authErrorAlert.style.display = "block";
                }
            } finally {
                if (submitBtn) {
                    submitBtn.disabled = false;
                    submitBtn.textContent = "Sign In";
                }
            }
        });
    }

    // Citizen Registration Form Handler
    const registerForm = document.getElementById("registerForm");
    if (registerForm) {
        registerForm.addEventListener("submit", async (e) => {
            e.preventDefault();
            const authErrorAlert = document.getElementById("authErrorAlert");
            if (authErrorAlert) authErrorAlert.style.display = "none";

            const registerUser = document.getElementById("registerUsername");
            const registerEmail = document.getElementById("registerEmail");
            const registerPass = document.getElementById("registerPassword");
            const registerPassConfirm = document.getElementById("registerPasswordConfirm");

            const username = registerUser ? registerUser.value.trim() : "";
            const email = registerEmail ? registerEmail.value.trim() : "";
            const password = registerPass ? registerPass.value : "";
            const passwordConfirm = registerPassConfirm ? registerPassConfirm.value : "";

            if (!username || !password) return;
            if (password.length < 8) {
                if (authErrorAlert) {
                    authErrorAlert.textContent = "Password must be at least 8 characters long.";
                    authErrorAlert.style.display = "block";
                }
                return;
            }
            if (password !== passwordConfirm) {
                if (authErrorAlert) {
                    authErrorAlert.textContent = "Passwords do not match. Please verify both entries.";
                    authErrorAlert.style.display = "block";
                }
                return;
            }

            const submitBtn = document.getElementById("registerSubmitBtn");
            if (submitBtn) {
                submitBtn.disabled = true;
                submitBtn.textContent = "Creating Account...";
            }

            try {
                const res = await fetch("/api/auth/register", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ username, email, password })
                });
                const data = await res.json();

                if (!res.ok || data.status !== "success") {
                    throw new Error(data.message || "Registration failed.");
                }

                if (data.csrf_token) currentCsrfToken = data.csrf_token;
                currentUser = data.user;
                closeAuthModal();
                await checkAuthStatus();
                switchView("dashboard");
                loadCitizenDashboard();
            } catch (err) {
                if (authErrorAlert) {
                    authErrorAlert.textContent = err.message || "Registration failed.";
                    authErrorAlert.style.display = "block";
                }
            } finally {
                if (submitBtn) {
                    submitBtn.disabled = false;
                    submitBtn.textContent = "Create Citizen Account & Sign In";
                }
            }
        });
    }

    if (setupAdminForm) {
        setupAdminForm.addEventListener("submit", async (e) => {
            e.preventDefault();
            if (authErrorAlert) authErrorAlert.style.display = "none";

            const username = setupAdminUsername ? setupAdminUsername.value.trim() : "";
            const email = setupAdminEmail ? setupAdminEmail.value.trim() : "";
            const password = setupAdminPassword ? setupAdminPassword.value : "";
            if (!username || !password) return;

            const submitBtn = document.getElementById("setupAdminSubmitBtn");
            if (submitBtn) {
                submitBtn.disabled = true;
                submitBtn.textContent = "Configuring Admin...";
            }

            try {
                const res = await fetch("/api/auth/setup-admin", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ username, email, password })
                });
                const data = await res.json();

                if (!res.ok || data.status !== "success") {
                    throw new Error(data.message || "Failed to configure administrator.");
                }

                if (data.csrf_token) currentCsrfToken = data.csrf_token;
                currentUser = data.user;
                if (authModal) authModal.style.display = "none";
                await checkAuthStatus();
                loadDashboardStats();
                loadRecordsHeaderCount();
                switchView("dashboard");
            } catch (err) {
                if (authErrorAlert) {
                    authErrorAlert.textContent = err.message || "Admin setup failed.";
                    authErrorAlert.style.display = "block";
                }
            } finally {
                if (submitBtn) {
                    submitBtn.disabled = false;
                    submitBtn.textContent = "Create Administrator Account";
                }
            }
        });
    }

    if (logoutBtn) {
        logoutBtn.addEventListener("click", async () => {
            try {
                const res = await fetch("/api/auth/logout", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" }
                });
                if (res.ok) {
                    const data = await res.json().catch(() => null);
                    if (data && data.csrf_token) {
                        currentCsrfToken = data.csrf_token;
                    }
                }
            } catch (err) {
                console.error("Logout request error:", err);
            }
            currentUser = null;
            await checkAuthStatus();
            renderGuestDashboard();
            switchView("dashboard");
        });
    }

    // Citizen & Landing Action Buttons
    const landingReportBtn = document.getElementById("landingReportBtn");
    const landingExploreMapBtn = document.getElementById("landingExploreMapBtn");
    const landingRoadCardBtn = document.getElementById("landingRoadCardBtn");
    const landingHomeCardBtn = document.getElementById("landingHomeCardBtn");
    const citizenStartRoadReportBtn = document.getElementById("citizenStartRoadReportBtn");
    const citizenStartHomeReportBtn = document.getElementById("citizenStartHomeReportBtn");
    const citizenExploreMapBtn = document.getElementById("citizenExploreMapBtn");
    const citizenViewAllRecordsBtn = document.getElementById("citizenViewAllRecordsBtn");
    const refreshCitizenDashBtn = document.getElementById("refreshCitizenDashBtn");

    if (landingReportBtn) {
        landingReportBtn.addEventListener("click", () => {
            if (!currentUser) {
                openAuthModal();
            } else {
                switchView("new");
            }
        });
    }

    if (landingRoadCardBtn) {
        landingRoadCardBtn.addEventListener("click", () => {
            setInspectionDomain("road");
            if (!currentUser) {
                openAuthModal();
            } else {
                switchView("new");
            }
        });
    }

    if (landingHomeCardBtn) {
        landingHomeCardBtn.addEventListener("click", () => {
            setInspectionDomain("home");
            if (!currentUser) {
                openAuthModal();
            } else {
                switchView("new");
            }
        });
    }

    if (landingExploreMapBtn) {
        landingExploreMapBtn.addEventListener("click", () => {
            switchView("map");
        });
    }

    if (citizenStartRoadReportBtn) {
        citizenStartRoadReportBtn.addEventListener("click", () => {
            clearLocationInputs();
            setInspectionDomain("road");
            switchView("new");
        });
    }

    if (citizenStartHomeReportBtn) {
        citizenStartHomeReportBtn.addEventListener("click", () => {
            clearLocationInputs();
            setInspectionDomain("home");
            switchView("new");
        });
    }

    if (citizenExploreMapBtn) {
        citizenExploreMapBtn.addEventListener("click", () => {
            switchView("map");
        });
    }

    if (citizenViewAllRecordsBtn) {
        citizenViewAllRecordsBtn.addEventListener("click", () => {
            switchView("records");
        });
    }

    if (refreshCitizenDashBtn) {
        refreshCitizenDashBtn.addEventListener("click", loadCitizenDashboard);
    }

    const citizenSearchInput = document.getElementById("citizenSearchInput");
    const citizenCategoryFilter = document.getElementById("citizenCategoryFilter");
    const citizenStatusFilter = document.getElementById("citizenStatusFilter");
    const citizenComplaintStatusFilter = document.getElementById("citizenComplaintStatusFilter");
    const citizenDateFilter = document.getElementById("citizenDateFilter");
    const citizenSortFilter = document.getElementById("citizenSortFilter");
    const citizenResetFiltersBtn = document.getElementById("citizenResetFiltersBtn");
    const citizenClearFiltersInlineBtn = document.getElementById("citizenClearFiltersInlineBtn");

    if (citizenSearchInput) {
        citizenSearchInput.addEventListener("input", () => {
            clearTimeout(citizenSearchDebounceTimer);
            citizenSearchDebounceTimer = setTimeout(() => {
                loadCitizenDashboard();
            }, 300);
        });
    }

    if (citizenCategoryFilter) {
        citizenCategoryFilter.addEventListener("change", loadCitizenDashboard);
    }
    if (citizenStatusFilter) {
        citizenStatusFilter.addEventListener("change", loadCitizenDashboard);
    }
    if (citizenComplaintStatusFilter) {
        citizenComplaintStatusFilter.addEventListener("change", loadCitizenDashboard);
    }
    if (citizenDateFilter) {
        citizenDateFilter.addEventListener("change", loadCitizenDashboard);
    }
    if (citizenSortFilter) {
        citizenSortFilter.addEventListener("change", loadCitizenDashboard);
    }
    if (citizenResetFiltersBtn) {
        citizenResetFiltersBtn.addEventListener("click", resetCitizenFilters);
    }
    if (citizenClearFiltersInlineBtn) {
        citizenClearFiltersInlineBtn.addEventListener("click", resetCitizenFilters);
    }

    // User Management Functions (Admin Only)
    async function loadUsers() {
        if (!usersTableBody) return;
        if (!currentUser || currentUser.role !== "admin") {
            usersTableBody.innerHTML = `<tr><td colspan="7" class="text-center text-danger" style="padding: 2rem;">🔒 Access Restricted: Administrator privileges required to view user directory.</td></tr>`;
            return;
        }
        usersTableBody.innerHTML = `<tr><td colspan="7" class="text-center" style="padding: 2rem;">Loading authorized users...</td></tr>`;

        try {
            const res = await fetch("/api/users");
            const data = await res.json();

            if (!res.ok || data.status !== "success") {
                if (res.status === 401 || res.status === 403) {
                    usersTableBody.innerHTML = `<tr><td colspan="7" class="text-center text-danger" style="padding: 2rem;">🔒 Access Restricted: Administrator privileges required to view user directory.</td></tr>`;
                    return;
                }
                throw new Error(data.message || "Failed to load user directory.");
            }

            const users = data.users || [];
            if (users.length === 0) {
                usersTableBody.innerHTML = `<tr><td colspan="7" class="text-center" style="padding: 2rem;">No user accounts found.</td></tr>`;
                return;
            }

            usersTableBody.innerHTML = "";
            users.forEach(u => {
                const tr = document.createElement("tr");
                const isSelf = currentUser && currentUser.id === u.id;
                const selfBadge = isSelf ? ` <span class="badge badge-info" style="font-size:0.7rem; padding: 2px 5px;">You</span>` : "";

                const statusBadge = u.is_active
                    ? `<span class="badge badge-status-active">Active</span>`
                    : `<span class="badge badge-status-inactive">Inactive</span>`;

                const roleOptions = [
                    { value: "admin", label: "Administrator" },
                    { value: "inspector", label: "Inspector" },
                    { value: "maintenance", label: "Maintenance Staff" }
                ].map(opt => `<option value="${opt.value}" ${u.role === opt.value ? 'selected' : ''}>${opt.label}</option>`).join("");

                const roleSelectHtml = `
                    <select class="form-control role-change-select" data-user-id="${u.id}" ${isSelf ? 'disabled title="Cannot change your own role"' : ''} style="font-size: 0.85rem; padding: 0.25rem 0.5rem;">
                        ${roleOptions}
                    </select>
                `;

                const toggleBtnHtml = u.is_active
                    ? `<button type="button" class="btn btn-sm btn-outline-danger toggle-status-btn" data-user-id="${u.id}" data-active="0" ${isSelf ? 'disabled title="Cannot deactivate your own account"' : ''}>Deactivate</button>`
                    : `<button type="button" class="btn btn-sm btn-outline-success toggle-status-btn" data-user-id="${u.id}" data-active="1">Activate</button>`;

                tr.innerHTML = `
                    <td><strong>#${u.id}</strong></td>
                    <td><strong>${escapeHtml(u.username)}</strong>${selfBadge}</td>
                    <td>${escapeHtml(u.email || "—")}</td>
                    <td>${roleSelectHtml}</td>
                    <td>${statusBadge}</td>
                    <td style="font-size: 0.8rem; color: var(--text-secondary);">${formatDateTime(u.last_login_at)}</td>
                    <td style="text-align: right;">${toggleBtnHtml}</td>
                `;
                usersTableBody.appendChild(tr);
            });

            // Bind role change selects
            usersTableBody.querySelectorAll(".role-change-select").forEach(sel => {
                sel.addEventListener("change", async (e) => {
                    const userId = e.target.getAttribute("data-user-id");
                    const newRole = e.target.value;
                    try {
                        const patchRes = await fetch(`/api/users/${userId}`, {
                            method: "PATCH",
                            headers: { "Content-Type": "application/json" },
                            body: JSON.stringify({ role: newRole })
                        });
                        const patchData = await patchRes.json();
                        if (!patchRes.ok || patchData.status !== "success") {
                            throw new Error(patchData.message || "Failed to update role.");
                        }
                        loadUsers();
                    } catch (err) {
                        alert(`Role update error: ${err.message}`);
                        loadUsers();
                    }
                });
            });

            // Bind toggle status buttons
            usersTableBody.querySelectorAll(".toggle-status-btn").forEach(btn => {
                btn.addEventListener("click", async () => {
                    const userId = btn.getAttribute("data-user-id");
                    const targetActive = parseInt(btn.getAttribute("data-active"), 10) === 1;
                    const actionLabel = targetActive ? "activate" : "deactivate";

                    if (!confirm(`Are you sure you want to ${actionLabel} user #${userId}?`)) {
                        return;
                    }

                    try {
                        const patchRes = await fetch(`/api/users/${userId}`, {
                            method: "PATCH",
                            headers: { "Content-Type": "application/json" },
                            body: JSON.stringify({ is_active: targetActive ? 1 : 0 })
                        });
                        const patchData = await patchRes.json();
                        if (!patchRes.ok || patchData.status !== "success") {
                            throw new Error(patchData.message || `Failed to ${actionLabel} user.`);
                        }
                        loadUsers();
                    } catch (err) {
                        alert(`Account status update error: ${err.message}`);
                        loadUsers();
                    }
                });
            });
        } catch (err) {
            console.error("Load users error:", err);
            usersTableBody.innerHTML = `<tr><td colspan="7" class="text-center text-danger" style="padding: 2rem;">Error loading users: ${escapeHtml(err.message)}</td></tr>`;
        }
    }

    if (refreshUsersBtn) {
        refreshUsersBtn.addEventListener("click", loadUsers);
    }

    if (createUserModalBtn) {
        createUserModalBtn.addEventListener("click", () => {
            if (createUserErrorAlert) {
                createUserErrorAlert.style.display = "none";
                createUserErrorAlert.textContent = "";
            }
            if (createUserForm) createUserForm.reset();
            if (createUserModal) createUserModal.style.display = "flex";
        });
    }

    if (closeCreateUserModalBtn) {
        closeCreateUserModalBtn.addEventListener("click", () => {
            if (createUserModal) createUserModal.style.display = "none";
        });
    }
    if (cancelCreateUserBtn) {
        cancelCreateUserBtn.addEventListener("click", () => {
            if (createUserModal) createUserModal.style.display = "none";
        });
    }

    if (createUserForm) {
        createUserForm.addEventListener("submit", async (e) => {
            e.preventDefault();
            if (createUserErrorAlert) createUserErrorAlert.style.display = "none";

            const username = newUsername ? newUsername.value.trim() : "";
            const email = newUserEmail ? newUserEmail.value.trim() : "";
            const role = newUserRole ? newUserRole.value : "inspector";
            const password = newUserPassword ? newUserPassword.value : "";
            const is_active = newUserActive ? newUserActive.checked : true;

            if (!username || !password) return;

            const saveBtn = document.getElementById("saveCreateUserBtn");
            if (saveBtn) {
                saveBtn.disabled = true;
                saveBtn.textContent = "Creating...";
            }

            try {
                const res = await fetch("/api/users", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ username, email, role, password, is_active })
                });
                const data = await res.json();

                if (!res.ok || data.status !== "success") {
                    throw new Error(data.message || "Failed to create user.");
                }

                if (createUserModal) createUserModal.style.display = "none";
                loadUsers();
            } catch (err) {
                if (createUserErrorAlert) {
                    createUserErrorAlert.textContent = err.message || "Failed to create user.";
                    createUserErrorAlert.style.display = "block";
                }
            } finally {
                if (saveBtn) {
                    saveBtn.disabled = false;
                    saveBtn.textContent = "Create Account";
                }
            }
        });
    }

    // -------------------------------------------------------------------------
    // Phase 4.7: Assignment Helpers, Staff Loader, Task Modal & Work Queue
    // -------------------------------------------------------------------------

    function getAssignmentBadgeClass(status) {
        switch (String(status || "").toLowerCase()) {
            case "assigned": return "badge badge-assign-assigned";
            case "in_progress": return "badge badge-assign-in-progress";
            case "completed": return "badge badge-assign-completed";
            case "cancelled": return "badge badge-assign-cancelled";
            default: return "badge badge-assign-unassigned";
        }
    }

    function formatAssignmentStatus(status) {
        switch (String(status || "").toLowerCase()) {
            case "assigned": return "Assigned";
            case "in_progress": return "In Progress";
            case "completed": return "Completed";
            case "cancelled": return "Cancelled";
            default: return "Unassigned";
        }
    }

    function renderAssignmentHistory(assignments) {
        if (!detailAssignmentHistoryList) return;
        detailAssignmentHistoryList.innerHTML = "";
        const list = Array.isArray(assignments) ? assignments : [];
        if (detailAssignmentEventsCountBadge) {
            detailAssignmentEventsCountBadge.textContent = `${list.length} Event${list.length === 1 ? '' : 's'}`;
        }
        if (list.length === 0) {
            detailAssignmentHistoryList.innerHTML = `<p class="text-muted" style="font-size: 0.8rem; margin: 0;">No assignment activity logged yet.</p>`;
            return;
        }

        list.forEach(a => {
            const div = document.createElement("div");
            div.className = "assignment-history-item";
            const stBadge = `<span class="${getAssignmentBadgeClass(a.assignment_status)}" style="font-size:0.7rem; padding: 2px 6px;">${escapeHtml(formatAssignmentStatus(a.assignment_status))}</span>`;
            const tech = a.assigned_to_username ? `<strong>${escapeHtml(a.assigned_to_username)}</strong>` : "<em>Unassigned</em>";
            const byUser = a.assigned_by_username ? `by <strong>${escapeHtml(a.assigned_by_username)}</strong>` : "";
            const instr = a.instructions ? `<div style="font-size:0.75rem; color:var(--text-secondary); margin-top:2px;">"${escapeHtml(a.instructions)}"</div>` : "";

            div.innerHTML = `
                <div>
                    <div>Assigned to ${tech} ${byUser} — ${stBadge}</div>
                    ${instr}
                </div>
                <div class="ah-meta">${formatDateTime(a.created_at || a.assigned_at)}</div>
            `;
            detailAssignmentHistoryList.appendChild(div);
        });
    }

    async function loadMaintenanceStaffOptions(selectedUserId = null) {
        if (!assigneeSelect) return;
        assigneeSelect.innerHTML = `<option value="">Loading maintenance personnel...</option>`;
        try {
            const res = await fetch("/api/maintenance/staff");
            const data = await res.json();
            if (!res.ok || data.status !== "success") {
                throw new Error(data.message || "Failed to load maintenance staff.");
            }
            const staff = data.staff || [];
            if (staff.length === 0) {
                assigneeSelect.innerHTML = `<option value="">No active Maintenance Staff accounts available</option>`;
                return;
            }
            assigneeSelect.innerHTML = `<option value="">Select Maintenance Technician...</option>` +
                staff.map(s => {
                    const sel = (selectedUserId && parseInt(selectedUserId, 10) === s.id) ? "selected" : "";
                    const emailTxt = s.email ? ` (${s.email})` : "";
                    return `<option value="${s.id}" ${sel}>${escapeHtml(s.username)}${escapeHtml(emailTxt)}</option>`;
                }).join("");
        } catch (err) {
            console.error("Load staff error:", err);
            assigneeSelect.innerHTML = `<option value="">Error loading staff: ${escapeHtml(err.message)}</option>`;
        }
    }

    if (openAssignTaskModalBtn) {
        openAssignTaskModalBtn.addEventListener("click", async () => {
            if (!currentDetailId) return;
            if (assignTaskErrorAlert) {
                assignTaskErrorAlert.style.display = "none";
                assignTaskErrorAlert.textContent = "";
            }
            if (assignTaskInspectionId) assignTaskInspectionId.value = currentDetailId;
            if (assignInstructionsInput) {
                assignInstructionsInput.value = (detailAssignmentInstructionsDisplay && detailAssignmentInstructionsDisplay.textContent !== "No special instructions provided.") 
                    ? detailAssignmentInstructionsDisplay.textContent 
                    : "";
            }
            await loadMaintenanceStaffOptions();
            if (assignTaskModal) assignTaskModal.style.display = "flex";
        });
    }

    if (closeAssignTaskModalBtn) {
        closeAssignTaskModalBtn.addEventListener("click", () => {
            if (assignTaskModal) assignTaskModal.style.display = "none";
        });
    }
    if (cancelAssignTaskModalBtn) {
        cancelAssignTaskModalBtn.addEventListener("click", () => {
            if (assignTaskModal) assignTaskModal.style.display = "none";
        });
    }

    if (assignTaskForm) {
        assignTaskForm.addEventListener("submit", async (e) => {
            e.preventDefault();
            if (assignTaskErrorAlert) assignTaskErrorAlert.style.display = "none";

            const inspId = assignTaskInspectionId ? assignTaskInspectionId.value : currentDetailId;
            const staffId = assigneeSelect ? assigneeSelect.value : "";
            const instructions = assignInstructionsInput ? assignInstructionsInput.value.trim() : "";

            if (!inspId || !staffId) return;

            if (saveAssignTaskBtn) {
                saveAssignTaskBtn.disabled = true;
                saveAssignTaskBtn.textContent = "Assigning...";
            }

            try {
                const res = await fetch(`/api/inspections/${inspId}/assign`, {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({
                        assigned_to_user_id: parseInt(staffId, 10),
                        instructions: instructions
                    })
                });
                const data = await res.json();
                if (!res.ok || data.status !== "success") {
                    throw new Error(data.message || "Failed to assign task.");
                }

                if (assignTaskModal) assignTaskModal.style.display = "none";
                await openRecordDetail(inspId);
                loadMaintenanceQueue();
            } catch (err) {
                if (assignTaskErrorAlert) {
                    assignTaskErrorAlert.textContent = err.message || "Assignment failed.";
                    assignTaskErrorAlert.style.display = "block";
                }
            } finally {
                if (saveAssignTaskBtn) {
                    saveAssignTaskBtn.disabled = false;
                    saveAssignTaskBtn.textContent = "Save Assignment";
                }
            }
        });
    }

    if (cancelAssignmentBtn) {
        cancelAssignmentBtn.addEventListener("click", async () => {
            if (!currentDetailId) return;
            if (!confirm(`Are you sure you want to cancel the maintenance assignment for Inspection Record #${currentDetailId}?`)) {
                return;
            }

            try {
                const res = await fetch(`/api/inspections/${currentDetailId}/cancel-assignment`, {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ reason: "Cancelled by administrator via record detail" })
                });
                const data = await res.json();
                if (!res.ok || data.status !== "success") {
                    throw new Error(data.message || "Failed to cancel assignment.");
                }
                await openRecordDetail(currentDetailId);
                loadMaintenanceQueue();
            } catch (err) {
                alert(`Error cancelling assignment: ${err.message}`);
            }
        });
    }

    // Maintenance Work Queue Loader (Phase 4.7 & Phase 5)
    async function loadQueueStaffFilterOptions() {
        if (!queueAssigneeFilter || !currentUser || currentUser.role !== "admin") return;
        if (queueAssigneeFilter.options.length > 2) return;
        try {
            const res = await fetch("/api/maintenance/staff");
            const data = await res.json();
            if (!res.ok || data.status !== "success") return;
            const staff = data.staff || [];
            let html = '<option value="">All Staff</option><option value="unassigned">Unassigned Only</option>';
            staff.forEach(s => {
                const display = s.full_name ? `${s.username} (${s.full_name})` : s.username;
                html += `<option value="${s.id}">${escapeHtml(display)}</option>`;
            });
            queueAssigneeFilter.innerHTML = html;
        } catch (_) {}
    }

    async function loadMaintenanceQueue() {
        if (!queueTableBody) return;
        if (!currentUser) {
            if (queueEmptyState) queueEmptyState.style.display = "none";
            if (queueErrorState) queueErrorState.style.display = "none";
            if (queueTable) queueTable.style.display = "table";
            queueTableBody.innerHTML = `<tr><td colspan="9" class="text-center" style="padding: 2.5rem; color: var(--text-muted);">
                🔒 Authentication Required. Please <button class="btn btn-sm btn-primary guest-login-btn" style="margin-left: 0.5rem;">Sign In</button> to view maintenance tasks.
            </td></tr>`;
            bindGuestLoginButtons();
            return;
        }

        if (queueErrorState) queueErrorState.style.display = "none";

        // Show/hide admin-specific assignee filter
        if (currentUser.role === "admin") {
            if (queueAssigneeFilterWrap) queueAssigneeFilterWrap.style.display = "flex";
            loadQueueStaffFilterOptions();
        } else {
            if (queueAssigneeFilterWrap) queueAssigneeFilterWrap.style.display = "none";
        }

        queueTableBody.innerHTML = `<tr><td colspan="9" class="text-center" style="padding: 2rem; color: var(--text-muted);">Loading maintenance tasks...</td></tr>`;

        const status = queueStatusFilter ? queueStatusFilter.value : "";
        const urgency = queueUrgencyFilter ? queueUrgencyFilter.value : "";
        const category = queueCategoryFilter ? queueCategoryFilter.value : "";
        const domain = queueDomainFilter ? queueDomainFilter.value : "";
        const sortBy = queueSortFilter ? queueSortFilter.value : "newest";
        const assignee = (queueAssigneeFilter && currentUser.role === "admin") ? queueAssigneeFilter.value : "";
        const q = queueSearchInput ? queueSearchInput.value.trim() : "";

        try {
            const params = new URLSearchParams();
            if (status) params.append("status", status);
            if (urgency) params.append("urgency", urgency);
            if (category) params.append("category", category);
            if (domain) params.append("domain", domain);
            if (sortBy) params.append("sort_by", sortBy);
            if (q) params.append("q", q);

            if (assignee === "unassigned") {
                params.append("assignment_status", "unassigned");
            } else if (assignee) {
                params.append("assigned_to_user_id", assignee);
            }

            if (currentUser.role === "admin" && !assignee) {
                params.append("include_unassigned", "1");
            }

            const res = await fetch(`/api/maintenance/queue?${params.toString()}`);
            const data = await res.json();

            if (!res.ok || data.status !== "success") {
                if (res.status === 401 || res.status === 403) {
                    if (queueEmptyState) queueEmptyState.style.display = "none";
                    if (queueErrorState) queueErrorState.style.display = "none";
                    if (queueTable) queueTable.style.display = "table";
                    queueTableBody.innerHTML = `<tr><td colspan="9" class="text-center text-danger" style="padding: 2rem;">🔒 Access Restricted: Login as Maintenance Staff or Administrator to view tasks.</td></tr>`;
                    return;
                }
                throw new Error(data.message || "Failed to load maintenance work queue.");
            }

            const tasks = data.tasks || [];
            const counts = data.counts || {};

            // Update telemetry
            if (queueTotalCount) queueTotalCount.textContent = counts.total || tasks.length;
            if (queuePendingCount) queuePendingCount.textContent = (counts.assigned || 0) + (counts.in_progress || 0);
            if (queueOverdueCount) queueOverdueCount.textContent = counts.overdue || 0;
            if (queueCompletedCount) queueCompletedCount.textContent = counts.completed || 0;

            if (queueCountBadgeHeader) {
                const pending = (counts.assigned || 0) + (counts.in_progress || 0);
                queueCountBadgeHeader.textContent = pending;
                queueCountBadgeHeader.className = pending > 0 ? "badge badge-warning" : "badge badge-secondary";
            }

            if (tasks.length === 0) {
                if (queueEmptyState) queueEmptyState.style.display = "block";
                if (queueTable) queueTable.style.display = "none";
                if (queueErrorState) queueErrorState.style.display = "none";
                return;
            }

            if (queueEmptyState) queueEmptyState.style.display = "none";
            if (queueErrorState) queueErrorState.style.display = "none";
            if (queueTable) queueTable.style.display = "table";

            queueTableBody.innerHTML = "";
            tasks.forEach(t => {
                const tr = document.createElement("tr");

                // Category Badge (Home vs Road)
                const isHome = (t.inspection_type || "").toLowerCase() === "home";
                const catBadge = isHome
                    ? '<span class="badge badge-info" style="font-size:0.75rem; padding: 2px 6px;">🏡 Home</span>'
                    : '<span class="badge badge-primary" style="font-size:0.75rem; padding: 2px 6px;">🛣️ Road</span>';

                // Assignee
                let techDisplay = t.assigned_to_username ? `<strong>${escapeHtml(t.assigned_to_username)}</strong>` : '<span class="text-muted"><em>Unassigned</em></span>';
                if (t.assigned_to_user_active === false) {
                    techDisplay += ` <span class="badge badge-warning" style="font-size:0.68rem; padding: 1px 4px;">Deactivated</span>`;
                }

                // Road / Location
                const roadName = t.road_name ? `<strong>${escapeHtml(t.road_name)}</strong>` : (isHome ? "<em>Residential Property</em>" : "<em>Unspecified Road</em>");
                const subLoc = [t.area, t.city].filter(Boolean).map(escapeHtml).join(", ");
                const locHtml = subLoc ? `${roadName}<br/><small style="color:var(--text-muted);">${subLoc}</small>` : roadName;

                // Defects
                const defectCount = t.defect_count > 0 
                    ? `<strong class="text-danger">${t.defect_count}</strong> (${escapeHtml(t.defect_type || "Defect")})`
                    : `<span class="text-success">0 (Sound)</span>`;
                const conf = (t.defect_count > 0 && t.confidence) ? ` <small class="text-muted">${(t.confidence * 100).toFixed(0)}%</small>` : "";

                // Creation Date
                const createdDate = t.uploaded_at ? escapeHtml(t.uploaded_at.split("T")[0]) : "—";

                // Target Date & Urgency
                const targetDate = t.target_repair_date || "Not Scheduled";
                const urgBadge = getDeadlineBadge(t);
                const targetHtml = `<div>${escapeHtml(targetDate)}</div><div style="margin-top:2px;">${urgBadge}</div>`;

                // Workflow status badge
                const wfBadge = `<span class="${getStatusBadgeClass(t.status)}" style="font-size:0.75rem; padding:2px 6px;">${escapeHtml(t.status)}</span>`;

                tr.innerHTML = `
                    <td><strong>#${t.id}</strong></td>
                    <td>${catBadge}</td>
                    <td>${defectCount}${conf}</td>
                    <td>${locHtml}</td>
                    <td><small style="color:var(--text-muted);">${createdDate}</small></td>
                    <td>${targetHtml}</td>
                    <td>${wfBadge}</td>
                    <td>${techDisplay}</td>
                    <td style="text-align: right;">
                        <button type="button" class="btn btn-primary btn-sm open-queue-task-btn" data-id="${t.id}">
                            👁️ Open Task
                        </button>
                    </td>
                `;
                queueTableBody.appendChild(tr);
            });

            // Bind clicks
            queueTableBody.querySelectorAll(".open-queue-task-btn").forEach(btn => {
                btn.addEventListener("click", () => {
                    const id = btn.getAttribute("data-id");
                    openRecordDetail(id);
                });
            });
        } catch (err) {
            console.error("Load queue error:", err);
            if (queueErrorState) {
                if (queueErrorText) queueErrorText.textContent = err.message || "Failed to load maintenance work queue.";
                queueErrorState.style.display = "block";
            }
            if (queueTable) queueTable.style.display = "none";
            if (queueEmptyState) queueEmptyState.style.display = "none";
        }
    }

    function resetAllQueueFilters() {
        if (queueStatusFilter) queueStatusFilter.value = "";
        if (queueUrgencyFilter) queueUrgencyFilter.value = "";
        if (queueCategoryFilter) queueCategoryFilter.value = "";
        if (queueDomainFilter) queueDomainFilter.value = "";
        if (queueSortFilter) queueSortFilter.value = "newest";
        if (queueAssigneeFilter) queueAssigneeFilter.value = "";
        if (queueSearchInput) queueSearchInput.value = "";
        loadMaintenanceQueue();
    }

    if (queueStatusFilter) queueStatusFilter.addEventListener("change", loadMaintenanceQueue);
    if (queueUrgencyFilter) queueUrgencyFilter.addEventListener("change", loadMaintenanceQueue);
    if (queueCategoryFilter) queueCategoryFilter.addEventListener("change", loadMaintenanceQueue);
    if (queueDomainFilter) queueDomainFilter.addEventListener("change", loadMaintenanceQueue);
    if (queueSortFilter) queueSortFilter.addEventListener("change", loadMaintenanceQueue);
    if (queueAssigneeFilter) queueAssigneeFilter.addEventListener("change", loadMaintenanceQueue);
    if (queueSearchInput) queueSearchInput.addEventListener("input", debounce(loadMaintenanceQueue, 300));
    if (resetQueueFiltersBtn) resetQueueFiltersBtn.addEventListener("click", resetAllQueueFilters);
    if (queueEmptyResetBtn) queueEmptyResetBtn.addEventListener("click", resetAllQueueFilters);
    if (queueRetryBtn) queueRetryBtn.addEventListener("click", loadMaintenanceQueue);
    if (refreshQueueBtn) refreshQueueBtn.addEventListener("click", loadMaintenanceQueue);

    // Hash Route Support (e.g. #map, #records, #new, #dashboard, #reports, #queue, #users)
    function checkHashRoute() {
        const hash = (window.location.hash || "").toLowerCase().replace("#", "").trim();
        if (!currentUser) {
            // For unauthenticated visitors, show public/guest views or default to dashboard
            if (hash === "map" || hash === "defect-map") {
                switchView("map");
            } else if (hash === "records") {
                switchView("records");
            } else if (hash && hash !== "dashboard") {
                switchView("dashboard");
                openAuthModal();
            } else {
                switchView("dashboard");
            }
            return;
        }

        if (hash === "map" || hash === "defect-map") {
            switchView("map");
        } else if (hash === "records") {
            switchView("records");
        } else if (hash === "new" || hash === "inspect") {
            if (currentUser.role === "maintenance") {
                switchView("queue");
            } else {
                switchView("new");
            }
        } else if (hash === "dashboard") {
            switchView("dashboard");
        } else if (hash === "reports" || hash === "export") {
            if (currentUser.role === "maintenance") {
                switchView("queue");
            } else {
                switchView("reports");
            }
        } else if (hash === "queue" || hash === "maintenance-queue" || hash === "work-queue") {
            if (currentUser.role === "inspector" || currentUser.role === "citizen") {
                switchView("dashboard");
            } else {
                switchView("queue");
            }
        } else if (hash === "users" || hash === "user-management") {
            if (currentUser.role !== "admin") {
                switchView("dashboard");
            } else {
                switchView("users");
            }
        }
    }
    // -------------------------------------------------------------------------
    // Civic Complaint Draft Assistance UI Controller (Phase 3)
    // -------------------------------------------------------------------------
    const openComplaintDraftBtn = document.getElementById("openComplaintDraftBtn");
    const complaintDraftModal = document.getElementById("complaintDraftModal");
    const closeComplaintDraftModalBtn = document.getElementById("closeComplaintDraftModalBtn");
    const cancelComplaintDraftBtn = document.getElementById("cancelComplaintDraftBtn");
    const complaintDraftForm = document.getElementById("complaintDraftForm");
    const complaintDraftInspId = document.getElementById("complaintDraftInspId");
    const complaintDraftCurrentStatus = document.getElementById("complaintDraftCurrentStatus");
    const complaintDraftSubtitle = document.getElementById("complaintDraftSubtitle");
    const complaintStatusBadge = document.getElementById("complaintStatusBadge");
    const complaintDraftNoticeAlert = document.getElementById("complaintDraftNoticeAlert");
    const complaintSubmittedBanner = document.getElementById("complaintSubmittedBanner");
    const submittedChannelLabel = document.getElementById("submittedChannelLabel");
    const submittedRefLabel = document.getElementById("submittedRefLabel");
    const submittedDateLabel = document.getElementById("submittedDateLabel");
    const complaintFeedback = document.getElementById("complaintFeedback");

    const complaintEvidenceDomain = document.getElementById("complaintEvidenceDomain");
    const complaintEvidenceDefects = document.getElementById("complaintEvidenceDefects");
    const complaintEvidenceConf = document.getElementById("complaintEvidenceConf");
    const complaintEvidenceGps = document.getElementById("complaintEvidenceGps");
    const complaintEvidencePhoto = document.getElementById("complaintEvidencePhoto");

    const complaintComplainantName = document.getElementById("complaintComplainantName");
    const complaintComplainantContact = document.getElementById("complaintComplainantContact");
    const complaintLocationInput = document.getElementById("complaintLocationInput");
    const complaintAgencyInput = document.getElementById("complaintAgencyInput");
    const complaintSubjectInput = document.getElementById("complaintSubjectInput");
    const complaintBodyTextarea = document.getElementById("complaintBodyTextarea");

    const toggleOfficialGuidanceBtn = document.getElementById("toggleOfficialGuidanceBtn");
    const complaintGuidanceBody = document.getElementById("complaintGuidanceBody");
    const guidanceToggleIcon = document.getElementById("guidanceToggleIcon");
    const officialChannelsList = document.getElementById("officialChannelsList");

    const manualSubmissionPanel = document.getElementById("manualSubmissionPanel");
    const openManualSubmitBtn = document.getElementById("openManualSubmitBtn");
    const cancelManualSubmitBtn = document.getElementById("cancelManualSubmitBtn");
    const confirmManualSubmitBtn = document.getElementById("confirmManualSubmitBtn");
    const manualSubmissionChannel = document.getElementById("manualSubmissionChannel");
    const manualSubmissionRef = document.getElementById("manualSubmissionRef");
    const manualSubmissionConfirmCheck = document.getElementById("manualSubmissionConfirmCheck");

    const markReadyComplaintBtn = document.getElementById("markReadyComplaintBtn");
    const saveComplaintDraftBtn = document.getElementById("saveComplaintDraftBtn");
    const copyComplaintDraftBtn = document.getElementById("copyComplaintDraftBtn");
    const exportComplaintTxtBtn = document.getElementById("exportComplaintTxtBtn");
    const exportComplaintPdfBtn = document.getElementById("exportComplaintPdfBtn");

    function updateComplaintStatusBadge(status, draft) {
        const st = (status || "draft").toLowerCase();
        if (complaintDraftCurrentStatus) complaintDraftCurrentStatus.value = st;

        if (complaintStatusBadge) {
            complaintStatusBadge.className = "complaint-status-badge";
            if (st === "submitted") {
                complaintStatusBadge.classList.add("complaint-status-submitted");
                complaintStatusBadge.textContent = "✅ Submitted";
            } else if (st === "ready_to_submit") {
                complaintStatusBadge.classList.add("complaint-status-ready");
                complaintStatusBadge.textContent = "🚀 Ready to Submit";
            } else if (st === "exported") {
                complaintStatusBadge.classList.add("complaint-status-exported");
                complaintStatusBadge.textContent = "📑 Exported";
            } else {
                complaintStatusBadge.classList.add("complaint-status-draft");
                complaintStatusBadge.textContent = "📝 Draft";
            }
        }

        if (st === "submitted" && draft) {
            if (complaintSubmittedBanner) {
                complaintSubmittedBanner.style.display = "flex";
                if (submittedChannelLabel) submittedChannelLabel.textContent = draft.submission_channel || "Manual Citizen Filing";
                if (submittedRefLabel) submittedRefLabel.textContent = draft.submission_reference || "Self-Reported";
                if (submittedDateLabel) submittedDateLabel.textContent = draft.submitted_at ? String(draft.submitted_at).substring(0, 19) : "Recorded";
            }
            if (complaintDraftNoticeAlert) complaintDraftNoticeAlert.style.display = "none";
            if (openManualSubmitBtn) openManualSubmitBtn.style.display = "none";
        } else {
            if (complaintSubmittedBanner) complaintSubmittedBanner.style.display = "none";
            if (complaintDraftNoticeAlert) complaintDraftNoticeAlert.style.display = "flex";
            if (openManualSubmitBtn) openManualSubmitBtn.style.display = "inline-block";
        }
    }

    async function openComplaintDraftModal(inspectionId) {
        if (!inspectionId) return;
        if (complaintFeedback) {
            complaintFeedback.style.display = "none";
            complaintFeedback.textContent = "";
        }
        if (manualSubmissionPanel) manualSubmissionPanel.style.display = "none";
        if (complaintDraftInspId) complaintDraftInspId.value = inspectionId;
        if (complaintDraftSubtitle) complaintDraftSubtitle.textContent = `Loading draft for Inspection #${inspectionId}...`;
        if (complaintDraftModal) complaintDraftModal.style.display = "flex";

        try {
            const res = await fetch(`/api/inspections/${inspectionId}/complaint-draft`);
            const data = await res.json();
            if (!res.ok || data.status !== "success") {
                throw new Error(data.message || "Failed to load complaint draft.");
            }
            const draft = data.draft;
            const domain = (draft.inspection_type || "road").toUpperCase();

            if (complaintDraftSubtitle) {
                complaintDraftSubtitle.textContent = `Formal grievance draft for Record #${inspectionId} (${domain} Problem)`;
            }

            // Evidence Bar
            if (complaintEvidenceDomain) complaintEvidenceDomain.textContent = domain;
            if (complaintEvidenceDefects) {
                const count = draft.inspection_defect_count || 1;
                complaintEvidenceDefects.textContent = `${draft.inspection_defect_type || "Distress"} (${count} area${count === 1 ? '' : 's'})`;
            }
            if (complaintEvidenceConf) {
                complaintEvidenceConf.textContent = draft.inspection_confidence ? `${Math.round(draft.inspection_confidence * 100)}%` : "N/A";
            }
            if (complaintEvidenceGps) {
                if (draft.inspection_latitude && draft.inspection_longitude) {
                    complaintEvidenceGps.textContent = `${Number(draft.inspection_latitude).toFixed(4)}, ${Number(draft.inspection_longitude).toFixed(4)}`;
                } else {
                    complaintEvidenceGps.textContent = "Not recorded";
                }
            }
            if (complaintEvidencePhoto) complaintEvidencePhoto.textContent = draft.inspection_image_name || `Record #${inspectionId} Photo`;

            // Form inputs
            if (complaintComplainantName) {
                complaintComplainantName.value = draft.complainant_name || (currentUser && currentUser.username !== "guest" ? currentUser.username : "");
            }
            if (complaintComplainantContact) complaintComplainantContact.value = draft.complainant_contact || "";
            if (complaintLocationInput) complaintLocationInput.value = draft.inspection_location || "";
            if (complaintAgencyInput) complaintAgencyInput.value = draft.recipient_agency || "";
            if (complaintSubjectInput) complaintSubjectInput.value = draft.subject || "";
            if (complaintBodyTextarea) complaintBodyTextarea.value = draft.complaint_body || "";

            // Official submission guidance channels
            if (officialChannelsList) {
                officialChannelsList.innerHTML = "";
                const channels = draft.official_channels || [];
                channels.forEach(ch => {
                    const card = document.createElement("div");
                    card.className = "official-channel-card";
                    card.innerHTML = `
                        <div class="official-channel-title">
                            <span>🏛️</span>
                            <span>${escapeHtml(ch.channel_name)}</span>
                            <small class="text-muted" style="margin-left: auto; font-size: 0.72rem;">${escapeHtml(ch.authority_type)}</small>
                        </div>
                        <div style="font-size: 0.8rem; line-height: 1.4; color: #cbd5e1;">
                            ${escapeHtml(ch.instructions)}
                        </div>
                    `;
                    officialChannelsList.appendChild(card);
                });
            }

            updateComplaintStatusBadge(draft.status || "draft", draft);
        } catch (err) {
            console.error("Failed to load complaint draft:", err);
            if (complaintFeedback) {
                complaintFeedback.style.display = "block";
                complaintFeedback.className = "alert alert-danger";
                complaintFeedback.textContent = `Error loading draft: ${err.message}`;
            }
        }
    }

    function closeComplaintDraftModal() {
        if (complaintDraftModal) complaintDraftModal.style.display = "none";
        if (complaintFeedback) {
            complaintFeedback.style.display = "none";
            complaintFeedback.textContent = "";
        }
        if (manualSubmissionPanel) manualSubmissionPanel.style.display = "none";
    }

    if (openComplaintDraftBtn) {
        openComplaintDraftBtn.addEventListener("click", () => {
            if (currentDetailId) {
                openComplaintDraftModal(currentDetailId);
            }
        });
    }

    if (closeComplaintDraftModalBtn) closeComplaintDraftModalBtn.addEventListener("click", closeComplaintDraftModal);
    if (cancelComplaintDraftBtn) cancelComplaintDraftBtn.addEventListener("click", closeComplaintDraftModal);

    // Toggle Official Submission Guidance
    if (toggleOfficialGuidanceBtn && complaintGuidanceBody) {
        toggleOfficialGuidanceBtn.addEventListener("click", () => {
            const isHidden = complaintGuidanceBody.style.display === "none";
            complaintGuidanceBody.style.display = isHidden ? "block" : "none";
            if (guidanceToggleIcon) guidanceToggleIcon.textContent = isHidden ? "▲" : "▼";
        });
    }

    // Toggle Manual Submission Panel
    if (openManualSubmitBtn && manualSubmissionPanel) {
        openManualSubmitBtn.addEventListener("click", () => {
            const isHidden = manualSubmissionPanel.style.display === "none";
            manualSubmissionPanel.style.display = isHidden ? "block" : "none";
            if (isHidden && manualSubmissionChannel) {
                manualSubmissionChannel.focus();
            }
        });
    }

    if (cancelManualSubmitBtn && manualSubmissionPanel) {
        cancelManualSubmitBtn.addEventListener("click", () => {
            manualSubmissionPanel.style.display = "none";
        });
    }

    // Confirm & Log Manual Citizen Submission
    if (confirmManualSubmitBtn) {
        confirmManualSubmitBtn.addEventListener("click", async () => {
            const inspId = complaintDraftInspId ? complaintDraftInspId.value : currentDetailId;
            if (!inspId) return;

            const isConfirmed = manualSubmissionConfirmCheck && manualSubmissionConfirmCheck.checked;
            if (!isConfirmed) {
                if (complaintFeedback) {
                    complaintFeedback.style.display = "block";
                    complaintFeedback.className = "alert alert-danger";
                    complaintFeedback.textContent = "Please check the confirmation box certifying that you have submitted this grievance to the official authority.";
                }
                return;
            }

            const channel = manualSubmissionChannel ? manualSubmissionChannel.value.trim() : "";
            if (!channel) {
                if (complaintFeedback) {
                    complaintFeedback.style.display = "block";
                    complaintFeedback.className = "alert alert-danger";
                    complaintFeedback.textContent = "Please enter the filing channel or authority name.";
                }
                if (manualSubmissionChannel) manualSubmissionChannel.focus();
                return;
            }

            const refNum = manualSubmissionRef ? manualSubmissionRef.value.trim() : "";
            confirmManualSubmitBtn.disabled = true;
            confirmManualSubmitBtn.textContent = "Recording...";

            try {
                const payload = {
                    manual_submission: true,
                    submission_channel: channel,
                    submission_reference: refNum || "Self-Reported",
                    recipient_agency: complaintAgencyInput ? complaintAgencyInput.value.trim() : "",
                    subject: complaintSubjectInput ? complaintSubjectInput.value.trim() : "",
                    complaint_body: complaintBodyTextarea ? complaintBodyTextarea.value.trim() : "",
                    complainant_name: complaintComplainantName ? complaintComplainantName.value.trim() : "",
                    complainant_contact: complaintComplainantContact ? complaintComplainantContact.value.trim() : "",
                    location_address: complaintLocationInput ? complaintLocationInput.value.trim() : "",
                };

                const res = await fetch(`/api/inspections/${inspId}/complaint-draft`, {
                    method: "PUT",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify(payload)
                });
                const data = await res.json();
                if (!res.ok || data.status !== "success") {
                    throw new Error(data.message || "Failed to record submission.");
                }

                if (manualSubmissionPanel) manualSubmissionPanel.style.display = "none";
                updateComplaintStatusBadge("submitted", data.draft);

                if (complaintFeedback) {
                    complaintFeedback.style.display = "block";
                    complaintFeedback.className = "alert alert-success";
                    complaintFeedback.textContent = "✓ Official grievance submission recorded successfully for your citizen records.";
                }

                // Refresh citizen dashboard table if active
                if (typeof loadCitizenDashboard === "function") {
                    loadCitizenDashboard();
                }
            } catch (err) {
                if (complaintFeedback) {
                    complaintFeedback.style.display = "block";
                    complaintFeedback.className = "alert alert-danger";
                    complaintFeedback.textContent = `Error recording submission: ${err.message}`;
                }
            } finally {
                confirmManualSubmitBtn.disabled = false;
                confirmManualSubmitBtn.textContent = "Confirm & Mark as Submitted";
            }
        });
    }

    // Mark as Ready to Submit
    if (markReadyComplaintBtn) {
        markReadyComplaintBtn.addEventListener("click", async () => {
            const inspId = complaintDraftInspId ? complaintDraftInspId.value : currentDetailId;
            if (!inspId) return;

            const agency = complaintAgencyInput ? complaintAgencyInput.value.trim() : "";
            const subject = complaintSubjectInput ? complaintSubjectInput.value.trim() : "";
            const body = complaintBodyTextarea ? complaintBodyTextarea.value.trim() : "";

            if (!agency || !subject || !body) {
                if (complaintFeedback) {
                    complaintFeedback.style.display = "block";
                    complaintFeedback.className = "alert alert-danger";
                    complaintFeedback.textContent = "Agency, Subject, and Complaint Body are all required.";
                }
                return;
            }

            markReadyComplaintBtn.disabled = true;
            markReadyComplaintBtn.textContent = "Marking Ready...";

            try {
                const res = await fetch(`/api/inspections/${inspId}/complaint-draft`, {
                    method: "PUT",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({
                        status: "ready_to_submit",
                        recipient_agency: agency,
                        subject: subject,
                        complaint_body: body,
                        complainant_name: complaintComplainantName ? complaintComplainantName.value.trim() : "",
                        complainant_contact: complaintComplainantContact ? complaintComplainantContact.value.trim() : "",
                        location_address: complaintLocationInput ? complaintLocationInput.value.trim() : "",
                    })
                });
                const data = await res.json();
                if (!res.ok || data.status !== "success") {
                    throw new Error(data.message || "Failed to mark ready.");
                }

                updateComplaintStatusBadge("ready_to_submit", data.draft);
                if (complaintFeedback) {
                    complaintFeedback.style.display = "block";
                    complaintFeedback.className = "alert alert-success";
                    complaintFeedback.textContent = "✓ Notice marked as Ready to Submit. You can now export the document and file it with the official authority.";
                }
            } catch (err) {
                if (complaintFeedback) {
                    complaintFeedback.style.display = "block";
                    complaintFeedback.className = "alert alert-danger";
                    complaintFeedback.textContent = `Error: ${err.message}`;
                }
            } finally {
                markReadyComplaintBtn.disabled = false;
                markReadyComplaintBtn.textContent = "🚀 Mark Ready";
            }
        });
    }

    // Save Draft Form
    if (complaintDraftForm) {
        complaintDraftForm.addEventListener("submit", async (e) => {
            e.preventDefault();
            const inspId = complaintDraftInspId ? complaintDraftInspId.value : currentDetailId;
            if (!inspId) return;

            const agency = complaintAgencyInput ? complaintAgencyInput.value.trim() : "";
            const subject = complaintSubjectInput ? complaintSubjectInput.value.trim() : "";
            const body = complaintBodyTextarea ? complaintBodyTextarea.value.trim() : "";
            const cName = complaintComplainantName ? complaintComplainantName.value.trim() : "";
            const cContact = complaintComplainantContact ? complaintComplainantContact.value.trim() : "";
            const loc = complaintLocationInput ? complaintLocationInput.value.trim() : "";

            if (saveComplaintDraftBtn) {
                saveComplaintDraftBtn.disabled = true;
                saveComplaintDraftBtn.textContent = "Saving...";
            }

            try {
                const currentSt = complaintDraftCurrentStatus ? complaintDraftCurrentStatus.value : "draft";
                const payload = {
                    recipient_agency: agency,
                    subject: subject,
                    complaint_body: body,
                    complainant_name: cName,
                    complainant_contact: cContact,
                    location_address: loc,
                };
                if (currentSt !== "submitted") {
                    payload.status = currentSt || "draft";
                }

                const res = await fetch(`/api/inspections/${inspId}/complaint-draft`, {
                    method: "PUT",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify(payload)
                });
                const data = await res.json();
                if (!res.ok || data.status !== "success") {
                    throw new Error(data.message || "Failed to update draft.");
                }
                updateComplaintStatusBadge(data.draft.status || "draft", data.draft);

                if (complaintFeedback) {
                    complaintFeedback.style.display = "block";
                    complaintFeedback.className = "alert alert-success";
                    complaintFeedback.textContent = "✓ Complaint draft saved successfully.";
                }
            } catch (err) {
                if (complaintFeedback) {
                    complaintFeedback.style.display = "block";
                    complaintFeedback.className = "alert alert-danger";
                    complaintFeedback.textContent = `Error saving draft: ${err.message}`;
                }
            } finally {
                if (saveComplaintDraftBtn) {
                    saveComplaintDraftBtn.disabled = false;
                    saveComplaintDraftBtn.textContent = "💾 Save Draft";
                }
            }
        });
    }

    if (copyComplaintDraftBtn) {
        copyComplaintDraftBtn.addEventListener("click", async () => {
            if (!complaintBodyTextarea || !complaintBodyTextarea.value) return;
            try {
                await navigator.clipboard.writeText(complaintBodyTextarea.value);
                const prev = copyComplaintDraftBtn.textContent;
                copyComplaintDraftBtn.textContent = "✓ Copied!";
                setTimeout(() => { copyComplaintDraftBtn.textContent = prev; }, 2000);
            } catch (err) {
                complaintBodyTextarea.select();
                document.execCommand("copy");
                const prev = copyComplaintDraftBtn.textContent;
                copyComplaintDraftBtn.textContent = "✓ Copied!";
                setTimeout(() => { copyComplaintDraftBtn.textContent = prev; }, 2000);
            }
        });
    }

    if (exportComplaintTxtBtn) {
        exportComplaintTxtBtn.addEventListener("click", () => {
            const inspId = complaintDraftInspId ? complaintDraftInspId.value : currentDetailId;
            if (inspId) {
                window.location.href = `/api/inspections/${inspId}/complaint-draft/export/txt`;
            }
        });
    }

    if (exportComplaintPdfBtn) {
        exportComplaintPdfBtn.addEventListener("click", () => {
            const inspId = complaintDraftInspId ? complaintDraftInspId.value : currentDetailId;
            if (inspId) {
                window.location.href = `/api/inspections/${inspId}/complaint-draft/export/pdf`;
            }
        });
    }

    // Orchestrated Application Initialization
    async function initApp() {
        bindGuestLoginButtons();
        await checkAuthStatus();

        if (currentUser) {
            if (currentUser.role === "citizen") {
                switchView("dashboard");
                loadCitizenDashboard();
            } else {
                loadDashboardStats();
                loadRecordsHeaderCount();
                if (window.location.hash) {
                    checkHashRoute();
                } else {
                    switchView("dashboard");
                }
            }
        } else {
            renderGuestDashboard();
            if (window.location.hash) {
                checkHashRoute();
            } else {
                switchView("dashboard");
            }
        }
    }

    initApp();
});
