from setuptools import setup, find_packages

setup(
    name="googleserp",
    version="0.2.0",
    packages=find_packages(where="src"),
    package_dir={"": "src"},
    install_requires=[
        "beautifulsoup4>=4.9.3",
        "httpx>=0.24.1",
        "httpx[socks]",
    ],
)
