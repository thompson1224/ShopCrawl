function sanitizeExternalUrl(value) {
    if (!value) return '#';

    try {
        const parsed = new URL(value, window.location.origin);
        if (!['http:', 'https:'].includes(parsed.protocol)) {
            return '#';
        }
        return parsed.href;
    } catch {
        return '#';
    }
}

function toggleDarkMode() {
    const html = document.documentElement;
    const isDark = html.classList.contains('dark');
    
    if (isDark) {
        html.classList.remove('dark');
        localStorage.setItem('theme', 'light');
    } else {
        html.classList.add('dark');
        localStorage.setItem('theme', 'dark');
    }
}

function initDarkMode() {
    const savedTheme = localStorage.getItem('theme');
    const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
    
    if (savedTheme === 'dark' || (!savedTheme && prefersDark)) {
        document.documentElement.classList.add('dark');
    }
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
        if (match.index > lastIndex) {
            container.appendChild(document.createTextNode(text.slice(lastIndex, match.index)));
        }

        if (match[2] !== undefined) {
            const strong = document.createElement('strong');
            strong.textContent = match[2];
            container.appendChild(strong);
        } else {
            const link = document.createElement('a');
            link.href = sanitizeExternalUrl(match[4]);
            link.target = '_blank';
            link.rel = 'noopener noreferrer';
            link.className = 'text-purple-600 font-bold underline hover:text-purple-800';
            link.textContent = `${match[3]} 🔗`;
            container.appendChild(link);
        }

        lastIndex = pattern.lastIndex;
    }

    if (lastIndex < text.length) {
        container.appendChild(document.createTextNode(text.slice(lastIndex)));
    }
}

function renderAiAnswer(container, answer) {
    container.replaceChildren();

    String(answer || '').split('\n').forEach((line, index) => {
        if (index > 0) {
            container.appendChild(document.createElement('br'));
        }

        const normalizedLine = line.startsWith('* ') ? `• ${line.slice(2)}` : line;
        appendInlineMarkdown(container, normalizedLine);
    });
}

