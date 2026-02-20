# Usage: .\release.ps1 1.0.0
param(
    [Parameter(Mandatory)]
    [string]$Version
)

$tag = "v$Version"

Set-Content -Path VERSION -Value $Version

git add -A
git commit -m "Release $tag"
git tag $tag
git push origin master
git push origin $tag

Write-Host "Released $tag — check Actions: https://github.com/$(git remote get-url origin | Select-String '(?<=github\.com[/:])[^/]+/[^/]+(?=\.git|$)' | ForEach-Object { $_.Matches.Value })/actions"
