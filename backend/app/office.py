import json
import subprocess
import tempfile
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path


BROWSER_CANDIDATES = [
    Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"),
    Path(r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"),
    Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe"),
    Path(r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"),
]


def find_browser():
    for candidate in BROWSER_CANDIDATES:
        if candidate.exists():
            return candidate
    return None


def _run_powershell_script(script, args, timeout, failure_message, expected_output=None):
    with tempfile.NamedTemporaryFile("w", suffix=".ps1", delete=False, encoding="utf-8") as script_file:
        script_file.write(script)
        script_path = Path(script_file.name)

    try:
        command = [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(script_path),
        ]
        command.extend([str(arg) for arg in args])
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        if result.returncode != 0:
            raise RuntimeError((result.stderr or result.stdout or failure_message).strip())
        if expected_output is not None and not Path(expected_output).exists():
            raise RuntimeError(failure_message)
        return Path(expected_output).resolve() if expected_output is not None else None
    finally:
        if script_path.exists():
            script_path.unlink()


def _write_json_file(data):
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as json_file:
        json.dump(data, json_file, ensure_ascii=False, indent=2)
        return Path(json_file.name)


def count_pptx_slides(pptx_path):
    try:
        with zipfile.ZipFile(pptx_path) as archive:
            root = ET.fromstring(archive.read("docProps/app.xml"))
            namespace = {"ep": "http://schemas.openxmlformats.org/officeDocument/2006/extended-properties"}
            slides = root.find("ep:Slides", namespace)
            return int(slides.text) if slides is not None and slides.text else 0
    except Exception:
        return 0


def html_to_pdf(html_path, output_path):
    browser = find_browser()
    if browser is None:
        raise RuntimeError("Edge or Chrome is required to export HTML to PDF")

    html_path = Path(html_path).resolve()
    output_path = Path(output_path).resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if output_path.exists():
        output_path.unlink()

    with tempfile.TemporaryDirectory() as profile_dir:
        command = [
            str(browser),
            "--headless",
            "--disable-gpu",
            "--no-first-run",
            "--no-default-browser-check",
            "--disable-crash-reporter",
            "--disable-breakpad",
            "--allow-file-access-from-files",
            f"--user-data-dir={profile_dir}",
            f"--print-to-pdf={output_path}",
            html_path.as_uri(),
        ]
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
        if result.returncode != 0 or not output_path.exists():
            raise RuntimeError((result.stderr or result.stdout or "Browser did not output PDF").strip())
        return output_path


def slides_to_pptx(slides, output_path):
    output_path = Path(output_path).resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    json_path = _write_json_file(slides)
    script = r"""
param(
    [Parameter(Mandatory = $true)][string]$JsonPath,
    [Parameter(Mandatory = $true)][string]$OutputPath
)
$ErrorActionPreference = 'Stop'
$slides = Get-Content -Raw -Encoding UTF8 -LiteralPath $JsonPath | ConvertFrom-Json
$ppt = $null
$presentation = $null

function Add-TextBox($slide, $text, $left, $top, $width, $height, $fontSize, $bold, $color) {
    if ([string]::IsNullOrWhiteSpace([string]$text)) { return $null }
    $shape = $slide.Shapes.AddTextbox(1, $left, $top, $width, $height)
    $shape.TextFrame.TextRange.Text = [string]$text
    $shape.TextFrame.TextRange.Font.Size = $fontSize
    $shape.TextFrame.TextRange.Font.Name = 'Microsoft YaHei'
    $shape.TextFrame.TextRange.Font.Color.RGB = $color
    if ($bold) { $shape.TextFrame.TextRange.Font.Bold = -1 }
    return $shape
}

function Add-FilledBox($slide, $left, $top, $width, $height, $fillColor, $lineColor) {
    $box = $slide.Shapes.AddShape(1, $left, $top, $width, $height)
    $box.Fill.ForeColor.RGB = $fillColor
    $box.Line.ForeColor.RGB = $lineColor
    return $box
}

function Join-Bullets($bullets) {
    $bodyText = ''
    foreach ($line in $bullets) {
        if ([string]::IsNullOrWhiteSpace([string]$line)) { continue }
        if ($bodyText.Length -gt 0) { $bodyText += [Environment]::NewLine }
        $bodyText += "- " + [string]$line
    }
    return $bodyText
}

function Add-ImagePanel($slide, $slideData, $left, $top, $width, $height) {
    $imagePath = [string]$slideData.image_path
    if (-not [string]::IsNullOrWhiteSpace($imagePath) -and (Test-Path -LiteralPath $imagePath)) {
        $slide.Shapes.AddPicture($imagePath, $false, $true, $left, $top, $width, $height) | Out-Null
        return
    }
    Add-FilledBox $slide $left $top $width $height 15921906 10079487 | Out-Null
    Add-TextBox $slide 'AI image prompt' ($left + 18) ($top + 18) ($width - 36) 28 13 $true 5066061 | Out-Null
    Add-TextBox $slide ([string]$slideData.image_prompt) ($left + 18) ($top + 58) ($width - 36) ($height - 78) 15 $false 2631720 | Out-Null
}

try {
    $ppt = New-Object -ComObject PowerPoint.Application
    $ppt.Visible = -1
    $presentation = $ppt.Presentations.Add()
    while ($presentation.Slides.Count -gt 0) {
        $presentation.Slides.Item(1).Delete()
    }
    foreach ($slideData in $slides) {
        $slide = $presentation.Slides.Add($presentation.Slides.Count + 1, 12)
        $layout = [string]$slideData.layout
        $titleText = [string]$slideData.title
        $subtitle = [string]$slideData.subtitle
        $bodyText = Join-Bullets $slideData.bullets
        $notes = [string]$slideData.speaker_notes

        Add-FilledBox $slide 0 0 720 405 16448250 16448250 | Out-Null

        if ($layout -eq 'cover') {
            Add-FilledBox $slide 0 0 720 405 13785622 13785622 | Out-Null
            Add-TextBox $slide $titleText 58 96 590 90 34 $true 2631720 | Out-Null
            Add-TextBox $slide $subtitle 60 184 560 42 19 $false 5066061 | Out-Null
            Add-TextBox $slide $bodyText 64 250 520 90 17 $false 2631720 | Out-Null
            Add-TextBox $slide ([string]$slideData.image_prompt) 64 350 560 28 12 $false 6710886 | Out-Null
        } elseif ($layout -eq 'image_right') {
            Add-TextBox $slide $titleText 42 34 380 48 26 $true 2631720 | Out-Null
            Add-TextBox $slide $subtitle 44 78 380 30 14 $false 6710886 | Out-Null
            Add-TextBox $slide $bodyText 52 122 315 175 18 $false 2631720 | Out-Null
            Add-ImagePanel $slide $slideData 420 76 244 210
        } elseif ($layout -eq 'process') {
            Add-TextBox $slide $titleText 42 30 600 42 25 $true 2631720 | Out-Null
            $items = @($slideData.bullets)
            $count = [Math]::Max(1, $items.Count)
            $boxWidth = [Math]::Min(148, [Math]::Floor(600 / $count) - 8)
            for ($i = 0; $i -lt $items.Count; $i++) {
                $left = 50 + ($i * ($boxWidth + 14))
                Add-FilledBox $slide $left 145 $boxWidth 118 15134930 10079487 | Out-Null
                Add-TextBox $slide ([string]($i + 1)) ($left + 12) 155 28 30 22 $true 2631720 | Out-Null
                Add-TextBox $slide ([string]$items[$i]) ($left + 16) 194 ($boxWidth - 30) 58 14 $false 2631720 | Out-Null
            }
            Add-TextBox $slide ([string]$slideData.image_prompt) 54 315 600 34 12 $false 6710886 | Out-Null
        } elseif ($layout -eq 'case_card') {
            Add-TextBox $slide $titleText 42 30 600 42 25 $true 2631720 | Out-Null
            Add-FilledBox $slide 54 100 590 210 16777215 10079487 | Out-Null
            Add-TextBox $slide $subtitle 76 118 520 30 15 $true 5066061 | Out-Null
            Add-TextBox $slide $bodyText 78 160 500 120 17 $false 2631720 | Out-Null
            Add-TextBox $slide ([string]$slideData.image_prompt) 76 324 520 30 12 $false 6710886 | Out-Null
        } elseif ($layout -eq 'summary') {
            Add-TextBox $slide $titleText 42 30 600 42 27 $true 2631720 | Out-Null
            $items = @($slideData.bullets)
            for ($i = 0; $i -lt $items.Count; $i++) {
                $top = 96 + ($i * 56)
                Add-FilledBox $slide 62 $top 560 42 15134930 10079487 | Out-Null
                Add-TextBox $slide ([string]$items[$i]) 82 ($top + 10) 520 26 16 $false 2631720 | Out-Null
            }
            Add-TextBox $slide $notes 64 345 560 28 12 $false 6710886 | Out-Null
        } else {
            Add-TextBox $slide $titleText 42 34 600 48 26 $true 2631720 | Out-Null
            Add-TextBox $slide $subtitle 44 78 580 30 14 $false 6710886 | Out-Null
            if ($layout -eq 'two_column') {
                Add-TextBox $slide $bodyText 52 130 280 180 17 $false 2631720 | Out-Null
                Add-FilledBox $slide 380 124 245 170 15134930 10079487 | Out-Null
                Add-TextBox $slide ([string]$slideData.image_prompt) 400 146 205 105 14 $false 2631720 | Out-Null
            } else {
                Add-TextBox $slide $bodyText 58 128 560 190 18 $false 2631720 | Out-Null
                Add-TextBox $slide ([string]$slideData.image_prompt) 60 330 560 28 12 $false 6710886 | Out-Null
            }
        }

        if (-not [string]::IsNullOrWhiteSpace($notes) -and $layout -ne 'summary') {
            Add-TextBox $slide $notes 46 366 620 24 10 $false 6710886 | Out-Null
        }
    }
    $presentation.SaveAs($OutputPath, 24)
}
finally {
    if ($presentation -ne $null) {
        $presentation.Close()
        [void][System.Runtime.InteropServices.Marshal]::ReleaseComObject($presentation)
    }
    if ($ppt -ne $null) {
        $ppt.Quit()
        [void][System.Runtime.InteropServices.Marshal]::ReleaseComObject($ppt)
    }
    [GC]::Collect()
    [GC]::WaitForPendingFinalizers()
}
"""
    try:
        return _run_powershell_script(
            script,
            [json_path, output_path],
            timeout=90,
            failure_message="PowerPoint did not generate courseware",
            expected_output=output_path,
        )
    finally:
        if json_path.exists():
            json_path.unlink()


def fill_word_template(template_path, output_path, replacements):
    template_path = Path(template_path).resolve()
    output_path = Path(output_path).resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    replacement_path = _write_json_file(replacements)
    script = r"""
param(
    [Parameter(Mandatory = $true)][string]$TemplatePath,
    [Parameter(Mandatory = $true)][string]$OutputPath,
    [Parameter(Mandatory = $true)][string]$ReplacementPath
)
$ErrorActionPreference = 'Stop'
$entries = Get-Content -Raw -Encoding UTF8 -LiteralPath $ReplacementPath | ConvertFrom-Json
$word = $null
$document = $null

function Replace-InRange($range, $findText, $replaceText) {
    $find = $range.Find
    $find.ClearFormatting()
    $find.Replacement.ClearFormatting()
    [void]$find.Execute($findText, $false, $false, $false, $false, $false, $true, 1, $false, [string]$replaceText, 2)
}

function Replace-InShape($shape, $findText, $replaceText) {
    if ($shape.TextFrame -ne $null -and $shape.TextFrame.HasText -eq -1) {
        $shape.TextFrame.TextRange.Text = $shape.TextFrame.TextRange.Text.Replace($findText, [string]$replaceText)
    }
}

try {
    $word = New-Object -ComObject Word.Application
    $word.Visible = $false
    $document = $word.Documents.Open($TemplatePath)
    foreach ($entry in $entries.PSObject.Properties) {
        $findText = [string]$entry.Name
        $replaceText = [string]$entry.Value
        foreach ($storyRange in $document.StoryRanges) {
            $currentRange = $storyRange
            while ($currentRange -ne $null) {
                Replace-InRange $currentRange $findText $replaceText
                $currentRange = $currentRange.NextStoryRange
            }
        }
        foreach ($shape in $document.Shapes) {
            Replace-InShape $shape $findText $replaceText
        }
    }
    $document.SaveAs([ref]$OutputPath, [ref]16)
}
finally {
    if ($document -ne $null) {
        $document.Close()
        [void][System.Runtime.InteropServices.Marshal]::ReleaseComObject($document)
    }
    if ($word -ne $null) {
        $word.Quit()
        [void][System.Runtime.InteropServices.Marshal]::ReleaseComObject($word)
    }
    [GC]::Collect()
    [GC]::WaitForPendingFinalizers()
}
"""
    try:
        return _run_powershell_script(
            script,
            [template_path, output_path, replacement_path],
            timeout=180,
            failure_message="Word template fill failed",
            expected_output=output_path,
        )
    finally:
        if replacement_path.exists():
            replacement_path.unlink()


def fill_ppt_template(template_path, output_path, replacements):
    template_path = Path(template_path).resolve()
    output_path = Path(output_path).resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    replacement_path = _write_json_file(replacements)
    script = r"""
param(
    [Parameter(Mandatory = $true)][string]$TemplatePath,
    [Parameter(Mandatory = $true)][string]$OutputPath,
    [Parameter(Mandatory = $true)][string]$ReplacementPath
)
$ErrorActionPreference = 'Stop'
$entries = Get-Content -Raw -Encoding UTF8 -LiteralPath $ReplacementPath | ConvertFrom-Json
$ppt = $null
$presentation = $null

function Apply-Replacements($text) {
    $result = [string]$text
    foreach ($entry in $entries.PSObject.Properties) {
        $result = $result.Replace([string]$entry.Name, [string]$entry.Value)
    }
    return $result
}

function Update-Shape($shape) {
    if ($shape.Type -eq 6) {
        foreach ($groupItem in $shape.GroupItems) {
            Update-Shape $groupItem
        }
        return
    }

    if ($shape.HasTextFrame -eq -1 -and $shape.TextFrame.HasText -eq -1) {
        $shape.TextFrame.TextRange.Text = Apply-Replacements $shape.TextFrame.TextRange.Text
    }
}

try {
    $ppt = New-Object -ComObject PowerPoint.Application
    $ppt.Visible = -1
    $presentation = $ppt.Presentations.Open($TemplatePath, $true, $false, $false)
    foreach ($slide in $presentation.Slides) {
        foreach ($shape in $slide.Shapes) {
            Update-Shape $shape
        }
    }
    $presentation.SaveAs($OutputPath, 24)
}
finally {
    if ($presentation -ne $null) {
        $presentation.Close()
        [void][System.Runtime.InteropServices.Marshal]::ReleaseComObject($presentation)
    }
    if ($ppt -ne $null) {
        $ppt.Quit()
        [void][System.Runtime.InteropServices.Marshal]::ReleaseComObject($ppt)
    }
    [GC]::Collect()
    [GC]::WaitForPendingFinalizers()
}
"""
    try:
        return _run_powershell_script(
            script,
            [template_path, output_path, replacement_path],
            timeout=180,
            failure_message="PowerPoint template fill failed",
            expected_output=output_path,
        )
    finally:
        if replacement_path.exists():
            replacement_path.unlink()


def docx_to_pdf(docx_path, output_path):
    output_path = Path(output_path).resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    script = r"""
param(
    [Parameter(Mandatory = $true)][string]$InputPath,
    [Parameter(Mandatory = $true)][string]$OutputPath
)
$ErrorActionPreference = 'Stop'
$word = $null
$document = $null
try {
    $word = New-Object -ComObject Word.Application
    $word.Visible = $false
    $document = $word.Documents.Open($InputPath)
    $document.SaveAs([ref]$OutputPath, [ref]17)
}
finally {
    if ($document -ne $null) {
        $document.Close()
        [void][System.Runtime.InteropServices.Marshal]::ReleaseComObject($document)
    }
    if ($word -ne $null) {
        $word.Quit()
        [void][System.Runtime.InteropServices.Marshal]::ReleaseComObject($word)
    }
    [GC]::Collect()
    [GC]::WaitForPendingFinalizers()
}
"""
    return _run_powershell_script(
        script,
        [Path(docx_path).resolve(), output_path],
        timeout=180,
        failure_message="Word did not export PDF",
        expected_output=output_path,
    )


def pptx_to_pdf(pptx_path, output_path):
    output_path = Path(output_path).resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    script = r"""
param(
    [Parameter(Mandatory = $true)][string]$InputPath,
    [Parameter(Mandatory = $true)][string]$OutputPath
)
$ErrorActionPreference = 'Stop'
$ppt = $null
$presentation = $null
try {
    $ppt = New-Object -ComObject PowerPoint.Application
    $ppt.Visible = -1
    $presentation = $ppt.Presentations.Open($InputPath, $true, $false, $false)
    $presentation.SaveAs($OutputPath, 32)
}
finally {
    if ($presentation -ne $null) {
        $presentation.Close()
        [void][System.Runtime.InteropServices.Marshal]::ReleaseComObject($presentation)
    }
    if ($ppt -ne $null) {
        $ppt.Quit()
        [void][System.Runtime.InteropServices.Marshal]::ReleaseComObject($ppt)
    }
    [GC]::Collect()
    [GC]::WaitForPendingFinalizers()
}
"""
    return _run_powershell_script(
        script,
        [Path(pptx_path).resolve(), output_path],
        timeout=180,
        failure_message="PowerPoint did not export PDF",
        expected_output=output_path,
    )
