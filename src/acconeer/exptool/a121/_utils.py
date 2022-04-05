from typing import Optional, Union


def convert_validate_int(
    value: Union[float, int], max_value: Optional[int] = None, min_value: Optional[int] = None
) -> int:
    """Converts an argument to an int.

    :param value: The argument to be converted and boundary checked
    :param max_value: Maximum value allowed
    :param min_value: Minimum value allowed

    :raises: TypeError if value is a string or a float with decimals
    :raises: ValueError if value does not agree with max_value and min_value
    """
    try:
        int_value = int(value)  # may raise ValueError if "value" is a non-int string
        if int_value != value:  # catches e.g. int("3") != "3", int(3.5) != 3.5.
            raise ValueError
    except ValueError:
        raise TypeError(f"{value} cannot be fully represented as an int.")

    if max_value is not None and int_value > max_value:
        raise ValueError(f"Cannot be greater than {max_value}")

    if min_value is not None and int_value < min_value:
        raise ValueError(f"Cannot be less than {min_value}")

    return int_value
