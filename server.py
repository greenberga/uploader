import datetime
import html
import json
import re
from os import listdir, remove, environ
from os.path import join, basename
from sys import stdout, stderr

import requests
import boto3
from bottle import abort, post, request, run
from git import Repo
from PIL import Image
from PIL.ExifTags import TAGS as EXIF_TAGS
from requests.exceptions import RequestException


USERNAME = environ.get('MG_USER')
PASSWORD = environ.get('MG_PASS')
MG_API_KEY = environ.get('MG_API_KEY')
DRY = environ.get('DRY')
AUTH = ('api', MG_API_KEY)
BLOG_DOMAIN = environ.get('BLOG_DOMAIN')

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

BUCKET = environ.get('AWS_BUCKET')
s3 = None
git = None


class UploaderError(Exception):
    pass


def log(msg):
    now = datetime.datetime.now().strftime('%D %T')
    stdout.write('* [ {0} ] {1}\n'.format(now, msg))


def log_err(msg, err):
    now = datetime.datetime.now().strftime('%D %T')
    stderr.write('X [ {0} ] {1}\n'.format(now, msg))
    stderr.write('X {}\n'.format(' ' * (5 + len(now)) + str(err)))
    raise UploaderError


AUTHORIZED_SENDERS = re.compile(environ.get('AUTHORIZED_SENDERS_PATTERN'))

def is_authorized():
    sender = request.forms.get('from')
    return AUTHORIZED_SENDERS.match(sender) is not None


def parse_attachment(attachment):
    """
    Parses a Mailgun attachment string into a JSON object and extracts its
    URL, filename, and Content-Type.
    """

    attachment = json.loads(attachment)

    try:
        attachment = attachment[0]
    except IndexError as e:
        log_err('Couldn\'t find any attached files', e)

    return ( attachment['url'], attachment['name'], attachment['content-type'] )


def download_attachment(url, save_path):
    """
    Downloads a media attachment from Mailgun.

    Parameters
    ----------
    url: The string URL pointing to the attachment's location on Mailgun.
    save_path: A string location to save the downloaded attachment on disk.
    """

    try:
        response = requests.get(url, auth = AUTH, stream = True)
        response.raise_for_status()
        with open(save_path, 'wb') as f:
            for chunk in response:
                f.write(chunk)
    except RequestException as e:
        log_err('Failed to download attachment \'{}\''.format(url), e)


def get_new_oid():
    posts = listdir('blog/_posts')
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
        log('Deleting {0}'.format(path))
        if not DRY:
            try:
                remove(path)
            except OSError as e:
                err_msg = 'Error while attempting to delete \'{}\''.format(path)
                log_err(err_msg, e)


def upload_files(*file_paths):
    """
    Uploads files to the specified Amazon S3 bucket.
    """

    for path in file_paths:
        file_name = basename(path)
        log('Uploading {0} to Amazon S3'.format(path))
        if not DRY:
            with open(path, 'rb') as f:
                s3.Object(BUCKET, file_name).put(Body = f, ACL = 'public-read')


def format_summary(summary):
    """
    Formats a summary string, sanitizing special HTML characters and
    converting link patterns into actual anchor tags.
    """

    if not summary: return ''
    summary = html.escape(summary)
    summary = re.sub(
        r'(^|\W)/(\d+)',
        '\g<1><a href="http://{}/\g<2>">/\g<2></a>'.format(BLOG_DOMAIN),
        summary,
    )
    return '<span>{}</span>'.format(summary)


def make_post(oid, date, contents, summary):
    """
    Writes a Jekyll markdown post into the blog's _posts directory.

    Parameters
    ----------
    oid: The ID number of the new post.
    date: The date to use for tagging the post.
    contents: An <img/> or <video/> tag containing the main content of the post.
    summary: A string to be used for the caption of the post.
    """

    log('Writing post #{0}'.format(oid))

    today = datetime.date.today()

    if date is None:
        date = today
    else:
        date = datetime.datetime.strptime(date, '%Y-%m-%d')

    date = '{d:%B} {d.day}, {d:%Y}'.format(d = date)

    new_post_file_name = 'blog/_posts/{0}-{1}.md'.format(str(today), oid)

    summary = format_summary(summary)

    post_contents = r'''---
layout: post
---

<p>
  <time><a href="/{oid}">{date}</a></time>
  <a href="/{oid}">{contents}</a>{summary}
</p>
'''.format(oid = oid, date = date, contents = contents, summary = summary)

    if not DRY:
        with open(new_post_file_name, 'w') as f:
            f.write(post_contents)


