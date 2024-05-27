import datetime
import json
import logging
import os
import unittest
from unittest.mock import patch, mock_open, Mock, call, DEFAULT

from PIL import Image

old_mode = os.environ.get('MODE', None)
os.environ['MODE'] = 'test'

from server import (
    is_authorized,
    get_new_oid,
    get_img_date,
    delete,
    upload_files,
    autolink_posts,
    resize_image,
    create_img_tag,
    process_image,
    create_post,
)

def setUpModule():
    logging.disable(logging.CRITICAL)

def tearDownModule():
    logging.disable(logging.NOTSET)

    if old_mode:
        os.environ['MODE'] = old_mode
    else:
        del os.environ['MODE']

class TestServer(unittest.TestCase):

    def test_is_authorized(self):
        SPECS = [
            (('First Last <email@add.rs>', 'yodelist', 'blastocyte'), True),
            (('failure@add.rs', 'yodelist', 'blastocyte'), False),
            (('Cool Name <email@add.rs>', 'failure', 'blastocyte'), False),
            (('email@add.rs', 'yodelist', 'failure'), False),
        ]

        for args, expected in SPECS:
            e, u, p = args
            request = Mock()
            request.params = { 'from': e }
            request.auth = (u, p)
            self.assertEqual(is_authorized(request), expected)


    @patch('server.listdir', Mock(return_value = [
        '2012-05-15-0.md',
        '2016-11-02-1.md',
        '2017-01-16-3.md',
    ]))
    def test_get_new_oid(self):
        self.assertEqual(get_new_oid(), 4)

    @patch('server.listdir', Mock(return_value = []))
    def test_get_new_oid_first_post(self):
        self.assertEqual(get_new_oid(), 0)

    def test_get_img_date(self):
        img = Mock()
        img.getexif = Mock(return_value = { 306: '2015:04:02' })
        d = get_img_date(img)
        self.assertEqual(d, '4/2/2015')

    def test_get_img_date_no_date(self):
        img = Mock()
        img.getexif = Mock(return_value = {})
        exif = get_img_date(img)
        self.assertIsNone(exif)

    def test_get_img_date_no_exif(self):
        img = Mock()
        img.getexif = Mock(side_effect = AttributeError)
        exif = get_img_date(img)
        self.assertIsNone(exif)

    @patch('server.remove')
    def test_delete(self, remove):
        delete('1', '2', '3')
        self.assertEqual(remove.call_args_list, [ call('1'), call('2'), call('3') ])

    @patch('server.remove', Mock(side_effect = OSError))
    def test_delete_error(self):
        with self.assertRaises(OSError):
            delete('os error')


    @patch('server.open', mock_open(), create = True)
    @patch('botocore.client.BaseClient._make_api_call')
    def test_upload_files(self, put_object):
        files = [ '/tmp/a.jpg', '/tmp/b.jpg', '/tmp/c.jpg' ]
        upload_files(*files)
        for i, f in enumerate(files):
            op, args = put_object.call_args_list[i][0]
            self.assertEqual(op, 'PutObject')

            # Ignore the 'Body' arg, which is a `MagicMock` object.
            del args['Body']

            self.assertEqual(args, {
                'Bucket': 'aws.bucket',
                'Key': os.path.basename(f),
                'ACL': 'public-read',
                'ContentType': 'image/jpeg',
            })

    def test_autolink_posts(self):

        specs = {
            'Pic of Joe, see /644': 'Pic of Joe, see <a href="http://foo.bar/644">/644</a>',
            'Cool pic, <3 //6': 'Cool pic, <3 /<a href="http://foo.bar/6">/6</a>',
            'A pic, /s': 'A pic, /s',
            'This pic is 10/10!': 'This pic is 10/10!',
            '/164 is similar': '<a href="http://foo.bar/164">/164</a> is similar',
            '(/322,/333)': '(<a href="http://foo.bar/322">/322</a>,<a href="http://foo.bar/333">/333</a>)',
        }

        for summary, expected in specs.items():
            self.assertEqual(autolink_posts(summary), expected)

    def test_resize_image(self):

        img = Image.new('RGBA', size = (1600, 1200))
        resized = resize_image(img)
        self.assertEqual(len(resized), 4)
        self.assertEqual(resized[0].size, (320, 240))
        self.assertEqual(resized[1].size, (640, 480))
        self.assertEqual(resized[2].size, (960, 720))
        self.assertEqual(resized[3].size, (1280, 960))


    def test_create_image_tag(self):

        SPECS = [
            (
                ( 777, [ 300, 500, 700, 900 ], '', '5/24/2024' ),
                '<img data-taken="5/24/2024" sizes="(min-width: 700px) 50vw, calc(100vw - 2rem)" src="{{ site.assets_url }}/777-500.jpg" srcset="{{ site.assets_url }}/777-300.jpg 300w, {{ site.assets_url }}/777-500.jpg 500w, {{ site.assets_url }}/777-700.jpg 700w, {{ site.assets_url }}/777-900.jpg 900w" />',
            ),
            (
                ( 888, [ 200, 400, 600, 800 ], 'Summary', None ),
                '<img alt="{{ page.summary }}" sizes="(min-width: 700px) 50vw, calc(100vw - 2rem)" src="{{ site.assets_url }}/888-400.jpg" srcset="{{ site.assets_url }}/888-200.jpg 200w, {{ site.assets_url }}/888-400.jpg 400w, {{ site.assets_url }}/888-600.jpg 600w, {{ site.assets_url }}/888-800.jpg 800w" />',
            ),
        ]

        for args, expected in SPECS:
            self.assertEqual(create_img_tag(*args), expected)

    @patch('PIL.Image.open')
    @patch.multiple(
        'server',
        create_img_tag = DEFAULT,
        upload_files = DEFAULT,
        delete = DEFAULT,
        resize_image = DEFAULT,
    )
    def test_process_image(
        self,
        Image_open,
        resize_image,
        delete,
        upload_files,
        create_img_tag,
    ):

        # Setup

        resized = [
            Mock(size = (150, 100)),
            Mock(size = (200, 300)),
            Mock(size = (300, 450)),
            Mock(size = (500, 750)),
        ]
        resize_image.return_value = resized

        create_img_tag.return_value = '<img src="111.jpg" />'

        # Call

        post_object = { 'oid': 111, 'summary': 'Hi hello' }
        process_image(post_object, '/path/to/file.jpg')

        # Assert

        Image_open.assert_called_once_with('/path/to/file.jpg')

        kwargs = { 'optimize': True, 'progressive': True }
        resized[0].save.assert_called_once_with('/tmp/111-150.jpg', **kwargs)
        resized[1].save.assert_called_once_with('/tmp/111-200.jpg', **kwargs)
        resized[2].save.assert_called_once_with('/tmp/111-300.jpg', **kwargs)
        resized[3].save.assert_called_once_with('/tmp/111-500.jpg', **kwargs)

        upload_files.assert_called_once_with(
            '/tmp/111-150.jpg',
            '/tmp/111-200.jpg',
            '/tmp/111-300.jpg',
            '/tmp/111-500.jpg',
        )

        delete.assert_called_once_with(
            '/tmp/111-150.jpg',
            '/tmp/111-200.jpg',
            '/tmp/111-300.jpg',
            '/tmp/111-500.jpg',
        )

        self.assertEqual(post_object, {
            'oid': 111,
            'summary': 'Hi hello',
            'og_image': '111-500.jpg',
            'content': '<img src="111.jpg" />',
        })

    def test_create_post(self):

        today = datetime.datetime.today()
        today_str = today.isoformat().split('T')[0]

        SPECS = [
            (
                {
                    'oid': 872,
                    'date': '1992-11-16',
                    'summary': 'Apples &amp; Bananas',
                    'og_image': '872-1280.jpg',
                    'content': '<img src="872-1280.jpg" />',
                },
                '\n'.join([
                    '---',
                    'layout: post',
                    "summary: 'Apples &amp; Bananas'",
                    'og_image: 872-1280.jpg',
                    '---',
                    '',
                    '<p>',
                    '  <time>',
                    '    <a href="/872">',
                    '      {{ page.date | date: "%B %-d, %Y" }}',
                    '    </a>',
                    '  </time>',
                    '  <a href="/872">',
                    '    <img src="872-1280.jpg" />',
                    '  </a>',
                    '  <span>Apples &amp; Bananas</span>',
                    '</p>',
                    '',
                ])
            ),
            (
                {
                    'oid': 431,
                    'date': '2004-01-31',
                    'summary': '',
                    'content': '<img src="431-960.jpg" />',
                },
                '\n'.join([
                    '---',
                    'layout: post',
                    "summary: 'Post #431'",
                    '---',
                    '',
                    '<p>',
                    '  <time>',
                    '    <a href="/431">',
                    '      {{ page.date | date: "%B %-d, %Y" }}',
                    '    </a>',
                    '  </time>',
                    '  <a href="/431">',
                    '    <img src="431-960.jpg" />',
                    '  </a>',
                    '</p>',
                    '',
                ])
            ),
        ]

        for post_object, expected in SPECS:
            with patch('server.open', mock_open(), create = True) as m:
                oid = post_object['oid']
                post_path = 'blog/_posts/%s-%d.md' % ( today_str, oid )
                post_path = os.path.join(os.getcwd(), post_path)
                create_post(post_object)
                m.assert_called_once_with(post_path, 'w')
                handle = m()
                handle.write.assert_called_once_with(expected)
