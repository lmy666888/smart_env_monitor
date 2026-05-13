/*
 * Smart Environment Monitoring System - Frontend Logic
 *
 * Responsibilities:
 *  - Fetch sensor data + thresholds from the AWS API Gateway endpoint.
 *  - Sort/validate the returned readings.
 *  - Compute warnings and trend analysis on the client side.
 *  - Render the dashboard (latest values, warnings, analysis, chart).
 *  - Handle empty / network / parse error states gracefully.
 */

// Pull the API endpoint and refresh interval from config.js (loaded first).
const CONFIG = window.APP_CONFIG || {};
const API_ENDPOINT = CONFIG.API_ENDPOINT;
const REFRESH_INTERVAL_MS = CONFIG.REFRESH_INTERVAL_MS || 5000;
const FETCH_TIMEOUT_MS = CONFIG.FETCH_TIMEOUT_MS || 8000;
const CHART_MAX_POINTS = CONFIG.CHART_MAX_POINTS || 30;
const SPIKE_THRESHOLD_C = CONFIG.SPIKE_THRESHOLD_C ?? 3.0;
const TREND_DELTA_C = CONFIG.TREND_DELTA_C ?? 0.5;

// Chart.js instance is created once on init.
let chart = null;

// Cache the most recent successful payload so transient errors don't blank the UI.
let lastGoodPayload = null;

// ----------------------------------------------------------------------------
// Tiny DOM helpers
// ----------------------------------------------------------------------------

function $(id) {
    return document.getElementById(id);
}

function setText(id, value) {
    const el = $(id);
    if (el) el.textContent = (value === null || value === undefined || value === "") ? "--" : String(value);
}

function formatNumber(value, decimals = 2) {
    const num = Number(value);
    if (!Number.isFinite(num)) return "--";
    return num.toFixed(decimals);
}

function formatTimestamp(ts) {
    if (!ts) return "--";
    // The API returns ISO-like timestamps (e.g. 2026-05-13T15:50:42.803254).
    // Try to render in local time; fall back to the raw string if it cannot be parsed.
    const d = new Date(ts);
    if (Number.isNaN(d.getTime())) return String(ts);
    return d.toLocaleString();
}

// ----------------------------------------------------------------------------
// Networking
// ----------------------------------------------------------------------------

/**
 * fetchSensorData()
 *
 * Calls the AWS API endpoint with a timeout and returns the parsed JSON
 * payload. Throws on network failure, non-2xx response, or invalid JSON.
 */
async function fetchSensorData() {
    if (!API_ENDPOINT) {
        throw new Error("API endpoint is not configured (check config.js).");
    }

    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), FETCH_TIMEOUT_MS);

    try {
        const response = await fetch(API_ENDPOINT, {
            method: "GET",
            cache: "no-store",
            signal: controller.signal,
        });

        if (!response.ok) {
            throw new Error(`API responded with HTTP ${response.status}.`);
        }

        const data = await response.json();
        if (!data || typeof data !== "object") {
            throw new Error("API returned an unexpected response shape.");
        }
        return data;
    } catch (err) {
        if (err.name === "AbortError") {
            throw new Error(`Network timeout after ${FETCH_TIMEOUT_MS} ms.`);
        }
        throw err;
    } finally {
        clearTimeout(timer);
    }
}

// ----------------------------------------------------------------------------
// Validation & data shaping
// ----------------------------------------------------------------------------

/**
 * validateSensorReading(reading)
 *
 * Returns true if the reading has numeric temperature/humidity/pressure values
 * within sensible physical ranges. Used to filter the AWS payload.
 */
function validateSensorReading(reading) {
    if (!reading || typeof reading !== "object") return false;

    const temperature = Number(reading.temperature);
    const humidity = Number(reading.humidity);
    const pressure = Number(reading.pressure);

    if (!Number.isFinite(temperature) || !Number.isFinite(humidity) || !Number.isFinite(pressure)) {
        return false;
    }

    if (temperature < -50 || temperature > 100) return false;
    if (humidity < 0 || humidity > 100) return false;
    if (pressure < 300 || pressure > 1200) return false;

    return true;
}

/**
 * sortReadingsByTimestamp(readings)
 *
 * Returns a new array sorted oldest -> newest by timestamp. Readings without
 * parseable timestamps fall back to their original order (placed last).
 */
function sortReadingsByTimestamp(readings) {
    return readings.slice().sort((a, b) => {
        const ta = new Date(a.timestamp).getTime();
        const tb = new Date(b.timestamp).getTime();
        const va = Number.isNaN(ta) ? Number.POSITIVE_INFINITY : ta;
        const vb = Number.isNaN(tb) ? Number.POSITIVE_INFINITY : tb;
        return va - vb;
    });
}

