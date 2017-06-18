#
# Licensed to the Apache Software Foundation (ASF) under one
# or more contributor license agreements.  See the NOTICE file
# distributed with this work for additional information
# regarding copyright ownership.  The ASF licenses this file
# to you under the Apache License, Version 2.0 (the
# "License"); you may not use this file except in compliance
# with the License.  You may obtain a copy of the License at
#
#   http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing,
# software distributed under the License is distributed on an
# "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
# KIND, either express or implied.  See the License for the
# specific language governing permissions and limitations
# under the License.
#

from __future__ import absolute_import
from __future__ import division
from __future__ import print_function
from __future__ import unicode_literals
from __future__ import with_statement

import collections as _collections
import proton as _proton
import proton.handlers as _handlers
import proton.reactor as _reactor
import sys as _sys
import threading as _threading

from .common import *

_description = "Send AMQP messages"

class SendCommand(Command):
    def __init__(self, home_dir):
        super(SendCommand, self).__init__(home_dir)

        self.parser.description = _description

        self.parser.add_argument("url", metavar="ADDRESS-URL", nargs="+",
                                 help="The location of a message target")
        self.parser.add_argument("-m", "--message", metavar="MESSAGE",
                                 action="append", default=list(),
                                 help="A string containing message content")
        self.parser.add_argument("-i", "--input", metavar="FILE", default="-",
                                 help="Read message content from FILE; '-' means stdin")

        self.add_common_arguments()

        self.container = _reactor.Container(_SendHandler(self))
        self.events = _reactor.EventInjector()
        self.messages = _collections.deque()
        self.ready = _threading.Event()
        self.input_thread = _InputThread(self)
        self.container.selectable(self.events)

    def init(self):
        super(SendCommand, self).init()

        self.init_common_attributes()

        self.urls = self.args.url
        self.input_file = _sys.stdin

        if self.args.input != "-":
            self.input_file = open(self.args.input, "r")

        for value in self.args.message:
            # XXX Move this to the handler so it runs after link setup?
            message = _proton.Message(unicode(value))
            self.send_input(message)

        if self.messages:
            self.send_input(None)

        self.container.container_id = self.id

    def send_input(self, message):
        self.messages.appendleft(message)
        self.events.trigger(_reactor.ApplicationEvent("input"))

    def run(self):
        self.input_thread.start()
        self.container.run()

class _InputThread(_threading.Thread):
    def __init__(self, command):
        _threading.Thread.__init__(self)

        self.command = command
        self.daemon = True

    def run(self):
        self.command.ready.wait()

        with self.command.input_file as f:
            while True:
                body = f.readline()

                if body == "":
                    self.command.send_input(None)
                    break

                body = unicode(body[:-1])
                message = _proton.Message(body)

                self.command.send_input(message)

class _SendHandler(_handlers.MessagingHandler):
    def __init__(self, command):
        super(_SendHandler, self).__init__()

        self.command = command
        self.connections = set()
        self.senders = _collections.deque()
        self.stop_requested = False

        self.opened_senders = 0
        self.sent_messages = 0
        self.settled_messages = 0

    def on_start(self, event):
        for url in self.command.urls:
            host, port, path = parse_address_url(url)
            domain = "{}:{}".format(host, port)

            connection = event.container.connect(domain, allowed_mechs=b"ANONYMOUS")
            sender = event.container.create_sender(connection, path)

            self.connections.add(connection)
            self.senders.appendleft(sender)

    def on_connection_opened(self, event):
        assert event.connection in self.connections

        if self.command.verbose:
            self.command.notice("Connected to container '{}'",
                                event.connection.remote_container)

    def on_link_opened(self, event):
        assert event.link in self.senders

        self.command.notice("Created sender for target address '{}' on container '{}'",
                            event.link.target.address,
                            event.connection.remote_container)

        self.opened_senders += 1

        if self.opened_senders == len(self.senders):
            self.command.ready.set()

    def on_sendable(self, event):
        self.send_message(event)

    def on_input(self, event):
        self.send_message(event)

    def on_settled(self, event):
        self.settled_messages += 1

        if self.command.verbose:
            self.command.notice("Settled delivery '{}' to '{}'",
                                event.delivery.tag, event.link.target.address)

        if self.stop_requested and self.sent_messages == self.settled_messages:
            self.close()

    def send_message(self, event):
        if self.stop_requested:
            return

        if not self.command.ready.is_set():
            return

        try:
            message = self.command.messages.pop()
        except IndexError:
            return

        if message is None:
            if self.sent_messages == self.settled_messages:
                self.close()
            else:
                self.stop_requested = True

            return

        sender = event.link

        if sender is None:
            sender = self.senders.pop()
            self.senders.appendleft(sender)

        if not sender.credit:
            self.command.messages.append(message)
            return

        delivery = sender.send(message)

        self.sent_messages += 1

        if self.command.verbose:
            self.command.notice("Sent message '{}' as delivery '{}' to '{}' on '{}'",
                                message.body,
                                delivery.tag,
                                sender.target.address,
                                sender.connection.remote_container)

    def close(self):
        for connection in self.connections:
            connection.close()

        self.command.events.close()
