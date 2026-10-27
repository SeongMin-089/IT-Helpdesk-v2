$ErrorActionPreference = "Stop"

Set-Location $PSScriptRoot

$env:ENV_FILE = ".env.test"

# .env.test에서 DB 이름 읽기
$config = @{}

Get-Content ".env.test" | ForEach-Object {
    if ($_ -match '^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)$') {
        $config[$matches[1]] = $matches[2].Trim().Trim('"', "'")
    }
}

if ($config["ODOO_DB"] -cne "It_Helpdesk_v2_test") {
    throw "안전 차단: 테스트 DB가 아닙니다."
}

if ($config["ODOO_URL"] -notmatch '^http://(localhost|127\.0\.0\.1):8070/?$') {
    throw "안전 차단: 테스트 Odoo 서버(8070)가 아닙니다."
}

Write-Host "테스트 환경 확인: It_Helpdesk_v2_test / Odoo 8070"
Write-Host "주의: 아래 실행은 Mock 기반 unittest이며 실제 Odoo DB 연동 테스트가 아닙니다."

# 테스트에 사용하는 설정을 명시적으로 고정
$env:ODOO_URL = $config["ODOO_URL"]
$env:ODOO_DB = $config["ODOO_DB"]
$env:ODOO_API_KEY = $config["ODOO_API_KEY"]

& ".\.venv\Scripts\python.exe" -m unittest discover -s tests -v

if ($LASTEXITCODE -ne 0) {
    throw "테스트 실패: exit code $LASTEXITCODE"
}