/**
 * getLatestReading(readings)
 *
 * Given a chronological array (oldest -> newest), returns the last element
 * (most recent reading), or null if none.
 */
function getLatestReading(readings) {
    if (!Array.isArray(readings) || readings.length === 0) return null;
    return readings[readings.length - 1];
}

// ----------------------------------------------------------------------------
// Warnings
// ----------------------------------------------------------------------------

/**
 * generateWarnings(latest, settings)
 *
 * Returns an array of human-readable warning strings based on whether the
 * latest reading is outside the configured min/max thresholds. Returns an
 * empty array if all values are within range.
 */
function generateWarnings(latest, settings) {
    const warnings = [];
    if (!latest || !settings) return warnings;

    const temperature = Number(latest.temperature);
    const humidity = Number(latest.humidity);
    const pressure = Number(latest.pressure);

    const tempMin = Number(settings.temp_min);
    const tempMax = Number(settings.temp_max);
    const humMin = Number(settings.humidity_min);
    const humMax = Number(settings.humidity_max);
    const presMin = Number(settings.pressure_min);
    const presMax = Number(settings.pressure_max);

    if (Number.isFinite(temperature) && Number.isFinite(tempMin) && Number.isFinite(tempMax)) {
        if (temperature < tempMin) {
            warnings.push(`Temperature too low (${temperature.toFixed(2)}°C, min ${tempMin}°C).`);
        } else if (temperature > tempMax) {
            warnings.push(`Temperature too high (${temperature.toFixed(2)}°C, max ${tempMax}°C).`);
        }
    }

    if (Number.isFinite(humidity) && Number.isFinite(humMin) && Number.isFinite(humMax)) {
        if (humidity < humMin) {
            warnings.push(`Humidity too low (${humidity.toFixed(2)}%, min ${humMin}%).`);
        } else if (humidity > humMax) {
            warnings.push(`Humidity too high (${humidity.toFixed(2)}%, max ${humMax}%).`);
        }
    }

    if (Number.isFinite(pressure) && Number.isFinite(presMin) && Number.isFinite(presMax)) {
        if (pressure < presMin) {
            warnings.push(`Pressure too low (${pressure.toFixed(2)} hPa, min ${presMin} hPa).`);
        } else if (pressure > presMax) {
            warnings.push(`Pressure too high (${pressure.toFixed(2)} hPa, max ${presMax} hPa).`);
        }
    }

    return warnings;
}

// ----------------------------------------------------------------------------
// Trend analysis
// ----------------------------------------------------------------------------

/**
 * analyzeTemperatureTrend(readings)
 *
 * Inspects the chronological array of temperature readings and returns:
 *   { spike_drop: string, trend: string, summary: string }
 * Uses a simple ±SPIKE_THRESHOLD_C between the latest two readings for
 * spike/drop detection, and the slope across the recent window for trend.
 */
function analyzeTemperatureTrend(readings) {
    const out = {
        spike_drop: "Not enough data to detect a spike or drop.",
        trend: "Not enough data to detect a trend.",
        summary: "Awaiting more sensor readings.",
    };

    if (!Array.isArray(readings) || readings.length < 2) {
        return out;
    }

    const temps = readings
        .map(r => Number(r.temperature))
        .filter(t => Number.isFinite(t));

    if (temps.length < 2) return out;

    const latest = temps[temps.length - 1];
    const previous = temps[temps.length - 2];
    const delta = latest - previous;

    // Spike / drop based on the most recent pair.
    if (delta > SPIKE_THRESHOLD_C) {
        out.spike_drop = `Temperature spike: +${delta.toFixed(2)}°C since previous reading.`;
    } else if (delta < -SPIKE_THRESHOLD_C) {
        out.spike_drop = `Temperature drop: ${delta.toFixed(2)}°C since previous reading.`;
    } else {
        out.spike_drop = `No spike/drop (Δ ${delta >= 0 ? "+" : ""}${delta.toFixed(2)}°C).`;
    }

    // Overall trend across the available window.
    const first = temps[0];
    const last = temps[temps.length - 1];
    const totalChange = last - first;

    if (totalChange > TREND_DELTA_C) {
        out.trend = `Increasing trend (+${totalChange.toFixed(2)}°C over ${temps.length} readings).`;
    } else if (totalChange < -TREND_DELTA_C) {
        out.trend = `Decreasing trend (${totalChange.toFixed(2)}°C over ${temps.length} readings).`;
    } else {
        out.trend = `Stable trend (Δ ${totalChange >= 0 ? "+" : ""}${totalChange.toFixed(2)}°C across ${temps.length} readings).`;
    }

    const minTemp = Math.min(...temps);
    const maxTemp = Math.max(...temps);
    out.summary = `Last ${temps.length} readings ranged from ${minTemp.toFixed(2)}°C to ${maxTemp.toFixed(2)}°C.`;

    return out;
}

