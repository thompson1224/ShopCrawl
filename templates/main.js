function sanitizeExternalUrl(value) {
    if (!value) return '#';
    try {
        const parsed = new URL(value, window.location.origin);
        return ['http:', 'https:'].includes(parsed.protocol) ? parsed.href : '#';
    } catch { return '#'; }
}

function toggleDarkMode() {
    const html = document.documentElement;
    const isDark = html.classList.contains('dark');
    html.classList.toggle('dark');
    localStorage.setItem('theme', isDark ? 'light' : 'dark');
}

function initDarkMode() {
    const savedTheme = localStorage.getItem('theme');
    const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
    if (savedTheme === 'dark' || (!savedTheme && prefersDark)) document.documentElement.classList.add('dark');
}

function createFallbackThumbnail() {
    const fallback = document.createElement('div');
    fallback.className = 'w-full h-full bg-gradient-to-br from-purple-100 to-blue-100 rounded-lg flex items-center justify-center text-gray-400 text-xl';
    fallback.style.minHeight = '4rem';
    fallback.textContent = '🖼️';
    return fallback;
}

function appendInlineMarkdown(container, text) {
    const pattern = /(\*\*(.+?)\*\*|\[(.+?)\]\((.+?)\))/g;
    let lastIndex = 0;
    let match;
    while ((match = pattern.exec(text)) !== null) {
        if (match.index > lastIndex) container.appendChild(document.createTextNode(text.slice(lastIndex, match.index)));
        if (match[2] !== undefined) {
            const strong = document.createElement('strong');
            strong.textContent = match[2];
            container.appendChild(strong);
        } else {
            const link = document.createElement('a');
            link.href = sanitizeExternalUrl(match[4]);
            link.target = '_blank'; link.rel = 'noopener noreferrer';
            link.className = 'text-purple-600 font-bold underline hover:text-purple-800';
            link.textContent = `${match[3]} 🔗`;
            container.appendChild(link);
        }
        lastIndex = pattern.lastIndex;
    }
    if (lastIndex < text.length) container.appendChild(document.createTextNode(text.slice(lastIndex)));
}

function renderAiAnswer(container, answer) {
    container.replaceChildren();
    String(answer || '').split('\n').forEach((line, index) => {
        if (index > 0) container.appendChild(document.createElement('br'));
        const normalizedLine = line.startsWith('* ') ? `• ${line.slice(2)}` : line;
        appendInlineMarkdown(container, normalizedLine);
    });
}

function showToast(message, type = 'info') {
    const container = document.getElementById('toast-container');
    if (!container) return;
    const toast = document.createElement('div');
    const bgClass = type === 'error' ? 'bg-red-500' : (type === 'success' ? 'bg-green-500' : 'bg-gray-800/90');
    toast.className = `toast px-6 py-3 rounded-2xl text-white font-medium shadow-2xl backdrop-blur-md ${bgClass} flex items-center gap-2`;
    toast.innerHTML = `<span>${type==='error'?'❌':type==='success'?'✅':'🔔'}</span><span class="text-sm">${message}</span>`;
    container.appendChild(toast);
    setTimeout(() => {
        toast.style.opacity = '0'; toast.style.transform = 'translateY(10px)'; toast.style.transition = 'all 0.3s ease';
        setTimeout(() => toast.remove(), 300);
    }, 3000);
}

function getElement(id) {
    return document.getElementById(id);
}

function createSkeletonCard() {
    const card = document.createElement('div');
    card.className = 'glass-morphism rounded-2xl shadow-lg overflow-hidden flex flex-row sm:flex-col h-full bg-white dark:bg-gray-800';
    card.innerHTML = `<div class="w-28 sm:w-full sm:aspect-video skeleton"></div><div class="flex-1 p-3 sm:p-4 space-y-3"><div class="flex gap-2"><div class="h-4 w-12 skeleton rounded-md"></div><div class="h-4 w-16 skeleton rounded-md ml-auto"></div></div><div class="h-5 w-full skeleton rounded-md"></div><div class="h-5 w-3/4 skeleton rounded-md"></div><div class="pt-2 border-t border-gray-100 dark:border-gray-700/50 flex justify-between"><div class="h-6 w-24 skeleton rounded-md"></div><div class="h-6 w-6 skeleton rounded-full"></div></div></div>`;
    return card;
}

