// ── Bootstrap ───────────────────────────────────────
(function bootstrap() {
    var saved = localStorage.getItem('quant-theme');
    var prefers = window.matchMedia('(prefers-color-scheme: dark)').matches;
    applyTheme(saved || (prefers ? 'dark' : 'light'));
    var script = document.createElement('script');
    script.src = 'https://cdn.bootcdn.net/ajax/libs/echarts/5.5.0/echarts.min.js';
    script.onload = function () {
        var splash = document.getElementById('splash');
        if (splash) splash.classList.add('done');
        setTimeout(function () { if (splash) splash.remove(); }, 600);
        renderHistoryList();
    };
    script.onerror = function () {
        var splash = document.getElementById('splash');
        if (splash) { splash.querySelector('p').textContent = 'CDN 加载失败，请刷新重试'; }
    };
    document.head.appendChild(script);
})();

// ── State ────────────────────────────────────────────
var activeTab = 'home';
var singleState = 'init'; // init | loaded
var currentSymbol = '';
var currentPeriod = '3m';
var klineRawData = [];
var newsDateOffset = 0;

// ── ECharts ──────────────────────────────────────────
var klineChart, volumeChart, macdChart, rsiChart;
var overlayChart, scatterChart;
var chartsReady = false;

function initCharts() {
    if (chartsReady) return;
    if (typeof echarts === 'undefined') return;
    var containers = {
        kline: document.getElementById('klineChart'),
        volume: document.getElementById('volumeChart'),
        macd: document.getElementById('macdChart'),
        rsi: document.getElementById('rsiChart'),
        overlay: document.getElementById('overlayChart'),
        scatter: document.getElementById('scatterChart')
    };
    // Single-stock charts (init only when visible)
    if (containers.kline && containers.kline.offsetParent) {
        klineChart = echarts.init(containers.kline);
        volumeChart = echarts.init(containers.volume);
        macdChart = echarts.init(containers.macd);
        rsiChart = echarts.init(containers.rsi);
    }
    // Dual charts
    if (containers.overlay && containers.overlay.offsetParent) {
        overlayChart = echarts.init(containers.overlay);
        scatterChart = echarts.init(containers.scatter);
    }
    chartsReady = true;
}

