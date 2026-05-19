let chart = null;
let isSettingsFormDirty = false;
let lastSuccessfulPayload = null;
let firstLoadComplete = false;

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

        applyDashboardPayload(data);
        updateSystemStatus(data.source === "aws" ? "Online (AWS Brain)" : "Online");
        updateLastUpdateTime(new Date().toLocaleString());
    } catch (error) {
        console.error("Fetch error:", error);
        updateSystemStatus("Offline / error");
        updateCloudPanels({
            runtime: { cloud_api_reachable: false },
            cloud: {}
        });
        showWarningBanner("error", "Failed to load monitoring data from the server.");

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

    const hasPoints =
        (data.cloud && data.cloud.sensor_points > 0) ||
        (data.latest && data.chart_values && data.chart_values.length) ||
        (data.sensor_data && data.sensor_data.length > 0);

    setEmptyStateVisible(!data.latest && !hasPoints);

    updateRealtimeReadings(data.latest);
    updateWarnings(data.warnings || [], data.warning_status, data.warning_banner);
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

function updateWarnings(warnings, warningStatus, warningBanner) {
    const countEl = document.getElementById("warningCount");
    if (countEl) {
        countEl.textContent = warningStatus?.count ?? warnings.length ?? 0;
    }

    const level = warningStatus?.level || (warnings.length > 0 ? "warning" : "normal");
    updateOverallLevel(level);
    showWarningBanner(level, warningBanner || "No warning information available.");
    renderWarnings(warnings);
}

function showWarningBanner(level, text) {
    const banner = document.getElementById("warningBanner");
    if (!banner) return;

    banner.textContent = text || "No warning information available.";
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

    warningsList.innerHTML = "";

    if (!warnings || warnings.length === 0) {
        warningsList.innerHTML = "<li>No warnings.</li>";
        return;
    }
    warnings.forEach(item => {
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

function updateSettingsForm(settings) {
    if (!settings || isSettingsFormDirty) return;

    document.getElementById("temp_min").value = settings.temp_min ?? "";
    document.getElementById("temp_max").value = settings.temp_max ?? "";
    document.getElementById("humidity_min").value = settings.humidity_min ?? "";
    document.getElementById("humidity_max").value = settings.humidity_max ?? "";
    document.getElementById("pressure_min").value = settings.pressure_min ?? "";
    document.getElementById("pressure_max").value = settings.pressure_max ?? "";
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
