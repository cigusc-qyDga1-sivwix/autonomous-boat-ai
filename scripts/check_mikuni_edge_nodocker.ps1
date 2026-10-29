# BOAT LAB: Built-in Windows PowerShell 5.1 + Microsoft Edge, no Docker.
# Temporary isolated browser; localhost ephemeral DevTools only. No video files.
param(
  [ValidatePattern('^\d{4}-\d{2}-\d{2}$')][string]$Date=(Get-Date).ToString('yyyy-MM-dd'),
  [ValidateRange(1,12)][int]$Race=1,
  [switch]$SelfTest,
  [switch]$LayoutAudit,
  [switch]$VisibleEdge,
  [switch]$PlaybackProbe
)
$ErrorActionPreference='Stop'

function Find-Edge {
  $paths=@()
  foreach($root in @([Environment]::GetEnvironmentVariable('ProgramFiles(x86)'), $env:ProgramFiles, $env:LOCALAPPDATA)){
    if($root){ $paths+=Join-Path $root 'Microsoft\Edge\Application\msedge.exe' }
  }
  foreach($path in $paths){ if(Test-Path -LiteralPath $path -PathType Leaf){return $path} }
  throw 'Microsoft Edge executable not found.'
}

function Send-CDP([string]$method,[object]$params=@{}){
  $script:nextId++
  $body=@{id=$script:nextId;method=$method;params=$params}|ConvertTo-Json -Compress -Depth 25
  $bytes=[Text.Encoding]::UTF8.GetBytes($body)
  $seg=New-Object 'System.ArraySegment[byte]' -ArgumentList @(,$bytes)
  [void]$script:ws.SendAsync($seg,[Net.WebSockets.WebSocketMessageType]::Text,
    $true,[Threading.CancellationToken]::None).GetAwaiter().GetResult()
  return $script:nextId
}

# Do not cancel a pending WebSocket receive just to poll: it can abort .NET 4.x sockets.
function Read-CDP([int]$timeoutMs=500){
  if(-not $script:pendingRead){
    $script:recvBuffer=New-Object byte[] 65536
    $seg=New-Object 'System.ArraySegment[byte]' -ArgumentList @(,$script:recvBuffer)
    $script:pendingRead=$script:ws.ReceiveAsync($seg,[Threading.CancellationToken]::None)
  }
  if(-not $script:pendingRead.Wait($timeoutMs)){return $null}
  $piece=$script:pendingRead.GetAwaiter().GetResult()
  $script:pendingRead=$null
  if($piece.MessageType -eq [Net.WebSockets.WebSocketMessageType]::Close){throw 'Edge DevTools closed.'}
  $script:messageBuffer.Write($script:recvBuffer,0,$piece.Count)
  if($script:messageBuffer.Length -gt 1048576){throw 'Unexpected large DevTools message.'}
  if(-not $piece.EndOfMessage){return $null}
  $s=[Text.Encoding]::UTF8.GetString($script:messageBuffer.ToArray())
  $script:messageBuffer.SetLength(0)
  return ($s|ConvertFrom-Json)
}

function Is-Media([string]$url){
  return $url -match '(?i)\.(m3u8|mpd|mp4|webm|mov|m4v|ts|m4s|cmfv|cmfa|key|license)(\?|#|$)'
}

function Process-Event($event){
  switch([string]$event.method){
    'Fetch.requestPaused' {
      $q=$event.params
      $url=[string]$q.request.url
      $type=[string]$q.resourceType
      $method=[string]$q.request.method
      $allowed=$true
      $requestHost=''
      try {
        $u=[Uri]$url; $requestHost=$u.Host.ToLowerInvariant()
        if($u.Scheme -notin @('https','http')){$allowed=$false}
      }catch{$allowed=$false}
      if((Is-Media $url) -or $type -eq 'Media'){
        $allowed=$false;$script:blockedMedia++
      }elseif($type -in @('XHR','Fetch')){
        if($method -ne 'GET' -or $requestHost -notin @(
          'livebb.jlc.ne.jp','front.player.boatrace-cdn.jp','playback.api.streaks.jp'
        )){
          $allowed=$false;$script:blockedOpaque++
        }
        if($requestHost -eq 'playback.api.streaks.jp'){
          $script:apiGets++
          if($script:apiGets -gt 5){$allowed=$false}
        }
      }
      if($allowed){
        $null=Send-CDP 'Fetch.continueRequest' @{requestId=[string]$q.requestId}
      }else{
        $null=Send-CDP 'Fetch.failRequest' @{requestId=[string]$q.requestId;errorReason='BlockedByClient'}
      }
    }
    'Network.responseReceived' {
      $q=$event.params.response
      try{$u=[Uri][string]$q.url}catch{return}
      if($u.Host -eq 'livebb.jlc.ne.jp' -and $u.AbsolutePath -eq '/bb_top/sp_bb/tvod_10.php'){
        $script:landingStatus=[int]$q.status
      }
      if($u.Host -eq 'playback.api.streaks.jp'){
        $status=[int]$q.status
        if($script:apiStatuses -notcontains $status){$script:apiStatuses+= $status}
      }
    }
  }
}

