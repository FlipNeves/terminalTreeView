function Invoke-Ttv {
    $path = python src/terminaltreeview/app.py
    if ($path -and (Test-Path $path)) {
        Set-Location $path
    }
}

Set-Alias ttv Invoke-Ttv -Scope Global
