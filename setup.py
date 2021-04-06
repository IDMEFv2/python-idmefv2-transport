# Copyright (C) 2021 CS GROUP - France. All Rights Reserved.
# SPDX-License-Identifier: BSD-2-Clause

from setuptools import setup, find_packages

VERSION = "0.0.0"

setup(
    name="idmeftransport",
    version=VERSION,
    maintainer="Prelude Team",
    maintainer_email="contact.secef@csgroup.eu",
    license="GPL",
    url="https://www.secef.net",
    description="Transport layer implementations for IDMEF v2",
    long_description="""
""",
    classifiers=[
        "Development Status :: 2 - Pre-Alpha",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: BSD License",
        "Natural Language :: English",
        "Operating System :: OS Independent",
        "Programming Language :: Python :: 3 :: Only",
        "Topic :: Software Development :: Libraries :: Python Modules",
        "Topic :: Security",
        "Topic :: System :: Monitoring"
    ],
    install_requires=[
        "idmef",
        "kafka-python",
        "requests",
        "setuptools",
    ],
    packages=find_packages("."),
    entry_points={
        'idmef.transport': [
            'file = idmeftransport.transports.file:FileTransport',
            'http = idmeftransport.transports.http:HTTPTransport',
            'https = idmeftransport.transports.http:HTTPTransport',
            'kafka = idmeftransport.transports.kafka:KafkaTransport',
        ],
    },
)
