param(
  [Parameter(ValueFromRemainingArguments = $true)]
  [string[]]$Args
)

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
python "$scriptDir/live_byoc_lite.py" @Args
exit $LASTEXITCODE
