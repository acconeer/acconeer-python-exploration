# Copyright (c) Acconeer AB, 2022
# All rights reserved

from __future__ import annotations

from typing import Optional, Sequence


def yn_prompt(message: str) -> bool:
    message = message + " [y/n]"
    inp = input(message)

    while not inp.startswith(("y", "n")):
        print("Please enter 'yes' or 'no':")
        inp = str(input(message))

    return inp.lower().startswith("y")


def number_prompt(message: str) -> int:
    inp = input(message)
    while not inp.isnumeric():
        print("Please enter a digit:")
        inp = input(message)
    return int(inp)


def get_selection_from_user(message: str, choices: Sequence[str]) -> Optional[str]:
    print(message)
    for i, choice in enumerate(choices):
        print(f"{i:<10}{choice}")

    index = number_prompt("Make a selection:")

    try:
        return choices[index]
    except IndexError:
        print(f"Invalid choice: {index}. The valid choices are {list(range(len(choices)))}")
        return None
