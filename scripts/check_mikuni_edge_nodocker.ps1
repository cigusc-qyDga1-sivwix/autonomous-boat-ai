# BOAT LAB: Built-in Windows PowerShell 5.1 + Microsoft Edge, no Docker.
# Temporary isolated browser; localhost ephemeral DevTools only. No video files.
param(
  [ValidatePattern('^\d{4}-\d{2}-\d{2}$')][string]$Date=(Get-Date).ToString('yyyy-MM-dd'),
  [ValidateRange(1,12)][int]$Race=1,
  [switch]$SelfTest,
  [switch]$LayoutAudit,
  [switch]$VisibleEdge,
  [switch]$HoldOpen,
  [switch]$AutoPlay,
  [switch]$PcSite
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

function Classify-Official-Player-Open([string]$raw,[string]$date,[int]$race){
  # Classify only the public URL type; never print or persist a full URL,
  # authentication string, query or media token.
  if([string]::IsNullOrWhiteSpace($raw)){return 'BLANK_OR_EMPTY_WINDOW_OPEN'}
  try {$u=[Uri]$raw}catch{return 'UNPARSEABLE_WINDOW_OPEN'}
  if($u.Scheme -eq 'about'){return 'BLANK_OR_EMPTY_WINDOW_OPEN'}
  if($u.Scheme -ne 'https' -or $u.Host.ToLowerInvariant() -ne 'livebb.jlc.ne.jp' -or
     $u.AbsolutePath -ne '/bb_top/sp_bb/streamer/streamer26pi.php'){
    return 'WINDOW_OPEN_NOT_OFFICIAL_PLAYER'
  }
  $values=@{}
  foreach($part in $u.Query.TrimStart('?').Split('&')){
    $pair=$part.Split('=',2)
    if($pair.Count -eq 2 -and $pair[0] -in @('date','race','jo')){
      $values[$pair[0]]=$pair[1]
    }
  }
  $ymd=$date.Replace('-','')
  if($values['date'] -ne $ymd -or
     $values['race'] -notin @([string]$race,('{0:D2}' -f $race)) -or
     $values['jo'] -ne '10'){
    return 'OFFICIAL_PLAYER_WRONG_RACE_OR_DATE'
  }
  return 'OFFICIAL_PLAYER_MATCHED'
}

function Process-Event($event){
  switch([string]$event.method){
    'Runtime.consoleAPICalled' {
      # Observe only an exact application-generated marker. Never record
      # arbitrary page console content, URLs or page-provided code.
      $args=@($event.params.args)
      if($args.Count -ge 1){
        $marker=[string]$args[0].value
        if($marker -eq '__BOATLABS_RACE_CLICK_TRUSTED__'){
          $script:trustedRaceClickDelivered=$true
          $script:trustedRaceClickSeen=$true
        }
        if($marker -eq '__BOATLABS_RACE_MOUSEDOWN__'){
          $script:raceMouseDownSeen=$true
        }
        if($marker -eq '__BOATLABS_RACE_MOUSEUP__'){
          $script:raceMouseUpSeen=$true
        }
      }
    }
    'Page.windowOpen' {
      $script:windowOpenEventCount++
      $kind=Classify-Official-Player-Open ([string]$event.params.url) $Date $Race
      if($kind -eq 'OFFICIAL_PLAYER_MATCHED'){
        $script:windowOpenEventKind=$kind
      }elseif($script:windowOpenEventKind -ne 'OFFICIAL_PLAYER_MATCHED'){
        $script:windowOpenEventKind=$kind
      }
    }
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

function Try-Official-Play($target,[string]$date,[int]$race){
  try {$u=[Uri][string]$target.url}catch{return 'BAD_TARGET'}
  if($u.Scheme -ne 'https' -or $u.Host.ToLowerInvariant() -ne 'livebb.jlc.ne.jp' -or
    $u.AbsolutePath -ne '/bb_top/sp_bb/streamer/streamer26pi.php'){return 'UNVERIFIED_OFFICIAL_REPLAY'}
  Add-Type -AssemblyName System.Web
  $q=[System.Web.HttpUtility]::ParseQueryString($u.Query)
  if($q['date'] -ne $date.Replace('-','') -or $q['race'] -notin @([string]$race,('{0:D2}' -f $race)) -or
    $q['jo'] -ne '10'){return 'WRONG_DATE_RACE'}
  $socket=[Uri][string]$target.webSocketDebuggerUrl
  if($socket.Scheme -ne 'ws' -or $socket.Host -notin @('localhost','127.0.0.1')){
    return 'NONLOCAL_SOCKET_REJECTED'
  }
  if($script:ws){$script:ws.Dispose()}
  $script:pendingRead=$null
  $script:messageBuffer.Dispose()
  $script:messageBuffer=New-Object IO.MemoryStream
  $script:ws=New-Object Net.WebSockets.ClientWebSocket
  [void]$script:ws.ConnectAsync($socket,[Threading.CancellationToken]::None).GetAwaiter().GetResult()
  foreach($cmd in @('Page.enable','Runtime.enable')){
    $id=Send-CDP $cmd;$null=Await-CDP $id
  }
  $pageStatus=Eval-CDP @'
(()=>{const t=(document.body?.innerText||'').trim();return t==='File not found.'?'SERVER_REPLAY_FILE_NOT_FOUND':'CHECK_PLAY_CONTROL';})()
'@
  if($pageStatus -eq 'SERVER_REPLAY_FILE_NOT_FOUND'){return $pageStatus}
  $point=$null
  for($attempt=0;$attempt -lt 10;$attempt++){
    $point=Eval-CDP @'
(()=>{
 const visible=e=>{const r=e.getBoundingClientRect();return r.width>15&&r.height>15&&r.left>=0&&r.top>=0&&r.right<=innerWidth&&r.bottom<=innerHeight};
 const candidates=[...document.querySelectorAll('button,[role="button"],.vjs-big-play-button,.jw-display-icon-container')]
  .filter(visible).filter(e=>/play|再生|start/i.test([e.getAttribute('aria-label'),e.title,e.className,e.textContent].join(' ')));
 if(candidates.length!==1)return {kind:'PLAY_CONTROL_NOT_UNIQUE',count:candidates.length};
 const e=candidates[0],r=e.getBoundingClientRect(),x=Math.round(r.left+r.width/2),y=Math.round(r.top+r.height/2);
 const top=document.elementFromPoint(x,y);
 if(!top||!(top===e||e.contains(top)))return {kind:'PLAY_CONTROL_OBSCURED'};
 return {kind:'FOUND',x,y};
})()
'@
    if($point.kind -eq 'FOUND'){break}
    Start-Sleep -Milliseconds 400
  }
  if($point.kind -ne 'FOUND'){return [string]$point.kind}
  Invoke-Trusted-PointClick ([int]$point.x) ([int]$point.y)
  Start-Sleep -Milliseconds 1800
  return [string](Eval-CDP @'
(()=>{
 const v=[...document.querySelectorAll('video')];
 if(v.some(e=>!e.paused&&!e.ended))return 'VIDEO_ELEMENT_PLAYING';
 return v.length?'CLICKED_PLAY_UNCONFIRMED':'CLICKED_VIDEO_ELEMENT_NOT_FOUND';
})()
'@)
}

function Get-Pc-Page-Metrics {
  # Count only generic, non-identifying player/controls metadata. No URLs,
  # page text, video frames, tokens, cookies or media requests are recorded.
  $pcJs=@'
(()=>{
  const tally={dom_status:document.readyState,iframe_count:0,
    accessible_frame_count:0,inaccessible_frame_count:0,video_elements:0,playing_video_elements:0,object_elements:0,embed_elements:0,canvas_elements:0,
    replay_menu_candidates:0,exhibition_menu_candidates:0,
    race_one_candidates:0};
  const scanned=new Set();
  const scan=doc=>{
    if(!doc || scanned.has(doc))return;
    scanned.add(doc); tally.accessible_frame_count++;
    tally.object_elements+=doc.querySelectorAll('object').length;
    tally.embed_elements+=doc.querySelectorAll('embed').length;
    tally.canvas_elements+=doc.querySelectorAll('canvas').length;
    for(const v of doc.querySelectorAll('video')){
      tally.video_elements++;
      if(!v.paused && !v.ended && v.readyState>=2 && v.currentTime>0){
        tally.playing_video_elements++;
      }
    }
    const controls=[...doc.querySelectorAll('a,button,[role="button"],input[type="button"],input[type="submit"]')];
    for(const el of controls){
      let label=[el.textContent,el.getAttribute('aria-label'),el.getAttribute('value'),el.getAttribute('title')].filter(Boolean).join(' ').trim().replace(/\s+/g,' ');
      if(label.length>90)continue;
      if(/展示リプレイ|展示\s*リプレイ/.test(label))tally.exhibition_menu_candidates++;
      else if(/過去のレース|リプレイ/.test(label))tally.replay_menu_candidates++;
      if(/^(?:1R|1Ｒ|１Ｒ|1レース|１レース)$/.test(label))tally.race_one_candidates++;
    }
    const frames=[...doc.querySelectorAll('iframe,frame')];
    tally.iframe_count+=frames.length;
    for(const el of frames){
      let inner=null;
      try{inner=el.contentDocument}catch(e){}
      if(inner)scan(inner);
      else tally.inaccessible_frame_count++;
    }
  };
  scan(document);
  return tally;
})()
'@
  return (Eval-CDP $pcJs)
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
$script:windowOpenEventCount=0;$script:windowOpenEventKind='NO_WINDOW_OPEN_EVENT'
$script:trustedRaceClickDelivered=$false
$script:trustedRaceClickSeen=$false;$script:raceMouseDownSeen=$false;$script:raceMouseUpSeen=$false
$process=$null
$script:phase='START'
$profile=Join-Path ([IO.Path]::GetTempPath()) ('boatlabs-edge-'+[guid]::NewGuid().ToString('N'))
$result=[ordered]@{
  schema='boatlabs.mikuni_edge_nodocker.v1';date=$Date;venue='三国';race=$Race
  access_decision='NOT_RUN';landing_http_status=$null
  edge_start_mode=if($VisibleEdge){'VISIBLE_ISOLATED'}else{'HEADLESS_ISOLATED'}
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
  playback_auto_click=if($AutoPlay){'NOT_ATTEMPTED'}else{'NOT_REQUESTED'}
  replay_navigation_mode='NOT_ATTEMPTED'
  window_open_events=0;window_open_kind='NO_WINDOW_OPEN_EVENT'
  trusted_race_click_delivered=$false
  race_mouse_down_seen=$false;race_mouse_up_seen=$false;race_click_seen=$false
  race_click_point_rechecked=$false
  race_click_hit_verified=$false;race_click_event_observed='NOT_CHECKED'
  race_click_hit_reason='NOT_EVALUATED'
  fetch_mode_at_race_click='BLOCKED_DIAGNOSTIC'
  opaque_requests_blocked_before_click=0
  pc_site_mode=if($PcSite){'MANUAL_PLAYBACK_PROBE'}else{'OFF'}
  pc_initial=$null;pc_observed_targets=@();pc_playing_video_elements=0
  pc_manual_playback_reported=$false;pc_inaccessible_frames_observed=0
  pc_embedded_players_observed=0;pc_video_surface_diagnosis='NOT_OBSERVED'
  note='API response status alone is not a verified video download.'
}
try {
  $d=[datetime]::MinValue
  if(-not [datetime]::TryParseExact($Date,'yyyy-MM-dd',
    [Globalization.CultureInfo]::InvariantCulture,
    [Globalization.DateTimeStyles]::None,[ref]$d)){throw 'Invalid calendar date.'}
  if($AutoPlay -and -not $VisibleEdge){throw 'AutoPlay requires -VisibleEdge.'}
  if($PcSite -and -not $VisibleEdge){throw 'PcSite requires -VisibleEdge.'}
  if($PcSite -and ($AutoPlay -or $LayoutAudit -or $SelfTest)){
    throw 'PcSite is a separate, manual UI diagnostic mode; omit AutoPlay/LayoutAudit/SelfTest.'
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
    $null=Eval-CDP "(function(){const b=document.querySelector('button');for(const k of ['mousedown','mouseup','click'])b.addEventListener(k,e=>{if(e.isTrusted)console.log(k==='mousedown'?'__BOATLABS_RACE_MOUSEDOWN__':k==='mouseup'?'__BOATLABS_RACE_MOUSEUP__':'__BOATLABS_RACE_CLICK_TRUSTED__')});return true;})()"
    $script:raceMouseDownSeen=$false;$script:raceMouseUpSeen=$false;$script:trustedRaceClickSeen=$false
    Invoke-Trusted-PointClick 55 43
    Pump-CDP 250
    if(-not ($script:raceMouseDownSeen -and $script:raceMouseUpSeen -and $script:trustedRaceClickSeen)){
      throw 'Mouse event telemetry did not capture down, up and click.'
    }
    $pcTest=Get-Pc-Page-Metrics
    if($pcTest.accessible_frame_count -lt 1 -or
       $null -eq $pcTest.inaccessible_frame_count -or
       $null -eq $pcTest.embed_elements -or
       $pcTest.video_elements -ne 0 -or
       $pcTest.playing_video_elements -ne 0){
      throw 'PC page DOM probe self-test failed.'
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
    if((Classify-Official-Player-Open 'https://livebb.jlc.ne.jp/bb_top/sp_bb/streamer/streamer26pi.php?tenji=1&jo=10&race=01&date=20261028' '2026-10-28' 1) -ne 'OFFICIAL_PLAYER_MATCHED'){
      throw 'Official window-open classifier self-test failed'
    }
    if((Classify-Official-Player-Open 'https://livebb.jlc.ne.jp/bb_top/sp_bb/streamer/streamer26pi.php?tenji=1&jo=10&race=11&date=20261028' '2026-10-28' 1) -ne 'OFFICIAL_PLAYER_WRONG_RACE_OR_DATE'){
      throw 'Official window-open classifier must reject different race'
    }
    if((Classify-Official-Player-Open 'about:blank' '2026-10-28' 1) -ne 'BLANK_OR_EMPTY_WINDOW_OPEN'){
      throw 'Blank window-open classification failed'
    }
    $result.access_decision='EDGE_SELFTEST_PASSED_NO_NETWORK'
  }elseif($PcSite){
    $script:phase='PC_OFFICIAL_ENTRY'
    # This is the official, documented PC landing PAGE, not a synthesized
    # media URL or unauthorized replay endpoint.
    $id=Send-CDP 'Page.navigate' @{
      url='https://livebb.jlc.ne.jp/bb_top/new_bb/index.php?tpl=1'
    }
    $nav=Await-CDP $id
    if($nav.errorText){throw 'Official PC landing page navigation failed.'}
    Pump-CDP 2500
    $result.pc_initial=Get-Pc-Page-Metrics
    Write-Host 'BOAT LAB PC probe: in this isolated Edge window, open Mikuni exhibition replay and play it manually.'
    Write-Host 'Use the isolated Edge opened by this script, NOT your usual Edge.'
    Write-Host 'After trying to play the video, type Y if it was visibly playing, otherwise press ENTER.'
    $manualAnswer=Read-Host 'Video visibly played in this Edge? (Y/Enter)'
    $result.pc_manual_playback_reported=([string]$manualAnswer -match '^[yY]$')
    $script:phase='PC_OBSERVE_ATTACHED_TABS'
    # The isolated CDP port belongs only to this diagnostic Edge profile.
    $tabs=Invoke-RestMethod -Uri "http://127.0.0.1:$port/json/list" -TimeoutSec 5
    $records=@()
    foreach($target in @($tabs|Where-Object {$_.type -eq 'page'})){
      $safe=Get-Safe-Popup-Info ([string]$target.url)
      $item=[ordered]@{page_kind=[string]$safe.category;
        host=if($safe.host -eq 'livebb.jlc.ne.jp'){'JLC_PC_OFFICIAL'}else{'OTHER_OR_INTERNAL'};
        metrics=$null}
      if($safe.category -eq 'HTTPS_HOST' -and $safe.host -eq 'livebb.jlc.ne.jp'){
        $socket=[Uri][string]$target.webSocketDebuggerUrl
        if($socket.Scheme -eq 'ws' -and $socket.Host -in @('127.0.0.1','localhost')){
          if($script:ws){$script:ws.Dispose()}
          $script:pendingRead=$null
          $script:messageBuffer.Dispose()
          $script:messageBuffer=New-Object IO.MemoryStream
          $script:ws=New-Object Net.WebSockets.ClientWebSocket
          [void]$script:ws.ConnectAsync($socket,[Threading.CancellationToken]::None).GetAwaiter().GetResult()
          $id=Send-CDP 'Runtime.enable';$null=Await-CDP $id
          try{
            $item.metrics=Get-Pc-Page-Metrics
            $result.pc_playing_video_elements += [int]$item.metrics.playing_video_elements
            $result.pc_inaccessible_frames_observed += [int]$item.metrics.inaccessible_frame_count
            $result.pc_embedded_players_observed += [int]$item.metrics.object_elements
            $result.pc_embedded_players_observed += [int]$item.metrics.embed_elements
          }catch{
            $item.metrics=@{dom_status='UNAVAILABLE';video_elements=0;playing_video_elements=0}
          }
        }
      }
      $records+= $item
    }
    $result.pc_observed_targets=$records
    if($result.pc_playing_video_elements -gt 0){
      $result.pc_video_surface_diagnosis='HTML_VIDEO_PLAYING'
      $result.access_decision='PC_MANUAL_VIDEO_ELEMENT_PLAYING_VERIFIED'
    }elseif($result.pc_inaccessible_frames_observed -gt 0){
      $result.pc_video_surface_diagnosis='CROSS_ORIGIN_OR_UNAVAILABLE_IFRAME'
      $result.access_decision='PC_VIDEO_IN_INACCESSIBLE_FRAME_POSSIBLE_NOT_VERIFIED'
    }elseif($result.pc_embedded_players_observed -gt 0){
      $result.pc_video_surface_diagnosis='OBJECT_OR_EMBED_PLAYER_PRESENT'
      $result.access_decision='PC_EMBEDDED_PLAYER_UNVERIFIED'
    }else{
      $result.pc_video_surface_diagnosis='NO_HTML_VIDEO_FOUND'
      $result.access_decision='PC_VIDEO_ELEMENT_PLAYBACK_NOT_VERIFIED'
    }
    # The PC branch is observation-only: no media capture or prediction writes.
  }else{
    $script:phase='JLC_PAGE_DIAGNOSTIC'
    $id=Send-CDP 'Fetch.enable' @{patterns=@(@{urlPattern='*';requestStage='Request'})}
    $null=Await-CDP $id
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
   linkInfo,point:null,hints:[],hitVerified:false,hitReason:'NOT_EVALUATED'};
 if($layoutFlag){metrics.hints=hints;return metrics;}
 if(!meeting||!day||dayIcons.length!==1||!chosenLink){
   metrics.hitReason='NO_UNIQUE_DAY_RACE_LINK';
   return metrics;
 }
 const icon=dayIcons[0];
 if(!chosenLink.contains(icon)){
   metrics.hitReason='ICON_NOT_CHILD_OF_LINK';
   return metrics;
 }
 // The anchor can span an entire table cell; its geometric center may not
 // actually point to the race icon. Check bounded points INSIDE the exact
 // icon, not inside the anchor, and reject any obstructing outside element.
 icon.scrollIntoView({block:'center',inline:'center'});
 await sleep(150);
 const rect=icon.getBoundingClientRect();
 if(rect.width<6||rect.height<6){
   metrics.hitReason='TARGET_ICON_TOO_SMALL';
   return metrics;
 }
 const candidates=[[0.5,0.5],[0.35,0.5],[0.65,0.5],
                   [0.5,0.35],[0.5,0.65]];
 let hadViewportPoint=false,hadTopElement=false;
 for(const [dx,dy] of candidates){
   const x=Math.round(rect.left+rect.width*dx);
   const y=Math.round(rect.top+rect.height*dy);
   if(x<1||y<1||x>=innerWidth||y>=innerHeight)continue;
   hadViewportPoint=true;
   const hit=document.elementFromPoint(x,y);
   if(!hit)continue;
   hadTopElement=true;
   if(hit===chosenLink||chosenLink.contains(hit)){
     metrics.hitVerified=true;
     metrics.hitReason='EXACT_DAY_RACE_ICON_HIT';
     metrics.point={x,y};
     break;
   }
 }
 if(!metrics.hitVerified){
   metrics.hitReason=!hadViewportPoint?'ICON_OFFSCREEN':
     !hadTopElement?'NO_ELEMENT_AT_ICON':'ICON_OBSCURED_BY_OTHER_ELEMENT';
   return metrics;
 }
 window.__boatlabsRaceClickTrace='NOT_OBSERVED';
 window.__boatlabsRaceExpectedAnchor=chosenLink;
 // Keep the detector active for an independently delivered mouseup/click.
 // A once-only document listener could be consumed by an unrelated click.
 for(const kind of ['mousedown','mouseup','click']){
   document.addEventListener(kind,e=>{
     if(e.target===chosenLink||chosenLink.contains(e.target)){
       if(!e.isTrusted)return;
       if(kind==='mousedown')console.log('__BOATLABS_RACE_MOUSEDOWN__');
       if(kind==='mouseup')console.log('__BOATLABS_RACE_MOUSEUP__');
       if(kind==='click'){
         window.__boatlabsRaceClickTrace='TRUSTED_CLICK_ON_RACE_LINK';
         console.log('__BOATLABS_RACE_CLICK_TRUSTED__');
       }
     }
   },{capture:true});
 }
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
    $result.race_click_hit_verified=[bool]$clicked.hitVerified
    $result.race_click_hit_reason=[string]$clicked.hitReason
    if(-not $LayoutAudit -and $clicked.point -and
      $clicked.dayIconCount -eq 1 -and $clicked.meeting -and $clicked.day){
      $script:phase='TRUSTED_POINTING_DEVICE_CLICK'
      # Opt-in browser playback must be allowed to perform the web site's
      # normal network operations BEFORE clicking. The previous probe blocked
      # an XHR and may have prevented the replay window from being created.
      # Never disable the request guard for ordinary diagnostics or CI.
      if($AutoPlay -and $VisibleEdge){
        $result.opaque_requests_blocked_before_click=$script:blockedOpaque
        $id=Send-CDP 'Fetch.disable'
        $null=Await-CDP $id
        $result.fetch_mode_at_race_click='NORMAL_BROWSER_USER_OPT_IN'
      }
      # Verify the target did not move since the earlier hit-test. Explicit
      # focus helps distinguish background Edge input from page interaction.
      $id=Send-CDP 'Page.bringToFront'
      $null=Await-CDP $id
      $preX=[int]$clicked.point.x
      $preY=[int]$clicked.point.y
      $verifyJs="(()=>{const a=window.__boatlabsRaceExpectedAnchor;const h=document.elementFromPoint($preX,$preY);return !!a&&document.contains(a)&&!!h&&(h===a||a.contains(h));})()"
      $result.race_click_point_rechecked=[bool](Eval-CDP $verifyJs)
      if($result.race_click_point_rechecked){
        Invoke-Trusted-PointClick $preX $preY
        $result.race_click_status='TRUSTED_MOUSE_CLICK_EXACT_DAY_AND_RACE'
      }else{
        $result.race_click_status='RACE_TARGET_CHANGED_BEFORE_CLICK_NO_CLICK'
      }
      try{
        $eventTrace=Eval-CDP "(function(){return String(window.__boatlabsRaceClickTrace||'NOT_OBSERVED')})()"
        $result.race_click_event_observed=[string]$eventTrace
      }catch{
        # The page may have navigated as a direct result of the click.
        $result.race_click_event_observed='PAGE_CHANGED_OR_NOT_AVAILABLE'
      }
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
    # Important: the official page works from a normal UI click, but a
    # manually reconstructed URL returned "File not found." on the user's PC.
    # Never synthesize a replay link or force Page.navigate to it. Instead,
    # inspect only the browser target reached through the real site's click.
    if($AutoPlay -and $VisibleEdge -and $result.browser_tabs_after_click -eq 1){
      if($result.race_click_status -ne 'TRUSTED_MOUSE_CLICK_EXACT_DAY_AND_RACE' -or
         $result.race_icon_target_day_matches -ne 1){
        $result.playback_auto_click='EXACT_RACE_NOT_VERIFIED_NO_REPLAY'
      }else{
        $onlyTabs=@($tabList|Where-Object {$_.type -eq 'page'})
        $only=$onlyTabs[0]
        $onlyUrl=[string]$only.url
        try {$onlyUri=[Uri]$onlyUrl}catch{$onlyUri=$null}
        if($onlyUri -and $onlyUri.Scheme -eq 'https' -and
           $onlyUri.Host.ToLowerInvariant() -eq 'livebb.jlc.ne.jp' -and
           $onlyUri.AbsolutePath -eq '/bb_top/sp_bb/streamer/streamer26pi.php'){
          $result.replay_navigation_mode='OFFICIAL_PLAYER_ALREADY_IN_CDP_TAB'
          $script:phase='OPT_IN_PLAY_EXISTING_CDP_TARGET'
          $result.playback_auto_click=Try-Official-Play $only $Date $Race
        }else{
          # The visible popup could be outside this diagnostic CDP session.
          # Do not guess at a URL, send credentials, or click blindly.
          $result.replay_navigation_mode='NATIVE_CLICK_ONLY_NO_DIRECT_URL'
          $result.playback_auto_click='PLAYER_TARGET_NOT_ATTACHED_NO_CLICK'
        }
      }
    }
    if($result.browser_tabs_after_click -gt 1){
      if($opened.Count -eq 1){
        $popup=$opened[0]
        $popupInfo=Get-Safe-Popup-Info ([string]$popup.url)
        $result.new_tab_url_type=[string]$popupInfo.category
        $result.new_tab_domain=[string]$popupInfo.host
        if($popupInfo.category -in @('BROWSER_INTERNAL','ABOUT_BLANK_OR_INTERNAL')){
          $result.new_tab_internal_kind=Get-Safe-Internal-Popup-Kind ([string]$popup.url)
        }
        if($AutoPlay -and $VisibleEdge){
          if($popupInfo.category -eq 'BROWSER_INTERNAL' -or
             $popupInfo.category -eq 'ABOUT_BLANK_OR_INTERNAL'){
            $result.replay_navigation_mode='BROWSER_INTERNAL_NOT_OFFICIAL_REPLAY'
            $result.playback_auto_click='NO_VERIFIED_PLAYER_TARGET_NO_CLICK'
          }else{
            # Try-Official-Play independently validates HTTPS, official JLC
            # host, precise player path, venue/date/race, and local CDP socket.
            $script:phase='OPT_IN_REPLAY_PLAY'
            $result.playback_auto_click=Try-Official-Play $popup $Date $Race
            if($result.playback_auto_click -eq 'UNVERIFIED_OFFICIAL_REPLAY'){
              $result.replay_navigation_mode='NEW_TARGET_NOT_OFFICIAL_REPLAY'
            }else{
              $result.replay_navigation_mode='OBSERVED_VERIFIED_JLC_POPUP'
            }
          }
        }elseif($popupInfo.category -eq 'HTTPS_HOST' -and
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
    $result.trusted_race_click_delivered=[bool]$script:trustedRaceClickDelivered
    $result.race_mouse_down_seen=[bool]$script:raceMouseDownSeen
    $result.race_mouse_up_seen=[bool]$script:raceMouseUpSeen
    $result.race_click_seen=[bool]$script:trustedRaceClickSeen
    $result.window_open_events=$script:windowOpenEventCount
    $result.window_open_kind=$script:windowOpenEventKind
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
  if(($HoldOpen -or $AutoPlay) -and $VisibleEdge -and -not $PcSite -and -not $SelfTest -and $process -and -not $process.HasExited){
    # This is an explicitly interactive inspection mode, never enabled in CI.
    # Keep the isolated Edge window and its page available for manual viewing.
    # Read-Host only changes process lifetime; it does not record video or credentials.
    Write-Host 'BOAT LAB: Edge window is held open for inspection. Press ENTER here to close it.'
    try { $null=Read-Host 'Press ENTER when finished inspecting the playback page' }catch{}
  }
  if($script:ws){try{$script:ws.Dispose()}catch{}}
  $script:messageBuffer.Dispose()
  if($process){try{& taskkill.exe /PID $process.Id /T /F 2>$null|Out-Null}catch{}}
  try{Remove-Item -LiteralPath $profile -Recurse -Force -ErrorAction SilentlyContinue}catch{}
}
$result|ConvertTo-Json -Depth 12
if($result.access_decision -in @('EDGE_SELFTEST_PASSED_NO_NETWORK','PLAYBACK_API_2XX_VIDEO_UNVERIFIED','PC_MANUAL_VIDEO_ELEMENT_PLAYING_VERIFIED','PC_VIDEO_IN_INACCESSIBLE_FRAME_POSSIBLE_NOT_VERIFIED','PC_EMBEDDED_PLAYER_UNVERIFIED','PC_VIDEO_ELEMENT_PLAYBACK_NOT_VERIFIED')){exit 0}
exit 2
