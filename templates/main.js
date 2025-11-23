document.addEventListener('DOMContentLoaded', () => {
    const hotdealList = document.getElementById('hotdeal-list');
    const sourceButtonsContainer = document.getElementById('source-buttons');
    const paginationContainer = document.getElementById('pagination');
    
    let currentPage = 1;
    let currentSource = 'all';
    let totalPages = 1;

    const fetchHotDeals = async (source = 'all', page = 1) => {
        currentSource = source;
        currentPage = page;
        
        const sourceName = source === 'all' ? '전체' : source;
        hotdealList.innerHTML = `<div class="p-4 text-center text-gray-500 bg-white rounded-lg shadow"><span class="animate-pulse">딜냥이가 핫딜을 물어오는 중...</span></div>`;

        const backendUrl = `/api/hotdeals?source=${encodeURIComponent(source)}&page=${page}&per_page=20`;

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

                const linkContainer = document.createElement('a');
                linkContainer.href = deal.link;
                linkContainer.target = '_blank';
                linkContainer.className = 'block glass-morphism p-4 rounded-xl shadow-lg deal-item-container';

                // 모바일 최적화된 카드 레이아웃
                linkContainer.innerHTML = `
                    <div class="flex items-start space-x-3">
                        <div class="flex-shrink-0 w-16 h-16">
                            <img src="/image-proxy?url=${encodeURIComponent(deal.thumbnail)}&source=${encodeURIComponent(deal.source)}" 
                                alt="${deal.title}" 
                                class="w-full h-full object-cover rounded-lg border-2 border-gray-100 shadow-md"
                                onerror="this.outerHTML='<div class=\\'w-full h-full bg-gradient-to-br from-purple-100 to-blue-100 rounded-lg flex items-center justify-center text-gray-400\\' style=\\'min-height:4rem\\'><svg xmlns=\\'http://www.w3.org/2000/svg\\' class=\\'h-6 w-6\\' fill=\\'none\\' viewBox=\\'0 0 24 24\\' stroke=\\'currentColor\\'><path stroke-linecap=\\'round\\' stroke-linejoin=\\'round\\' stroke-width=\\'2\\' d=\\'M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z\\' /></svg></div>'">
                        </div>
                        <div class="flex-1 min-w-0">
                            <div class="flex items-center space-x-1.5 text-xs mb-1.5">
                                <span class="font-bold px-2 py-0.5 bg-gradient-to-r from-purple-500 to-blue-500 text-white rounded-full text-xs">
                                    ${deal.source}
                                </span>
                                <span class="text-gray-500 truncate">
                                    by ${deal.author}
                                </span>
                                <span class="text-gray-400">
                                    • ${getTimeAgo(deal.created_at)}
                                </span>
                            </div>
                            <h2 class="text-base font-bold text-gray-800 leading-tight line-clamp-2 mb-1">
                                ${displayTitle}
                            </h2>
                            <div class="flex items-baseline space-x-2">
                                <span class="text-lg font-bold bg-gradient-to-r from-red-500 to-pink-500 bg-clip-text text-transparent">
                                    ${deal.price || '가격 정보 없음'}
                                </span>
                                ${deal.shipping ? `<span class="text-xs text-gray-600 bg-gray-100 px-1.5 py-0.5 rounded"> ${deal.shipping} </span>` : ''}
                            </div>
                        </div>
                    </div>
                `;

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
        let formattedAnswer = data.answer
            // 1. **굵게** -> <strong>굵게</strong>
            .replace(/\*\*(.*?)\*\*/g, '<strong class="text-purple-600">$1</strong>')
            // 2. * 목록 -> 깔끔한 점으로 변환
            .replace(/^\* /gm, '• ')
            // 3. 줄바꿈 -> <br>
            .replace(/\n/g, '<br>');

        answerText.innerHTML = formattedAnswer;

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
                card.href = source.link;
                card.target = '_blank';
                card.className = 'block bg-white p-3 rounded-lg shadow-sm border border-gray-100 hover:shadow-md hover:border-purple-200 transition-all flex items-center justify-between group';
                
                card.innerHTML = `
                    <div class="flex items-center space-x-2 overflow-hidden">
                        <span class="text-lg">🛍️</span>
                        <span class="text-sm text-gray-700 truncate group-hover:text-purple-600 transition-colors">${source.title}</span>
                    </div>
                    <svg class="w-4 h-4 text-gray-300 group-hover:text-purple-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5l7 7-7 7" />
                    </svg>
                `;
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