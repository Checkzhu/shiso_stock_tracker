$ErrorActionPreference = "Stop"
$python = "C:\Users\14222\AppData\Local\Programs\Python\Python312\python.exe"
& $python -m pip install httpx 2>&1 | Write-Output
