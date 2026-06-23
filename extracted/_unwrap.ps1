# Unwrap Drive MCP tool-result JSON files into named markdown files
# Auto-identifies each sheet from its content patterns.

$srcDir = "C:\Users\vilas\.claude\projects\c--Users-vilas-Downloads-AI-Hedge-Fund\8ab97dc2-a24b-4600-b298-a5ed5b6a09ac\tool-results"
$dstDir = "c:\Users\vilas\Downloads\AI_Hedge_Fund\extracted"

function Identify-Sheet {
    param([string]$content)
    $head = $content.Substring(0, [Math]::Min(2000, $content.Length))

    # Order matters - more specific first
    if ($head -match "1\\\\\.\s*India_Top100" -and $head -match "Aggregate" -or
        ($content -match "EMA Signal/50D_EMA" -and $content -match "Drawdown Signal/Drawdown_10%" -and $content -match "Zone Signal/50D_Low")) {
        return "Aggregate_Signal"
    }
    if ($head -match "Crossover" -or $content -match "Crossover.*50.*200|Golden Cross|Death Cross") { return "EMA_Crossover_Analyser" }
    if ($content -match "Drawdown_10%.*Drawdown_15%.*Drawdown_20%" -and $content -match "Analyser.*Relative|Relative.*Drawdown") { return "Drawdown_Analyser_Relative" }
    if ($content -match "Drawdown_10%.*Drawdown_15%.*Drawdown_20%" -and $content -match "200.*Day|200_Days") { return "Drawdown_Analyser_200_Days" }
    if ($head -match "Drawdown_10%" -and $head -match "Drawdown_15%" -and $head -match "Drawdown_20%" -and $content.Length -lt 200000) {
        # Distinguish Signal vs base Analyser
        if ($content -match "Annual.*Return|CAGR|Hit Rate|Win Rate|Sharpe") { return "Drawdown_Analyser" }
        return "Drawdown_Signal"
    }
    if ($head -match "50D_Low" -and $head -match "100D_Low" -and $head -match "200D_Low") {
        if ($content -match "Annual|CAGR|Hit Rate|Win Rate|Sharpe") { return "Zone_Signal_Analyser" }
        return "Zone_Signal"
    }
    if ($head -match "Correlation" -or $content -match "Correlation.*Coefficient|Pearson|correl") { return "Stock_Correlation_Analyser" }
    if ($head -match "50D_EMA" -and $head -match "100D_EMA" -and $head -match "200D_EMA") {
        if ($content -match "Annual|CAGR|Hit Rate|Win Rate|Sharpe|backtest") { return "EMA_Signal_Analyser" }
        return "EMA_Signal"
    }
    if ($head -match "Buy.?Signal.?v3|v3" -and $content -match "Buy") { return "Buy_Signal_v3" }
    if ($head -match "Buy.?Signal.?v2|v2" -and $content -match "Buy") { return "Buy_Signal_v2" }
    if ($head -match "Buy.?Signal.?v1|v1" -and $content -match "Buy") { return "Buy_Signal_v1" }
    if ($content -match "Buy_Signal_Analyser|50DMA Analyser") { return "Buy_Signal_Analyser_unknown" }
    return "UNIDENTIFIED"
}

$files = Get-ChildItem $srcDir -Filter "*.txt" | Sort-Object LastWriteTime
$results = @()

foreach ($f in $files) {
    try {
        $json = Get-Content $f.FullName -Raw | ConvertFrom-Json
        $content = $json.fileContent
        if (-not $content) { continue }

        $name = Identify-Sheet $content
        $size = $content.Length

        # If name conflicts, append timestamp suffix
        $outPath = Join-Path $dstDir "$name.md"
        if (Test-Path $outPath) {
            $stamp = $f.BaseName.Substring($f.BaseName.Length - 6)
            $outPath = Join-Path $dstDir "$name`_$stamp.md"
        }

        $content | Out-File -FilePath $outPath -Encoding utf8
        $results += [PSCustomObject]@{
            Source = $f.Name.Substring($f.Name.Length - 17)
            Identified = $name
            Chars = $size
            Lines = ($content -split "`n").Count
            Output = (Split-Path $outPath -Leaf)
        }
    } catch {
        Write-Warning "Failed on $($f.Name): $_"
    }
}

$results | Format-Table -AutoSize | Out-String -Width 200
