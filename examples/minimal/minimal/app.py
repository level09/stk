import stk.notification
from stk import Stk

from minimal import note
from minimal.settings import Config

# Each extension is a package with init_app(app); order is precedence.
extensions = [stk.notification, note]

app = Stk(__name__, config=Config, extensions=extensions)
