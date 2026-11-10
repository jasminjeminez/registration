"""
Events Registration System
Python (Flask) + sqlite3 + Bootstrap 5

Run:
    pip install flask
    python app.py
Open: http://127.0.0.1:5000

Fee rule (from the data dictionary):  regFPaid = evRFee - partDRate
If your teacher says the discount rate is a PERCENT, set DISCOUNT_IS_PERCENT = True.
"""
import os
import sqlite3
from datetime import date

from flask import Flask, g, render_template, request, redirect, url_for, flash
from jinja2 import DictLoader

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "Registration.db")
LOCAL_CSS = os.path.join(BASE_DIR, "static", "bootstrap.min.css")

DISCOUNT_IS_PERCENT = False   # False: fee - discount   |   True: fee * (1 - discount/100)

app = Flask(__name__)
app.secret_key = "skilltest-events"


# ----------------------------------------------------------------------
# DATABASE
# ----------------------------------------------------------------------
SCHEMA = """
CREATE TABLE IF NOT EXISTS Events (
    evCode   INTEGER PRIMARY KEY,
    evName   TEXT NOT NULL,
    evDate   TEXT NOT NULL,            -- YYYY-MM-DD
    evVenue  TEXT NOT NULL,
    evRFee   REAL NOT NULL             -- decimal
);

CREATE TABLE IF NOT EXISTS Participants (
    partID     INTEGER PRIMARY KEY,
    evCode     INTEGER NOT NULL,
    partFName  TEXT NOT NULL,
    partLName  TEXT NOT NULL,
    partDRate  REAL NOT NULL DEFAULT 0,   -- decimal
    FOREIGN KEY (evCode) REFERENCES Events(evCode)
);

CREATE TABLE IF NOT EXISTS Registration (
    regCode  INTEGER PRIMARY KEY AUTOINCREMENT,
    partID   INTEGER NOT NULL,
    regDate  TEXT NOT NULL,            -- YYYY-MM-DD
    regFPaid REAL NOT NULL,            -- evRFee - partDRate
    regPMode TEXT NOT NULL CHECK (regPMode IN ('Card','Cash')),
    FOREIGN KEY (partID) REFERENCES Participants(partID)
);
"""


def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


@app.teardown_appcontext
def close_db(_exc):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    db = sqlite3.connect(DB_PATH)
    db.executescript(SCHEMA)
    if db.execute("SELECT COUNT(*) FROM Events").fetchone()[0] == 0:
        db.executemany("INSERT INTO Events VALUES (?,?,?,?,?)", [
            (1, "Tech Summit", "2024-11-15", "UC Main Gym", 500),
            (2, "Career Fair", "2024-11-20", "UC Main Auditorium", 300),
            (3, "Hackathon", "2024-12-05", "CCS Building", 1000),
        ])
        db.executemany("INSERT INTO Participants VALUES (?,?,?,?,?)", [
            (101, 1, "Juan", "Dela Cruz", 0),
            (102, 1, "Maria", "Clara", 50),
            (103, 2, "Jose", "Rizal", 30),
            (104, 3, "Andres", "Bonifacio", 100),
            (105, 3, "Gabriela", "Silang", 0),
        ])
        db.executemany(
            "INSERT INTO Registration (partID, regDate, regFPaid, regPMode) VALUES (?,?,?,?)", [
                (101, "2024-10-01", 500, "Cash"),
                (102, "2024-10-03", 450, "Card"),
                (103, "2024-10-05", 270, "Cash"),
                (104, "2024-10-07", 900, "Card"),
            ])
    db.commit()
    db.close()


# ----------------------------------------------------------------------
# HELPERS
# ----------------------------------------------------------------------
@app.context_processor
def inject_globals():
    return {"use_local_css": os.path.exists(LOCAL_CSS),
            "percent_mode": DISCOUNT_IS_PERCENT}


@app.template_filter("money")
def fmt_money(value):
    return f"{float(value or 0):,.2f}"


def compute_fee(fee, disc):
    """Registration fee to be paid after applying the participant's discount."""
    paid = fee * (1 - disc / 100) if DISCOUNT_IS_PERCENT else fee - disc
    return round(max(paid, 0), 2)


