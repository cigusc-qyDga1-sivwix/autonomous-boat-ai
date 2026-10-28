# BOAT LAB: Built-in Windows PowerShell 5.1 + Microsoft Edge, no Docker.
# Temporary isolated browser; localhost ephemeral DevTools only. No video files.
param(
  [ValidatePattern('^\d{4}-\d{2}-\d{2}$')][string]$Date=(Get-Date).ToString('yyyy-MM-dd'),
  [ValidateRange(1,12)][int]$Race=1,
  [switch]$SelfTest
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
  $script:ws.SendAsync($seg,[Net.WebSockets.WebSocketMessageType]::Text,
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
      $host=''
      try {
        $u=[Uri]$url; $host=$u.Host.ToLowerInvariant()
        if($u.Scheme -notin @('https','http')){$allowed=$false}
      }catch{$allowed=$false}
      if((Is-Media $url) -or $type -eq 'Media'){
        $allowed=$false;$script:blockedMedia++
      }elseif($type -in @('XHR','Fetch')){
        if($method -ne 'GET' -or $host -notin @(
          'livebb.jlc.ne.jp','front.player.boatrace-cdn.jp','playback.api.streaks.jp'
        )){
          $allowed=$false;$script:blockedOpaque++
        }
        if($host -eq 'playback.api.streaks.jp'){
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
  race_click_status='NOT_ATTEMPTED';playback_api_statuses=@()
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
  $script:phase='FIND_EDGE'
  $edge=Find-Edge
  New-Item -ItemType Directory -Path $profile -Force|Out-Null
  $arguments=@('--headless=new','--disable-gpu','--no-first-run',
    '--no-default-browser-check','--remote-debugging-port=0',
    ('--user-data-dir="'+$profile+'"'),'about:blank')
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
  $script:ws.ConnectAsync($wsUrl,[Threading.CancellationToken]::None).GetAwaiter().GetResult()
  $script:phase='CDP_SETUP'
  foreach($cmd in @('Page.enable','Runtime.enable','Network.enable')){
    $id=Send-CDP $cmd
    $null=Await-CDP $id
  }
  if($SelfTest){
    $script:phase='CDP_SELFTEST'
    if((Eval-CDP '6*7') -ne 42){throw 'Browser selftest failed.'}
    $result.access_decision='EDGE_SELFTEST_PASSED_NO_NETWORK'
  }else{
    $script:phase='JLC_PAGE_DIAGNOSTIC'
    $id=Send-CDP 'Fetch.enable' @{patterns=@(@{urlPattern='*';requestStage='Request'})}
    $null=Await-CDP $id
    $id=Send-CDP 'Page.navigate' @{url='https://livebb.jlc.ne.jp/bb_top/sp_bb/tvod_10.php'}
    $null=Await-CDP $id
    Pump-CDP 2200
    $monthDay='{0}/{1}' -f [int]$d.Month,[int]$d.Day
    $dateSlash=$d.ToString('yyyy/MM/dd')
    $js=@"
(async()=>{
 const sleep=ms=>new Promise(r=>setTimeout(r,ms));
 const visible=e=>!!e.getClientRects().length&&getComputedStyle(e).visibility!=='hidden';
 const clickText=t=>{
   const a=[...document.querySelectorAll('span,button,a,div,td')]
     .filter(e=>visible(e)&&e.textContent.trim()===t);
   a.sort((x,y)=>x.querySelectorAll('*').length-y.querySelectorAll('*').length);
   if(!a.length)return false;a[0].click();return true;
 };
 const text=document.body?.innerText||'';
 const ds=[...new Set(text.match(/20[0-9]{2}\/[0-9]{1,2}\/[0-9]{1,2}/g)||[])]
   .filter(s=>new Date(s)<=new Date('$dateSlash')).sort();
 const meeting=ds.length?clickText(ds[ds.length-1]):false;
 await sleep(600);const day=clickText('$monthDay');await sleep(600);
 const icons=[...document.querySelectorAll('img[src*="$($Race)R.png"]')].filter(visible);
 if(!icons.length)return {meeting,day,click:false};
 icons[0].click();return {meeting,day,click:true};
})()
"@
    $clicked=Eval-CDP $js
    $result.race_click_status=if($clicked.click){'CLICKED_DATE_ASSOCIATION_UNVERIFIED'}else{'RACE_ICON_NOT_FOUND'}
    Pump-CDP 5500
    $result.landing_http_status=$script:landingStatus
    $result.playback_api_statuses=@($script:apiStatuses|Sort-Object -Unique)
    $result.playback_api_requests=$script:apiGets
    if($script:apiStatuses -contains 403){$result.access_decision='PLAYBACK_API_HTTP_403'}
    elseif(@($script:apiStatuses|Where-Object {$_ -eq 200 -or $_ -eq 206}).Count){
      $result.access_decision='PLAYBACK_API_2XX_VIDEO_UNVERIFIED'
    }elseif($script:apiStatuses.Count){$result.access_decision='PLAYBACK_API_OTHER_HTTP_STATUS'}
    else{$result.access_decision='NO_PLAYBACK_API_RESPONSE'}
  }
}catch{
  $result.access_decision='EDGE_DIAGNOSTIC_FAILED'
  $result['failure_category']='EDGE_CDP_OR_NETWORK_UNAVAILABLE'
  $result['failure_stage']=$script:phase
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
