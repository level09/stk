---
title: "Renaming Your App"
description: "Turn stk into your product without editing templates"
---

An app built on stk keeps the framework's templates and changes three settings and two files. Never search and replace "stk" across templates: the next framework update would undo it.

## Name and copy

```bash
APP_NAME=Acme
APP_TAGLINE=Invoices that send themselves.
APP_DESCRIPTION=Acme chases late payments so you do not have to.
```

`APP_NAME` is the page title, the author meta tag, and the heading on exported recovery codes. `APP_TAGLINE` and `APP_DESCRIPTION` fill the sign-up panel.

The authenticator label is `SECURITY_TOTP_ISSUER` in `stk/settings.py`. It is not read from the environment, so set it in your settings to make authenticator apps show your product's name.

## Logo and favicon

- `stk/templates/_brand.html` is the only place the logo is referenced. Replace its `<img>` with your own. Keep `class="logo-adaptive"` if your logo is dark-on-light: dark mode inverts it.
- `stk/static/img/favicon.ico` is the favicon for every layout.

Then check both themes in a browser: `uv run stk smoke` writes `.stk/smoke/dashboard.png`.