function resizeAllCharts() {
    [klineChart, volumeChart, macdChart, rsiChart, overlayChart, scatterChart].forEach(function (c) {
        if (c) c.resize();
    });
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

// ── Tab / Page Navigation ────────────────────────────
function goHome() { switchTab('home'); }
var singleResultShown = false;
function switchTab(tab) {
    activeTab = tab;
    var header = document.getElementById('appHeader');
    ['Home', 'Single', 'Dual', 'News'].forEach(function (t) {
        var el = document.getElementById('page' + t);
        if (el) el.classList.toggle('hidden', t.toLowerCase() !== tab);
    });
    if (tab === 'home') {
        if (header) header.classList.add('hidden');
    } else {
        if (header) header.classList.remove('hidden');
        document.querySelectorAll('.tab-btn').forEach(function (b) {
            b.classList.toggle('active', b.dataset.tab === tab);
        });
    }
    // History panel visibility based on tab
    var hp = document.getElementById('historyPanel');
    if (hp) {
        if (tab === 'news') {
            hp.style.display = 'none';
        } else {
            hp.style.display = 'flex';
        }
    }
    if (tab === 'news') loadNews();
    if (tab === 'dual') { chartsReady = false; }
    if (tab === 'single' && singleState === 'init') resetSingleInit();
    renderHistoryList();
    resizeAllCharts();
}

// ── Tab button clicks ────────────────────────────────
document.querySelectorAll('.tab-btn').forEach(function (btn) {
    btn.addEventListener('click', function () { switchTab(this.dataset.tab); });
});

// ── Single: reset ────────────────────────────────────
function resetSingleInit() {
    singleState = 'init';
    var init = document.getElementById('singleInit');
    var result = document.getElementById('singleResult');
    if (init) init.classList.remove('done');
    if (result) result.classList.add('hidden');
    document.getElementById('searchError').classList.add('hidden');
    document.getElementById('symbolInput').value = '';
    document.getElementById('symbolInput2').value = '';
    hideError();
    hideReport();
    singleResultShown = false;
}

// ── Single: search animation ─────────────────────────
function showSingleResult() {
    if (singleResultShown) return;
    singleResultShown = true;
    var init = document.getElementById('singleInit');
    var result = document.getElementById('singleResult');
    if (init) init.classList.add('done');
    if (result) result.classList.remove('hidden');
    singleState = 'loaded';
}

// ── Enter key ────────────────────────────────────────
var inputEl = document.getElementById('symbolInput');
if (inputEl) inputEl.addEventListener('keydown', function (e) { if (e.key === 'Enter') doAnalyze(); });
var inputEl2 = document.getElementById('symbolInput2');
if (inputEl2) inputEl2.addEventListener('keydown', function (e) { if (e.key === 'Enter') doAnalyze(); });
var dualA = document.getElementById('dualInputA');
if (dualA) dualA.addEventListener('keydown', function (e) { if (e.key === 'Enter') doDualSync(); });
var dualB = document.getElementById('dualInputB');
if (dualB) dualB.addEventListener('keydown', function (e) { if (e.key === 'Enter') doDualSync(); });

// ── Period buttons ───────────────────────────────────
document.querySelectorAll('.period-btn').forEach(function (btn) {
    btn.addEventListener('click', function () {
        document.querySelectorAll('.period-btn').forEach(function (b) { b.classList.remove('active'); });
        this.classList.add('active');
        currentPeriod = this.dataset.period;
        if (currentSymbol) fetchKlineOnly(currentSymbol, currentPeriod);
    });
});

// ── Do Analyze ───────────────────────────────────────
async function doAnalyze() {
    var inp = singleState === 'init' ? document.getElementById('symbolInput') : document.getElementById('symbolInput2');
    if (!inp) return;
    var symbol = inp.value.trim();
    if (!symbol || symbol.length !== 6 || !/^\d{6}$/.test(symbol)) {
        showError('请输入6位数字A股代码');
        return;
    }
    currentSymbol = symbol;
    showLoading(true);
    hideError();
    hideReport();
    // Immediately add history entry with fetching status
    saveToHistory({symbol: symbol, name: '', report: null}, 'fetching', '数据获取中...', null);
    try {
        var resp = await fetch('/api/analyze', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ symbol: symbol })
        });
        if (!resp.ok) { var err = await resp.json(); throw new Error(err.detail || '请求失败'); }
        var data = await resp.json();
        showSingleResult();
        renderResult(data);
        // Save to history with reporting status (report not ready yet)
        var dataSummary = data.data_summary || null;
        saveToHistory(data, 'reporting', 'AI推演中...', dataSummary);
        // Call report API separately
        try {
            var reportResp = await fetch('/api/report', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ symbol: symbol, data_summary: dataSummary })
            });
            if (!reportResp.ok) throw new Error('报告生成失败');
            var reportData = await reportResp.json();
            renderReport(reportData.report);
            var snippet = (reportData.report || '').replace(/\*\*/g, '').slice(0, 80);
            updateHistoryEntry(symbol, { status: 'done', snippet: snippet });
        } catch (reportErr) {
            showError(reportErr.message);
            updateHistoryEntry(symbol, { status: 'error', snippet: reportErr.message });
        }
    } catch (e) {
        if (singleState === 'init') {
            var errEl = document.getElementById('searchError');
            errEl.textContent = e.message;
            errEl.classList.remove('hidden');
        } else {
            showError(e.message);
        }
    } finally { showLoading(false); }
}

async function fetchKlineOnly(symbol, period) {
    try {
        var resp = await fetch('/api/kline/' + symbol + '?period=' + period);
        if (resp.ok) {
            var data = await resp.json();
            klineRawData = data.kline_data;
            var visible = data.display_bars || data.kline_data.length;
            renderAllCharts(data.kline_data, visible);
        }
    } catch (e) { console.error(e); }
}

