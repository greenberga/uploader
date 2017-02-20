import os

def setup():
    os.environ['BLOG_DOMAIN'] = 'foo.bar'
    os.environ['AUTHORIZED_SENDERS_PATTERN'] = 'email@add.rs'

def teardown():
    del os.environ['BLOG_DOMAIN']
    del os.environ['AUTHORIZED_SENDERS_PATTERN']

def test_format_summary():

    from server import format_summary

    s = 'Pic of Joe, see /644'
    e = '<span>Pic of Joe, see <a href="http://foo.bar/644">/644</a></span>'
    assert format_summary(s) == e
    assert format_summary(s, convert_links = False) == '<span>' + s + '</span>'

    s = 'Cool pic, <3 //6'
    e = '<span>Cool pic, &lt;3 //6</span>'
    assert format_summary(s) == e
    assert format_summary(s, convert_links = False) == e

    s = 'A pic, /s'
    e = '<span>' + s + '</span>'
    assert format_summary(s) == e
    assert format_summary(s, convert_links = False) == e

    s = 'This pic is 10/10!'
    e = '<span>' + s + '</span>'
    assert format_summary(s) == e
    assert format_summary(s, convert_links = False) == e

    s = '/164 is similar'
    e = '<span><a href="http://foo.bar/164">/164</a> is similar</span>'
    assert format_summary(s) == e
    assert format_summary(s, convert_links = False) == '<span>' + s + '</span>'