const getTimeAgo = (dateString) => {
    const diffMs = new Date() - new Date(dateString);
    const m = Math.floor(diffMs / 60000), h = Math.floor(diffMs / 3600000), d = Math.floor(diffMs / 86400000);
    if (m < 1) return '방금 전'; if (m < 60) return `${m}분 전`; if (h < 24) return `${h}시간 전`; if (d < 7) return `${d}일 전`;
    return new Date(dateString).toLocaleDateString('ko-KR');
};

function createDealCard(deal) {
    const safeLink = sanitizeExternalUrl(deal.link), safeThumb = sanitizeExternalUrl(deal.thumbnail);
    const card = document.createElement('div'); card.className = 'relative h-full';
    const link = document.createElement('a'); link.href = safeLink; link.target = '_blank'; link.rel = 'noopener noreferrer';
    link.className = 'block glass-morphism rounded-2xl shadow-lg hover:shadow-xl group overflow-hidden flex flex-row sm:flex-col h-full bg-white dark:bg-gray-800 transition-all duration-300';
    
    let thumbHtml = safeThumb !== '#' ? `<img src="/image-proxy?url=${encodeURIComponent(safeThumb)}&source=${encodeURIComponent(deal.source)}" class="absolute inset-0 w-full h-full object-cover group-hover:scale-105 transition-transform duration-300" onerror="this.src='data:image/svg+xml,%3Csvg xmlns=%22http://www.w3.org/2000/svg%22 width=%22100%25%22 height=%22100%25%22%3E%3Crect width=%22100%25%22 height=%22100%25%22 fill=%22%23eee%22/%3E%3Ctext x=%2250%25%22 y=%2250%25%22 dominant-baseline=%22middle%22 text-anchor=%22middle%22 font-size=%2220%22%3E🖼️%3C/text%3E%3C/svg%3E'">` : `<div class="absolute inset-0 w-full h-full bg-gray-100 flex items-center justify-center text-xl">🖼️</div>`;

    link.innerHTML = `<div class="w-28 sm:w-full sm:aspect-video flex-shrink-0 relative overflow-hidden bg-gray-50 dark:bg-gray-900 border-r sm:border-r-0 sm:border-b border-gray-100 dark:border-gray-700">${thumbHtml}</div><div class="flex-1 p-3 sm:p-4 flex flex-col justify-between min-w-0"><div class="top"><div class="flex items-center gap-1.5 text-[10px] sm:text-xs mb-2 flex-wrap"><span class="font-bold px-2 py-0.5 bg-gradient-to-r from-purple-500 to-blue-500 text-white rounded-md">${deal.source}</span><span class="px-1.5 py-0.5 bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-300 rounded-md border border-gray-200 dark:border-gray-600">${deal.category||'기타'}</span><span class="text-gray-400 ml-auto">${getTimeAgo(deal.created_at)}</span></div><h2 class="font-bold text-gray-800 dark:text-gray-200 mb-2 text-sm sm:text-base leading-snug line-clamp-2">${deal.title}</h2></div><div class="bottom flex items-end justify-between gap-2 mt-2 pt-2 border-t border-gray-100 dark:border-gray-700/50"><div class="flex flex-wrap items-baseline gap-1.5"><span class="font-extrabold text-lg sm:text-xl text-red-500 tracking-tight">${deal.price||'가격없음'}</span>${deal.shipping?`<span class="text-[10px] sm:text-xs text-blue-600 bg-blue-50 px-1.5 py-0.5 rounded border border-blue-100">${deal.shipping}</span>`:''}</div></div></div>`;
    
    const commentBtn = document.createElement('button');
    commentBtn.className = 'absolute top-2 right-2 p-2 bg-white/90 dark:bg-gray-800/90 rounded-full shadow-md text-purple-500 z-10';
    commentBtn.innerHTML = '<svg class="w-4 h-4" fill="currentColor" viewBox="0 0 20 20"><path d="M18 10c0 3.866-3.582 7-8 7a8.841 8.841 0 01-4.083-.98L2 17l1.338-3.123C2.493 12.767 2 11.434 2 10c0-3.866 3.582-7 8-7s8 3.134 8 7zM7 9H5v2h2V9zm8 0h-2v2h2V9zM9 9h2v2H9V9z"></path></svg>';
    commentBtn.onclick = (e) => { e.preventDefault(); e.stopPropagation(); openCommentModal(deal.id, deal.title); };
    card.appendChild(link); card.appendChild(commentBtn);
    return card;
}

