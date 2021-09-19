import datetime
import hmac
import html
import json
import logging
import re
import time
from contextlib import contextmanager
from configparser import ConfigParser
from email.utils import parseaddr
from os import listdir, remove, environ, getcwd, chdir
from os.path import join, basename, dirname, realpath

import boto3
from bottle import abort, post, request, run
from git import Repo
from PIL import Image
from PIL.ExifTags import TAGS as EXIF_TAGS

uploader_dirpath = dirname(realpath(__file__))
rel = lambda f: join(uploader_dirpath, f)

@contextmanager
def pushd(where):
    start_dir = getcwd()
    chdir(where)
    yield
    chdir(start_dir)

mode = environ.get('MODE', 'prod')
config = ConfigParser()
config.read(rel('config.ini'))
config = config[mode]

DRY = environ.get('DRY')

logging.basicConfig(
    format = '[%(levelname)s] (%(name)s) %(message)s',
    level = logging.DEBUG if DRY else logging.INFO,
)

S3 = boto3.client(
    's3',
    aws_access_key_id = config['aws-access-key-id'],
    aws_secret_access_key = config['aws-secret-access-key'],
)

blog_path = config.get('blog-path', rel('blog'))
git = Repo(blog_path).git if mode == 'prod' else None

ORIENTATIONS = [
    None,
    None,
    None,
    -180,
    None,
    None,
    -90,
    None,
    -270,
]

TEMP_PATH = '/tmp'


authorized_senders = re.compile(config['authorized-senders-pattern'])
def is_authorized(request):
    _, email = parseaddr(request.params.get('from'))
    sender_authorized = authorized_senders.match(email) is not None
    user_authorized = hmac.compare_digest(request.auth[0], config['sendgrid-user'])
    pass_authorized = hmac.compare_digest(request.auth[1], config['sendgrid-pass'])
    return sender_authorized and user_authorized and pass_authorized


def get_new_oid():
    posts = listdir(join(blog_path, '_posts'))

    if len(posts) == 0:
        return 0

    sorted_oids = sorted([ int(p.split('.')[0].split('-')[-1]) for p in posts ])
    return sorted_oids[-1] + 1


def get_img_data(img):
    """
    Gets an image's EXIF metadata.

    Parameters
    ----------
    img: A PIL Image object.

    Returns
    -------
    A dictionary keyed by EXIF tags with their data as the values.
    """

    # Certain image files do not contain EXIF data, and `_getexif()` calls
    # raise an `AttributeError`. If this happens, just return an empty dict.
    try:
        img_exif = img._getexif()
        return {
            EXIF_TAGS[k]: v for k, v in img_exif.items() if k in EXIF_TAGS
        }
    except AttributeError:
        return {}


def delete(*paths):
    """
    Gathers its arguments into a list of file paths and deletes them.
    """

    for path in paths:
        logging.info('Deleting {0}'.format(path))
        if not DRY:
            remove(path)


def upload_files(*file_paths):
    """
    Uploads files to the specified Amazon S3 bucket.
    """

    for path in file_paths:
        file_name = basename(path)
        logging.info('Uploading {0} to Amazon S3'.format(path))
        if not DRY:
            with open(path, 'rb') as f:
                S3.put_object(
                    Bucket = config['aws-bucket'],
                    Key = file_name,
                    Body = f,
                    ACL = 'public-read',
                )


def autolink_posts(text):
    """
    Searches a string of text for substrings that look like posts (/XXX) and
    replaces them with <a> tags to the specified post.
    """

    if not text: return ''
    return re.sub(
        r'(^|\W)/(\d+)',
        '\g<1><a href="http://{}/\g<2>">/\g<2></a>'.format(config['domain']),
        text,
    )


def resize_image(img, metadata):
    """
    Resizes an image into four different sizes.

    Parameters
    ----------
    img: A `PIL.Image` to be resized.
    metadata: A dictionary of EXIF data for the image. Used to determine the
    image's orientation, because it might need to be rotated.

    Returns
    -------
    A list of four resized `PIL.Image`s.
    """

    degree_to_rotate = ORIENTATIONS[metadata.get('Orientation', 0)]
    if degree_to_rotate is not None:
        img = img.rotate(degree_to_rotate, expand = True)

    width, height = img.size
    larger_dimension = width if width > height else height
    scales = [ x / larger_dimension for x in [ 320.0, 640.0, 960.0, 1280.0 ] ]
    new_sizes = [ (round(width * s), round(height * s)) for s in scales ]
    return [ img.resize(size, Image.LANCZOS) for size in new_sizes ]


def create_img_tag(oid, widths, summary):
    """
    Creates an HTML <img> tag for an image post. Uses the OID, widths, and
    optional summary for the different components of the tag.

    Parameters
    ----------
    oid: A number representing the OID of the <img>'s associated post.
    widths: A list of numbers representing each width of the image.
    summary: A summary image that, if truthy, will cause an "alt" attribute to
    be added to the tag.

    Returns
    -------
    A string <img> tag.
    """

    assets_url = '{{ site.assets_url }}'

    # Use the second-to-smallest file (widths[1]) as the default.
    src = '%s/%d-%d.jpg' % (assets_url, oid, widths[1])
    srcset = [ '%s/%d-%d.jpg %dw' % (assets_url, oid, w, w) for w in widths ]
    img_tag = '<img src="{0}" '.format(src)
    img_tag += 'srcset="{0}, {1}, {2}, {3}" '.format(*srcset)
    img_tag += 'sizes="(min-width: 700px) 50vw, calc(100vw - 2rem)" '
    img_tag += 'alt="{{ page.summary }}" ' if summary else ''
    img_tag += '/>'

    return img_tag

