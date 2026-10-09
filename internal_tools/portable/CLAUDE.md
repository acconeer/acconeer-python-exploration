# CLAUDE.md

Batch scripts in `package_contents/` check a command's result with
`IF %ERRORLEVEL% EQU 0` / `IF %ERRORLEVEL% NEQ 0` against the exact code,
never the legacy `IF ERRORLEVEL N` form. That legacy form tests
"exit code >= N", not equality: `IF ERRORLEVEL 0` is therefore always true,
since no exit code is negative, which silently turns a failure branch into
dead code if written that way.
