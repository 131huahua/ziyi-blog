// ========== ZIYI 博客动效 ==========

// 0) HELLO ZIYI 欢迎动画：只在「首页」且本次会话第一次进入时播放
//    （浏览器恢复标签页/直接打开其他页面时不播，避免在文章页等地方开场）
const mask = document.getElementById('welcomeMask');
if (mask) {
    const isHome = location.pathname === '/';
    const isFirst = !sessionStorage.getItem('ziyi_welcomed');
    if (isHome && isFirst) {
        sessionStorage.setItem('ziyi_welcomed', '1');
        mask.style.display = 'flex';           // 显示并播放动画
        setTimeout(() => mask.remove(), 4000); // 播完移除，避免遮挡
    } else {
        mask.remove();
    }
}

// 1) 顶栏滚动变色：首屏透明白字 → 滚动后超薄磨砂深字
const header = document.getElementById('topNavHeader');
const logo = document.getElementById('navLogo');
const navLinks = document.querySelectorAll('.nav-link');
const searchBtn = document.getElementById('searchBtn');
const githubIcon = document.getElementById('githubIcon');
const mobileMenuBtn = document.getElementById('mobileMenuBtn');
const darkToggle = document.getElementById('darkToggle');
const mobileMenu = document.getElementById('mobileMenu');

function applyNav(scrolled) {
    if (!header) return;
    // 11.0：顶栏固定深色底，文字恒亮色，滚动只收缩 padding
    if (scrolled) {
        header.classList.add('is-scrolled');
    } else {
        header.classList.remove('is-scrolled');
    }
}

if (header) {
    // 只有带全屏深色 Hero 的页面（首页）在顶部才用透明+白字；
    // 其他页面（白底）或滚动离开 Hero 后，一律磨砂深字，避免白字消失
    const hasHero = !!document.querySelector('.hero-full');
    window.addEventListener('scroll', () => {
        applyNav(!(hasHero && window.scrollY <= 50));
    }, { passive: true });
    if (!hasHero) applyNav(true);
}

// 16.0 移动端全屏菜单（按钮 onclick 已直接调 toggleMobileMenu，此处兜底）
if (mobileMenuBtn) {
    mobileMenuBtn.addEventListener('click', () => window.toggleMobileMenu && window.toggleMobileMenu());
}

// 内页顶栏（文章/说说/随笔/关于）：向下滚动隐藏，向上滚动呼出
const innerNav = document.getElementById('innerNavHeader');
if (innerNav) {
    let lastScrollY = window.scrollY;
    window.addEventListener('scroll', () => {
        const y = window.scrollY;
        if (y > lastScrollY && y > 80) {
            innerNav.classList.add('inner-nav-hidden');
        } else {
            innerNav.classList.remove('inner-nav-hidden');
        }
        lastScrollY = y;
    }, { passive: true });
}

document.addEventListener('keydown', (e) => {
    // Ctrl/Cmd + K：打开搜索模态框
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault();
        openSearch();
    }
    // ESC：关闭搜索 / 移动菜单
    if (e.key === 'Escape') {
        window.closeSearch && window.closeSearch();
        if (mobileMenu) mobileMenu.classList.add('hidden');
    }
});

// 2b) 17.0 日夜双模：localStorage.theme 持久化 + ☀️/🌙 图标切换（Anti-FART）
function syncDarkIcon() {
    const isDark = document.documentElement.classList.contains('dark');
    const icon = document.getElementById('themeModeIcon') || darkToggle;
    if (icon) icon.textContent = isDark ? '🌙' : '☀️';
}
function toggleThemeMode() {
    const isDark = document.documentElement.classList.toggle('dark');
    localStorage.setItem('theme', isDark ? 'dark' : 'light');
    localStorage.removeItem('pine-night');
    syncDarkIcon();
}
if (darkToggle) {
    darkToggle.addEventListener('click', toggleThemeMode);
    syncDarkIcon();
}
window.toggleThemeMode = toggleThemeMode;
// 16.0 移动端全屏菜单开关（淡入淡出 + 底页滚动锁）
function toggleMobileMenu() {
    const menu = document.getElementById('mobileMenuModal');
    if (!menu) return;
    if (menu.classList.contains('hidden')) {
        menu.classList.remove('hidden');
        setTimeout(() => menu.classList.remove('opacity-0'), 10);
        document.body.style.overflow = 'hidden';
    } else {
        menu.classList.add('opacity-0');
        setTimeout(() => {
            menu.classList.add('hidden');
            document.body.style.overflow = '';
        }, 300);
    }
}
window.toggleMobileMenu = toggleMobileMenu;

