# Copyright (C) 2003-2007  Robey Pointer <robeypointer@gmail.com>
#
# This file is part of paramiko.
#
# Paramiko is free software; you can redistribute it and/or modify it under the
# terms of the GNU Lesser General Public License as published by the Free
# Software Foundation; either version 2.1 of the License, or (at your option)
# any later version.
#
# Paramiko is distributed in the hope that it will be useful, but WITHOUT ANY
# WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS FOR
# A PARTICULAR PURPOSE.  See the GNU Lesser General Public License for more
# details.
#
# You should have received a copy of the GNU Lesser General Public License
# along with Paramiko; if not, write to the Free Software Foundation, Inc.,
# 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301 USA.

"""
Implementation of an SSH2 "message".
"""

import struct
from io import BytesIO

from paramiko import util
from paramiko.common import zero_byte, max_byte, one_byte
from paramiko.util import u


class Message(object):
    """
    An SSH2 message is a stream of bytes that encodes some combination of
    strings, integers, bools, and infinite-precision integers.  This class
    builds or breaks down such a byte stream.

    Normally you don't need to deal with anything this low-level, but it's
    exposed for people implementing custom extensions, or features that
    paramiko doesn't support yet.
    """

    big_int = 0xff000000

    def __init__(self, content=None):
        """
        Create a new SSH2 message.

        :param str content:
            the byte stream to use as the message content (passed in only when
            decomposing a message).
        """
        if content is not None:
            self.packet = BytesIO(content)
        else:
            self.packet = BytesIO()

    def __str__(self):
        """
        Return the byte stream content of this message, as a string/bytes obj.
        """
        return self.asbytes()

    def __repr__(self):
        """
        Returns a string representation of this object, for debugging.
        """
        return "paramiko.Message(" + repr(self.packet.getvalue()) + ")"

    def asbytes(self):
        """
        Return the byte stream content of this Message, as bytes.
        """
        return self.packet.getvalue()

    def rewind(self):
        """
        Rewind the message to the beginning as if no items had been parsed
        out of it yet.
        """
        self.packet.seek(0)

    def get_remainder(self):
        """
        Return the bytes (as a `str`) of this message that haven't already been
        parsed and returned.
        """
        position = self.packet.tell()
        remainder = self.packet.read()
        self.packet.seek(position)
        return remainder

    def get_so_far(self):
        """
        Returns the `str` bytes of this message that have been parsed and
        returned. The string passed into a message's constructor can be
        regenerated by concatenating ``get_so_far`` and `get_remainder`.
        """
        position = self.packet.tell()
        self.rewind()
        return self.packet.read(position)

    def get_bytes(self, n):
        """
        Return the next ``n`` bytes of the message (as a `str`), without
        decomposing into an int, decoded string, etc.  Just the raw bytes are
        returned. Returns a string of ``n`` zero bytes if there weren't ``n``
        bytes remaining in the message.
        """
        b = self.packet.read(n)
        max_pad_size = 1 << 20  # Limit padding to 1 MB
        if len(b) < n < max_pad_size:
            return b + zero_byte * (n - len(b))
        return b

    def get_byte(self):
        """
        Return the next byte of the message, without decomposing it.  This
        is equivalent to `get_bytes(1) <get_bytes>`.

        :return:
            the next (`str`) byte of the message, or ``'\000'`` if there aren't
            any bytes remaining.
        """
        return self.get_bytes(1)

    def get_boolean(self):
        """
        Fetch a boolean from the stream.
        """
        b = self.get_bytes(1)
        return b != zero_byte

    def get_adaptive_int(self):
        """
        Fetch an int from the stream.

        :return: a 32-bit unsigned `int`.
        """
        byte = self.get_bytes(1)
        if byte == max_byte:
            return util.inflate_long(self.get_binary())
        byte += self.get_bytes(3)
        return struct.unpack(">I", byte)[0]

    def get_int(self):
        """
        Fetch an int from the stream.
        """
        return struct.unpack(">I", self.get_bytes(4))[0]

    def get_int64(self):
        """
        Fetch a 64-bit int from the stream.

        :return: a 64-bit unsigned integer (`int`).
        """
        return struct.unpack(">Q", self.get_bytes(8))[0]

    def get_mpint(self):
        """
        Fetch a long int (mpint) from the stream.

        :return: an arbitrary-length integer (`int`).
        """
        return util.inflate_long(self.get_binary())

    def get_string(self):
        """
        Fetch a `str` from the stream.  This could be a byte string and may
        contain unprintable characters.  (It's not unheard of for a string to
        contain another byte-stream message.)
        """
        return self.get_bytes(self.get_int())

    def get_text(self):
        """
        Fetch a Unicode string from the stream.
        """
        return u(self.get_string())

    def get_binary(self):
        """
        Fetch a string from the stream.  This could be a byte string and may
        contain unprintable characters.  (It's not unheard of for a string to
        contain another byte-stream Message.)
        """
        return self.get_bytes(self.get_int())

    def get_list(self):
        """
        Fetch a list of `strings <str>` from the stream.

        These are trivially encoded as comma-separated values in a string.
        """
        return self.get_text().split(",")

    def add_bytes(self, b):
        """
        Write bytes to the stream, without any formatting.

        :param str b: bytes to add
        """
        self.packet.write(b)
        return self

    def add_byte(self, b):
        """
        Write a single byte to the stream, without any formatting.

        :param str b: byte to add
        """
        self.packet.write(b)
        return self

    def add_boolean(self, b):
        """
        Add a boolean value to the stream.

        :param bool b: boolean value to add
        """
        if b:
            self.packet.write(one_byte)
        else:
            self.packet.write(zero_byte)
        return self

    def add_int(self, n):
        """
        Add an integer to the stream.

        :param int n: integer to add
        """
        self.packet.write(struct.pack(">I", n))
        return self

    def add_adaptive_int(self, n):
        """
        Add an integer to the stream.

        :param int n: integer to add
        """
        if n >= Message.big_int:
            self.packet.write(max_byte)
            self.add_string(util.deflate_long(n))
        else:
            self.packet.write(struct.pack(">I", n))
        return self

    def add_int64(self, n):
        """
        Add a 64-bit int to the stream.

        :param long n: long int to add
        """
        self.packet.write(struct.pack(">Q", n))
        return self

    def add_mpint(self, z):
        """
        Add a long int to the stream, encoded as an infinite-precision
        integer.  This method only works on positive numbers.

        :param long z: long int to add
        """
        self.add_string(util.deflate_long(z))
        return self

    def add_string(self, s):
        """
        Add a string to the stream.

        :param str s: string to add
        """
        s = util.asbytes(s)
        self.add_int(len(s))
        self.packet.write(s)
        return self

    def add_list(self, l):  # noqa: E741
        """
        Add a list of strings to the stream.  They are encoded identically to
        a single string of values separated by commas.  (Yes, really, that's
        how SSH2 does it.)

        :param l: list of strings to add
        """
        self.add_string(",".join(l))
        return self

    def _add(self, i):
        if type(i) is bool:
            return self.add_boolean(i)
        elif isinstance(i, int):
            return self.add_adaptive_int(i)
        elif type(i) is list:
            return self.add_list(i)
        else:
            return self.add_string(i)

    def add(self, *seq):
        """
        Add a sequence of items to the stream.  The values are encoded based
        on their type: str, int, bool, list, or long.

        .. warning::
            Longs are encoded non-deterministically.  Don't use this method.

        :param seq: the sequence of items
        """
        for item in seq:
            self._add(item)