// ── Render Single Result ─────────────────────────────
function renderResult(data) {
    document.getElementById('stockName').textContent = data.name || data.symbol;
    document.getElementById('stockIndustry').textContent = '行业: ' + (data.industry || '未知');
    document.getElementById('stockBusiness').textContent = '主营: ' + (data.business || '未知');
    document.getElementById('stockInfo').classList.remove('hidden');
    renderQuoteCards(data.quote);
    klineRawData = data.kline_data || [];
    var analyzeVisible = {"1m": 22, "3m": 60, "6m": 60, "1y": 60};
    renderAllCharts(klineRawData, analyzeVisible[currentPeriod] || 60);
    document.getElementById('klineChart').scrollIntoView({ behavior: 'smooth', block: 'start' });
}

function renderQuoteCards(quote) {
    if (!quote) return;
    var c = document.getElementById('quoteCards');
    c.classList.remove('hidden');
    var pct = quote.pct_change;
    var cls = pct > 0 ? 'up' : pct < 0 ? 'down' : '';
    var items = [
        { l: '收盘价', v: quote.close.toFixed(2) },
        { l: '涨跌幅', v: (pct > 0 ? '+' : '') + pct.toFixed(2) + '%', c: cls },
        { l: '量比', v: quote.volume_ratio.toFixed(2) },
        { l: 'RSI(14)', v: quote.rsi_14.toFixed(1) },
        { l: 'MACD', v: quote.macd.toFixed(3) },
        { l: '波动(5日)', v: quote.volatility.toFixed(2) + '%' },
        { l: 'MA20偏离', v: (quote.ma20_bias * 100).toFixed(2) + '%' },
        { l: '数据日期', v: quote.date }
    ];
    c.innerHTML = items.map(function (i) {
        return '<div class="quote-card"><div class="label">' + i.l + '</div><div class="value ' + (i.c || '') + '">' + i.v + '</div></div>';
    }).join('');
}

