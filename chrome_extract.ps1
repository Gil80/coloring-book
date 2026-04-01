<#
.SYNOPSIS
    Extract the largest image URL from each Chrome tab via Chrome DevTools Protocol.
    Designed to run on the Windows side from WSL2 via: powershell.exe -File chrome_extract.ps1

.DESCRIPTION
    Connects to Chrome's CDP HTTP endpoint and WebSocket to evaluate JavaScript
    in each tab. Returns one image URL per line on stdout.
    Status/errors go to stderr.

.PARAMETER Port
    Chrome DevTools port (default 9222)
#>
param(
    [int]$Port = 9222
)

$ErrorActionPreference = 'Stop'

# JavaScript to find images (same logic as get_chrome_urls.py)
$jsCode = @'
(() => {
    const imgs = Array.from(document.querySelectorAll('img'));
    const data = imgs
        .filter(i => i.src && i.src.startsWith('http'))
        .map(i => ({
            src: i.currentSrc || i.src,
            natW: i.naturalWidth  || 0,
            natH: i.naturalHeight || 0,
            natArea: (i.naturalWidth || 0) * (i.naturalHeight || 0),
            dispW: i.offsetWidth  || i.clientWidth  || 0,
            dispH: i.offsetHeight || i.clientHeight || 0,
            dispArea: (i.offsetWidth || i.clientWidth || 0)
                    * (i.offsetHeight || i.clientHeight || 0),
        }));
    return JSON.stringify(data);
})()
'@

function Get-ChromeTabs {
    param([int]$Port)
    try {
        $response = Invoke-WebRequest -Uri "http://localhost:$Port/json/list" -UseBasicParsing -TimeoutSec 5
        $targets = $response.Content | ConvertFrom-Json
        $tabs = @()
        foreach ($t in $targets) {
            if ($t.type -eq 'page' -and $t.url -match '^(http|file)') {
                $tabs += @{
                    url    = $t.url
                    title  = $t.title
                    ws_url = $t.webSocketDebuggerUrl
                }
            }
        }
        return $tabs
    }
    catch {
        Write-Error "Failed to get tabs from port ${Port}: $_"
        return @()
    }
}

function Invoke-CDPEvaluate {
    param(
        [string]$WsUrl,
        [string]$Expression
    )

    $ws = New-Object System.Net.WebSockets.ClientWebSocket
    $cts = New-Object System.Threading.CancellationTokenSource
    $cts.CancelAfter(10000)  # 10 second timeout

    try {
        $uri = [System.Uri]::new($WsUrl)
        $ws.ConnectAsync($uri, $cts.Token).GetAwaiter().GetResult() | Out-Null

        # Send Runtime.evaluate command
        $msg = @{
            id     = 1
            method = 'Runtime.evaluate'
            params = @{
                expression    = $Expression
                returnByValue = $true
            }
        } | ConvertTo-Json -Depth 5 -Compress

        $sendBuf = [System.Text.Encoding]::UTF8.GetBytes($msg)
        $segment = [System.ArraySegment[byte]]::new($sendBuf)
        $ws.SendAsync($segment, [System.Net.WebSockets.WebSocketMessageType]::Text, $true, $cts.Token).GetAwaiter().GetResult() | Out-Null

        # Receive response (accumulate fragments)
        $allBytes = New-Object System.Collections.Generic.List[byte]
        $recvBuf = New-Object byte[] 65536
        do {
            $recvSeg = [System.ArraySegment[byte]]::new($recvBuf)
            $result = $ws.ReceiveAsync($recvSeg, $cts.Token).GetAwaiter().GetResult()
            for ($i = 0; $i -lt $result.Count; $i++) {
                $allBytes.Add($recvBuf[$i])
            }
        } while (-not $result.EndOfMessage)

        $responseText = [System.Text.Encoding]::UTF8.GetString($allBytes.ToArray())

        # Parse and keep reading until we get id=1
        # Chrome may send events before our response
        $response = $responseText | ConvertFrom-Json
        if ($response.id -eq 1) {
            return $response.result.result.value
        }

        # If first message wasn't our response, keep reading
        for ($attempt = 0; $attempt -lt 10; $attempt++) {
            $allBytes.Clear()
            do {
                $recvSeg = [System.ArraySegment[byte]]::new($recvBuf)
                $result = $ws.ReceiveAsync($recvSeg, $cts.Token).GetAwaiter().GetResult()
                for ($i = 0; $i -lt $result.Count; $i++) {
                    $allBytes.Add($recvBuf[$i])
                }
            } while (-not $result.EndOfMessage)

            $responseText = [System.Text.Encoding]::UTF8.GetString($allBytes.ToArray())
            $response = $responseText | ConvertFrom-Json
            if ($response.id -eq 1) {
                return $response.result.result.value
            }
        }

        return $null
    }
    catch {
        Write-Host "  WebSocket error: $_" -ForegroundColor Yellow
        return $null
    }
    finally {
        if ($ws.State -eq [System.Net.WebSockets.WebSocketState]::Open) {
            try {
                $ws.CloseAsync(
                    [System.Net.WebSockets.WebSocketCloseStatus]::NormalClosure,
                    'done',
                    [System.Threading.CancellationToken]::None
                ).GetAwaiter().GetResult() | Out-Null
            } catch {}
        }
        $ws.Dispose()
        $cts.Dispose()
    }
}

