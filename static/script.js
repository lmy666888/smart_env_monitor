let chart = null;
let isSettingsFormDirty = false;

/**
 * Fetch monitoring data from the backend and update the dashboard.
 */
async function fetchData() {
    try {
        const response = await fetch("/api/data");
        const data = await response.json();

        if (!response.ok || !data.success) {
            throw new Error(data.message || "Failed to fetch monitoring data.");
        }

        updateSystemStatus("Online");
        updateSensorSource(data.sensor_source || "--");
        updateRealtimeReadings(data.latest);
        updateWarnings(data.warnings || [], data.warning_status, data.warning_banner);
        updateAnalysis(data.analysis);
        updateSettingsForm(data.settings);
        updateChart(data.chart_labels || [], data.chart_values || []);
    } catch (error) {
        console.error("Fetch error:", error);
        updateSystemStatus("Offline / Error");
        showWarningBanner("error", "Failed to load monitoring data from the server.");
        renderWarnings(["Unable to retrieve warning data."]);
        updateAnalysis({
            spike_drop: "Analysis unavailable.",
            trend: "Analysis unavailable.",
            prediction: "Analysis unavailable."
        });
    }
}

/**
 * Update the system status text.
 */
function updateSystemStatus(statusText) {
    const statusEl = document.getElementById("systemStatus");
    if (statusEl) {
        statusEl.textContent = statusText;
    }
}

/**
 * Update the sensor source display.
 */
function updateSensorSource(sourceText) {
    const sourceEl = document.getElementById("sensorSource");
    if (sourceEl) {
        sourceEl.textContent = sourceText;
    }
}

/**
 * Update real-time reading cards.
 */
function updateRealtimeReadings(latest) {
    if (!latest) {
        document.getElementById("temperature").textContent = "--";
        document.getElementById("humidity").textContent = "--";
        document.getElementById("pressure").textContent = "--";
        document.getElementById("timestamp").textContent = "--";
        return;
    }

    document.getElementById("temperature").textContent = Number(latest.temperature).toFixed(2);
    document.getElementById("humidity").textContent = Number(latest.humidity).toFixed(2);
    document.getElementById("pressure").textContent = Number(latest.pressure).toFixed(2);
    document.getElementById("timestamp").textContent = latest.timestamp || "--";
}

/**
 * Update warning count, banner, and warning list.
 */
function updateWarnings(warnings, warningStatus, warningBanner) {
    const countEl = document.getElementById("warningCount");
    if (countEl) {
        countEl.textContent = warningStatus?.count ?? warnings.length ?? 0;
    }

    const level = warningStatus?.level || (warnings.length > 0 ? "warning" : "normal");
    showWarningBanner(level, warningBanner || "No warning information available.");
    renderWarnings(warnings);
}

/**
 * Render warning banner with style level.
 */
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

/**
 * Render warning list items.
 */
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

/**
 * Update analysis section.
 */
function updateAnalysis(analysis) {
    document.getElementById("spike_drop").textContent =
        analysis?.spike_drop || "No analysis available.";

    document.getElementById("trend").textContent =
        analysis?.trend || "No analysis available.";

    document.getElementById("prediction").textContent =
        analysis?.prediction || "No analysis available.";
}

/**
 * Update settings form values, unless the user is actively editing.
 */
function updateSettingsForm(settings) {
    if (!settings || isSettingsFormDirty) return;

    document.getElementById("temp_min").value = settings.temp_min ?? "";
    document.getElementById("temp_max").value = settings.temp_max ?? "";
    document.getElementById("humidity_min").value = settings.humidity_min ?? "";
    document.getElementById("humidity_max").value = settings.humidity_max ?? "";
    document.getElementById("pressure_min").value = settings.pressure_min ?? "";
    document.getElementById("pressure_max").value = settings.pressure_max ?? "";
}

/**
 * Initialize the temperature chart once.
 */
function initChart() {
    const canvas = document.getElementById("tempChart");
    if (!canvas) return;

    const ctx = canvas.getContext("2d");

    chart = new Chart(ctx, {
        type: "line",
        data: {
            labels: [],
            datasets: [{
                label: "Temperature (°C)",
                data: [],
                tension: 0.25
            }]
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

/**
 * Update chart data without destroying and recreating the chart.
 */
function updateChart(labels, values) {
    if (!chart) {
        initChart();
    }

    if (!chart) return;

    chart.data.labels = labels;
    chart.data.datasets[0].data = values;
    chart.update();
}

/**
 * Show user-facing feedback message for form actions.
 */
function showFormMessage(elementId, message, isSuccess = true) {
    const el = document.getElementById(elementId);
    if (!el) return;

    el.textContent = message;
    el.classList.remove("success", "error");
    el.classList.add(isSuccess ? "success" : "error");
}

/**
 * Submit settings form to backend.
 */
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
        const response = await fetch("/api/settings", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload)
        });

        const result = await response.json();

        if (!response.ok || !result.success) {
            throw new Error(result.message || "Failed to update settings.");
        }

        showFormMessage("settingsMessage", result.message, true);
        isSettingsFormDirty = false;
        await fetchData();
    } catch (error) {
        console.error("Settings update error:", error);
        showFormMessage("settingsMessage", error.message, false);
    }
}

/**
 * Submit manual simulated sensor data.
 */
async function handleSimulateSubmit(event) {
    event.preventDefault();

    const payload = {
        temperature: document.getElementById("sim_temperature").value,
        humidity: document.getElementById("sim_humidity").value,
        pressure: document.getElementById("sim_pressure").value
    };

    try {
        const response = await fetch("/api/simulate", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload)
        });

        const result = await response.json();

        if (!response.ok || !result.success) {
            throw new Error(result.message || "Failed to submit sensor data.");
        }

        showFormMessage("simulateMessage", result.message, true);

        document.getElementById("simulateForm").reset();
        await fetchData();
    } catch (error) {
        console.error("Simulation submit error:", error);
        showFormMessage("simulateMessage", error.message, false);
    }
}

/**
 * Mark settings form as dirty while user is editing.
 */
function trackSettingsFormChanges() {
    const settingsInputs = document.querySelectorAll("#settingsForm input");
    settingsInputs.forEach(input => {
        input.addEventListener("input", () => {
            isSettingsFormDirty = true;
        });
    });
}

/**
 * Register event listeners.
 */
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

/**
 * Initialize the dashboard.
 */
function initDashboard() {
    initChart();
    registerEventListeners();
    fetchData();
    setInterval(fetchData, 3000);
}

document.addEventListener("DOMContentLoaded", initDashboard);