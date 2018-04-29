import json
from os import environ, listdir, path
from configparser import ConfigParser

import requests

DRY = environ.get('DRY')

UPLOADER_DIR = path.dirname(path.realpath(__file__))

mode = environ.get('MODE', 'prod')
config = ConfigParser()
config.read(path.join(UPLOADER_DIR, 'config.ini'))
config = config[mode]

blog_path = config.get('blog-path', path.join(UPLOADER_DIR, 'blog'))

def compute_new_post_count():

    all_posts = listdir(path.join(blog_path, '_posts'))
    all_posts = [ int(p.split('.')[0].split('-')[-1]) for p in all_posts ]
    all_posts = sorted(all_posts)
    latest = all_posts[-1]

    with open(path.join(UPLOADER_DIR, 'latest.txt'), 'r+') as f:
        old_latest = int(f.read().strip())

        if not DRY:
            # Update 'latest.txt' with the new latest.
            f.seek(0)
            f.write(str(latest) + '\n')
            f.truncate()

    return latest - old_latest

def send_update(recipient, new_count):

    if new_count == 1:
        has, post, it = ('has', 'post', 'it')
    else:
        has, post, it = ('have', 'posts', 'them')

    address = recipient['address']
    text_content = recipient['text'].format(
        n = new_count,
        has = has,
        post = post,
        it = it,
    )
    html_content = recipient['html'].format(
        n = new_count,
        has = has,
        post = post,
        it = it,
    )

    data = {
        'to': address,
        'from': config['mailgun-from'],
        'subject': 'New photos on {}'.format(config['domain']),
        'text': text_content,
        'html': html_content,
        'bcc': config['mailgun-bcc'],
        'h:Reply-To': config['mailgun-reply-to'],
    }

    print('Sending update to %s' % address)

    if not DRY:
        response = requests.post(
            config['mailgun-notifications-url'],
            auth = ('api', config['mailgun-key']),
            data = data,
        )
        response.raise_for_status()

if __name__ == '__main__':

    new_post_count = compute_new_post_count()

    if new_post_count > 0:
        with open(path.join(UPLOADER_DIR, 'emails.json')) as f:
            emails = json.load(f)

        for recipient in emails['recipients']:
            send_update(recipient, new_post_count)

        print('Updates sent successfully')
