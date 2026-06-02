document.addEventListener('DOMContentLoaded', () => {
    fetchSignals();
});

async function fetchSignals() {
    try {
        const response = await fetch('/api/signals/arb');
        if (!response.ok) throw new Error('Network response was not ok');
        
        const data = await response.json();
        renderTable(data.signals);
    } catch (error) {
        console.error('Error fetching signals:', error);
        document.getElementById('signals-body').innerHTML = `
            <tr>
                <td colspan="5" class="error">Failed to load data. API might be offline.</td>
            </tr>
        `;
    }
}

function renderTable(signals) {
    const tbody = document.getElementById('signals-body');
    
    if (!signals || signals.length === 0) {
        tbody.innerHTML = `<tr><td colspan="5" class="empty">No active signals found.</td></tr>`;
        return;
    }

    tbody.innerHTML = signals.map(sig => `
        <tr>
            <td>${sig.market_title}</td>
            <td>${(sig.pm_price_yes * 100).toFixed(1)}¢</td>
            <td>${(sig.tau_yes * 100).toFixed(1)}%</td>
            <td class="spread ${sig.arb_spread > 0.1 ? 'high-edge' : ''}">${(sig.arb_spread * 100).toFixed(1)}%</td>
            <td>${sig.tier_1_active ? '✅' : '⏳'}</td>
        </tr>
    `).join('');
}