def next_id(table, col):
    return (get_db().execute(f"SELECT COALESCE(MAX({col}), 0) + 1 FROM {table}").fetchone()[0])


# ----------------------------------------------------------------------
# MENU
# ----------------------------------------------------------------------
@app.route("/")
def menu():
    return render_template("menu.html")


# ----------------------------------------------------------------------
# EVENTS MANAGEMENT  (add / search-update / search-delete / view)
# ----------------------------------------------------------------------
@app.route("/events")
def events():
    q = request.args.get("q", "").strip()
    rows = get_db().execute(
        "SELECT * FROM Events WHERE evName LIKE ? OR evVenue LIKE ? OR CAST(evCode AS TEXT) LIKE ? "
        "ORDER BY evCode", (f"%{q}%",) * 3).fetchall()
    return render_template("events.html", rows=rows, q=q)


@app.route("/events/add", methods=["GET", "POST"])
def event_add():
    if request.method == "POST":
        f = request.form
        try:
            code = int(f["evCode"]) if f["evCode"].strip() else next_id("Events", "evCode")
            get_db().execute("INSERT INTO Events VALUES (?,?,?,?,?)",
                             (code, f["evName"].strip(), f["evDate"], f["evVenue"].strip(), float(f["evRFee"])))
            get_db().commit()
            flash("Event added.", "ok")
            return redirect(url_for("events"))
        except (sqlite3.IntegrityError, ValueError):
            flash("Could not add: invalid input or duplicate event code.", "err")
    return render_template("event_form.html", e=None)


@app.route("/events/edit/<int:code>", methods=["GET", "POST"])
def event_edit(code):
    db = get_db()
    e = db.execute("SELECT * FROM Events WHERE evCode=?", (code,)).fetchone()
    if e is None:
        return redirect(url_for("events"))
    if request.method == "POST":
        f = request.form
        try:
            db.execute("UPDATE Events SET evName=?, evDate=?, evVenue=?, evRFee=? WHERE evCode=?",
                       (f["evName"].strip(), f["evDate"], f["evVenue"].strip(), float(f["evRFee"]), code))
            db.commit()
            flash("Event updated.", "ok")
            return redirect(url_for("events"))
        except ValueError:
            flash("Invalid input.", "err")
    return render_template("event_form.html", e=e)


@app.route("/events/delete/<int:code>", methods=["POST"])
def event_delete(code):
    try:
        get_db().execute("DELETE FROM Events WHERE evCode=?", (code,))
        get_db().commit()
        flash("Event deleted.", "ok")
    except sqlite3.IntegrityError:
        flash("Cannot delete: participants are assigned to this event.", "err")
    return redirect(url_for("events"))


# ----------------------------------------------------------------------
# PARTICIPANTS MANAGEMENT  (add / search-update / search-delete / view)
# ----------------------------------------------------------------------
@app.route("/participants")
def participants():
    q = request.args.get("q", "").strip()
    rows = get_db().execute(
        "SELECT p.*, e.evName FROM Participants p LEFT JOIN Events e ON e.evCode = p.evCode "
        "WHERE p.partFName LIKE ? OR p.partLName LIKE ? OR CAST(p.partID AS TEXT) LIKE ? "
        "ORDER BY p.partID", (f"%{q}%",) * 3).fetchall()
    return render_template("participants.html", rows=rows, q=q)


@app.route("/participants/add", methods=["GET", "POST"])
def participant_add():
    db = get_db()
    evs = db.execute("SELECT * FROM Events ORDER BY evName").fetchall()
    if request.method == "POST":
        f = request.form
        try:
            pid = int(f["partID"]) if f["partID"].strip() else next_id("Participants", "partID")
            db.execute("INSERT INTO Participants VALUES (?,?,?,?,?)",
                       (pid, int(f["evCode"]), f["partFName"].strip(), f["partLName"].strip(),
                        float(f["partDRate"] or 0)))
            db.commit()
            flash("Participant added.", "ok")
            return redirect(url_for("participants"))
        except (sqlite3.IntegrityError, ValueError):
            flash("Could not add: invalid input or duplicate participant ID.", "err")
    return render_template("part_form.html", p=None, evs=evs)


