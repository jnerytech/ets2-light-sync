# Edit VERSION, then run .\release.ps1 to commit, tag, and push.

$Version = (Get-Content -Path VERSION -Raw).Trim()
$tag = "v$Version"

# Error if the tag already exists locally or on the remote
$existing = git tag --list $tag
if ($existing) {
    Write-Error "Tag $tag already exists. Update VERSION and try again."
    exit 1
}

git add -A
git commit -m "Release $tag"
git tag $tag
git push origin master
git push origin $tag

$remote = git remote get-url origin
if ($remote -match '(?<=github\.com[/:])[^/]+/[^.]+') {
    Write-Host "Released $tag — https://github.com/$($Matches[0])/actions"
} else {
    Write-Host "Released $tag"
}
