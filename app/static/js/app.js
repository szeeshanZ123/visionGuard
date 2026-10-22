/**
 * VisionGuard AI - Client-Side Inspection Controller (Vanilla ES6+ JavaScript)
 * Communicates with Flask REST API (/api/inspect, /api/health)
 */

document.addEventListener("DOMContentLoaded", () => {
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

    let currentFile = null;

    // 1. Initial Health Check
    async function checkHealth() {
        try {
            const res = await fetch("/api/health");
            const data = await res.json();

            // DB status
            if (data.database && data.database.connected) {
                dbStatusBadge.textContent = "Database: Connected";
                dbStatusBadge.className = "badge badge-success";
            } else {
                dbStatusBadge.textContent = "Database: Offline";
                dbStatusBadge.className = "badge badge-danger";
            }

            // Model status
            if (data.model && data.model.loaded) {
                modelStatusBadge.textContent = "Model: YOLOv8n (Loaded)";
                modelStatusBadge.className = "badge badge-success";
                systemNoticeBanner.style.display = "none";
            } else {
                modelStatusBadge.textContent = "Model: Weights Missing";
                modelStatusBadge.className = "badge badge-warning";

                systemNoticeTitle.textContent = "Model Checkpoint Awaiting Configuration";
                systemNoticeMsg.textContent = data.model ? data.model.status_message : "Checkpoint 'best.pt' not loaded.";
                systemNoticeInstructions.textContent = 
                    "Setup Steps:\n" +
                    "1. Download 'best.pt' from your Google Drive ('VisionGuard_Artifacts/best.pt') or Colab export.\n" +
                    "2. Place the file at: visionGuard/ai/models/best.pt\n" +
                    "3. Reload this page or call POST /api/reload-model.";
                systemNoticeInstructions.style.display = "block";
                systemNoticeBanner.style.display = "flex";
            }
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
        if (!currentFile) return;

        // UI State: Loading
        inspectBtn.disabled = true;
        inspectSpinner.style.display = "inline-block";
        inspectBtn.querySelector(".btn-text").textContent = "Analyzing Road Imagery...";

        const activeThreshold = parseFloat(confSlider.value) || 0.25;
        const modeRadio = document.querySelector('input[name="inspectionMode"]:checked');
        const activeMode = modeRadio ? modeRadio.value : "standard";

        const formData = new FormData();
        formData.append("image", currentFile);
        formData.append("confidence_threshold", activeThreshold.toFixed(2));
        formData.append("inspection_mode", activeMode);

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
        if (status === 503 || (data && data.error_code === "MODEL_WEIGHTS_MISSING")) {
            systemNoticeTitle.textContent = "Model Weights Checkpoint Required (HTTP 503)";
            systemNoticeMsg.textContent = (data && data.message) || message;
            systemNoticeInstructions.textContent = (data && data.setup_instructions) || "Place best.pt into ai/models/best.pt";
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
        modelCheckpointCaption.textContent = modelInfo.name || "YOLOv8n";
        metricModelName.textContent = modelInfo.name || "YOLOv8 Nano";

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

            emptyRow.innerHTML = `
                <td colspan="7" style="text-align: center; color: var(--text-muted); padding: 1.5rem;">
                    <div>✅ No surface cracks or potholes detected at confidence threshold ≥ ${usedThreshold}.</div>
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

        if (saveRoadNameInput) saveRoadNameInput.value = "";
        if (saveAreaInput) saveAreaInput.value = "";
        if (saveCityInput) saveCityInput.value = "";
        if (saveLatInput) saveLatInput.value = "";
        if (saveLonInput) saveLonInput.value = "";
        if (saveNotesInput) saveNotesInput.value = "";
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
    const dashboardSection = document.getElementById("dashboardSection");
    const newInspectionSection = document.getElementById("newInspectionSection");
    const recordsSection = document.getElementById("recordsSection");
    const recordDetailSection = document.getElementById("recordDetailSection");
    const mapSection = document.getElementById("mapSection");
    const recordsCountBadgeHeader = document.getElementById("recordsCountBadgeHeader");
    const mapCountBadgeHeader = document.getElementById("mapCountBadgeHeader");

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
    const legendCountSound = document.getElementById("legendCountSound");

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
        return html;
    }

    // Helper: Map status to badge class
    function getStatusBadgeClass(status) {
        switch (status) {
            case "Open": return "badge badge-status-open";
            case "In Progress": return "badge badge-status-in-progress";
            case "Under Review": return "badge badge-status-review";
            case "Repair in Progress": return "badge badge-status-repair";
            case "Resolved": return "badge badge-status-resolved";
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

            tr.innerHTML = `
                <td><span style="font-size: 0.78rem; color: var(--text-secondary);">${formatDateTime(act.created_at)}</span></td>
                <td>${actionBadge}</td>
                <td>${statusTransition}</td>
                <td>${dateTransition}</td>
                <td><span style="font-size: 0.8rem; color: var(--text-primary);">${escapeHtml(act.notes || "No notes entered")}</span></td>
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
        if (viewName === "dashboard") {
            if (tabDashboardBtn) tabDashboardBtn.classList.add("active");
            if (tabNewInspectionBtn) tabNewInspectionBtn.classList.remove("active");
            if (tabRecordsBtn) tabRecordsBtn.classList.remove("active");
            if (tabMapBtn) tabMapBtn.classList.remove("active");
            if (dashboardSection) dashboardSection.style.display = "flex";
            if (newInspectionSection) newInspectionSection.style.display = "none";
            if (recordsSection) recordsSection.style.display = "none";
            if (recordDetailSection) recordDetailSection.style.display = "none";
            if (mapSection) mapSection.style.display = "none";
            loadDashboardStats();
            window.scrollTo({ top: 0, behavior: "smooth" });
        } else if (viewName === "new") {
            if (tabDashboardBtn) tabDashboardBtn.classList.remove("active");
            if (tabNewInspectionBtn) tabNewInspectionBtn.classList.add("active");
            if (tabRecordsBtn) tabRecordsBtn.classList.remove("active");
            if (tabMapBtn) tabMapBtn.classList.remove("active");
            if (dashboardSection) dashboardSection.style.display = "none";
            if (newInspectionSection) newInspectionSection.style.display = "block";
            if (recordsSection) recordsSection.style.display = "none";
            if (recordDetailSection) recordDetailSection.style.display = "none";
            if (mapSection) mapSection.style.display = "none";
        } else if (viewName === "records") {
            if (tabDashboardBtn) tabDashboardBtn.classList.remove("active");
            if (tabNewInspectionBtn) tabNewInspectionBtn.classList.remove("active");
            if (tabRecordsBtn) tabRecordsBtn.classList.add("active");
            if (tabMapBtn) tabMapBtn.classList.remove("active");
            if (dashboardSection) dashboardSection.style.display = "none";
            if (newInspectionSection) newInspectionSection.style.display = "none";
            if (recordsSection) recordsSection.style.display = "flex";
            if (recordDetailSection) recordDetailSection.style.display = "none";
            if (mapSection) mapSection.style.display = "none";
            loadRecords();
        } else if (viewName === "map") {
            if (tabDashboardBtn) tabDashboardBtn.classList.remove("active");
            if (tabNewInspectionBtn) tabNewInspectionBtn.classList.remove("active");
            if (tabRecordsBtn) tabRecordsBtn.classList.remove("active");
            if (tabMapBtn) tabMapBtn.classList.add("active");
            if (dashboardSection) dashboardSection.style.display = "none";
            if (newInspectionSection) newInspectionSection.style.display = "none";
            if (recordsSection) recordsSection.style.display = "none";
            if (recordDetailSection) recordDetailSection.style.display = "none";
            if (mapSection) mapSection.style.display = "flex";
            initDefectMap();
            loadMapRecords();
            window.scrollTo({ top: 0, behavior: "smooth" });
        } else if (viewName === "detail") {
            if (tabDashboardBtn) tabDashboardBtn.classList.remove("active");
            if (tabNewInspectionBtn) tabNewInspectionBtn.classList.remove("active");
            if (tabRecordsBtn) tabRecordsBtn.classList.add("active");
            if (tabMapBtn) tabMapBtn.classList.remove("active");
            if (dashboardSection) dashboardSection.style.display = "none";
            if (newInspectionSection) newInspectionSection.style.display = "none";
            if (recordsSection) recordsSection.style.display = "none";
            if (recordDetailSection) recordDetailSection.style.display = "flex";
            if (mapSection) mapSection.style.display = "none";
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
    if (backToRecordsBtn) backToRecordsBtn.addEventListener("click", () => switchView("records"));
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
    function filterMapRecord(rec, catFilter, statusFilter, deadlineFilter, kwFilter) {
        if (!isValidCoordinate(rec.latitude, rec.longitude)) return false;

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
            } else {
                const dt = (rec.defect_type || "").toLowerCase();
                if (!dt.includes(catFilter.toLowerCase())) return false;
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
        let d00 = 0, d10 = 0, d20 = 0, d40 = 0, sound = 0;
        geotaggedRecords.forEach(rec => {
            const cfg = getMarkerConfig(rec);
            if (cfg.category === "Sound") sound++;
            else if (cfg.category === "Pothole") d40++;
            else if (cfg.category === "Alligator") d20++;
            else if (cfg.category === "Transverse") d10++;
            else d00++;
        });

        if (legendCountD00) legendCountD00.textContent = `${d00} record${d00 === 1 ? "" : "s"}`;
        if (legendCountD10) legendCountD10.textContent = `${d10} record${d10 === 1 ? "" : "s"}`;
        if (legendCountD20) legendCountD20.textContent = `${d20} record${d20 === 1 ? "" : "s"}`;
        if (legendCountD40) legendCountD40.textContent = `${d40} record${d40 === 1 ? "" : "s"}`;
        if (legendCountSound) legendCountSound.textContent = `${sound} record${sound === 1 ? "" : "s"}`;
    }

    // Render Markers on Leaflet Map
    function renderMapMarkers() {
        if (!defectMapInstance || !markersLayerGroup) return;

        // Clear existing markers to prevent duplicates
        markersLayerGroup.clearLayers();

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

        const filtered = validGeotagged.filter(rec => filterMapRecord(rec, catFilter, statusFilter, deadlineFilter, kwFilter));
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
    if (mapCategoryFilter) mapCategoryFilter.addEventListener("change", renderMapMarkers);
    if (mapStatusFilter) mapStatusFilter.addEventListener("change", renderMapMarkers);
    if (mapDeadlineFilter) mapDeadlineFilter.addEventListener("change", renderMapMarkers);
    if (mapSearchInput) mapSearchInput.addEventListener("input", debounce(renderMapMarkers, 250));
    if (resetMapFiltersBtn) {
        resetMapFiltersBtn.addEventListener("click", () => {
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
    loadRecordsHeaderCount();

    // Save Inspection Action (with duplicate protection)
    if (saveInspectionBtn) {
        saveInspectionBtn.addEventListener("click", async () => {
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
                        <span style="color: var(--text-secondary); display: inline-flex; align-items: center; gap: 0.4rem;">
                            <span>ℹ️</span> ${data.message || "This inspection is already saved."}
                            <button type="button" class="btn btn-secondary btn-sm" id="viewSavedRecordBtn" style="margin-left: 0.5rem; padding: 0.25rem 0.65rem; font-size: 0.8rem;">
                                View in Records History →
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
                    <span style="color: var(--success); display: inline-flex; align-items: center; gap: 0.4rem;">
                        <span>✓</span> Successfully persisted to database.
                        <button type="button" class="btn btn-secondary btn-sm" id="viewSavedRecordBtn" style="margin-left: 0.5rem; padding: 0.25rem 0.65rem; font-size: 0.8rem;">
                            View in Records History →
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
        const filterStatus = recordsStatusFilter ? recordsStatusFilter.value : "";
        const filterCategory = recordsCategoryFilter ? recordsCategoryFilter.value : "";
        const filterDeadline = recordsDeadlineFilter ? recordsDeadlineFilter.value : "";
        const filterSearch = recordsSearchInput ? recordsSearchInput.value.trim() : "";

        recordsTableBody.innerHTML = `<tr><td colspan="10" style="text-align: center; padding: 2rem; color: var(--text-muted);">Loading inspection records...</td></tr>`;

        try {
            const params = new URLSearchParams();
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

    if (recordsStatusFilter) recordsStatusFilter.addEventListener("change", loadRecords);
    if (recordsCategoryFilter) recordsCategoryFilter.addEventListener("change", loadRecords);
    if (recordsDeadlineFilter) recordsDeadlineFilter.addEventListener("change", loadRecords);
    if (recordsSearchInput) recordsSearchInput.addEventListener("input", debounce(loadRecords, 300));
    if (resetRecordsFiltersBtn) {
        resetRecordsFiltersBtn.addEventListener("click", () => {
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

            tr.innerHTML = `
                <td><strong>#${rec.id}</strong></td>
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
        } catch (err) {
            console.error("Open detail error:", err);
            alert(`Failed to load inspection detail:\n${err.message}`);
            switchView("records");
        }
    }

    // Status Update Action
    if (updateStatusBtn) {
        updateStatusBtn.addEventListener("click", async () => {
            if (!currentDetailId) return;

            const newStatus = detailStatusSelect ? detailStatusSelect.value : "";
            const targetRepairDate = detailTargetDateInput ? detailTargetDateInput.value.trim() : "";
            const notes = detailStatusNotes ? detailStatusNotes.value.trim() : "";

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
            } catch (err) {
                console.error("Status update error:", err);
                alert(`Error updating inspection record:\n${err.message}`);
            } finally {
                updateStatusBtn.disabled = false;
                updateStatusSpinner.style.display = "none";
            }
        });
    }

    // Initialize Dashboard and Records Count
    loadDashboardStats();
    loadRecordsHeaderCount();

    // Hash Route Support (e.g. #map, #records, #new, #dashboard)
    function checkHashRoute() {
        const hash = (window.location.hash || "").toLowerCase().replace("#", "").trim();
        if (hash === "map" || hash === "defect-map") {
            switchView("map");
        } else if (hash === "records") {
            switchView("records");
        } else if (hash === "new" || hash === "inspect") {
            switchView("new");
        } else if (hash === "dashboard") {
            switchView("dashboard");
        }
    }
    window.addEventListener("hashchange", checkHashRoute);
    if (window.location.hash) {
        checkHashRoute();
    }
});
