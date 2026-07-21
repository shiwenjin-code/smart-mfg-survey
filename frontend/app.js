/**
 * 智能制造问卷 - 前端交互 v5.0
 * 全响应式 · 丝滑切换 · 6题 · 企业智能联想 · 基本信息不计入题数
 */
const API_BASE = location.origin + '/api';
const $ = s => document.querySelector(s);
const $$ = s => document.querySelectorAll(s);

let sessionId = null, selectedOption = null;
let currentQNum = 0, currentQText = '';
const TOTAL_QUESTIONS = 6;  // 6道AI选择题（基本信息不占题数）
let autocompleteTimer = null;

// ==================== 工具 ====================
function showLoading(text) { $('#loadingText').textContent = text; $('#loadingLayer').classList.add('show'); }
function hideLoading() { $('#loadingLayer').classList.remove('show'); }
function toast(msg) {
    const old = document.querySelector('.toast-msg'); if (old) old.remove();
    const el = document.createElement('div'); el.className = 'toast-msg'; el.textContent = msg;
    document.body.appendChild(el); setTimeout(() => el.remove(), 2800);
}
function esc(t) { const d = document.createElement('div'); d.textContent = t || ''; return d.innerHTML; }

// ==================== 企业名称智能联想 ====================
async function autocompleteCompany() {
    const input = $('#company');
    const dropdown = $('#companySuggestions');
    const val = (input.value || '').trim();

    if (val.length < 1) {
        dropdown.innerHTML = '';
        dropdown.classList.remove('show');
        return;
    }

    try {
        const resp = await fetch(`${API_BASE}/autocomplete/company?q=${encodeURIComponent(val)}`);
        if (!resp.ok) return;
        const data = await resp.json();
        const list = data.suggestions || [];

        if (list.length === 0) {
            dropdown.innerHTML = '<div class="autocomplete-empty">未找到匹配企业，可手动输入</div>';
        } else {
            dropdown.innerHTML = list.map(name =>
                `<div class="autocomplete-item" onclick="selectCompany('${esc(name).replace(/'/g, "\\'")}')">${esc(name)}</div>`
            ).join('');
        }
        dropdown.classList.add('show');
    } catch(e) {
        // 静默失败
    }
}

function selectCompany(name) {
    $('#company').value = name;
    $('#companySuggestions').innerHTML = '';
    $('#companySuggestions').classList.remove('show');
    // 自动聚焦到岗位输入
    setTimeout(() => $('#position').focus(), 100);
}

// 输入防抖
$('#company').addEventListener('input', function() {
    clearTimeout(autocompleteTimer);
    autocompleteTimer = setTimeout(autocompleteCompany, 200);
});
$('#company').addEventListener('focus', function() {
    if (this.value.trim().length >= 1) autocompleteCompany();
});
$('#company').addEventListener('blur', function() {
    setTimeout(() => {
        $('#companySuggestions').classList.remove('show');
    }, 200);
});

// ==================== 步骤切换 ====================
function switchStep(fromStepId, toStepId) {
    const from = $(`#${fromStepId}`), to = $(`#${toStepId}`);
    if (from) from.classList.remove('active');
    if (to) { to.classList.add('active'); to.classList.add('animate-in'); setTimeout(() => to.classList.remove('animate-in'), 500); }
}

// ==================== 进度更新 ====================
function updateProgress(current, total) {
    total = total || TOTAL_QUESTIONS;
    // current 为 0 时表示基本信息步骤
    const pct = current === 0 ? 0 : ((current) / total) * 100;
    $('#progressTrack').style.width = pct + '%';
    $$('.progress-dot').forEach(d => {
        const s = parseInt(d.dataset.step);
        d.classList.remove('done', 'current');
        if (s < current) d.classList.add('done');
        else if (s === current) d.classList.add('current');
    });
    const labels = ['', '数字化现状', '核心痛点', '投入意愿', '时间规划', '采购决策', '技术人才'];
    if (current === 0) {
        $('#progressLabel').textContent = `基本信息 · 共 ${total} 题`;
    } else {
        $('#progressLabel').textContent = `${current}/${total} · ${labels[current] || ''}`;
    }
}

// ==================== 开始调研 ====================
async function startSurvey() {
    const name = $('#name').value.trim(), company = $('#company').value.trim(), position = $('#position').value.trim();
    if (!name) { toast('请输入您的姓名'); return; }
    if (!company) { toast('请输入所属企业'); return; }
    if (!position) { toast('请输入负责岗位'); return; }

    const btn = $('#btnStart'); btn.disabled = true; btn.textContent = '正在生成题目...';
    showLoading('AI 正在为您定制问卷题目...');

    try {
        const resp = await fetch(API_BASE + '/session/start', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ name, company, position }) });
        if (!resp.ok) { const err = await resp.json(); throw new Error(err.detail || '请求失败'); }
        const data = await resp.json();
        sessionId = data.session_id;
        renderChoice(data.question_number, data.question, data.options, data.is_last);
        switchStep('step1', 'stepChoice');
        updateProgress(data.question_number);
        hideLoading();
    } catch (err) {
        hideLoading(); toast('初始化失败：' + err.message);
        btn.disabled = false; btn.textContent = '开始答题 →';
    }
}

