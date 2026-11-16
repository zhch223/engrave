// 星语铭 - 本地留言系统前端（替换 utterances 评论）
// 依赖后端 API：与站点同端口（/api/messages）

(function () {
    // 前后端同端口部署（无论直连、局域网还是端口映射），API 永远走同源相对路径
    const API_BASE = '';

    // HTML 转义，防 XSS
    function esc(s) {
        return String(s == null ? '' : s)
            .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
    }

    // 注入样式
    function injectStyles() {
        if (document.getElementById('gb-style')) return;
        const css = `
        .gb-box { background: var(--pure-white, #fff); border-radius: 12px; box-shadow: 0 4px 20px var(--shadow, rgba(0,0,0,.08)); padding: 1.5rem; margin-top: 1.5rem; }
        .gb-form { display: flex; flex-direction: column; gap: .75rem; margin-bottom: 1.5rem; }
        .gb-form input, .gb-form textarea {
            border: 1px solid #d8e2f0; border-radius: 8px; padding: .6rem .8rem;
            font: inherit; font-size: .95rem; outline: none; background: #fafcff; resize: vertical;
        }
        .gb-form input:focus, .gb-form textarea:focus { border-color: var(--sky-blue, #6aa9e9); }
        .gb-form textarea { min-height: 90px; }
        .gb-submit { align-self: flex-end; border: none; border-radius: 8px; padding: .55rem 1.4rem;
            background: linear-gradient(45deg, var(--sky-blue, #6aa9e9), var(--coral-pink, #f49bb0));
            color: #fff; font-size: .95rem; cursor: pointer; }
        .gb-submit:disabled { opacity: .5; cursor: not-allowed; }
        .gb-list { display: flex; flex-direction: column; gap: .9rem; }
        .gb-item { border-left: 3px solid var(--sky-blue, #6aa9e9); background: #f6faff; border-radius: 0 8px 8px 0; padding: .7rem 1rem; }
        .gb-item-head { display: flex; justify-content: space-between; font-size: .85rem; color: var(--text-light, #8a97a8); margin-bottom: .3rem; }
        .gb-item-name { font-weight: 600; color: var(--text-dark, #3a4a5c); }
        .gb-item-content { white-space: pre-wrap; word-break: break-word; font-size: .95rem; line-height: 1.7; }
        .gb-tip { text-align: center; color: var(--text-light, #8a97a8); font-size: .9rem; padding: .8rem 0; }
        .gb-err { color: #e05a6d; font-size: .85rem; }
        `;
        const s = document.createElement('style');
        s.id = 'gb-style';
        s.textContent = css;
        document.head.appendChild(s);
    }

    function getProfileId() {
        return new URLSearchParams(window.location.search).get('id')
            || new URLSearchParams(window.location.search).get('name') || '';
    }

    async function fetchMessages(profileId) {
        const res = await fetch(`${API_BASE}/api/messages?profile=${encodeURIComponent(profileId)}`);
        if (!res.ok) throw new Error('HTTP ' + res.status);
        const data = await res.json();
        return data.messages || [];
    }

    async function submitMessage(profileId, name, content) {
        const res = await fetch(`${API_BASE}/api/messages`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ profile: profileId, name: name, content: content })
        });
        const data = await res.json().catch(() => ({}));
        if (!res.ok) throw new Error(data.error || '提交失败');
        return data.message;
    }

    function renderList(container, messages) {
        const list = container.querySelector('.gb-list');
        if (!messages.length) {
            list.innerHTML = '<div class="gb-tip">还没有留言，来写下第一句祝福吧 🌸</div>';
            return;
        }
        list.innerHTML = messages.map(m => `
            <div class="gb-item">
                <div class="gb-item-head">
                    <span class="gb-item-name">${esc(m.name)}</span>
                    <span>${esc(m.time)}</span>
                </div>
                <div class="gb-item-content">${esc(m.content)}</div>
            </div>
        `).join('');
    }

    // 入口：把留言板渲染进指定容器
    window.renderGuestbook = function (containerId) {
        const container = document.getElementById(containerId);
        if (!container) return;

        const profileId = getProfileId();
        if (!profileId) return;

        injectStyles();

        container.innerHTML = `
            <div class="gb-box">
                <form class="gb-form">
                    <input type="text" class="gb-name" maxlength="32" placeholder="昵称（留空则为匿名）">
                    <textarea class="gb-content" maxlength="500" placeholder="写下你想说的话…（最多 500 字）"></textarea>
                    <button type="submit" class="gb-submit">送出留言</button>
                    <span class="gb-err"></span>
                </form>
                <div class="gb-list"><div class="gb-tip">加载中…</div></div>
            </div>
        `;

        const form = container.querySelector('.gb-form');
        const nameInput = container.querySelector('.gb-name');
        const contentInput = container.querySelector('.gb-content');
        const errSpan = container.querySelector('.gb-err');
        const submitBtn = container.querySelector('.gb-submit');

        // 加载已有留言
        fetchMessages(profileId)
            .then(msgs => renderList(container, msgs))
            .catch(() => {
                container.querySelector('.gb-list').innerHTML =
                    '<div class="gb-tip gb-err">留言加载失败，请确认后端服务已启动（' + window.location.host + '）</div>';
            });

        // 提交
        form.addEventListener('submit', async function (e) {
            e.preventDefault();
            errSpan.textContent = '';
            const content = contentInput.value.trim();
            if (!content) { errSpan.textContent = '留言内容不能为空'; return; }

            submitBtn.disabled = true;
            try {
                await submitMessage(profileId, nameInput.value.trim(), content);
                contentInput.value = '';
                const msgs = await fetchMessages(profileId);
                renderList(container, msgs);
            } catch (err) {
                errSpan.textContent = err.message || '提交失败，请稍后重试';
            } finally {
                submitBtn.disabled = false;
            }
        });
    };

    // 覆盖 profile.js 的 utterances 加载入口，改用本地留言板
    document.addEventListener('DOMContentLoaded', function () {
        window.loadUtterances = function () {
            window.renderGuestbook('utterances-container');
        };
    });
})();