def process_image(post_object, img_obj):
    """
    Processes an uploaded image file, extract information from it to generate
    a post.

    Parameters
    ----------
    post_object: A dictionary of post data that will be updated.
    img_obj: A bottle FileUpload object representing the uploaded file.
    """

    oid = post_object['oid']

    logging.info('Making image post #%s' % oid)

    img = Image.open(img_obj)

    metadata = get_img_data(img)

    # Attempt to extract the date the image was captured from the metadata.
    if 'DateTime' in metadata:
        dt = metadata['DateTime']
        post_object['date'] = dt.split(' ')[0].replace(':', '-')

    logging.info('Resizing image #%s' % oid)

    # 1. Get list of resized `Image`s.
    resized = resize_image(img, metadata)

    # 2. Make a list of their widths.
    widths = [ r.size[0] for r in resized ]

    # 3. Save them as {oid}-{width}.jpg in a temporary location.
    new_files = [ join(TEMP_PATH, '%d-%d.jpg' % (oid, w)) for w in widths ]
    for r, f in zip(resized, new_files):
        r.save(f, optimize = True, progressive = True)
        r.close()

    img.close()

    # Upload resized images to S3.
    upload_files(*new_files)

    # Clean up temporary files.
    delete(*new_files)

    # Use the largest of the resized images for the OpenGraph image meta tag.
    post_object['og_image'] = '%d-%d.jpg' % (oid, max(widths))
    post_object['content'] = create_img_tag(oid, widths, post_object['summary'])


def create_post(post_object):
    """
    Converts a post object dictionary into an actual post and writes it
    to a file.

    Parameters
    ----------
    post_object: A dictionary of data for the post. Includes things like OID,
    content, summary, date, etc.
    """

    oid = post_object['oid']

    logging.info('Writing post #{0}'.format(oid))

    today = datetime.date.today()

    if 'date' in post_object:
        date = datetime.datetime.strptime(post_object['date'], '%Y-%m-%d')
    else:
        date = today

    date_str = '{d:%B} {d.day}, {d:%Y}'.format(d = date)

    lines = [
        '---',
        'layout: post',
        "summary: '%s'" % (post_object['summary'] or 'Post #%d' % oid)
    ]

    if 'og_image' in post_object:
        lines.append('og_image: %s' % post_object['og_image'])

    lines.extend([
        '---',
        '',
        '<p>',
        '  <time>',
        '    <a href="/%s">%s</a>' % (oid, date_str),
        '  </time>',
        '  <a href="/%s">' % oid,
        '    %s' % post_object['content'],
        '  </a>',
    ])

    summary = post_object['summary']
    if summary:
        lines.append('  <span>%s</span>' % autolink_posts(summary))

    lines.extend([ '</p>', '' ])
    contents = '\n'.join(lines)

    # Not sure why, but seems I have to double-decode strings?
    # And this makes the text look right, as opposed to gibberish.
    contents = contents.encode('raw_unicode_escape').decode('utf-8')

    logging.debug(contents)

    file_name = join(blog_path, '_posts/{0}-{1}.md'.format(str(today), oid))
    if not DRY:
        with open(file_name, 'w') as f:
            f.write(contents)

def update_site(new_post_number):
    """
    Adds a new post and pushes the site to GitHub, where it will be republished.

    Parameters
    ----------
    new_post_number: The OID/number of the new post (used for logging and for
    generating the commit message.)
    """

    logging.info('Uploading blog post #{0}'.format(new_post_number))

    if not DRY:
        with pushd(uploader_dirpath):
            git.add('_posts')
            git.commit('-m', 'Add post {0}'.format(new_post_number))
            git.push('origin', 'master')


@post('/upload')
def upload():

    if request.auth is None:
        logging.info('No webhook request auth provided')
        abort(401)

    if not is_authorized(request):
        logging.info('Unauthorized request to /upload')
        abort(403)

    # Ensure the local blog copy is up to date.
    with pushd(uploader_dirpath):
        git.pull('origin', 'master') if not DRY else None

    try:

        post_object = {}

        new_oid = get_new_oid()
        post_object['oid'] = new_oid

        summary = request.params.get('subject', '')
        post_object['summary'] = html.escape(summary)

        file_object = request.files.attachment1.file
        file_type = json.loads(request.params['attachment-info'])['attachment1']['type']

        # This section creates the main content for the post, based on the
        # type of uploaded file. The `process_<type>` functions update the
        # `post_object` with values that will be used to write the post,
        # but also perform side effects (like resizing, uploading, etc.)
        if file_type.startswith('image'):
            process_image(post_object, file_object)

        create_post(post_object)

        update_site(new_oid)

    except Exception as e:
        logging.exception(e)
        abort(500)


if __name__ == '__main__':
    logging.info('Starting server')
    run(host = config.get('host', 'localhost'), port = config.get('port', 8080))
