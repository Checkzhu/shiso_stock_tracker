$env:PYTHONUNBUFFERED = "1"
$proc = Start-Process -FilePath "C:\Users\14222\AppData\Local\Programs\Python\Python312\python.exe" `
    -ArgumentList "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8000" `
    -WorkingDirectory "d:\workspace\git\ai\shiso_stock_tracker" `
    -RedirectStandardOutput "d:\workspace\git\ai\shiso_stock_tracker\server.log" `
    -RedirectStandardError "d:\workspace\git\ai\shiso_stock_tracker\server.err.log" `
    -PassThru -WindowStyle Hidden
Write-Output "Started PID: $($proc.Id)"
Start-Sleep -Seconds 3
Get-NetTCPConnection -LocalPort 8000 -ErrorAction SilentlyContinue | Format-Table LocalPort,State,OwningProcess