// 2c) 全站搜索模态框（Raycast 风格）：放大镜 / Ctrl+⌘K 唤起，实时搜索
const searchModal = document.getElementById('searchModal');
const modalSearchInput = document.getElementById('modalSearchInput');
const searchResults = document.getElementById('searchResults');

function openSearch() {
    if (!searchModal) return;
    searchModal.classList.remove('hidden');
    searchModal.classList.add('flex');
    document.body.style.overflow = 'hidden';
    setTimeout(() => modalSearchInput && modalSearchInput.focus(), 50);
}
window.closeSearch = function () {
    if (!searchModal) return;
    searchModal.classList.add('hidden');
    searchModal.classList.remove('flex');
    document.body.style.overflow = '';
};

// 所有放大镜入口（首页/内页）
document.querySelectorAll('#searchBtn, a[title*="搜索"]').forEach((el) => {
    el.addEventListener('click', (e) => {
        e.preventDefault();
        openSearch();
    });
});

if (modalSearchInput && searchResults) {
    const escapeHtml = (s) => s.replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
    let searchTimer = null;
    modalSearchInput.addEventListener('input', () => {
        clearTimeout(searchTimer);
        const q = modalSearchInput.value.trim();
        if (!q) {
            searchResults.innerHTML = '<p class="text-xs text-gray-400 text-center py-8 font-light">输入关键词开始搜索…</p>';
            return;
        }
        searchTimer = setTimeout(async () => {
            try {
                const res = await fetch('/api/search?q=' + encodeURIComponent(q));
                const items = await res.json();
                if (!items.length) {
                    searchResults.innerHTML = '<p class="text-xs text-gray-400 text-center py-8 font-light">没有找到相关内容</p>';
                    return;
                }
                searchResults.innerHTML = items.map((it) => `
                    <a href="/post/${it.id}" class="flex items-center gap-3 p-3 rounded-xl hover:bg-gray-50  transition">
                        ${it.cover ? `<img src="${it.cover}" class="w-10 h-8 rounded-lg object-cover">` : '<div class="w-10 h-8 rounded-lg bg-gray-100 "></div>'}
                        <div class="min-w-0">
                            <p class="text-sm font-medium text-gray-800  truncate">${escapeHtml(it.title)}</p>
                            <p class="text-[10px] text-gray-400 mt-0.5"># ${escapeHtml(it.tags || '未分类')}</p>
                        </div>
                    </a>`).join('');
            } catch (e) {
                searchResults.innerHTML = '<p class="text-xs text-gray-400 text-center py-8 font-light">搜索出错了…</p>';
            }
        }, 200);
    });
}

// 2) 滚动浮现（函数化：初始 + HTMX 切页后都要调用）
function observeReveals() {
    const io = new IntersectionObserver((entries) => {
        entries.forEach((e) => {
            if (e.isIntersecting) {
                e.target.classList.add(e.target.classList.contains('reveal-item') ? 'active' : 'visible');
                io.unobserve(e.target);
            }
        });
    }, { threshold: 0.1 });
    document.querySelectorAll('.reveal, .reveal-item').forEach((el) => io.observe(el));
}
observeReveals();

// 3) Hero 视差（函数化）
function bindHeroParallax() {
    const heroTitle = document.getElementById('heroTitle');
    const heroFull = document.querySelector('.hero-full');
    if (heroTitle && heroFull && !heroTitle.dataset.px) {
        heroTitle.dataset.px = '1';
        const heroH = heroFull.offsetHeight;
        window.addEventListener('scroll', () => {
            const y = window.scrollY;
            if (y <= heroH) {
                heroTitle.style.transform = `translateY(${y * 0.25}px)`;
                heroTitle.style.opacity = Math.max(0, 1 - (y / heroH) * 1.2);
            }
        }, { passive: true });
    }
}
bindHeroParallax();

// 4) 文章封面视差（函数化）
function bindPostParallax() {
    const hero = document.querySelector('.post-hero');
    if (hero && !hero.dataset.px) {
        hero.dataset.px = '1';
        const img = hero.querySelector('img');
        window.addEventListener('scroll', () => {
            const y = window.scrollY;
            if (y < window.innerHeight * 1.2) {
                img.style.transform = `translateY(${y * 0.35}px)`;
            }
        }, { passive: true });
    }
}
bindPostParallax();

