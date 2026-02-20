# Edit VERSION, then run .\release.ps1 to commit, tag, and push.

$Version = (Get-Content -Path VERSION -Raw).Trim()
$tag = "v$Version"

# Error if the tag already exists
$existing = git tag --list $tag
if ($existing) {
    Write-Error "Tag $tag already exists. Update VERSION and try again."
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