// ── Render Charts ────────────────────────────────────
function renderAllCharts(data, visible) {
    if (!data || data.length === 0) return;
    initCharts();
    if (!chartsReady || !klineChart) return;
    if (!visible) visible = data.length;
    renderKlineChart(data, visible);
    renderVolumeChart(data, visible);
    renderMACDChart(data, visible);
    renderRSIChart(data, visible);
}
function getCC() {
    var s = getComputedStyle(document.documentElement);
    return { up: s.getPropertyValue('--up-color').trim() || '#dc2626', down: s.getPropertyValue('--down-color').trim() || '#16a34a', text: s.getPropertyValue('--text-secondary').trim() || '#999', border: s.getPropertyValue('--border').trim() || '#e5e7eb' };
}
function renderKlineChart(data, visible) {
    var sliced = data.slice(-visible);
    var allCloses = data.map(function (d) { return d.close; });
    var dates = sliced.map(function (d) { return d.date; });
    var ohlc = sliced.map(function (d) { return [d.open, d.close, d.low, d.high]; });
    var c = getCC();
    var showMa5 = calcMA(allCloses, 5).slice(-visible);
    var showMa10 = calcMA(allCloses, 10).slice(-visible);
    var showMa20 = calcMA(allCloses, 20).slice(-visible);
    klineChart.setOption({
        tooltip: { trigger: 'axis', axisPointer: { type: 'cross' } },
        grid: { left: '8%', right: '2%', top: '8%', bottom: '8%' },
        xAxis: { type: 'category', data: dates, axisLabel: { color: c.text, fontSize: 10, rotate: visible > 60 ? 45 : 0 } },
        yAxis: { type: 'value', scale: true, splitLine: { lineStyle: { color: c.border, type: 'dashed' } }, axisLabel: { color: c.text, fontSize: 11, formatter: function (v) { return v.toFixed(0); } } },
        series: [
            { name: 'K线', type: 'candlestick', data: ohlc, itemStyle: { color: c.up, color0: c.down, borderColor: c.up, borderColor0: c.down } },
            { name: 'MA5', type: 'line', data: showMa5, symbol: 'none', smooth: true, lineStyle: { color: '#f59e0b', width: 1 } },
            { name: 'MA10', type: 'line', data: showMa10, symbol: 'none', smooth: true, lineStyle: { color: '#8b5cf6', width: 1 } },
            { name: 'MA20', type: 'line', data: showMa20, symbol: 'none', smooth: true, lineStyle: { color: '#ec4899', width: 1 } }
        ],
        legend: { data: ['K线', 'MA5', 'MA10', 'MA20'], top: 0, textStyle: { color: c.text, fontSize: 11 } }
    }, true);
}
function renderVolumeChart(data, visible) {
    var sliced = data.slice(-visible);
    var dates = sliced.map(function (d) { return d.date; });
    var c = getCC();
    volumeChart.setOption({
        tooltip: { trigger: 'axis' },
        grid: { left: '8%', right: '2%', top: '8%', bottom: '4%' },
        xAxis: { type: 'category', data: dates, axisLabel: { color: c.text, fontSize: 10 } },
        yAxis: { type: 'value', splitLine: { lineStyle: { color: c.border, type: 'dashed' } }, axisLabel: { color: c.text, fontSize: 10, formatter: function (v) { return v > 1e8 ? (v / 1e8).toFixed(1) + '亿' : (v / 1e6).toFixed(0) + '万'; } } },
        series: [{ name: '成交量', type: 'bar', data: sliced.map(function (d) { return { value: d.volume, itemStyle: { color: d.close >= d.open ? c.up : c.down, opacity: 0.7 } }; }) }]
    }, true);
}
function renderMACDChart(data, visible) {
    var allDates = data.map(function (d) { return d.date; });
    var allCloses = data.map(function (d) { return d.close; });
    var c = getCC();
    var r = calcMACD(allCloses);
    var dif = r.dif.slice(-visible), dea = r.dea.slice(-visible), macd = r.macd.slice(-visible);
    var dates = allDates.slice(-visible);
    macdChart.setOption({
        tooltip: { trigger: 'axis' },
        grid: { left: '8%', right: '2%', top: '8%', bottom: '18%' },
        legend: { data: ['DIF', 'DEA', 'MACD'], bottom: 0, textStyle: { color: c.text, fontSize: 11 } },
        xAxis: { type: 'category', data: dates, axisLabel: { color: c.text, fontSize: 10 } },
        yAxis: { type: 'value', splitLine: { lineStyle: { color: c.border, type: 'dashed' } }, axisLabel: { color: c.text, fontSize: 10, formatter: function (v) { return v.toFixed(2); } } },
        series: [
            { name: 'DIF', type: 'line', data: dif, symbol: 'none', lineStyle: { color: '#3b82f6', width: 1.5 } },
            { name: 'DEA', type: 'line', data: dea, symbol: 'none', lineStyle: { color: '#f97316', width: 1.5 } },
            { name: 'MACD', type: 'bar', data: macd.map(function (v) { return { value: v, itemStyle: { color: (v != null && v >= 0) ? c.up : c.down, opacity: 0.7 } }; }) }
        ]
    }, true);
}
function renderRSIChart(data, visible) {
    var allDates = data.map(function (d) { return d.date; });
    var allCloses = data.map(function (d) { return d.close; });
    var c = getCC();
    var rsi = calcRSI(allCloses, 14).slice(-visible);
    var dates = allDates.slice(-visible);
    rsiChart.setOption({
        tooltip: { trigger: 'axis' },
        grid: { left: '8%', right: '2%', top: '8%', bottom: '4%' },
        xAxis: { type: 'category', data: dates, axisLabel: { color: c.text, fontSize: 10 } },
        yAxis: { type: 'value', min: 0, max: 100, splitLine: { lineStyle: { color: c.border, type: 'dashed' } }, axisLabel: { color: c.text, fontSize: 10 } },
        series: [{
            name: 'RSI(14)', type: 'line', data: rsi, symbol: 'none', lineStyle: { color: '#a855f7', width: 1.5 },
            markLine: { silent: true, symbol: 'none', lineStyle: { type: 'dashed', width: 1 }, data: [{ yAxis: 70, label: { formatter: '70', color: c.text, fontSize: 10 }, lineStyle: { color: '#f97316' } }, { yAxis: 30, label: { formatter: '30', color: c.text, fontSize: 10 }, lineStyle: { color: '#3b82f6' } }] }
        }]
    }, true);
}