function Await-CDP([int]$id,[int]$timeoutMs=15000){
  $deadline=(Get-Date).AddMilliseconds($timeoutMs)
  while((Get-Date) -lt $deadline){
    $m=Read-CDP 500
    if($null -eq $m){continue}
    if($m.method){Process-Event $m;continue}
    if($m.id -eq $id){
      if($m.error){throw 'Edge DevTools command failed.'}
      return $m.result
    }
  }
  throw 'Edge DevTools timed out.'
}

function Pump-CDP([int]$ms){
  $until=(Get-Date).AddMilliseconds($ms)
  while((Get-Date) -lt $until){
    $m=Read-CDP 300
    if($m -and $m.method){Process-Event $m}
  }
}

function Get-Safe-Popup-Info([string]$pageUrl){
  # Only expose an HTTPS hostname or a non-HTTPS category. NO URL path,
  # query, tokens, cookies, IP address, or title is ever logged.
  $info=@{category='INVALID';host='NOT_DISCLOSED'}
  if([string]::IsNullOrWhiteSpace($pageUrl)){
    $info.category='EMPTY';return $info
  }
  try {$parsed=[Uri]$pageUrl} catch {return $info}
  if($parsed.Scheme -eq 'about'){
    $info.category='ABOUT_BLANK_OR_INTERNAL';return $info
  }
  if($parsed.Scheme -in @('chrome','chrome-error','chrome-untrusted','edge','ms-edge')){
    $info.category='BROWSER_INTERNAL';return $info
  }
  if($parsed.Scheme -eq 'file'){
    $info.category='LOCAL_FILE_NO_REPLAY';return $info
  }
  if($parsed.Scheme -in @('blob','data','javascript')){
    $info.category='NON_HTTP_SCHEME';return $info
  }
  if($parsed.Scheme -notin @('http','https')){
    $info.category='OTHER_SCHEME';return $info
  }
  $domain=$parsed.DnsSafeHost.ToLowerInvariant()
  if($domain.Length -gt 160 -or $domain -notmatch '^[a-z0-9][a-z0-9.-]*$' -or
    $domain -match '\.\.' -or $domain -eq 'localhost' -or
    $domain -match '(^|\.)local$' -or
    $domain -match '^\d{1,3}(?:\.\d{1,3}){3}$'){
    $info.category='HOST_NOT_DISCLOSED';return $info
  }
  # HTTP hostname is disclosed for identification only. Never navigate/reload
  # its URL, even if hostname matches a known official playback provider.
  $info.category=if($parsed.Scheme -eq 'https'){'HTTPS_HOST'}else{'HTTP_HOST_NO_REPLAY'}
  $info.host=$domain
  return $info
}

function Get-Safe-Internal-Popup-Kind([string]$pageUrl){
  # Classify browser internals WITHOUT exposing arbitrary internal paths or URLs.
  if([string]::IsNullOrWhiteSpace($pageUrl)){return 'EMPTY'}
  try {$u=[Uri]$pageUrl}catch{return 'MALFORMED'}
  if($u.Scheme -eq 'chrome-error'){return 'BROWSER_ERROR_PAGE'}
  if($u.Scheme -eq 'about'){return 'ABOUT_BLANK_OR_INTERNAL'}
  if($u.Scheme -eq 'edge'){
    if($u.DnsSafeHost -eq 'newtab'){return 'EDGE_NEW_TAB'}
    return 'EDGE_OTHER_INTERNAL'
  }
  if($u.Scheme -eq 'chrome'){
    if($u.DnsSafeHost -eq 'newtab'){return 'CHROMIUM_NEW_TAB'}
    return 'CHROMIUM_OTHER_INTERNAL'
  }
  if($u.Scheme -eq 'chrome-untrusted'){return 'CHROMIUM_UNTRUSTED_INTERNAL'}
  return 'NOT_BROWSER_INTERNAL'
}

