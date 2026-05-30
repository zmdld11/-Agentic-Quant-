// ── Bootstrap ───────────────────────────────────────
(function bootstrap() {
    // theme can apply immediately
    var saved = localStorage.getItem('quant-theme');
    var prefers = window.matchMedia('(prefers-color-scheme: dark)').matches;
    applyTheme(saved || (prefers ? 'dark' : 'light'));

    // async load ECharts then hide splash
    var script = document.createElement('script');
    script.src = 'https://cdn.bootcdn.net/ajax/libs/echarts/5.5.0/echarts.min.js';
    script.onload = function () {
        var splash = document.getElementById('splash');
        if (splash) splash.classList.add('done');
        // remove splash from DOM after fade
        setTimeout(function () { if (splash) splash.remove(); }, 600);
        renderHistoryList();
    };
    script.onerror = function () {
        var splash = document.getElementById('splash');
        if (splash) {
            splash.querySelector('p').textContent = 'CDN 加载失败，请刷新重试';
            splash.querySelector('.splash-bar-fill').style.animation = 'none';
            splash.querySelector('.splash-bar-fill').style.width = '100%';
        }
    };
    document.head.appendChild(script);
})();

// ── State ────────────────────────────────────────────
var currentSymbol = '';
var currentPeriod = '3m';
var klineRawData = [];

// ── ECharts (lazy init) ──────────────────────────────
var klineChart, volumeChart, macdChart, rsiChart;
var chartsReady = false;

function initCharts() {
    if (chartsReady) return;
    if (typeof echarts === 'undefined') return;
    var klineEl = document.getElementById('klineChart');
    if (!klineEl) return;
    klineChart = echarts.init(klineEl);
    volumeChart = echarts.init(document.getElementById('volumeChart'));
    macdChart = echarts.init(document.getElementById('macdChart'));
    rsiChart = echarts.init(document.getElementById('rsiChart'));
    chartsReady = true;
}

function resizeAllCharts() {
    if (!chartsReady) return;
    klineChart.resize();
    volumeChart.resize();
    macdChart.resize();
    rsiChart.resize();
}

window.addEventListener('resize', resizeAllCharts);

// ── Theme ────────────────────────────────────────────

function toggleTheme() {
    var current = document.documentElement.getAttribute('data-theme');
    applyTheme(current === 'dark' ? 'light' : 'dark');
}

function applyTheme(theme) {
    document.documentElement.setAttribute('data-theme', theme);
    var btn = document.getElementById('themeToggle');
    if (btn) btn.textContent = theme === 'dark' ? '☀️' : '🌙';
    localStorage.setItem('quant-theme', theme);
    resizeAllCharts();
}

// ── Period buttons ───────────────────────────────────
document.querySelectorAll('.period-btn').forEach(function (btn) {
    btn.addEventListener('click', function () {
        document.querySelectorAll('.period-btn').forEach(function (b) { b.classList.remove('active'); });
        this.classList.add('active');
        currentPeriod = this.dataset.period;
        if (currentSymbol) fetchKlineOnly(currentSymbol, currentPeriod);
    });
});

// ── Enter key ────────────────────────────────────────
var inputEl = document.getElementById('symbolInput');
if (inputEl) {
    inputEl.addEventListener('keydown', function (e) {
        if (e.key === 'Enter') doAnalyze();
    });
}

// ── API calls ────────────────────────────────────────
async function doAnalyze() {
    var symbol = document.getElementById('symbolInput').value.trim();
    if (!symbol || symbol.length !== 6 || !/^\d{6}$/.test(symbol)) {
        showError('请输入6位数字A股代码');
        return;
    }

    currentSymbol = symbol;
    showLoading(true);
    hideError();
    hideReport();

    try {
        var resp = await fetch('/api/analyze', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ symbol: symbol })
        });

        if (!resp.ok) {
            var err = await resp.json();
            throw new Error(err.detail || '请求失败');
        }

        var data = await resp.json();
        renderResult(data);
    } catch (e) {
        showError(e.message);
    } finally {
        showLoading(false);
    }
}

async function fetchKlineOnly(symbol, period) {
    try {
        var resp = await fetch('/api/kline/' + symbol + '?period=' + period);
        if (resp.ok) {
            var data = await resp.json();
            klineRawData = data.kline_data;
            renderAllCharts(data.kline_data);
        }
    } catch (e) {
        console.error('K线刷新失败:', e);
    }
}

