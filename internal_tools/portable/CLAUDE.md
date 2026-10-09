# CLAUDE.md

Batch scripts in `package_contents/` check a command's result with
`IF %ERRORLEVEL% EQU 0` / `IF %ERRORLEVEL% NEQ 0` against the exact code,
never the legacy `IF ERRORLEVEL N` form. That legacy form tests
"exit code >= N", not equality: `IF ERRORLEVEL 0` is therefore always true,
since no exit code is negative, which silently turns a failure branch into
dead code if written that way.

Never nest such a check inside an already-open `( ... )` block: cmd.exe
expands every `%ERRORLEVEL%` in a block when the block is parsed, before any
of its lines run, so a nested check sees the value from before the block
started rather than the command that just ran. Fall through to a `GOTO`
label instead, as update.bat does for its winget-install check.
