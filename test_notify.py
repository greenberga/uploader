import os
import unittest
from unittest.mock import Mock, mock_open, patch

MODE = 'test'
old_mode = os.environ.get('MODE', None)
os.environ['MODE'] = MODE

from notify import compute_new_post_count, send_update, config

old_config_notify_bcc = config.get(MODE, 'notify-bcc', fallback=None)

def tearDownModule():
    if old_mode:
        os.environ['MODE'] = old_mode
    else:
        del os.environ['MODE']

def build_request_body(text_value, html_value):
    return {
        'personalizations': [
            {
                'to': [
                    {
                        'email': 'a@b.com',
                    },
                ],
                'subject': 'New photos on foo.bar',
            },
        ],
        'from': {
            'email': 'from@foo.bar',
            'name': 'From Name',
        },
        'reply_to': {
            'email': 'replies@foo.bar',
        },
        'content': [
            {
                'type': 'text/plain',
                'value': text_value,
            },
            {
                'type': 'text/html',
                'value': html_value,
            },
        ],
    }

class TestNotify(unittest.TestCase):

    def tearDown(self):
        if old_config_notify_bcc:
            config.set(MODE, 'notify-bcc', old_config_notify_bcc)
        else:
            config.remove_option(MODE, 'notify-bcc')

    @patch('notify.listdir', Mock(return_value = [
        '2022-11-04-0.md',
        '2022-11-14-1.md',
        '2022-11-22-2.md',
    ]))
    def test_compute_new_post_count(self):
        with patch('notify.open', mock_open(read_data = '0\n')) as mocked_open:
            self.assertEqual(compute_new_post_count(), 2)
            handle = mocked_open()
            handle.write.assert_called_once_with('2\n')

    @patch('requests.post')
    def test_send_update_one_new(self, requests_post):
        recipient = {
            'address': 'a@b.com',
            'text': '{it} {has} {n} {post}',
            'html': '{n} {post} {it} {has}',
        }

        send_update(recipient, 1)

        requests_post.assert_called_once_with(
            'https://notify.com/',
            headers = {
                'Content-Type': 'application/json',
                'Authorization': 'Bearer keykeydeliveryservice',
            },
            json = build_request_body('it has 1 post', '1 post it has'),
        )

    @patch('requests.post')
    def test_send_update_multiple_new(self, requests_post):
        recipient = {
            'address': 'a@b.com',
            'text': '{it} {has} {n} {post}',
            'html': '{n} {post} {it} {has}',
        }

        send_update(recipient, 5000)

        requests_post.assert_called_once_with(
            'https://notify.com/',
            headers = {
                'Content-Type': 'application/json',
                'Authorization': 'Bearer keykeydeliveryservice',
            },
            json = build_request_body('them have 5000 posts', '5000 posts them have'),
        )

    @patch('requests.post')
    def test_send_update_config_bcc(self, requests_post):
        bcc = 'config@b.cc'
        config.set(MODE, 'notify-bcc', bcc)

        recipient = {
            'address': 'a@b.com',
            'text': '{it} {has} {n} {post}',
            'html': '{n} {post} {it} {has}',
        }

        send_update(recipient, 1)

        body = build_request_body('it has 1 post', '1 post it has')
        body['personalizations'][0]['bcc'] = [{ 'email': bcc }]

        requests_post.assert_called_once_with(
            'https://notify.com/',
            headers = {
                'Content-Type': 'application/json',
                'Authorization': 'Bearer keykeydeliveryservice',
            },
            json = body,
        )

    @patch('requests.post')
    def test_send_update_recipient_bcc(self, requests_post):
        bcc = 'recipient@b.cc'

        recipient = {
            'address': 'a@b.com',
            'text': '{it} {has} {n} {post}',
            'html': '{n} {post} {it} {has}',
            'bcc': bcc,
        }

        send_update(recipient, 1)

        body = build_request_body('it has 1 post', '1 post it has')
        body['personalizations'][0]['bcc'] = [{ 'email': bcc }]

        requests_post.assert_called_once_with(
            'https://notify.com/',
            headers = {
                'Content-Type': 'application/json',
                'Authorization': 'Bearer keykeydeliveryservice',
            },
            json = body,
        )

    @patch('requests.post')
    def test_send_update_both_bcc(self, requests_post):
        config_bcc = 'config@b.cc'
        config.set(MODE, 'notify-bcc', config_bcc)

        recipient_bcc = 'recipient@b.cc'
        recipient = {
            'address': 'a@b.com',
            'text': '{it} {has} {n} {post}',
            'html': '{n} {post} {it} {has}',
            'bcc': recipient_bcc,
        }

        send_update(recipient, 1)

        body = build_request_body('it has 1 post', '1 post it has')
        body['personalizations'][0]['bcc'] = [{ 'email': recipient_bcc }]

        requests_post.assert_called_once_with(
            'https://notify.com/',
            headers = {
                'Content-Type': 'application/json',
                'Authorization': 'Bearer keykeydeliveryservice',
            },
            json = body,
        )
