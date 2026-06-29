var CACHE = "haqita-v1";
var SHELL = [
  "/",
  "/admin.html",
  "/assets/app.css",
  "/assets/admin.css",
  "/assets/app.js",
  "/assets/admin.js",
];

self.addEventListener("install", function (event) {
  event.waitUntil(
    caches.open(CACHE).then(function (cache) {
      return cache.addAll(SHELL);
    }),
  );
});

self.addEventListener("activate", function (event) {
  event.waitUntil(
    caches.keys().then(function (keys) {
      return Promise.all(
        keys
          .filter(function (k) {
            return k !== CACHE;
          })
          .map(function (k) {
            return caches.delete(k);
          }),
      );
    }),
  );
});

self.addEventListener("fetch", function (event) {
  var url = new URL(event.request.url);
  if (SHELL.includes(url.pathname)) {
    event.respondWith(
      caches.match(event.request).then(function (cached) {
        return cached || fetch(event.request);
      }),
    );
    return;
  }
  if (url.pathname.startsWith("/api/")) {
    event.respondWith(
      fetch(event.request)
        .then(function (resp) {
          var clone = resp.clone();
          caches.open(CACHE).then(function (cache) {
            cache.put(event.request, clone);
          });
          return resp;
        })
        .catch(function () {
          return caches.match(event.request);
        }),
    );
    return;
  }
  event.respondWith(
    caches.match(event.request).then(function (cached) {
      return cached || fetch(event.request);
    }),
  );
});
