import datetime
import hmac
import html
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
from PIL import Image, ImageOps
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


def get_img_date(img):
    """
    Attempts to get the date the image's was captured.

    Parameters
    ----------
    img: A PIL Image object.

    Returns
    -------
    A date string or None, if the date can't be retrieved.
    """

    # Certain image files do not contain EXIF data, and `_getexif()` calls
    # raise an `AttributeError`. If this happens, just return an empty dict.
    try:
        img_exif = img.getexif()
        md = {
            EXIF_TAGS[k]: v for k, v in img_exif.items() if k in EXIF_TAGS
        }
    except AttributeError:
        md = {}

    if 'DateTime' in md:
        y, m, d = md['DateTime'].split(' ')[0].split(':')
        m = m.lstrip('0')
        d = d.lstrip('0')
        return '/'.join([m, d, y])


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
                    ContentType = 'image/jpeg',
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


def resize_image(img):
    """
    Resizes an image into four different sizes.

    Parameters
    ----------
    img: A `PIL.Image` to be resized.

    Returns
    -------
    A list of four resized `PIL.Image`s.
    """

    width, height = img.size
    larger_dimension = width if width > height else height
    scales = [ x / larger_dimension for x in [ 320.0, 640.0, 960.0, 1280.0 ] ]
    new_sizes = [ (round(width * s), round(height * s)) for s in scales ]
    return [ img.resize(size, Image.Resampling.LANCZOS) for size in new_sizes ]


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
    img_tag = '<img '
    img_tag += 'alt="{{ page.summary }}" ' if summary else ''
    img_tag += 'sizes="(min-width: 700px) 50vw, calc(100vw - 2rem)" '
    img_tag += 'src="{0}" '.format(src)
    img_tag += 'srcset="{0}, {1}, {2}, {3}" '.format(*srcset)
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

    # Attempt to extract the date the image was captured from the metadata.
    # This must be done BEFORE the next step, which seems to remove EXIF data.
    date = get_img_date(img)
    if date is not None:
        post_object['taken'] = date

    img = ImageOps.exif_transpose(img).convert('RGB')

    logging.info('Resizing image #%s' % oid)

    # 1. Get list of resized `Image`s.
    resized = resize_image(img)

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
    post_object['content'] = create_img_tag(oid, widths, post_object['summary'], date)


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

    lines = [
        '---',
        'layout: post',
        "summary: '%s'" % (post_object['summary'] or 'Post #%d' % oid)
    ]

    if 'og_image' in post_object:
        lines.append('og_image: %s' % post_object['og_image'])

    if 'taken' in post_object:
        figure = '<figure data-taken="%s">' % post_object['taken']
    else:
        figure = '<figure>'

    lines.extend([
        '---',
        '',
        '<div class="post">',
        '  <time>',
        '    <a href="/%s">' % oid,
        '      {{ page.date | date: "%B %-d, %Y" }}',
        '    </a>',
        '  </time>',
        '  <a href="/%s">' % oid,
        '    %s' % figure,
        '      %s' % post_object['content'],
        '    </figure>',
        '  </a>',
    ])

    summary = post_object['summary']
    if summary:
        lines.extend([
            '  <span>',
            '    %s' % autolink_posts(summary),
            '  </span>',
        ])

    lines.extend([ '</div>', '' ])
    contents = '\n'.join(lines)

    logging.debug(contents)

    file_name = join(blog_path, '_posts/{0}-{1}.md'.format(str(datetime.date.today()), oid))
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

        process_image(post_object, file_object)

        create_post(post_object)

        update_site(new_oid)

    except Exception as e:
        logging.exception(e)
        abort(500)


if __name__ == '__main__':
    logging.info('Starting server')
    run(host = config.get('host', 'localhost'), port = config.get('port', 8080))
