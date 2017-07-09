# Uploader

Code for a web server that facilitates uploading emailed photos to a website.
I have a site where I post photos. It used to be hosted on Tumblr, but then
Tumblr stopped allowing post-by-email. Now the site is hosted on GitHub Pages
and I built this application to allow post-by-email.

The server listens for webhooks from [Mailgun](https://www.mailgun.com/). When
it receives a notification that an email was received, it downloads the
attached photo (and some metadata), resizes it, creates a new post on the
GitHub Pages site's repository, and pushes it (which republishes the website.)

It's implemented in Python using [Bottle](https://bottlepy.org/docs/dev/).