// 4b) 晨雾沉浸式极致播放器（Dynamic Island / Apple 风：SVG 图标 + 律动条 + 歌单）
const SVG_PLAY = '<svg class="w-4 h-4 fill-current ml-0.5" viewBox="0 0 24 24"><path d="M8 5v14l11-7z"/></svg>';
const SVG_PAUSE = '<svg class="w-4 h-4 fill-current" viewBox="0 0 24 24"><path d="M6 19h4V5H6v14zm8-14v14h4V5h-4z"/></svg>';
const bgAudio = document.getElementById('bgAudio');
const navPlayIcon = document.getElementById('navPlayIcon');
const bigPlayIcon = document.getElementById('bigPlayIcon');
const navEqContainer = document.getElementById('navEqContainer');
const playerProgress = document.getElementById('progressBar');
const lyricContainer = document.getElementById('lyricContainer');
let playlist = window.BGM_PLAYLIST || [];
let currentTrackIndex = 0;
let lyricsData = [];

if (bgAudio && playlist.length) {
    const formatTime = (sec) => {
        if (!isFinite(sec)) return '00:00';
        const m = Math.floor(sec / 60), s = Math.floor(sec % 60);
        return (m < 10 ? '0' : '') + m + ':' + (s < 10 ? '0' : '') + s;
    };

    // 加载曲目 + 封面同步 + 歌词（lrc 地址异步加载）
    function loadTrack(index, autoPlay = false) {
        const track = playlist[index];
        if (!track) return;
        bgAudio.src = track.src;
        const label = (track.artist ? track.artist + ' - ' : '') + track.title;
        document.getElementById('navSongTitle').innerText = track.title;
        document.getElementById('bigSongTitle').innerText = track.title;
        document.getElementById('bigArtist').innerText = track.artist || '晨雾电台';
        document.getElementById('bigAlbumCover').src = track.cover;
        document.getElementById('bgGlow').src = track.cover;
        sessionStorage.setItem('bgm_track_index', String(index));
        if (track.lrc) loadLyricsFromUrl(track.lrc); else parseLRC('');
        if (autoPlay) {
            bgAudio.play().then(() => { sessionStorage.setItem('bgm_playing', 'true'); updateUI(true); }).catch(() => updateUI(false));
        }
    }

    // 解析 LRC 文本（[mm:ss.xx]）
    function parseLRC(lrcText) {
        lyricsData = [];
        const lines = (lrcText || '').split('\n');
        const timeReg = /\[(\d{2}):(\d{2})\.(\d{2,3})\]/;
        lines.forEach((line) => {
            const m = timeReg.exec(line);
            if (m) {
                const time = parseInt(m[1]) * 60 + parseInt(m[2]) + (m[3].length === 2 ? parseInt(m[3]) / 100 : parseInt(m[3]) / 1000);
                const text = line.replace(timeReg, '').trim();
                if (text) lyricsData.push({ time, text });
            }
        });
        if (lyricContainer) {
            lyricContainer.innerHTML = lyricsData.length
                ? lyricsData.map((item, idx) => `<p id="lrc-line-${idx}" class="text-xs text-slate-500/80 dark:text-white/35 font-light transition-all duration-300 py-1">${item.text.replace(/</g, '&lt;')}</p>`).join('')
                : '<p class="text-xs text-slate-500/80 dark:text-white/35 font-light">~ 暂无歌词 ~</p>';
        }
    }

    // 异步加载 .lrc 文件
    async function loadLyricsFromUrl(url) {
        try {
            const res = await fetch(url);
            parseLRC(await res.text());
        } catch (e) { parseLRC(''); }
    }

    // 初始化：恢复状态
    const savedIndex = sessionStorage.getItem('bgm_track_index');
    if (savedIndex !== null && playlist[savedIndex]) currentTrackIndex = parseInt(savedIndex);
    const track = playlist[currentTrackIndex];
    bgAudio.src = track.src;
    document.getElementById('navSongTitle').innerText = track.title;
    document.getElementById('bigSongTitle').innerText = track.title;
    document.getElementById('bigArtist').innerText = track.artist || '晨雾电台';
    document.getElementById('bigAlbumCover').src = track.cover;
    document.getElementById('bgGlow').src = track.cover;
    if (track.lrc) loadLyricsFromUrl(track.lrc); else parseLRC('');

    // 拉取完整歌单（static/audio/ 自动扫描）
    fetch('/api/playlist').then((r) => r.json()).then((list) => {
        if (list && list.length) {
            playlist = list;
            const idx = sessionStorage.getItem('bgm_track_index');
            currentTrackIndex = (idx !== null && list[idx]) ? parseInt(idx) : 0;
            loadTrack(currentTrackIndex, false);
        }
    }).catch(() => {});

    const savedVol = sessionStorage.getItem('bgm_volume');
    bgAudio.volume = savedVol !== null ? parseFloat(savedVol) : 0.5;
    const bigVolume = document.getElementById('bigVolume');
    if (bigVolume) bigVolume.value = String(bgAudio.volume);

    const savedTime = sessionStorage.getItem('bgm_time');
    if (savedTime && isFinite(parseFloat(savedTime))) {
        const t = parseFloat(savedTime);
        const seek = () => { if (isFinite(bgAudio.duration) && t < bgAudio.duration - 1) bgAudio.currentTime = t; };
        if (bgAudio.readyState >= 1) seek(); else bgAudio.addEventListener('loadedmetadata', seek, { once: true });
    }
    if (sessionStorage.getItem('bgm_playing') === 'true') {
        bgAudio.play().then(() => updateUI(true)).catch(() => { sessionStorage.setItem('bgm_playing', 'false'); updateUI(false); });
    }

    // 播放/暂停 / 切歌 / 进度 / 音量
    window.togglePlay = function (e) {
        if (e) e.stopPropagation();
        if (bgAudio.paused) {
            bgAudio.play().then(() => { sessionStorage.setItem('bgm_playing', 'true'); updateUI(true); }).catch(() => updateUI(false));
        } else {
            bgAudio.pause();
            sessionStorage.setItem('bgm_playing', 'false');
            updateUI(false);
        }
    };
    window.nextTrack = function () { currentTrackIndex = (currentTrackIndex + 1) % playlist.length; loadTrack(currentTrackIndex, true); };
    window.prevTrack = function () { currentTrackIndex = (currentTrackIndex - 1 + playlist.length) % playlist.length; loadTrack(currentTrackIndex, true); };
    window.seekAudio = function (val) { if (bgAudio.duration) bgAudio.currentTime = (val / 100) * bgAudio.duration; };
    window.adjustVolume = function (val) { bgAudio.volume = parseFloat(val); sessionStorage.setItem('bgm_volume', String(val)); };

    // 时间同步：进度条 + 歌词高亮滚动 + Mini 单行
    bgAudio.addEventListener('timeupdate', () => {
        const cur = bgAudio.currentTime;
        const dur = bgAudio.duration || 1;
        if (playerProgress) playerProgress.value = String((cur / dur) * 100);
        document.getElementById('currentTimeText').innerText = formatTime(cur);
        document.getElementById('durationText').innerText = formatTime(dur);
        sessionStorage.setItem('bgm_time', String(cur));

        for (let i = 0; i < lyricsData.length; i++) {
            if (cur >= lyricsData[i].time && (!lyricsData[i + 1] || cur < lyricsData[i + 1].time)) {
                if (lyricContainer) {
                    lyricContainer.querySelectorAll('p').forEach((p) => { p.className = 'text-xs text-slate-500/80 dark:text-white/35 font-light transition-all duration-300 py-1 scale-95 opacity-60'; });
                    const activeLine = document.getElementById('lrc-line-' + i);
                    if (activeLine) {
                        activeLine.className = 'text-xs md:text-sm text-emerald-700 dark:text-emerald-400 font-bold transition-all duration-300 py-1 scale-105 opacity-100';
                        lyricContainer.scrollTop = activeLine.offsetTop - lyricContainer.offsetTop - 50;
                    }
                }
                break;
            }
        }
    });
    bgAudio.addEventListener('ended', () => { nextTrack(); });
    bgAudio.addEventListener('error', () => {
        updateUI(false);
    });

    // UI 状态：SVG 图标切换 + 律动条
    function updateUI(isPlaying) {
        if (navPlayIcon) navPlayIcon.innerHTML = isPlaying ? SVG_PAUSE : SVG_PLAY;
        if (bigPlayIcon) bigPlayIcon.innerHTML = isPlaying ? SVG_PAUSE : SVG_PLAY;
        if (navEqContainer) navEqContainer.classList.toggle('paused', !isPlaying);
    }

    // 防卡死 Modal 展开/关闭（hidden 类控制 + 点黑幕/ESC 逃生）
    window.openBigPlayer = function () {
        const modal = document.getElementById('bigPlayerModal');
        if (!modal) return;
        // 12.0 DOM Portaling：提挂到 body 根节点，突破父级 backdrop-blur/transform 定位限制（防沉底）
        if (modal.parentNode !== document.body) document.body.appendChild(modal);
        modal.classList.remove('hidden');
        document.body.style.overflow = 'hidden';  // 锁定背景滚动
    };
    window.closeBigPlayer = function () {
        const modal = document.getElementById('bigPlayerModal');
        if (!modal) return;
        modal.classList.add('hidden');
        document.body.style.overflow = '';  // 恢复背景滚动
    };
    // ESC 逃生（点黑幕关闭由 Modal 上的 onclick 处理）
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape') { window.closeBigPlayer && window.closeBigPlayer(); }
    });
}
// 5) 文章详情：顶部阅读进度条（函数化）
function bindProgressBar() {
    const progressBar = document.getElementById('progress-bar');
    if (progressBar && !progressBar.dataset.bound) {
        progressBar.dataset.bound = '1';
        window.addEventListener('scroll', () => {
            const doc = document.documentElement;
            const max = doc.scrollHeight - doc.clientHeight;
            progressBar.style.width = (max > 0 ? (doc.scrollTop / max) * 100 : 0) + '%';
        }, { passive: true });
    }
}
bindProgressBar();

