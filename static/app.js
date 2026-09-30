/** Mini Device Fleet Monitor – Operator Dashboard */

const POLL_INTERVAL_MS = 2500;

const $totalCount   = document.getElementById("total-count");
const $onlineCount  = document.getElementById("online-count");
const $offlineCount = document.getElementById("offline-count");
const $tbody        = document.getElementById("device-tbody");
const $statusMsg    = document.getElementById("status-msg");
const $lastRefresh  = document.getElementById("last-refresh");
const $filterBtns   = document.querySelectorAll(".filter-btn");

let currentFilter = "ALL"; // ALL, ONLINE, OFFLINE

// Click events for filter buttons
$filterBtns.forEach(btn => {
    btn.addEventListener("click", () => {
        $filterBtns.forEach(b => b.classList.remove("active"));
        btn.classList.add("active");
        currentFilter = btn.dataset.filter;
        fetchFleetData();
    });
});

// Click summary cards to filter
document.getElementById("card-total")?.addEventListener("click", () => setFilter("ALL"));
document.getElementById("card-online")?.addEventListener("click", () => setFilter("ONLINE"));
document.getElementById("card-offline")?.addEventListener("click", () => setFilter("OFFLINE"));

function setFilter(filter) {
    currentFilter = filter;
    $filterBtns.forEach(b => {
        b.classList.toggle("active", b.dataset.filter === filter);
    });
    fetchFleetData();
}

function formatElapsed(seconds) {
    if (seconds === null || seconds === undefined) return "Never";
    const s = Math.round(seconds);
    if (s < 0) return "0 sec ago";
    if (s < 60) return `${s} sec ago`;
    const m = Math.floor(s / 60);
    return `${m}m ${s % 60}s ago`;
}

function showError(msg) {
    $statusMsg.textContent = msg;
    $statusMsg.className = "status-msg error";
}

function hideError() {
    $statusMsg.className = "status-msg hidden";
    $statusMsg.textContent = "";
}

function renderSummary(summary) {
    $totalCount.textContent   = summary.total;
    $onlineCount.textContent  = summary.online;
    $offlineCount.textContent = summary.offline;
}

function renderDevices(devices) {
    if (devices.length === 0) {
        const msg = currentFilter === "ALL"
            ? "No devices registered yet. Run <code>python simulator.py</code> in a terminal to connect devices."
            : `No ${currentFilter} devices found.`;
        $tbody.innerHTML = `<tr><td colspan="5" class="center">${msg}</td></tr>`;
        return;
    }

    $tbody.innerHTML = devices.map(d => {
        const badgeClass = d.status === "ONLINE" ? "badge-online" : "badge-offline";
        const cpuText = d.cpu_usage !== null && d.cpu_usage !== undefined
            ? `<span class="metric-pill">${d.cpu_usage}%</span>`
            : "—";
        const sigText = d.signal_strength !== null && d.signal_strength !== undefined
            ? `<span class="metric-pill">${d.signal_strength} dBm</span>`
            : "—";

        return `<tr>
            <td><strong>${escapeHtml(d.name)}</strong> <small style="color:#888;">(${escapeHtml(d.id)})</small></td>
            <td><span class="badge ${badgeClass}">${d.status}</span></td>
            <td>${formatElapsed(d.seconds_since_heartbeat)}</td>
            <td>${cpuText}</td>
            <td>${sigText}</td>
        </tr>`;
    }).join("");
}

function escapeHtml(text) {
    if (!text) return "";
    const div = document.createElement("div");
    div.textContent = text;
    return div.innerHTML;
}

async function fetchFleetData() {
    try {
        const devUrl = currentFilter === "ALL" ? "/devices" : `/devices?status=${currentFilter}`;
        const [devicesResp, summaryResp] = await Promise.all([
            fetch(devUrl),
            fetch("/summary"),
        ]);

        if (!devicesResp.ok) throw new Error(`Devices error: HTTP ${devicesResp.status}`);
        if (!summaryResp.ok) throw new Error(`Summary error: HTTP ${summaryResp.status}`);

        const devices = await devicesResp.json();
        const summary = await summaryResp.json();

        hideError();
        renderSummary(summary);
        renderDevices(devices);
        $lastRefresh.textContent = `Last poll: ${new Date().toLocaleTimeString()}`;
    } catch (err) {
        showError(`Cannot connect to server: ${err.message}`);
    }
}

// Initial fetch + background polling
fetchFleetData();
setInterval(fetchFleetData, POLL_INTERVAL_MS);
