import os

from setuptools import setup, find_packages


def _data_files(package_dir, *folders):
    """Every file under the given folders of a package, relative to it, so the
    login theme's templates and fonts install with its code."""
    found = []
    for folder in folders:
        for root, _dirs, files in os.walk(os.path.join(package_dir, folder)):
            found += [os.path.relpath(os.path.join(root, name), package_dir) for name in files]
    return found


setup(
    name="optibroker-common",
    version="1.1.0",
    packages=find_packages(),
    package_data={
        "optibroker_common.login_theme": _data_files("optibroker_common/login_theme", "theme", "fonts"),
    },
    install_requires=[
        "Flask>=2.3.0",
        "PyJWT>=2.0.0",
        "requests>=2.28.0",
        "SQLAlchemy>=1.4.0",
        "boto3>=1.26.0",
        "Werkzeug>=2.3.0",
    ],
    python_requires=">=3.9",
)