document.addEventListener('DOMContentLoaded', () => {
    initDarkMode();
    const list = getElement('hotdeal-list');
    const sBtns = getElement('source-buttons');
    const pg = getElement('pagination');
    const sentinel = getElement('infinite-scroll-sentinel');
    if (!list || !sBtns || !pg) return;
    let page = 1, source = 'all', total = 1, pr = 'all', cat = 'all', ship = false, sort = 'latest', loading = false;

    const observer = new IntersectionObserver(es => { if(es[0].isIntersecting && !loading && page < total) fetchDeals(source, page + 1, true); }, { threshold: 0.1 });
    if (sentinel) observer.observe(sentinel);

    window.switchTab = t => {
        const h = getElement('nav-home');
        const a = getElement('nav-ai');
        if (!h || !a) return;
        if(t==='home') {
            window.scrollTo({top:0, behavior:'smooth'});
            h.className='flex flex-col items-center gap-1 text-purple-600';
            a.className='flex flex-col items-center gap-1 text-gray-400';
            showToast('홈 리스트다냥!');
        } else {
            const ai = getElement('aiSearchInput');
            if(ai){
                ai.scrollIntoView({behavior:'smooth',block:'center'});
                ai.focus();
            }
            a.className='flex flex-col items-center gap-1 text-purple-600';
            h.className='flex flex-col items-center gap-1 text-gray-400';
            showToast('AI 딜냥이다냥! 🐱');
        }
    };

    window.toggleFilters = () => {
        const c = getElement('filterContent');
        const i = getElement('filterToggleIcon');
        if (!c || !i) return;
        c.classList.toggle('hidden'); i.classList.toggle('rotate-180');
    };

    window.toggleProfileMenu = () => {
        const d = document.querySelector('.profile-dropdown');
        if (!d) return;
        d.style.display = d.style.display === 'block' ? 'none' : 'block';
    };

    const fetchDeals = async (s = 'all', p = 1, append = false) => {
        if(loading) return; loading = true; source = s; page = p;
        if(!append) { list.innerHTML = ''; for(let i=0;i<8;i++) list.appendChild(createSkeletonCard()); }
        const ps = new URLSearchParams({source:s, page:p, per_page:20, price_range:pr, category:cat, shipping_free:ship, sort:sort});
        try {
            const res = await fetch(`/api/hotdeals?${ps}`);
            const data = await res.json();
            const deals = data.deals || data;
            total = data.pagination ? data.pagination.total_pages : 1;
            if(!append) { list.innerHTML = ''; if(deals.length===0) { list.innerHTML = '<div class="col-span-full text-center p-10 bg-white rounded-xl shadow">😿 핫딜이 없다냥!</div>'; return; } }
            deals.forEach(d => list.appendChild(createDealCard(d)));
            renderPagination(data.pagination);
        } catch(e) { console.error(e); if(!append) list.innerHTML = '에러났다냥 😿'; else showToast('추가 로딩 실패 😿', 'error'); }
        finally { loading = false; }
    };

    const renderPagination = (p) => {
        pg.innerHTML = ''; if(!p || p.total_pages <= 1) return;
        const w = document.createElement('div'); w.className = 'flex justify-center gap-1 mt-6';
        const btn = (t, v, active) => {
            const b = document.createElement('button'); b.textContent = t;
            b.className = `px-3 py-1.5 rounded-lg text-sm ${active?'bg-purple-600 text-white':'bg-white text-gray-700 border'}`;
            b.onclick = () => fetchDeals(source, v); return b;
        };
        if(page > 1) w.appendChild(btn('‹', page-1));
        for(let i=Math.max(1,page-2);i<=Math.min(p.total_pages,page+2);i++) w.appendChild(btn(i, i, i===page));
        if(page < p.total_pages) w.appendChild(btn('›', page+1));
        pg.appendChild(w);
    };

    sBtns.addEventListener('click', e => {
        const b = e.target.closest('button');
        if(b) { sBtns.querySelectorAll('.source-btn').forEach(x=>x.classList.remove('active','bg-purple-600','text-white')); b.classList.add('active','bg-purple-600','text-white'); fetchDeals(b.dataset.source, 1); }
    });

    const f1=getElement('priceRangeFilter'), f2=getElement('categoryFilter'), f3=getElement('shippingFreeFilter'), f4=getElement('sortOrder');
    if (!f1 || !f2 || !f3 || !f4) return;
    const apply = () => { pr=f1.value; cat=f2.value; ship=f3.checked; sort=f4.value; fetchDeals(source, 1); };
    [f1,f2,f3,f4].forEach(x=>x.addEventListener('change', apply));
    window.resetFilters = () => { f1.value=f2.value='all'; f3.checked=false; f4.value='latest'; apply(); };

    fetchDeals('all', 1);

    let pullStartY = 0;
    let pullCurrentY = 0;
    let isPulling = false;
    let pullIndicator = null;

    const createPullIndicator = () => {
        if (pullIndicator) return;
        pullIndicator = document.createElement('div');
        pullIndicator.id = 'pull-indicator';
        pullIndicator.className = 'fixed top-0 left-0 right-0 z-50 flex justify-center items-center py-2 bg-purple-600 text-white text-sm font-medium transition-transform duration-200 -translate-y-full';
        pullIndicator.innerHTML = '<span class="mr-2">↓</span> 당겨서 새로고침';
        document.body.appendChild(pullIndicator);
    };

    const updatePullIndicator = (offset) => {
        if (!pullIndicator) return;
        if (offset > 0) {
            pullIndicator.style.transform = `translateY(${Math.min(offset, 80)}px)`;
            pullIndicator.classList.toggle('bg-purple-600', offset < 80);
            pullIndicator.classList.toggle('bg-green-500', offset >= 80);
            pullIndicator.querySelector('span').textContent = offset >= 80 ? '↻放手刷新' : '↓';
        }
    };

    const resetPullIndicator = () => {
        if (!pullIndicator) return;
        pullIndicator.style.transform = '-translate-y-full';
    };

    document.addEventListener('touchstart', (e) => {
        if (window.scrollY === 0) {
            pullStartY = e.touches[0].clientY;
            isPulling = true;
            createPullIndicator();
        }
    }, { passive: true });

    document.addEventListener('touchmove', (e) => {
        if (!isPulling) return;
        pullCurrentY = e.touches[0].clientY;
        const pullDiff = pullCurrentY - pullStartY;
        if (pullDiff > 0) {
            e.preventDefault();
            updatePullIndicator(pullDiff);
        }
    }, { passive: false });

    document.addEventListener('touchend', () => {
        if (!isPulling) return;
        const pullDiff = pullCurrentY - pullStartY;
        if (pullDiff >= 80) {
            pullIndicator.style.transition = 'transform 0.3s ease';
            pullIndicator.style.transform = 'translateY(0)';
            pullIndicator.querySelector('span').textContent = '↻';
            pullIndicator.querySelector('span').classList.add('animate-spin');
            fetchDeals(source, 1);
            setTimeout(() => {
                resetPullIndicator();
                pullIndicator.style.transition = 'transform 0.2s ease';
                if (pullIndicator) pullIndicator.querySelector('span').classList.remove('animate-spin');
            }, 1000);
        } else {
            resetPullIndicator();
        }
        isPulling = false;
        pullStartY = 0;
        pullCurrentY = 0;
    }, { passive: true });
});

