let chart = null;
let isSettingsFormDirty = false;
let lastSuccessfulPayload = null;
let firstLoadComplete = false;
/** After Save to cloud, ignore stale settings from /api/data polls briefly. */
let settingsPinnedUntil = 0;

function formatDisplayTime(value) {
    if (!value) return "--";
    return String(value);
}

function setLoading(isLoading) {
    const overlay = document.getElementById("loadingOverlay");
    if (!overlay) return;
    overlay.classList.toggle("visible", isLoading);
    overlay.setAttribute("aria-hidden", isLoading ? "false" : "true");
}

function setButtonLoading(buttonId, isLoading, loadingText, defaultText) {
    const btn = document.getElementById(buttonId);
    if (!btn) return;
    btn.disabled = isLoading;
    btn.textContent = isLoading ? loadingText : defaultText;
}

function setEmptyStateVisible(show) {
    const el = document.getElementById("emptyState");
    if (!el) return;
    el.classList.toggle("hidden", !show);
}

function updateOverallLevel(level) {
    const el = document.getElementById("overallStatusLevel");
    if (!el) return;
    const map = {
        normal: "Normal",
        warning: "Warning",
        critical: "Critical",
        error: "Error"
    };
    el.textContent = map[level] || map.normal;
    el.classList.remove("normal", "warning", "critical", "error");
    el.classList.add("status-pill", level === "critical" ? "critical" : level || "normal");
}

function updateCloudPanels(data) {
    const rt = data.runtime || {};
    const cloud = data.cloud || {};

    const fetchOk = rt.cloud_api_reachable === true;
    const cloudEl = document.getElementById("cloudApiStatus");
    if (cloudEl) {
        cloudEl.textContent = fetchOk ? "Online" : "Offline / degraded";
        cloudEl.classList.toggle("text-ok", fetchOk);
        cloudEl.classList.toggle("text-bad", !fetchOk);
    }

    const dynamoEl = document.getElementById("dynamoStatus");
    if (dynamoEl) {
        const ok = rt.dynamodb_indicated_ok === true;
        dynamoEl.textContent = ok ? "Writes OK" : "Unknown / no recent write";
        dynamoEl.classList.toggle("text-ok", ok);
        dynamoEl.classList.toggle("text-warn", !ok);
    }

    const lastFetch = document.getElementById("lastCloudFetch");
    if (lastFetch) lastFetch.textContent = formatDisplayTime(rt.last_cloud_fetch_success_at);

    const lastUp = document.getElementById("lastCloudUpload");
    if (lastUp) lastUp.textContent = formatDisplayTime(rt.last_cloud_upload_success_at);

    if (!firstLoadComplete) {
        firstLoadComplete = true;
        setLoading(false);
    }
}

