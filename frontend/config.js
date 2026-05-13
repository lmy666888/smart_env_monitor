// Frontend configuration for the Smart Environment Monitoring System.
// Adjust API_ENDPOINT here if the AWS API Gateway URL changes.
window.APP_CONFIG = {
    // AWS API Gateway endpoint that returns { sensor_data: [...], settings: {...} }.
    API_ENDPOINT: "https://9jzbd9a34j.execute-api.ap-southeast-2.amazonaws.com/data",

    // How often (ms) the dashboard refetches data from the AWS endpoint.
    REFRESH_INTERVAL_MS: 5000,

    // Network timeout (ms) for each fetch request.
    FETCH_TIMEOUT_MS: 8000,

    // Max readings used for the chart (oldest -> newest).
    CHART_MAX_POINTS: 30,

    // Trend / spike thresholds (°C).
    SPIKE_THRESHOLD_C: 3.0,
    TREND_DELTA_C: 0.5,

    // Optional very basic client-side auth (matches frontend/login.html).
    // Coursework demo only — not real security.
    DEMO_USERNAME: "admin",
    DEMO_PASSWORD: "admin123",
};
