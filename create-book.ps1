<#
.SYNOPSIS
    Windows shortcut wrapper: runs create-book.py in WSL and shows a notification when done.
#>

# Run the coloring book script in WSL
$output = wsl -d Ubuntu -- bash -c "cd /home/gil/projects/coloring-book && venv/bin/python create-book.py --no-llm 2>&1"
$exitCode = $LASTEXITCODE

# Show output in console
$output | ForEach-Object { Write-Host $_ }

# Windows notification
Add-Type -AssemblyName System.Windows.Forms

$notify = New-Object System.Windows.Forms.NotifyIcon
$notify.Icon = [System.Drawing.SystemIcons]::Information
$notify.Visible = $true

if ($exitCode -eq 0) {
    $notify.BalloonTipTitle = "Coloring Book Ready"
    $notify.BalloonTipText = "Your coloring book has been created!"
    $notify.BalloonTipIcon = [System.Windows.Forms.ToolTipIcon]::Info

    # Open the DOCX file
    $docxPath = "\\wsl$\Ubuntu\home\gil\projects\coloring-book\Kawaii_Coloring_Book_Final.docx"
    if (Test-Path $docxPath) {
        Start-Process $docxPath
    }
} else {
    $notify.BalloonTipTitle = "Coloring Book Failed"
    $notify.BalloonTipText = "Something went wrong. Check the console output."
    $notify.BalloonTipIcon = [System.Windows.Forms.ToolTipIcon]::Error
}

$notify.ShowBalloonTip(5000)
Start-Sleep -Seconds 6
$notify.Dispose()

# Keep window open on failure so user can read errors
if ($exitCode -ne 0) {
    Write-Host "`nPress any key to close..."
    $null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
}