async function performAiSearch() {
    const i = getElement('aiSearchInput'), r = getElement('aiResultArea'), l = getElement('aiLoading'), ab = getElement('aiAnswerBox'), at = getElement('aiAnswerText'), sl = getElement('aiSourceList');
    if (!i || !r || !l || !ab || !at || !sl) {
        showToast('AI 검색 UI가 아직 준비되지 않았다냥.', 'info');
        return;
    }
    const q = i.value.trim(); if(!q) { showToast('뭐 찾냐냥? 😺'); return; }
    r.classList.remove('hidden'); l.classList.remove('hidden'); ab.classList.add('hidden');
    try {
        const res = await fetch(`/api/search/ai?query=${encodeURIComponent(q)}`);
        const d = await res.json();
        l.classList.add('hidden'); ab.classList.remove('hidden'); renderAiAnswer(at, d.answer);
        const sSec = getElement('aiSourceSection'), sc = getElement('aiSourceCount'), ti = getElement('aiToggleIcon');
        if (!sSec || !sc || !ti) return;
        sl.innerHTML = '';
        if(d.sources && d.sources.length > 0) {
            sSec.classList.remove('hidden'); sl.classList.remove('hidden'); ti.classList.remove('rotate-180'); sc.textContent = d.sources.length;
            d.sources.forEach(s => {
                const c = document.createElement('a'); c.href = sanitizeExternalUrl(s.link); c.target = '_blank'; c.className = 'block bg-white p-3 rounded-lg shadow-sm border mb-2 flex justify-between items-center';
                c.innerHTML = `<div class="flex items-center gap-2 overflow-hidden"><span>🛍️</span><span class="text-sm truncate">${s.title}</span></div><span>›</span>`;
                sl.appendChild(c);
            });
        } else sSec.classList.add('hidden');
    } catch(e) { l.classList.add('hidden'); ab.classList.remove('hidden'); at.textContent = "에러났다냥 😿"; showToast('AI 검색 에러 😿', 'error'); }
}

async function performSearch() {
    const i = getElement('searchInput');
    const l = getElement('hotdeal-list');
    if(!i || !l) return;
    const q = i.value.trim();
    if(!q) { showToast('검색어 입력해라냥!'); return; }
    try {
        const res = await fetch(`/api/search?q=${encodeURIComponent(q)}&source=all&page=1&per_page=50`);
        const d = await res.json();
        l.innerHTML = '';
        if(d.deals && d.deals.length > 0) {
            d.deals.forEach(x => l.appendChild(createDealCard(x)));
            const pagination = getElement('pagination');
            if (pagination) pagination.innerHTML = '';
        } else l.innerHTML = '<div class="col-span-full text-center p-10 bg-white rounded-xl shadow">🔍 결과 없다냥!</div>';
    } catch(e) { showToast('검색 중 에러났다냥 😿', 'error'); }
}

function toggleAiSourceList() {
    const l = getElement('aiSourceList');
    const i = getElement('aiToggleIcon');
    if (!l || !i) return;
    l.classList.toggle('hidden');
    i.classList.toggle('rotate-180');
}
