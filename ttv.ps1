function Invoke-Ttv {
    $path = python C:\Users\PC\source\person_repos\terminalTreeView\src\terminaltreeview\app.py
    if ($path -and (Test-Path $path)) {
        Set-Location $path
    }
}

Set-Alias ttv Invoke-Ttv -Scope Global