@app.route("/participants/edit/<int:pid>", methods=["GET", "POST"])
def participant_edit(pid):
    db = get_db()
    p = db.execute("SELECT * FROM Participants WHERE partID=?", (pid,)).fetchone()
    if p is None:
        return redirect(url_for("participants"))
    evs = db.execute("SELECT * FROM Events ORDER BY evName").fetchall()
    if request.method == "POST":
        f = request.form
        try:
            db.execute("UPDATE Participants SET evCode=?, partFName=?, partLName=?, partDRate=? WHERE partID=?",
                       (int(f["evCode"]), f["partFName"].strip(), f["partLName"].strip(),
                        float(f["partDRate"] or 0), pid))
            db.commit()
            flash("Participant updated.", "ok")
            return redirect(url_for("participants"))
        except (sqlite3.IntegrityError, ValueError):
            flash("Invalid input.", "err")
    return render_template("part_form.html", p=p, evs=evs)


@app.route("/participants/delete/<int:pid>", methods=["POST"])
def participant_delete(pid):
    try:
        get_db().execute("DELETE FROM Participants WHERE partID=?", (pid,))
        get_db().commit()
        flash("Participant deleted.", "ok")
    except sqlite3.IntegrityError:
        flash("Cannot delete: participant has registration records.", "err")
    return redirect(url_for("participants"))


# ----------------------------------------------------------------------
# PARTICIPANT REGISTRATION  (register / compute fee / view latest -> oldest)
# ----------------------------------------------------------------------
REG_SQL = (
    "SELECT r.*, p.partFName || ' ' || p.partLName AS fullName, p.partDRate, e.evName, e.evRFee "
    "FROM Registration r "
    "JOIN Participants p ON p.partID = r.partID "
    "JOIN Events e ON e.evCode = p.evCode "
)


@app.route("/registration", methods=["GET", "POST"])
def registration():
    db = get_db()
    if request.method == "POST":
        f = request.form
        try:
            row = db.execute(
                "SELECT p.partDRate, e.evRFee FROM Participants p "
                "JOIN Events e ON e.evCode = p.evCode WHERE p.partID=?", (int(f["partID"]),)).fetchone()
            if row is None:
                raise ValueError
            if f["regPMode"] not in ("Card", "Cash"):
                raise ValueError
            paid = compute_fee(row["evRFee"], row["partDRate"])
            db.execute("INSERT INTO Registration (partID, regDate, regFPaid, regPMode) VALUES (?,?,?,?)",
                       (int(f["partID"]), f["regDate"], paid, f["regPMode"]))
            db.commit()
            flash(f"Registered! Fee to pay: {paid:,.2f}", "ok")
            return redirect(url_for("registration"))
        except (sqlite3.IntegrityError, ValueError):
            flash("Invalid registration data.", "err")
    parts = db.execute(
        "SELECT p.*, e.evName, e.evRFee FROM Participants p "
        "JOIN Events e ON e.evCode = p.evCode ORDER BY p.partLName").fetchall()
    rows = db.execute(REG_SQL + "ORDER BY r.regDate DESC, r.regCode DESC").fetchall()
    return render_template("registration.html", parts=parts, rows=rows, today=date.today().isoformat())


# ----------------------------------------------------------------------
# EVENTS REGISTRATION MONITORING  (filter: Event's Name + aggregates)
# ----------------------------------------------------------------------
@app.route("/monitor")
def monitor():
    db = get_db()
    q = request.args.get("q", "").strip()
    all_names = db.execute("SELECT evName FROM Events ORDER BY evName").fetchall()
    evs = db.execute("SELECT * FROM Events WHERE evName LIKE ? ORDER BY evName", (f"%{q}%",)).fetchall()
    sections = []
    for ev in evs:
        rows = db.execute(
            "SELECT p.partFName || ' ' || p.partLName AS fullName, r.regDate, r.regFPaid "
            "FROM Registration r JOIN Participants p ON p.partID = r.partID "
            "WHERE p.evCode = ? ORDER BY r.regDate, r.regCode", (ev["evCode"],)).fetchall()
        # aggregate functions
        agg = db.execute(
            "SELECT COUNT(r.regCode) AS a, COALESCE(SUM(r.regFPaid), 0) AS b "
            "FROM Registration r JOIN Participants p ON p.partID = r.partID "
            "WHERE p.evCode = ?", (ev["evCode"],)).fetchone()
        sections.append({
            "ev": ev, "rows": rows,
            "count": agg["a"],                              # count()
            "total": agg["b"],                              # sum()
            "discount": agg["a"] * ev["evRFee"] - agg["b"],  # (a * evRFee) - b
        })
    return render_template("monitor.html", sections=sections, q=q, names=all_names)


