"""Pure rendering functions for scaffold templates.

Each function takes a name (snake_case) and returns the file content as a string.
No filesystem I/O here -- keeps this fully unit-testable.
"""

from string import Template


def _t(src: str, **kwargs) -> str:
    return Template(src).substitute(**kwargs)


def _cls(name: str) -> str:
    return "".join(w.capitalize() for w in name.split("_"))


def render_init(name: str) -> str:  # noqa: ARG001
    return '"""Blueprint package."""\n'


def render_models(name: str) -> str:
    cls = _cls(name)
    return _t(
        '''\
"""Models for $name blueprint."""

import dataclasses
from datetime import datetime

from sqlalchemy import Column, DateTime, Integer, String

from stk.extensions import Base


@dataclasses.dataclass
class $cls(Base):
    __tablename__ = "$name"

    id = Column(Integer, primary_key=True)
    name = Column(String(255), nullable=False)
    description = Column(String(1024), nullable=True)
    created_at = Column(DateTime, default=datetime.now, nullable=False)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now, nullable=False)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

    async def from_dict(self, data: dict) -> "$cls":
        self.name = data.get("name", self.name)
        self.description = data.get("description", self.description)
        return self

    def __repr__(self) -> str:
        return f"<$cls {self.id}: {self.name}>"
''',
        name=name,
        cls=cls,
    )


def render_views(name: str) -> str:
    cls = _cls(name)
    plural = name + "s"
    # Pre-compute all function names to avoid string.Template misparses
    fn_page = f"{plural}_page"
    fn_list = f"api_{plural}_list"
    fn_create = f"api_{name}_create"
    fn_update = f"api_{name}_update"
    fn_delete = f"api_{name}_delete"
    return _t(
        '''\
"""Views for $name blueprint."""

import logging

import orjson as json
from quart import Blueprint, Response, g, render_template, request
from quart_security import auth_required, current_user, roles_required
from sqlalchemy import func, select

from stk.user.models import Activity
from stk.$name.models import $cls

log = logging.getLogger(__name__)

bp_$name = Blueprint("$name", __name__)

PER_PAGE = 25


@bp_$name.before_request
@auth_required("session")
@roles_required("admin")
async def before_request():
    pass


@bp_$name.get("/$plural/")
async def $fn_page():
    return await render_template("cms/$name.html")


@bp_$name.get("/api/$plural")
async def $fn_list():
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", PER_PAGE, type=int)
    search = request.args.get("search", "").strip()

    query = select($cls)
    count_query = select(func.count()).select_from($cls)

    if search:
        query = query.where($cls.name.ilike(f"%{search}%"))
        count_query = count_query.where($cls.name.ilike(f"%{search}%"))

    total = (await g.db_session.execute(count_query)).scalar()
    result = await g.db_session.execute(
        query.offset((page - 1) * per_page).limit(per_page)
    )
    items = [item.to_dict() for item in result.scalars().all()]

    return Response(
        json.dumps({"items": items, "total": total, "perPage": per_page}),
        content_type="application/json",
    )


@bp_$name.post("/api/$name/")
async def $fn_create():
    json_data = await request.json
    item_data = json_data.get("item", {})
    item = $cls()
    await item.from_dict(item_data)
    g.db_session.add(item)
    try:
        await g.db_session.flush()
        await Activity.register(current_user.id, "$cls Create", item.to_dict())
        await g.db_session.commit()
        return {"message": "$cls successfully created!"}
    except Exception:
        await g.db_session.rollback()
        log.exception("Error creating $name")
        return {"message": "Error creating $name"}, 412


@bp_$name.post("/api/$name/<int:id>")
async def $fn_update(id):
    item = await g.db_session.get($cls, id)
    if item is None:
        return {"message": "$cls not found"}, 404
    json_data = await request.json
    item_data = json_data.get("item", {})
    old_data = item.to_dict()
    try:
        await item.from_dict(item_data)
        await g.db_session.flush()
        await Activity.register(
            current_user.id,
            "$cls Update",
            {"old": old_data, "new": item.to_dict()},
        )
        await g.db_session.commit()
        return {"message": "$cls successfully updated!"}
    except Exception:
        await g.db_session.rollback()
        log.exception("Error updating $name")
        return {"message": "Error updating $name"}, 412


@bp_$name.route("/api/$name/<int:id>", methods=["DELETE"])
async def $fn_delete(id):
    item = await g.db_session.get($cls, id)
    if item is None:
        return {"message": "$cls not found"}, 404
    old_data = item.to_dict()
    try:
        await g.db_session.delete(item)
        await Activity.register(current_user.id, "$cls Delete", old_data)
        await g.db_session.commit()
        return {"message": "$cls successfully deleted!"}
    except Exception:
        await g.db_session.rollback()
        log.exception("Error deleting $name")
        return {"message": "Error deleting $name"}, 412
''',
        name=name,
        cls=cls,
        plural=plural,
        fn_page=fn_page,
        fn_list=fn_list,
        fn_create=fn_create,
        fn_update=fn_update,
        fn_delete=fn_delete,
    )


