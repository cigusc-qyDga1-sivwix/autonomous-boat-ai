// Standalone WEATHER LAB PWA shell; never cache the cross-origin weather feed.
const PREFIX="weather-lab-shell-";
const CACHE=PREFIX+"v1";
const SHELL=["./","./index.html","./weather.css","./weather.js","./manifest.webmanifest","./icon.svg"];
self.addEventListener("install",event=>event.waitUntil(
 caches.open(CACHE).then(cache=>cache.addAll(SHELL)).then(()=>self.skipWaiting())
));
self.addEventListener("activate",event=>event.waitUntil(
 caches.keys().then(keys=>Promise.all(keys.filter(key=>key.startsWith(PREFIX)&&key!==CACHE)
 .map(key=>caches.delete(key)))).then(()=>self.clients.claim())
));
self.addEventListener("fetch",event=>{
 const request=event.request;
 if(request.method!=="GET")return;
 const url=new URL(request.url);
 if(url.origin!==self.location.origin)return; // WEATHER LAB JSON never served from cache.
 if(!url.pathname.includes("/weather/"))return;
 event.respondWith(fetch(request,{cache:"no-store"}).then(response=>{
   if(response.ok){const copy=response.clone();caches.open(CACHE).then(c=>c.put(request,copy)).catch(()=>{});}
   return response;
 }).catch(async()=>{
   const cached=await caches.match(request);
   if(cached)return cached;
   return request.mode==="navigate"?(await caches.match("./index.html")||Response.error()):Response.error();
 }));
});
