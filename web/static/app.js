let currentSymbol = '';
let currentPeriod = '3m';
let klineRawData = [];
let currentQuote = null;

// ── Theme ──────────────────────────────────────────────
(function initTheme() {
    const saved = localStorage.getItem('quant-theme');
    const prefers = window.matchMedia('(prefers-color-scheme: dark)').matches;
    const theme = saved || (prefers ? 'dark' : 'light');
    applyTheme(theme);
})();

function toggleTheme() {
    const current = document.documentElement.getAttribute('data-theme');
    applyTheme(current === 'dark' ? 'light' : 'dark');
}

function applyTheme(theme) {
    document.documentElement.setAttribute('data-theme', theme);
    document.getElementById('themeToggle').textContent = theme === 'dark' ? '☀️' : '🌙';
    localStorage.setItem('quant-theme', theme);
    resizeAllCharts();
}

// ── ECharts init ───────────────────────────────────────
const klineChart = echarts.init(document.getElementById('klineChart'));
const volumeChart = echarts.init(document.getElementById('volumeChart'));
const macdChart = echarts.init(document.getElementById('macdChart'));
const rsiChart = echarts.init(document.getElementById('rsiChart'));

window.addEventListener('resize', resizeAllCharts);

function resizeAllCharts() {
    klineChart.resize();
    volumeChart.resize();
    macdChart.resize();
    rsiChart.resize();
}

// ── Period buttons ─────────────────────────────────────
document.querySelectorAll('.period-btn').forEach(btn => {
    btn.addEventListener('click', function () {
        document.querySelectorAll('.period-btn').forEach(b => b.classList.remove('active'));
        this.classList.add('active');
        currentPeriod = this.dataset.period;
        if (currentSymbol) fetchKlineOnly(currentSymbol, currentPeriod);
    });
});

// ── Enter key ──────────────────────────────────────────
document.getElementById('symbolInput').addEventListener('keydown', function (e) {
    if (e.key === 'Enter') doAnalyze();
});

// ── Analyze ────────────────────────────────────────────
async function doAnalyze() {
    const symbol = document.getElementById('symbolInput').value.trim();
    if (!symbol || symbol.length !== 6 || !/^\d{6}$/.test(symbol)) {
        showError('请输入6位数字A股代码');
        return;
    }

    currentSymbol = symbol;
    showLoading(true);
    hideError();
    hideReport();

    try {
        const resp = await fetch('/api/analyze', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ symbol })
        });

        if (!resp.ok) {
            const err = await resp.json();
            throw new Error(err.detail || '请求失败，请稍后重试');
        }

        const data = await resp.json();
        renderResult(data);
    } catch (e) {
        showError(e.message);
    } finally {
        showLoading(false);
    }
}

async function fetchKlineOnly(symbol, period) {
    try {
        const resp = await fetch(`/api/kline/${symbol}?period=${period}`);
        if (resp.ok) {
            const data = await resp.json();
            klineRawData = data.kline_data;
            renderAllCharts(data.kline_data);
        }
    } catch (e) {
        console.error('K线数据刷新失败:', e);
    }
}

// ── Render ─────────────────────────────────────────────
function renderResult(data) {
    document.getElementById('stockName').textContent = data.name || data.symbol;
    document.getElementById('stockIndustry').textContent = '行业: ' + (data.industry || '未知');
    document.getElementById('stockBusiness').textContent = '主营: ' + (data.business || '未知');
    document.getElementById('stockInfo').classList.remove('hidden');

    currentQuote = data.quote;
    renderQuoteCards(data.quote);

    klineRawData = data.kline_data || [];
    renderAllCharts(klineRawData);

    renderReport(data.report);

    // scroll to charts
    document.getElementById('klineChart').scrollIntoView({ behavior: 'smooth', block: 'start' });
}

function renderQuoteCards(quote) {
    if (!quote) return;
    const container = document.getElementById('quoteCards');
    container.classList.remove('hidden');

    const pct = quote.pct_change;
    const pctCls = pct > 0 ? 'up' : pct < 0 ? 'down' : '';

    const items = [
        { label: '收盘价', value: quote.close.toFixed(2) },
        { label: '涨跌幅', value: (pct > 0 ? '+' : '') + pct.toFixed(2) + '%', cls: pctCls },
        { label: '量比', value: quote.volume_ratio.toFixed(2) },
        { label: 'RSI(14)', value: quote.rsi_14.toFixed(1) },
        { label: 'MACD', value: quote.macd.toFixed(3) },
        { label: '波动(5日)', value: quote.volatility.toFixed(2) + '%' },
        { label: 'MA20偏离', value: (quote.ma20_bias * 100).toFixed(2) + '%' },
        { label: '数据日期', value: quote.date }
    ];

    container.innerHTML = items.map(i =>
        `<div class="quote-card">
            <div class="label">${i.label}</div>
            <div class="value ${i.cls || ''}">${i.value}</div>
        </div>`
    ).join('');
}

