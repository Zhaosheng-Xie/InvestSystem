[CmdletBinding()]
param(
    [string]$PythonPath = "E:\Conda\envs\Data_Analysis\python.exe",
    [switch]$Upgrade
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
$env:PIP_DISABLE_PIP_VERSION_CHECK = "1"
$env:PIP_NO_INPUT = "1"

$repositoryRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")).Path

if (-not (Test-Path -LiteralPath $PythonPath -PathType Leaf)) {
    throw "Python interpreter not found: $PythonPath"
}

$temporaryRoot = [System.IO.Path]::GetTempPath()
$temporaryEnvironment = Join-Path (
    $temporaryRoot
) ("invest-system-locks-" + [guid]::NewGuid().ToString("N"))

try {
    & $PythonPath -m venv $temporaryEnvironment
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to create the temporary lock environment."
    }

    $temporaryPython = Join-Path $temporaryEnvironment "Scripts\python.exe"
    # pip and pip-tools are lock compiler tooling, not project dependencies.
    # Keep both exact in this disposable environment so lock output cannot
    # drift with the shared interpreter's independently managed pip version.
    & $temporaryPython -m pip install --quiet "pip==25.3" "pip-tools==7.6.0"
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to install temporary lock tooling."
    }

    $compileArguments = @(
        "-m",
        "piptools",
        "compile",
        "--quiet",
        "--generate-hashes",
        "--allow-unsafe",
        "--resolver=backtracking",
        "--strip-extras",
        "--no-emit-index-url",
        "--no-emit-trusted-host",
        "--newline=lf"
    )

    if ($Upgrade) {
        $compileArguments += "--upgrade"
    }

    Push-Location $repositoryRoot
    try {
        & $temporaryPython @compileArguments `
            "--output-file=requirements.lock" `
            "pyproject.toml" `
            "requirements-build.in"
        if ($LASTEXITCODE -ne 0) {
            throw "Failed to compile requirements.lock."
        }

        & $temporaryPython @compileArguments `
            "--extra=dev" `
            "--constraint=requirements.lock" `
            "--output-file=requirements-dev.lock" `
            "pyproject.toml" `
            "requirements-build.in"
        if ($LASTEXITCODE -ne 0) {
            throw "Failed to compile requirements-dev.lock."
        }
    }
    finally {
        Pop-Location
    }
}
finally {
    if (Test-Path -LiteralPath $temporaryEnvironment) {
        $resolvedTemporaryRoot = [System.IO.Path]::GetFullPath($temporaryRoot)
        $resolvedTemporaryEnvironment = [System.IO.Path]::GetFullPath($temporaryEnvironment)
        $temporaryName = [System.IO.Path]::GetFileName($resolvedTemporaryEnvironment)

        if (
            -not $resolvedTemporaryEnvironment.StartsWith(
                $resolvedTemporaryRoot,
                [System.StringComparison]::OrdinalIgnoreCase
            ) -or
            -not $temporaryName.StartsWith(
                "invest-system-locks-",
                [System.StringComparison]::OrdinalIgnoreCase
            )
        ) {
            throw "Refusing to remove unexpected temporary path: $resolvedTemporaryEnvironment"
        }

        Remove-Item -LiteralPath $resolvedTemporaryEnvironment -Recurse -Force
    }
}
