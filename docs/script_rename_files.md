```bash
$f = Get-ChildItem -File | Where-Object { $_.Extension -match '^\.(jpg|jpeg|png|gif|webp)$' } | Sort-Object Name; (($f | ForEach-Object { "'" + ($_.Name -replace "'", "\'") + "'" }) -join ', ') | Set-Clipboard
```