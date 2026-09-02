$ErrorActionPreference = "Stop"
$ProjectDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location -LiteralPath $ProjectDir

$PythonExe = Join-Path $ProjectDir ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $PythonExe)) {
    $PythonExe = "python"
}

$LanIp = Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue |
    Where-Object {
        $_.IPAddress -like "192.168.*" -or
        $_.IPAddress -like "10.*" -or
        $_.IPAddress -like "172.*"
    } |
    Select-Object -First 1 -ExpandProperty IPAddress

Write-Host ""
Write-Host "小红书封面工具正在启动……" -ForegroundColor Yellow
Write-Host "电脑访问：http://localhost:8501"
if ($LanIp) {
    Write-Host "手机访问：http://${LanIp}:8501" -ForegroundColor Green
    Write-Host "请让手机与电脑连接同一个 Wi-Fi。"
}
Write-Host "请勿关闭此窗口。按 Ctrl+C 可停止程序。"
Write-Host ""

Start-Process "http://localhost:8501"
& $PythonExe -m streamlit run app.py --server.address=0.0.0.0 --server.port=8501
