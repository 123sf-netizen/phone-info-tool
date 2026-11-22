function Get-StartupMode([bool]$HasEnv, [bool]$HasVolume) {
    if ($HasEnv -and $HasVolume) { return 'existing' }
    if (-not $HasEnv -and -not $HasVolume) { return 'new' }
    if ($HasVolume) { throw '检测到已有数据库卷但 .env 不存在。请找回原 .env；不能生成新口令替代旧口令。' }
    throw '检测到 .env 但数据库卷不存在。请先检查 Docker 环境或按备份恢复，启动程序不会创建空数据库。'
}
