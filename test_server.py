import datetime
import os
from unittest.mock import patch, mock_open

from nose.tools import ok_

old_mode = os.environ.get('MODE', None)
os.environ['MODE'] = 'test'

from server import format_summary, make_post

def teardown():
    if old_mode:
        os.environ['MODE'] = old_mode
    else:
        del os.environ['MODE']

def test_format_summary():

    specs = {
        'Pic of Joe, see /644': '<span>Pic of Joe, see <a href="http://foo.bar/644">/644</a></span>',
        'Cool pic, <3 //6': '<span>Cool pic, &lt;3 /<a href="http://foo.bar/6">/6</a></span>',
        'A pic, /s': '<span>A pic, /s</span>',
        'This pic is 10/10!': '<span>This pic is 10/10!</span>',
        '/164 is similar': '<span><a href="http://foo.bar/164">/164</a> is similar</span>',
        '(/322,/333)': '<span>(<a href="http://foo.bar/322">/322</a>,<a href="http://foo.bar/333">/333</a>)</span>',
    }

    for summary, expected in specs.items():
        yield ok_, format_summary(summary), expected

def test_make_post():

    today = datetime.date.today()
    str_today = str(today)
    nice_today = '{d:%B} {d.day}, {d:%Y}'.format(d = today)

    specs = [

        # WITH NO PASSED DATE OR SUMMARY
        (
            ('123', None, 'POSTCONTENT', None),
            'blog/_posts/%s-123.md' % str_today,
            r'''---
layout: post
---

<p>
  <time><a href="/123">%s</a></time>
  <a href="/123">POSTCONTENT</a>
</p>
''' % nice_today,
        ),

        # WITH PASSED DATE
        (
            ('234', '2017-03-27', 'POSTCONTENT', None),
            'blog/_posts/%s-234.md' % str_today,
            r'''---
layout: post
---

<p>
  <time><a href="/234">March 27, 2017</a></time>
  <a href="/234">POSTCONTENT</a>
</p>
''',
        ),

        # WITH PASSED SUMMARY
        (
            ('123', None, 'POSTCONTENT', 'A post about content'),
            'blog/_posts/%s-123.md' % str_today,
            r'''---
layout: post
---

<p>
  <time><a href="/123">%s</a></time>
  <a href="/123">POSTCONTENT</a><span>A post about content</span>
</p>
''' % nice_today,
        ),

    ]

    for args, expected_filename, expected_content in specs:
        yield check_make_post, args, expected_filename, expected_content

def check_make_post(args, expected_filename, expected_content):
    m = mock_open()
    with patch(make_post.__module__ + '.open', m, create = True):
        make_post(*args)
        m.assert_called_once_with(expected_filename, 'w')
        handle = m()
        handle.write.assert_called_once_with(expected_content)