async function fetchData() {
    if (!firstLoadComplete) setLoading(true);
    try {
        const response = await fetch("/api/data");
        const data = await response.json();

        if (!response.ok || data.success === false) {
            const msg = data.message || "Failed to fetch monitoring data.";
            if (data.fallback_used && data.source === "local_fallback") {
                showWarningBanner("error", `${msg} (local fallback — AWS unavailable)`);
                lastSuccessfulPayload = data;
                applyDashboardPayload(data);
                updateSystemStatus("Degraded (local fallback)");
                updateLastUpdateTime(new Date().toLocaleString());
                return;
            }
            throw new Error(
                data.error_code ? `${msg} [${data.error_code}]` : msg
            );
        }

        lastSuccessfulPayload = data;

        if (data.data_source || data.analysis_source || data.settings_source) {
            console.debug("[DEBUG] /api/data", {
                data_source: data.data_source || data.source,
                settings_source: data.settings_source,
                analysis_source: data.analysis_source,
                warnings_source: data.warnings_source,
                settings: data.settings,
                warnings: data.warnings,
                warning_status: data.warning_status,
                analysis: data.analysis
            });
        }

        applyDashboardPayload(data);
        const statusLabel =
            data.data_source === "LOCAL_FALLBACK"
                ? "Degraded (local fallback)"
                : data.source === "aws"
                  ? "Online (AWS Brain)"
                  : "Online";
        updateSystemStatus(statusLabel);
        updateLastUpdateTime(new Date().toLocaleString());
    } catch (error) {
        console.error("Fetch error:", error);
        updateSystemStatus("Offline / error");
        updateCloudPanels({
            runtime: { cloud_api_reachable: false },
            cloud: {}
        });
        showWarningBanner("error", "Failed to load monitoring data from the server.");
        updateBrainSourceDisplay(
            { success: false, message: "Failed to load monitoring data from the server." },
            []
        );

        if (!lastSuccessfulPayload) {
            renderWarnings(["Unable to retrieve warning data."]);
            updateAnalysis({
                spike_drop: "Analysis unavailable.",
                trend: "Analysis unavailable.",
                prediction: "Analysis unavailable."
            });
            updateRuntime({});
            setEmptyStateVisible(true);
        }
    } finally {
        if (!firstLoadComplete) {
            firstLoadComplete = true;
            setLoading(false);
        }
    }
}

function applyDashboardPayload(data) {
    updateSensorSource(data.sensor_source || "--");
    updateCloudPanels(data);

    const cloudWarnings = extractCloudWarnings(data);
    updateBrainSourceDisplay(data, cloudWarnings);

    const hasPoints =
        (data.cloud && data.cloud.sensor_points > 0) ||
        (data.latest && data.chart_values && data.chart_values.length) ||
        (data.sensor_data && data.sensor_data.length > 0);

    setEmptyStateVisible(!data.latest && !hasPoints);

    updateRealtimeReadings(data.latest);
    const authWarnings = getAuthoritativeWarnings(data);
    const statusBannerText =
        authWarnings.length > 0
            ? authWarnings.join(" | ")
            : data.warning_banner;
    updateWarnings(cloudWarnings, data.warning_status, statusBannerText);
    updateAnalysis(data.analysis);
    updateSettingsForm(data.settings);
    updateChart(data.chart_labels || [], data.chart_values || [], data.settings);
    updateRuntime(data.runtime || {});
}

function updateSystemStatus(statusText) {
    const statusEl = document.getElementById("systemStatus");
    if (statusEl) statusEl.textContent = statusText;
}

function updateLastUpdateTime(value) {
    const el = document.getElementById("lastUpdateTime");
    if (el) el.textContent = value || "--";
}

function updateSensorSource(sourceText) {
    const sourceEl = document.getElementById("sensorSource");
    if (sourceEl) sourceEl.textContent = sourceText;
}

function updateRealtimeReadings(latest) {
    const temperatureEl = document.getElementById("temperature");
    const humidityEl = document.getElementById("humidity");
    const pressureEl = document.getElementById("pressure");
    const timestampEl = document.getElementById("timestamp");

    if (!temperatureEl || !humidityEl || !pressureEl || !timestampEl) return;

    if (!latest) {
        temperatureEl.textContent = "--";
        humidityEl.textContent = "--";
        pressureEl.textContent = "--";
        timestampEl.textContent = "--";
        return;
    }

    temperatureEl.textContent = Number(latest.temperature).toFixed(2);
    humidityEl.textContent = Number(latest.humidity).toFixed(2);
    pressureEl.textContent = Number(latest.pressure).toFixed(2);
    timestampEl.textContent = latest.timestamp || "--";
}

/**
 * AWS GET /data schema is authoritative for dashboard warnings (data.warnings, data.warning_status).
 * Legacy Flask fields (warning_info, warning_message, local_warning) are deprecated fallbacks only.
 */