// 6) 文章详情：侧边目录滚动高亮（函数化）
function bindToc() {
    const tocNav = document.getElementById('tocNav');
    if (tocNav && !tocNav.dataset.bound) {
        tocNav.dataset.bound = '1';
        const links = tocNav.querySelectorAll('a');
        const headings = document.querySelectorAll('.article-content h2, .article-content h3, .article-content h4');
        const spy = new IntersectionObserver((entries) => {
            entries.forEach((e) => {
                if (e.isIntersecting) {
                    links.forEach((l) => {
                        l.classList.toggle('toc-active', l.getAttribute('href') === '#' + e.target.id);
                    });
                }
            });
        }, { rootMargin: '-80px 0px -70% 0px' });
        headings.forEach((h) => spy.observe(h));
    }
}
bindToc();

// 7) 文章列表页：分类筛选 + 标题搜索（函数化，HTMX 切页后重新绑定）
function bindFilterBar() {
    const filterBar = document.getElementById('filterBar');
    if (filterBar && !filterBar.dataset.bound) {
        filterBar.dataset.bound = '1';
        const cards = document.querySelectorAll('.article-card');
        const searchInput = document.getElementById('searchInput');
        const emptyState = document.getElementById('emptyState');
        let activeCat = 'all';

        const applyFilters = () => {
            const q = (searchInput ? searchInput.value : '').trim().toLowerCase();
            let visible = 0;
            cards.forEach((card) => {
                const tags = (card.dataset.tags || '').split(',').map((s) => s.trim());
                const catOk = activeCat === 'all' || tags.includes(activeCat);
                const titleOk = !q || (card.dataset.title || '').includes(q);
                const show = catOk && titleOk;
                card.style.display = show ? '' : 'none';
                if (show) {
                    card.classList.add('active'); // 被筛选出来时直接显示
                    visible++;
                }
            });
            if (emptyState) emptyState.style.display = visible ? 'none' : 'block';
        };

        filterBar.querySelectorAll('[data-filter]').forEach((btn) => {
            btn.addEventListener('click', () => {
                activeCat = btn.dataset.filter;
                filterBar.querySelectorAll('[data-filter]').forEach((b) => {
                    b.classList.toggle('tag-btn-active', b === btn);
                });
                applyFilters();
            });
        });

        if (searchInput) searchInput.addEventListener('input', applyFilters);
    }
}
bindFilterBar();