// ==================== 渲染选择题 ====================
function renderChoice(qNum, question, options, isLast) {
    currentQNum = qNum; currentQText = question; selectedOption = null;

    $('#choiceBadge').textContent = `📋 第 ${qNum} 题 / 共 ${TOTAL_QUESTIONS} 题`;
    $('#choiceTitle').textContent = question;

    $('#optionsList').innerHTML = options.map((opt, idx) => {
        const letter = String.fromCharCode(65 + idx);
        const text = opt.replace(/^[A-D][.、\s]+/, '');
        return `<div class="option-card" data-value="${esc(opt)}" onclick="selectOpt(this,'${esc(opt)}')">
            <span class="option-letter">${letter}</span><span class="option-text">${esc(text)}</span><span class="option-check">✓</span>
        </div>`;
    }).join('');

    const btn = $('#btnSubmit');
    btn.disabled = true; btn.textContent = '请先选择一项'; btn.className = 'survey-btn btn-main';
    updateProgress(qNum);
}

function selectOpt(el, value) {
    $$('.option-card').forEach(c => c.classList.remove('selected'));
    el.classList.add('selected');
    selectedOption = value;
    const btn = $('#btnSubmit');
    btn.disabled = false;
    btn.textContent = currentQNum >= TOTAL_QUESTIONS ? '提交并查看分析 →' : '下一题 →';
    btn.className = 'survey-btn btn-main';
}

// ==================== 提交 ====================
async function submitChoice() {
    if (!selectedOption) { toast('请先选择一个选项'); return; }
    const btn = $('#btnSubmit'); btn.disabled = true; btn.textContent = '提交中...';

    if (currentQNum >= TOTAL_QUESTIONS) showLoading('AI 正在分析您的全部回答...');

    try {
        const resp = await fetch(API_BASE + '/session/answer', {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ session_id: sessionId, question_number: currentQNum, question: currentQText, answer: selectedOption })
        });
        if (!resp.ok) { const err = await resp.json(); throw new Error(err.detail || '提交失败'); }
        const data = await resp.json();

        if (data.options) {
            renderChoice(data.question_number, data.question, data.options, data.is_last);
            hideLoading();
        } else {
            renderComplete(data);
            switchStep('stepChoice', 'stepComplete');
            updateProgress(TOTAL_QUESTIONS);
            hideLoading();
        }
    } catch (err) {
        hideLoading(); toast('提交失败：' + err.message);
        btn.disabled = false; btn.textContent = '请先选择一项';
    }
}

// ==================== 完成页 ====================
function renderComplete(data) {
    // 线索评级
    const lvl = data.lead_level || '普通';
    const score = data.lead_score || 50;
    const colors = { '高优': '#dc2626', '中优': '#d97706', '普通': '#64748b' };
    const color = colors[lvl] || '#64748b';
    $('#leadBadge').style.background = color;
    $('#leadBadge').textContent = `🎯 线索: ${lvl} · ${score}分`;

    // 问答回顾
    if (data.qa_list?.length) {
        const html = data.qa_list.map(q => `<div class="qa-row"><div class="q">Q${q.question_number}: ${esc(q.question)}</div><div class="a">👉 ${esc(q.answer)}</div></div>`).join('');
        $('#qaReview').innerHTML = `<h4>📋 您的回答</h4><div class="qa-list">${html}</div>`;
    }

    // 企业画像
    const painHtml = (data.pain_points || []).map(p => `<span class="pain-tag">${esc(p)}</span>`).join('');
    $('#analysisSummary').innerHTML = `
        <div class="text">${esc(data.summary || '分析完成')}</div>
        ${painHtml ? '<div class="pain-tags">'+painHtml+'</div>' : ''}
        ${data.follow_up_advice ? '<div class="advice">📝 '+esc(data.follow_up_advice)+'</div>' : ''}
    `;

    // 洞察
    if (data.insights?.length) {
        const icons = ['💡', '🔍', '📌', '🎯', '✨', '📊', '⚡', '🔥'];
        const items = data.insights.map((t, i) => `<div class="insight-row"><span class="dot">${icons[i % icons.length]}</span><span>${esc(t)}</span></div>`).join('');
        $('#insightList').innerHTML = `<h4>🔎 关键洞察与建议</h4>${items}`;
    }
}

// ==================== 初始化 ====================
updateProgress(0);