// Config del negocio (tipo de tienda) servida por el backend desde el .env.
// El frontend estático no lee el .env, así que la pide a /api/config/ una sola
// vez. Las páginas usan getStoreConfig().then(cfg => ...) para saber si mostrar
// variantes (talla/color) y cómo rotular el 2º precio.
let _storeConfigPromise = null;
window.getStoreConfig = function() {
    if (!_storeConfigPromise) {
        _storeConfigPromise = $.ajax({ url: '/api/config/', method: 'GET' })
            .then(function(cfg) { window.STORE_CONFIG = cfg; return cfg; })
            .catch(function() {
                const def = { store_type: 'simple', show_variants: false, price_wholesale_label: 'Precio con descuento' };
                window.STORE_CONFIG = def; return def;
            });
    }
    return _storeConfigPromise;
};

$(document).ready(function() {
    // Cargar config del negocio cuanto antes (deja window.STORE_CONFIG listo)
    window.getStoreConfig();

    // 1. Cargar Topbar
    if ($('#topbar-placeholder').length) {
        $('#topbar-placeholder').load('components/topbar.html');
    }

    // 2. Cargar Navbar y Aplicar Lógica
    if ($('#navbar-placeholder').length) {
        let currentPath = window.location.pathname.split('/').pop() || 'index.html';

        $('#navbar-placeholder').load('components/navbar.html', function() {
            // Marcar enlace activo
            $('.navbar-nav a').removeClass('active');
            $(`.navbar-nav a[href="${currentPath}"]`).addClass('active');

            // Aplicar Seguridad y UI
            applyAuthLogic();
        });
    } else {
        applyAuthLogic();
    }

    // 3. Cargar Footer
    if ($('#footer-placeholder').length) {
        $('#footer-placeholder').load('components/footer.html');
    }
});

function applyAuthLogic() {
    let roles = [];
    try {
        roles = JSON.parse(localStorage.getItem('user_roles') || '[]');
    } catch(e) {}
    
    const is_admin = roles.includes('ADMIN') || roles.includes('SUPERADMIN');
    const is_superadmin = roles.includes('SUPERADMIN');

    // Páginas solo para Admin/SuperAdmin
    const adminPages = ['catalogo.html', 'inventario.html', 'ventas.html', 'monitor_ventas.html'];

    // a) Ocultar los links de páginas admin si no es Admin o SuperAdmin
    if (!is_admin) {
        adminPages.forEach(p => $(`a[href="${p}"]`).hide());
    }

    // b) Redirección forzosa si intenta acceder escribiendo la URL
    if (!is_admin && adminPages.some(p => window.location.pathname.includes(p))) {
        window.location.href = 'index.html';
    }

    // c) Modificar botones Login/Registro por "Hola, admin" / "Salir"
    const token = localStorage.getItem('access_token');
    if (token) {
        const username = localStorage.getItem('username');
        const loginContainer = $('.navbar-nav.ml-auto');
        if(loginContainer.length) {
            let superAdminBtn = is_superadmin ? `<a href="/admin/" class="nav-item nav-link text-danger font-weight-bold">Panel Django</a>` : '';
            loginContainer.html(`
                ${superAdminBtn}
                <span class="nav-item nav-link text-primary font-weight-bold" style="cursor:default">Hola, ${username}</span>
                <a href="#" class="nav-item nav-link" id="logout-btn">Salir</a>
            `);
            $('#logout-btn').click(function(e) {
                e.preventDefault();
                if (typeof clearSession === 'function') {
                    clearSession();
                } else {
                    localStorage.removeItem('access_token');
                    localStorage.removeItem('refresh_token');
                    localStorage.removeItem('user_roles');
                    localStorage.removeItem('username');
                }
                window.location.href = 'index.html';
            });
        }
        
        // d) Auto-logout por inactividad (Solo Administradores)
        if (is_admin) {
            let inactivityTime = function () {
                let time;
                window.onload = resetTimer;
                document.onmousemove = resetTimer;
                document.onkeypress = resetTimer;
                document.ontouchstart = resetTimer; 
                document.onclick = resetTimer;      

                function logout() {
                    alert("Tu sesión administrativa ha sido cerrada por seguridad debido a 30 minutos de inactividad.");
                    $('#logout-btn').click();
                }

                function resetTimer() {
                    clearTimeout(time);
                    time = setTimeout(logout, 30 * 60 * 1000); // 30 minutos
                }
            };
            inactivityTime();
        }
    }

    // d) Actualizar carrito
    if (typeof updateCartBadge === 'function') {
        updateCartBadge();
    }
}
