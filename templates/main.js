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
        hotdealList.innerHTML = `<div class="p-4 text-center text-gray-500 bg-white rounded-lg shadow"><span class="animate-pulse">최신 핫딜 정보를 불러오는 중... (${sourceName}, 페이지 ${page})</span></div>`;

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
                hotdealList.innerHTML = '<div class="p-4 text-center text-gray-500 bg-white rounded-lg shadow">표시할 핫딜 정보가 없습니다.</div>';
                paginationContainer.innerHTML = '';
                return;
            }
            
            deals.forEach(deal => {
                const linkContainer = document.createElement('a');
                linkContainer.href = deal.link;
                linkContainer.target = '_blank';
                linkContainer.className = 'block glass-morphism p-5 rounded-2xl shadow-lg deal-item-container';
            
                const dealWrapper = document.createElement('div');
                dealWrapper.className = 'flex items-start space-x-4';
            
                // 썸네일
                let thumbnailElement;
                if (deal.thumbnail && deal.thumbnail.trim() !== '') {
                    thumbnailElement = document.createElement('img');
                    thumbnailElement.src = `/image-proxy?url=${encodeURIComponent(deal.thumbnail)}&source=${encodeURIComponent(deal.source)}`;
                    thumbnailElement.alt = deal.title;
                    thumbnailElement.className = 'w-24 h-24 object-cover rounded-xl border-2 border-gray-100 flex-shrink-0 shadow-md';
                    
                    thumbnailElement.onerror = function() {
                        const placeholder = document.createElement('div');
                        placeholder.className = 'w-24 h-24 bg-gradient-to-br from-purple-100 to-blue-100 rounded-xl flex items-center justify-center text-gray-400 flex-shrink-0 shadow-md';
                        placeholder.innerHTML = '<svg xmlns="http://www.w3.org/2000/svg" class="h-10 w-10" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z" /></svg>';
                        this.parentElement.replaceChild(placeholder, this);
                    };
                } else {
                    thumbnailElement = document.createElement('div');
                    thumbnailElement.className = 'w-24 h-24 bg-gradient-to-br from-purple-100 to-blue-100 rounded-xl flex items-center justify-center text-gray-400 flex-shrink-0 shadow-md';
                    thumbnailElement.innerHTML = '<svg xmlns="http://www.w3.org/2000/svg" class="h-10 w-10" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z" /></svg>';
                }
            
                const contentWrapper = document.createElement('div');
                contentWrapper.className = 'flex-grow min-w-0';
            
                const topMeta = document.createElement('div');
                topMeta.className = 'flex items-center space-x-2 text-xs mb-2';
            
                const sourceTag = document.createElement('span');
                sourceTag.className = 'font-bold px-3 py-1 bg-gradient-to-r from-purple-500 to-blue-500 text-white rounded-full shadow-sm';
                sourceTag.textContent = deal.source;
            
                const authorTag = document.createElement('span');
                authorTag.className = 'text-gray-500';
                authorTag.textContent = `by ${deal.author}`;
                
                const timeTag = document.createElement('span');
                timeTag.className = 'text-gray-400';
                timeTag.textContent = `• ${getTimeAgo(deal.created_at)}`;
                
                topMeta.appendChild(sourceTag);
                topMeta.appendChild(authorTag);
                topMeta.appendChild(timeTag);
            
                const title = document.createElement('h2');
                title.className = 'text-lg font-bold text-gray-800 leading-tight mb-2 line-clamp-2';
                title.textContent = deal.title;
                
                const bottomMeta = document.createElement('div');
                bottomMeta.className = 'flex items-baseline space-x-2';
                
                const price = document.createElement('span');
                price.className = 'text-xl font-bold bg-gradient-to-r from-red-500 to-pink-500 bg-clip-text text-transparent';
                price.textContent = deal.price || '가격 정보 없음';
            
                const shipping = document.createElement('span');
                shipping.className = 'text-sm text-gray-600 bg-gray-100 px-2 py-1 rounded-lg';
                shipping.textContent = deal.shipping || '';
            
                bottomMeta.appendChild(price);
                if (deal.shipping) {
                    bottomMeta.appendChild(shipping);
                }
            
                contentWrapper.appendChild(topMeta);
                contentWrapper.appendChild(title);
                contentWrapper.appendChild(bottomMeta);
                
                dealWrapper.appendChild(thumbnailElement);
                dealWrapper.appendChild(contentWrapper);
                linkContainer.appendChild(dealWrapper);
                hotdealList.appendChild(linkContainer);
            });            
            
            
            renderPagination(pagination);
            
        } catch (error) {
            console.error('핫딜 정보를 가져오는 중 오류 발생:', error);
            hotdealList.innerHTML = `<div class="p-4 text-center text-red-500 bg-red-50 rounded-lg shadow">데이터 로딩에 실패했습니다: ${error.message}</div>`;
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
        paginationWrapper.className = 'flex justify-center items-center space-x-2 mt-6';
        
        if (currentPage > 1) {
            const prevBtn = createPageButton('‹ 이전', currentPage - 1);
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
                dots.className = 'px-2 text-gray-500';
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
                dots.className = 'px-2 text-gray-500';
                paginationWrapper.appendChild(dots);
            }
            const lastBtn = createPageButton(pagination.total_pages, pagination.total_pages);
            paginationWrapper.appendChild(lastBtn);
        }
        
        if (currentPage < pagination.total_pages) {
            const nextBtn = createPageButton('다음 ›', currentPage + 1);
            paginationWrapper.appendChild(nextBtn);
        }
        
        paginationContainer.appendChild(paginationWrapper);
    };
    
    const createPageButton = (text, page, isActive = false) => {
        const btn = document.createElement('button');
        btn.textContent = text;
        btn.className = `px-3 py-1 rounded-lg font-medium transition-colors text-sm ${
            isActive 
                ? 'bg-blue-500 text-white shadow-md' 
                : 'bg-white text-gray-700 border border-gray-300 hover:bg-gray-100'
        }`;
        btn.onclick = () => fetchHotDeals(currentSource, page);
        return btn;
    };

    sourceButtonsContainer.addEventListener('click', (event) => {
        const button = event.target.closest('button');
        if (button) {
            sourceButtonsContainer.querySelectorAll('.source-btn').forEach(btn => btn.classList.remove('active'));
            button.classList.add('active');
            const selectedSource = button.dataset.source;
            fetchHotDeals(selectedSource, 1);
        }
    });

    fetchHotDeals('all', 1);
});
