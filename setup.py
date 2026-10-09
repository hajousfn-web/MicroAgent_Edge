from setuptools import find_packages, setup

with open('README.md', encoding='utf-8') as readme:
    long_description = readme.read()

setup(
    name='microagent-edge',
    version='0.1.0',
    description='Offline-first, kernel-governed edge code-repair prototype',
    long_description=long_description,
    long_description_content_type='text/markdown',
    packages=find_packages(),
    python_requires='>=3.10',
    install_requires=[],
    license='Apache-2.0',
    classifiers=[
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.10',
        'License :: OSI Approved :: Apache Software License',
        'Operating System :: OS Independent',
    ],
)
