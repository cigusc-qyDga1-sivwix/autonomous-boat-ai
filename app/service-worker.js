const CACHE='boat-lab-static-v51';
const ASSETS=['./head-share-chart.js','./head-share-chart.css','./statistical-shadow.js','./four-factor.js','./ticket-policy.js','./','./index.html','./exhibition.html','./exhibition-watch.html','./exhibition-watch.js','./exhibition-research.js','./styles.css','./app.js','./mobile-race-nav.js','./venue-board.js','./venue-board.css','./race-timeline.js','./race-timeline.css','./cumulative-settlement.js','./official-direct-refresh.js','./cumulative-settlement.css','./boaters-reference.js','./boaters-reference.css','./forecast-reanalysis.js','./forecast-reanalysis.css','./racer-rating.js','./racer-rating-panel.js','./wake-study.js','./race-visual.js','./venue-tactics-v2.js','./tactical-1m.js','./exhibition-direct.js','./exhibition-audit.js','./result-quickboard.js','./result-reader.js','./result-reader.css','./batch-result-reader.js','./batch-result-reader.css','./manifest.webmanifest','./icons/mark.svg','./icons/app-192.png','./data/2026-10-22.json'];
self.addEventListener('install',event=>event.waitUntil(caches.open(CACHE).then(cache=>cache.addAll(ASSETS)).then(()=>self.skipWaiting())));
self.addEventListener('activate',event=>event.waitUntil(Promise.all([caches.keys().then(keys=>Promise.all(keys.filter(k=>k!==CACHE).map(k=>caches.delete(k)))),self.clients.claim()])));
self.addEventListener('fetch',event=>{
 if(event.request.method!=='GET')return;
 const url=new URL(event.request.url);
 if(url.origin!==self.location.origin)return;
 // Official results / frozen ledgers must never be served from a stale PWA cache.
 // A failed network request is an error, not a fake "success" with HTML/old JSON.
 if(url.pathname.includes('/data/live/')||url.pathname.includes('/data/exhibition/')||url.pathname.includes('/data/experiments/statistical-')){
   event.respondWith(fetch(event.request,{cache:'no-store'}));
   return;
 }
 event.respondWith(fetch(event.request).then(response=>{
   if(response.ok){
     const copy=response.clone();
     caches.open(CACHE).then(cache=>cache.put(event.request,copy)).catch(()=>{});
   }
   return response;
 }).catch(async()=>{
   const cached=await caches.match(event.request);
   if(cached)return cached;
   if(event.request.mode==='navigate')return caches.match('./index.html')||Response.error();
   return Response.error();
 }));
});
