from stk import Stk

from __app__.settings import Config

# Each extension is a package with init_app(app); order is precedence.
extensions = []

app = Stk(__name__, config=Config, extensions=extensions)
