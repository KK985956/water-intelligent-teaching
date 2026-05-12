import json
import subprocess
import tempfile
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


def html_to_pdf(html_path, output_path):
    browser = find_browser()
    if browser is None:
        raise RuntimeError("未找到 Edge 或 Chrome，无法执行 HTML 转 PDF。")

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
            raise RuntimeError((result.stderr or result.stdout or "浏览器未输出 PDF").strip())
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
try {
    $ppt = New-Object -ComObject PowerPoint.Application
    $ppt.Visible = -1
    $presentation = $ppt.Presentations.Add()
    while ($presentation.Slides.Count -gt 0) {
        $presentation.Slides.Item(1).Delete()
    }
    foreach ($slideData in $slides) {
        $slide = $presentation.Slides.Add($presentation.Slides.Count + 1, 2)
        $titleText = [string]$slideData.title
        $slide.Shapes.Title.TextFrame.TextRange.Text = $titleText
        $bodyText = ''
        foreach ($line in $slideData.bullets) {
            if ([string]::IsNullOrWhiteSpace([string]$line)) { continue }
            if ($bodyText.Length -gt 0) { $bodyText += [Environment]::NewLine }
            $bodyText += [string]$line
        }
        if ($slide.Shapes.Placeholders.Count -ge 2) {
            $slide.Shapes.Placeholders.Item(2).TextFrame.TextRange.Text = $bodyText
        } else {
            $textbox = $slide.Shapes.AddTextbox(1, 60, 140, 620, 280)
            $textbox.TextFrame.TextRange.Text = $bodyText
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
            failure_message="PowerPoint 未成功生成课件",
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
            failure_message="Word 模板填充失败",
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
            failure_message="PowerPoint 模板填充失败",
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
        failure_message="Word 未成功导出 PDF",
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
        failure_message="PowerPoint 未成功导出 PDF",
        expected_output=output_path,
    )
