$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
. (Join-Path $PSScriptRoot 'startup_preflight.ps1')
$null = docker info --format '{{.ServerVersion}}' 2>$null
if ($LASTEXITCODE -ne 0) { throw '无法连接 Docker Desktop，请先启动 Docker 引擎。' }
$hasEnv = Test-Path -LiteralPath '.env'
$volumeNames = @(docker volume ls --quiet --filter 'name=^local-app_phone_mysql$')
if ($LASTEXITCODE -ne 0) { throw '无法读取 Docker 数据卷，请检查 Docker 引擎。' }
$hasVolume = $volumeNames -contains 'local-app_phone_mysql'
$startupMode = Get-StartupMode $hasEnv $hasVolume
if (-not (Test-Path -LiteralPath '.env')) {
    $bytes = [byte[]]::new(24)
    $rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    try {
        $rng.GetBytes($bytes)
        $password = ([BitConverter]::ToString($bytes)).Replace('-', '').ToLowerInvariant()
        $rng.GetBytes($bytes)
        $rootPassword = ([BitConverter]::ToString($bytes)).Replace('-', '').ToLowerInvariant()
    } finally { $rng.Dispose() }
    @("MYSQL_PASSWORD=$password", "MYSQL_ROOT_PASSWORD=$rootPassword") | Set-Content -LiteralPath '.env' -Encoding ASCII
}
if (-not (Select-String -LiteralPath '.env' -Pattern '^ADMIN_TOKEN=.+$' -Quiet)) {
    $bytes = [byte[]]::new(32)
    $rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    try { $rng.GetBytes($bytes) } finally { $rng.Dispose() }
    $adminToken = ([BitConverter]::ToString($bytes)).Replace('-', '').ToLowerInvariant()
    Add-Content -LiteralPath '.env' -Value "ADMIN_TOKEN=$adminToken" -Encoding ASCII
}
if ($startupMode -eq 'new') {
    $null = docker volume create local-app_phone_mysql
    if ($LASTEXITCODE -ne 0) { throw '创建新数据库卷失败；已生成 .env，请保留并检查 Docker。' }
}
docker compose up -d --build
if ($LASTEXITCODE -ne 0) { throw '启动失败，请确认 Docker Desktop 已启动并查看上面的错误。' }
Write-Host '启动完成，请访问 http://localhost:61434'
Write-Host '本机管理页面：http://localhost:61435 ，管理口令保存在 local-app\.env 的 ADMIN_TOKEN 中。'