function renderAllCharts(data) {
    if (!data || data.length === 0) return;
    renderKlineChart(data);
    renderVolumeChart(data);
    renderMACDChart(data);
    renderRSIChart(data);
}

function getChartColors() {
    const style = getComputedStyle(document.documentElement);
    return {
        up: style.getPropertyValue('--up-color').trim() || '#dc2626',
        down: style.getPropertyValue('--down-color').trim() || '#16a34a',
        text: style.getPropertyValue('--text-secondary').trim() || '#999',
        border: style.getPropertyValue('--border').trim() || '#e5e7eb',
        accent: style.getPropertyValue('--accent').trim() || '#2563eb'
    };
}

function renderKlineChart(data) {
    const dates = data.map(d => d.date);
    const ohlc = data.map(d => [d.open, d.close, d.low, d.high]);
    const closes = data.map(d => d.close);
    const colors = getChartColors();

    // MA lines
    const ma5 = calcMA(closes, 5);
    const ma10 = calcMA(closes, 10);
    const ma20 = calcMA(closes, 20);

    klineChart.setOption({
        tooltip: {
            trigger: 'axis',
            axisPointer: { type: 'cross' },
            valueFormatter: v => v != null ? v.toFixed(2) : '-'
        },
        grid: { left: '8%', right: '2%', top: '6%', bottom: '4%' },
        xAxis: {
            type: 'category', data: dates,
            axisLine: { lineStyle: { color: colors.border } },
            axisLabel: { color: colors.text, fontSize: 11 }
        },
        yAxis: {
            type: 'value', scale: true,
            splitLine: { lineStyle: { color: colors.border, type: 'dashed' } },
            axisLabel: { color: colors.text, fontSize: 11, formatter: v => v.toFixed(0) }
        },
        series: [
            {
                name: 'K线', type: 'candlestick', data: ohlc,
                itemStyle: { color: colors.up, color0: colors.down, borderColor: colors.up, borderColor0: colors.down }
            },
            { name: 'MA5', type: 'line', data: ma5, symbol: 'none', smooth: true, lineStyle: { color: '#f59e0b', width: 1 } },
            { name: 'MA10', type: 'line', data: ma10, symbol: 'none', smooth: true, lineStyle: { color: '#8b5cf6', width: 1 } },
            { name: 'MA20', type: 'line', data: ma20, symbol: 'none', smooth: true, lineStyle: { color: '#ec4899', width: 1 } }
        ],
        legend: { data: ['K线', 'MA5', 'MA10', 'MA20'], bottom: 0, textStyle: { color: colors.text } }
    }, true);
}

function renderVolumeChart(data) {
    const dates = data.map(d => d.date);
    const colors = getChartColors();

    volumeChart.setOption({
        tooltip: { trigger: 'axis' },
        grid: { left: '8%', right: '2%', top: '8%', bottom: '4%' },
        xAxis: { type: 'category', data: dates, axisLabel: { color: colors.text, fontSize: 10 }, axisLine: { lineStyle: { color: colors.border } } },
        yAxis: {
            type: 'value',
            splitLine: { lineStyle: { color: colors.border, type: 'dashed' } },
            axisLabel: { color: colors.text, fontSize: 10, formatter: v => v > 1e8 ? (v / 1e8).toFixed(1) + '亿' : (v / 1e6).toFixed(0) + '万' }
        },
        series: [{
            name: '成交量', type: 'bar',
            data: data.map((d, i) => ({
                value: d.volume,
                itemStyle: { color: d.close >= d.open ? colors.up : colors.down, opacity: 0.7 }
            }))
        }]
    }, true);
}

function renderMACDChart(data) {
    const dates = data.map(d => d.date);
    const closes = data.map(d => d.close);
    const colors = getChartColors();
    const { dif, dea, macd } = calcMACD(closes);

    macdChart.setOption({
        tooltip: { trigger: 'axis' },
        grid: { left: '8%', right: '2%', top: '8%', bottom: '18%' },
        legend: { data: ['DIF', 'DEA', 'MACD'], bottom: 0, textStyle: { color: colors.text, fontSize: 11 } },
        xAxis: { type: 'category', data: dates, axisLabel: { color: colors.text, fontSize: 10 }, axisLine: { lineStyle: { color: colors.border } } },
        yAxis: { type: 'value', splitLine: { lineStyle: { color: colors.border, type: 'dashed' } }, axisLabel: { color: colors.text, fontSize: 10, formatter: v => v.toFixed(2) } },
        series: [
            { name: 'DIF', type: 'line', data: dif, symbol: 'none', lineStyle: { color: '#3b82f6', width: 1.5 } },
            { name: 'DEA', type: 'line', data: dea, symbol: 'none', lineStyle: { color: '#f97316', width: 1.5 } },
            { name: 'MACD', type: 'bar', data: macd.map((v, i) => ({ value: v, itemStyle: { color: v >= 0 ? colors.up : colors.down, opacity: 0.7 } })) }
        ]
    }, true);
}

