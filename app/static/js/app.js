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

        // Show container and scroll
        resultsContainer.style.display = "flex";
        resultsContainer.scrollIntoView({ behavior: "smooth", block: "start" });
    }
});
