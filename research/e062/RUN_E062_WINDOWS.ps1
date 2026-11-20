# Independent, read-only-with-respect-to-Darwin E062 exploration.
# This script only runs the colocated Python files. It does not touch
# a Git repository, Darwin's SQLite database, model weights or network.
$ErrorActionPreference = 'Stop'
Push-Location $PSScriptRoot
try {
    Write-Host 'Darwin E062 — independent tests (not Darwin kernel tests)'
    & py -m unittest discover -s . -p 'test_e062_exploratory_benchmark.py' -v
    if ($LASTEXITCODE -ne 0) { throw 'E062 unit test failure.' }

    Write-Host 'Darwin E062 — exploratory simulation'
    & py .\e062_exploratory_benchmark.py --output .\e062_exploratory_results_windows.json
    if ($LASTEXITCODE -ne 0) { throw 'E062 exploratory simulation failure.' }

    Write-Host 'Exploratory result saved in this directory.'
}
finally {
    Pop-Location
}
