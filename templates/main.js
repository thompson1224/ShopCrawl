const state = {
    page: 1,
    source: "all",
    totalPages: 1,
    priceRange: "all",
    category: "all",
    shippingFree: false,
    sort: "latest",
    loading: false,
    searchMode: false,
    currentQuery: "",
    currentDeals: [],
};

function sanitizeExternalUrl(value) {
    if (!value) return "#";
    try {
        const parsed = new URL(value, window.location.origin);
        return ["http:", "https:"].includes(parsed.protocol) ? parsed.href : "#";
    } catch {
        return "#";
    }
}

function getElement(id) {
    return document.getElementById(id);
}

function formatCount(value) {
    return new Intl.NumberFormat("ko-KR").format(Number(value) || 0);
}

function getSourceLabel(value) {
    return value === "all" ? "전체" : value;
}

function getTimeAgo(dateString) {
    const date = new Date(dateString);
    if (Number.isNaN(date.getTime())) return "-";
    const diffMs = new Date() - date;
    const minutes = Math.floor(diffMs / 60000);
    const hours = Math.floor(diffMs / 3600000);
    const days = Math.floor(diffMs / 86400000);
    if (minutes < 1) return "방금";
    if (minutes < 60) return `${minutes}분 전`;
    if (hours < 24) return `${hours}시간 전`;
    if (days < 7) return `${days}일 전`;
    return date.toLocaleDateString("ko-KR");
}

function toggleDarkMode() {
    const html = document.documentElement;
    const isDark = html.classList.contains("dark");
    html.classList.toggle("dark");
    localStorage.setItem("theme", isDark ? "light" : "dark");
}

function initDarkMode() {
    const savedTheme = localStorage.getItem("theme");
    const prefersDark = window.matchMedia("(prefers-color-scheme: dark)").matches;
    if (savedTheme === "dark" || (!savedTheme && prefersDark)) {
        document.documentElement.classList.add("dark");
    }
}

function showToast(message, type = "info") {
    const container = getElement("toast-container");
    if (!container) return;
    const toast = document.createElement("div");
    const bgClass = type === "error" ? "bg-red-500" : type === "success" ? "bg-green-600" : "bg-slate-900/90";
    const icon = type === "error" ? "✕" : type === "success" ? "✓" : "i";
    toast.className = `toast px-5 py-3 rounded-2xl text-white shadow-2xl backdrop-blur-md ${bgClass} flex items-center gap-3`;
    toast.innerHTML = `<span class="font-bold">${icon}</span><span class="text-sm">${message}</span>`;
    toast.onclick = () => toast.remove();
    container.appendChild(toast);
    setTimeout(() => {
        toast.style.opacity = "0";
        toast.style.transform = "translateY(10px)";
        toast.style.transition = "all 0.3s ease";
        setTimeout(() => toast.remove(), 300);
    }, 3000);
}

function createFallbackThumbnail() {
    const fallback = document.createElement("div");
    fallback.className = "thumb-fallback";
    fallback.textContent = "◌";
    return fallback;
}

function createSkeletonCard() {
    const card = document.createElement("article");
    card.className = "deal-card skeleton-card";
    card.innerHTML = `
        <div class="deal-link">
            <div class="deal-thumb skeleton-block"></div>
            <div class="deal-body">
                <div class="deal-meta">
                    <div class="skeleton-block rounded-full h-6 w-16"></div>
                    <div class="skeleton-block rounded-full h-6 w-20"></div>
                    <div class="skeleton-block rounded-full h-5 w-14 ml-auto"></div>
                </div>
                <div class="space-y-2">
                    <div class="skeleton-block h-5 rounded-xl"></div>
                    <div class="skeleton-block h-5 rounded-xl w-4/5"></div>
                </div>
                <div class="deal-foot">
                    <div class="deal-price-wrap space-y-2 flex-1">
                        <div class="skeleton-block h-7 rounded-xl w-28"></div>
                        <div class="skeleton-block h-5 rounded-full w-20"></div>
                    </div>
                    <div class="skeleton-block h-11 w-11 rounded-2xl"></div>
                </div>
            </div>
        </div>
    `;
    return card;
}

