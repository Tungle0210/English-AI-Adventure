param([string]$Source,[string]$Destination)
$ErrorActionPreference='Stop'
$deck=$null
$powerpoint=$null
try {
    New-Item -ItemType Directory -Force -Path $Destination | Out-Null
    $powerpoint=New-Object -ComObject PowerPoint.Application
    $originalSecurity=$powerpoint.AutomationSecurity
    $originalAlerts=$powerpoint.DisplayAlerts
    $powerpoint.AutomationSecurity=3
    $powerpoint.DisplayAlerts=1
    $deck=$powerpoint.Presentations.Open($Source,$true,$false,$false)
    $height=[int](1440*$deck.PageSetup.SlideHeight/$deck.PageSetup.SlideWidth)
    foreach($slide in $deck.Slides){
        $slide.Export((Join-Path $Destination ('slide-'+$slide.SlideIndex+'.png')),'PNG',1440,$height)
    }
} finally {
    if($null -ne $deck){$deck.Close();[void][Runtime.InteropServices.Marshal]::ReleaseComObject($deck)}
    if($null -ne $powerpoint){
        if($null -ne $originalSecurity){$powerpoint.AutomationSecurity=$originalSecurity}
        if($null -ne $originalAlerts){$powerpoint.DisplayAlerts=$originalAlerts}
        if($powerpoint.Presentations.Count -eq 0){$powerpoint.Quit()}
        [void][Runtime.InteropServices.Marshal]::ReleaseComObject($powerpoint)
    }
}
