# Copyright (C) 2021 CS GROUP - France. All Rights Reserved.
# SPDX-License-Identifier: BSD-2-Clause

import email.parser
import email.policy
import os
import io
import requests
import socket
import socketserver
import threading
import warnings

from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, HTTPServer
from idmef import Message, SerializedMessage, get_serializer
from queue import Queue
from typing import Optional
from urllib.parse import urlparse, unquote

from ..exceptions import InvalidLocationError
from ..transport import Transport


class HTTPRequestHandler(BaseHTTPRequestHandler):
    def _iter_parts(self, message):
        if not message.is_multipart():
            return iter([message])
        return message.iter_attachments()

    def do_POST(self):
        try:
            self._do_POST()
        except Exception as e:
            return self.send_error(HTTPStatus.INTERNAL_SERVER_ERROR, explain=str(e))

    def _do_POST(self):
        if self.path != '/':
            return self.send_error(HTTPStatus.FORBIDDEN)

        length = self.headers.get('Content-Length')
        if length is None:
            return self.send_error(HTTPStatus.LENGTH_REQUIRED)

        try:
            length = int(length)
        except ValueError:
            return self.send_error(HTTPStatus.BAD_REQUEST)

        # 640 kB ought to be enough for anybody... :)
        if length >= 655360:
            return self.send_error(HTTPStatus.REQUEST_ENTITY_TOO_LARGE)

        # Parse the HTTP data again starting from the headers.
        # Since the headers have already been parsed and rfile is non-seektable,
        # we cannot use email.message_from_binary_file() here.
        feedparser = email.parser.BytesFeedParser(None, policy=email.policy.HTTP)
        feedparser.feed(bytes(self.headers))
        while length > 0:
            data = self.rfile.read(min(8192, length))
            if not data:
                break
            feedparser.feed(data)
            length -= len(data)
        message = feedparser.close()

        # We iterate over the request's parts twice:
        # - we try to decode each part to a valid IDMEF message
        # - then, we add those messages to the queue
        #
        # We do that so as to ensure that either all the messages
        # have been processed, or none of them have.
        messages = []
        for part in self._iter_parts(message):
            content_type = part.get_content_type()
            try:
                messages.append(Message.unserialize(SerializedMessage(content_type, part.get_content())))
            except Exception:
                return self.send_error(HTTPStatus.UNSUPPORTED_MEDIA_TYPE)

        # We expect at least one IDMEF message.
        if not messages:
            return self.send_error(HTTPStatus.UNPROCESSABLE_ENTITY)

        # @HACK This code makes use of Queue.queue()'s internal API
        queue = self.server.message_queue
        nb_messages = len(messages)
        with queue.not_full:
            if queue.maxsize > 0 and (queue.maxsize - queue.qsize()) < nb_messages:
                return self.send_error(HTTPStatus.SERVICE_UNAVAILABLE)

            # Add each IDMEF message to the queue, in the same order
            # they appeared in the request.
            #
            # We use _put() here to enqueue the items to avoid making
            # any assumption on the queue's implementation.
            for idmef in messages:
                queue._put(idmef)
            queue.unfinished_tasks += nb_messages
            queue.not_empty.notify(nb_messages)

        self.send_response(HTTPStatus.NO_CONTENT)
        self.end_headers()


class ThreadedHTTPServer(socketserver.ThreadingMixIn, HTTPServer):
    def __init__(self, server_address, RequestHandlerClass, queue):
        super().__init__(server_address, RequestHandlerClass)
        self.message_queue = queue


class HTTPTransport(Transport):
    content_type = "application/json"
    parameters = {
        'interval': dict(allowed_types=(int, float), cast_to=float, min=1., max=None),
        'delay': dict(allowed_types=(int, float), cast_to=float, min=0., max=None),
        'my_cert': dict(allowed_types=str, cast_to=str),
        'my_key': dict(allowed_types=str, cast_to=str),
        'ca_cert': dict(allowed_types=str, cast_to=str),
        'requested_address': dict(allowed_types=(), cast_to=None),
        'server_address': dict(allowed_types=(), cast_to=None),
    }

    def __init__(self, url: str, queue: Optional[Queue] = None, content_type: Optional[str] = None) -> None:
        result = urlparse(url)
        if result.scheme not in ('http', 'https'):
            raise InvalidLocationError("Invalid scheme")

        if result.hostname is None:
            raise InvalidLocationError("No hostname provided")

        if content_type:
            self.content_type = content_type

        # Check whether the given content_type is supported.
        get_serializer(self.content_type)

        # Private parameters.
        self.lock = threading.Lock()
        self.started = False
        self.server = None
        self.server_thread = None
        self.queue = queue

        # Public r/w parameters.
        self.interval = 10
        self.delay = 0
        self.my_cert = None
        self.my_key = None
        self.ca_cert = None

        # Public r/o parameters.
        self.url = url
        self.server_address = None

    def set_parameter(self, name: str, value) -> Transport:
        if not name in self.parameters:
            raise KeyError(name)

        conf = self.parameters[name]
        if not isinstance(value, conf['allowed_types']):
            raise ValueError(value)

        value = conf['cast_to'](value)
        if (conf['min'] is not None and value < conf['min']) or \
           (conf['max'] is not None and value > conf['max']):
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

        headers = {'Content-Type': self.content_type}
        with self.lock:
            my_cert = self.my_cert
            my_key = self.my_key
            ca_cert = self.ca_cert

        params = {}
        if ca_cert:
            params['verify'] = ca_cert
        if my_cert:
            if my_key:
                params['cert'] = (my_cert, my_key)
            else:
                params['cert'] = my_cert

        response = requests.post(self.url, data=bytes(message.serialize(self.content_type)),
                                 headers=headers, **params)
        response.raise_for_status()
        return self

    def start(self) -> Transport:
        if self.started:
            raise RuntimeError()

        if self.queue:
            # We already parsed the URL once during init, and we already checked
            # that it contains a supported scheme and a seemingly valid hostname.
            result = urlparse(self.url)
            port = result.port
            if port is None:
                port = socket.getservbyname(result.scheme, 'tcp')

            # @FIXME Add support for HTTPS
            self.server = ThreadedHTTPServer((result.hostname, port),
                                             HTTPRequestHandler,
                                             self.queue)

            try:
                with self.lock:
                    self.server_address = self.server.socket.getsockname()
                    self.server_thread = threading.Thread(target=self.server.serve_forever)
                    self.server_thread.start()
            except:
                self.server.shutdown()
                self.server = None
                raise

        self.started = True

    def stop(self) -> Transport:
        if not self.started:
            raise RuntimeError()

        if self.server:
            with self.lock:
                self.server_address = None
            self.server.shutdown()
            self.server.server_close()
            self.server = None
            self.server_thread.join()
            self.server_thread = None

        self.started = False

