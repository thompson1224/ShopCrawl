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
    let currentShippingFree = false;
    let currentSort = 'latest';

    const fetchHotDeals = async (source = 'all', page = 1) => {
        currentSource = source;
        currentPage = page;
        
        hotdealList.innerHTML = `<div class="p-4 text-center text-gray-500 bg-white dark:bg-gray-800 rounded-lg shadow"><span class="animate-pulse">딜냥이가 핫딜을 물어오는 중...</span></div>`;

        const params = new URLSearchParams({
            source: source,
            page: page,
            per_page: 20,
            price_range: currentPriceRange,
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
                hotdealList.innerHTML = '<div class="p-4 text-center text-gray-500 bg-white rounded-lg shadow">😿 딜냥이가 핫딜을 찾지 못했어요!</div>';
                paginationContainer.innerHTML = '';
                return;
            }
            
            deals.forEach(deal => {
                // 모바일에서 제목 줄바꿈 개선
                const displayTitle = deal.title.length > 40 ? 
                    deal.title.substring(0, 40) + '...' : 
                    deal.title;
                const safeLink = sanitizeExternalUrl(deal.link);
                const safeThumbnail = sanitizeExternalUrl(deal.thumbnail);

                const linkContainer = document.createElement('a');
                linkContainer.href = safeLink;
                linkContainer.target = '_blank';
                linkContainer.rel = 'noopener noreferrer';
                linkContainer.className = 'block glass-morphism p-4 rounded-xl shadow-lg deal-item-container';

                const wrapper = document.createElement('div');
                wrapper.className = 'flex items-start space-x-3';

                const thumbnailWrapper = document.createElement('div');
                thumbnailWrapper.className = 'flex-shrink-0 w-16 h-16';

                if (safeThumbnail !== '#') {
                    const image = document.createElement('img');
                    image.src = `/image-proxy?url=${encodeURIComponent(safeThumbnail)}&source=${encodeURIComponent(deal.source)}`;
                    image.alt = deal.title || '핫딜 이미지';
                    image.className = 'w-full h-full object-cover rounded-lg border-2 border-gray-100 shadow-md';
                    image.onerror = () => {
                        image.replaceWith(createFallbackThumbnail());
                    };
                    thumbnailWrapper.appendChild(image);
                } else {
                    thumbnailWrapper.appendChild(createFallbackThumbnail());
                }

                const content = document.createElement('div');
                content.className = 'flex-1 min-w-0';

                const metaRow = document.createElement('div');
                metaRow.className = 'flex items-center space-x-1.5 text-xs mb-1.5';

                const sourceBadge = document.createElement('span');
                sourceBadge.className = 'font-bold px-2 py-0.5 bg-gradient-to-r from-purple-500 to-blue-500 text-white rounded-full text-xs';
                sourceBadge.textContent = deal.source;

                const authorText = document.createElement('span');
                authorText.className = 'text-gray-500 truncate';
                authorText.textContent = `by ${deal.author}`;

                const timeText = document.createElement('span');
                timeText.className = 'text-gray-400';
                timeText.textContent = `• ${getTimeAgo(deal.created_at)}`;

                metaRow.append(sourceBadge, authorText, timeText);

                const title = document.createElement('h2');
                title.className = 'text-base font-bold text-gray-800 leading-tight line-clamp-2 mb-1';
                title.textContent = displayTitle;

                const priceRow = document.createElement('div');
                priceRow.className = 'flex items-baseline space-x-2';

                const price = document.createElement('span');
                price.className = 'text-lg font-bold bg-gradient-to-r from-red-500 to-pink-500 bg-clip-text text-transparent';
                price.textContent = deal.price || '가격 정보 없음';
                priceRow.appendChild(price);

                if (deal.shipping) {
                    const shipping = document.createElement('span');
                    shipping.className = 'text-xs text-gray-600 bg-gray-100 px-1.5 py-0.5 rounded';
                    shipping.textContent = deal.shipping;
                    priceRow.appendChild(shipping);
                }

                content.append(metaRow, title, priceRow);
                wrapper.append(thumbnailWrapper, content);
                linkContainer.appendChild(wrapper);

                // 탭 후 백그라운드 색상 제거
                linkContainer.addEventListener('focus', () => {
                    linkContainer.classList.remove('bg-gray-50');
                });

                hotdealList.appendChild(linkContainer);
            });            
            
            renderPagination(pagination);
            
        } catch (error) {
            console.error('핫딜 정보를 가져오는 중 오류 발생:', error);
            hotdealList.innerHTML = `<div class="p-4 text-center text-red-500 bg-red-50 rounded-lg shadow">😾 딜냥이가 넘어졌어요! 잠시 후 다시 시도해주세요.</div>`;
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
        btn.className = `px-2.5 py-1 rounded text-sm font-medium transition-colors ${
            ariaLabel === 'active' || text === currentPage
                ? 'bg-blue-500 text-white shadow-md' 
                : 'bg-white text-gray-700 border border-gray-300 hover:bg-gray-100'
        } min-w-8 text-center`;
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
    const shippingFreeFilter = document.getElementById('shippingFreeFilter');
    const sortOrder = document.getElementById('sortOrder');

    const applyFilters = () => {
        currentPriceRange = priceRangeFilter.value;
        currentShippingFree = shippingFreeFilter.checked;
        currentSort = sortOrder.value;
        fetchHotDeals(currentSource, 1);
    };

    priceRangeFilter.addEventListener('change', applyFilters);
    shippingFreeFilter.addEventListener('change', applyFilters);
    sortOrder.addEventListener('change', applyFilters);

    // 필터 초기화 함수
    window.resetFilters = () => {
        priceRangeFilter.value = 'all';
        shippingFreeFilter.checked = false;
        sortOrder.value = 'latest';
        currentPriceRange = 'all';
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
