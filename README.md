# To Do

* [X] Fix `formatSummary` to only add `<span>`s when `convert_links == True`.
  * Alternatively, create a separate function for making the `alt` attribute vs. the post summary.
* [X] Change `formatSummary` so it auto-links any non-characters before a `/`.
* [ ] Flesh out the test suite
* [ ] Use Python's native `logging` module.
* [ ] Implement [Mailgun event verification][mailgun-webhooks].

[mailgun-webhooks]: https://documentation.mailgun.com/user_manual.html#webhooks
