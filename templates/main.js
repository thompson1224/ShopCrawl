document.addEventListener('DOMContentLoaded', () => {
    const hotdealList = document.getElementById('hotdeal-list');
    const sourceButtonsContainer = document.getElementById('source-buttons');

    const fetchHotDeals = async (source = 'all') => {
        const sourceName = source === 'all' ? '전체' : source;
        hotdealList.innerHTML = `<div class="p-4 text-center text-gray-500 bg-white rounded-lg shadow"><span class="animate-pulse">최신 핫딜 정보를 불러오는 중... (${sourceName})</span></div>`;

        const backendUrl = `/api/hotdeals?source=${source}`;

        try {
            const response = await fetch(backendUrl);
            if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
            const deals = await response.json();
            
            hotdealList.innerHTML = '';

            if (deals.length === 0) {
                hotdealList.innerHTML = '<div class="p-4 text-center text-gray-500 bg-white rounded-lg shadow">표시할 핫딜 정보가 없습니다.</div>';
                return;
            }
            
            deals.forEach(deal => {
                const linkContainer = document.createElement('a');
                linkContainer.href = deal.link;
                linkContainer.target = '_blank';
                linkContainer.className = 'block bg-white p-4 rounded-lg shadow transition-all duration-300 deal-item-container';

                const dealWrapper = document.createElement('div');
                dealWrapper.className = 'flex items-start space-x-4';

                const thumbnail = document.createElement('img');

                if (deal.thumbnail && deal.thumbnail.trim() !== '') {
                    thumbnail.src = `/image-proxy?url=${encodeURIComponent(deal.thumbnail)}&source=${deal.source}`;
                } else {
                    thumbnail.src = 'https://via.placeholder.com/80x80/e5e7eb/9ca3af?text=No+Image';
                }

                thumbnail.alt = deal.title;
                thumbnail.className = 'w-20 h-20 object-cover rounded-md border border-gray-200 flex-shrink-0';

                
                const contentWrapper = document.createElement('div');
                contentWrapper.className = 'flex-grow flex flex-col justify-between h-20';

                const topMeta = document.createElement('div');
                topMeta.className = 'flex items-center space-x-2 text-xs text-gray-500';

                const sourceTag = document.createElement('span');
                sourceTag.className = 'font-bold px-2 py-0.5 bg-gray-200 text-gray-700 rounded-full';
                sourceTag.textContent = deal.source;

                const authorTag = document.createElement('span');
                authorTag.textContent = `by ${deal.author}`;
                
                topMeta.appendChild(sourceTag);
                topMeta.appendChild(authorTag);

                const title = document.createElement('h2');
                title.className = 'text-base font-bold text-gray-800 leading-tight my-1';
                title.textContent = deal.title;
                
                const bottomMeta = document.createElement('div');
                bottomMeta.className = 'flex items-baseline space-x-2';
                
                const price = document.createElement('span');
                price.className = 'text-lg font-bold text-red-500';
                price.textContent = deal.price || '가격 정보 없음';

                const shipping = document.createElement('span');
                shipping.className = 'text-sm text-gray-600';
                shipping.textContent = deal.shipping;

                bottomMeta.appendChild(price);
                bottomMeta.appendChild(shipping);

                contentWrapper.appendChild(topMeta);
                contentWrapper.appendChild(title);
                contentWrapper.appendChild(bottomMeta);
                
                dealWrapper.appendChild(thumbnail);
                dealWrapper.appendChild(contentWrapper);
                linkContainer.appendChild(dealWrapper);
                hotdealList.appendChild(linkContainer);
            });
        } catch (error) {
            console.error('핫딜 정보를 가져오는 중 오류 발생:', error);
            hotdealList.innerHTML = `<div class="p-4 text-center text-red-500 bg-red-50 rounded-lg shadow">데이터 로딩에 실패했습니다: ${error.message}</div>`;
        }
    };

    sourceButtonsContainer.addEventListener('click', (event) => {
        const button = event.target.closest('button');
        if (button) {
            sourceButtonsContainer.querySelectorAll('.source-btn').forEach(btn => btn.classList.remove('active'));
            button.classList.add('active');
            const selectedSource = button.dataset.source;
            fetchHotDeals(selectedSource);
        }
    });

    fetchHotDeals('all');
});