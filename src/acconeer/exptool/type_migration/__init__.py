# Copyright (c) Acconeer AB, 2024-2025
# All rights reserved

"""
type_migration

This is a module that enables structural handling of value object migration.

Since a lot of our configs/context are subject to updates and recordings
are saved (and not modified), it's very troublesome to do a best effort to
keep backwards compatability.

This module aims to support us in keeping backwards compatibility in all cases
where it's possible.

This module works on the following premises:

1. Necessary parts of old config classes are kept around
2. Each "identity" that is e.g. a Config has an accompanying timeline that
   glues the historical record of e.g. a Config's definitions through time.

For example;

Say we have a simple Config

>>> import attrs
>>> import json
>>> import typing_extensions as te
>>>
>>> def typical_from_json(clz, json_str):
...     return clz(**json.loads(json_str))
...
>>> @attrs.mutable
... class Config_v0:
...     param: float
...     param_enabled: bool
...
...     # below is just to save some vertical space, it's equivalent to @classmethod def from_json ...
...     from_json = classmethod(typical_from_json)
...
>>> Config_v0.from_json('{"param": 0.5, "param_enabled": true}')
Config_v0(param=0.5, param_enabled=True)

But then we realize that our 'param' could be used in 3 different ways, so
we want to replace 'param_enabled' with an Enum, giving us the new version

>>> Mode = te.Literal["A", "B", "C"]  # poor man's Enum
...
>>> @attrs.mutable
... class Config_v1:
...     param: float
...     mode: Mode
...
...     from_json = classmethod(typical_from_json)
...

In order to keep backward compatability, we need to make sure that we can handle
both 'Config_v1' AND 'Config_v0', while our algorithm logic works with 'Config_v1'.

This is where this module comes in. We can use it to define a timeline of the 'Config'
"identity" like so:

>>> from acconeer.exptool import type_migration as tm
>>>
>>> def v0_to_v1(config: Config_v0):
...     # some arbitrary logic
...     mode = (
...         "A" if config.param < 0 else
...         "B" if config.param_enabled else
...         "C"
...     )
...     return Config_v1(param=config.param, mode=mode)
>>>
>>> config_timeline = (
...     tm
...     # declare first epoch of timeline
...     .start(Config_v0)
...
...     # declare how a str could be transformed to the epoch above
...     # and what is expected to fail (if given "wrong" input).
...     #   note that a single epoch can have multiple 'load's.
...     .load(str, Config_v0.from_json, fail=[TypeError])
...
...     # does nothing, but serves as a separator.
...     .nop()
...
...     # defines a new epoch by giving a new type, how to go from
...     # the epoch above to this, new, epoch (and what is expected to fail).
...     .epoch(Config_v1, v0_to_v1, fail=[])
...
...     # same as above
...     .load(str, Config_v1.from_json, fail=[TypeError])
... )

This timeline can now be used to migrate the following values to a 'Config_v1' object:
- A 'Config_v1' object,
- A 'Config_v1' json string,
- A 'Config_v0' object,
- A 'Config_v0' json string.

>>> config_timeline.migrate(Config_v1(param=0.5, mode='A'))
Config_v1(param=0.5, mode='A')

>>> config_timeline.migrate('{"param": 0.5, "mode": "B"}')
Config_v1(param=0.5, mode='B')

>>> config_timeline.migrate(Config_v0(param=0.5, param_enabled=False))
Config_v1(param=0.5, mode='C')

>>> config_timeline.migrate('{"param": 0.5, "param_enabled": true}')
Config_v1(param=0.5, mode='B')

The module also supports requiring context when defining the timeline
(with 'contextual_load' & 'contextual_epoch') and injecting context
to 'migrate' via a Completer (i.e. a function with a specific signature).
"""

from .core import Completer, MigrationError, MigrationErrorGroup, Node, start
