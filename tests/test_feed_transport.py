import ipaddress
import unittest
from unittest.mock import MagicMock,patch
from app import feeds


class FeedTransportTest(unittest.TestCase):
 def connection(self,status=200,chunks=None):
  connection=MagicMock()
  response=connection.getresponse.return_value
  response.status=status
  response.read1.side_effect=chunks or [b'BEGIN:VCALENDAR\nEND:VCALENDAR',b'']
  return connection

 def test_redirects_are_refused_without_following(self):
  conn=self.connection(302)
  with patch.object(feeds,'public_address',return_value=ipaddress.ip_address('8.8.8.8')),patch.object(feeds,'PinnedHTTPSConnection',return_value=conn):
   with self.assertRaisesRegex(feeds.FeedError,'redirects are not followed'):
    feeds.fetch_https('https://example.test/private')
  self.assertEqual(conn.request.call_count,1)
  conn.close.assert_called_once()

 def test_size_cap_and_wall_clock_deadline_close_connection(self):
  for timed in (False,True):
   conn=self.connection(chunks=[b'x'*(feeds.MAX_BYTES+1)])
   clock=[0,0,11] if timed else [0,0,0]
   with self.subTest(timed=timed),patch.object(feeds,'public_address',return_value=ipaddress.ip_address('8.8.8.8')),patch.object(feeds,'PinnedHTTPSConnection',return_value=conn),patch.object(feeds.time,'monotonic',side_effect=clock):
    with self.assertRaises(feeds.FeedError):feeds.fetch_https('https://example.test/private')
   conn.close.assert_called_once()

 def test_private_dns_answer_is_refused_before_connection(self):
  with patch.object(feeds.socket,'getaddrinfo',return_value=[(2,1,6,'',('10.0.0.1',443))]),patch.object(feeds,'PinnedHTTPSConnection') as connection:
   with self.assertRaises(feeds.FeedError):feeds.fetch_https('https://example.test/private')
   connection.assert_not_called()

 def test_invalid_port_error_never_reflects_secret_text(self):
  with self.assertRaises(ValueError) as error:
   feeds.validate_url('https://example.test:SECRET-FEED-TOKEN/private')
  self.assertNotIn('SECRET',str(error.exception))
