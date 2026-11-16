// 星语铭 - 个人主页 JavaScript

// ==================== 评论系统配置 ====================
const COMMENT_CONFIG = {
    system: 'utterances',
    utterances: {
        repo: 'zhch223/engrave',
        issueTerm: 'url',
        label: 'comment',
        theme: 'github-light'
    }
};

// 获取URL参数
function getUrlParam(param) {
    const urlParams = new URLSearchParams(window.location.search);
    const value = urlParams.get(param);
    console.log('getUrlParam:', param, value);  // 调试
    return value;
}

// 获取人物ID
function getProfileId() {
    const profileId = getUrlParam('id') || getUrlParam('name');
    const result = profileId ? profileId.replace(/\s+/g, '-') : '';
    console.log('getProfileId:', result);  // 调试
    return result;
}

// 渲染评论区域
function renderCommentsSection() {
    const profileId = getProfileId();

    if (!COMMENT_CONFIG.utterances.repo) {
        return `
            <section class="memories-section" id="commentsSection">
                <h2 style="text-align: center; margin-bottom: 2rem;">回忆与祝福</h2>
                <div style="text-align: center; padding: 2rem;">
                    <p style="color: var(--text-light); margin-bottom: 1.5rem;">暂无回忆</p>
                    <p style="color: var(--text-light); font-size: 0.9rem;">请联系管理员配置评论系统</p>
                </div>
            </section>
        `;
    }

    return `
        <section class="memories-section" id="commentsSection">
            <h2 style="text-align: center; margin-bottom: 2rem;">回忆与祝福</h2>
            <div id="utterances-container"></div>
        </section>
    `;
}

// 加载 Utterances 脚本
function loadUtterances() {
    const container = document.getElementById('utterances-container');
    if (!container) return;

    const config = COMMENT_CONFIG.utterances;

    const script = document.createElement('script');
    script.src = 'https://utteranc.es/client.js';
    script.setAttribute('repo', config.repo);
    script.setAttribute('issue-term', config.issueTerm);
    script.setAttribute('label', config.label);
    script.setAttribute('theme', config.theme);
    script.setAttribute('crossorigin', 'anonymous');
    script.async = true;

    container.appendChild(script);
}

// ==================== 页面渲染 ====================

// 加载个人资料
async function loadProfile() {
    const profileId = getProfileId();
    console.log('loadProfile, profileId:', profileId);  // 调试

    if (!profileId) {
        showError('未指定人物');
        return;
    }

    try {
        // 加载基本信息
        const infoUrl = `/data/people/${profileId}/info.json`;
        console.log('Fetching:', infoUrl);  // 调试
        const infoResponse = await fetch(infoUrl);
        console.log('Response status:', infoResponse.status);  // 调试

        if (!infoResponse.ok) {
            showError('未找到该纪念人物: ' + profileId);
            return;
        }
        const profile = await infoResponse.json();

        // 尝试加载生平介绍
        let bio = '';
        try {
            const bioUrl = `/data/people/${profileId}/bio.md`;
            console.log('Fetching bio:', bioUrl);  // 调试
            const bioResponse = await fetch(bioUrl);
            if (bioResponse.ok) {
                bio = await bioResponse.text();
            }
        } catch (e) {
            console.log('无生平介绍');
        }

        await renderProfile(profile, bio);
    } catch (error) {
        console.error('加载人物数据失败:', error);
        showError('加载失败，请稍后重试');
    }
}

