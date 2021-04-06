IDMEFv2 Transport library
#########################

This repository contains a Python library that provides a common interface
and various transport implementations that can be used to exchange security alerts
encoded using the Intrusion Detection Message Exchange Format version 2 (IDMEFv2)
between two systems/entities.
It is part of the `SECEF <https://www.secef.net/>` project.

You can find more information about the previous version (v1) of the
Intrusion Detection Message Exchange Format
in `RFC 4765 <https://tools.ietf.org/html/rfc4765>`.

Visit https://www.secef.net/ for more information about IDMEFv2's status
and development progress.

Installation
============

The following prerequisites must be installed on your system to install
and use this library:

* Python 3.6 or later
* The Python `requests <https://pypi.org/project/requests/>` package
  (usually available as a system package under the name ``python3-requests``)
* The Python `kafka-python <https://pypi.org/project/kafka-python/>` package
  (usually available as a system package under the name ``python3-kafka``)
* The Python `idmef <https://github.com/SECEF/idmefv2-lib-model>` package

To install the library, simply run:

..  sourcecode:: sh

    # Replace "python3" with the full path to the Python 3 interpreter
    # if necessary.
    sudo python3 install setup.py

Usage
=====

Send a message
--------------

To send an IDMEF message:

* Create an instance of the desired transport medium
* Start the transport medium
* Send the message and repeat this step as many times as necessary
* Stop the transport medium

Example:

..  sourcecode:: python

    # Import the transport factory
    from idmeftransport import get_transport

    # Create an HTTP transport the sends IDMEFv2 messages to a remote SIEM
    # hosted at "siem.example.com". The call to start() ensures that the transport
    # medium is fully initialized and ready to process messages.
    # The messages will be encoded using the "application/json" content type.
    #
    # This is usually done as part of the application's initialization/configuration
    # process.
    transport = get_transport('http://siem.example.com/', content_type="application/json")
    transport.start()

    # Assuming "msg" refers to an instance of idmef.Message
    transport.send_message(msg)

    # Shut the HTTP transport medium down after usage.
    #
    # This is usually done as part of the application's shutdown process.
    transport.stop()

Process incoming messages
-------------------------

To process incoming messages, a python queue (an instance of ``queue.Queue``)
is necessary. This is designed to integrate well will applications that
make use of Python's multi-threading features.

When the transport receives IDMEFv2 messages, it will automatically
unserialize them and store them in the queue.

Example:

..  sourcecode:: python

    import time
    from queue import Queue, Empty
    from idmeftransport import get_transport

    # Application initialization: create an empty queue and create
    # the transport medium.
    #
    # When receiving IDMEFv2 messages using the HTTP transport,
    # the address/hostname inside the URL specifies the IP address
    # to listen on.
    #
    # In addition, the second argument to "get_transport()" specifies
    # the queue where new IDMEFv2 messages will be stored.
    queue = Queue()
    transport = get_transport('http://127.0.0.1/', queue, content_type='application/json')

    # Start processing of incoming messages.
    transport.start()

    # Wait 30 seconds, then stop processing incoming messages.
    time.sleep(30)
    transport.stop()

    try:
        # Check whether a message was indeed received
        msg = queue.get(timeout=0)
    except Empty:
        print("No message received")
    else:
        # Do something with the message and acknowledge it.
        # The acknowledgement part is necessary to allow processing
        # of the next message.
        queue.task_done()

    # Application shutdown: wait for the queue to shut down
    queue.join()

Contributions
=============

All contributions must be licensed under the BSD 2-clause license.
See the LICENSE file inside this repository for more information.

To improve coordination between the various contributors, we kindly ask
that new contributors subscribe to the `SECEF mailing list
<https://www.freelists.org/list/secef>` as a way to introduce themselves.