function Inspect-Official-Playback-Tab($target){
  # Only a tab that our own click opened. Reject any other web origin.
  $targetPageUrl=[string]$target.url
  try {$targetUri=[Uri]$targetPageUrl} catch {return 'UNRECOGNIZED'}
  $recognized=@('front.player.boatrace-cdn.jp','livebb.jlc.ne.jp','playback.api.streaks.jp')
  if($targetUri.Scheme -ne 'https' -or $targetUri.Host.ToLowerInvariant() -notin $recognized){
    return 'UNRECOGNIZED'
  }
  if($targetPageUrl -match '(?i)(\.m3u8|\.mpd|\.mp4|\.webm)(\?|$)'){return 'MEDIA_TARGET_NOT_OPENED'}
  $targetWsUrl=[Uri][string]$target.webSocketDebuggerUrl
  if($targetWsUrl.Scheme -ne 'ws' -or $targetWsUrl.Host -notin @('127.0.0.1','localhost')){
    return 'NONLOCAL_SOCKET_REJECTED'
  }
  # Switch to the new isolated tab, never connect to the user's default browser.
  if($script:ws){$script:ws.Dispose()}
  $script:pendingRead=$null
  $script:messageBuffer.Dispose()
  $script:messageBuffer=New-Object IO.MemoryStream
  $script:ws=New-Object Net.WebSockets.ClientWebSocket
  [void]$script:ws.ConnectAsync($targetWsUrl,
    [Threading.CancellationToken]::None).GetAwaiter().GetResult()
  foreach($cmd in @('Page.enable','Runtime.enable','Network.enable')){
    $id=Send-CDP $cmd
    $null=Await-CDP $id
  }
  # A tab created before monitoring may have fetched its initial metadata.
  # Install the same media/XHR blocks FIRST, then run one normal browser reload.
  $id=Send-CDP 'Fetch.enable' @{patterns=@(@{urlPattern='*';requestStage='Request'})}
  $null=Await-CDP $id
  $id=Send-CDP 'Page.reload' @{ignoreCache=$true}
  $null=Await-CDP $id
  Pump-CDP 6000
  return 'GUARDED_RELOAD_COMPLETE'
}

function Invoke-Trusted-PointClick([int]$x,[int]$y){
  # DevTools Input events model an actual pointing-device click. DOM el.click()
  # lacks user activation and may open a browser-internal fallback tab.
  if($x -lt 0 -or $y -lt 0 -or $x -gt 4000 -or $y -gt 3000){
    throw 'Target click coordinate outside bounded browser viewport.'
  }
  foreach($data in @(
    @{type='mouseMoved';x=$x;y=$y;button='none';buttons=0},
    @{type='mousePressed';x=$x;y=$y;button='left';buttons=1;clickCount=1},
    @{type='mouseReleased';x=$x;y=$y;button='left';buttons=0;clickCount=1}
  )){
    $id=Send-CDP 'Input.dispatchMouseEvent' $data
    $null=Await-CDP $id 12000
  }
}

function Eval-CDP([string]$js){
  $id=Send-CDP 'Runtime.evaluate' @{expression=$js;returnByValue=$true;awaitPromise=$true;userGesture=$true}
  $r=Await-CDP $id 15000
  if($r.exceptionDetails){throw 'Page interaction failed.'}
  return $r.result.value
}