// ----------------------------------------------------------------------------
// Chart data prep + rendering
// ----------------------------------------------------------------------------

/**
 * prepareChartData(readings)
 *
 * Trims the chronological array to CHART_MAX_POINTS and returns:
 *   { labels: string[], temperature: number[], humidity: number[], pressure: number[] }
 */
function prepareChartData(readings) {
    const safe = Array.isArray(readings) ? readings.slice(-CHART_MAX_POINTS) : [];

    const labels = safe.map(r => {
        const d = new Date(r.timestamp);
        if (Number.isNaN(d.getTime())) return String(r.timestamp || "");
        // Compact HH:MM:SS for readability on the x-axis.
        return d.toLocaleTimeString();
    });

    return {
        labels,
        temperature: safe.map(r => Number(r.temperature)),
        humidity: safe.map(r => Number(r.humidity)),
        pressure: safe.map(r => Number(r.pressure)),
    };
}

function initChart() {
    const canvas = $("tempChart");
    if (!canvas || typeof Chart === "undefined") return;

    const ctx = canvas.getContext("2d");
    chart = new Chart(ctx, {
        type: "line",
        data: {
            labels: [],
            datasets: [
                {
                    label: "Temperature (°C)",
                    data: [],
                    borderColor: "#ef4444",
                    backgroundColor: "rgba(239,68,68,0.12)",
                    yAxisID: "y",
                    tension: 0.25,
                },
                {
                    label: "Humidity (%)",
                    data: [],
                    borderColor: "#2563eb",
                    backgroundColor: "rgba(37,99,235,0.10)",
                    yAxisID: "y",
                    tension: 0.25,
                },
                {
                    label: "Pressure (hPa)",
                    data: [],
                    borderColor: "#10b981",
                    backgroundColor: "rgba(16,185,129,0.10)",
                    yAxisID: "y1",
                    tension: 0.25,
                },
            ],
        },
        options: {
            responsive: true,
            maintainAspectRatio: true,
            animation: false,
            interaction: { mode: "index", intersect: false },
            plugins: {
                legend: { display: true },
                tooltip: { enabled: true },
            },
            scales: {
                x: {
                    title: { display: true, text: "Timestamp" },
                    ticks: { maxRotation: 0, autoSkip: true, maxTicksLimit: 8 },
                },
                y: {
                    position: "left",
                    title: { display: true, text: "Temperature (°C) / Humidity (%)" },
                },
                y1: {
                    position: "right",
                    title: { display: true, text: "Pressure (hPa)" },
                    grid: { drawOnChartArea: false },
                },
            },
        },
    });
}

/**
 * updateChart(chartData)
 *
 * Pushes new labels/series into the existing Chart.js instance. Safe to call
 * with 0, 1, or many readings — Chart.js handles short series without crashing.
 */
function updateChart(chartData) {
    if (!chart) initChart();
    if (!chart) return;

    chart.data.labels = chartData.labels;
    chart.data.datasets[0].data = chartData.temperature;
    chart.data.datasets[1].data = chartData.humidity;
    chart.data.datasets[2].data = chartData.pressure;
    chart.update();
}

// ----------------------------------------------------------------------------
// Dashboard rendering
// ----------------------------------------------------------------------------

function renderBanner(level, message) {
    const banner = $("warningBanner");
    if (!banner) return;
    banner.classList.remove("normal", "warning", "error");
    banner.classList.add(level);
    banner.textContent = message;
}

function renderWarningList(warnings) {
    const list = $("warnings");
    if (!list) return;

    list.innerHTML = "";
    if (!warnings || warnings.length === 0) {
        const li = document.createElement("li");
        li.className = "normal";
        li.textContent = "All readings are within normal ranges.";
        list.appendChild(li);
        return;
    }
    warnings.forEach(text => {
        const li = document.createElement("li");
        li.textContent = text;
        list.appendChild(li);
    });
}

function renderThresholds(settings) {
    if (!settings) {
        setText("thresholdTemp", "--");
        setText("thresholdHumidity", "--");
        setText("thresholdPressure", "--");
        return;
    }
    setText("thresholdTemp", `${settings.temp_min} – ${settings.temp_max} °C`);
    setText("thresholdHumidity", `${settings.humidity_min} – ${settings.humidity_max} %`);
    setText("thresholdPressure", `${settings.pressure_min} – ${settings.pressure_max} hPa`);
}

function renderDatasetInfo(readings) {
    setText("readingsCount", readings.length);
    if (readings.length > 0) {
        setText("latestTimestamp", formatTimestamp(readings[readings.length - 1].timestamp));
        setText("earliestTimestamp", formatTimestamp(readings[0].timestamp));
    } else {
        setText("latestTimestamp", "--");
        setText("earliestTimestamp", "--");
    }
}

