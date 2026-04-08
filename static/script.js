let chart = null;
let isSettingsFormDirty = false;
let lastSuccessfulPayload = null;

function formatDisplayTime(value) {
    if (!value) return "--";
    return String(value);
}

function setButtonLoading(buttonId, isLoading, loadingText, defaultText) {
    const btn = document.getElementById(buttonId);
    if (!btn) return;

    btn.disabled = isLoading;
    btn.textContent = isLoading ? loadingText : defaultText;
}
async function fetchData() {
    try {
        const response = await fetch("/api/data");
        const data = await response.json();

        if (!response.ok || !data.success) {
            throw new Error(data.message || "Failed to fetch monitoring data.");
        }

        lastSuccessfulPayload = data;

        updateSystemStatus("Online");
        updateLastUpdateTime(new Date().toLocaleString());
        updateSensorSource(data.sensor_source || "--");
        updateRealtimeReadings(data.latest);
        updateWarnings(data.warnings || [], data.warning_status, data.warning_banner);
        updateAnalysis(data.analysis);
        updateSettingsForm(data.settings);
        updateChart(data.chart_labels || [], data.chart_values || [], data.settings);
        updateRuntime(data.runtime || {});
    } catch (error) {
        console.error("Fetch error:", error);

        updateSystemStatus("Offline / Error");
        showWarningBanner("error", "Failed to load monitoring data from the server.");

        if (!lastSuccessfulPayload) {
            renderWarnings(["Unable to retrieve warning data."]);
            updateAnalysis({
                spike_drop: "Analysis unavailable.",
                trend: "Analysis unavailable.",
                prediction: "Analysis unavailable."
            });
            updateRuntime({});
        }
    }
}

function updateSystemStatus(statusText) {
    const statusEl = document.getElementById("systemStatus");
    if (statusEl) {
        statusEl.textContent = statusText;
    }
}

function updateLastUpdateTime(value) {
    const el = document.getElementById("lastUpdateTime");
    if (el) {
        el.textContent = value || "--";
    }
}
function updateSensorSource(sourceText) {
    const sourceEl = document.getElementById("sensorSource");
    if (sourceEl) {
        sourceEl.textContent = sourceText;
    }
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
    showWarningBanner(level, warningBanner || "No warning information available.");
    renderWarnings(warnings);
}

function showWarningBanner(level, text) {
    const banner = document.getElementById("warningBanner");
    if (!banner) return;


    banner.textContent = text || "No warning information available.";
    banner.classList.remove("normal", "warning", "error");

    if (level === "error") {
        banner.classList.add("error");
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
                    tension: 0.25
                },
                {
                    label: "Min Threshold",
                    data: [],
                    borderDash: [6, 6],
                    pointRadius: 0,
                    tension: 0
                },
                {
                    label: "Max Threshold",
                    data: [],
                    borderDash: [6, 6],
                    pointRadius: 0,
                    tension: 0
                }
            ]
        },
        options: {
            responsive: true,
            maintainAspectRatio: true,
            animation: false,
            plugins: {
                legend: {
                    display: true
                }
            },
            scales: {
                x: {
                    title: {
                        display: true,
                        text: "Timestamp"
                    }
                },
                y: {
                    title: {
                        display: true,
                        text: "Temperature (°C)"
                    }
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
        setButtonLoading("settingsSubmitBtn", true, "Saving...", "Save Settings");

        const response = await fetch("/api/settings", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload)
        });

        const result = await response.json();



        if (!response.ok || !result.success) {
            throw new Error(result.message || "Failed to update settings.");
        }

        showFormMessage("settingsMessage", result.message || "Settings updated successfully.", true);
        isSettingsFormDirty = false;
        await fetchData();
    } catch (error) {
        console.error("Settings update error:", error);
        showFormMessage("settingsMessage", error.message, false);
    } finally {
        setButtonLoading("settingsSubmitBtn", false, "Saving...", "Save Settings");
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
        setButtonLoading("simulateSubmitBtn", true, "Submitting...", "Submit Sensor Data");

        const response = await fetch("/api/simulate", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload)
        });

        const result = await response.json();

        if (!response.ok || !result.success) {
            throw new Error(result.message || "Failed to submit sensor data.");
        }


        showFormMessage("simulateMessage", result.message || "Sensor data submitted successfully.", true);
        document.getElementById("simulateForm").reset();
        await fetchData();
    } catch (error) {
        console.error("Simulation submit error:", error);
        showFormMessage("simulateMessage", error.message, false);
    } finally {
        setButtonLoading("simulateSubmitBtn", false, "Submitting...", "Submit Sensor Data");
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
    fetchData();
    setInterval(fetchData, window.APP_CONFIG?.dataRefreshMs || 3000);
}
document.addEventListener("DOMContentLoaded", initDashboard);