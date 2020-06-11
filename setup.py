import setuptools
import instafs


with open("README.adoc", "r") as fh:
    long_description = fh.read()


setuptools.setup(
    name="instafs",
    version=instafs.__version__,
    author=instafs.__author__,
    author_email="igsha@users.noreply.github.com",
    description=instafs.__description__,
    long_description=long_description,
    long_description_content_type="text/asciidoc",
    url="https://github.com/igsha/instafs",
    packages=setuptools.find_packages(),
    entry_points={
        'console_scripts': [
            'instafs = instafs.instafs:main'
        ],
    },
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
    python_requires='>=3.6',
    install_requires=[
        'requests>=2.23.0',
        'fuse-python>=1.0.0',
    ],
)
