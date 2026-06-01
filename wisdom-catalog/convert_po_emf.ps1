<#
convert_po_emf.ps1 — Rasterize the EMF/WMF/PNG product photos extracted from a
Wisdom PO Excel into normalized PNGs, using Windows GDI+ (System.Drawing).

EMF is a Windows vector metafile; there is no cross-platform converter on this
box (no ImageMagick / Inkscape / LibreOffice), but .NET's System.Drawing can
render a Metafile to a Bitmap natively. Each <code>.emf|.png in the input dir is
rendered onto a white background and upscaled so the long side is >= 800px
(HighQualityBicubic), then saved as <code>.png in the output dir.

Usage:
  powershell -File wisdom-catalog/convert_po_emf.ps1
  powershell -File wisdom-catalog/convert_po_emf.ps1 -Src <rawdir> -Dst <pngdir> -LongSide 800
#>
param(
  [string]$Src = "wisdom-catalog/exports/po_images_raw",
  [string]$Dst = "wisdom-catalog/exports/po_images_png",
  [int]$LongSide = 800
)

Add-Type -AssemblyName System.Drawing
$Src = (Resolve-Path $Src).Path
New-Item -ItemType Directory -Force -Path $Dst | Out-Null
$Dst = (Resolve-Path $Dst).Path

$manifest = Get-Content (Join-Path $Src "manifest.json") -Raw | ConvertFrom-Json
$ok = 0; $fail = 0
foreach ($m in $manifest) {
  if (-not $m.code) { continue }
  $in = Join-Path $Src $m.file
  try {
    $img = [System.Drawing.Image]::FromFile($in)
    $w = $img.Width; $h = $img.Height
    $long = [Math]::Max($w, $h)
    $scale = if ($long -lt $LongSide) { [double]$LongSide / $long } else { 1.0 }
    $nw = [int][Math]::Round($w * $scale); $nh = [int][Math]::Round($h * $scale)
    $bmp = New-Object System.Drawing.Bitmap($nw, $nh)
    $bmp.SetResolution(96, 96)
    $g = [System.Drawing.Graphics]::FromImage($bmp)
    $g.InterpolationMode = [System.Drawing.Drawing2D.InterpolationMode]::HighQualityBicubic
    $g.Clear([System.Drawing.Color]::White)
    $g.DrawImage($img, 0, 0, $nw, $nh)
    $bmp.Save((Join-Path $Dst "$($m.code).png"), [System.Drawing.Imaging.ImageFormat]::Png)
    $g.Dispose(); $bmp.Dispose(); $img.Dispose()
    $ok++
  } catch {
    Write-Host "FAIL $($m.code): $($_.Exception.Message)"
    $fail++
  }
}
Write-Host "Converted OK=$ok FAIL=$fail -> $Dst"