document.addEventListener('DOMContentLoaded', () => {
    initDarkMode();
    
    const hotdealList = document.getElementById('hotdeal-list');
    const sourceButtonsContainer = document.getElementById('source-buttons');
    const paginationContainer = document.getElementById('pagination');
    
    let currentPage = 1;
    let currentSource = 'all';
    let totalPages = 1;
    let currentPriceRange = 'all';
    let currentCategory = 'all';
    let currentShippingFree = false;
    let currentSort = 'latest';
    let filtersExpanded = false;
    
    // 필터 접기/펼치기 (모바일)
    window.toggleFilters = () => {
        const content = document.getElementById('filterContent');
        const icon = document.getElementById('filterToggleIcon');
        filtersExpanded = !filtersExpanded;
        if (filtersExpanded) {
            content.classList.remove('hidden');
            icon.classList.remove('rotate-180');
        } else {
            content.classList.add('hidden');
            icon.classList.add('rotate-180');
        }
    };

    const fetchHotDeals = async (source = 'all', page = 1) => {
        currentSource = source;
        currentPage = page;
        
        hotdealList.innerHTML = `<div class="glass-morphism p-6 text-center rounded-xl shadow-lg"><div class="flex justify-center gap-1 mb-2"><span class="paw-print">🐾</span><span class="paw-print">🐾</span><span class="paw-print">🐾</span></div><p class="text-gray-500 text-sm">딜냥이가 핫딜을 물어오는 중...</p></div>`;

        const params = new URLSearchParams({
            source: source,
            page: page,
            per_page: 20,
            price_range: currentPriceRange,
            category: currentCategory,
            shipping_free: currentShippingFree,
            sort: currentSort
        });
        const backendUrl = `/api/hotdeals?${params.toString()}`;

        try {
            const response = await fetch(backendUrl);
            if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
            const data = await response.json();
            
            let deals, pagination;
            
            if (Array.isArray(data)) {
                deals = data;
                pagination = { page: 1, per_page: data.length, total: data.length, total_pages: 1 };
            } else if (data.deals && Array.isArray(data.deals)) {
                deals = data.deals;
                pagination = data.pagination;
            } else {
                console.error('잘못된 API 응답:', data);
                throw new Error('잘못된 API 응답 형식');
            }
            
            totalPages = pagination.total_pages;
            hotdealList.innerHTML = '';

            if (deals.length === 0) {
                hotdealList.innerHTML = '<div class="p-6 text-center text-gray-500 dark:text-gray-400 bg-white dark:bg-gray-800 rounded-xl shadow"><span class="text-3xl">😿</span><p class="mt-2 text-sm">딜냥이가 핫딜을 찾지 못했어요!</p></div>';
                paginationContainer.innerHTML = '';
                return;
            }
            
            deals.forEach(deal => {
                const safeLink = sanitizeExternalUrl(deal.link);
                const safeThumbnail = sanitizeExternalUrl(deal.thumbnail);

                const cardContainer = document.createElement('div');
                cardContainer.className = 'relative';

                const linkContainer = document.createElement('a');
                linkContainer.href = safeLink;
                linkContainer.target = '_blank';
                linkContainer.rel = 'noopener noreferrer';
                linkContainer.className = 'block glass-morphism rounded-xl shadow-lg deal-item-container hotdeal-card';

                const wrapper = document.createElement('div');
                wrapper.className = 'flex gap-3';

                const thumbnailWrapper = document.createElement('div');
                thumbnailWrapper.className = 'flex-shrink-0 hotdeal-thumb';

                if (safeThumbnail !== '#') {
                    const image = document.createElement('img');
                    image.src = `/image-proxy?url=${encodeURIComponent(safeThumbnail)}&source=${encodeURIComponent(deal.source)}`;
                    image.alt = deal.title || '핫딜 이미지';
                    image.className = 'w-full h-full object-cover rounded-lg border-2 border-gray-100 dark:border-gray-700 shadow-sm';
                    image.onerror = () => {
                        const fallback = createFallbackThumbnail();
                        fallback.className += ' rounded-lg';
                        image.replaceWith(fallback);
                    };
                    thumbnailWrapper.appendChild(image);
                } else {
                    thumbnailWrapper.appendChild(createFallbackThumbnail());
                }

                const content = document.createElement('div');
                content.className = 'flex-1 min-w-0 flex flex-col justify-between';

                const topSection = document.createElement('div');

                const metaRow = document.createElement('div');
                metaRow.className = 'flex items-center gap-1.5 text-[10px] sm:text-xs mb-1 flex-wrap';

                const sourceBadge = document.createElement('span');
                sourceBadge.className = 'font-bold px-1.5 py-0.5 bg-gradient-to-r from-purple-500 to-blue-500 text-white rounded-full';
                sourceBadge.textContent = deal.source;

                const categoryBadge = document.createElement('span');
                categoryBadge.className = 'px-1.5 py-0.5 bg-gray-200 dark:bg-gray-700 text-gray-600 dark:text-gray-300 rounded-full text-[10px]';
                categoryBadge.textContent = deal.category || '기타';

                const timeText = document.createElement('span');
                timeText.className = 'text-gray-400';
                timeText.textContent = getTimeAgo(deal.created_at);

                metaRow.append(sourceBadge, categoryBadge, timeText);

                const title = document.createElement('h2');
                title.className = 'hotdeal-title font-bold text-gray-800 dark:text-gray-200 mb-1';
                title.textContent = deal.title;

                topSection.append(metaRow, title);
                content.appendChild(topSection);

                const bottomSection = document.createElement('div');
                bottomSection.className = 'flex items-end justify-between gap-2 mt-1';

                const priceRow = document.createElement('div');
                priceRow.className = 'flex flex-wrap items-baseline gap-1';

                const price = document.createElement('span');
                price.className = 'hotdeal-price font-bold bg-gradient-to-r from-red-500 to-pink-500 bg-clip-text text-transparent';
                price.textContent = deal.price || '가격 없음';
                priceRow.appendChild(price);

                if (deal.shipping) {
                    const shipping = document.createElement('span');
                    shipping.className = 'text-[10px] sm:text-xs text-gray-500 dark:text-gray-400 bg-gray-100 dark:bg-gray-700 px-1.5 py-0.5 rounded';
                    shipping.textContent = deal.shipping;
                    priceRow.appendChild(shipping);
                }

                bottomSection.appendChild(priceRow);

                const arrow = document.createElement('span');
                arrow.className = 'text-gray-300 text-lg';
                arrow.textContent = '→';
                bottomSection.appendChild(arrow);

                content.appendChild(bottomSection);
                wrapper.appendChild(thumbnailWrapper);
                wrapper.appendChild(content);
                linkContainer.appendChild(wrapper);

                // 댓글 버튼
                const commentBtn = document.createElement('button');
                commentBtn.className = 'absolute top-3 right-3 p-2 bg-white/80 dark:bg-gray-800/80 rounded-full shadow text-purple-500 hover:bg-purple-100 dark:hover:bg-purple-900 transition-colors';
                commentBtn.innerHTML = '💬';
                commentBtn.onclick = (e) => {
                    e.preventDefault();
                    e.stopPropagation();
                    openCommentModal(deal.id, deal.title);
                };
                cardContainer.appendChild(linkContainer);
                cardContainer.appendChild(commentBtn);

                hotdealList.appendChild(cardContainer);
            });            
            
            renderPagination(pagination);
            
        } catch (error) {
            console.error('핫딜 정보를 가져오는 중 오류 발생:', error);
            hotdealList.innerHTML = `<div class="p-6 text-center text-red-500 bg-red-50 dark:bg-red-900/30 rounded-xl shadow"><span class="text-3xl">😾</span><p class="mt-2 text-sm">딜냥이가 넘어졌어요!<br>잠시 후 다시 시도해주세요.</p></div>`;
        }
    };
    
    // 시간 경과 표시 함수
    const getTimeAgo = (dateString) => {
        const now = new Date();
        const past = new Date(dateString);
        const diffMs = now - past;
        const diffMins = Math.floor(diffMs / 60000);
        const diffHours = Math.floor(diffMs / 3600000);
        const diffDays = Math.floor(diffMs / 86400000);
        
        if (diffMins < 1) return '방금 전';
        if (diffMins < 60) return `${diffMins}분 전`;
        if (diffHours < 24) return `${diffHours}시간 전`;
        if (diffDays < 7) return `${diffDays}일 전`;
        return past.toLocaleDateString('ko-KR');
    };
    
    const renderPagination = (pagination) => {
        paginationContainer.innerHTML = '';
        
        if (!pagination || pagination.total_pages <= 1) return;
        
        const paginationWrapper = document.createElement('div');
        paginationWrapper.className = 'flex justify-center items-center space-x-1 mt-6 flex-wrap';
        
        if (currentPage > 1) {
            const prevBtn = createPageButton('‹', currentPage - 1, '이전');
            paginationWrapper.appendChild(prevBtn);
        }
        
        const startPage = Math.max(1, currentPage - 2);
        const endPage = Math.min(pagination.total_pages, currentPage + 2);
        
        if (startPage > 1) {
            const firstBtn = createPageButton(1, 1);
            paginationWrapper.appendChild(firstBtn);
            if (startPage > 2) {
                const dots = document.createElement('span');
                dots.textContent = '...';
                dots.className = 'px-1 text-gray-500 text-sm';
                paginationWrapper.appendChild(dots);
            }
        }
        
        for (let i = startPage; i <= endPage; i++) {
            const pageBtn = createPageButton(i, i, i === currentPage);
            paginationWrapper.appendChild(pageBtn);
        }
        
        if (endPage < pagination.total_pages) {
            if (endPage < pagination.total_pages - 1) {
                const dots = document.createElement('span');
                dots.textContent = '...';
                dots.className = 'px-1 text-gray-500 text-sm';
                paginationWrapper.appendChild(dots);
            }
            const lastBtn = createPageButton(pagination.total_pages, pagination.total_pages);
            paginationWrapper.appendChild(lastBtn);
        }
        
        if (currentPage < pagination.total_pages) {
            const nextBtn = createPageButton('›', currentPage + 1, '다음');
            paginationWrapper.appendChild(nextBtn);
        }
        
        paginationContainer.appendChild(paginationWrapper);
    };
    
    const createPageButton = (text, page, ariaLabel = null) => {
        const btn = document.createElement('button');
        btn.textContent = text;
        btn.className = `page-btn px-2 py-1.5 rounded-lg text-sm font-medium transition-colors ${
            ariaLabel === 'active' || text === currentPage
                ? 'bg-gradient-to-r from-purple-500 to-blue-500 text-white shadow-md' 
                : 'bg-white dark:bg-gray-800 text-gray-700 dark:text-gray-300 border border-gray-200 dark:border-gray-700 hover:bg-gray-50 dark:hover:bg-gray-700'
        }`;
        if (ariaLabel) btn.setAttribute('aria-label', ariaLabel);
        btn.onclick = () => fetchHotDeals(currentSource, page);
        return btn;
    };

    // 소스 버튼 이벤트 리스너
    sourceButtonsContainer.addEventListener('click', (event) => {
        const button = event.target.closest('button');
        if (button) {
            sourceButtonsContainer.querySelectorAll('.source-btn').forEach(btn => {
                btn.classList.remove('active');
                btn.classList.add('bg-white');
            });
            button.classList.add('active');
            const selectedSource = button.dataset.source;
            fetchHotDeals(selectedSource, 1);
        }
    });

    // 필터 이벤트 리스너
    const priceRangeFilter = document.getElementById('priceRangeFilter');
    const categoryFilter = document.getElementById('categoryFilter');
    const shippingFreeFilter = document.getElementById('shippingFreeFilter');
    const sortOrder = document.getElementById('sortOrder');

    const applyFilters = () => {
        currentPriceRange = priceRangeFilter.value;
        currentCategory = categoryFilter.value;
        currentShippingFree = shippingFreeFilter.checked;
        currentSort = sortOrder.value;
        fetchHotDeals(currentSource, 1);
    };

    priceRangeFilter.addEventListener('change', applyFilters);
    categoryFilter.addEventListener('change', applyFilters);
    shippingFreeFilter.addEventListener('change', applyFilters);
    sortOrder.addEventListener('change', applyFilters);

    // 필터 초기화 함수
    window.resetFilters = () => {
        priceRangeFilter.value = 'all';
        categoryFilter.value = 'all';
        shippingFreeFilter.checked = false;
        sortOrder.value = 'latest';
        currentPriceRange = 'all';
        currentCategory = 'all';
        currentShippingFree = false;
        currentSort = 'latest';
        fetchHotDeals(currentSource, 1);
    };

    // 최초 로딩
    fetchHotDeals('all', 1);
});

