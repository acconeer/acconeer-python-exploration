# Copyright (c) Acconeer AB, 2022
# All rights reserved

from . import platforms as _  # noqa: F401
from .base import PlatformInstall, SetupStep, prompts, utils
from .cli import SetupArgumentParser


def main() -> None:
    args = SetupArgumentParser().parse_args()

    selected_platform = args.platform or prompts.get_selection_from_user(
        "Platforms:", PlatformInstall.platforms()
    )

    mby_setupper = PlatformInstall.from_key(str(selected_platform))
    if selected_platform is None or mby_setupper is None:
        exit()

    setupper: SetupStep = utils.WithDescription(
        f"==== Setting up {selected_platform!r} will do the following:\n",
        mby_setupper,
    )

    if setupper is None:
        print(f"Platform {selected_platform!r} is not supported.")
        exit(1)

    if not args.silent:
        setupper.report()

        if not prompts.yn_prompt("Proceed?"):
            return

    success = setupper.run()
    if success:
        print("All done!")
    else:
        print("Something went wrong.")


if __name__ == "__main__":
    try:
        main()
    except RuntimeError as re:
        print(*re.args)
    except KeyboardInterrupt:
        pass
