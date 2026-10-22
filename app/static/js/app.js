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
        const saveNotesInput = document.getElementById("saveNotesInput");
        const saveStatusSelect = document.getElementById("saveStatusSelect");
        const saveInspectionBtn = document.getElementById("saveInspectionBtn");
        const saveSpinner = document.getElementById("saveSpinner");
        const saveFeedback = document.getElementById("saveFeedback");
        const saveCardStatusBadge = document.getElementById("saveCardStatusBadge");

        if (saveRoadNameInput) saveRoadNameInput.value = "";
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

    const tabNewInspectionBtn = document.getElementById("tabNewInspectionBtn");
    const tabRecordsBtn = document.getElementById("tabRecordsBtn");
    const newInspectionSection = document.getElementById("newInspectionSection");
    const recordsSection = document.getElementById("recordsSection");
    const recordDetailSection = document.getElementById("recordDetailSection");
    const recordsCountBadgeHeader = document.getElementById("recordsCountBadgeHeader");

    const saveInspectionBtn = document.getElementById("saveInspectionBtn");
    const saveSpinner = document.getElementById("saveSpinner");
    const saveFeedback = document.getElementById("saveFeedback");
    const saveCardStatusBadge = document.getElementById("saveCardStatusBadge");
    const saveRoadNameInput = document.getElementById("saveRoadNameInput");
    const saveNotesInput = document.getElementById("saveNotesInput");
    const saveStatusSelect = document.getElementById("saveStatusSelect");

    const recordsStatusFilter = document.getElementById("recordsStatusFilter");
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
    const detailStatusNotes = document.getElementById("detailStatusNotes");
    const updateStatusBtn = document.getElementById("updateStatusBtn");
    const updateStatusSpinner = document.getElementById("updateStatusSpinner");
    const detailStatusFeedback = document.getElementById("detailStatusFeedback");

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

    // Helper: Map status to badge class
    function getStatusBadgeClass(status) {
        switch (status) {
            case "Open": return "badge badge-status-open";
            case "Under Review": return "badge badge-status-review";
            case "Repair in Progress": return "badge badge-status-repair";
            case "Resolved": return "badge badge-status-resolved";
            default: return "badge badge-secondary";
        }
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
        if (viewName === "new") {
            tabNewInspectionBtn.classList.add("active");
            tabRecordsBtn.classList.remove("active");
            newInspectionSection.style.display = "block";
            recordsSection.style.display = "none";
            recordDetailSection.style.display = "none";
        } else if (viewName === "records") {
            tabNewInspectionBtn.classList.remove("active");
            tabRecordsBtn.classList.add("active");
            newInspectionSection.style.display = "none";
            recordsSection.style.display = "flex";
            recordDetailSection.style.display = "none";
            loadRecords();
        } else if (viewName === "detail") {
            tabNewInspectionBtn.classList.remove("active");
            tabRecordsBtn.classList.add("active");
            newInspectionSection.style.display = "none";
            recordsSection.style.display = "none";
            recordDetailSection.style.display = "flex";
            window.scrollTo({ top: 0, behavior: "smooth" });
        }
    }

    if (tabNewInspectionBtn) tabNewInspectionBtn.addEventListener("click", () => switchView("new"));
    if (tabRecordsBtn) tabRecordsBtn.addEventListener("click", () => switchView("records"));
    if (backToRecordsBtn) backToRecordsBtn.addEventListener("click", () => switchView("records"));

    // Initial Count Fetch
    async function loadRecordsHeaderCount() {
        try {
            const res = await fetch("/api/inspections?limit=1");
            const data = await res.json();
            if (data.status === "success" && recordsCountBadgeHeader) {
                // Fetch full count via list or health
                const healthRes = await fetch("/api/health");
                const healthData = await healthRes.json();
                const total = (healthData.database && healthData.database.records_count) || data.count || 0;
                recordsCountBadgeHeader.textContent = total;
            }
        } catch (_) {}
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
            const locationNotes = saveNotesInput ? saveNotesInput.value.trim() : "";
            const status = saveStatusSelect ? saveStatusSelect.value : "Open";

            const payload = {
                image_name: lastInspectionResult.filename,
                original_image_path: lastInspectionResult.original_file_path || "",
                annotated_image_path: lastInspectionResult.processed_file_path || "",
                road_name: roadName,
                location_notes: locationNotes,
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
    async function loadRecords() {
        const filterStatus = recordsStatusFilter ? recordsStatusFilter.value : "";
        recordsTableBody.innerHTML = `<tr><td colspan="9" style="text-align: center; padding: 2rem; color: var(--text-muted);">Loading inspection records...</td></tr>`;

        try {
            const url = filterStatus ? `/api/inspections?status=${encodeURIComponent(filterStatus)}` : "/api/inspections";
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
            recordsTableBody.innerHTML = `<tr><td colspan="9" style="text-align: center; color: var(--danger); padding: 1.5rem;">Failed to load records: ${err.message}</td></tr>`;
        }
    }

    if (recordsStatusFilter) recordsStatusFilter.addEventListener("change", loadRecords);
    if (refreshRecordsBtn) refreshRecordsBtn.addEventListener("click", loadRecords);

    // Update Summary Metric Cards
    function updateRecordsStats(inspections) {
        if (!statTotalInspections) return;
        const total = inspections.length;
        const openCount = inspections.filter(i => i.status === "Open").length;
        const activeCount = inspections.filter(i => i.status === "Under Review" || i.status === "Repair in Progress").length;
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
            const roadDisplay = rec.road_name ? `<strong>${rec.road_name}</strong>` : '<span style="color: var(--text-muted); font-style: italic;">Unspecified Location</span>';
            const countDisplay = rec.defect_count > 0 
                ? `<span class="badge badge-warning" style="font-weight: 700;">${rec.defect_count} Defect${rec.defect_count === 1 ? "" : "s"}</span>`
                : `<span class="badge badge-success">0 (Sound)</span>`;
            
            const confDisplay = rec.defect_count > 0 && rec.confidence ? `${(rec.confidence * 100).toFixed(1)}%` : "N/A";
            const modeDisplay = (rec.inspection_mode || "standard") === "tiled" ? "🔬 Tiled" : "⚡ Standard";
            const statusClass = getStatusBadgeClass(rec.status);

            tr.innerHTML = `
                <td><strong>#${rec.id}</strong></td>
                <td><span style="font-size: 0.82rem; color: var(--text-secondary);">${formatDateTime(rec.uploaded_at)}</span></td>
                <td>
                    ${roadDisplay}
                    ${rec.location_notes ? `<div style="font-size: 0.75rem; color: var(--text-muted); max-width: 200px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;">${rec.location_notes}</div>` : ""}
                </td>
                <td>${countDisplay}</td>
                <td><span style="font-size: 0.82rem;">${rec.defect_type || "--"}</span></td>
                <td><strong>${confDisplay}</strong></td>
                <td><span style="font-size: 0.78rem; color: var(--text-secondary);">${modeDisplay}</span></td>
                <td><span class="${statusClass}">${rec.status}</span></td>
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
            detailRecordIdHeader.textContent = `Inspection Record #${rec.id} — ${rec.road_name || rec.image_name}`;
            detailCurrentStatusBadge.textContent = rec.status;
            detailCurrentStatusBadge.className = getStatusBadgeClass(rec.status);
            if (detailStatusSelect) detailStatusSelect.value = rec.status;
            if (detailStatusNotes) detailStatusNotes.value = rec.notes || rec.location_notes || "";

            // Images via safe streaming endpoints
            detailOriginalImg.src = `/api/inspections/${id}/image/original`;
            detailAnnotatedImg.src = `/api/inspections/${id}/image/annotated`;

            // Telemetry
            detailRoadName.textContent = rec.road_name || "Unspecified Location";
            detailLocationNotes.textContent = rec.location_notes || "No notes entered";
            detailDefectCount.textContent = rec.defect_count;
            detailDefectTypes.textContent = rec.defect_type || "None";
            detailTopConf.textContent = (rec.defect_count > 0 && rec.confidence) ? `${(rec.confidence * 100).toFixed(1)}%` : "N/A";
            detailTimestamp.textContent = formatDateTime(rec.uploaded_at);
            detailInspectionMode.textContent = (rec.inspection_mode === "tiled" ? "Tiled Slicing" : "Standard Full-Frame") + ` (≥ ${rec.confidence_threshold.toFixed(2)})`;

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
            const notes = detailStatusNotes ? detailStatusNotes.value.trim() : "";

            updateStatusBtn.disabled = true;
            updateStatusSpinner.style.display = "inline-block";
            detailStatusFeedback.style.display = "none";

            try {
                const res = await fetch(`/api/inspections/${currentDetailId}/status`, {
                    method: "PATCH",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ status: newStatus, notes: notes }),
                });
                const data = await res.json();

                if (!res.ok || data.status !== "success") {
                    throw new Error(data.message || `Update failed (HTTP ${res.status})`);
                }

                detailCurrentStatusBadge.textContent = newStatus;
                detailCurrentStatusBadge.className = getStatusBadgeClass(newStatus);

                detailStatusFeedback.innerHTML = `
                    <div class="alert alert-success alert-sm" style="margin-top: 0.75rem;">
                        <strong>✓ Status Updated:</strong> Inspection #${currentDetailId} is now marked as <strong>${newStatus}</strong>.
                    </div>
                `;
                detailStatusFeedback.style.display = "block";

                loadRecordsHeaderCount();
            } catch (err) {
                console.error("Status update error:", err);
                alert(`Error updating inspection status:\n${err.message}`);
            } finally {
                updateStatusBtn.disabled = false;
                updateStatusSpinner.style.display = "none";
            }
        });
    }
});