// --- AI 검색 기능 ---

async function performAiSearch() {
    const input = document.getElementById('aiSearchInput');
    const resultArea = document.getElementById('aiResultArea');
    const loading = document.getElementById('aiLoading');
    const answerBox = document.getElementById('aiAnswerBox');
    const answerText = document.getElementById('aiAnswerText');
    const sourceList = document.getElementById('aiSourceList');

    const query = input.value.trim();
    if (!query) {
        alert('찾고 싶은 물건을 물어봐달라냥! 😺');
        return;
    }

    // UI 초기화 및 로딩 시작
    resultArea.classList.remove('hidden');
    loading.classList.remove('hidden');
    answerBox.classList.add('hidden');
    sourceList.classList.add('hidden');
    
    // 기존 추천 목록 비우기 (제목 제외)
    while (sourceList.children.length > 1) {
        sourceList.removeChild(sourceList.lastChild);
    }

    try {
        // 백엔드 API 호출
        const response = await fetch(`/api/search/ai?query=${encodeURIComponent(query)}`);
        const data = await response.json();

        // 로딩 끝
        loading.classList.add('hidden');
        answerBox.classList.remove('hidden');

        // 답변 출력 (줄바꿈 처리)
        renderAiAnswer(answerText, data.answer);

        // 추천 상품 섹션 처리
        const sourceSection = document.getElementById('aiSourceSection');
        const sourceList = document.getElementById('aiSourceList');
        const sourceCount = document.getElementById('aiSourceCount');
        const toggleIcon = document.getElementById('aiToggleIcon');

        // 기존 리스트 초기화
        sourceList.innerHTML = '';

        if (data.sources && data.sources.length > 0) {
            sourceSection.classList.remove('hidden'); // 섹션 보이기
            sourceList.classList.remove('hidden');    // 리스트 펼치기 (기본값)
            toggleIcon.classList.remove('rotate-180'); // 아이콘 초기화
            sourceCount.textContent = data.sources.length; // 개수 표시

            data.sources.forEach(source => {
                const card = document.createElement('a');
                card.href = sanitizeExternalUrl(source.link);
                card.target = '_blank';
                card.rel = 'noopener noreferrer';
                card.className = 'block bg-white p-3 rounded-lg shadow-sm border border-gray-100 hover:shadow-md hover:border-purple-200 transition-all flex items-center justify-between group';

                const left = document.createElement('div');
                left.className = 'flex items-center space-x-2 overflow-hidden';

                const icon = document.createElement('span');
                icon.className = 'text-lg';
                icon.textContent = '🛍️';

                const title = document.createElement('span');
                title.className = 'text-sm text-gray-700 truncate group-hover:text-purple-600 transition-colors';
                title.textContent = source.title;

                const arrow = document.createElement('span');
                arrow.className = 'w-4 h-4 text-gray-300 group-hover:text-purple-500';
                arrow.textContent = '›';

                left.append(icon, title);
                card.append(left, arrow);
                sourceList.appendChild(card);
            });
        } else {
            sourceSection.classList.add('hidden'); // 없으면 섹션 통째로 숨김
        }

    } catch (error) {
        console.error('AI 검색 실패:', error);
        loading.classList.add('hidden');
        answerBox.classList.remove('hidden');
        answerText.textContent = "지금 딜냥이가 너무 바빠서 대답할 수 없다냥... 😿 잠시 후에 다시 물어봐줘!";
    }
}

