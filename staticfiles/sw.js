self.addEventListener('push', (event) => {
  let payload = {};
  if (event.data) {
    try {
      payload = event.data.json();
    } catch (err) {
      payload = { body: event.data.text() };
    }
  }

  const title = payload.title || 'پیام جدید پشتیبانی';
  const options = {
    body: payload.body || 'یک پیام جدید از کاربر دریافت شد.',
    icon: '/static/img/og-fallback.svg',
    badge: '/static/img/og-fallback.svg',
    tag: payload.thread_id ? `support-thread-${payload.thread_id}` : 'support-message',
    data: {
      url: payload.url || '/support/operator/',
      thread_id: payload.thread_id || null,
    },
    renotify: true,
  };

  event.waitUntil(self.registration.showNotification(title, options));
});

self.addEventListener('notificationclick', (event) => {
  event.notification.close();

  const targetUrl =
    (event.notification && event.notification.data && event.notification.data.url) ||
    '/support/operator/';

  event.waitUntil(
    clients.matchAll({ type: 'window', includeUncontrolled: true }).then((clientList) => {
      for (const client of clientList) {
        if (client.url.includes('/support/operator/')) {
          return client.focus().then(() => client.navigate(targetUrl));
        }
      }
      return clients.openWindow(targetUrl);
    })
  );
});
