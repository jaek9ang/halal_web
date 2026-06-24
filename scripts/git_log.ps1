param(
    [int]$Count = 30
)

$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $ProjectRoot

git --no-pager log -n $Count --date=format:'%Y-%m-%d %H:%M' --pretty=format:'%C(auto)%h%Creset | %ad | %s'
Write-Host ''