// ── Dual Sync ────────────────────────────────────────
async function doDualSync() {
    var a = document.getElementById('dualInputA').value.trim();
    var b = document.getElementById('dualInputB').value.trim();
    if (!a || !b || a.length !== 6 || b.length !== 6 || !/^\d{6}$/.test(a) || !/^\d{6}$/.test(b)) {
        document.getElementById('dualError').textContent = '请输入两个有效的6位A股代码';
        document.getElementById('dualError').classList.remove('hidden');
        return;
    }
    document.getElementById('dualError').classList.add('hidden');
    document.getElementById('dualLoading').classList.remove('hidden');
    document.getElementById('dualResult').classList.add('hidden');
    try {
        var resp = await fetch('/api/sync', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ symbol_a: a, symbol_b: b })
        });
        if (!resp.ok) { var err = await resp.json(); throw new Error(err.detail); }
        var data = await resp.json();
        renderDualResult(data);
    } catch (e) {
        document.getElementById('dualError').textContent = e.message;
        document.getElementById('dualError').classList.remove('hidden');
    } finally {
        document.getElementById('dualLoading').classList.add('hidden');
    }
}
function renderDualResult(data) {
    document.getElementById('dualPearson').textContent = data.pearson;
    document.getElementById('dualLevel').textContent = data.sync_level;
    document.getElementById('dualDays').textContent = data.common_days + ' 天';
    document.getElementById('dualResult').classList.remove('hidden');
    saveDualToHistory(data);
    // Init dual charts
    if (overlayChart) { overlayChart.dispose(); }
    if (scatterChart) { scatterChart.dispose(); }
    overlayChart = echarts.init(document.getElementById('overlayChart'));
    scatterChart = echarts.init(document.getElementById('scatterChart'));
    chartsReady = true;
    var c = getCC();
    // Overlay chart
    var dates = data.overlay.map(function (d) { return d.date; });
    var aVals = data.overlay.map(function (d) { return d.norm_a; });
    var bVals = data.overlay.map(function (d) { return d.norm_b; });
    overlayChart.setOption({
        tooltip: { trigger: 'axis' },
        grid: { left: '8%', right: '2%', top: '8%', bottom: '4%' },
        legend: { data: [data.symbol_a, data.symbol_b], top: 0, textStyle: { color: c.text } },
        xAxis: { type: 'category', data: dates, axisLabel: { color: c.text, fontSize: 10 } },
        yAxis: { type: 'value', name: '归一化价格', axisLabel: { color: c.text, fontSize: 10 } },
        series: [
            { name: data.symbol_a, type: 'line', data: aVals, symbol: 'none', lineStyle: { color: '#3b82f6', width: 1.5 } },
            { name: data.symbol_b, type: 'line', data: bVals, symbol: 'none', lineStyle: { color: '#f97316', width: 1.5 } }
        ]
    }, true);
    // Scatter chart
    var scatterData = data.scatter.map(function (d) { return [d.x, d.y]; });
    scatterChart.setOption({
        tooltip: { trigger: 'item', formatter: function (p) { return data.symbol_a + ': ' + p.value[0].toFixed(2) + '<br>' + data.symbol_b + ': ' + p.value[1].toFixed(2); } },
        grid: { left: '10%', right: '4%', top: '8%', bottom: '8%' },
        xAxis: { type: 'value', name: data.symbol_a + ' 价格', axisLabel: { color: c.text, fontSize: 10 } },
        yAxis: { type: 'value', name: data.symbol_b + ' 价格', axisLabel: { color: c.text, fontSize: 10 } },
        series: [{ type: 'scatter', data: scatterData, symbolSize: 4, itemStyle: { color: '#8b5cf6', opacity: 0.6 } }]
    }, true);
}

