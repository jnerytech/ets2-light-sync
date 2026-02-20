# Run .\release.ps1 to auto-bump patch version, commit, tag, and push.
# Or run .\release.ps1 -Version 1.2.3 to use a specific version.

param(
    [string]$Version
)

if ($Version) {
    Set-Content -Path VERSION -Value $Version -NoNewline
} else {
    $current = (Get-Content -Path VERSION -Raw).Trim()
    $parts = $current -split '\.'
    $parts[2] = [int]$parts[2] + 1
    $Version = $parts -join '.'
    Set-Content -Path VERSION -Value $Version -NoNewline
}

$tag = "v$Version"

# Error if the tag already exists
$existing = git tag --list $tag
if ($existing) {
    Write-Error "Tag $tag already exists."
    exit 1
}

git add -A
$changes = git status --porcelain
if ($changes) {
    git commit -m "Release $tag"
}
git tag $tag
git push origin master
git push origin $tag

$remote = git remote get-url origin
$match = [regex]::Match($remote, '(?<=github\.com[/:])[^/]+/[^.]+')
if ($match.Success) {
    Write-Host "Released $tag -> https://github.com/$($match.Value)/actions"
} else {
    Write-Host "Released $tag"
}
