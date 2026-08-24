import pathlib
import re

from setuptools import find_packages, setup

here = pathlib.Path(__file__).parent.resolve()

long_description = (here / "README.md").read_text(encoding="utf-8")

with open("requirements.txt") as f:
    requireds = [
        line.strip()
        for line in f
        if line.strip() and not line.lstrip().startswith("#")
    ]

# Nguồn sự thật duy nhất của version là __init__.py — runtime cần tự biết mình
# là bản nào để ghi vào log/báo cáo QC, nên version không thể sống ở setup.py.
version = re.search(
    r'^__version__ = "([^"]+)"',
    (here / "src" / "classify_scanned" / "__init__.py").read_text(encoding="utf-8"),
    re.MULTILINE,
).group(1)

setup(
    name="classify-scanned",
    version=version,
    description=(
        "Document scanner and quality gate: crop, deskew, and report why when it cannot"
    ),
    long_description=long_description,
    long_description_content_type="text/markdown",
    keywords="document, scanner, quality control, qc, opencv",
    package_dir={"": "src"},
    packages=find_packages(where="src"),
    # rembg/onnxruntime/numpy hiện đại cần ≥3.9; khai ">=3.5" cho phép pip cài
    # lên môi trường chắc chắn gãy.
    python_requires=">=3.9, <4",
    install_requires=requireds,
    entry_points={
        "console_scripts": [
            "classify-scanned=classify_scanned.cmd.cli:main",
            "classify-scanned-batch=classify_scanned.cmd.batch:main",
            "classify-scanned-server=classify_scanned.cmd.server:main",
            "classify-scanned-bench=classify_scanned.bench:main",
            "classify-scanned-eval=classify_scanned.eval:main",
            "classify-scanned-smartdoc=classify_scanned.smartdoc:main",
            "classify-scanned-fetch-models=classify_scanned.docaligner:main",
            "classify-scanned-apikey=classify_scanned.auth:main",
        ],
    },
)