function extractCloudWarnings(data) {
    if (!data || typeof data !== "object") return [];

    try {
        const primary = data.warnings;
        if (Array.isArray(primary) && primary.length > 0) {
            return normalizeWarningStrings(primary);
        }
        if (typeof primary === "string" && primary.trim()) {
            return [primary.trim()];
        }

        const status = data.warning_status;
        if (status && Array.isArray(status.messages) && status.messages.length > 0) {
            return normalizeWarningStrings(status.messages);
        }

        // Deprecated local/Flask fields — kept for backward compatibility with older payloads.
        const legacy =
            data.warning_info ||
            data.warning_message ||
            data.local_warning ||
            (data.analysis && data.analysis.warning_info);
        if (Array.isArray(legacy) && legacy.length > 0) {
            return normalizeWarningStrings(legacy);
        }
        if (typeof legacy === "string" && legacy.trim()) {
            return [legacy.trim()];
        }
    } catch {
        return [];
    }

    return [];
}

function normalizeWarningStrings(items) {
    if (!Array.isArray(items)) return [];
    return items
        .map(item => (item == null ? "" : String(item).trim()))
        .filter(Boolean);
}

const BRAIN_NO_WARNINGS_TEXT = "No warning information available.";

function escapeHtml(text) {
    return String(text)
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#39;");
}

/** Authoritative AWS ``data.warnings`` only (same array as GET /data; not legacy Flask fields). */
function getAuthoritativeWarnings(data) {
    if (!data || typeof data !== "object") return [];
    try {
        const warnings = Array.isArray(data.warnings) ? data.warnings : [];
        return warnings
            .map(item => (item == null ? "" : String(item).trim()))
            .filter(Boolean);
    } catch {
        return [];
    }
}

function resolveWarningBannerText(warnings, warningStatus, warningBanner) {
    const list = normalizeWarningStrings(warnings);
    const explicit =
        warningBanner != null && warningBanner !== false
            ? String(warningBanner).trim()
            : "";

    if (list.length > 0) {
        if (explicit && explicit !== BRAIN_NO_WARNINGS_TEXT) {
            return explicit;
        }
        return list.join(" | ");
    }

    const statusMessages = warningStatus?.messages;
    if (Array.isArray(statusMessages) && statusMessages.length > 0) {
        return normalizeWarningStrings(statusMessages).join(" | ");
    }

    if (explicit && explicit !== BRAIN_NO_WARNINGS_TEXT) return explicit;
    return BRAIN_NO_WARNINGS_TEXT;
}

function setBrainWarningDetailTone(el, tone) {
    el.classList.remove("text-ok", "text-warn", "text-bad");
    if (tone === "warning") {
        el.classList.add("text-warn");
    } else if (tone === "error") {
        el.classList.add("text-bad");
    } else {
        el.classList.add("text-ok");
    }
}

function isBrainFetchFailed(data) {
    if (!data || typeof data !== "object") return true;
    if (data.data_source === "AWS_ERROR") return true;
    if (data.error_code && data.success === false && !data.fallback_used) return true;
    return data.success === false && !data.fallback_used;
}

/**
 * Brain source card: lineage on #brainSource; warning details on #brainWarningInfo.
 * Uses the same warnings array as the Warnings card (extractCloudWarnings / data.warnings).
 */
function updateBrainSourceDisplay(data, warnings) {
    const brainEl = document.getElementById("brainSource");
    const brainWarningEl = document.getElementById("brainWarningInfo");

    if (brainEl) {
        const parts = [
            data?.data_source || data?.source,
            data?.analysis_source ? `analysis:${data.analysis_source}` : null,
            data?.settings_source ? `settings:${data.settings_source}` : null
        ].filter(Boolean);
        brainEl.textContent = parts.join(" · ") || "—";
    }

    if (!brainWarningEl) return;

    const list = normalizeWarningStrings(
        Array.isArray(warnings) ? warnings : extractCloudWarnings(data)
    );

    if (list.length > 0) {
        brainWarningEl.textContent = list.join(" · ");
        setBrainWarningDetailTone(brainWarningEl, "warning");
        return;
    }

    if (isBrainFetchFailed(data)) {
        const msg =
            data?.message ||
            data?.warning_banner ||
            "Failed to load monitoring data from the server.";
        brainWarningEl.textContent = String(msg).trim();
        setBrainWarningDetailTone(brainWarningEl, "error");
        return;
    }

    brainWarningEl.textContent = "No warnings.";
    setBrainWarningDetailTone(brainWarningEl, "normal");
}

