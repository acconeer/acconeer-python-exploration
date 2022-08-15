# Copyright (c) Acconeer AB, 2022
# All rights reserved

import argparse
import configparser
import datetime
import fnmatch
import re
import subprocess
import sys
from enum import Enum, auto
from pathlib import Path


class Status(Enum):
    """ """

    OK = auto()
    NOT_SUPPORTED = auto()
    MISSING = auto()
    YEAR_NOT_UP_TO_DATE = auto()


def update_copyright_year(file_content, copyright_line_nbr, current_year, copyright_pattern):
    """
    Update the year in a copyright statement in a source to the current year.
    If the current year is already present, nothing will be done.
    If no year is stated the result is undefined behavior.

    file_content   - The content of the source file as a list where every entry is a line
    copyright_line - The line where the year is stated (first line has index 0)
    """

    if copyright_line_nbr is None:
        copyright_statement = [copyright_pattern[0] + "\n"] + [copyright_pattern[1] + "\n\n"]
        file_content = copyright_statement + file_content
    else:
        copyright_line = file_content[copyright_line_nbr]

        # If the current year is in the file, the job has been done for us
        if str(current_year) in copyright_line:
            return

        # We use regex to find the year in copyright statement
        year_format = re.compile(r".*([1-2][0-9]{3})")
        result = year_format.match(copyright_line)
        start_pos = result.start(1)
        end_pos = result.end(1)

        # Check whether we had a standalone year, e.g., 2017, or a range, e.g, 2017-2018
        # In either case update the year to the current year
        if copyright_line[start_pos - 1] == "-":
            file_content[copyright_line_nbr] = (
                copyright_line[:start_pos]
                + str(current_year)
                + copyright_line[start_pos + 4 : end_pos]
                + "\n"
            )
        else:
            file_content[copyright_line_nbr] = (
                copyright_line[: start_pos + 4]
                + "-"
                + str(current_year)
                + copyright_line[start_pos + 5 : end_pos + 4]
                + "\n"
            )

    return file_content


def match_copyright_pattern(file_content, patterns):
    """
    Match a list of patterns against the file content.
    Returns the line number where the first matching pattern begins. If no match exists,
    None is returned.

    file_content - The content of the source file as a list where every entry is a line
    patterns - A list of patterns (a pattern is a list of strings)
    """
    if not all(isinstance(p, list) for p in patterns):
        patterns = [patterns]

    if any([len(file_content) >= len(p) for p in patterns]):
        for row, line in enumerate(file_content):
            for pattern in patterns:
                if pattern[0] in line:
                    line_matches = [i in j for i, j in zip(pattern, file_content[row:])]
                    if all(line_matches):
                        return row

    return None


def year_string_to_range(s):
    """
    Convert a year string to a list of years containing all years.
    '2022' -> [2022]
    '2020-2022' -> [2020, 2021, 2022]
    """
    year_range = sum(
        (
            (
                list(range(*[int(j) + k for k, j in enumerate(i.split("-"))]))
                if "-" in i
                else [int(i)]
            )
            for i in s.split(",")
        ),
        [],
    )

    return sorted(set(year_range))


def match_copyright_year(line, year_pattern, year):
    """
    Check if the line matches the regex pattern and year, none is returned if regex match fails
    or the year is not matching.

    line         - The line where the year is stated
    year_pattern - The copyright year line regex pattern
    year         - The year that should be checked for
    """
    years_match = year_pattern.match(line)

    if years_match:
        years = years_match.group("date")
        return year in year_string_to_range(years)

    return None


def copyright_pattern_py(year=""):
    """
    Copyright pattern for python files

    year - Replaces year in the copyright statement.
            Should be left empty when used to match against file content.
    """
    return [f"# Copyright (c) Acconeer AB, {year}", "# All rights reserved"]


def copyright_exists_py(file_content):
    """
    Check if a copyright statement is present in a .py file and is in the correct format.
    Returns the line number where the copyright statement begins. If no statement exists or
    is in the wrong format, None is returned.

    file_content - The content of the source file as a list where every entry is a line
    """

    return match_copyright_pattern(file_content, copyright_pattern_py())


def copyright_check_year_py(file_content, line_nbr, current_year):
    """
    Check that the current year is present in a copyright statement in a .py-file.

    file_content - the content of the file
    line_nbr     - the line number where the copyright statement begins
    """

    year_pattern = re.compile(
        r"# Copyright (\(c\)|&copy;) Acconeer AB, "
        + r"(?P<date>\d+(-\d+)?)(. All rights reserved.)?\n"
    )

    return match_copyright_year(file_content[line_nbr], year_pattern, current_year)


def read_file(file_path):
    """
    Read a source file and return its content

    file_path - the absolute or relative path to the source file
    """

    contents = ""
    with open(file_path, "r", errors=None) as file:
        contents = list(file)

    return contents


def write_file(file_path, content):
    """
    Write to a file.

    file_path - the absolute or relative path to the source file
    content   - the content to be written
    """

    content = "".join(content)
    with open(file_path, "w") as header_file:
        header_file.write(content)