function Get-LargestImageUrl {
    param([string]$RawJson)

    if (-not $RawJson) { return $null }

    try {
        $images = $RawJson | ConvertFrom-Json
    }
    catch {
        return $null
    }

    if ($images.Count -eq 0) { return $null }

    $MIN_DIM = 100

    # Filter to big images
    $big = @($images | Where-Object { $_.natW -gt $MIN_DIM -and $_.natH -gt $MIN_DIM })
    if ($big.Count -eq 0) {
        $big = @($images | Where-Object { $_.natArea -gt 0 })
    }
    if ($big.Count -eq 0) {
        $big = @($images | Where-Object { $_.dispArea -gt 0 })
    }
    if ($big.Count -eq 0) { return $null }

    # Sort by natArea desc, then dispArea desc
    $sorted = $big | Sort-Object -Property @{Expression={$_.natArea}; Descending=$true}, @{Expression={$_.dispArea}; Descending=$true}
    return $sorted[0].src
}

# --- Main ---

# Check Chrome is accessible
try {
    $versionResp = Invoke-WebRequest -Uri "http://localhost:$Port/json/version" -UseBasicParsing -TimeoutSec 3
    $versionInfo = $versionResp.Content | ConvertFrom-Json
    [Console]::Error.WriteLine("Chrome found on port ${Port}: $($versionInfo.Browser)")
}
catch {
    [Console]::Error.WriteLine("No Chrome DevTools on port $Port. Launch Chrome with --remote-debugging-port=$Port")
    exit 1
}

$tabs = Get-ChromeTabs -Port $Port

if ($tabs.Count -eq 0) {
    [Console]::Error.WriteLine("No page tabs found.")
    exit 2
}

[Console]::Error.WriteLine("Found $($tabs.Count) tab(s)")

$imageUrls = @()

foreach ($tab in $tabs) {
    $title = if ($tab.title.Length -gt 60) { $tab.title.Substring(0, 60) } else { $tab.title }
    if (-not $title) { $title = $tab.url.Substring(0, [Math]::Min(60, $tab.url.Length)) }
    [Console]::Error.WriteLine("Inspecting: $title")

    if (-not $tab.ws_url) {
        [Console]::Error.WriteLine("  -> (no WebSocket URL)")
        continue
    }

    $rawJson = Invoke-CDPEvaluate -WsUrl $tab.ws_url -Expression $jsCode

    $imgUrl = Get-LargestImageUrl -RawJson $rawJson

    if ($imgUrl) {
        $imageUrls += $imgUrl
        $display = if ($imgUrl.Length -gt 120) { $imgUrl.Substring(0, 120) } else { $imgUrl }
        [Console]::Error.WriteLine("  -> $display")
    }
    else {
        [Console]::Error.WriteLine("  -> (no image found)")
    }
}

if ($imageUrls.Count -eq 0) {
    [Console]::Error.WriteLine("No images found in any tab.")
    exit 2
}

# Output image URLs to stdout (one per line)
foreach ($url in $imageUrls) {
    Write-Output $url
}
