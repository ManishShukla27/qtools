# Qtools

    qsend URL [URLS] [OPTIONS] [< messages.txt]
    qreceive URL [URLS] [OPTIONS] [> messages.txt]

    $ qreceive amqp://amqp.zone/queue1 --count 1 &
    $ qsend amqp://amqp.zone/queue1 --message hello

    qrequest URL [URLS] [OPTIONS] [< requests.txt] [> responses.txt]
    qrespond URL [URLS] [OPTIONS]

    $ qrespond amqp://amqp.zone/requests &
    $ qrequest amqp://amqp.zone/requests < requests.txt

    qmessage [OPTIONS] | {qsend,qrequest}

    $ qmessage --count 10 | qsend amqp://amqp.zone/queue1
    $ qmessage --rate 1 | qrequest amqp://amqp.zone/requests

## Installation

### Dependencies

 - make
 - python-qpid-proton

### Using Docker images

    $ docker run -it ssorj/qtools

### Using Fedora packages

    $ sudo dnf install dnf-plugins-core
    $ sudo dnf copr enable jross/ssorj
    $ sudo dnf install qtools

### Using RHEL 7 packages

    $ cd /etc/yum.repos.d && sudo wget https://copr.fedorainfracloud.org/coprs/jross/ssorj/repo/epel-7/jross-ssorj-epel-7.repo
    $ sudo yum install qtools

### Using Ubuntu packages

Qtools requires a newer version of python-qpid-proton than Ubuntu
provides by default.  Use these commands to install it from an Ubuntu
PPA.

    $ sudo apt-get install software-properties-common
    $ sudo add-apt-repository ppa:qpid/released
    $ sudo apt-get upgrade python-qpid-proton

After this you can install from source.

### Installing from source

    $ sudo make install PREFIX=/usr/local

## Command-line interface

### Common arguments

The core commands take one or more URLs.  These indicate the location
of a message source or target, such as a queue or topic.

    qsend ADDRESS-URL [ADDRESS-URL ...]

An address URL has optional scheme and server parts.  The default
scheme is 'amqp' and 'server' is '127.0.0.1:5672'.  You can use the
`--server` option to change the default server.

    [SCHEME:][//SERVER/]ADDRESS

With a few exceptions, all the tools share the following options.

    -h, --help            Print help output
    --verbose             Print detailed logging
    --quiet               Print no logging

Tools that read from or write to the console take these options.

    --input FILE          Read input from FILE
    --output FILE         Write output to FILE

### The `qsend` and `qreceive` commands

These commands perform one-way message transfers.

    qsend URL --message MESSAGE

    qreceive URL --count 1
    -> MESSAGE

Typical usage:

    $ qsend //amqp.zone/queue1 --message m1 &
    $ qreceive //amqp.zone/queue1
    queue1: m1

### The `qrequest` and `qrespond` commands

The request command sends a request and waits for a response.  The
respond command listens for requests, processes them, and sends
responses.

    qrequest URL --message REQUEST
    -> RESPONSE

    qrespond URL --count 1

Typical usage:

    $ qrespond //amqp.zone/jobs --upper &
    $ qrequest //amqp.zone/jobs --message abc
    ABC

### The `qmessage` command

This command generates message content for use by the `qsend` and
`qrequest` tools.

    qmessage --id ID --body CONTENT
    -> MESSAGE

    qmessage --count 3
    -> MESSAGE
    -> MESSAGE
    -> MESSAGE

The output is in JSON format.  The send and request tools can consume
it.  Usually you pipe it in, like this.

    $ qmessage | qsend queue1
    $ qmessage --rate 1 | qrequest //amqp.zone/jobs

### The `qbroker` command

This is a simple broker implementation that you can use for testing.

    qbroker [--host HOST] [--port PORT]
