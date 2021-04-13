# Copyright (C) 2021 CS GROUP - France. All Rights Reserved.
# SPDX-License-Identifier: BSD-2-Clause

from setuptools import setup, find_packages

VERSION = "0.0.0"

setup(
    name="idmefv2-transport",
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
        "idmefv2",
        "kafka-python",
        "requests",
        "setuptools",
    ],
    packages=find_packages("."),
    entry_points={
        'idmefv2.transport': [
            'file = idmefv2_transport.transports.file:FileTransport',
            'http = idmefv2_transport.transports.http:HTTPTransport',
            'https = idmefv2_transport.transports.http:HTTPTransport',
            'kafka = idmefv2_transport.transports.kafka:KafkaTransport',
        ],
    },
)
