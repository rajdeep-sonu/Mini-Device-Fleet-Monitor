/** Mini Device Fleet Monitor – dashboard logic */

const POLL_INTERVAL_MS = 3000;

const $totalCount   = document.getElementById("total-count");
const $onlineCount  = document.getElementById("online-count");
const $offlineCount = document.getElementById("offline-count");
const $tbody        = document.getElementById("device-tbody");
const $statusMsg    = document.getElementById("status-msg");
const $lastRefresh  = document.getElementById("last-refresh");

function formatElapsed(seconds) {
    if (seconds === null || seconds === undefined) return "Never";
    const s = Math.round(seconds);
    if (s < 60) return `${s} sec ago`;
    const m = Math.floor(s / 60);
    return `${m} min ${s % 60} sec ago`;
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
        $tbody.innerHTML = '<tr><td colspan="3" class="center">No devices registered.</td></tr>';
        return;
    }
    $tbody.innerHTML = devices.map(d => {
        const badgeClass = d.status === "ONLINE" ? "badge-online" : "badge-offline";
        return `<tr>
            <td>${escapeHtml(d.name)}</td>
            <td><span class="badge ${badgeClass}">${d.status}</span></td>
            <td>${formatElapsed(d.seconds_since_heartbeat)}</td>
        </tr>`;
    }).join("");
}

function escapeHtml(text) {
    const div = document.createElement("div");
    div.textContent = text;
    return div.innerHTML;
}

async function fetchFleetData() {
    try {
        const [devicesResp, summaryResp] = await Promise.all([
            fetch("/devices"),
            fetch("/summary"),
        ]);
        if (!devicesResp.ok) throw new Error(`Devices: HTTP ${devicesResp.status}`);
        if (!summaryResp.ok) throw new Error(`Summary: HTTP ${summaryResp.status}`);

        const devices = await devicesResp.json();
        const summary = await summaryResp.json();

        hideError();
        renderSummary(summary);
        renderDevices(devices);
        $lastRefresh.textContent = `Last refreshed: ${new Date().toLocaleTimeString()}`;
    } catch (err) {
        showError(`Unable to reach server: ${err.message}`);
    }
}

// Initial fetch + polling
fetchFleetData();
setInterval(fetchFleetData, POLL_INTERVAL_MS);
