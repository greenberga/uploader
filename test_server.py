import os
from nose.tools import ok_

def setup():
    os.environ['BLOG_DOMAIN'] = 'foo.bar'
    os.environ['AUTHORIZED_SENDERS_PATTERN'] = 'email@add.rs'

def teardown():
    del os.environ['BLOG_DOMAIN']
    del os.environ['AUTHORIZED_SENDERS_PATTERN']

def test_format_summary():

    from server import format_summary

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
