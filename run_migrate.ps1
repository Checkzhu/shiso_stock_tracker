$ErrorActionPreference = "Stop"
$pinfo = New-Object System.Diagnostics.ProcessStartInfo
$pinfo.FileName = "C:\Users\14222\AppData\Local\Programs\Python\Python312\python.exe"
$pinfo.Arguments = "d:\workspace\git\ai\shiso_stock_tracker\migrate_db.py"
$pinfo.RedirectStandardOutput = $true
$pinfo.RedirectStandardError = $true
$pinfo.UseShellExecute = $false
$p = New-Object System.Diagnostics.Process
$p.StartInfo = $pinfo
$p.Start() | Out-Null
$stdout = $p.StandardOutput.ReadToEnd()
$stderr = $p.StandardError.ReadToEnd()
$p.WaitForExit()
Write-Output $stdout
if ($stderr) { Write-Output "STDERR: $stderr" }
Write-Output "Exit code: $($p.ExitCode)"