$script:nextId=0;$script:pendingRead=$null
$script:messageBuffer=New-Object IO.MemoryStream
$script:blockedMedia=0;$script:blockedOpaque=0;$script:apiGets=0
$script:apiStatuses=@();$script:landingStatus=$null;$script:ws=$null
$process=$null
$script:phase='START'
$profile=Join-Path ([IO.Path]::GetTempPath()) ('boatlabs-edge-'+[guid]::NewGuid().ToString('N'))
$result=[ordered]@{
  schema='boatlabs.mikuni_edge_nodocker.v1';date=$Date;venue='三国';race=$Race
  access_decision='NOT_RUN';landing_http_status=$null
  edge_start_mode=if($VisibleEdge){'VISIBLE_ISOLATED'}else{'HEADLESS_ISOLATED'}
  playback_probe='NOT_REQUESTED';player_video_count=0
  player_button_candidates=0;player_click='NOT_ATTEMPTED'
  playback_time_progressed=$false
  race_click_status='NOT_ATTEMPTED';meeting_header_clicked=$false
  day_header_clicked=$false;race_icon_matches=0;race_icon_visible_exact=0
  race_icon_target_day_matches=0;browser_tabs_after_click=0
  new_tab_domain='NOT_OBSERVED';new_tab_url_type='NOT_OBSERVED'
  new_tab_guard_status='NOT_NEEDED';new_tab_internal_kind='NOT_OBSERVED'
  race_link_kind='NOT_INSPECTED';race_link_host='NOT_DISCLOSED'
  race_link_target='NOT_INSPECTED';race_link_has_inline_handler=$false
  layout_hints=@()
  playback_api_statuses=@()
  playback_api_requests=0;media_requests_blocked=0;opaque_requests_blocked=0
  video_bytes_saved=0;video_frames_decoded=0;confirmed_six_boat_tracks=0
  formal_forecast_modified=$false
  note='API response status alone is not a verified video download.'
}
try {
  $d=[datetime]::MinValue
  if(-not [datetime]::TryParseExact($Date,'yyyy-MM-dd',
    [Globalization.CultureInfo]::InvariantCulture,
    [Globalization.DateTimeStyles]::None,[ref]$d)){throw 'Invalid calendar date.'}
  if($PlaybackProbe -and (-not $VisibleEdge -or $SelfTest -or $LayoutAudit)){
    throw 'PlaybackProbe requires VisibleEdge, without SelfTest or LayoutAudit.'
  }
  $script:phase='FIND_EDGE'
  $edge=Find-Edge
  New-Item -ItemType Directory -Path $profile -Force|Out-Null
  # Use a fresh, isolated profile in both modes; never attach to the user's
  # existing Edge session. Visible mode tests ordinary window rendering, not
  # authentication or media download, and is opt-in only.
  $arguments=@('--no-first-run','--no-default-browser-check',
    '--remote-debugging-port=0',('--user-data-dir="'+$profile+'"'),'about:blank')
  if($VisibleEdge){
    $arguments=@('--window-size=1280,900')+$arguments
  }else{
    $arguments=@('--headless=new','--disable-gpu')+$arguments
  }
  $script:phase='START_EDGE'
  $process=Start-Process -FilePath $edge -ArgumentList $arguments -PassThru
  $portFile=Join-Path $profile 'DevToolsActivePort'
  $until=(Get-Date).AddSeconds(20)
  while(-not (Test-Path -LiteralPath $portFile) -and (Get-Date) -lt $until){Start-Sleep -Milliseconds 150}
  if(-not (Test-Path -LiteralPath $portFile)){throw 'Isolated Edge could not start.'}
  $script:phase='READ_DEBUGGING_PORT'
  $port=[int]((Get-Content -LiteralPath $portFile -TotalCount 1).Trim())
  if($port -lt 1024 -or $port -gt 65535){throw 'Invalid local port.'}
  $script:phase='LIST_BROWSER_TABS'
  $pages=Invoke-RestMethod -Uri "http://127.0.0.1:$port/json/list" -TimeoutSec 5
  $page=@($pages|Where-Object {$_.type -eq 'page'}|Select-Object -First 1)
  if($page.Count -ne 1){throw 'No diagnostic browser tab.'}
  $wsUrl=[Uri]$page[0].webSocketDebuggerUrl
  if($wsUrl.Scheme -ne 'ws' -or $wsUrl.Host -notin @('127.0.0.1','localhost')){
    throw 'Nonlocal debugging socket rejected.'
  }
  $script:ws=New-Object Net.WebSockets.ClientWebSocket
  $script:phase='CONNECT_CDP_SOCKET'
  [void]$script:ws.ConnectAsync($wsUrl,[Threading.CancellationToken]::None).GetAwaiter().GetResult()
  $script:phase='CDP_SETUP'
  foreach($cmd in @('Page.enable','Runtime.enable','Network.enable')){
    $id=Send-CDP $cmd
    $null=Await-CDP $id
  }
  if($SelfTest){
    $script:phase='CDP_SELFTEST'
    if((Eval-CDP '6*7') -ne 42){throw 'Browser selftest failed.'}
    $null=Eval-CDP "(function(){const b=document.createElement('button');b.style.cssText='position:fixed;left:20px;top:20px;width:90px;height:45px;z-index:2147483647';b.textContent='Test';document.body.appendChild(b);window.__boatlabs_click_trusted=false;b.addEventListener('click',e=>{window.__boatlabs_click_trusted=e.isTrusted;});return true;})()"
    Invoke-Trusted-PointClick 55 43
    if((Eval-CDP 'window.__boatlabs_click_trusted===true') -ne $true){
      throw 'Input dispatch did not deliver a trusted browser click.'
    }
    $strict=Eval-CDP "'/static/1R.png'.match(new RegExp('(?:^|/)1R[.]png(?:[?#]|$)'))!==null&&'/static/11R.png'.match(new RegExp('(?:^|/)1R[.]png(?:[?#]|$)'))===null"
    if($strict -ne $true){throw '1R versus 11R selector is ambiguous.'}
    $safe=Get-Safe-Popup-Info 'https://player.example.org/path?token=DO_NOT_DISCLOSE'
    if($safe.category -ne 'HTTPS_HOST' -or $safe.host -ne 'player.example.org'){
      throw 'Safe popup hostname test failed.'
    }
    $blank=Get-Safe-Popup-Info 'about:blank'
    if($blank.category -ne 'ABOUT_BLANK_OR_INTERNAL' -or
       $blank.host -ne 'NOT_DISCLOSED'){throw 'Blank popup test failed.'}
    $plain=Get-Safe-Popup-Info 'http://public-replay.example.org/path?token=DO_NOT_DISCLOSE'
    if($plain.category -ne 'HTTP_HOST_NO_REPLAY' -or
       $plain.host -ne 'public-replay.example.org'){throw 'HTTP popup categorization failed.'}
    $local=Get-Safe-Popup-Info 'http://127.0.0.1:5555/private'
    if($local.category -ne 'HOST_NOT_DISCLOSED' -or
       $local.host -ne 'NOT_DISCLOSED'){throw 'Localhost redaction failed.'}
    $internal=Get-Safe-Popup-Info 'edge://newtab/'
    if($internal.category -ne 'BROWSER_INTERNAL'){throw 'Edge internal page failed.'}
    if((Get-Safe-Internal-Popup-Kind 'edge://newtab/') -ne 'EDGE_NEW_TAB' -or
       (Get-Safe-Internal-Popup-Kind 'chrome-error://chromewebdata/') -ne 'BROWSER_ERROR_PAGE' -or
       (Get-Safe-Internal-Popup-Kind 'https://front.player.boatrace-cdn.jp/path?secret=1') -ne 'NOT_BROWSER_INTERNAL'){
      throw 'Privacy-safe browser internal classification failed.'
    }
    $result.access_decision='EDGE_SELFTEST_PASSED_NO_NETWORK'
  }else{
    $script:phase='JLC_PAGE_DIAGNOSTIC'
    # PlaybackProbe deliberately uses normal browser streaming for observation.
    # No media is captured by the script. The default diagnostic blocks media.
    if(-not $PlaybackProbe){
      $id=Send-CDP 'Fetch.enable' @{patterns=@(@{urlPattern='*';requestStage='Request'})}
      $null=Await-CDP $id
    }
    $id=Send-CDP 'Page.navigate' @{url='https://livebb.jlc.ne.jp/bb_top/sp_bb/tvod_10.php'}
    $null=Await-CDP $id
    Pump-CDP 2200
    $monthDay='{0}/{1}' -f [int]$d.Month,[int]$d.Day
    $dateSlash=$d.ToString('yyyy/MM/dd')
    $layoutFlag=if($LayoutAudit){'true'}else{'false'}
    $js=@"
(async()=>{
 const sleep=ms=>new Promise(r=>setTimeout(r,ms));
 const visible=e=>!!e.getClientRects().length&&getComputedStyle(e).visibility!=='hidden';
 const clickText=t=>{
   const a=[...document.querySelectorAll('span,button,a,div,td,p,li')]
     .filter(e=>visible(e)&&e.textContent&&e.textContent.trim().includes(t)
       &&e.textContent.trim().length<140);
   a.sort((x,y)=>(x.textContent.trim().length-y.textContent.trim().length)
       ||(x.querySelectorAll('*').length-y.querySelectorAll('*').length));
   if(!a.length)return false;a[0].click();return true;
 };
 let meeting=false;
 for(let tries=0;tries<8&&!meeting;tries++){
   const text=document.body?.innerText||'';
   const ds=[...new Set(text.match(/20[0-9]{2}\/[0-9]{1,2}\/[0-9]{1,2}/g)||[])]
     .filter(s=>new Date(s)<=new Date('$dateSlash')).sort();
   if(ds.length)meeting=clickText(ds[ds.length-1]);
   if(!meeting)await sleep(350);
 }
 let day=false;
 for(let tries=0;tries<8&&!day;tries++){
   day=clickText('$monthDay');
   if(!day)await sleep(350);
 }
 const exactFile=new RegExp('(?:^|/)$($Race)R[.]png(?:[?#]|$)','i');
 let allIcons=[],icons=[],dayIcons=[];
 const owningDay=e=>{
   // JLC HTML: img > a.stream_a > td > tr > tbody > table
   // > center > li > ul > li (single day) > ul > li (meeting).
   const dayLi=e.closest('li')?.parentElement?.closest('li');
   if(!dayLi)return false;
   const dates=[...new Set((dayLi.textContent||'').match(/(?:20[0-9]{2}\/)?[0-9]{1,2}\/[0-9]{1,2}/g)||[])];
   return dates.length===1&&dates[0]==='$monthDay';
 };
 for(let tries=0;tries<8;tries++){
   allIcons=[...document.querySelectorAll('img')].filter(e=>exactFile.test(e.getAttribute('src')||''));
   icons=allIcons.filter(visible);
   dayIcons=icons.filter(owningDay);
   if(dayIcons.length===1)break;
   await sleep(350);
 }
 const describe=(e,i)=>{
   let n=e;const ancestry=[];
   for(let k=0;k<13&&n;k++,n=n.parentElement){
     let own='';
     for(const child of n.childNodes){
       if(child.nodeType===3)own+=child.nodeValue||'';
     }
     const dates=[...new Set((own.match(/(?:20[0-9]{2}\/)?[0-9]{1,2}\/[0-9]{1,2}/g)||[]))].slice(0,2);
     const descDates=[...new Set(((n.textContent||'').match(/(?:20[0-9]{2}\/)?[0-9]{1,2}\/[0-9]{1,2}/g)||[]))].slice(0,5);
     ancestry.push({
       tag:n.tagName.toLowerCase(),
       id:(n.id||'').replace(/[^a-zA-Z0-9_-]/g,'').slice(0,35),
       classes:[...(n.classList||[])].slice(0,3).map(s=>s.replace(/[^a-zA-Z0-9_-]/g,'').slice(0,35)),
       dates,descDates
     });
   }
   return {i,visible:visible(e),ancestry};
 };
 const hints=allIcons.slice(0,7).map(describe);
 const chosenLink=dayIcons.length===1?dayIcons[0].closest('a'):null;
 const describeLink=a=>{
   if(!a)return {kind:'NO_UNIQUE_LINK',host:'NOT_DISCLOSED',target:'NONE',inline:false};
   const href=a.getAttribute('href')||'';
   let kind='MISSING',host='NOT_DISCLOSED';
   if(href.startsWith('#'))kind='FRAGMENT';
   else if(/^javascript:/i.test(href))kind='JAVASCRIPT';
   else if(href){
     try{
       const u=new URL(href,document.baseURI);
       if(u.protocol==='https:'){
         kind='HTTPS_LINK';
         if(['livebb.jlc.ne.jp','front.player.boatrace-cdn.jp',
           'playback.api.streaks.jp'].includes(u.hostname.toLowerCase())){
           host=u.hostname.toLowerCase();
         }
       }else if(u.protocol==='http:')kind='HTTP_LINK';
       else kind='OTHER_SCHEME';
     }catch(e){kind='UNPARSEABLE';}
   }
   const t=(a.getAttribute('target')||'').toLowerCase();
   const target=t==='_blank'?'BLANK':t==='_self'?'SELF':t?'NAMED':'NONE';
   return {kind,host,target,inline:!!a.getAttribute('onclick')};
 };
 const linkInfo=describeLink(chosenLink);
 const metrics={meeting,day,click:false,iconTotal:allIcons.length,
   visibleExactCount:icons.length,dayIconCount:dayIcons.length,
   linkInfo,point:null,hints:[]};
 if($layoutFlag){metrics.hints=hints;return metrics;}
 if(!meeting||!day||dayIcons.length!==1||!chosenLink)return metrics;
 chosenLink.scrollIntoView({block:'center',inline:'center'});
 await sleep(90);
 const rect=chosenLink.getBoundingClientRect();
 const x=Math.round(rect.left+rect.width/2);
 const y=Math.round(rect.top+rect.height/2);
 if(rect.width>4&&rect.height>4&&x>0&&y>0&&
   x<innerWidth&&y<innerHeight){metrics.point={x,y};}
 return metrics;
})()
"@
    $clicked=Eval-CDP $js
    if($LayoutAudit){$result.layout_hints=@($clicked.hints)}
    $result.meeting_header_clicked=[bool]$clicked.meeting
    $result.day_header_clicked=[bool]$clicked.day
    $result.race_icon_matches=[int]$clicked.iconTotal
    $result.race_icon_visible_exact=[int]$clicked.visibleExactCount
    $result.race_icon_target_day_matches=[int]$clicked.dayIconCount
    $result.race_link_kind=[string]$clicked.linkInfo.kind
    $result.race_link_host=[string]$clicked.linkInfo.host
    $result.race_link_target=[string]$clicked.linkInfo.target
    $result.race_link_has_inline_handler=[bool]$clicked.linkInfo.inline
    if(-not $LayoutAudit -and $clicked.point -and
      $clicked.dayIconCount -eq 1 -and $clicked.meeting -and $clicked.day){
      $script:phase='TRUSTED_POINTING_DEVICE_CLICK'
      Invoke-Trusted-PointClick ([int]$clicked.point.x) ([int]$clicked.point.y)
      $result.race_click_status='TRUSTED_MOUSE_CLICK_EXACT_DAY_AND_RACE'
    }elseif($LayoutAudit){
      $result.race_click_status='LAYOUT_ONLY_NO_CLICK'
    }elseif($clicked.dayIconCount -gt 1){
      $result.race_click_status='AMBIGUOUS_DATE_RACE_MATCH_NO_CLICK'
    }else{
      $result.race_click_status='EXACT_DAY_RACE_NOT_FOUND_OR_OFFSCREEN_NO_CLICK'
    }
    Pump-CDP 5500
    # about:blank is a temporary popup state, not a playback domain.
    # Read only the local DevTools tab list, without URLs in diagnostic output.
    $opened=@()
    for($popupTry=0;$popupTry -lt 9;$popupTry++){
      $tabList=Invoke-RestMethod -Uri "http://127.0.0.1:$port/json/list" -TimeoutSec 5
      $opened=@($tabList|Where-Object {$_.type -eq 'page' -and $_.id -ne $page[0].id})
      if($opened.Count -ne 1){break}
      $popupInfo=Get-Safe-Popup-Info ([string]$opened[0].url)
      if($popupInfo.category -notin @('ABOUT_BLANK_OR_INTERNAL','EMPTY')){break}
      Start-Sleep -Milliseconds 400
    }
    $result.browser_tabs_after_click=@($tabList|Where-Object {$_.type -eq 'page'}).Count
    if($result.browser_tabs_after_click -gt 1){
      if($opened.Count -eq 1){
        $popup=$opened[0]
        $popupInfo=Get-Safe-Popup-Info ([string]$popup.url)
        $result.new_tab_url_type=[string]$popupInfo.category
        $result.new_tab_domain=[string]$popupInfo.host
        if($popupInfo.category -in @('BROWSER_INTERNAL','ABOUT_BLANK_OR_INTERNAL')){
          $result.new_tab_internal_kind=Get-Safe-Internal-Popup-Kind ([string]$popup.url)
        }
        if($popupInfo.category -eq 'HTTPS_HOST' -and
          $popupInfo.host -in @('front.player.boatrace-cdn.jp',
            'livebb.jlc.ne.jp','playback.api.streaks.jp')){
          $script:phase='POPUP_GUARDED_REPLAY_DIAGNOSTIC'
          $result.new_tab_guard_status=Inspect-Official-Playback-Tab $popup
        }else{
          $result.new_tab_guard_status='NOT_ALLOWLISTED_NO_REPLAY'
        }
      }else{
        $result.new_tab_guard_status='AMBIGUOUS_POPUP_COUNT_NO_REPLAY'
      }
    }
    if($PlaybackProbe){
      $script:phase='PLAYER_PLAYBACK_PROBE'
      # Observe one same-tab HTML5 video or one explicitly named play control.
      # Do not inspect cross-origin frames, service worker tokens, or network bodies.
      $probeJs=@'
(function(){
 const shown=e=>!!e.getClientRects().length && getComputedStyle(e).visibility!=='hidden';
 const videos=[...document.querySelectorAll('video')].filter(shown);
 const buttons=[...document.querySelectorAll('button,[role="button"]')].filter(shown)
   .filter(e=>/^(play|再生|動画を再生|再生する)$/i.test(
     ((e.getAttribute('aria-label')||e.getAttribute('title')||e.textContent||'').trim())));
 const candidate=videos.length===1?videos[0]:
   videos.length===0&&buttons.length===1?buttons[0]:null;
 let point=null;
 if(candidate){const r=candidate.getBoundingClientRect();
   const x=Math.round(r.x+r.width/2),y=Math.round(r.y+r.height/2);
   if(r.width>10&&r.height>10&&x>=0&&y>=0&&x<innerWidth&&y<innerHeight)
     point={x,y};}
 return {videos:videos.length,buttons:buttons.length,point,
   time:videos.length===1?Number(videos[0].currentTime)||0:null};
})()
'@
      $probe=Eval-CDP $probeJs
      $result.player_video_count=[int]$probe.videos
      $result.player_button_candidates=[int]$probe.buttons
      if($probe.point){
        Invoke-Trusted-PointClick ([int]$probe.point.x) ([int]$probe.point.y)
        $result.player_click='ONE_UNAMBIGUOUS_VISIBLE_CONTROL_CLICKED'
        Pump-CDP 2400
        $after=Eval-CDP '(function(){const v=[...document.querySelectorAll("video")].filter(e=>!!e.getClientRects().length);return v.length===1?{time:Number(v[0].currentTime)||0,paused:v[0].paused}:null})()'
        if($null -ne $after -and $null -ne $probe.time){
          $result.playback_time_progressed=([double]$after.time -gt [double]$probe.time + 0.25)
        }
      }else{$result.player_click='NO_UNIQUE_SAME_DOCUMENT_CONTROL'}
      $result.playback_probe=if($result.playback_time_progressed){'HTML5_TIME_ADVANCED'}else{'PLAYBACK_NOT_VERIFIED'}
    }
    $result.landing_http_status=$script:landingStatus
    $result.playback_api_statuses=@($script:apiStatuses|Sort-Object -Unique)
    $result.playback_api_requests=$script:apiGets
    if($script:apiStatuses -contains 403){$result.access_decision='PLAYBACK_API_HTTP_403'}
    elseif(@($script:apiStatuses|Where-Object {$_ -eq 200 -or $_ -eq 206}).Count){
      $result.access_decision='PLAYBACK_API_2XX_VIDEO_UNVERIFIED'
    }elseif($script:apiStatuses.Count){$result.access_decision='PLAYBACK_API_OTHER_HTTP_STATUS'}
    elseif($result.browser_tabs_after_click -gt 1){
      if($result.new_tab_guard_status -eq 'GUARDED_RELOAD_COMPLETE'){
        $result.access_decision='POPUP_CHECKED_NO_PLAYBACK_API_RESPONSE'
      }else{
        $result.access_decision='POPUP_NOT_ALLOWLISTED_API_UNVERIFIED'
      }
    }
    else{$result.access_decision='NO_PLAYBACK_API_RESPONSE'}
  }
}catch{
  $result.access_decision='EDGE_DIAGNOSTIC_FAILED'
  $result['failure_category']='EDGE_CDP_OR_NETWORK_UNAVAILABLE'
  $result['failure_stage']=$script:phase
  $result['failure_exception_type']=$_.Exception.GetType().Name
  $result['failure_script_line']=[int]$_.InvocationInfo.ScriptLineNumber
  if($SelfTest){$result['selftest_failure_detail']=[string]$_.Exception.Message}
}finally{
  $result.media_requests_blocked=$script:blockedMedia
  $result.opaque_requests_blocked=$script:blockedOpaque
  if($script:ws){try{$script:ws.Dispose()}catch{}}
  $script:messageBuffer.Dispose()
  if($process){try{& taskkill.exe /PID $process.Id /T /F 2>$null|Out-Null}catch{}}
  try{Remove-Item -LiteralPath $profile -Recurse -Force -ErrorAction SilentlyContinue}catch{}
}
$result|ConvertTo-Json -Depth 12
if($result.access_decision -in @('EDGE_SELFTEST_PASSED_NO_NETWORK','PLAYBACK_API_2XX_VIDEO_UNVERIFIED')){exit 0}
exit 2
