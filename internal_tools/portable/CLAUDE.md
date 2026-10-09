# CLAUDE.md

Builds the portable, no-install Windows distribution: `make.bash` zips
`package_contents/` (the `.bat` launchers plus whatever `uv`/`uvx` fetches at
first run) into `portable_exploration_tool_<sha>.zip`.

## Windows batch scripts

`package_contents/*.bat` run under `cmd.exe`, not a POSIX shell.

A bare `echo` with no argument does not print a blank line there: it
reports the shell's current echo state, so the console shows a literal
"ECHO is off." or "ECHO is on.". Use `echo.` (no space before the dot) for a
blank line instead.

Check a command's result with `IF %ERRORLEVEL% EQU 0` / `IF %ERRORLEVEL% NEQ
0` against the exact code, never the legacy `IF ERRORLEVEL N` form. That
legacy form tests "exit code >= N", not equality: `IF ERRORLEVEL 0` is
therefore always true, since no exit code is negative, which silently turns
a failure branch into dead code if written that way.

Never nest such a check inside an already-open `( ... )` block: cmd.exe
expands every `%ERRORLEVEL%` in a block when the block is parsed, before any
of its lines run, so a nested check sees the value from before the block
started rather than the command that just ran. Fall through to a `GOTO`
label instead, as update.bat does for its winget-install check.
