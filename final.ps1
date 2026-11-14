# Supervisor for the final: restarts the desk until the world ends (exit 0). Usage: pwsh ./final.ps1 [cfg/gated.json]
param([string]$Cfg = "cfg/gated.json")
Set-Location $PSScriptRoot
while ($true) {
  node src/run-final.ts --cfg $Cfg
  if ($LASTEXITCODE -eq 0) { Write-Host "final ended"; break }
  if ($LASTEXITCODE -eq 130) { Write-Host "stopped by Ctrl-C"; break }
  Write-Host "desk exited with $LASTEXITCODE; restarting in 2 s"
  Start-Sleep -Seconds 2
}
