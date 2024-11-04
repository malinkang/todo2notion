from setuptools import setup, find_packages

setup(
    version="0.0.1",
    packages=find_packages(),
    install_requires=[
        "requests",
        "pendulum",
        "retrying",
        "notion-client",
        "github-heatmap",
        "python-dotenv",
        "emoji",
        "mistletoe",
    ],
    entry_points={
        "console_scripts": [
            "todo = todo2notion.todo:main",
            "heatmap = todo2notion.update_heatmap:main",
        ],
    },
    author="malinkang",
    author_email="linkang.ma@gmail.com",
    description="自动将todo同步到Notion",
    long_description=open("README.md").read(),
    long_description_content_type="text/markdown",
    url="https://github.com/malinkang/todo2notion",
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
    python_requires=">=3.6",
)
