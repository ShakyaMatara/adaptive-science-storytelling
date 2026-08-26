<#
.SYNOPSIS
    Build the code archive submitted alongside the thesis.

.DESCRIPTION
    Produces CB011725_ASCALS_code.zip in the repository root, containing the source,
    the configuration templates and the COMPLETE evaluation directory - probes,
    results, figures and run logs. The evaluation output is thesis evidence and is
    not regenerable: the T4 chapters were sampled at temperature 0.7, so re-running
    produces different text and different numbers.

    Deliberately EXCLUDED:
      venv/, node_modules/           regenerable from requirements.txt / package-lock
      __pycache__/, *.pyc            byte-compiled caches
      chroma_store/                  50 MB, rebuildable with build_index
      chroma_store_backup_prefix/    42 MB, local pre-repair snapshot
      textbooks/                     government-published, third-party copyright
      db.sqlite3                     local development data
      frontend/dist/                 build artefact
      .git/                          history
      .env                           credentials - .env.example ships instead

    THE TEXTBOOK PDFs ARE NEVER INCLUDED. They are copyright material published by
    the Sri Lankan Educational Publications Department. build_index expects them at
    backend/textbooks/; see the note in README.md.

.PARAMETER OutFile
    Archive path. Defaults to CB011725_ASCALS_code.zip in the repository root.

.PARAMETER Force
    Overwrite an existing archive instead of stopping.

.EXAMPLE
    pwsh ./scripts/make_submission_zip.ps1
    pwsh ./scripts/make_submission_zip.ps1 -Force
#>
[CmdletBinding()]
param(
    [string]$OutFile,
    [switch]$Force
)

$ErrorActionPreference = 'Stop'

$RepoRoot = Split-Path -Parent $PSScriptRoot
if (-not $OutFile) {
    $OutFile = Join-Path $RepoRoot 'CB011725_ASCALS_code.zip'
}

Write-Host "Repository : $RepoRoot"
Write-Host "Archive    : $OutFile"
Write-Host ''

if (Test-Path $OutFile) {
    if (-not $Force) {
        throw "$OutFile already exists. Re-run with -Force to overwrite."
    }
    Remove-Item $OutFile -Force
    Write-Host 'Removed the existing archive (-Force).'
}

# Directory names excluded wherever they appear in the tree.
$ExcludedDirs = @(
    'venv', 'node_modules', '__pycache__', '.git', '.claude',
    'chroma_store', 'chroma_store_backup_prefix', 'textbooks', 'dist',
    '.vscode', '.idea'
)
# Exact repo-relative paths excluded.
$ExcludedPaths = @(
    'backend/db.sqlite3',
    'backend/.env'
)
# Filename patterns excluded.
$ExcludedPatterns = @('*.pyc', '*.pyo', '*.pyd', '.DS_Store', 'Thumbs.db', '*.zip')

function Test-Excluded {
    param([string]$RelPath)

    $parts = $RelPath -split '/'
    # Every path segment except the final filename is a directory name.
    foreach ($seg in $parts[0..([Math]::Max(0, $parts.Count - 2))]) {
        if ($ExcludedDirs -contains $seg) { return $true }
    }
    if ($ExcludedPaths -contains $RelPath) { return $true }
    $leaf = $parts[-1]
    foreach ($pat in $ExcludedPatterns) {
        if ($leaf -like $pat) { return $true }
    }
    # A bare ".env" anywhere, but never ".env.example".
    if ($leaf -eq '.env') { return $true }
    return $false
}

Write-Host 'Selecting files...'
$staged = Join-Path ([System.IO.Path]::GetTempPath()) ("ascals_submission_" + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $staged -Force | Out-Null

$included = 0
$skipped = 0
try {
    Get-ChildItem -Path $RepoRoot -Recurse -File -Force | ForEach-Object {
        $rel = $_.FullName.Substring($RepoRoot.Length).TrimStart('\', '/') -replace '\\', '/'
        if (Test-Excluded -RelPath $rel) {
            $skipped++
            return
        }
        $dest = Join-Path $staged $rel
        $destDir = Split-Path -Parent $dest
        if (-not (Test-Path $destDir)) {
            New-Item -ItemType Directory -Path $destDir -Force | Out-Null
        }
        Copy-Item -LiteralPath $_.FullName -Destination $dest -Force
        $included++
    }

    Write-Host "  included : $included files"
    Write-Host "  excluded : $skipped files"
    Write-Host ''

    # Fail loudly rather than ship a secret or a copyrighted PDF.
    $leaked = Get-ChildItem -Path $staged -Recurse -File -Force |
        Where-Object { $_.Name -eq '.env' -or $_.Extension -eq '.pdf' }
    if ($leaked) {
        $leaked | ForEach-Object { Write-Host "  LEAK: $($_.FullName)" }
        throw 'Refusing to build: the staging area contains a .env or a PDF.'
    }

    Write-Host 'Compressing...'
    Compress-Archive -Path (Join-Path $staged '*') -DestinationPath $OutFile -CompressionLevel Optimal
}
finally {
    Remove-Item $staged -Recurse -Force -ErrorAction SilentlyContinue
}

$size = (Get-Item $OutFile).Length
Write-Host ''
Write-Host ("Archive built: {0}" -f $OutFile)
Write-Host ("Size         : {0:N2} MB ({1:N0} bytes)" -f ($size / 1MB), $size)
Write-Host ''
Write-Host 'Top-level contents:'

Add-Type -AssemblyName System.IO.Compression.FileSystem
$zip = [System.IO.Compression.ZipFile]::OpenRead($OutFile)
try {
    $zip.Entries |
        Group-Object { ($_.FullName -split '/')[0] } |
        Sort-Object Name |
        ForEach-Object {
            $bytes = ($_.Group | Measure-Object -Property Length -Sum).Sum
            '{0,-28} {1,5} files {2,10:N1} KB' -f $_.Name, $_.Count, ($bytes / 1KB)
        }
    Write-Host ''
    Write-Host ('Total entries: {0}' -f $zip.Entries.Count)
    $envs = $zip.Entries | Where-Object { $_.Name -eq '.env' }
    $pdfs = $zip.Entries | Where-Object { $_.Name -like '*.pdf' }
    Write-Host ('.env files in archive : {0}' -f $envs.Count)
    Write-Host ('PDF files in archive  : {0}' -f $pdfs.Count)
}
finally {
    $zip.Dispose()
}
