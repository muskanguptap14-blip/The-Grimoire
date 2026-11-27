"""Lost Ledger: reads a ledger settings file and queues entries (Python 2 module names)."""
import ConfigParser
import Queue
import urllib2
from StringIO import StringIO

import six

SETTINGS = u"""
[ledger]
name = Harbour Accounts
entries = 3
"""


def load_settings(text):
    parser = ConfigParser.SafeConfigParser()
    parser.readfp(StringIO(text))
    return parser.get("ledger", "name"), parser.getint("ledger", "entries")


def queue_entries(count):
    q = Queue.Queue()
    for n in range(count):
        q.put("entry-%d" % n)
    return q


def is_network_error(exc):
    # Only the exception classes are used; no request is ever made.
    return isinstance(exc, urllib2.URLError)


def main():
    name, count = load_settings(SETTINGS)
    assert isinstance(name, six.string_types)
    q = queue_entries(count)
    print("%s: %d queued" % (name, q.qsize()))
    print("network error check:", is_network_error(ValueError("x")))
    print("LOST LEDGER ALIVE")


if __name__ == "__main__":
    main()