// ── Render ───────────────────────────────────────────
function renderResult(data) {
    document.getElementById('stockName').textContent = data.name || data.symbol;
    document.getElementById('stockIndustry').textContent = '行业: ' + (data.industry || '未知');
    document.getElementById('stockBusiness').textContent = '主营: ' + (data.business || '未知');
    document.getElementById('stockInfo').classList.remove('hidden');

    renderQuoteCards(data.quote);

    klineRawData = data.kline_data || [];
    renderAllCharts(klineRawData);

    renderReport(data.report);

    saveToHistory(data);

    document.getElementById('klineChart').scrollIntoView({ behavior: 'smooth', block: 'start' });
}

function renderQuoteCards(quote) {
    if (!quote) return;
    var container = document.getElementById('quoteCards');
    container.classList.remove('hidden');

    var pct = quote.pct_change;
    var pctCls = pct > 0 ? 'up' : pct < 0 ? 'down' : '';

    var items = [
        { label: '收盘价', value: quote.close.toFixed(2) },
        { label: '涨跌幅', value: (pct > 0 ? '+' : '') + pct.toFixed(2) + '%', cls: pctCls },
        { label: '量比', value: quote.volume_ratio.toFixed(2) },
        { label: 'RSI(14)', value: quote.rsi_14.toFixed(1) },
        { label: 'MACD', value: quote.macd.toFixed(3) },
        { label: '波动(5日)', value: quote.volatility.toFixed(2) + '%' },
        { label: 'MA20偏离', value: (quote.ma20_bias * 100).toFixed(2) + '%' },
        { label: '数据日期', value: quote.date }
    ];

    container.innerHTML = items.map(function (i) {
        return '<div class="quote-card"><div class="label">' + i.label + '</div><div class="value ' + (i.cls || '') + '">' + i.value + '</div></div>';
    }).join('');
}

function renderAllCharts(data) {
    if (!data || data.length === 0) return;
    initCharts();
    if (!chartsReady) { console.error('ECharts not loaded'); return; }
    renderKlineChart(data);
    renderVolumeChart(data);
    renderMACDChart(data);
    renderRSIChart(data);
}

function getChartColors() {
    var style = getComputedStyle(document.documentElement);
    return {
        up: style.getPropertyValue('--up-color').trim() || '#dc2626',
        down: style.getPropertyValue('--down-color').trim() || '#16a34a',
        text: style.getPropertyValue('--text-secondary').trim() || '#999',
        border: style.getPropertyValue('--border').trim() || '#e5e7eb'
    };
}

function renderKlineChart(data) {
    var dates = data.map(function (d) { return d.date; });
    var ohlc = data.map(function (d) { return [d.open, d.close, d.low, d.high]; });
    var closes = data.map(function (d) { return d.close; });
    var colors = getChartColors();
    var ma5 = calcMA(closes, 5);
    var ma10 = calcMA(closes, 10);
    var ma20 = calcMA(closes, 20);

    klineChart.setOption({
        tooltip: { trigger: 'axis', axisPointer: { type: 'cross' } },
        grid: { left: '8%', right: '2%', top: '6%', bottom: '4%' },
        xAxis: { type: 'category', data: dates, axisLabel: { color: colors.text, fontSize: 11 }, axisLine: { lineStyle: { color: colors.border } } },
        yAxis: { type: 'value', scale: true, splitLine: { lineStyle: { color: colors.border, type: 'dashed' } }, axisLabel: { color: colors.text, fontSize: 11, formatter: function (v) { return v.toFixed(0); } } },
        series: [
            { name: 'K线', type: 'candlestick', data: ohlc, itemStyle: { color: colors.up, color0: colors.down, borderColor: colors.up, borderColor0: colors.down } },
            { name: 'MA5', type: 'line', data: ma5, symbol: 'none', smooth: true, lineStyle: { color: '#f59e0b', width: 1 } },
            { name: 'MA10', type: 'line', data: ma10, symbol: 'none', smooth: true, lineStyle: { color: '#8b5cf6', width: 1 } },
            { name: 'MA20', type: 'line', data: ma20, symbol: 'none', smooth: true, lineStyle: { color: '#ec4899', width: 1 } }
        ],
        legend: { data: ['K线', 'MA5', 'MA10', 'MA20'], bottom: 0, textStyle: { color: colors.text } }
    }, true);
}

function renderVolumeChart(data) {
    var dates = data.map(function (d) { return d.date; });
    var colors = getChartColors();

    volumeChart.setOption({
        tooltip: { trigger: 'axis' },
        grid: { left: '8%', right: '2%', top: '8%', bottom: '4%' },
        xAxis: { type: 'category', data: dates, axisLabel: { color: colors.text, fontSize: 10 }, axisLine: { lineStyle: { color: colors.border } } },
        yAxis: { type: 'value', splitLine: { lineStyle: { color: colors.border, type: 'dashed' } }, axisLabel: { color: colors.text, fontSize: 10, formatter: function (v) { return v > 1e8 ? (v / 1e8).toFixed(1) + '亿' : (v / 1e6).toFixed(0) + '万'; } } },
        series: [{
            name: '成交量', type: 'bar',
            data: data.map(function (d) {
                return { value: d.volume, itemStyle: { color: d.close >= d.open ? colors.up : colors.down, opacity: 0.7 } };
            })
        }]
    }, true);
}

