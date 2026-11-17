"""Frontend mistakes that render without an error must still fail verify."""

import contextlib
import io
import tempfile
import unittest
from pathlib import Path

from stk import checks
from stk.app import Stk
from stk.checks import check_frontend_rules
from stk.settings import TestingConfig

BROKEN = """{% extends 'layout.html' %}
{% block content %}
<div class="text-h6 mb-2">Title</div>
<i class="mdi mdi-home"></i>
<script type="application/json" id="data">{}</script>
{% endblock %}
{% block js %}
<script>createApp({ setup() { return {}; } })</script>
{% endblock %}
"""

FINE = """{% extends 'layout.html' %}
{% block content %}
<div class="text-title-large">Title</div>
<i class="ti ti-home"></i>
{% endblock %}
{% block js %}
<script type="application/json" id="data">{}</script>
<script>createApp({ data() { return {}; } })</script>
{% endblock %}
"""


class FrontendRulesTest(unittest.IsolatedAsyncioTestCase):
    async def run_check(self, page):
        app = Stk(__name__, config=TestingConfig)
        with tempfile.TemporaryDirectory() as folder:
            (Path(folder) / "page.html").write_text(page)
            app.template_folders.insert(0, Path(folder))
            with contextlib.redirect_stdout(io.StringIO()):
                passed = await check_frontend_rules(app)
        return passed, checks.RESULTS[-1]["detail"]

    async def test_stk_itself_follows_the_rules(self):
        app = Stk(__name__, config=TestingConfig)
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertTrue(await check_frontend_rules(app))

    async def test_each_silent_mistake_is_named_with_its_line(self):
        passed, detail = await self.run_check(BROKEN)
        self.assertFalse(passed)
        self.assertIn("page.html:3: MD2 class text-h6 does nothing", detail)
        self.assertIn("page.html:4: MDI icon mdi-home", detail)
        self.assertIn("page.html:5: <script> in {% block content %}", detail)
        self.assertIn("page.html:8: Composition API setup()", detail)

    async def test_the_right_way_passes(self):
        passed, _ = await self.run_check(FINE)
        self.assertTrue(passed)
