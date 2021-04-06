# Copyright (C) 2021 CS GROUP - France. All Rights Reserved.
# SPDX-License-Identifier: BSD-2-Clause

import fcntl
import mimetypes
import os
import threading
import time
import warnings

from idmef import Message, SerializedMessage, get_serializer
from queue import Queue
from typing import Optional
from urllib.parse import urlparse, unquote

from ..exceptions import InvalidLocationError
from ..transport import Transport

O_BINARY = getattr(os, 'O_BINARY', 0)
O_CREAT = getattr(os, 'O_CREAT', 0)
O_EXCL = getattr(os, 'O_EXCL', 0)
O_EXLOCK = getattr(os, 'O_EXLOCK', 0)
O_NONBLOCK = getattr(os, 'O_NONBLOCK', 0)


class FileTransport(Transport):
    content_type = "application/json"
    parameters = {
        'interval': dict(allowed_types=(int, float), cast_to=float, min=1., max=None),
        'delay': dict(allowed_types=(int, float), cast_to=float, min=0., max=None),
        'uid': dict(allowed_types=int, cast_to=int, min=-1, max=None),
        'gid': dict(allowed_types=int, cast_to=int, min=-1, max=None),
        'permissions': dict(allowed_types=int, cast_to=int, min=0o000, max=0o777),
    }

    def __init__(self, url: str, queue: Optional[Queue] = None, content_type: Optional[str] = None) -> None:
        if not mimetypes.inited:
            mimetypes.init()

        result = urlparse(url)
        if result.scheme != 'file':
            raise InvalidLocationError("Invalid scheme")

        path = unquote(result.path)
        if not os.path.isdir(path) or not os.access(path, os.R_OK | os.W_OK):
            raise InvalidLocationError("Invalid path")

        if content_type:
            self.content_type = content_type

        # Check whether the given content_type is supported.
        get_serializer(self.content_type)

        # Private parameters.
        self.path = path
        self.lock = threading.Lock()
        self.checker = None
        self.checker_shutdown = threading.Event()
        self.queue = queue

        # Public r/w parameters.
        self.interval = 10
        self.delay = 0
        self.uid = -1
        self.gid = -1
        self.permissions = 0o640

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
        if self.checker is None:
            raise RuntimeError("start() must be called before calling send_message()")

        content_type = self.content_type
        extension = mimetypes.guess_extension(content_type)
        filename = os.path.join(self.path, '%d%s' % (time.time(), extension))
        with self.lock:
            permissions = self.permissions
            uid = self.uid
            gid = self.gid
        fd = os.open(filename, os.O_WRONLY | O_BINARY | O_NONBLOCK | O_EXLOCK | O_CREAT | O_EXCL, permissions)
        try:
            if not O_EXLOCK:
                fcntl.lockf(fd, fcntl.LOCK_EX)
            try:
                os.fchown(fd, uid, gid)
                data = bytes(message.serialize(content_type))
                while data:
                    try:
                        written = os.write(fd, data)
                    except InterruptedError:
                        continue
                    data = data[written:]
            finally:
                if not O_EXLOCK:
                    fcntl.lockf(fd, fcntl.LOCK_UN)
        finally:
            os.close(fd)

    def _handle_file(self, content_type, filename):
        buf = b""
        try:
            # On some systems, the file descriptor must be opened in (read-)write mode
            # so that an exclusive lock can be obtained.
            fd = os.open(filename, os.O_RDWR | O_BINARY | O_NONBLOCK | O_EXLOCK, 0)
            try:
                if not O_EXLOCK:
                    fcntl.lockf(fd, fcntl.LOCK_EX)
                try:
                    while True:
                        data = os.read(fd, 1024)
                        if not data:
                            break
                        buf += data
                finally:
                    if not O_EXLOCK:
                        fcntl.lockf(fd, fcntl.LOCK_UN)
            finally:
                os.close(fd)
            os.unlink(filename)
        except Exception as e:
            warnings.warn(str(e), RuntimeWarning)
        else:
            self.queue.put(Message.unserialize(SerializedMessage(content_type, buf)), timeout=30)

    def _check_files(self):
        if not self.queue:
            return

        with self.lock:
            interval = max(0.0, self.delay)
        if self.checker_shutdown.wait(interval):
            return

        while True:
            for file in os.listdir(self.path):
                filename, extension = os.path.splitext(file)
                try:
                    mime = mimetypes.types_map[extension]
                    get_serializer(mime) # Is this a supported MIME type?
                except KeyError as e:
                    continue
                self._handle_file(mime, os.path.join(self.path, file))

            with self.lock:
                interval = self.interval
            if self.checker_shutdown.wait(interval):
                break

    def start(self) -> Transport:
        if self.checker is not None:
            raise RuntimeError()

        self.checker_shutdown.clear()
        self.checker = threading.Thread(target=self._check_files)
        self.checker.start()

    def stop(self) -> Transport:
        if self.checker is None:
            raise RuntimeError()

        self.checker_shutdown.set()
        self.checker.join()
        self.checker = None

