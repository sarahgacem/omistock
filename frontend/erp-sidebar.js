/**
 * OMISTOCK ERP — Menu latéral mobile (partagé par toutes les pages dashboard)
 */
(function () {
    // Intercept all fetch requests globally to add the ngrok bypass header
    const originalFetch = window.fetch;
    window.fetch = function(input, init) {
        init = init || {};
        init.headers = init.headers || {};
        
        if (init.headers instanceof Headers) {
            init.headers.set('ngrok-skip-browser-warning', '1');
        } else if (Array.isArray(init.headers)) {
            init.headers.push(['ngrok-skip-browser-warning', '1']);
        } else {
            init.headers['ngrok-skip-browser-warning'] = '1';
        }
        
        return originalFetch(input, init);
    };

    const MOBILE_BREAKPOINT = 1024;

    function toggleMobileMenu() {
        const sidebar = document.querySelector('.sidebar');
        const overlay = document.getElementById('sidebar-overlay');
        if (!sidebar || !overlay) return;

        sidebar.classList.toggle('sidebar-visible');
        overlay.classList.toggle('hidden');
        document.body.classList.toggle('sidebar-open', sidebar.classList.contains('sidebar-visible'));
    }

    function closeMobileMenu() {
        const sidebar = document.querySelector('.sidebar');
        const overlay = document.getElementById('sidebar-overlay');
        if (!sidebar || !overlay) return;

        sidebar.classList.remove('sidebar-visible');
        overlay.classList.add('hidden');
        document.body.classList.remove('sidebar-open');
    }

    function initErpSidebar() {
        const overlay = document.getElementById('sidebar-overlay');
        const toggleBtn = document.getElementById('menu-toggle');

        if (overlay) {
            overlay.addEventListener('click', toggleMobileMenu);
        }
        if (toggleBtn) {
            toggleBtn.addEventListener('click', toggleMobileMenu);
        }

        window.addEventListener('resize', function () {
            if (window.innerWidth >= MOBILE_BREAKPOINT) {
                closeMobileMenu();
            }
        });

        document.querySelectorAll('.sidebar .nav-item').forEach(function (link) {
            link.addEventListener('click', function () {
                if (window.innerWidth < MOBILE_BREAKPOINT) {
                    closeMobileMenu();
                }
            });
        });
    }

    window.toggleMobileMenu = toggleMobileMenu;
    window.closeMobileMenu = closeMobileMenu;

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initErpSidebar);
    } else {
        initErpSidebar();
    }
})();