# ----------------------------------------------------------------------
# TEMPLATES (inline so the whole project is a single file)
# ----------------------------------------------------------------------
TEMPLATES = {
    "base.html": """<!doctype html>
<html lang="en"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Events Registration System</title>
{% if use_local_css %}
<link href="{{ url_for('static', filename='bootstrap.min.css') }}" rel="stylesheet">
{% else %}
<link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css" rel="stylesheet">
{% endif %}
</head>
<body>
<nav class="navbar navbar-dark bg-dark mb-4">
  <div class="container">
    <a class="navbar-brand" href="{{ url_for('menu') }}">Events Registration System</a>
  </div>
</nav>
<div class="container pb-5">
{% with msgs = get_flashed_messages(with_categories=true) %}
  {% for cat, m in msgs %}
  <div class="alert alert-{{ 'success' if cat == 'ok' else 'danger' }}">{{ m }}</div>
  {% endfor %}
{% endwith %}
{% block content %}{% endblock %}
</div>
</body></html>""",

    "menu.html": """{% extends 'base.html' %}{% block content %}
<h3>Main Menu</h3>
<div class="list-group col-md-6 mt-3">
 <a class="list-group-item list-group-item-action" href="{{ url_for('events') }}">Events Management</a>
 <a class="list-group-item list-group-item-action" href="{{ url_for('participants') }}">Participants Management</a>
 <a class="list-group-item list-group-item-action" href="{{ url_for('registration') }}">Participant Registration</a>
 <a class="list-group-item list-group-item-action" href="{{ url_for('monitor') }}">Events Registration Monitoring</a>
</div>{% endblock %}""",

    "events.html": """{% extends 'base.html' %}{% block content %}
<h3>Events Management</h3>
<div class="d-flex justify-content-between mb-3">
 <form method="get" class="d-flex gap-2">
  <input class="form-control" name="q" value="{{ q }}" placeholder="Search event (name, venue, code)">
  <button class="btn btn-primary">Search</button>
  <a class="btn btn-outline-secondary" href="{{ url_for('events') }}">All</a>
 </form>
 <div>
  <a class="btn btn-success" href="{{ url_for('event_add') }}">Add Event</a>
  <a class="btn btn-secondary" href="{{ url_for('menu') }}">Back to Menu</a>
 </div>
</div>
<table class="table table-bordered table-striped text-center align-middle">
<thead class="table-dark"><tr><th>Code</th><th>Name</th><th>Date</th><th>Venue</th><th>Reg. Fee</th><th>Actions</th></tr></thead>
{% for r in rows %}
<tr><td>{{ r.evCode }}</td><td>{{ r.evName }}</td><td>{{ r.evDate }}</td><td>{{ r.evVenue }}</td>
<td>{{ r.evRFee | money }}</td>
<td><a class="btn btn-sm btn-warning" href="{{ url_for('event_edit', code=r.evCode) }}">Edit</a>
 <form class="d-inline" method="post" action="{{ url_for('event_delete', code=r.evCode) }}"
  onsubmit="return confirm('Delete this event?')"><button class="btn btn-sm btn-danger">Del</button></form></td></tr>
{% else %}<tr><td colspan="6">No events found.</td></tr>{% endfor %}
</table>{% endblock %}""",

    "event_form.html": """{% extends 'base.html' %}{% block content %}
<h3>{{ 'Edit' if e else 'Add' }} Event</h3>
<form method="post" class="col-md-5">
 <div class="mb-3"><label class="form-label">Event Code {{ '' if e else '(leave blank for auto)' }}</label>
  <input class="form-control" name="evCode" type="number" value="{{ e.evCode if e }}" {{ 'readonly' if e }}></div>
 <div class="mb-3"><label class="form-label">Event Name</label>
  <input class="form-control" name="evName" required value="{{ e.evName if e }}"></div>
 <div class="mb-3"><label class="form-label">Event Date</label>
  <input class="form-control" type="date" name="evDate" required value="{{ e.evDate if e }}"></div>
 <div class="mb-3"><label class="form-label">Venue</label>
  <input class="form-control" name="evVenue" required value="{{ e.evVenue if e }}"></div>
 <div class="mb-3"><label class="form-label">Registration Fee</label>
  <input class="form-control" type="number" step="0.01" min="0" name="evRFee" required value="{{ e.evRFee if e }}"></div>
 <button class="btn btn-success">Save</button>
 <a class="btn btn-secondary" href="{{ url_for('events') }}">Cancel</a>
</form>{% endblock %}""",

    "participants.html": """{% extends 'base.html' %}{% block content %}
<h3>Participants Management</h3>
<div class="d-flex justify-content-between mb-3">
 <form method="get" class="d-flex gap-2">
  <input class="form-control" name="q" value="{{ q }}" placeholder="Search participant (name or ID)">
  <button class="btn btn-primary">Search</button>
  <a class="btn btn-outline-secondary" href="{{ url_for('participants') }}">All</a>
 </form>
 <div>
  <a class="btn btn-success" href="{{ url_for('participant_add') }}">Add Participant</a>
  <a class="btn btn-secondary" href="{{ url_for('menu') }}">Back to Menu</a>
 </div>
</div>
<table class="table table-bordered table-striped text-center align-middle">
<thead class="table-dark"><tr><th>ID</th><th>Event</th><th>First Name</th><th>Last Name</th><th>Discount Rate</th><th>Actions</th></tr></thead>
{% for r in rows %}
<tr><td>{{ r.partID }}</td><td>{{ r.evCode }} - {{ r.evName }}</td><td>{{ r.partFName }}</td><td>{{ r.partLName }}</td>
<td>{{ r.partDRate | money }}</td>
<td><a class="btn btn-sm btn-warning" href="{{ url_for('participant_edit', pid=r.partID) }}">Edit</a>
 <form class="d-inline" method="post" action="{{ url_for('participant_delete', pid=r.partID) }}"
  onsubmit="return confirm('Delete this participant?')"><button class="btn btn-sm btn-danger">Del</button></form></td></tr>
{% else %}<tr><td colspan="6">No participants found.</td></tr>{% endfor %}
</table>{% endblock %}""",

    "part_form.html": """{% extends 'base.html' %}{% block content %}
<h3>{{ 'Edit' if p else 'Add' }} Participant</h3>
{% if not evs %}<div class="alert alert-warning">Add an event first.</div>{% endif %}
<form method="post" class="col-md-5">
 <div class="mb-3"><label class="form-label">Participant ID {{ '' if p else '(leave blank for auto)' }}</label>
  <input class="form-control" name="partID" type="number" value="{{ p.partID if p }}" {{ 'readonly' if p }}></div>
 <div class="mb-3"><label class="form-label">Event</label>
  <select class="form-select" name="evCode" required>
   {% for e in evs %}<option value="{{ e.evCode }}" {{ 'selected' if p and p.evCode == e.evCode }}>{{ e.evCode }} - {{ e.evName }}</option>{% endfor %}
  </select></div>
 <div class="mb-3"><label class="form-label">First Name</label>
  <input class="form-control" name="partFName" required value="{{ p.partFName if p }}"></div>
 <div class="mb-3"><label class="form-label">Last Name</label>
  <input class="form-control" name="partLName" required value="{{ p.partLName if p }}"></div>
 <div class="mb-3"><label class="form-label">Discount Rate</label>
  <input class="form-control" type="number" step="0.01" min="0" name="partDRate" value="{{ p.partDRate if p else 0 }}"></div>
 <button class="btn btn-success">Save</button>
 <a class="btn btn-secondary" href="{{ url_for('participants') }}">Cancel</a>
</form>{% endblock %}""",

    "registration.html": """{% extends 'base.html' %}{% block content %}
<h3>Participant Registration</h3>
<a class="btn btn-secondary mb-3" href="{{ url_for('menu') }}">Back to Menu</a>
<form method="post" class="row g-3 mb-4">
 <div class="col-md-5"><label class="form-label">Participant</label>
  <select class="form-select" name="partID" id="part" required>
   {% for p in parts %}
   <option value="{{ p.partID }}" data-fee="{{ p.evRFee }}" data-disc="{{ p.partDRate }}">
     {{ p.partID }} - {{ p.partLName }}, {{ p.partFName }} ({{ p.evName }})</option>
   {% endfor %}
  </select></div>
 <div class="col-md-3"><label class="form-label">Registration Date</label>
  <input class="form-control" type="date" name="regDate" value="{{ today }}" required></div>
 <div class="col-md-2"><label class="form-label">Payment Mode</label>
  <select class="form-select" name="regPMode"><option>Cash</option><option>Card</option></select></div>
 <div class="col-md-2 d-flex align-items-end"><button class="btn btn-primary w-100">Register</button></div>
 <div class="col-12">
  <div class="alert alert-info mb-0">Event fee: <b id="fee">0.00</b> &nbsp; Discount: <b id="disc">0.00</b>
   &nbsp; <span class="fs-5">Fee to pay: <b id="pay">0.00</b></span></div>
 </div>
</form>
<script>
 var PERCENT = {{ 'true' if percent_mode else 'false' }};
 function calc() {
   var o = document.getElementById('part').selectedOptions[0];
   if (!o) return;
   var fee = parseFloat(o.dataset.fee), d = parseFloat(o.dataset.disc);
   var pay = PERCENT ? fee * (1 - d / 100) : fee - d;
   document.getElementById('fee').textContent = fee.toFixed(2);
   document.getElementById('disc').textContent = d.toFixed(2) + (PERCENT ? '%' : '');
   document.getElementById('pay').textContent = Math.max(pay, 0).toFixed(2);
 }
 document.getElementById('part').addEventListener('change', calc); calc();
</script>
<h5>Registration Transactions (latest to oldest)</h5>
<table class="table table-bordered table-striped text-center align-middle">
<thead class="table-dark"><tr><th>Reg. Code</th><th>Participant</th><th>Event</th><th>Reg. Date</th><th>Fee Paid</th><th>Mode</th></tr></thead>
{% for r in rows %}
<tr><td>{{ r.regCode }}</td><td>{{ r.partID }} - {{ r.fullName }}</td><td>{{ r.evName }}</td>
<td>{{ r.regDate }}</td><td>{{ r.regFPaid | money }}</td><td>{{ r.regPMode }}</td></tr>
{% else %}<tr><td colspan="6">No registrations yet.</td></tr>{% endfor %}
</table>{% endblock %}""",

    "monitor.html": """{% extends 'base.html' %}{% block content %}
<h3>Events Registration Monitoring</h3>
<div class="d-flex justify-content-between mb-3">
 <form method="get" class="d-flex gap-2">
  <input class="form-control" name="q" value="{{ q }}" list="names" placeholder="Filter: Event's Name (blank = all)">
  <datalist id="names">{% for n in names %}<option value="{{ n.evName }}">{% endfor %}</datalist>
  <button class="btn btn-primary">Filter</button>
 </form>
 <a class="btn btn-secondary" href="{{ url_for('menu') }}">Back to Menu</a>
</div>
{% for s in sections %}
<h4 class="mt-4">Event: {{ s.ev.evName }}</h4>
<table class="table table-bordered table-striped text-center">
<thead class="table-dark"><tr><th>Participant's Full Name</th><th>Registration Date</th><th>Registration Fee Paid</th></tr></thead>
{% for r in s.rows %}
<tr><td>{{ r.fullName }}</td><td>{{ r.regDate }}</td><td>{{ r.regFPaid | money }}</td></tr>
{% else %}<tr><td colspan="3">No registrations.</td></tr>{% endfor %}
</table>
<div class="row fw-bold">
 <div class="col-md-4">Number of records: {{ s.count }}</div>
 <div class="col-md-4">Total Registration Fees Paid: {{ s.total | money }}</div>
 <div class="col-md-4">Total Amount of Discounts: {{ s.discount | money }}</div>
</div>
{% else %}
<div class="alert alert-warning">No event matches that name.</div>
{% endfor %}{% endblock %}""",
}
app.jinja_loader = DictLoader(TEMPLATES)

if __name__ == "__main__":
    init_db()
    app.run(debug=True)