def check_copyright(file_path, ignore_year, update, current_year):
    """
    Check copyright statement of a file

    file_path    - The file to check
    ignore_year  - Don't check the year stated in copyright statement
    update       - Update year of copyright statement or add copyright statement if missing
    current_year - The current year. Used to check year of copyright statement
    """

    link_copyright_methods = {
        ".py": (copyright_exists_py, copyright_check_year_py, copyright_pattern_py),
    }

    copyright_methods = link_copyright_methods.get(Path(file_path).suffix, None)

    if copyright_methods:
        copyright_exist, copyright_check_year, copyright_pattern = copyright_methods

        # Read the file
        try:
            content = read_file(file_path)
        except ValueError:
            return (
                Status.NOT_SUPPORTED,
                "{}: encoding seems to be something else than utf-8".format(file_path),
            )

        # Empty files without copyright is accepted
        if len(content):
            # Check if there is a correctly formatted copyright statement
            copyright_line_nbr = copyright_exist(content)

            if copyright_line_nbr is None and not update:
                return (
                    Status.MISSING,
                    "{}: copyright statement is missing or has incorrect format.".format(
                        file_path
                    ),
                )

            if not current_year:
                current_year = datetime.datetime.now().year

            year_up_to_date = (
                copyright_check_year(content, copyright_line_nbr, current_year)
                if copyright_line_nbr is not None
                else False
            )

            # Update the year and write it to the source file
            if update and not year_up_to_date:
                content = update_copyright_year(
                    content, copyright_line_nbr, current_year, copyright_pattern(current_year)
                )
                write_file(file_path, content)
                print("{}: updated copyright year.".format(file_path))

            # Check that the copyright year is up to date
            elif not ignore_year and not year_up_to_date:
                return Status.YEAR_NOT_UP_TO_DATE, "{}: copyright year is not up-to-date.".format(
                    file_path
                )

        return Status.OK, None
    else:
        return Status.NOT_SUPPORTED, None


def check_copyright_files(file_paths, ignore_year=False, update_year=False, current_year=None):
    """
    Check that Acconeer copyright statement is present and correctly formatted in source files.
    A list containing files with incorrect copyright statement is returned.

    file_paths  - a list containing file paths
    ignore_year - set to True if the copyright year should be ignored when checking the format
    update_year - if True, the year in the copyright statement will be updated to the current year
    """

    incorrect_files = []
    for file_path in file_paths:
        file_status, print_str = check_copyright(file_path, ignore_year, update_year, current_year)
        if print_str:
            print(print_str)
        if file_status not in {Status.OK, Status.NOT_SUPPORTED}:
            incorrect_files.append(file_path)

    return incorrect_files


def _get_modified_files():
    # This will show all modified files except deleted and wholly renamed files
    git_args = [
        "git",
        "show",
        "--name-only",
        "--diff-filter=dr",
        "-M100%",
        "--format=tformat:",
        "HEAD",
    ]
    completed_process = subprocess.run(
        git_args, stdout=subprocess.PIPE, universal_newlines=True, check=False
    )
    completed_process.check_returncode()

    return completed_process.stdout.splitlines()


def _get_all_files():
    git_args = ["git", "ls-files"]
    completed_process = subprocess.run(
        git_args, stdout=subprocess.PIPE, universal_newlines=True, check=False
    )
    completed_process.check_returncode()

    return completed_process.stdout.splitlines()


def _get_commit_time():
    git_args = [
        "git",
        "log",
        "-1",
        "--date=unix",
        "--format=%cd",
        "HEAD",
    ]
    completed_process = subprocess.run(
        git_args, stdout=subprocess.PIPE, universal_newlines=True, check=False
    )
    completed_process.check_returncode()

    return int(completed_process.stdout.splitlines()[0])


def main():
    """Main entry function"""

    arg_parser = argparse.ArgumentParser()
    arg_parser.add_argument(
        "-a",
        "--all-files",
        action="store_true",
        help="check all repository files, not just the changed ones",
    )

    arg_parser.add_argument("--year", type=int, help="year to use for copyright year check")

    arg_parser.add_argument(
        "-u", "--update-year", action="store_true", help="update the year in the copyright"
    )

    args = arg_parser.parse_args()
    config = configparser.ConfigParser()
    config.read("setup.cfg")
    section = "check_copyright"

    ignore_files = config.get(section, "ignore_files", fallback="")
    ignore_files = [s.strip() for s in ignore_files.split(",")]
    ignore_files = [s for s in ignore_files if s]

    current_year = args.year

    if not current_year:
        commit_time = _get_commit_time()

        current_year = (
            datetime.datetime.fromtimestamp(commit_time, tz=datetime.timezone.utc).year
            if commit_time
            else None
        )

    filenames = _get_modified_files() if not args.all_files else _get_all_files()

    for filename in filenames.copy():
        if any(fnmatch.fnmatch(filename, p) for p in ignore_files):
            filenames.remove(filename)

    incorrect_files = check_copyright_files(
        filenames, update_year=args.update_year, current_year=current_year
    )

    # Check if there were incorrect files
    if incorrect_files:
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