function updateWarnings(warnings, warningStatus, warningBanner) {
    const list = normalizeWarningStrings(warnings);
    const countEl = document.getElementById("warningCount");
    if (countEl) {
        const count = warningStatus?.count;
        countEl.textContent =
            count != null && count !== "" ? count : list.length;
    }

    const level =
        warningStatus?.level || (list.length > 0 ? "warning" : "normal");
    updateOverallLevel(level);
    showWarningBanner(
        level,
        resolveWarningBannerText(list, warningStatus, warningBanner)
    );
    renderWarnings(list);
}

function showWarningBanner(level, text) {
    const banner = document.getElementById("warningBanner");
    if (!banner) return;

    banner.textContent = text || BRAIN_NO_WARNINGS_TEXT;
    banner.classList.remove("normal", "warning", "error", "critical");

    if (level === "error") {
        banner.classList.add("error");
    } else if (level === "critical") {
        banner.classList.add("critical");
    } else if (level === "warning") {
        banner.classList.add("warning");
    } else {
        banner.classList.add("normal");
    }
}

function renderWarnings(warnings) {
    const warningsList = document.getElementById("warnings");
    if (!warningsList) return;

    const list = normalizeWarningStrings(warnings);
    warningsList.innerHTML = "";

    if (list.length === 0) {
        warningsList.innerHTML = "<li>No warnings.</li>";
        return;
    }
    list.forEach(item => {
        const li = document.createElement("li");
        li.textContent = item;
        warningsList.appendChild(li);
    });
}

function updateAnalysis(analysis) {
    const spikeEl = document.getElementById("spike_drop");
    const trendEl = document.getElementById("trend");
    const predictionEl = document.getElementById("prediction");
    if (spikeEl) spikeEl.textContent = analysis?.spike_drop || "No analysis available.";
    if (trendEl) trendEl.textContent = analysis?.trend || "No analysis available.";
    if (predictionEl) predictionEl.textContent = analysis?.prediction || "No analysis available.";
}

function updateRuntime(runtime) {
    const collectorStatus = document.getElementById("collectorStatus");
    const lastCollectionTime = document.getElementById("lastCollectionTime");
    const lastDisplayUpdate = document.getElementById("lastDisplayUpdate");
    const failureCount = document.getElementById("failureCount");
    if (collectorStatus) {
        collectorStatus.textContent = runtime.collector_thread_alive ? "Running" : "Stopped";
    }

    if (lastCollectionTime) {
        lastCollectionTime.textContent = formatDisplayTime(runtime.last_collection_success_at);
    }

    if (lastDisplayUpdate) {
        lastDisplayUpdate.textContent = formatDisplayTime(runtime.last_display_update_at);
    }

    if (failureCount) {
        failureCount.textContent = runtime.consecutive_collection_failures ?? 0;
    }
}

function normalizeSettingsForForm(settings) {
    if (!settings || typeof settings !== "object") return null;
    const pick = (...keys) => {
        for (const k of keys) {
            if (settings[k] !== undefined && settings[k] !== null && settings[k] !== "") {
                return settings[k];
            }
        }
        return "";
    };
    return {
        temp_min: pick("temp_min", "temperature_min", "min_temp"),
        temp_max: pick("temp_max", "temperature_max", "max_temp"),
        humidity_min: pick("humidity_min", "hum_min", "min_humidity"),
        humidity_max: pick("humidity_max", "hum_max", "max_humidity"),
        pressure_min: pick("pressure_min", "pressure_low", "min_pressure"),
        pressure_max: pick("pressure_max", "pressure_high", "max_pressure")
    };
}

