# Copyright (c) Acconeer AB, 2022
# All rights reserved

from .launcher import run_launcher


if __name__ == "__main__":
    selected_generation = run_launcher()

    if selected_generation == "a121":
        from .new import main

        main()
    elif selected_generation == "a111":
        from .old import main

        main()