// --- 일반 검색 기능 ---
async function performSearch() {
    const input = document.getElementById('searchInput');
    const query = input.value.trim();
    
    if (!query) {
        alert('검색어를 입력해주세요.');
        return;
    }
    
    const params = new URLSearchParams({
        q: query,
        source: 'all',
        page: 1,
        per_page: 50,
        category: 'all',
        price_range: 'all',
        shipping_free: false,
        sort: 'latest'
    });
    
    const backendUrl = `/api/search?${params.toString()}`;
    
    try {
        const response = await fetch(backendUrl);
        if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
        const data = await response.json();
        
        if (data.deals && data.deals.length > 0) {
            renderSearchResults(data.deals);
        } else {
            document.getElementById('hotdeal-list').innerHTML = 
                '<div class="glass-morphism p-6 text-center rounded-xl shadow-lg"><span class="text-3xl">🔍</span><p class="mt-2 text-gray-500">검색 결과가 없습니다.</p></div>';
        }
    } catch (error) {
        console.error('검색 실패:', error);
        document.getElementById('hotdeal-list').innerHTML = 
            '<div class="glass-morphism p-6 text-center rounded-xl shadow-lg"><span class="text-3xl">😾</span><p class="mt-2 text-red-500">검색 중 오류가 발생했습니다.</p></div>';
    }
}

