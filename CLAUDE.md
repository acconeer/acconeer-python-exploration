# CLAUDE.md

Everything below is a claim about the repo; a stale one is worse than none,
since it gets trusted. Fix an invalidated claim in the **same commit** as the
change, and verify new ones by running them. Most likely to rot: the Hatch
scripts, the `internal_tools/` checkers, the `Jenkinsfile` stages, the test
layout, the per-algorithm file split.

## Commands

Everything runs through [Hatch](https://hatch.pypa.io/) envs in
`pyproject.toml`; `noxfile.py` only prints the Hatch equivalent. Without
`hatch` on PATH, run `uvx --exclude-newer <date> hatch@<pin>` with the date and
pin from `docker/Dockerfile`. Pass the date as the flag, not as
`UV_EXCLUDE_NEWER`, which hatch's envs inherit.

| Command | Purpose |
|---|---|
| `hatch check code`, `hatch check fmt` | The lint gate, run by CI and the pre-push hook (install: `internal_tools/install-git-hooks.sh`). More than ruff; see below. |
| `hatch check code --fix`, `hatch check fmt --fix` | Auto-fix: copyright years, example-script doc pages, `ruff check --fix`, `ruff format`. |
| `hatch run mypy:check` | Pinned mypy on the oldest supported Python (`mypy` env). |
| `hatch test tests/ src/` | Tests on one interpreter of the matrix in `pyproject.toml`; `-py=<version>` picks it. Without paths, collecting `examples/` fails. Extra args pass to pytest. |
| `hatch test --update-outputs tests/processing/test_processing.py -k "distance_processor or distance_detector"` | Regenerate one algorithm's regression baselines. `-k` also matches input file names. |
| `hatch run docs:html` | Build docs. An html build ends by building `SINGLE_PAGE_GUIDES` of `docs/conf.py` as one printable page each. `docs:autobuild` live-reloads; `docs:build` is the CI gate. |
| `hatch run docs:compress-images <paths>` | Shrink images before committing (`--check` only reports). |
| `hatch run app:new` | Launch the GUI. |

Test-running traps:

- `tests/integration/` and `tests/model/` need CLI paths to RSS artifacts
  (`--a121-exploration-server-paths` and friends, see `tests/cli_options.py`).
  Without them nearly every test **skips**, so a green run proves almost
  nothing; only CI, which fetches the binaries, runs them for real.
- `tests/processing/`'s only A121 test module is `test_processing.py`, which
  parametrizes over factory functions in `tests/processing/a121/<algo>_test.py`.
  Despite the names those hold no tests, so pytest on one collects nothing.
- Default `addopts` ignores `tests/gui` and A111's source, not its tests. The
  test env's `--doctest-modules` makes the examples in `type_migration`'s module
  docstring tests, collected only when `src/` is passed, as CI does.
- `tests/flash/test_devsite.py` needs `--test-devsite` and credentials.
- Tests of plugins that need the algo bundle skip without `--algo-bundle <zip>`.
  A zip whose SHA-256 the release doesn't pin aborts the run unless
  `--dangerously-skip-integrity-check` is also passed.

## The lint gate is more than ruff

`hatch check code` also runs `internal_tools/` checkers:

- **Copyright headers** `# Copyright (c) Acconeer AB, <years>` /
  `# All rights reserved` in every `.py` file. The checker reads only files
  **HEAD's commit** touched (plus `docs/conf.py`), not the working tree, so
  `hatch check code --fix` won't add a header to an uncommitted new file: commit
  it, then fix and amend. It wants HEAD's *commit* year, so old commits stay
  green.
- **Changelog roles**: user-visible changes go in `UNRELEASED_CHANGELOG.md`, and
  `CHANGELOG.md` is rewritten only at release. The checker only guards these
  roles; a missing entry fails nothing.
- **Prose line length** in `CHANGELOG.md`, `UNRELEASED_CHANGELOG.md` and
  `LICENSE.md`, capped by `[tool.check_line_length]` in `pyproject.toml`. Other
  Markdown is unchecked.
- **Import-free `__init__.py`**: files listed in `[tool.check_no_imports]`
  in `pyproject.toml` may hold no imports, so callers import from the
  submodule itself.
- **SDK version consistency** across `README.md`, `docs/**/*.rst`,
  `Jenkinsfile`, and the app's resource tab.
- **Generated doc pages**: adding or renaming an example script requires
  `python docs/generate_example_script_pages.py fix`.

The Sphinx toctree `:glob:` ban and the no-images-in-`docs/_static` rule (images
go in `docs/images/`) are *not* in this gate but in
`hatch run docs:lint`, which is stubbed out on Windows.

## Architecture

**New work belongs in A121.** A111 is legacy: excluded from mypy and from
doctest collection, exempted from several ruff rule groups. `app/old` is legacy
too; use `app/new`. Don't extend the legacy side unless asked.

`_core/` is generation-agnostic plumbing (links, message stream, the generic
`Client` base, h5 recording); `a121/_core/` builds entities, the exploration
protocol and recording on top of it. Import from the public
`acconeer.exptool.a121`, not the underscore submodules.

**`a121/algo/<name>/` comes in two shapes.** The detectors (`distance/`,
`presence/`, `obstacle/`, `speed/`) split into `_processors.py` (per-frame
Sparse IQ processing), `_detector.py` (owns a `Client`, drives the session) and
`_detector_plugin.py` (GUI wiring), plus `_pidget_mapping.py` (config editor
widgets) in `distance/` and `presence/`; only `distance/` splits calibration
into `_context.py` and `_thresholds.py`. The rest are apps: a `*_plugin.py`,
mostly over a `_processor(s).py` of their own. Bases in `algo/_base.py`; copy
`distance/` or `presence/` for a detector. Each app plugin's `PluginSpec` and
`PluginPresetId` live apart, in `algo/_plugin_specs/<name>.py` (in both `a121/`
and `a2/`), importing the plugin module only inside `create_*_plugin` and
`replay_dialog_*`, so the plugin list loads no algorithm (guarded by
`tests/unit/test_plugin_specs_are_light.py`). A plugin shipped in the module
bundle has a `BundledPluginSpec` instead, which forwards to the spec class a
bundle package lists in `PLUGIN_SPECS` of its `plugin_specs` module, under
the same key.

**The app runs in two processes.** `MpBackend` (`app/new/backend/_backend.py`)
runs the `Model` in a `multiprocessing.Process`, exchanging `Task`/`Message`
over queues; `AppModel` lives in the Qt process. Anything crossing must be
picklable, and backend errors surface as a `ClosedTask`, not a traceback. A
plugin is a backend + view + plot triplet from a `PluginSpec`.

**Recordings are a compatibility surface.** `opser/` does h5
(de)serialization; `type_migration/` keeps configs in *old* recordings loadable
as classes evolve, so changing a persisted config is a migration, not an edit;
read its module docstring first. `_ReplayingClient` replays a record through
the `Client` interface, so `tests/processing/` needs no hardware.

Tests: `unit/`, `processing/` (algorithm regression; baselines in
`a121/data_files/expected_output/`), `app/` (Qt), `examples/`, `integration/`
(real RSS server), `model/` (power/memory vs RSS limits), `package/`,
`environment/`, `flash/`.

## Reuse before you add

The algorithms overlap: search before writing. Signal-processing and
sensor-config helpers belong in `a121/algo/_utils.py` (peak finding and
interpolation, distance and velocity axes, filter coefficients, PRF and profile
selection, temperature compensation, frame-rate estimation), and
extended-structure (group → sensor → entry) manipulation in
`a121/_core/utils.py`. Subclass the bases in `algo/_base.py`, and build config
editors from the pidget factories in `app/new/ui/components/pidgets/` plus
`AttrsConfigEditor`; hand-rolled config-field widgets are rarely right. When
something is missing, extend the shared module rather than add a private copy
next to the one caller.

## Changelog entries

`UNRELEASED_CHANGELOG.md` is populated during development and moved to
`CHANGELOG.md` at release. `CHANGELOG.md` is read by Exploration Tool GUI
users, in the docs and in the app's update dialog.

- Only what differs from the last release: a bug introduced and fixed
  between two releases gets no entry.
- Two lines at most, saying what the user notices. Longer only for a step the
  user must take, or for a new sensor, which may list its apps.
- One entry per noticeable outcome; merge related commits.
- Fixes name the symptom the user saw, not its cause.
- API changes only when breaking, saying what to change.
- Install changes only when they change which machines can run ET (Python
  versions, OS requirements), not dependency pins.
- Keep a workaround (e.g. an environment variable) in its entry.

## Conventions

Code you write or change uses native typing (`X | None`, and `Self`,
`ParamSpec`, `Protocol` and friends from `typing`); untouched lines keep `te.`
(`typing_extensions`). `attrs` value objects with `numpy.typing` annotations
are house style.

Fix the cause, not the symptom, even when the diff is larger: put things where
the tool expects them instead of configuring around it, and fix a bug where it
arises instead of guarding callers against it.

## Pointers

- `.claude/skills/code-review-local/`: repo review skill with
  signal-processing dimensions.
- `Jenkinsfile`: three build scopes (sanity / hourly / nightly) differing in
  Python and RSS versions; only nightly runs the developer site tests, and
  only nightly lets the other parallel stages finish when one fails. Tag
  builds run nightly. A Gerrit change build posts a link to its docs
  preview. Only a `vX.Y.Z` tag publishes to PyPI, and only from a commit
  that also carries a `vX.Y.Z-rcN` tag.
- `docker/Dockerfile`: Jenkins builds `ci` via `TARGET_STAGE`. `dev`, the
  default, takes `UID`/`GID` build args for a devcontainer.
- Published docs: <https://docs.acconeer.com>, built from `docs/`.
