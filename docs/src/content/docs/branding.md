---
title: "Renaming Your App"
description: "Turn stk into your product without editing templates"
---

An app built on stk keeps the framework's templates and changes three settings and two files of its own. Never copy stk's templates to search and replace "stk": a copy stops receiving framework fixes.

## Name and copy

```bash
APP_NAME=Acme
APP_TAGLINE=Invoices that send themselves.
APP_DESCRIPTION=Acme chases late payments so you do not have to.
```

`APP_NAME` is the page title, the author meta tag, and the heading on exported recovery codes. `APP_TAGLINE` and `APP_DESCRIPTION` fill the sign-up panel.

The authenticator label is `SECURITY_TOTP_ISSUER`. It is not read from the environment, so set it on the `Config` in your app's `settings.py` to make authenticator apps show your product's name. `stk init` sets `APP_NAME` there already.

## Logo and favicon

- `_brand.html` is the only template that references the logo. Put your own at `myapp/templates/_brand.html`, and the logo file under `myapp/static/img/`; yours win over stk's. Keep `class="logo-adaptive"` if your logo is dark-on-light: dark mode inverts it.
- `myapp/static/img/favicon.ico` replaces the favicon for every layout.

Then check both themes in a browser: `uv run stk smoke` writes `.stk/smoke/dashboard.png`.