function renderSearchResults(deals) {
    const hotdealList = document.getElementById('hotdeal-list');
    hotdealList.innerHTML = '';
    
    deals.forEach(deal => {
        const safeLink = sanitizeExternalUrl(deal.link);
        const safeThumbnail = sanitizeExternalUrl(deal.thumbnail);

        const cardContainer = document.createElement('div');
        cardContainer.className = 'relative';

        const linkContainer = document.createElement('a');
        linkContainer.href = safeLink;
        linkContainer.target = '_blank';
        linkContainer.rel = 'noopener noreferrer';
        linkContainer.className = 'block glass-morphism rounded-xl shadow-lg deal-item-container hotdeal-card';

        const wrapper = document.createElement('div');
        wrapper.className = 'flex gap-3';

        const thumbnailWrapper = document.createElement('div');
        thumbnailWrapper.className = 'flex-shrink-0 hotdeal-thumb';

        if (safeThumbnail !== '#') {
            const image = document.createElement('img');
            image.src = `/image-proxy?url=${encodeURIComponent(safeThumbnail)}&source=${encodeURIComponent(deal.source)}`;
            image.alt = deal.title || '핫딜 이미지';
            image.className = 'w-full h-full object-cover rounded-lg border-2 border-gray-100 dark:border-gray-700 shadow-sm';
            image.onerror = () => {
                const fallback = createFallbackThumbnail();
                fallback.className += ' rounded-lg';
                image.replaceWith(fallback);
            };
            thumbnailWrapper.appendChild(image);
        } else {
            thumbnailWrapper.appendChild(createFallbackThumbnail());
        }

        const content = document.createElement('div');
        content.className = 'flex-1 min-w-0 flex flex-col justify-between';

        const topSection = document.createElement('div');

        const metaRow = document.createElement('div');
        metaRow.className = 'flex items-center gap-1.5 text-[10px] sm:text-xs mb-1 flex-wrap';

        const sourceBadge = document.createElement('span');
        sourceBadge.className = 'font-bold px-1.5 py-0.5 bg-gradient-to-r from-purple-500 to-blue-500 text-white rounded-full';
        sourceBadge.textContent = deal.source;

        const categoryBadge = document.createElement('span');
        categoryBadge.className = 'px-1.5 py-0.5 bg-gray-200 dark:bg-gray-700 text-gray-600 dark:text-gray-300 rounded-full text-[10px]';
        categoryBadge.textContent = deal.category || '기타';

        const timeText = document.createElement('span');
        timeText.className = 'text-gray-400';
        timeText.textContent = getTimeAgo(deal.created_at);

        metaRow.append(sourceBadge, categoryBadge, timeText);

        const title = document.createElement('h2');
        title.className = 'hotdeal-title font-bold text-gray-800 dark:text-gray-200 mb-1';
        title.textContent = deal.title;

        topSection.append(metaRow, title);
        content.appendChild(topSection);

        const bottomSection = document.createElement('div');
        bottomSection.className = 'flex items-end justify-between gap-2 mt-1';

        const priceRow = document.createElement('div');
        priceRow.className = 'flex flex-wrap items-baseline gap-1';

        const price = document.createElement('span');
        price.className = 'hotdeal-price font-bold bg-gradient-to-r from-red-500 to-pink-500 bg-clip-text text-transparent';
        price.textContent = deal.price || '가격 없음';
        priceRow.appendChild(price);

        if (deal.shipping) {
            const shipping = document.createElement('span');
            shipping.className = 'text-[10px] sm:text-xs text-gray-500 dark:text-gray-400 bg-gray-100 dark:bg-gray-700 px-1.5 py-0.5 rounded';
            shipping.textContent = deal.shipping;
            priceRow.appendChild(shipping);
        }

        bottomSection.appendChild(priceRow);

        const arrow = document.createElement('span');
        arrow.className = 'text-gray-300 text-lg';
        arrow.textContent = '→';
        bottomSection.appendChild(arrow);

        content.appendChild(bottomSection);
        wrapper.appendChild(thumbnailWrapper);
        wrapper.appendChild(content);
        linkContainer.appendChild(wrapper);

        const commentBtn = document.createElement('button');
        commentBtn.className = 'absolute top-3 right-3 p-2 bg-white/80 dark:bg-gray-800/80 rounded-full shadow text-purple-500 hover:bg-purple-100 dark:hover:bg-purple-900 transition-colors';
        commentBtn.innerHTML = '💬';
        commentBtn.onclick = (e) => {
            e.preventDefault();
            e.stopPropagation();
            openCommentModal(deal.id, deal.title);
        };
        cardContainer.appendChild(linkContainer);
        cardContainer.appendChild(commentBtn);

        hotdealList.appendChild(cardContainer);
    });
    
    document.getElementById('pagination').innerHTML = '';
}

// --- [추가] 리스트 토글 기능 ---
function toggleAiSourceList() {
    const list = document.getElementById('aiSourceList');
    const icon = document.getElementById('aiToggleIcon');
    
    if (list.classList.contains('hidden')) {
        // 펼치기
        list.classList.remove('hidden');
        icon.classList.remove('rotate-180');
    } else {
        // 접기
        list.classList.add('hidden');
        icon.classList.add('rotate-180');
    }
}
