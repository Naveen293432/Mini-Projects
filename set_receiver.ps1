<#
Usage:
  - Interactive:   .\set_receiver.ps1
  - One-shot:      .\set_receiver.ps1 -Address "PASTE_ADDRESS_HERE"

This writes `ALGORAND_RECEIVER_ADDRESS` into .env.bat in the project root.
Do NOT commit .env.bat to version control if it contains secrets.
#>
[CmdletBinding()]
param(
    [string]$Address
)
if (-not $Address) {
    $Address = Read-Host -Prompt 'Enter ALGORAND_RECEIVER_ADDRESS (58-char Algorand address)'
}
if (-not $Address) {
    Write-Host 'No address provided. Aborting.' -ForegroundColor Yellow
    exit 1
}
$envFile = Join-Path $PSScriptRoot '.env.bat'
$content = "@echo off`r`nREM Project-local environment overrides.`r`nREM DO NOT COMMIT THIS FILE IF IT CONTAINS PRIVATE KEYS OR ADDRESSES.`r`nSET ALGORAND_RECEIVER_ADDRESS=$Address`r`n"
Set-Content -Path $envFile -Value $content -Encoding UTF8
Write-Host "Wrote $envFile" -ForegroundColor Green
