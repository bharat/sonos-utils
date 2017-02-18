#!/usr/bin/python
import unittest
import sonos

class TestCoreMethods(unittest.TestCase):
    def test_fuzzy(self):
        self.assertEqual(sonos.fuzz('80:2A:A8:D1:07:95'),
                         [
                             '80:2A:A8:D1:07:94',
                             '80:2A:A8:D1:07:96',
                             '80:2A:A8:D1:06:95',
                             '80:2A:A8:D1:07:95',
                             '80:2A:A8:D1:08:95',
                             '80:2A:A8:D0:07:95',
                             '80:2A:A8:D2:07:95',
                         ])

    def test_fuzzy_boundaries(self):
        """
        If we hit a boundary, we wrap around so:
          FF + 1 == 00
          00 - 1 == FF

        I have no idea if this is actually what network manufacturers do
        in this case. I assume it'll break for somebody and they'll tell me.
        """
        self.assertEqual(sonos.fuzz('80:2A:A8:00:7F:FF'),
                         [
                             '80:2A:A8:00:7F:FE',
                             '80:2A:A8:00:7F:00',
                             '80:2A:A8:00:7E:FF',
                             '80:2A:A8:00:7F:FF',
                             '80:2A:A8:00:80:FF',
                             '80:2A:A8:FF:7F:FF',
                             '80:2A:A8:01:7F:FF',
                         ])

if __name__ == '__main__':
        unittest.main()

