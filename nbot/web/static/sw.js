// NekoBot Service Worker
const CACHE_NAME = 'nekobot-v1';
const STATIC_ASSETS = [
    '/',
    '/static/css/app.css',
    '/static/js/nbot-shared.js',
    '/static/js/nbot-methods.js',
    '/static/js/nbot-router.js',
    '/static/vendor/socket.io.min.js',
    '/static/vendor/vue.global.prod.js',
    '/static/vendor/vue-router.global.prod.js',
    '/static/vendor/axios.min.js',
    '/static/vendor/marked.min.js',
    '/static/vendor/highlight.min.js',
    '/static/vendor/styles/highlight-github-dark.min.css',
    '/static/neko.png'
];

// 安装：预缓存静态资源
self.addEventListener('install', (event) => {
    event.waitUntil(
        caches.open(CACHE_NAME).then((cache) => {
            return cache.addAll(STATIC_ASSETS);
        }).then(() => {
            return self.skipWaiting();
        })
    );
});

// 激活：清理旧缓存
self.addEventListener('activate', (event) => {
    event.waitUntil(
        caches.keys().then((cacheNames) => {
            return Promise.all(
                cacheNames
                    .filter((name) => name !== CACHE_NAME)
                    .map((name) => caches.delete(name))
            );
        }).then(() => {
            return self.clients.claim();
        })
    );
});

// 请求拦截：网络优先，离线回退缓存
self.addEventListener('fetch', (event) => {
    const { request } = event;

    // 非 GET 请求不缓存
    if (request.method !== 'GET') return;

    // API 请求和 Socket.IO 不缓存
    if (request.url.includes('/api/') || request.url.includes('/socket.io/')) return;

    // HTML 页面：网络优先
    if (request.headers.get('accept')?.includes('text/html')) {
        event.respondWith(
            fetch(request)
                .then((response) => {
                    const clone = response.clone();
                    caches.open(CACHE_NAME).then((cache) => {
                        cache.put(request, clone);
                    });
                    return response;
                })
                .catch(() => {
                    return caches.match(request).then((cached) => {
                        return cached || caches.match('/');
                    });
                })
        );
        return;
    }

    // 静态资源：缓存优先，网络回退
    event.respondWith(
        caches.match(request).then((cached) => {
            if (cached) return cached;
            return fetch(request).then((response) => {
                if (response.ok) {
                    const clone = response.clone();
                    caches.open(CACHE_NAME).then((cache) => {
                        cache.put(request, clone);
                    });
                }
                return response;
            }).catch(() => {
                return new Response('', { status: 408, statusText: 'Offline' });
            });
        })
    );
});

// Push 通知
self.addEventListener('push', (event) => {
    let data = {};

    try {
        data = event.data ? event.data.json() : {};
    } catch {
        data = {
            title: 'NekoBot',
            body: event.data ? event.data.text() : 'You have a new message.',
        };
    }

    const title = data.title || 'NekoBot';
    const options = {
        body: data.body || 'You have a new message.',
        icon: '/static/neko.png',
        badge: '/static/neko.png',
        tag: data.tag || 'nekobot-message',
        renotify: true,
        data: {
            url: data.url || '/',
        },
    };

    event.waitUntil(self.registration.showNotification(title, options));
});

// 通知点击
self.addEventListener('notificationclick', (event) => {
    event.notification.close();
    const targetUrl = event.notification.data?.url || '/';

    event.waitUntil(
        clients.matchAll({ type: 'window', includeUncontrolled: true }).then((clientList) => {
            for (const client of clientList) {
                if ('focus' in client) {
                    client.navigate(targetUrl);
                    return client.focus();
                }
            }
            if (clients.openWindow) {
                return clients.openWindow(targetUrl);
            }
        })
    );
});
