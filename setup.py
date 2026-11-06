from setuptools import setup, find_packages

setup(
    name="workbuddy-cli",
    version="0.1.0",
    packages=find_packages(include=["workbuddy_cli", "workbuddy_cli.*"]),
    include_package_data=True,
    entry_points={
        "console_scripts": [
            "workbuddy=workbuddy_cli.cli:main",
            "wb=workbuddy_cli.cli:main",
        ],
    },
)