// 8) 页面切换：HTMX hx-boost 软导航接管（只换 #main-content，顶栏/播放器 DOM 常驻 → 音乐零中断）

// 9) HTMX 软导航后重新绑定页面行为（切页只换 #main-content，顶栏/播放器 DOM 常驻）
function initPageBehaviors() {
    observeReveals();
    bindHeroParallax();
    bindPostParallax();
    bindProgressBar();
    bindToc();
    bindFilterBar();
    bindHomeCinema();
    // 表单不参与 hx-boost（登录/后台/评论等保持常规提交）
    if (window.htmx) {
        document.querySelectorAll('form').forEach((f) => f.setAttribute('hx-boost', 'false'));
    }
    // 非首页顶栏初始状态（首页有深色 Hero 才透明态）
    if (typeof header !== 'undefined' && header && !document.querySelector('.hero-full')) applyNav(true);
}

// 8b) 影院级动效（8.0）：Hero 级联拉焦 + 鼠标视差 + 3D 卡片倾斜
function bindHomeCinema() {
    // 1. Hero 级联元素拉焦涌现
    const heroItems = document.querySelectorAll('#heroSection .hero-cascade-item');
    if (heroItems.length) {
        setTimeout(() => {
            heroItems.forEach((el) => el.classList.add('is-mounted'));
        }, 100);
    }

    // 2. 鼠标视差移动（Hero 背景微幅联动）
    const hero = document.getElementById('heroSection');
    const parallaxBg = document.getElementById('parallaxBg');
    if (hero && parallaxBg && !hero.dataset.px) {
        hero.dataset.px = '1';
        hero.addEventListener('mousemove', (e) => {
            const xPos = (e.clientX / window.innerWidth - 0.5) * 20;
            const yPos = (e.clientY / window.innerHeight - 0.5) * 20;
            requestAnimationFrame(() => {
                parallaxBg.style.transform = `scale(1.05) translate3d(${xPos}px, ${yPos}px, 0)`;
            });
        });
    }

    // 3. 3D 悬浮物理倾斜 + 液态扫光
    document.querySelectorAll('.glass-shine-card:not([data-tilt])').forEach((card) => {
        card.dataset.tilt = '1';
        card.addEventListener('mousemove', (e) => {
            const rect = card.getBoundingClientRect();
            const x = e.clientX - rect.left;
            const y = e.clientY - rect.top;
            const centerX = rect.width / 2;
            const centerY = rect.height / 2;
            const rotateX = ((y - centerY) / centerY) * -8;
            const rotateY = ((x - centerX) / centerX) * 8;
            requestAnimationFrame(() => {
                card.style.transform = `perspective(1000px) rotateX(${rotateX}deg) rotateY(${rotateY}deg) translateY(-6px) scale(1.01)`;
            });
        });
        card.addEventListener('mouseleave', () => {
            requestAnimationFrame(() => {
                card.style.transform = '';
            });
        });
    });
}
bindHomeCinema();

