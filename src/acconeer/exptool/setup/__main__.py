from . import platforms as _  # noqa: F401
from .base import PlatformInstall
from .cli import SetupArgumentParser, prompts


def main():
    args = SetupArgumentParser().parse_args()

    selected_platform = args.platform or prompts.get_selection_from_user(
        "Platforms:", PlatformInstall.platforms()
    )
    if selected_platform is None:
        exit()

    setupper = PlatformInstall.from_key(selected_platform)

    if setupper is None:
        print(f"Platform {selected_platform!r} is not supported.")
        exit(1)

    if not args.silent:
        print(f"Setting up {selected_platform!r} will do the following:")
        print()
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