// 渲染个人资料页面
async function renderProfile(profile, bio) {
    document.getElementById('pageTitle').textContent = `${profile.name} - 星语铭`;

    let ageText = profile.age || '';
    if (profile.birthDate && profile.passDate && !profile.age) {
        ageText = calculateAge(profile.birthDate, profile.passDate);
    }

    // 头像路径
    const avatar = `/data/people/${profile.id}/avatar.jpg`;

    // 网站链接
    let websiteLinks = '';
    if (profile.websites && Array.isArray(profile.websites) && profile.websites.length > 0) {
        const linksHtml = profile.websites.map(link => {
            return link.replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2" target="_blank" style="color: var(--sky-blue); margin: 0 0.5rem;">$1</a>');
        }).join(' ');
        websiteLinks = `<div class="profile-info-item"><strong>链接：</strong>${linksHtml}</div>`;
    }

    // 引用资料链接
    let sourceLinks = '';
    if (profile.sources && Array.isArray(profile.sources) && profile.sources.length > 0) {
        const linksHtml = profile.sources.map(link => {
            return link.replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2" target="_blank" style="color: var(--sky-blue); margin: 0 0.5rem;">$1</a>');
        }).join(' ');
        sourceLinks = `<div class="profile-info-item"><strong>引用资料：</strong>${linksHtml}</div>`;
    }

    const content = document.getElementById('profileContent');
    content.innerHTML = `
        <section class="profile-header">
            <img src="${avatar}" alt="${profile.name}" class="profile-avatar-large" 
                 onerror="this.src='/images/default-avatar.svg'">
            <h1>${profile.name}</h1>
            <p style="color: var(--text-light); font-size: 1.2rem;">${profile.handle || ''}</p>
            
            <div class="profile-info">
                ${profile.aliases ? `<div class="profile-info-item"><strong>别名：</strong>${profile.aliases}</div>` : ''}
                ${profile.location ? `<div class="profile-info-item"><strong>地点：</strong>${profile.location}</div>` : ''}
                <div class="profile-info-item">
                    <strong>出生日期：</strong>${profile.birthDate || '不详'}
                </div>
                <div class="profile-info-item">
                    <strong>已离开：</strong>${profile.passDate || '不详'}
                </div>
                ${ageText ? `<div class="profile-info-item"><strong>年龄：</strong>${ageText}</div>` : ''}
                ${websiteLinks}
                ${sourceLinks}
            </div>
        </section>

        <section class="profile-bio-section">
            <h2 style="text-align: center; margin-bottom: 2rem;">生平介绍</h2>
            <div style="line-height: 1.8;">${parseMarkdown(bio)}</div>
        </section>

        ${renderCommentsSection()}

        <section class="prevention-section">
            <h3>🌟 心理支持与援助资源</h3>
            <p>如果您正在经历困难时期，请记住您不是一个人。以下资源可以为您提供帮助：</p>
            <div class="prevention-resources">
                <div class="resource-card">
                    <h4>📞 援助热线</h4>
                    <p>全国心理援助热线：<strong>400-161-9995</strong></p>
                    <p>北京心理危机研究与干预中心：<strong>800-810-1117</strong></p>
                </div>
                <div class="resource-card">
                    <h4>🏥 专业支持</h4>
                    <p>请及时就医，寻求专业心理咨询师或医生的帮助</p>
                </div>
                <div class="resource-card">
                    <h4>👥 社区陪伴</h4>
                    <p>联系当地心理健康中心或社区服务中心</p>
                </div>
            </div>
        </section>
    `;

    // 加载 Utterances 评论
    loadUtterances();
}

// 计算年龄
function calculateAge(birthDate, passDate) {
    try {
        const birth = new Date(birthDate);
        const pass = new Date(passDate);

        if (isNaN(birth.getTime()) || isNaN(pass.getTime())) {
            return '';
        }

        let age = pass.getFullYear() - birth.getFullYear();
        const monthDiff = pass.getMonth() - birth.getMonth();

        if (monthDiff < 0 || (monthDiff === 0 && pass.getDate() < birth.getDate())) {
            age--;
        }

        return age > 0 ? `${age}岁` : '';
    } catch (e) {
        return '';
    }
}

// 使用 marked.js 解析 Markdown（GitHub 风格）
function parseMarkdown(text) {
    if (!text) return '';

    // 配置 marked（更接近 GitHub 渲染）
    marked.setOptions({
        breaks: true,           // 允许换行
        gfm: true,              // GitHub 风格 Markdown
        headerIds: true,        // 添加标题 ID
        mangle: false,          // 不转义邮件链接
        linkTarget: '_blank',   // 链接新窗口打开
        pedantic: false,        // 不严格遵循原始 Markdown
        smartLists: true,       // 智能列表
        smartypants: false      // 不使用排版引号
    });

    // 解析并消毒 HTML
    const html = marked.parse(text);
    return DOMPurify.sanitize(html, {
        ADD_ATTR: ['target'],   // 允许 target 属性
        ADD_TAGS: ['iframe'],   // 允许 iframe
        FORCE_BODY: true        // 强制解析为完整 HTML
    });
}

// 显示错误
function showError(message) {
    const content = document.getElementById('profileContent');
    document.getElementById('pageTitle').textContent = '错误 - 星语铭';
    content.innerHTML = `
        <div class="error-container">
            <h1>404</h1>
            <p>${message}</p>
            <a href="/" class="btn">返回首页</a>
        </div>
    `;
}

// 页面加载完成后执行
document.addEventListener('DOMContentLoaded', loadProfile);
