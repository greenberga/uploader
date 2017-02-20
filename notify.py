import json
from os import environ, listdir, path

import requests

DRY = environ.get('DRY')
MG_URL = environ.get('MG_NOTIFICATIONS_URL')
MG_API_KEY = environ.get('MG_API_KEY')
AUTH = ('api', MG_API_KEY)
UPLOADER_DIR = path.dirname(path.realpath(__file__))

def compute_new_post_count():

    all_posts = listdir(path.join(UPLOADER_DIR, 'blog/_posts'))
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

    has, post, it = ('has', 'post', 'it') if new_count == 1 else ('have', 'posts', 'them')

    address = recipient['address']
    text_content = recipient['text'].format(n = new_count, has = has, post = post, it = it)
    html_content = recipient['html'].format(n = new_count, has = has, post = post, it = it)

    data = {
        'to': address,
        'from': environ.get('MG_FROM'),
        'subject': 'New photos on {}'.format(environ.get('BLOG_DOMAIN')),
        'text': text_content,
        'html': html_content,
        'h:Reply-To': environ.get('MG_REPLY_TO'),
    }

    if not DRY:
        response = requests.post(MG_URL, auth = AUTH, data = data)
        response.raise_for_status()

if __name__ == '__main__':

    new_post_count = compute_new_post_count()

    if new_post_count > 0:
        with open(path.join(UPLOADER_DIR, 'emails.json')) as f:
            emails = json.load(f)

        for recipient in emails['recipients']:
            send_update(recipient, new_post_count)