if (window.htmx) {
    document.addEventListener('htmx:afterSwap', initPageBehaviors);
}

// 10) 软导航后：滚动回顶 + 导航高亮动态更新（导航在 #main-content 外，切页后 Jinja 高亮不会刷新）
function updateNavActiveState() {
    const currentPath = window.location.pathname;
    // 首页导航（翡翠圆点高亮，双模）
    document.querySelectorAll('.nav-link').forEach((link) => {
        const href = link.getAttribute('href');
        if (href === currentPath) {
            link.className = 'nav-link text-emerald-700 dark:text-emerald-300 font-semibold relative py-1 after:absolute after:bottom-0 after:left-1/2 after:-translate-x-1/2 after:w-4 after:h-[2px] after:bg-emerald-500 after:rounded-full transition-all';
        } else {
            link.className = 'nav-link hover:text-emerald-600 dark:hover:text-emerald-400 transition-colors duration-300';
        }
    });
    // 内页导航（液态胶囊）
    document.querySelectorAll('.nav-pill-item').forEach((link) => {
        link.classList.toggle('nav-pill-active', link.getAttribute('href') === currentPath);
    });
    // 移动端全屏菜单高亮（16.0）
    document.querySelectorAll('#mobileMenuModal a').forEach((link) => {
        const active = link.getAttribute('href') === currentPath;
        if (active) {
            link.classList.add('text-emerald-600', 'dark:text-emerald-400');
            link.classList.remove('hover:text-emerald-500');
        } else {
            link.classList.remove('text-emerald-600', 'dark:text-emerald-400');
            link.classList.add('hover:text-emerald-500');
        }
    });
    // 非首页顶栏初始状态
    if (typeof header !== 'undefined' && header && !document.querySelector('.hero-full')) applyNav(true);
}
document.addEventListener('DOMContentLoaded', updateNavActiveState);
if (window.htmx) {
    // 软导航完成后：回顶 + 高亮（afterOnLoad 早于 afterSwap，两个都挂上兜底）
    document.body.addEventListener('htmx:afterOnLoad', () => {
        window.scrollTo({ top: 0, behavior: 'instant' });
        updateNavActiveState();
    });
    document.body.addEventListener('htmx:afterSwap', updateNavActiveState);
}