function createDealCard(deal) {
    const safeLink = sanitizeExternalUrl(deal.link);
    const safeThumb = sanitizeExternalUrl(deal.thumbnail);

    const card = document.createElement("article");
    card.className = "deal-card";

    const link = document.createElement("a");
    link.className = "deal-link";
    link.href = safeLink;
    link.target = "_blank";
    link.rel = "noopener noreferrer";

    const thumb = document.createElement("div");
    thumb.className = "deal-thumb";
    if (safeThumb !== "#") {
        const image = document.createElement("img");
        image.src = `/image-proxy?url=${encodeURIComponent(safeThumb)}&source=${encodeURIComponent(deal.source || "all")}`;
        image.alt = deal.title || "딜 이미지";
        image.loading = "lazy";
        image.onerror = () => {
            thumb.replaceChildren(createFallbackThumbnail());
        };
        thumb.appendChild(image);
    } else {
        thumb.appendChild(createFallbackThumbnail());
    }

    const body = document.createElement("div");
    body.className = "deal-body";

    const meta = document.createElement("div");
    meta.className = "deal-meta";

    const sourceBadge = document.createElement("span");
    sourceBadge.className = "deal-source";
    sourceBadge.textContent = deal.source || "소스";

    const categoryBadge = document.createElement("span");
    categoryBadge.className = "deal-badge";
    categoryBadge.textContent = deal.category || "기타";

    const age = document.createElement("span");
    age.className = "deal-age";
    age.textContent = getTimeAgo(deal.created_at);

    meta.append(sourceBadge, categoryBadge, age);

    const title = document.createElement("h3");
    title.className = "deal-title line-clamp-2";
    title.textContent = deal.title || "제목 없음";

    const foot = document.createElement("div");
    foot.className = "deal-foot";

    const priceWrap = document.createElement("div");
    priceWrap.className = "deal-price-wrap";

    const price = document.createElement("span");
    price.className = "deal-price";
    price.textContent = deal.price || "가격 확인";
    priceWrap.appendChild(price);

    if (deal.shipping) {
        const shipping = document.createElement("span");
        shipping.className = "deal-shipping";
        shipping.textContent = deal.shipping;
        priceWrap.appendChild(shipping);
    }

    const commentBtn = document.createElement("button");
    commentBtn.type = "button";
    commentBtn.className = "comment-btn";
    commentBtn.setAttribute("aria-label", "댓글 열기");
    commentBtn.innerHTML = `
        <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 10h8m-8 4h5m7 6l-3.4-3.4A8 8 0 1018 18.6L22 22"></path>
        </svg>
    `;
    commentBtn.onclick = (event) => {
        event.preventDefault();
        event.stopPropagation();
        openCommentModal(deal.id, deal.title);
    };

    foot.append(priceWrap, commentBtn);
    body.append(meta, title, foot);
    link.append(thumb, body);
    card.appendChild(link);

    return card;
}

function updateSourceButtons() {
    const sourceButtons = getElement("source-buttons");
    if (!sourceButtons) return;
    sourceButtons.querySelectorAll(".source-btn").forEach((button) => {
        const isActive = button.dataset.source === state.source;
        button.classList.toggle("active", isActive);
    });
}

function updateBottomNav(tab) {
    const home = getElement("nav-home");
    const search = getElement("nav-search");
    if (!home || !search) return;
    home.classList.toggle("active", tab === "home");
    search.classList.toggle("active", tab === "search");
}

