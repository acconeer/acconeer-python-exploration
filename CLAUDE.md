# CLAUDE.md

Everything below is a claim about the repo as it stands, and a stale claim is
worse than none — it gets trusted and acted on. Fix an invalidated claim in the
**same commit** as the change, and verify new ones by running them. Most likely
to rot: the Hatch scripts, the `internal_tools/` checkers, the `Jenkinsfile`
stages, the test layout, the per-algorithm file split.

## Commands

Everything goes through [Hatch](https://hatch.pypa.io/) envs in
`pyproject.toml`; `noxfile.py` only prints the Hatch equivalent. Without
`hatch` on PATH, run it through `uvx` with the same `--exclude-newer` date and
`--from` hatch constraint as `docker/Dockerfile` — the date pin is required, or
a newer `virtualenv` breaks every env build.

| Command | Purpose |
|---|---|
| `hatch fmt --check` | The lint gate — what CI and the pre-push hook run. Much more than ruff; see below. |
| `hatch fmt` | Auto-fix: copyright years, example-script doc pages, `ruff check --fix`, `ruff format`. |
| `hatch run mypy:check` | Type check — pinned mypy on the oldest supported Python; see the `mypy` env in `pyproject.toml`. |
| `hatch test` | Tests across the Python matrix in `pyproject.toml`. Extra args pass to pytest; `-py=<version>` picks one interpreter. |
| `hatch test --update-outputs tests/processing/test_processing.py -k distance` | Regenerate one algorithm's regression baselines. |
| `hatch run docs:html` | Build docs. `docs:autobuild` live-reloads; `docs:build` is the CI gate. |
| `hatch run app:new` | Launch the GUI. |

Test-running traps:

- `tests/integration/` and `tests/model/` only run when given CLI paths to RSS
  artifacts (`--a121-exploration-server-paths` and friends, see
  `pytest_addoption` in `tests/conftest.py`). Without them every test **skips**,
  so a green run exercised nothing — only CI, which fetches the binaries, runs
  them for real.
- `tests/processing/`'s only test module is `test_processing.py`, which
  parametrizes over factory functions in `tests/processing/a121/<algo>_test.py`.
  Despite the names those are helpers with no test functions — pointing pytest
  at one collects nothing.
- Default `addopts` ignores `a111` and `tests/gui`, and the test env adds
  `--doctest-modules`, making the examples in `type_migration`'s module
  docstring executable tests — pass `src/` explicitly (as CI does) to collect
  them.
- `tests/flash/test_devsite.py` needs `--test-devsite` and credentials.
- `internal_tools/install-git-hooks.sh` installs the pre-push
  `hatch fmt --check`.

## The lint gate is more than ruff

`hatch fmt --check` also runs bespoke checkers from `internal_tools/`, covering
repo obligations nothing in a diff would hint at:

- **Copyright headers** — `# Copyright (c) Acconeer AB, <years>` /
  `# All rights reserved` in every `.py` file. Two traps: the checker looks only
  at files touched by **HEAD's commit**, not the working tree, so `hatch fmt`
  won't add a header to an uncommitted new file — use
  `python internal_tools/check_copyright.py --update-year --all-files`. And the
  year it wants is HEAD's *commit* year, so old commits stay green.
- **Changelog roles** — user-visible changes go in `UNRELEASED_CHANGELOG.md`;
  `CHANGELOG.md` is rewritten only at release. The checker only guards that the
  two keep their roles; nothing fails for a missing entry.
- **Prose line length** in `CHANGELOG.md`, `UNRELEASED_CHANGELOG.md`,
  `LICENSE.md` — the cap is `[tool.check_line_length]` in `pyproject.toml`.
  Other Markdown is unchecked.
- **SDK version consistency** across `README.md`, `docs/**/*.rst`,
  `Jenkinsfile`, and the app's resource tab.
- **Generated doc pages** — adding or renaming an example script requires
  `python docs/generate_example_script_pages.py fix`.

The `:glob:` ban in Sphinx toctrees is *not* in this gate — it's
`hatch run docs:lint`, and stubbed out on Windows.

## Architecture

**A121 is the active generation and where new work belongs.** A111 is legacy —
excluded from mypy, ignored by the default pytest run, exempted from several
ruff rule groups. Same split for `app/new` vs `app/old`. Don't extend the
legacy side unless asked.

`_core/` is generation-agnostic plumbing (links, message stream, the generic
`Client` base, h5 recording); `a121/_core/` builds entities, the exploration
protocol and recording on top of it. Import from the public
`acconeer.exptool.a121`, not the underscore submodules.

**Every `a121/algo/<name>/` follows the same file split** — knowing it once
saves reading any of them: `_processors.py` (per-frame Sparse IQ processing),
`_detector.py` (owns a `Client`, drives the session), `_configs.py` plus
`_context.py`/`_thresholds.py` where calibration is involved,
`_detector_plugin.py` (GUI wiring), `_views.py` + `_pidget_mapping.py` (config
editor widgets). Bases in `algo/_base.py`; copy `distance/` or `presence/`.

**The app runs in two processes.** `MpBackend` (`app/new/backend/_backend.py`)
runs the `Model` in a `multiprocessing.Process`, exchanging `Task`/`Message`
over queues, while `AppModel` lives in the Qt process. Anything crossing must
be picklable, and backend errors surface as a `ClosedTask`, not a traceback. A
plugin is a backend + view + plot triplet from a `PluginSpec`.

**Recordings are a compatibility surface.** `opser/` does h5
(de)serialization; `type_migration/` keeps configs in *old* recordings loadable
as classes evolve — changing a persisted config is a migration, not an edit;
read its module docstring first. `_ReplayingClient` replays a record through
the `Client` interface, so examples and `tests/processing/` need no hardware.

Tests: `unit/`, `processing/` (algorithm regression; baselines in
`a121/data_files/expected_output/`), `app/` (Qt), `integration/` (real RSS
server), `model/` (power/memory vs RSS limits), `package/`, `environment/`.

## Reuse before you add

The algorithm directories solve overlapping problems, so almost anything you
are about to write probably exists already — search first. Signal-processing
and sensor-config helpers belong in `a121/algo/_utils.py` (peak finding and
interpolation, distance and velocity axes, filter coefficients, PRF and profile
selection, temperature compensation, frame-rate estimation); the
extended-structure (group → sensor → entry) manipulation that configs and
results are full of belongs in `a121/_core/utils.py`. Subclass the bases in
`algo/_base.py`, and assemble config editors from the existing pidget factories
in `app/new/ui/components/pidgets/` plus `AttrsConfigEditor` — a hand-rolled
widget for a config field is nearly always the wrong answer. When something
genuinely is missing, extend the shared module rather than adding a private
copy next to the one caller.

## Conventions

Ruff names its own rules on violation. What it won't tell you: `Self`,
`ParamSpec`, `Protocol` and friends are imported from `typing_extensions`
(as `import typing_extensions as te`) throughout, even though the
`requires-python` floor now covers native equivalents for all of them —
that's existing house style, not a version constraint, and untangling it is
separate follow-up work. `attrs` value objects carrying `numpy.typing`
annotations are the house style too.

## Pointers

- `.claude/skills/code-review-local/` — repo review skill with
  signal-processing dimensions.
- `Jenkinsfile` — three build scopes (sanity / hourly / nightly) differing in
  Python and RSS versions.
- Published docs: <https://docs.acconeer.com>, built from `docs/`.
