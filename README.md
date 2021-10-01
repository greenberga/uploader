# Uploader

Code for a web server that facilitates uploading emailed photos to a website.
I have a site where I post photos. It used to be hosted on Tumblr, but then
Tumblr stopped allowing post-by-email. Now the site is hosted on GitHub Pages
and I built this application to allow post-by-email.

The server listens for webhooks from [SendGrid](https://www.sendgrid.com/). When
it receives a notification that an email was received, it downloads the
attached photo (and some metadata), resizes it, creates a new post on the
GitHub Pages site's repository, and pushes it (which republishes the website.)

It's implemented in Python using [Bottle](https://bottlepy.org/docs/dev/).

## Testing

```
nosetests --with-coverage --cover-package=server --cover-erase --cover-html
```

## Setting up email notifications

You can run a [script](notify.py) that sends emails to notify subscribers of new
posts. Each time it runs, it calculates the number of new posts by comparing the
ID of the *current* latest post to the ID of the latest post from the *last time*
it ran (which it stores&mdash;and updates&mdash;in a file named `latest.txt`.) I
run it weekly, using `cron`. To set it up,

#### 1. Create `latest.txt`

Find the ID of the current latest post on your site. You can go to your site and
click on the first post you see. It will direct you to that post's page, and the
new URL will end with a number. That number is the ID of the current latest post.
If you don't have any posts, use `0`.

```
echo 123 > latest.txt
```

`latest.txt` should be in the root directory of this repository.

#### 2. Enter a list of subscribers in `emails.json`

The script reads in a JSON-formatted file that lists the subscribers that will
receive notifications. Copy the following contents into a file named
`emails.json`, and then customize it for your own subscribers.

```json
{
  "recipients": [
    {
      "address": "email@address.com",
      "text": "Hi Name!\n\nHope you had a nice weekend. There {has} been {n} new {post} since last week. You can see {it} at http://blog.example.com/.\n\nWarmly,\nAaron",
      "html": "<html><p>Hi Name!</p><p>Hope you had a nice weekend. There {has} been <strong style=\"color: #2e8540;\">{n}</strong> new {post} since last week. You can see {it} <a href=\"http://blog.example.com/\">on the blog</a>.</p><p>Warmly,<br>Aaron</p></html>"
    }
  ]
}
```

To add more subscribers, just copy, paste, and edit the inner block of JSON. The
keywords surrounded by curly braces will automatically be replaced. You should
just edit the address, the names, and the blog URL in the above snippet.

#### 3. Make sure your `config.ini` has the necessary values.

`notify.py` uses the following configuration parameters, so make sure they're
in your `config.ini`.

| Parameter | Description |
| --------- | ----------- |
| `domain` | The domain name where your blog is hosted. |
| `notify-name` | Your name. |
| `notify-from` | The email address from which to send the messages. It has to exist in your SendGrid account! |
| `notify-bcc` | An email address to BCC on the messages, just to stay in the loop. I use my personal email address. |
| `notify-reply-to` | An email address to use for the `Reply-To` header. Subscribers that click "Reply" will be emailing this address. |
| `notify-url` | This should be `https://api.sendgrid.com/v3/mail/send`. I think I made it configurable for testing? |
| `sendgrid-key` | An API key for SendGrid, which you generate in the dashboard. |

#### 4. Do a dry run.

With the above steps complete, you should be able to do a test run:

```sh
DRY=1 pipenv run python notify.py
```

You should see output that looks roughly like this:

```
Sending update to email@address.com
Updates sent successfully
```

#### 5. Configure `cron`.

From the server, run `crontab -e`. Add the following line to the bottom of the file.

```
0 0 * * 1 cd /path/to/uploader && /home/<user>/.pyenv/shims/pipenv run python notify.py > notify.log 2>&1
```

Change `<user>` to your username, and change `/path/to/uploader` to the absolute path
to the directory that contains `notify.py`.

This cron job will run every Sunday at midnight. You can change the frequency by changing
the cron schedule expression. I recommend using [crontab.guru](https://crontab.guru/) for that.

Save the file and exit.

## License

[MIT](LICENSE)
