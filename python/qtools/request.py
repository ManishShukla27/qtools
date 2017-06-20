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
import proton.reactor as _reactor
import sys as _sys

from .common import *

_description = "Send AMQP requests"

_epilog = """
example usage:
  $ qrequest //example.net/queue0 -r abc -r xyz
  $ qrequest queue0 queue1 < requests.txt
"""

class RequestCommand(Command):
    def __init__(self, home_dir):
        super(RequestCommand, self).__init__(home_dir)

        self.parser.description = _description
        self.parser.epilog = url_epilog + _epilog

        self.add_link_arguments()

        self.parser.add_argument("-r", "--request", metavar="CONTENT",
                                 action="append", default=list(),
                                 help="Send a request containing CONTENT.  This option can be repeated.")
        self.parser.add_argument("-i", "--input", metavar="FILE",
                                 help="Read requests from FILE, one per line (default stdin)")

        self.add_common_arguments()

        self.container.handler = _Handler(self)

        self.requests = _collections.deque()
        self.input_thread = InputThread(self)

    def init(self):
        super(RequestCommand, self).init()

        self.init_link_attributes()
        self.init_common_attributes()

        self.input_file = _sys.stdin

        if self.args.input is not None:
            self.input_file = open(self.args.input, "r")

        for value in self.args.request:
            message = _proton.Message(unicode(value))
            self.send_input(message)

        if self.requests:
            self.send_input(None)

    def send_input(self, message):
        self.requests.appendleft(message)
        self.events.trigger(_reactor.ApplicationEvent("input"))

    def run(self):
        self.input_thread.start()

        super(RequestCommand, self).run()

class _Handler(LinkHandler):
    def __init__(self, command):
        super(_Handler, self).__init__(command)

        self.senders = _collections.deque()
        self.receivers_by_sender = dict()

        self.sent_requests = 0
        self.settled_requests = 0
        self.received_responses = 0
        self.stop_requested = False

    def open_links(self, event, connection, address):
        sender = event.container.create_sender(connection, address)
        receiver = event.container.create_receiver(connection, None, dynamic=True)

        self.senders.appendleft(sender)
        self.receivers_by_sender[sender] = receiver

        return sender, receiver

    def on_sendable(self, event):
        self.send_request(event)

    def on_input(self, event):
        self.send_request(event)

    def on_settled(self, event):
        self.settled_requests += 1

        if self.stop_requested and self.sent_requests == self.received_responses:
            self.close()

    def on_message(self, event):
        self.received_responses += 1

        self.command.notice("Received response '{}'", event.message.body)

        if self.stop_requested and self.sent_requests == self.received_responses:
            self.close()

    def send_request(self, event):
        if self.stop_requested:
            return

        if not self.command.ready.is_set():
            return

        try:
            request = self.command.requests.pop()
        except IndexError:
            return

        if request is None:
            if self.sent_requests == self.received_responses:
                self.close()
            else:
                self.stop_requested = True

            return

        sender = event.link

        if sender is None:
            sender = self.senders.pop()
            self.senders.appendleft(sender)

        if not sender.credit:
            self.command.requests.append(request)
            return

        receiver = self.receivers_by_sender[sender]
        request.reply_to = receiver.remote_source.address

        if request.address is None:
            request.address = sender.target.address

        delivery = sender.send(request)

        self.sent_requests += 1

        if self.command.verbose:
            self.command.notice("Sent request '{}' as delivery '{}' to '{}' on '{}'",
                                request.body,
                                delivery.tag,
                                sender.target.address,
                                sender.connection.remote_container)
