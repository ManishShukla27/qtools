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

from .common import *

_description = "A simple AMQP message broker for testing"

class BrokerCommand(Command):
    def __init__(self, home_dir):
        super(BrokerCommand, self).__init__(home_dir)

        self.parser.description = _description

        self.parser.add_argument("domain", metavar="DOMAIN", default="localhost:5672")

        self.add_common_arguments()

    def init(self):
        super(BrokerCommand, self).init()

        self.init_common_attributes()

        self.domain = self.args.domain

    def run(self):
        handler = _BrokerHandler(self)
        container = _reactor.Container(handler)

        container.run()
        
class _BrokerQueue(object):
    def __init__(self, command, address):
        self.command = command
        self.address = address

        self.messages = _collections.deque()
        self.consumers = list()

        self.command.notice("Creating {}", self)

    def __repr__(self):
        return "queue '{}'".format(self.address)

    def add_consumer(self, link):
        assert link.is_sender
        assert link not in self.consumers

        self.command.notice("Adding consumer for '{}' to {}", link.connection.remote_container, self)

        self.consumers.append(link)

    def remove_consumer(self, link):
        assert link.is_sender

        self.command.notice("Removing consumer for '{}' from {}", link.connection.remote_container, self)

        try:
            self.consumers.remove(link)
        except ValueError:
            pass

    def store_message(self, message):
        self.messages.append(message)

    def forward_messages(self, link):
        assert link.is_sender

        while link.credit > 0:
            try:
                message = self.messages.popleft()
            except IndexError:
                break

            link.send(message)

class _BrokerHandler(_handlers.MessagingHandler):
    def __init__(self, command):
        super(_BrokerHandler, self).__init__()

        self.command = command
        self.queues = dict()        
        self.verbose = False

    def on_start(self, event):
        self.acceptor = event.container.listen(self.command.domain)

        self.command.notice("Listening on '{}'", self.command.domain)

    def get_queue(self, address):
        try:
            queue = self.queues[address]
        except KeyError:
            queue = self.queues[address] = _BrokerQueue(self.command, address)

        return queue

    def on_link_opening(self, event):
        if event.link.is_sender:
            if event.link.remote_source.dynamic:
                address = str(_uuid.uuid4())
            else:
                address = event.link.remote_source.address

            assert address is not None

            event.link.source.address = address

            queue = self.get_queue(address)
            queue.add_consumer(event.link)

        if event.link.is_receiver:
            address = event.link.remote_target.address

            assert address is not None

            event.link.target.address = address

    def on_link_closing(self, event):
        if event.link.is_sender:
            queue = self.queues[link.source.address]
            queue.remove_consumer(link)

    def on_connection_opening(self, event):
        self.command.notice("Opening connection from '{}'", event.connection.remote_container)

        # XXX I think this should happen automatically
        event.connection.container = event.container.container_id

    def on_connection_closing(self, event):
        self.command.notice("Closing connection from '{}'", event.connection.remote_container)

        self.remove_consumers(event.connection)

    def on_disconnected(self, event):
        self.command.notice("Disconnected from {}", event.connection.remote_container)

        self.remove_consumers(event.connection)

    def remove_consumers(self, connection):
        link = connection.link_head(_proton.Endpoint.REMOTE_ACTIVE)

        while link is not None:
            if link.is_sender:
                queue = self.queues[link.source.address]
                queue.remove_consumer(link)

            link = link.next(_proton.Endpoint.REMOTE_ACTIVE)

    def on_sendable(self, event):
        queue = self.get_queue(event.link.source.address)
        queue.forward_messages(event.link)

    def on_message(self, event):
        queue = self.get_queue(event.link.target.address)
        queue.store_message(event.message)

        for link in queue.consumers:
            queue.forward_messages(link)