def make_image_post(oid, summary, path):
    """
    Creates a new image post, resizing the original as necessary and uploading
    to S3. Also performs cleanup of temporary image files.

    Parameters
    ----------
    oid: The ID of the new image post.
    summary: A string summary to be used to caption the image.
    path: The path to the original, uploaded image file.
    """

    log('Making image post #{0}'.format(oid))

    try:
        img = Image.open(path)
    except (FileNotFoundError, OSError) as e:
        err_msg = 'Error while attempting to load \'{}\''.format(path)
        log_err(err_msg, e)

    meta = get_img_data(img)

    degree_to_rotate = ORIENTATIONS[meta.get('Orientation', 0)]
    if degree_to_rotate is not None:
        img = img.rotate(degree_to_rotate, expand = True)

    log('Resizing image #{0} ({1})'.format(oid, path))
    width, height = img.size
    larger_dimension = width if width > height else height
    scales = [ x / larger_dimension for x in [ 320.0, 640.0, 960.0, 1280.0 ] ]
    new_sizes = [ (round(width * s), round(height * s)) for s in scales ]
    new_files = [ '{0}-{1}.jpg'.format(oid, w) for w, h in new_sizes ]
    new_files = [ join(TEMP_PATH, f) for f in new_files ]

    if not DRY:
        for size, name in zip(new_sizes, new_files):
            resized = img.resize(size, Image.LANCZOS)
            resized.save(name)
            resized.close()

    img.close()

    # Upload resized images to S3.
    upload_files(*new_files)

    # Clean up temporary and local files.
    delete(path, *new_files)

    try:
        dt = meta['DateTime']
        dt = dt.split(' ')[0].replace(':', '-')
    except KeyError:
        dt = None

    new_file_names = [ basename(f) for f in new_files ]
    assets_url = '{{ site.assets_url }}'

    # Use the second-to-smallest file (new_file_names[1]) as the default.
    src = '{0}/{1}'.format(assets_url, new_file_names[1])

    widths = [ w for w, h in new_sizes ]
    srcset_data = zip(new_file_names, widths)
    srcset = [ '{0}/{1} {2}w'.format(assets_url, f, w) for f, w in srcset_data ]

    img = '<img src="{0}" '.format(src)
    img += 'srcset="{0}, {1}, {2}, {3}" '.format(*srcset)
    img += 'sizes="(min-width: 700px) 50vw, calc(100vw - 2rem)" '
    if summary:
        img += 'alt="{}" '.format(html.escape(summary))
    img += '/>'

    # Create the blog post and write it in the directory.
    make_post(oid, dt, img, summary)


def update_site(new_post_number):
    """
    Adds a new post and pushes the site to GitHub, where it will be republished.

    Parameters
    ----------
    new_post_number: The OID/number of the new post (used for logging and for
    generating the commit message.)
    """

    log('Uploading blog post #{0}'.format(new_post_number))

    if not DRY:
        git.add('_posts')
        git.commit('-m', 'Add post {0}'.format(new_post_number))
        git.push('origin', 'master')


@post('/upload')
def upload():

    if not is_authorized():
        abort(401)

    # Ensure the local blog copy is up to date.
    git.pull('origin', 'master')

    try:

        summary = request.forms.get('subject', '')
        file_url, file_name, file_type = parse_attachment(
            request.forms.get('attachments')
        )

        path = join(TEMP_PATH, file_name)

        download_attachment(file_url, path)

        new_oid = get_new_oid()

        if file_type.startswith('image'):
            make_image_post(new_oid, summary, path)
        else:
            log_err('Unsupported file type \'{0}\''.format(file_type))

        update_site(new_oid)

    except UploaderError:
        abort(500)


if __name__ == '__main__':

    # Initialize connection to AWS S3 and load the Git Repository object.
    s3 = boto3.resource('s3')
    git = Repo('blog').git

    log('Starting server')
    run(host = '0.0.0.0', port = 5678)
