'use strict';

(function () {
    const FAVORITES_STORAGE_KEY = 'accountinox.admin.favorites.v1';
    const SIDEBAR_GROUPS_STORAGE_KEY = 'accountinox.admin.sidebar.groups.v1';
    const RECENT_PAGES_STORAGE_KEY = 'accountinox.admin.recent.v1';
    const WORKSPACE_STORAGE_KEY = 'accountinox.admin.workspace.v1';
    const SAVED_VIEWS_STORAGE_KEY = 'accountinox.admin.saved_views.v1';
    const DENSITY_STORAGE_KEY = 'accountinox.admin.density.v1';

    function normalize(value) {
        return (value || '').toString().trim().toLowerCase();
    }

    function qs(selector, root) {
        return (root || document).querySelector(selector);
    }

    function qsa(selector, root) {
        return Array.from((root || document).querySelectorAll(selector));
    }

    function isInteractiveTarget(target) {
        return Boolean(target.closest('a, button, input, select, textarea, label, summary'));
    }

    function safeReadStorage(key, fallback) {
        try {
            const raw = localStorage.getItem(key);
            if (!raw) {
                return fallback;
            }
            const parsed = JSON.parse(raw);
            return parsed || fallback;
        } catch (_error) {
            return fallback;
        }
    }

    function safeWriteStorage(key, value) {
        try {
            localStorage.setItem(key, JSON.stringify(value));
        } catch (_error) {
            // Ignore storage write failures.
        }
    }

    function initCommandBar() {
        const input = qs('#admin-command-input');
        if (!input) {
            return;
        }
        const clearButton = qs('#admin-command-clear');
        const focusSearchButton = qs('[data-focus-changelist-search]');

        const searchableItems = qsa('[data-admin-search-item]');
        const navItems = qsa('[data-admin-nav-item]');
        const appCards = qsa('.admin-app-card');
        const modelRows = qsa('.admin-model-item');

        const applyFilter = (rawTerm) => {
            const term = normalize(rawTerm);
            const hasTerm = term.length > 0;

            searchableItems.forEach((item) => {
                const text = normalize(item.dataset.adminSearchText || item.textContent);
                const isMatch = !hasTerm || text.includes(term);
                item.classList.toggle('is-filter-hidden', !isMatch);
            });

            navItems.forEach((item) => {
                const text = normalize(item.dataset.adminSearchText || item.textContent);
                const isMatch = !hasTerm || text.includes(term);
                item.classList.toggle('is-filter-hidden', !isMatch);
            });

            appCards.forEach((card) => {
                const modelItemsInCard = qsa('.admin-model-item', card);
                const hasVisibleModel = modelItemsInCard.some((item) => !item.classList.contains('is-filter-hidden'));
                if (!hasTerm) {
                    card.classList.remove('is-filter-hidden');
                    return;
                }
                const cardText = normalize(card.dataset.adminSearchText || card.textContent);
                const showCard = hasVisibleModel || cardText.includes(term);
                card.classList.toggle('is-filter-hidden', !showCard);
            });

            if (hasTerm && modelRows.length) {
                appCards.forEach((card) => {
                    const visibleRows = qsa('.admin-model-item:not(.is-filter-hidden)', card);
                    card.classList.toggle('is-filter-hidden', visibleRows.length === 0);
                });
            }
        };

        input.addEventListener('input', () => {
            applyFilter(input.value);
        });

        input.addEventListener('keydown', (event) => {
            if (event.key === 'Enter') {
                const searchField = qs('#searchbar');
                if (searchField) {
                    event.preventDefault();
                    searchField.focus();
                    searchField.value = input.value;
                }
            }
            if (event.key === 'Escape') {
                input.value = '';
                applyFilter('');
            }
        });

        if (clearButton) {
            clearButton.addEventListener('click', () => {
                input.value = '';
                applyFilter('');
                input.focus();
            });
        }

        if (focusSearchButton) {
            focusSearchButton.addEventListener('click', () => {
                const searchField = qs('#searchbar');
                if (searchField) {
                    searchField.focus();
                }
            });
        }

        document.addEventListener('keydown', (event) => {
            const target = event.target;
            const isTypingContext = target && target.matches && target.matches('input, textarea, select, [contenteditable="true"]');
            if (!isTypingContext && !event.ctrlKey && !event.metaKey && !event.altKey && event.key === '/') {
                event.preventDefault();
                input.focus();
                input.select();
                return;
            }
            if ((event.ctrlKey && event.key === '/') || (event.ctrlKey && event.key.toLowerCase() === 'k')) {
                event.preventDefault();
                input.focus();
                input.select();
            }
        });
    }

    function getFavorites() {
        try {
            const raw = localStorage.getItem(FAVORITES_STORAGE_KEY);
            if (!raw) {
                return [];
            }
            const parsed = JSON.parse(raw);
            if (!Array.isArray(parsed)) {
                return [];
            }
            return parsed.filter((item) => item && item.id && item.label && item.url);
        } catch (_error) {
            return [];
        }
    }

    function setFavorites(items) {
        safeWriteStorage(FAVORITES_STORAGE_KEY, items);
    }

    function initFavorites() {
        const favoriteButtons = qsa('[data-favorite-id][data-favorite-url]');
        const favoritePanels = qsa('[data-favorites-list]');
        if (!favoriteButtons.length && !favoritePanels.length) {
            return;
        }

        const renderFavoritePanels = () => {
            const favorites = getFavorites();
            favoritePanels.forEach((panel) => {
                panel.innerHTML = '';
                if (!favorites.length) {
                    const empty = document.createElement('p');
                    empty.className = 'admin-favorites-empty';
                    empty.textContent = 'هنوز موردی ذخیره نشده است. از ستاره کنار مدل‌ها استفاده کنید.';
                    panel.appendChild(empty);
                    return;
                }
                favorites.forEach((item) => {
                    const row = document.createElement('div');
                    row.className = 'admin-favorite-item';

                    const link = document.createElement('a');
                    link.href = item.url;
                    link.textContent = item.label;
                    link.className = 'admin-favorite-link';

                    const remove = document.createElement('button');
                    remove.type = 'button';
                    remove.className = 'admin-favorite-remove';
                    remove.textContent = 'حذف';
                    remove.setAttribute('aria-label', `حذف علاقه‌مندی ${item.label}`);
                    remove.addEventListener('click', () => {
                        const updated = getFavorites().filter((existing) => existing.id !== item.id);
                        setFavorites(updated);
                        syncFavoriteButtons();
                        renderFavoritePanels();
                    });

                    row.appendChild(link);
                    row.appendChild(remove);
                    panel.appendChild(row);
                });
            });
        };

        const syncFavoriteButtons = () => {
            const favorites = getFavorites();
            const favoriteIds = new Set(favorites.map((item) => item.id));
            favoriteButtons.forEach((button) => {
                const id = button.dataset.favoriteId;
                const selected = favoriteIds.has(id);
                button.textContent = selected ? '★' : '☆';
                button.setAttribute('aria-pressed', selected ? 'true' : 'false');
                button.classList.toggle('is-active', selected);
            });
        };

        favoriteButtons.forEach((button) => {
            button.addEventListener('click', () => {
                const id = button.dataset.favoriteId;
                const label = button.dataset.favoriteLabel || id;
                const url = button.dataset.favoriteUrl;
                if (!id || !url) {
                    return;
                }
                const favorites = getFavorites();
                const exists = favorites.some((item) => item.id === id);
                let updated;
                if (exists) {
                    updated = favorites.filter((item) => item.id !== id);
                } else {
                    updated = favorites.concat([{ id, label, url }]);
                }
                setFavorites(updated);
                syncFavoriteButtons();
                renderFavoritePanels();
            });
        });

        syncFavoriteButtons();
        renderFavoritePanels();
    }

    function initSidebarFilter() {
        const filterInput = qs('[data-admin-nav-filter]') || qs('#nav-filter');
        if (!filterInput) {
            return;
        }
        const navItems = qsa('[data-admin-nav-item]');
        const groups = qsa('.admin-side-group');

        const applyFilter = (rawTerm) => {
            const term = normalize(rawTerm);
            const hasTerm = Boolean(term);

            navItems.forEach((item) => {
                const text = normalize(item.dataset.adminSearchText || item.textContent);
                const isMatch = !hasTerm || text.includes(term);
                item.classList.toggle('is-filter-hidden', !isMatch);
            });

            groups.forEach((group) => {
                const visibleChildren = qsa('[data-admin-nav-item]:not(.is-filter-hidden)', group);
                const shouldShow = visibleChildren.length > 0 || !hasTerm;
                group.classList.toggle('is-filter-hidden', !shouldShow);
                if (hasTerm && shouldShow) {
                    group.open = true;
                }
            });
        };

        filterInput.addEventListener('input', () => {
            applyFilter(filterInput.value);
        });

        filterInput.addEventListener('keydown', (event) => {
            if (event.key === 'Escape') {
                filterInput.value = '';
                applyFilter('');
            }
        });
    }

    function initSidebarGroupState() {
        const groups = qsa('.admin-side-group[data-group-id]');
        if (!groups.length) {
            return;
        }

        const state = safeReadStorage(SIDEBAR_GROUPS_STORAGE_KEY, {});
        groups.forEach((group) => {
            const groupId = group.dataset.groupId;
            if (!groupId) {
                return;
            }
            if (Object.prototype.hasOwnProperty.call(state, groupId)) {
                group.open = Boolean(state[groupId]);
            }
            group.addEventListener('toggle', () => {
                state[groupId] = group.open;
                safeWriteStorage(SIDEBAR_GROUPS_STORAGE_KEY, state);
            });
        });
    }

    function initChangelistRowClick() {
        const rows = qsa('#result_list tbody tr');
        rows.forEach((row) => {
            const primaryLink = qs('th a, td a', row);
            if (!primaryLink) {
                return;
            }
            row.classList.add('is-row-link');
            row.addEventListener('click', (event) => {
                if (isInteractiveTarget(event.target)) {
                    return;
                }
                window.location.href = primaryLink.href;
            });
        });
    }

    function initFilterPanelToggle() {
        const toggleButton = qs('[data-filter-toggle]');
        const changelist = qs('#changelist');
        const filterPanel = qs('#changelist-filter');
        if (!toggleButton || !changelist || !filterPanel) {
            return;
        }

        const setOpen = (open) => {
            changelist.classList.toggle('filters-open', open);
            toggleButton.setAttribute('aria-expanded', open ? 'true' : 'false');
        };

        toggleButton.addEventListener('click', () => {
            const isOpen = changelist.classList.contains('filters-open');
            setOpen(!isOpen);
        });

        if (window.innerWidth <= 992) {
            setOpen(false);
        }

        document.addEventListener('keydown', (event) => {
            if (event.key === 'Escape') {
                setOpen(false);
            }
        });
    }

    function initInlineCollapseControls() {
        const inlineGroups = qsa('.inline-group');
        if (!inlineGroups.length) {
            return;
        }

        const setCollapsed = (group, collapsed) => {
            group.classList.toggle('is-collapsed', collapsed);
        };

        inlineGroups.forEach((group) => {
            const heading = qs('h2', group);
            if (!heading) {
                return;
            }
            const toggle = document.createElement('button');
            toggle.type = 'button';
            toggle.className = 'admin-inline-toggle';
            toggle.textContent = 'جمع کردن';
            toggle.addEventListener('click', () => {
                const collapsed = !group.classList.contains('is-collapsed');
                setCollapsed(group, collapsed);
                toggle.textContent = collapsed ? 'باز کردن' : 'جمع کردن';
            });
            heading.appendChild(toggle);
        });

        const expandAllButton = qs('[data-inline-expand]');
        const collapseAllButton = qs('[data-inline-collapse]');

        if (expandAllButton) {
            expandAllButton.addEventListener('click', () => {
                inlineGroups.forEach((group) => setCollapsed(group, false));
                qsa('.admin-inline-toggle').forEach((button) => {
                    button.textContent = 'جمع کردن';
                });
            });
        }

        if (collapseAllButton) {
            collapseAllButton.addEventListener('click', () => {
                inlineGroups.forEach((group) => setCollapsed(group, true));
                qsa('.admin-inline-toggle').forEach((button) => {
                    button.textContent = 'باز کردن';
                });
            });
        }
    }

    function initErrorSummaryFocus() {
        const summary = qs('.admin-error-summary');
        if (summary) {
            summary.focus();
        }
    }

    function initEscapeClosePanels() {
        document.addEventListener('keydown', (event) => {
            if (event.key !== 'Escape') {
                return;
            }

            const changelist = qs('#changelist');
            if (changelist && changelist.classList.contains('filters-open')) {
                changelist.classList.remove('filters-open');
                const toggleButton = qs('[data-filter-toggle]');
                if (toggleButton) {
                    toggleButton.setAttribute('aria-expanded', 'false');
                }
            }

            const commandInput = qs('#admin-command-input');
            if (commandInput && commandInput.value) {
                commandInput.value = '';
                commandInput.dispatchEvent(new Event('input', { bubbles: true }));
            }

            qsa('[data-admin-panel][open], .admin-more-actions[open]').forEach((panel) => {
                panel.open = false;
            });
        });
    }

    function applyDensity(value) {
        const compact = value === 'compact';
        document.body.classList.toggle('admin-density-compact', compact);
    }

    function initDensityToggle() {
        const buttons = qsa('[data-density-toggle]');
        const stored = safeReadStorage(DENSITY_STORAGE_KEY, { mode: 'comfortable' });
        const initialMode = stored && stored.mode === 'compact' ? 'compact' : 'comfortable';
        applyDensity(initialMode);

        if (!buttons.length) {
            return;
        }

        const syncButtons = () => {
            const isCompact = document.body.classList.contains('admin-density-compact');
            buttons.forEach((button) => {
                button.setAttribute('aria-pressed', isCompact ? 'true' : 'false');
                button.textContent = isCompact ? 'نمای راحت' : 'نمای فشرده';
            });
        };

        buttons.forEach((button) => {
            button.addEventListener('click', () => {
                const isCompact = document.body.classList.contains('admin-density-compact');
                const nextMode = isCompact ? 'comfortable' : 'compact';
                applyDensity(nextMode);
                safeWriteStorage(DENSITY_STORAGE_KEY, { mode: nextMode });
                syncButtons();
            });
        });

        syncButtons();
    }

    function initActiveFilterChips() {
        const container = qs('[data-active-filter-chips]');
        if (!container) {
            return;
        }
        const params = new URLSearchParams(window.location.search);
        const ignored = new Set([
            'q',
            'p',
            'o',
            'ot',
            'all',
            '_popup',
            '_to_field',
            '_facets',
            '_changelist_filters',
        ]);

        const labelMap = {
            is_active__exact: 'وضعیت',
            assigned_to__id__exact: 'اپراتور',
            has_unread: 'خوانده‌نشده',
            has_active_session: 'جلسه فعال',
            paid__exact: 'پرداخت',
            success__exact: 'نتیجه',
            published__exact: 'انتشار',
            score__exact: 'امتیاز',
            score: 'امتیاز',
            failed_payment: 'پرداخت ناموفق',
            provider: 'درگاه',
            window: 'بازه زمانی',
        };

        const activeItems = [];
        params.forEach((value, key) => {
            if (ignored.has(key) || value === '' || value == null) {
                return;
            }
            activeItems.push({ key, value });
        });

        if (!activeItems.length) {
            container.innerHTML = '';
            return;
        }

        const fragment = document.createDocumentFragment();
        activeItems.forEach((item) => {
            const chip = document.createElement('a');
            chip.className = 'admin-active-filter-chip';

            const label = labelMap[item.key] || item.key;
            chip.textContent = `${label}: ${item.value} ×`;

            const next = new URLSearchParams(window.location.search);
            const values = next.getAll(item.key).filter((value) => value !== item.value);
            next.delete(item.key);
            values.forEach((value) => next.append(item.key, value));

            const query = next.toString();
            chip.href = query ? `${window.location.pathname}?${query}` : window.location.pathname;
            chip.setAttribute('aria-label', `حذف فیلتر ${label}`);
            fragment.appendChild(chip);
        });

        const clearAll = document.createElement('a');
        clearAll.className = 'admin-active-filter-clear';
        clearAll.textContent = 'پاک کردن همه';
        clearAll.href = window.location.pathname;
        clearAll.setAttribute('aria-label', 'حذف همه فیلترهای فعال');
        fragment.appendChild(clearAll);

        container.innerHTML = '';
        container.appendChild(fragment);
    }

    function initTransactionProviderChips() {
        if (!document.body.classList.contains('model-transactionlog')) {
            return;
        }
        const chipsRoot = qs('.admin-filter-chips');
        if (!chipsRoot) {
            return;
        }
        const providerLinks = qsa('#changelist-filter a[href*="provider="]');
        if (!providerLinks.length) {
            return;
        }

        const existingHrefs = new Set(
            qsa('a.admin-filter-chip', chipsRoot).map((link) => link.getAttribute('href') || '')
        );
        const added = new Set();
        let count = 0;
        providerLinks.forEach((link) => {
            if (count >= 4) {
                return;
            }
            const href = link.getAttribute('href') || '';
            const text = (link.textContent || '').trim();
            if (!href || !text || existingHrefs.has(href) || added.has(href)) {
                return;
            }
            const chip = document.createElement('a');
            chip.className = 'admin-filter-chip';
            chip.href = href;
            chip.textContent = `درگاه: ${text}`;
            chipsRoot.appendChild(chip);
            added.add(href);
            count += 1;
        });
    }

    function initWorkspaceSwitcher() {
        const root = qs('[data-workspace-switcher]');
        if (!root) {
            return;
        }
        const tabs = qsa('[data-workspace-tab]', root);
        const panels = qsa('[data-workspace-panel]', root);
        if (!tabs.length || !panels.length) {
            return;
        }

        const activate = (workspaceId) => {
            tabs.forEach((tab) => {
                const isActive = tab.dataset.workspaceTab === workspaceId;
                tab.classList.toggle('is-active', isActive);
                tab.setAttribute('aria-selected', isActive ? 'true' : 'false');
            });
            panels.forEach((panel) => {
                const isActive = panel.dataset.workspacePanel === workspaceId;
                panel.classList.toggle('is-active', isActive);
                panel.hidden = !isActive;
            });
            safeWriteStorage(WORKSPACE_STORAGE_KEY, { id: workspaceId });
        };

        const preferredWorkspace = root.dataset.defaultWorkspace || '';
        const hasPreferredWorkspace = tabs.some((tab) => tab.dataset.workspaceTab === preferredWorkspace);
        const defaultWorkspace = hasPreferredWorkspace ? preferredWorkspace : tabs[0].dataset.workspaceTab;
        const storedState = safeReadStorage(WORKSPACE_STORAGE_KEY, {});
        const storedWorkspace = storedState && storedState.id;
        const hasStoredWorkspace = tabs.some((tab) => tab.dataset.workspaceTab === storedWorkspace);
        activate(hasStoredWorkspace ? storedWorkspace : defaultWorkspace);

        tabs.forEach((tab) => {
            tab.addEventListener('click', () => {
                activate(tab.dataset.workspaceTab);
            });
        });
    }

    function trackRecentAdminPage() {
        if (!window.location.pathname.startsWith('/admin/')) {
            return;
        }
        if (
            window.location.pathname.includes('/admin/login')
            || window.location.pathname.includes('/admin/logout')
            || window.location.pathname.includes('/admin/jsi18n')
        ) {
            return;
        }

        const heading = qs('#content h1');
        const title = heading ? heading.textContent.trim() : document.title;
        const entry = {
            url: `${window.location.pathname}${window.location.search}`,
            title: title || 'صفحه مدیریت',
            timestamp: new Date().toISOString(),
        };

        const items = safeReadStorage(RECENT_PAGES_STORAGE_KEY, []);
        const deduped = items.filter((item) => item && item.url !== entry.url);
        const updated = [entry].concat(deduped).slice(0, 5);
        safeWriteStorage(RECENT_PAGES_STORAGE_KEY, updated);
    }

    function renderRecentAdminPages() {
        const container = qs('[data-recent-admin-list]');
        if (!container) {
            return;
        }
        const items = safeReadStorage(RECENT_PAGES_STORAGE_KEY, []);
        container.innerHTML = '';
        if (!items.length) {
            const empty = document.createElement('p');
            empty.className = 'admin-favorites-empty';
            empty.textContent = 'هنوز صفحه‌ای ثبت نشده است.';
            container.appendChild(empty);
            return;
        }

        const fragment = document.createDocumentFragment();
        items.forEach((item) => {
            if (!item || !item.url) {
                return;
            }
            const row = document.createElement('a');
            row.className = 'admin-recent-item';
            row.href = item.url;
            row.textContent = item.title || item.url;
            fragment.appendChild(row);
        });
        container.appendChild(fragment);
    }

    function getSavedViews() {
        const items = safeReadStorage(SAVED_VIEWS_STORAGE_KEY, []);
        if (!Array.isArray(items)) {
            return [];
        }
        return items.filter((item) => item && item.id && item.model && typeof item.query === 'string');
    }

    function setSavedViews(items) {
        safeWriteStorage(SAVED_VIEWS_STORAGE_KEY, items);
    }

    function scopeForModel(modelKey) {
        if (!modelKey) {
            return 'settings';
        }
        if (modelKey.startsWith('support.')) {
            return 'support';
        }
        if (modelKey === 'shop.order' || modelKey === 'shop.transactionlog') {
            return 'orders';
        }
        if (modelKey.startsWith('shop.')) {
            return 'products';
        }
        if (modelKey.startsWith('blog.')) {
            return 'blog';
        }
        return 'settings';
    }

    function currentChangelistQuery() {
        const params = new URLSearchParams(window.location.search);
        params.delete('p');
        return params.toString();
    }

    function renderPinnedViewsOnDashboard() {
        const containers = qsa('[data-pinned-views][data-pinned-scope]');
        if (!containers.length) {
            return;
        }
        const pinned = getSavedViews().filter((view) => view.pinned);

        containers.forEach((container) => {
            const scope = container.dataset.pinnedScope || '';
            const scoped = pinned.filter((view) => (view.scope || scopeForModel(view.model)) === scope).slice(0, 6);
            container.innerHTML = '';
            if (!scoped.length) {
                const empty = document.createElement('span');
                empty.className = 'admin-pinned-empty';
                empty.textContent = 'نمای سنجاق‌شده‌ای وجود ندارد.';
                container.appendChild(empty);
                return;
            }

            scoped.forEach((view) => {
                const link = document.createElement('a');
                link.className = 'admin-command-chip admin-pinned-view-chip';
                link.href = `${view.path || '/admin/'}${view.query ? `?${view.query}` : ''}`;
                link.textContent = view.name;
                container.appendChild(link);
            });
        });
    }

    function initSavedViews() {
        const root = qs('[data-saved-views-root]');
        if (!root) {
            renderPinnedViewsOnDashboard();
            return;
        }

        const modelKey = root.dataset.savedModel || '';
        const list = qs('[data-saved-view-list]', root);
        const nameInput = qs('#admin-saved-view-name', root);
        const saveButton = qs('[data-save-current-view]', root);
        if (!modelKey || !list || !nameInput || !saveButton) {
            renderPinnedViewsOnDashboard();
            return;
        }

        const render = () => {
            const views = getSavedViews().filter((view) => view.model === modelKey);
            list.innerHTML = '';
            if (!views.length) {
                const empty = document.createElement('span');
                empty.className = 'admin-pinned-empty';
                empty.textContent = 'نمای ذخیره‌شده‌ای ندارید.';
                list.appendChild(empty);
                return;
            }

            views.forEach((view) => {
                const row = document.createElement('div');
                row.className = 'admin-saved-view-item';

                const link = document.createElement('a');
                link.className = 'admin-filter-chip';
                link.href = `${view.path || window.location.pathname}${view.query ? `?${view.query}` : ''}`;
                link.textContent = view.name;

                const pinButton = document.createElement('button');
                pinButton.type = 'button';
                pinButton.className = 'admin-saved-view-pin';
                pinButton.textContent = view.pinned ? 'سنجاق‌شده' : 'سنجاق';
                pinButton.setAttribute('aria-pressed', view.pinned ? 'true' : 'false');
                pinButton.addEventListener('click', () => {
                    const next = getSavedViews().map((item) => {
                        if (item.id !== view.id) {
                            return item;
                        }
                        return { ...item, pinned: !item.pinned };
                    });
                    setSavedViews(next);
                    render();
                    renderPinnedViewsOnDashboard();
                });

                const removeButton = document.createElement('button');
                removeButton.type = 'button';
                removeButton.className = 'admin-saved-view-remove';
                removeButton.textContent = 'حذف';
                removeButton.addEventListener('click', () => {
                    const next = getSavedViews().filter((item) => item.id !== view.id);
                    setSavedViews(next);
                    render();
                    renderPinnedViewsOnDashboard();
                });

                row.appendChild(link);
                row.appendChild(pinButton);
                row.appendChild(removeButton);
                list.appendChild(row);
            });
        };

        saveButton.addEventListener('click', () => {
            const viewName = nameInput.value.trim() || `نمای ${new Date().toLocaleDateString('fa-IR')}`;
            const query = currentChangelistQuery();
            const path = window.location.pathname;
            const scope = scopeForModel(modelKey);
            const views = getSavedViews();
            const existing = views.find((view) => view.model === modelKey && view.query === query && view.path === path);

            let next;
            if (existing) {
                next = views.map((view) => (view.id === existing.id ? { ...view, name: viewName } : view));
            } else {
                next = views.concat([
                    {
                        id: `${Date.now()}_${Math.random().toString(36).slice(2, 8)}`,
                        model: modelKey,
                        name: viewName,
                        query,
                        path,
                        scope,
                        pinned: false,
                        created_at: new Date().toISOString(),
                    },
                ]);
            }

            setSavedViews(next);
            nameInput.value = '';
            render();
            renderPinnedViewsOnDashboard();
        });

        render();
        renderPinnedViewsOnDashboard();
    }

    function init() {
        initCommandBar();
        initFavorites();
        initSidebarFilter();
        initSidebarGroupState();
        initChangelistRowClick();
        initFilterPanelToggle();
        initInlineCollapseControls();
        initErrorSummaryFocus();
        initEscapeClosePanels();
        initActiveFilterChips();
        initTransactionProviderChips();
        initWorkspaceSwitcher();
        trackRecentAdminPage();
        renderRecentAdminPages();
        initSavedViews();
        initDensityToggle();
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
