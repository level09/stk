"""Note: blueprint, model, page, and sidebar entry."""

from minimal.note.views import bp_note


def init_app(app):
    app.register_blueprint(bp_note)
    app.navigation.append(
        {
            "title": "Notes",
            "icon": "ti ti-table",
            "to": "/notes/",
            "role": "admin",
        }
    )