def render_template_html(name: str) -> str:
    cls = _cls(name)
    title = name.replace("_", " ").title()
    plural = name + "s"
    plural_title = title + "s"
    # JS template literals use ${...} -- we need literal dollar-signs for those.
    # string.Template uses $$ for a literal $, so $${ becomes ${.
    return _t(
        """\
{% extends 'layout.html' %} {% block css %} {% endblock %} {% block sidebar %}
{% endblock %} {% block layout_classes %} align-center {% endblock %}
{% block content %}

    <v-card class="ma-2 mt-12 w-100 h-100">
        <v-toolbar>
            <v-toolbar-title>$plural_title</v-toolbar-title>
            <v-spacer></v-spacer>
        </v-toolbar>
        <v-card-text>

            <v-data-table-server
            :items="items"
            :items-length="itemsLength"
            :headers="headers"
            :page="options.page"
            :items-per-page="options.itemsPerPage"
            @update:options="refresh"
            hover
            >

                <template v-slot:top>
                    <v-toolbar class="mb-4" dense elevation="0" color="transparent">
                        <v-text-field
                            v-model="search"
                            density="compact"
                            label="Search"
                            prepend-inner-icon="ti ti-search"
                            variant="outlined"
                            hide-details
                            single-line
                            class="mr-4"
                            style="max-width:320px"
                            @update:model-value="refresh()"
                        ></v-text-field>
                        <v-btn class="ml-auto" @click="createItem" size="small" color="primary" variant="elevated">
                            <template v-slot:prepend><i class="ti ti-plus"></i></template>
                            Add $title
                        </v-btn>
                    </v-toolbar>
                </template>

                <template v-slot:item.actions="{ item }">
                    <v-icon small class="mr-2" @click="editItem(item)">ti ti-pencil</v-icon>
                    <v-icon small @click="deleteItem(item)">ti ti-trash</v-icon>
                </template>

            </v-data-table-server>

        </v-card-text>
    </v-card>


    <!--Edit Dialog-->
    <v-dialog v-model="edialog" width="660">
        <v-card v-if="edialog">
            <v-toolbar>
                <v-toolbar-title>$${eidialog_title}</v-toolbar-title>
                <template v-slot:append>
                    <v-btn @click="edialog=false" size="small" icon="ti ti-x" variant="text"></v-btn>
                </template>
            </v-toolbar>
            <v-card-text>
                <v-text-field label="Name" v-model="eitem.name" required></v-text-field>
                <v-textarea label="Description" v-model="eitem.description" rows="3"></v-textarea>
            </v-card-text>
            <v-card-actions>
                <v-spacer></v-spacer>
                <v-btn color="primary" @click="saveItem" variant="elevated">Save</v-btn>
            </v-card-actions>
        </v-card>
    </v-dialog>

    <v-snackbar size="small" class="d-flex" v-model="snackBar" rounded="pill" elevation="25">
        $${snackMessage}
        <template v-slot:actions>
            <v-btn @click="snackBar=false" icon="ti ti-x" class="ml-auto" size="small" variant="text"></v-btn>
        </template>
    </v-snackbar>

{% endblock %} {% block js %}

    <script>
        const {createApp, toRaw} = Vue;
        const {createVuetify} = Vuetify;

        const vuetify = createVuetify(config.vuetifyConfig);

        window.app = createApp({
            mixins: [layoutMixin],
            data() {
                return {
                    errors: "",
                    snackBar: false,
                    snackMessage: "",
                    search: "",
                    items: [],
                    itemsLength: 0,
                    options: {
                        page: 1,
                        itemsPerPage: 25
                    },
                    headers: [
                        {title: 'ID', value: 'id'},
                        {title: 'Name', value: 'name'},
                        {title: 'Description', value: 'description'},
                        {title: 'Actions', value: 'actions', sortable: false}
                    ],
                    edialog: false,
                    eitem: {id: "", name: "", description: ""},
                };
            },

            mounted() {
                // Table triggers refresh via @update:options on load
            },
            delimiters: config.delimiters,

            computed: {
                eidialog_title() {
                    return this.eitem.id ? 'Edit $title' : 'New $title';
                }
            },

            methods: {
                showSnack(message) {
                    this.snackMessage = message;
                    this.snackBar = true;
                },

                refresh(options) {
                    if (options) {
                        this.options = {
                            ...this.options,
                            page: options.page,
                            itemsPerPage: options.itemsPerPage
                        };
                    }
                    axios.get(`/api/$plural?page=$${this.options.page}&per_page=$${this.options.itemsPerPage}&search=$${this.search}`)
                        .then(res => {
                            this.items = res.data.items;
                            this.itemsLength = res.data.total;
                            if (res.data.perPage) this.options.itemsPerPage = res.data.perPage;
                        })
                        .catch(error => {
                            console.error('Error fetching $plural:', error);
                            this.showSnack('Failed to load $plural');
                        });
                },

                createItem() {
                    this.eitem = {id: "", name: "", description: ""};
                    this.edialog = true;
                },

                editItem(item) {
                    this.eitem = toRaw(item);
                    this.$$nextTick(() => { this.edialog = true; });
                },

                saveItem() {
                    if (this.eitem.id) {
                        axios.post(`/api/$name/$${this.eitem.id}`, {item: this.eitem})
                            .then(res => { this.showSnack(res.data?.message); this.refresh(); })
                            .catch(err => { this.showSnack(err.response?.data?.message || 'Error'); });
                    } else {
                        axios.post('/api/$name/', {item: this.eitem})
                            .then(res => { this.showSnack(res.data?.message); this.refresh(); })
                            .catch(err => { this.showSnack(err.response?.data?.message || 'Error'); });
                    }
                    this.edialog = false;
                },

                deleteItem(item) {
                    if (confirm('Are you sure?')) {
                        axios.delete(`/api/$name/$${item.id}`)
                            .then(res => { this.showSnack(res.data?.message); this.refresh(); })
                            .catch(err => { this.showSnack(err.response?.data?.message || 'Error'); });
                    }
                }
            }
        });

        registerStkComponents(app);
        app.use(vuetify).mount("#app");
    </script>
{% endblock %}
""",
        name=name,
        cls=cls,
        title=title,
        plural=plural,
        plural_title=plural_title,
    )


def render_nav_entry(name: str) -> str:
    title = name.replace("_", " ").title()
    plural = name + "s"
    icon = "ti ti-table"
    return (
        f"  {{\n"
        f"    title: '{title}',\n"
        f"    icon: '{icon}',\n"
        f"    to: '/{plural}',\n"
        f"    role: 'admin'\n"
        f"  }},\n"
    )


def render_app_import(name: str) -> str:
    """Return the import line to add to app.py."""
    bp = f"bp_{name}"
    return f"from stk.{name}.views import {bp}\n"


def render_app_register(name: str) -> str:
    """Return the register_blueprint line to add to app.py."""
    bp = f"bp_{name}"
    return f"    app.register_blueprint({bp})\n"