/**
 * updateDashboard(payload)
 *
 * Top-level renderer. Accepts the raw API payload, drives every section of
 * the dashboard, and is safe to call with degraded data (e.g. missing
 * settings or empty sensor_data array).
 */
function updateDashboard(payload) {
    const rawReadings = Array.isArray(payload?.sensor_data) ? payload.sensor_data : [];
    const settings = (payload && typeof payload.settings === "object") ? payload.settings : null;

    // Filter out invalid readings, then sort chronologically.
    const cleaned = rawReadings.filter(validateSensorReading);
    const readings = sortReadingsByTimestamp(cleaned);

    const latest = getLatestReading(readings);

    // Latest reading cards.
    if (latest) {
        setText("temperature", formatNumber(latest.temperature, 2));
        setText("humidity", formatNumber(latest.humidity, 2));
        setText("pressure", formatNumber(latest.pressure, 2));
        setText("timestamp", formatTimestamp(latest.timestamp));
        setText("deviceId", latest.device_id || "--");
    } else {
        setText("temperature", "--");
        setText("humidity", "--");
        setText("pressure", "--");
        setText("timestamp", "--");
        setText("deviceId", "--");
    }

    // Warnings + banner.
    const warnings = generateWarnings(latest, settings);
    setText("warningCount", warnings.length);
    renderWarningList(warnings);

    if (!latest) {
        renderBanner("error", "No sensor readings available from the API.");
    } else if (!settings) {
        renderBanner("warning", "Sensor data received but threshold settings are missing.");
    } else if (warnings.length === 0) {
        renderBanner("normal", "All readings are within normal ranges.");
    } else {
        renderBanner("warning", `${warnings.length} warning(s): ${warnings.join(" | ")}`);
    }

    // Thresholds card.
    renderThresholds(settings);

    // Dataset info.
    renderDatasetInfo(readings);

    // Trend analysis.
    const analysis = analyzeTemperatureTrend(readings);
    setText("spike_drop", analysis.spike_drop);
    setText("trend", analysis.trend);
    setText("prediction", analysis.summary);

    // Chart.
    const chartData = prepareChartData(readings);
    updateChart(chartData);
}

// ----------------------------------------------------------------------------
// Loading / refresh loop
// ----------------------------------------------------------------------------

async function refreshDashboard() {
    setText("systemStatus", "Refreshing...");
    try {
        const payload = await fetchSensorData();
        lastGoodPayload = payload;
        updateDashboard(payload);
        setText("systemStatus", "Online");
        setText("lastUpdateTime", new Date().toLocaleString());
        setText("fetchStatus", "OK");
    } catch (err) {
        console.error("Dashboard refresh failed:", err);
        setText("systemStatus", "Offline / Error");
        setText("fetchStatus", err.message || "Error");

        if (lastGoodPayload) {
            // Keep last known good data on screen but flag the connection issue.
            renderBanner("error", `Live update failed: ${err.message}. Showing last known data.`);
        } else {
            renderBanner("error", `Failed to load sensor data: ${err.message}`);
            renderWarningList(["Unable to retrieve sensor data from the API."]);
            setText("temperature", "--");
            setText("humidity", "--");
            setText("pressure", "--");
            setText("timestamp", "--");
            setText("deviceId", "--");
            setText("warningCount", 0);
            setText("readingsCount", 0);
            setText("latestTimestamp", "--");
            setText("earliestTimestamp", "--");
            setText("spike_drop", "No analysis available.");
            setText("trend", "No analysis available.");
            setText("prediction", "No analysis available.");
            renderThresholds(null);
            updateChart({ labels: [], temperature: [], humidity: [], pressure: [] });
        }
    }
}

// ----------------------------------------------------------------------------
// Logout + init
// ----------------------------------------------------------------------------

function setupLogout() {
    const btn = $("logoutBtn");
    if (!btn) return;
    btn.addEventListener("click", function (event) {
        event.preventDefault();
        try {
            sessionStorage.removeItem("sem_logged_in");
            sessionStorage.removeItem("sem_username");
        } catch (_) {
            /* ignore */
        }
        window.location.href = "login.html";
    });
}

function setupUserChip() {
    const usernameLabel = $("usernameLabel");
    if (!usernameLabel) return;
    let username = "admin";
    try {
        username = sessionStorage.getItem("sem_username") || "admin";
    } catch (_) {
        /* ignore */
    }
    usernameLabel.textContent = username;
}

function initDashboard() {
    initChart();
    setupLogout();
    setupUserChip();

    // Kick off an immediate fetch + schedule periodic refresh.
    refreshDashboard();
    setInterval(refreshDashboard, REFRESH_INTERVAL_MS);
}

document.addEventListener("DOMContentLoaded", initDashboard);
