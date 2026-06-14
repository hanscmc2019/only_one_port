(function ($) {
    "use strict";
    
    // Dropdown on mouse hover
    $(document).ready(function () {
        function toggleNavbarMethod() {
            if ($(window).width() > 992) {
                $('.navbar .dropdown').on('mouseover', function () {
                    $('.dropdown-toggle', this).trigger('click');
                }).on('mouseout', function () {
                    $('.dropdown-toggle', this).trigger('click').blur();
                });
            } else {
                $('.navbar .dropdown').off('mouseover').off('mouseout');
            }
        }
        toggleNavbarMethod();
        $(window).resize(toggleNavbarMethod);
    });
    
    
    // Back to top button
    $(window).scroll(function () {
        if ($(this).scrollTop() > 100) {
            $('.back-to-top').fadeIn('slow');
        } else {
            $('.back-to-top').fadeOut('slow');
        }
    });
    $('.back-to-top').click(function () {
        // Usa el easing personalizado si está cargado; si no, el de jQuery por defecto
        var easing = ($.easing && $.easing.easeInOutExpo) ? 'easeInOutExpo' : 'swing';
        $('html, body').animate({scrollTop: 0}, 1500, easing);
        return false;
    });


    // Carousels (solo si la librería owlCarousel está cargada en la página)
    if ($.fn.owlCarousel) {
        // Vendor carousel
        $('.vendor-carousel').owlCarousel({
            loop: true,
            margin: 29,
            nav: false,
            autoplay: true,
            smartSpeed: 1000,
            responsive: {
                0:{
                    items:2
                },
                576:{
                    items:3
                },
                768:{
                    items:4
                },
                992:{
                    items:5
                },
                1200:{
                    items:6
                }
            }
        });


        // Related carousel
        $('.related-carousel').owlCarousel({
            loop: true,
            margin: 29,
            nav: false,
            autoplay: true,
            smartSpeed: 1000,
            responsive: {
                0:{
                    items:1
                },
                576:{
                    items:2
                },
                768:{
                    items:3
                },
                992:{
                    items:4
                }
            }
        });
    }


    // Product Quantity
    $('.quantity button').on('click', function () {
        var button = $(this);
        var oldValue = button.parent().parent().find('input').val();
        if (button.hasClass('btn-plus')) {
            var newVal = parseFloat(oldValue) + 1;
        } else {
            if (oldValue > 0) {
                var newVal = parseFloat(oldValue) - 1;
            } else {
                newVal = 0;
            }
        }
        button.parent().parent().find('input').val(newVal);
    });
    
    // Helper for Guest ID
    function getGuestId() {
        let guestId = localStorage.getItem('guest_id');
        if (!guestId) {
            guestId = 'guest_' + Math.random().toString(36).substr(2, 9) + Date.now().toString(36);
            localStorage.setItem('guest_id', guestId);
        }
        return guestId;
    }

    // Auth and Role Management (AJAX Config only)
    $(document).ready(function() {
        $.ajaxSetup({
            beforeSend: function(xhr) {
                const token = localStorage.getItem('access_token');
                if (token) {
                    xhr.setRequestHeader('Authorization', 'Bearer ' + token);
                }
                xhr.setRequestHeader('X-Guest-ID', getGuestId());
            }
        });

        // Update login/logout navbar (DEPRECATED - logic moved to load_components.js)
    });

    // ──────────────────────────────────────────────
    // Helper: resuelve la URL de imagen de un producto
    // Centraliza la lógica antes duplicada en varias páginas.
    // ──────────────────────────────────────────────
    window.imageUrl = function(img, fallback) {
        if (fallback === undefined) fallback = 'img/product-1.jpg';
        if (!img) return fallback;
        return img.includes('http') ? new URL(img).pathname : img;
    };

    // ──────────────────────────────────────────────
    // Gestión de sesión / refresco de token JWT
    // ──────────────────────────────────────────────
    function clearSession() {
        localStorage.removeItem('access_token');
        localStorage.removeItem('refresh_token');
        localStorage.removeItem('user_roles');
        localStorage.removeItem('username');
    }
    window.clearSession = clearSession;

    window.refreshAccessToken = function() {
        const refresh = localStorage.getItem('refresh_token');
        if (!refresh) return $.Deferred().reject().promise();
        return $.ajax({
            url: '/api/token/refresh/',
            method: 'POST',
            contentType: 'application/json',
            data: JSON.stringify({ refresh: refresh }),
            _skipAuthRetry: true
        }).done(function(res) {
            if (res.access) localStorage.setItem('access_token', res.access);
        });
    };

    // Refresco proactivo: el access token dura 1h, lo renovamos cada 50 min
    if (localStorage.getItem('refresh_token')) {
        setInterval(function() {
            if (localStorage.getItem('refresh_token')) window.refreshAccessToken();
        }, 50 * 60 * 1000);
    }

    // Fallback: ante un 401, intenta refrescar UNA vez y reintenta la petición original
    $(document).ajaxError(function(event, jqXHR, settings) {
        if (jqXHR.status !== 401 || settings._skipAuthRetry || settings._retried) return;
        const url = settings.url || '';
        if (url.indexOf('/api/login/') !== -1 || url.indexOf('/api/token/refresh/') !== -1) return;
        if (!localStorage.getItem('refresh_token')) return;
        settings._retried = true;
        window.refreshAccessToken()
            .done(function() { $.ajax(settings); })
            .fail(function() { clearSession(); });
    });

    window.addToCart = function(productId, quantity = 1) {
        $.ajax({
            url: '/api/cart/add/',
            method: 'POST',
            contentType: 'application/json',
            data: JSON.stringify({ product_id: productId, quantity: quantity }),
            success: function(response) {
                // Notificar de forma sutil o usando alert simple
                alert('¡Producto añadido al carrito exitosamente!');
                updateCartBadge();
            },
            error: function(xhr) {
                alert('Error al añadir al carrito. ' + (xhr.responseJSON?.error || ''));
            }
        });
    };

    window.updateCartBadge = function() {
        $.ajax({
            url: '/api/cart/',
            method: 'GET',
            success: function(response) {
                let count = 0;
                if(response.items && response.items.length) {
                    count = response.items.reduce((sum, item) => sum + item.quantity, 0);
                }
                $('#cart-badge').text(count);
            },
            error: function() {
                $('#cart-badge').text("0");
            }
        });
    };

})(jQuery);