// ── News ─────────────────────────────────────────────
function changeNewsDate(delta) { newsDateOffset += delta; loadNews(); }
function loadNews() {
    var d = new Date();
    d.setDate(d.getDate() + newsDateOffset);
    var ds = d.toISOString().slice(0, 10);
    document.getElementById('newsDate').textContent = ds;
    document.getElementById('newsLoading').classList.remove('hidden');
    document.getElementById('newsError').classList.add('hidden');
    document.getElementById('newsContent').innerHTML = '';
    fetch('/api/news?date=' + ds)
        .then(function (r) { if (!r.ok) throw new Error('加载失败'); return r.json(); })
        .then(function (data) { renderNews(data); })
        .catch(function (e) { document.getElementById('newsError').textContent = e.message; document.getElementById('newsError').classList.remove('hidden'); })
        .finally(function () { document.getElementById('newsLoading').classList.add('hidden'); });
}
function renderNews(data) {
    var el = document.getElementById('newsContent');
    var sections = [
        { key: 'macro', title: '全球宏观' },
        { key: 'stock_specific', title: '市场快讯' }
    ];
    var html = '';
    sections.forEach(function (sec) {
        var items = data[sec.key] || [];
        html += '<div class="news-category"><div class="news-cat-title">' + sec.title + '</div>';
        if (items.length === 0) {
            html += '<div class="news-empty">暂无数据</div>';
        } else {
            var isMacro = sec.key === 'macro';
            items.forEach(function (item) {
                var title = item.title || '';
                var time = item.time || '';
                if (isMacro) {
                    // Global macro: plain list, no collapsible
                    html += '<div class="news-item">';
                    html += '<span class="news-item-title-text">' + escapeHtml(title) + '</span>';
                    if (time) html += '<span class="news-item-time">' + escapeHtml(time) + '</span>';
                    html += '</div>';
                } else {
                    // Market news: collapsible with 【title】+ body
                    var match = title.match(/^(【[^】]+】)(.*)$/);
                    var headPart = title;
                    var bodyPart = '';
                    if (match) {
                        headPart = match[1];
                        bodyPart = match[2].trim();
                    } else {
                        headPart = title;
                        bodyPart = '';
                    }
                    var hasBody = bodyPart.length > 0;
                    html += '<div class="news-item' + (hasBody ? '' : '') + '"' + (hasBody ? ' onclick="this.classList.toggle(\'open\')"' : '') + '>';
                    html += '<div class="news-item-head">';
                    html += '<span class="news-item-title-text">' + escapeHtml(headPart) + '</span>';
                    if (time) html += '<span class="news-item-time">' + escapeHtml(time) + '</span>';
                    if (hasBody) html += '<span class="news-item-expand">▼</span>';
                    html += '</div>';
                    if (hasBody) {
                        html += '<div class="news-item-body">' + escapeHtml(bodyPart) + '</div>';
                    }
                    html += '</div>';
                }
            });
        }
        html += '</div>';
    });
    el.innerHTML = html;
}
function escapeHtml(s) { return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;'); }

// ── Report rendering ─────────────────────────────────
function renderReport(text) {
    if (!text) return;
    var el = document.getElementById('report');
    var html = text
        .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
        .replace(/^---+$/gm, '<hr>')
        .replace(/^#### (.+)$/gm, '<h4>$1</h4>')
        .replace(/^### (.+)$/gm, '<h3>$1</h3>')
        .replace(/^## (.+)$/gm, '<h2>$1</h2>')
        .replace(/^# (.+)$/gm, '<h1>$1</h1>')
        .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
        .replace(/^- (.+)$/gm, '<li>$1</li>')
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
    var r = []; for (var i = 0; i < period - 1; i++) r.push(null);
    for (var i = period - 1; i < data.length; i++) { var s = 0; for (var j = 0; j < period; j++) s += data[i - j]; r.push(s / period); }
    return r;
}
function calcMACD(closes, fast, slow, signal) {
    fast = fast || 12; slow = slow || 26; signal = signal || 9;
    var ema = function (d, p) {
        var k = 2 / (p + 1), r = [];
        for (var i = 0; i < p - 1; i++) r.push(null);
        var prev = d[p - 1];
        for (var i = p - 1; i < d.length; i++) { prev = d[i] * k + prev * (1 - k); r.push(prev); }
        return r;
    };
    var e12 = ema(closes, fast), e26 = ema(closes, slow);
    var dif = e12.map(function (v, i) { return v != null && e26[i] != null ? v - e26[i] : null; });
    var vd = dif.filter(function (v) { return v != null; });
    var deaRaw = ema(vd, signal), dea = [];
    for (var i = 0; i < dif.length - vd.length; i++) dea.push(null);
    dea = dea.concat(deaRaw);
    var macd = dif.map(function (v, i) { return v != null && dea[i] != null ? (v - dea[i]) * 2 : null; });
    return { dif: dif, dea: dea, macd: macd };
}
function calcRSI(closes, period) {
    period = period || 14; var r = []; for (var i = 0; i < period; i++) r.push(null);
    var ag = 0, al = 0;
    for (var i = 1; i <= period; i++) { var d = closes[i] - closes[i - 1]; if (d > 0) ag += d; else al -= d; }
    ag /= period; al /= period;
    r[period] = 100 - 100 / (1 + ag / Math.max(al, 1e-10));
    for (var i = period + 1; i < closes.length; i++) {
        var d2 = closes[i] - closes[i - 1], g = d2 > 0 ? d2 : 0, l = d2 < 0 ? -d2 : 0;
        ag = (ag * (period - 1) + g) / period; al = (al * (period - 1) + l) / period;
        r[i] = 100 - 100 / (1 + ag / Math.max(al, 1e-10));
    }
    return r;
}

// ── History ──────────────────────────────────────────
function getHistoryKey() {
    if (activeTab === 'dual') return 'quant-history-dual';
    return 'quant-history-single';
}
function saveToHistory(data, status, snippet, dataSummary) {
    var entries = loadHistory();
    var ds = new Date().toISOString().slice(0, 10);
    var entrySnippet = snippet || (data && data.report ? data.report.replace(/\*\*/g, '').slice(0, 80) : '');
    entries.unshift({
        symbol: data.symbol,
        name: data.name,
        date: ds,
        snippet: entrySnippet,
        status: status || 'done',
        data: data,
        data_summary: dataSummary || null
    });
    var seen = {};
    entries = entries.filter(function (e) { var k = e.symbol + e.date; if (seen[k]) return false; seen[k] = true; return true; });
    if (entries.length > 50) entries = entries.slice(0, 50);
    try { localStorage.setItem(getHistoryKey(), JSON.stringify(entries)); } catch (e) {}
    renderHistoryList();
}
function saveDualToHistory(data) {
    var entries = loadHistory();
    var ds = new Date().toISOString().slice(0, 10);
    var snippet = 'Pearson: ' + data.pearson + ', ' + data.sync_level;
    entries.unshift({
        symbol: data.symbol_a + '/' + data.symbol_b,
        name: (data.name_a || '') + ' vs ' + (data.name_b || ''),
        date: ds,
        snippet: snippet,
        status: 'done',
        data: data,
        data_summary: null
    });
    var seen = {};
    entries = entries.filter(function (e) { var k = e.symbol + e.date; if (seen[k]) return false; seen[k] = true; return true; });
    if (entries.length > 50) entries = entries.slice(0, 50);
    try { localStorage.setItem(getHistoryKey(), JSON.stringify(entries)); } catch (e) {}
    renderHistoryList();
}
function updateHistoryEntry(symbol, updates) {
    var entries = loadHistory();
    for (var i = 0; i < entries.length; i++) {
        if (entries[i].symbol === symbol && entries[i].status !== 'done') {
            for (var k in updates) { if (updates.hasOwnProperty(k)) entries[i][k] = updates[k]; }
            break;
        }
    }
    try { localStorage.setItem(getHistoryKey(), JSON.stringify(entries)); } catch (e) {}
    renderHistoryList();
}
function loadHistory() { try { var r = localStorage.getItem(getHistoryKey()); return r ? JSON.parse(r) : []; } catch (e) { return []; } }
function renderHistoryList() {
    var entries = loadHistory(), container = document.getElementById('historyList');
    if (!container) return;
    var titleEl = document.querySelector('.history-body h3');
    if (titleEl) {
        if (activeTab === 'dual') titleEl.textContent = '双股同步历史';
        else titleEl.textContent = '单股查询历史';
    }
    if (entries.length === 0) { container.innerHTML = '<div style="color:var(--text-secondary);font-size:0.78rem;text-align:center;padding:16px;">暂无历史记录</div>'; return; }
    container.innerHTML = entries.map(function (e, i) {
        var statusHtml = e.status ? '<span class="hi-status ' + e.status + '">' + (e.status === 'reporting' ? 'AI推演中...' : e.status === 'fetching' ? '数据获取中' : e.status === 'done' ? '完成' : '异常') + '</span>' : '';
        var snippetHtml = '';
        if (e.status === 'done' && e.snippet) {
            snippetHtml = '<div class="hi-snippet">' + escapeHtml(e.snippet) + '</div>';
        } else if (!e.status || e.status === 'done') {
            snippetHtml = '<div class="hi-snippet">' + escapeHtml(e.snippet || '') + '</div>';
        }
        var nameHtml = e.name ? '<div class="hi-name">' + escapeHtml(e.name) + '</div>' : '';
        var dateHtml = e.date ? '<div class="hi-date">' + escapeHtml(e.date) + '</div>' : '';
        return '<div class="history-item" onclick="loadHistoryEntry(' + i + ')">'
            + '<div class="hi-head">'
            + statusHtml
            + '<span class="hi-code">' + escapeHtml(e.symbol || '') + '</span>'
            + '<button class="hi-delete" onclick="event.stopPropagation();deleteHistoryEntry(' + i + ')" title="删除">&times;</button>'
            + '</div>'
            + dateHtml
            + nameHtml
            + snippetHtml
            + '</div>';
    }).join('');
}
function loadHistoryEntry(idx) {
    var entries = loadHistory();
    if (idx < 0 || idx >= entries.length) return;
    var data = entries[idx].data; if (!data) return;
    // Dual sync entry
    if (data.symbol_a) {
        switchTab('dual');
        document.getElementById('dualInputA').value = data.symbol_a;
        document.getElementById('dualInputB').value = data.symbol_b;
        renderDualResult(data);
        return;
    }
    // Single stock entry
    currentSymbol = data.symbol;
    switchTab('single');
    document.getElementById('symbolInput').value = data.symbol;
    document.getElementById('symbolInput2').value = data.symbol;
    showSingleResult();
    renderResult(data);
    if (data.report) {
        renderReport(data.report);
    }
}
function clearAllHistory() { localStorage.removeItem(getHistoryKey()); renderHistoryList(); }
function deleteHistoryEntry(idx) {
    var entries = loadHistory();
    entries.splice(idx, 1);
    localStorage.setItem(getHistoryKey(), JSON.stringify(entries));
    renderHistoryList();
}

// ── Helpers ──────────────────────────────────────────
function showLoading(s) { document.getElementById('loading').classList.toggle('hidden', !s); }
function showError(m) { var e = document.getElementById('error'); if (e) { e.textContent = m; e.classList.remove('hidden'); } }
function hideError() { var e = document.getElementById('error'); if (e) e.classList.add('hidden'); }
function hideReport() { var e = document.getElementById('report'); if (e) e.classList.add('hidden'); }