function updateSettingsForm(settings, force = false) {
    const normalized = normalizeSettingsForForm(settings);
    if (!normalized) return;
    if (!force && isSettingsFormDirty) return;
    if (!force && Date.now() < settingsPinnedUntil) return;

    document.getElementById("temp_min").value = normalized.temp_min;
    document.getElementById("temp_max").value = normalized.temp_max;
    document.getElementById("humidity_min").value = normalized.humidity_min;
    document.getElementById("humidity_max").value = normalized.humidity_max;
    document.getElementById("pressure_min").value = normalized.pressure_min;
    document.getElementById("pressure_max").value = normalized.pressure_max;
}

function initChart() {
    const canvas = document.getElementById("tempChart");
    if (!canvas) return;
    const ctx = canvas.getContext("2d");

    chart = new Chart(ctx, {
        type: "line",
        data: {
            labels: [],
            datasets: [
                {
                    label: "Temperature (°C)",
                    data: [],
                    borderColor: "#4f46e5",
                    backgroundColor: "rgba(79, 70, 229, 0.12)",
                    fill: true,
                    tension: 0.35,
                    pointRadius: 2
                },
                {
                    label: "Min threshold",
                    data: [],
                    borderColor: "#94a3b8",
                    borderDash: [6, 6],
                    pointRadius: 0,
                    tension: 0
                },
                {
                    label: "Max threshold",
                    data: [],
                    borderColor: "#f97316",
                    borderDash: [6, 6],
                    pointRadius: 0,
                    tension: 0
                }
            ]
        },
        options: {
            responsive: true,
            maintainAspectRatio: true,
            animation: { duration: 400 },
            plugins: {
                legend: { display: true }
            },
            scales: {
                x: {
                    title: { display: true, text: "Timestamp" },
                    ticks: { maxRotation: 45, minRotation: 0, autoSkip: true, maxTicksLimit: 12 }
                },
                y: {
                    title: { display: true, text: "Temperature (°C)" }
                }
            }
        }
    });
}

function updateChart(labels, values, settings) {
    if (!chart) {
        initChart();
    }
    if (!chart) return;
    chart.data.labels = labels;
    chart.data.datasets[0].data = values;

    const minLine = labels.map(() => settings?.temp_min ?? null);
    const maxLine = labels.map(() => settings?.temp_max ?? null);
    chart.data.datasets[1].data = minLine;
    chart.data.datasets[2].data = maxLine;

    chart.update();
}

function showFormMessage(elementId, message, isSuccess = true) {
    const el = document.getElementById(elementId);
    if (!el) return;

    el.textContent = message;
    el.classList.remove("success", "error");
    el.classList.add(isSuccess ? "success" : "error");
}

function validateSettingsPayload(payload) {
    const tempMin = Number(payload.temp_min);
    const tempMax = Number(payload.temp_max);
    const humMin = Number(payload.humidity_min);
    const humMax = Number(payload.humidity_max);
    const pressureMin = Number(payload.pressure_min);
    const pressureMax = Number(payload.pressure_max);

    if (tempMin >= tempMax) {
        throw new Error("Temperature minimum must be less than maximum.");
    }
    if (humMin >= humMax) {
        throw new Error("Humidity minimum must be less than maximum.");
    }
    if (pressureMin >= pressureMax) {
        throw new Error("Pressure minimum must be less than maximum.");
    }
}

async function parseJsonResponse(response) {
    const text = await response.text();
    if (!text) return {};
    try {
        return JSON.parse(text);
    } catch {
        return { success: false, message: text || "Non-JSON response from server." };
    }
}