function updateSummary(deals = [], pagination = null, mode = "feed") {
    const visibleDeals = state.currentDeals.length > 0 ? state.currentDeals : deals;
    const resultCount = pagination ? pagination.total : deals.length;
    const freeShippingCount = visibleDeals.filter((deal) => String(deal.shipping || "").includes("무료")).length;
    const latestDeal = visibleDeals[0] ? getTimeAgo(visibleDeals[0].created_at) : "-";

    const feedTitle = getElement("feedTitleText");
    const feedDescription = getElement("feedDescriptionText");
    const feedResultCount = getElement("feedResultCount");
    const feedSourceLabel = getElement("feedSourceLabel");
    const activeSourceLabel = getElement("activeSourceLabel");
    const heroResultCount = getElement("heroResultCount");
    const heroFreeShippingCount = getElement("heroFreeShippingCount");
    const heroLatestLabel = getElement("heroLatestLabel");
    const statusLabel = getElement("feedStatusLabel");

    if (feedResultCount) feedResultCount.textContent = formatCount(resultCount);
    if (feedSourceLabel) feedSourceLabel.textContent = getSourceLabel(state.source);
    if (activeSourceLabel) activeSourceLabel.textContent = getSourceLabel(state.source);
    if (heroResultCount) heroResultCount.textContent = formatCount(resultCount);
    if (heroFreeShippingCount) heroFreeShippingCount.textContent = formatCount(freeShippingCount);
    if (heroLatestLabel) heroLatestLabel.textContent = latestDeal;

    if (mode === "search") {
        if (feedTitle) feedTitle.textContent = `검색 결과 · ${state.currentQuery}`;
        if (feedDescription) feedDescription.textContent = "검색어 기준 결과입니다.";
        if (feedSourceLabel) feedSourceLabel.textContent = "검색";
        if (statusLabel) statusLabel.textContent = `"${state.currentQuery}" 결과를 보여줍니다.`;
        return;
    }

    if (feedTitle) feedTitle.textContent = "현재 핫딜 피드";
    if (feedDescription) feedDescription.textContent = "선택한 조건 기준 최신 딜입니다.";
    if (statusLabel) statusLabel.textContent = `${getSourceLabel(state.source)} 피드 ${formatCount(resultCount)}건`;
}

function renderEmptyState(message) {
    const list = getElement("hotdeal-list");
    if (!list) return;
    list.innerHTML = `<div class="empty-state col-span-full">${message}</div>`;
}

function renderDeals(deals, append = false) {
    const list = getElement("hotdeal-list");
    if (!list) return;
    if (!append) list.innerHTML = "";
    deals.forEach((deal) => list.appendChild(createDealCard(deal)));
}

function renderLoadingState() {
    const list = getElement("hotdeal-list");
    if (!list) return;
    list.innerHTML = "";
    for (let index = 0; index < 6; index += 1) {
        list.appendChild(createSkeletonCard());
    }
}

function renderPagination(pagination) {
    const container = getElement("pagination");
    if (!container) return;
    container.innerHTML = "";
    if (state.searchMode || !pagination || pagination.total_pages <= 1) return;

    const row = document.createElement("div");
    row.className = "pagination-row";

    const makeButton = (label, targetPage, isActive = false) => {
        const button = document.createElement("button");
        button.type = "button";
        button.textContent = label;
        button.className = `pager-btn${isActive ? " active" : ""}`;
        button.onclick = () => fetchDeals(state.source, targetPage, false);
        return button;
    };

    if (state.page > 1) row.appendChild(makeButton("‹", state.page - 1));
    for (let page = Math.max(1, state.page - 2); page <= Math.min(pagination.total_pages, state.page + 2); page += 1) {
        row.appendChild(makeButton(String(page), page, page === state.page));
    }
    if (state.page < pagination.total_pages) row.appendChild(makeButton("›", state.page + 1));

    container.appendChild(row);
}

async function loadDashboardStats() {
    try {
        const response = await fetch("/api/stats");
        if (!response.ok) return;
        const stats = await response.json();
        const heroTotalDeals = getElement("heroTotalDeals");
        const heroCoverageText = getElement("heroCoverageText");
        if (heroTotalDeals) heroTotalDeals.textContent = formatCount(stats.total);
        if (heroCoverageText) {
            const sources = [
                ["뽐뿌", stats.ppomppu],
                ["루리웹", stats.ruliweb],
                ["Zod", stats.zod],
                ["어미새", stats.eomisae],
                ["퀘이사존", stats.quasarzone],
            ];
            sources.sort((left, right) => (right[1] || 0) - (left[1] || 0));
            const [topSource, topCount] = sources[0];
            heroCoverageText.textContent = `가장 많은 소스는 ${topSource} · ${formatCount(topCount)}건`;
        }
    } catch (error) {
        console.error("통계 로드 실패:", error);
    }
}

