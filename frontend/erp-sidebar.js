/**
 * OMISTOCK ERP — Menu latéral mobile (partagé par toutes les pages dashboard)
 */
(function () {
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