function apiErrorMessage(result, fallback) {
    if (!result || typeof result !== "object") return fallback;
    const parts = [];
    if (result.message) parts.push(result.message);
    if (result.error_code) parts.push(`[${result.error_code}]`);
    if (result.upstream_http_status != null) parts.push(`upstream HTTP ${result.upstream_http_status}`);
    if (result.upstream_url) parts.push(`at ${result.upstream_url}`);
    return parts.length ? parts.join(" ") : fallback;
}

async function prefetchSettingsFromApi() {
    if (isSettingsFormDirty) return;
    try {
        const response = await fetch("/api/settings");
        const result = await parseJsonResponse(response);
        if (response.ok && result.success && result.settings) {
            updateSettingsForm(result.settings);
        }
    } catch {
        /* optional; main poll fills from /api/data */
    }
}

async function handleSettingsSubmit(event) {
    event.preventDefault();

    const payload = {
        temp_min: document.getElementById("temp_min").value,
        temp_max: document.getElementById("temp_max").value,
        humidity_min: document.getElementById("humidity_min").value,
        humidity_max: document.getElementById("humidity_max").value,
        pressure_min: document.getElementById("pressure_min").value,
        pressure_max: document.getElementById("pressure_max").value
    };
    try {
        validateSettingsPayload(payload);
        setButtonLoading("settingsSubmitBtn", true, "Saving…", "Save to cloud");

        const response = await fetch("/api/settings", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload)
        });

        const result = await parseJsonResponse(response);

        if (!response.ok || !result.success) {
            throw new Error(apiErrorMessage(result, "Failed to update settings."));
        }

        showFormMessage("settingsMessage", result.message || "Settings saved to DynamoDB.", true);
        isSettingsFormDirty = false;
        if (result.settings) {
            settingsPinnedUntil = Date.now() + 10000;
            updateSettingsForm(result.settings, true);
        }
        await fetchData();
    } catch (error) {
        console.error("Settings update error:", error);
        showFormMessage("settingsMessage", error.message, false);
    } finally {
        setButtonLoading("settingsSubmitBtn", false, "Saving…", "Save to cloud");
    }
}

async function handleSimulateSubmit(event) {
    event.preventDefault();

    const payload = {
        temperature: document.getElementById("sim_temperature").value,
        humidity: document.getElementById("sim_humidity").value,
        pressure: document.getElementById("sim_pressure").value
    };
    try {
        setButtonLoading("simulateSubmitBtn", true, "Sending…", "Send to ingest");

        const response = await fetch("/api/simulate", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload)
        });

        const result = await response.json();

        if (!response.ok || !result.success) {
            throw new Error(result.message || "Failed to submit sensor data.");
        }

        showFormMessage("simulateMessage", result.message || "Reading accepted by ingest.", true);
        document.getElementById("simulateForm").reset();
        await fetchData();
    } catch (error) {
        console.error("Simulation submit error:", error);
        showFormMessage("simulateMessage", error.message, false);
    } finally {
        setButtonLoading("simulateSubmitBtn", false, "Sending…", "Send to ingest");
    }
}

function trackSettingsFormChanges() {
    const settingsInputs = document.querySelectorAll("#settingsForm input");
    settingsInputs.forEach(input => {
        input.addEventListener("input", () => {
            isSettingsFormDirty = true;
        });
    });
}

function registerEventListeners() {
    const settingsForm = document.getElementById("settingsForm");
    const simulateForm = document.getElementById("simulateForm");

    if (settingsForm) {
        settingsForm.addEventListener("submit", handleSettingsSubmit);
    }

    if (simulateForm) {
        simulateForm.addEventListener("submit", handleSimulateSubmit);
    }
    trackSettingsFormChanges();
}

function initDashboard() {
    initChart();
    registerEventListeners();
    prefetchSettingsFromApi();
    fetchData();
    setInterval(fetchData, window.APP_CONFIG?.dataRefreshMs || 4000);
}

document.addEventListener("DOMContentLoaded", initDashboard);