function renderMACDChart(data) {
    var dates = data.map(function (d) { return d.date; });
    var closes = data.map(function (d) { return d.close; });
    var colors = getChartColors();
    var result = calcMACD(closes);
    var dif = result.dif, dea = result.dea, macd = result.macd;

    macdChart.setOption({
        tooltip: { trigger: 'axis' },
        grid: { left: '8%', right: '2%', top: '8%', bottom: '18%' },
        legend: { data: ['DIF', 'DEA', 'MACD'], bottom: 0, textStyle: { color: colors.text, fontSize: 11 } },
        xAxis: { type: 'category', data: dates, axisLabel: { color: colors.text, fontSize: 10 }, axisLine: { lineStyle: { color: colors.border } } },
        yAxis: { type: 'value', splitLine: { lineStyle: { color: colors.border, type: 'dashed' } }, axisLabel: { color: colors.text, fontSize: 10, formatter: function (v) { return v.toFixed(2); } } },
        series: [
            { name: 'DIF', type: 'line', data: dif, symbol: 'none', lineStyle: { color: '#3b82f6', width: 1.5 } },
            { name: 'DEA', type: 'line', data: dea, symbol: 'none', lineStyle: { color: '#f97316', width: 1.5 } },
            { name: 'MACD', type: 'bar', data: macd.map(function (v) { return { value: v, itemStyle: { color: v >= 0 ? colors.up : colors.down, opacity: 0.7 } }; }) }
        ]
    }, true);
}

