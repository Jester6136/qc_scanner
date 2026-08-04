import pathlib

from setuptools import find_packages, setup

here = pathlib.Path(__file__).parent.resolve()

long_description = (here / "README.md").read_text(encoding="utf-8")

with open("requirements.txt") as f:
    requireds = f.read().splitlines()

setup(
    name="qc-scanner",
    version="0.1.0",
    description="Document scanner and quality gate: crop, deskew, and report why when it cannot",
    long_description=long_description,
    long_description_content_type="text/markdown",
    keywords="document, scanner, quality control, qc, opencv",
    package_dir={"": "src"},
    packages=find_packages(where="src"),
    python_requires=">=3.5, <4",
    install_requires=requireds,
    entry_points={
        "console_scripts": [
            "qc-scanner=qc_scanner.cmd.cli:main",
            "qc-scanner-server=qc_scanner.cmd.server:main",
        ],
    },
)
