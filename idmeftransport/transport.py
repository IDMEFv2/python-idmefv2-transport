# Copyright (C) 2021 CS GROUP - France. All Rights Reserved.
# SPDX-License-Identifier: BSD-2-Clause

import abc
import pkg_resources
import warnings

from collections.abc import Callable
from idmef import Message
from queue import Queue
from typing import Optional

_transports = None


class Transport(metaclass=abc.ABCMeta):
    @abc.abstractmethod
    def __init__(self, url: str, queue: Optional[Queue] = None, content_type: Optional[str] = None) -> None:
        """
        This method is responsible for initializing the transport layer.
        It MAY load and initialize additionnal resources/dependencies,
        set this layer's settings to their default values, allocate buffers, etc.

        @param url:
            URL to use to initialize the transport layer.

            The implementing class MUST raise an exception if the given URL
            does not specify a scheme or the specified scheme is not supported
            by this transport layer.

        @param queue:
            An optional instance of {queue.Queue} (or one of its subclasses)
            where received IDMEFv2 messages will be pushed.

            Note:   Checking for the presence of new IDMEF messages does not
                    start until the start() method is called.
                    The check is performed until the stop() method is called.
                    It can then be reenabled by calling the start() method
                    once again.

        @param content_type:
            If specified, the IDMEFv2 messages will be serialized to the
            given MIME content type before being sent.
            Otherwise, a default serialization mechanism will be selected
            automatically by the transport.

            Note:   This parameter only controls the content type of messages
                    being sent by this transport. If this transport is used
                    to receive IDMEFv2 message, any content type can be used
                    as long as a compatible serializer exists.

        This method MUST raise an exception in case a new transport layer
        cannot be created using the provided URL (e.g. because the URL was
        invalid, the URL's scheme is not supported, the URL lacked some kind
        of information, due to the lack of a required resource, ...).

        This method MUST raise an exception when a {content_type} is specified
        which cannot be used (e.g. because it is invalid or no serializer
        supporting that MIME type is available).
        """
        raise NotImplementedError()

    @abc.abstractmethod
    def set_parameter(self, name: str, value) -> 'Transport':
        """
        Sets a parameter related to this transport layer.

        @param name:
            Name of the parameter to set.

        @param value:
            Value for that parameter.

        This method MUST raise an exception when the parameter cannot be set
        (e.g. because the parameter name or value is invalid).
        """
        raise NotImplementedError()

    @abc.abstractmethod
    def get_parameter(self, name: str):
        """
        Retrieves the value for a parameter related to this transport layer.

        @param name:
            Name of the parameter to get.

        This method MUST raise an exception when the parameter name is invalid.
        """
        raise NotImplementedError()

    @abc.abstractmethod
    def send_message(self, message: Message) -> 'Transport':
        """
        Sends the given message using this transport layer.

        @param message:
            The IDMEFv2 message to send.

        Note:   IDMEF messages cannot be sent using this transport layer
                until the start() method is called.
                The ability to send IDMEF messages is also lost whenever
                the stop() method is called (until the next call to start()).

        This method MUST raise an exception in case one of the provided
        message cannot be sent.
        """
        raise NotImplementedError()

    @abc.abstractmethod
    def start(self) -> 'Transport':
        """
        This method is responsible for starting the transport layer.
        It must be called by the application after initializing.

        After this method is called, IDMEFv2 messages can be sent
        using send_message(). The queue passed to __init__(),
        if any, will also start received available IDMEFv2 messages.

        This usually includes connecting to a remote host/port.
        This method MAY be a no-op in case the transport layer is not
        permanent (e.g. when a new connection needs to be created for
        every operation).

        This method MAY raise an exception in case the transport layer
        cannot be started.
        """
        raise NotImplementedError()

    @abc.abstractmethod
    def stop(self) -> 'Transport':
        """
        This method is responsible for stopping the transport layer.

        It SHOULD therefore free up any resource that may have been
        called when start() was called.
        This method MAY be a no-op in case the transport layer is not
        permanent.

        This method MAY raise an exception in case the transport layer
        cannot be stopped.
        """
        raise NotImplementedError()


def get_transport(url: str, queue: Optional[Queue] = None, content_type: Optional[str] = None) -> Transport:
    """
    This methods returns a transport layer compatible with the
    given URL.

    @param url:
        URL containing the information required to create the new
        transport layer.

    @param content_type:
        If specified, the IDMEFv2 messages will be serialized to the
        given MIME content type before being sent.
        Otherwise, a default serialization mechanism will be selected
        automatically by the transport.

    This method MUST raise a KeyError exception when no transport
    layer compatible with the given URL or content type can be created.
    """
    global _transports

    if _transports is None:
        _transports = {}
        for entry_point in pkg_resources.iter_entry_points('idmef.transport'):
            try:
                cls = entry_point.load()
                if issubclass(cls, Transport):
                    _transports[entry_point.name] = cls
            except Exception as e:
                warnings.warn(str(e), ResourceWarning)

    return _transports[url.partition('://')[0]](url, queue, content_type)
