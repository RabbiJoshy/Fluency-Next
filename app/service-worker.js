// Retires the service worker that Fluency installed under /Fluency-Next/.
// It deletes no caches: they are shared with the app at /Fluency-App/.
self.addEventListener('install', () => self.skipWaiting());
self.addEventListener('activate', event => {
    event.waitUntil(self.registration.unregister());
});
