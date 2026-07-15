from setuptools import setup, find_packages

setup(
    name="optibroker-common",
    version="1.0.5",
    packages=find_packages(),
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