async function fetchDeals(source = "all", page = 1, append = false) {
    if (state.loading) return;
    state.loading = true;
    state.source = source;
    state.page = page;
    state.searchMode = false;
    state.currentQuery = "";
    updateSourceButtons();
    if (!append) renderLoadingState();

    const params = new URLSearchParams({
        source,
        page,
        per_page: "20",
        price_range: state.priceRange,
        category: state.category,
        shipping_free: String(state.shippingFree),
        sort: state.sort,
    });

    try {
        const response = await fetch(`/api/hotdeals?${params.toString()}`);
        const data = await response.json();
        const deals = data.deals || [];
        state.totalPages = data.pagination ? data.pagination.total_pages : 1;
        state.currentDeals = append ? state.currentDeals.concat(deals) : deals.slice();

        if (!append && deals.length === 0) {
            renderEmptyState("선택한 조건에 맞는 핫딜이 없습니다.");
            renderPagination(data.pagination);
            updateSummary([], data.pagination, "feed");
            return;
        }

        renderDeals(deals, append);
        renderPagination(data.pagination);
        updateSummary(deals, data.pagination, "feed");
    } catch (error) {
        console.error(error);
        if (!append) renderEmptyState("핫딜 피드를 불러오지 못했습니다.");
        else showToast("추가 로딩에 실패했습니다.", "error");
    } finally {
        state.loading = false;
    }
}

async function performSearch() {
    const input = getElement("searchInput");
    if (!input) return;

    const query = input.value.trim();
    if (!query) {
        showToast("검색어를 입력해주세요.", "info");
        return;
    }

    state.loading = true;
    state.searchMode = true;
    state.currentQuery = query;
    renderLoadingState();

    const params = new URLSearchParams({
        q: query,
        page: "1",
        per_page: "50",
        category: state.category,
        price_range: state.priceRange,
        shipping_free: String(state.shippingFree),
        sort: state.sort,
    });

    try {
        const response = await fetch(`/api/search?${params.toString()}`);
        const data = await response.json();
        const deals = data.deals || [];
        state.currentDeals = deals.slice();
        state.page = 1;
        state.totalPages = data.pagination ? data.pagination.total_pages : 1;

        if (deals.length === 0) {
            renderEmptyState(`"${query}" 검색 결과가 없습니다.`);
            updateSummary([], data.pagination, "search");
            renderPagination(null);
            return;
        }

        renderDeals(deals, false);
        renderPagination(null);
        updateSummary(deals, data.pagination, "search");
        showToast(`"${query}" 검색 결과를 불러왔습니다.`, "success");
    } catch (error) {
        console.error(error);
        renderEmptyState("검색 중 오류가 발생했습니다.");
        showToast("검색 중 오류가 발생했습니다.", "error");
    } finally {
        state.loading = false;
    }
}

function toggleMobilePanel(force) {
    const panel = getElement("mobileQuickPanel");
    const backdrop = getElement("mobileQuickBackdrop");
    if (!panel || !backdrop) return;

    const shouldOpen = typeof force === "boolean" ? force : panel.classList.contains("hidden");
    panel.classList.toggle("hidden", !shouldOpen);
    backdrop.classList.toggle("hidden", !shouldOpen);
}

function closeProfileMenu() {
    const dropdown = document.querySelector(".profile-dropdown");
    const trigger = getElement("profileTrigger");
    if (!dropdown || !trigger) return;
    dropdown.classList.remove("open");
    trigger.setAttribute("aria-expanded", "false");
}

function toggleProfileMenu() {
    const dropdown = document.querySelector(".profile-dropdown");
    const trigger = getElement("profileTrigger");
    if (!dropdown || !trigger) return;
    const isOpen = dropdown.classList.contains("open");
    dropdown.classList.toggle("open", !isOpen);
    trigger.setAttribute("aria-expanded", String(!isOpen));
}

function toggleFilters() {
    const content = getElement("filterContent");
    const icon = getElement("filterToggleIcon");
    if (!content || !icon) return;
    content.classList.toggle("hidden");
    icon.classList.toggle("rotate-180");
}

function switchTab(tab) {
    updateBottomNav(tab);
    toggleMobilePanel(false);

    if (tab === "home") {
        const target = getElement("workspace-start");
        if (target) target.scrollIntoView({ behavior: "smooth", block: "start" });
        return;
    }

    const searchShell = getElement("search-shell");
    if (searchShell) {
        searchShell.scrollIntoView({ behavior: "smooth", block: "start" });
    }
    const searchInput = getElement("searchInput");
    if (searchInput) searchInput.focus();
}

