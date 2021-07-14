import os
import platform
import shutil
import sys
from glob import glob
from subprocess import DEVNULL, run


def main():
    root_dir = os.path.dirname(os.path.realpath(__file__))
    src_dir = os.path.join(root_dir, "src")
    tmp_dir = os.path.join(root_dir, "build")
    res_dir = os.path.join(root_dir, "res")

    assert len(sys.argv) > 1

    if sys.argv[1] == "--all":
        fns = glob(os.path.join(src_dir, "**/*.tex"), recursive=True)
    else:
        fns = sys.argv[1:]

    paths = [os.path.realpath(os.path.abspath(fn)) for fn in fns]

    os.makedirs(tmp_dir, exist_ok=True)

    for path in paths:
        assert os.path.splitext(path)[1] == ".tex"
        assert os.path.isfile(path)
        assert os.path.dirname(path).startswith(src_dir)

        subpath = path[len(src_dir) + 1 :]
        tmp_path = os.path.join(tmp_dir, subpath)

        os.makedirs(os.path.dirname(tmp_path), exist_ok=True)

        shutil.copy(path, tmp_path)
        os.chdir(os.path.dirname(tmp_path))

        run(
            [
                "pdflatex",
                "-interaction=nonstopmode",
                "-halt-on-error",
                os.path.basename(path),
            ],
            stdout=DEVNULL,
            check=True,
        )

        pdf_path = os.path.splitext(tmp_path)[0] + ".pdf"
        out_ext = ".png"
        out_path = os.path.join(res_dir, os.path.splitext(subpath)[0] + out_ext)

        os.makedirs(os.path.dirname(out_path), exist_ok=True)

        cmd = "convert" if platform.system().lower() == "linux" else "magick"

        run(
            [
                cmd,
                "-density",
                "400",
                pdf_path,
                out_path,
            ],
            stdout=DEVNULL,
            check=True,
        )


if __name__ == "__main__":
    main()
