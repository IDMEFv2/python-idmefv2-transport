# Copyright (C) 2021 CS GROUP - France. All Rights Reserved.
# SPDX-License-Identifier: BSD-2-Clause

import os
import io
import requests
import socket
import threading
import warnings

from kafka import KafkaConsumer, KafkaProducer
from idmefv2 import Message, SerializedMessage, get_serializer
from queue import Queue
from typing import Optional
from urllib.parse import urlparse

from ..exceptions import InvalidLocationError
from ..transport import Transport


class KafkaTransport(Transport):
    content_type = "application/json"
    parameters = {
        'my_cert': dict(allowed_types=str, cast_to=str),
        'my_key': dict(allowed_types=str, cast_to=str),
        'ca_cert': dict(allowed_types=str, cast_to=str),
        'group_id': dict(allowed_types=str, cast_to=str),
        'client_id': dict(allowed_types=str, cast_to=str),
        'consumer_topics': dict(allowed_types=str, cast_to=str),
        'producer_topic': dict(allowed_types=str, cast_to=str),
        'interval': dict(allowed_types=(int, float), cast_to=float, min=1.),
    }

    def __init__(self, url: str, queue: Optional[Queue] = None, content_type: Optional[str] = None) -> None:
        result = urlparse(url)
        if result.scheme not in ('kafka'):
            raise InvalidLocationError("Invalid scheme")

        if result.netloc is None:
            raise InvalidLocationError("No bootstrap servers provided")

        if content_type:
            self.content_type = content_type

        # Check whether the given content_type is supported.
        get_serializer(self.content_type)

        # Private parameters.
        self.lock = threading.Lock()
        self.consumer = None
        self.producer = None
        self.bootstrap = result.netloc
        self.shutdown = threading.Event()
        self.started = False
        self.queue = queue

        # Public r/w parameters.
        self.interval = 5.0
        self.my_cert = None
        self.my_key = None
        self.ca_cert = None
        self.group_id = None
        self.client_id = None
        self.consumer_topics = 'idmefv2'
        self.producer_topic = 'idmefv2'

    def set_parameter(self, name: str, value) -> Transport:
        if not name in self.parameters:
            raise KeyError(name)

        conf = self.parameters[name]
        if not isinstance(value, conf['allowed_types']):
            raise ValueError(value)

        value = conf['cast_to'](value)
        conf_min = conf.get('min')
        conf_max = conf.get('max')
        if (conf_min is not None and value < conf_min) or \
           (conf_max is not None and value > conf_max):
            raise ValueError(value)

        with self.lock:
            setattr(self, name, value)

    def get_parameter(self, name: str):
        if not name in self.parameters:
            raise KeyError(name)

        with self.lock:
            return getattr(self, name)

    def send_message(self, message: Message) -> Transport:
        if not self.started:
            raise RuntimeError("start() must be called before calling send_message()")

        if not self.producer:
            raise RuntimeError("This transport cannot be used to send messages")

        headers = [('Content-Type', self.content_type.encode('ascii'))]
        with self.lock:
            self.producer.send(self.producer_topic, bytes(message.serialize(self.content_type)),
                               headers=headers)
        # @FIXME Make the delay customisable?
        self.producer.flush(60.)
        return self

    def _consume(self, interval, topics, params):
        consumer = KafkaConsumer(*topics, **params)
        while not self.shutdown.is_set():
            for topic, data in consumer.poll(interval).items():
                for msg in data:
                    content_type = [h[1] for h in msg.headers if h[0].lower() == 'content-type']
                    if len(content_type) != 1:
                        continue
                    content_type = content_type[0].decode('ascii')
                    self.queue.put(Message.unserialize(SerializedMessage(content_type, msg.value)), timeout=30)
        consumer.close()

    def start(self) -> Transport:
        if self.started:
            raise RuntimeError()

        with self.lock:
            interval = self.interval
            params = {
                'bootstrap_servers': self.bootstrap.split(','),
                'group_id': self.group_id,
                'client_id': self.client_id,
                'ssl_cafile': self.ca_cert,
                'ssl_certfile': self.my_cert,
                'ssl_keyfile': self.my_key,
            }

        if self.queue and self.consumer_topics:
            self.shutdown.clear()
            self.consumer = threading.Thread(target=self._consume,
                                             args=(interval, self.consumer_topics.split(','), params))
            self.consumer.start()

        if self.producer_topic:
            params.pop('group_id') # Only used by consumers
            self.producer = KafkaProducer(**params)

        if self.consumer is None and self.producer is None:
            raise RuntimeError()

        self.started = True

    def stop(self) -> Transport:
        if not self.started:
            raise RuntimeError()

        # Notify the consumer that we are shutting down.
        # We shut the producer down in between which leaves a little bit
        # of extra-time to the consumer.
        self.shutdown.set()

        if self.producer:
            self.producer.close()
            self.producer = None

        if self.consumer:
            self.consumer.join()
            self.consumer = None

        self.started = False