function resetFilters() {
    const categoryFilter = getElement("categoryFilter");
    const priceRangeFilter = getElement("priceRangeFilter");
    const shippingFreeFilter = getElement("shippingFreeFilter");
    const sortOrder = getElement("sortOrder");
    if (!categoryFilter || !priceRangeFilter || !shippingFreeFilter || !sortOrder) return;

    categoryFilter.value = "all";
    priceRangeFilter.value = "all";
    shippingFreeFilter.checked = false;
    sortOrder.value = "latest";

    state.category = "all";
    state.priceRange = "all";
    state.shippingFree = false;
    state.sort = "latest";

    fetchDeals(state.source, 1, false);
}

window.performSearch = performSearch;
window.toggleMobilePanel = toggleMobilePanel;
window.toggleProfileMenu = toggleProfileMenu;
window.toggleFilters = toggleFilters;
window.switchTab = switchTab;
window.resetFilters = resetFilters;
window.toggleDarkMode = toggleDarkMode;

document.addEventListener("DOMContentLoaded", () => {
    initDarkMode();

    const sourceButtons = getElement("source-buttons");
    const categoryFilter = getElement("categoryFilter");
    const priceRangeFilter = getElement("priceRangeFilter");
    const shippingFreeFilter = getElement("shippingFreeFilter");
    const sortOrder = getElement("sortOrder");
    const sentinel = getElement("infinite-scroll-sentinel");
    const mobileMenuBtn = getElement("mobileMenuBtn");
    const mobileBackdrop = getElement("mobileQuickBackdrop");

    if (!sourceButtons || !categoryFilter || !priceRangeFilter || !shippingFreeFilter || !sortOrder) return;

    updateBottomNav("home");
    loadDashboardStats();

    sourceButtons.addEventListener("click", (event) => {
        const button = event.target.closest("button[data-source]");
        if (!button) return;
        fetchDeals(button.dataset.source, 1, false);
    });

    const applyFilters = () => {
        state.category = categoryFilter.value;
        state.priceRange = priceRangeFilter.value;
        state.shippingFree = shippingFreeFilter.checked;
        state.sort = sortOrder.value;
        fetchDeals(state.source, 1, false);
    };

    [categoryFilter, priceRangeFilter, shippingFreeFilter, sortOrder].forEach((element) => {
        element.addEventListener("change", applyFilters);
    });

    document.querySelectorAll("[data-query-chip]").forEach((button) => {
        button.addEventListener("click", () => {
            const input = getElement("searchInput");
            if (!input) return;
            input.value = button.dataset.queryChip || "";
            performSearch();
        });
    });

    document.querySelectorAll("[data-scroll-target]").forEach((button) => {
        button.addEventListener("click", () => {
            const target = getElement(button.dataset.scrollTarget);
            toggleMobilePanel(false);
            if (target) target.scrollIntoView({ behavior: "smooth", block: "start" });
        });
    });

    if (mobileMenuBtn) {
        mobileMenuBtn.addEventListener("click", () => toggleMobilePanel());
    }

    if (mobileBackdrop) {
        mobileBackdrop.addEventListener("click", () => toggleMobilePanel(false));
    }

    document.addEventListener("click", (event) => {
        const target = event.target;
        if (!(target instanceof Element)) return;
        if (!target.closest(".profile-container")) closeProfileMenu();
    });

    document.addEventListener("keydown", (event) => {
        if (event.key !== "Escape") return;
        toggleMobilePanel(false);
        closeProfileMenu();
        if (!getElement("commentModal")?.classList.contains("hidden")) closeCommentModal();
        if (!getElement("telegramModal")?.classList.contains("hidden")) closeTelegramModal();
    });

    if (window.matchMedia("(max-width: 720px)").matches) {
        const filterContent = getElement("filterContent");
        if (filterContent) filterContent.classList.add("hidden");
    }

    if (sentinel) {
        const observer = new IntersectionObserver((entries) => {
            const entry = entries[0];
            if (!entry.isIntersecting || state.loading || state.searchMode || state.page >= state.totalPages) return;
            fetchDeals(state.source, state.page + 1, true);
        }, { threshold: 0.25 });
        observer.observe(sentinel);
    }

    fetchDeals("all", 1, false);
});
