# Copyright (c) Acconeer AB, 2022-2023
# All rights reserved

from .launcher import run_launcher


if __name__ == "__main__":
    selected_generation = run_launcher()

    if selected_generation == "new":
        from .new import main

        main()
    elif selected_generation == "old":
        from .old import main

        main()