function renderRSIChart(data) {
    var dates = data.map(function (d) { return d.date; });
    var closes = data.map(function (d) { return d.close; });
    var colors = getChartColors();
    var rsi = calcRSI(closes, 14);

    rsiChart.setOption({
        tooltip: { trigger: 'axis' },
        grid: { left: '8%', right: '2%', top: '8%', bottom: '4%' },
        xAxis: { type: 'category', data: dates, axisLabel: { color: colors.text, fontSize: 10 }, axisLine: { lineStyle: { color: colors.border } } },
        yAxis: { type: 'value', min: 0, max: 100, splitLine: { lineStyle: { color: colors.border, type: 'dashed' } }, axisLabel: { color: colors.text, fontSize: 10 } },
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
    var el = document.getElementById('report');
    var html = text
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
    html = html.replace(/<li>[\s\S]*?<\/li>/g, function (m) { return '<ul>' + m + '</ul>'; });
    html = html.replace(/<\/ul>\s*<ul>/g, '');

    el.innerHTML = html;
    el.classList.remove('hidden');
}

// ── Indicators ───────────────────────────────────────
function calcMA(data, period) {
    var result = [];
    for (var i = 0; i < period - 1; i++) result.push(null);
    for (var i = period - 1; i < data.length; i++) {
        var sum = 0;
        for (var j = 0; j < period; j++) sum += data[i - j];
        result.push(sum / period);
    }
    return result;
}

function calcMACD(closes, fast, slow, signal) {
    fast = fast || 12; slow = slow || 26; signal = signal || 9;
    var ema = function (data, period) {
        var k = 2 / (period + 1);
        var result = [];
        for (var i = 0; i < period - 1; i++) result.push(null);
        var prev = data[period - 1];
        for (var i = period - 1; i < data.length; i++) {
            prev = data[i] * k + prev * (1 - k);
            result.push(prev);
        }
        return result;
    };

    var ema12 = ema(closes, fast);
    var ema26 = ema(closes, slow);
    var dif = ema12.map(function (v, i) { return v != null && ema26[i] != null ? v - ema26[i] : null; });
    var validDif = dif.filter(function (v) { return v != null; });
    var deaRaw = ema(validDif, signal);
    var dea = [];
    for (var i = 0; i < dif.length - validDif.length; i++) dea.push(null);
    dea = dea.concat(deaRaw);
    var macd = dif.map(function (v, i) { return v != null && dea[i] != null ? (v - dea[i]) * 2 : null; });
    return { dif: dif, dea: dea, macd: macd };
}

function calcRSI(closes, period) {
    period = period || 14;
    var result = [];
    for (var i = 0; i < period; i++) result.push(null);
    var avgGain = 0, avgLoss = 0;
    for (var i = 1; i <= period; i++) {
        var delta = closes[i] - closes[i - 1];
        if (delta > 0) avgGain += delta; else avgLoss -= delta;
    }
    avgGain /= period; avgLoss /= period;
    result[period] = 100 - 100 / (1 + avgGain / Math.max(avgLoss, 1e-10));

    for (var i = period + 1; i < closes.length; i++) {
        var delta2 = closes[i] - closes[i - 1];
        var gain = delta2 > 0 ? delta2 : 0;
        var loss = delta2 < 0 ? -delta2 : 0;
        avgGain = (avgGain * (period - 1) + gain) / period;
        avgLoss = (avgLoss * (period - 1) + loss) / period;
        result[i] = 100 - 100 / (1 + avgGain / Math.max(avgLoss, 1e-10));
    }
    return result;
}

// ── Helpers ──────────────────────────────────────────
function showLoading(show) {
    document.getElementById('loading').classList.toggle('hidden', !show);
}

function showError(msg) {
    var el = document.getElementById('error');
    el.textContent = msg;
    el.classList.remove('hidden');
}

function hideError() {
    document.getElementById('error').classList.add('hidden');
}

function hideReport() {
    document.getElementById('report').classList.add('hidden');
}

// ── History ──────────────────────────────────────────
var HISTORY_KEY = 'quant-history';

function saveToHistory(data) {
    var entries = loadHistory();
    var date = new Date().toISOString().slice(0, 10);
    var snippet = (data.report || '').replace(/\*\*/g, '').slice(0, 80);

    entries.unshift({
        symbol: data.symbol,
        name: data.name,
        date: date,
        snippet: snippet,
        data: data
    });

    // deduplicate same stock + same date (keep latest)
    var seen = {};
    var deduped = [];
    for (var i = 0; i < entries.length; i++) {
        var key = entries[i].symbol + entries[i].date;
        if (seen[key]) continue;
        seen[key] = true;
        deduped.push(entries[i]);
    }
    entries = deduped;

    // keep only last 50 entries
    if (entries.length > 50) entries = entries.slice(0, 50);

    try {
        localStorage.setItem(HISTORY_KEY, JSON.stringify(entries));
    } catch (e) {
        // quota exceeded: remove oldest half
        entries = entries.slice(0, Math.floor(entries.length / 2));
        try { localStorage.setItem(HISTORY_KEY, JSON.stringify(entries)); } catch (e2) {}
    }

    renderHistoryList();
}

function loadHistory() {
    try {
        var raw = localStorage.getItem(HISTORY_KEY);
        if (!raw) return [];
        return JSON.parse(raw);
    } catch (e) { return []; }
}

function renderHistoryList() {
    var entries = loadHistory();
    var container = document.getElementById('historyList');
    if (!container) return;

    if (entries.length === 0) {
        container.innerHTML = '<div style="color:var(--text-secondary);font-size:0.78rem;text-align:center;padding:16px;">暂无历史记录</div>';
        return;
    }

    container.innerHTML = entries.map(function (e, idx) {
        return '<div class="history-item" onclick="loadHistoryEntry(' + idx + ')" title="' + e.symbol + ' ' + e.name + '">' +
            '<div class="hi-head">' +
                '<span class="hi-code">' + e.symbol + '</span>' +
                '<span class="hi-date">' + e.date + '</span>' +
            '</div>' +
            '<div class="hi-name">' + (e.name || '') + '</div>' +
            '<div class="hi-snippet">' + (e.snippet || '') + '</div>' +
        '</div>';
    }).join('');
}

function loadHistoryEntry(idx) {
    var entries = loadHistory();
    if (idx < 0 || idx >= entries.length) return;
    var data = entries[idx].data;
    if (!data) return;

    currentSymbol = data.symbol;
    document.getElementById('symbolInput').value = data.symbol;

    document.getElementById('stockName').textContent = data.name || data.symbol;
    document.getElementById('stockIndustry').textContent = '行业: ' + (data.industry || '未知');
    document.getElementById('stockBusiness').textContent = '主营: ' + (data.business || '未知');
    document.getElementById('stockInfo').classList.remove('hidden');

    renderQuoteCards(data.quote);

    klineRawData = data.kline_data || [];
    renderAllCharts(klineRawData);

    renderReport(data.report);

    document.getElementById('klineChart').scrollIntoView({ behavior: 'smooth', block: 'start' });
}

function clearAllHistory() {
    localStorage.removeItem(HISTORY_KEY);
    renderHistoryList();
}

// sidebar history loaded in bootstrap after ECharts ready