function renderRSIChart(data) {
    const dates = data.map(d => d.date);
    const closes = data.map(d => d.close);
    const colors = getChartColors();
    const rsi = calcRSI(closes, 14);

    rsiChart.setOption({
        tooltip: { trigger: 'axis', valueFormatter: v => v != null ? v.toFixed(1) : '-' },
        grid: { left: '8%', right: '2%', top: '8%', bottom: '4%' },
        xAxis: { type: 'category', data: dates, axisLabel: { color: colors.text, fontSize: 10 }, axisLine: { lineStyle: { color: colors.border } } },
        yAxis: {
            type: 'value', min: 0, max: 100,
            splitLine: { lineStyle: { color: colors.border, type: 'dashed' } },
            axisLabel: { color: colors.text, fontSize: 10 }
        },
        series: [{
            name: 'RSI(14)', type: 'line', data: rsi, symbol: 'none',
            lineStyle: { color: '#a855f7', width: 1.5 },
            markLine: {
                silent: true, symbol: 'none',
                lineStyle: { type: 'dashed', width: 1 },
                data: [
                    { yAxis: 70, label: { formatter: '70', color: colors.text, fontSize: 10 }, lineStyle: { color: '#f97316' } },
                    { yAxis: 30, label: { formatter: '30', color: colors.text, fontSize: 10 }, lineStyle: { color: '#3b82f6' } }
                ]
            }
        }]
    }, true);
}

function renderReport(text) {
    if (!text) return;
    const el = document.getElementById('report');
    // Convert markdown-like text to HTML
    let html = text
        .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
        .replace(/^### (.+)$/gm, '<h3>$1</h3>')
        .replace(/^## (.+)$/gm, '<h2>$1</h2>')
        .replace(/^# (.+)$/gm, '<h1>$1</h1>')
        .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
        .replace(/^- (.+)$/gm, '<li>$1</li>')
        .replace(/(\d+)\.\s(.+)/g, '<li>$2</li>')
        .replace(/\n{2,}/g, '</p><p>')
        .replace(/\n/g, '<br>');

    html = '<p>' + html + '</p>';
    html = html.replace(/<li>[\s\S]*?<\/li>/g, m => '<ul>' + m + '</ul>');
    html = html.replace(/<\/ul>\s*<ul>/g, '');

    el.innerHTML = html;
    el.classList.remove('hidden');
}

// ── Indicators (JS side) ───────────────────────────────
function calcMA(data, period) {
    const result = new Array(period - 1).fill(null);
    for (let i = period - 1; i < data.length; i++) {
        let sum = 0;
        for (let j = 0; j < period; j++) sum += data[i - j];
        result.push(sum / period);
    }
    return result;
}

function calcMACD(closes, fast = 12, slow = 26, signal = 9) {
    const ema = (data, period) => {
        const k = 2 / (period + 1);
        const result = new Array(period - 1).fill(null);
        let prev = data[period - 1];
        for (let i = period - 1; i < data.length; i++) {
            prev = data[i] * k + prev * (1 - k);
            result.push(prev);
        }
        return result;
    };

    const ema12 = ema(closes, fast);
    const ema26 = ema(closes, slow);
    const dif = ema12.map((v, i) => v != null && ema26[i] != null ? v - ema26[i] : null);
    const validDif = dif.filter(v => v != null);
    const deaRaw = ema(validDif, signal);
    const dea = new Array(dif.length - validDif.length).fill(null).concat(deaRaw);
    const macd = dif.map((v, i) => v != null && dea[i] != null ? (v - dea[i]) * 2 : null);

    return { dif, dea, macd };
}

function calcRSI(closes, period = 14) {
    const result = new Array(period).fill(null);
    let avgGain = 0, avgLoss = 0;
    for (let i = 1; i <= period; i++) {
        const delta = closes[i] - closes[i - 1];
        if (delta > 0) avgGain += delta; else avgLoss -= delta;
    }
    avgGain /= period; avgLoss /= period;
    result[period] = 100 - 100 / (1 + avgGain / Math.max(avgLoss, 1e-10));

    for (let i = period + 1; i < closes.length; i++) {
        const delta = closes[i] - closes[i - 1];
        const gain = delta > 0 ? delta : 0;
        const loss = delta < 0 ? -delta : 0;
        avgGain = (avgGain * (period - 1) + gain) / period;
        avgLoss = (avgLoss * (period - 1) + loss) / period;
        result[i] = 100 - 100 / (1 + avgGain / Math.max(avgLoss, 1e-10));
    }
    return result;
}

// ── Helpers ────────────────────────────────────────────
function showLoading(show) { document.getElementById('loading').classList.toggle('hidden', !show); }
function showError(msg) { const el = document.getElementById('error'); el.textContent = '❌ ' + msg; el.classList.remove('hidden'); }
function hideError() { document.getElementById('error').classList.add('hidden'); }
function hideReport() { document.getElementById('report').classList.add('hidden'); }
