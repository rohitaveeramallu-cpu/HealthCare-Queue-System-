from flask import Flask, render_template, request, jsonify, session
import mysql.connector
from mysql.connector import Error
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
import os

app = Flask(__name__)
app.secret_key = os.environ.get("HQM_SECRET_KEY", "change-this-secret-key-for-college-demo")

DB_CONFIG = {
    "host": "localhost",
    "user": "root",
    "password": "polavarapuneeharika@2008",
    "database": "healthcare_queue"
}

def get_db():
    return mysql.connector.connect(**DB_CONFIG)

def api_login_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not session.get("role"):
            return jsonify({"error": "Please log in first."}), 401
        return fn(*args, **kwargs)
    return wrapper

def staff_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if session.get("role") != "staff":
            return jsonify({"error": "Staff access required."}), 403
        return fn(*args, **kwargs)
    return wrapper

def doctor_scope(doctor_id):
    return session.get("role") == "staff" or (
        session.get("role") == "doctor" and session.get("doctor_id") == doctor_id
    )

def ensure_default_logins():
    """Set demo logins only for existing doctors whose login is not configured."""
    db = get_db()
    cur = db.cursor(dictionary=True)
    cur.execute("SELECT id, name, username, password_hash FROM doctors ORDER BY id")
    rows = cur.fetchall()
    defaults = {1: "sharma", 2: "reddy", 3: "khan"}
    for d in rows:
        if not d["username"] or not d["password_hash"]:
            username = defaults.get(d["id"], "doctor" + str(d["id"]))
            cur.execute(
                "UPDATE doctors SET username=%s, password_hash=%s WHERE id=%s",
                (username, generate_password_hash("doc123"), d["id"])
            )
    db.commit()
    cur.close()
    db.close()

@app.route("/")
def home():
    return render_template("index.html")

@app.route("/api/login", methods=["POST"])
def login():
    data = request.get_json(silent=True) or {}
    mode = data.get("mode")
    username = (data.get("username") or "").strip()
    password = data.get("password") or ""
    if mode == "staff":
        if username == "admin" and password == "admin123":
            session.clear()
            session["role"] = "staff"
            session["username"] = username
            return jsonify({"role": "staff", "name": "Staff"})
        return jsonify({"error": "Invalid staff username or password."}), 401
    if mode == "doctor":
        db = get_db()
        cur = db.cursor(dictionary=True)
        cur.execute("SELECT id, name, dept, username, password_hash FROM doctors WHERE username=%s", (username,))
        doctor = cur.fetchone()
        cur.close()
        db.close()
        if doctor and doctor["password_hash"] and check_password_hash(doctor["password_hash"], password):
            session.clear()
            session["role"] = "doctor"
            session["doctor_id"] = doctor["id"]
            session["username"] = username
            return jsonify({"role": "doctor", "doctor_id": doctor["id"], "name": doctor["name"]})
        return jsonify({"error": "Invalid doctor username or password."}), 401
    return jsonify({"error": "Choose Staff or Doctor login."}), 400

@app.route("/api/logout", methods=["POST"])
def logout():
    session.clear()
    return jsonify({"message": "Logged out."})

@app.route("/api/session")
def get_session():
    if not session.get("role"):
        return jsonify({"logged_in": False})
    result = {"logged_in": True, "role": session["role"], "name": session.get("username", "")}
    if session.get("doctor_id"):
        result["doctor_id"] = session["doctor_id"]
    return jsonify(result)

@app.route("/api/settings/hospital", methods=["GET", "PUT"])
@api_login_required
def hospital_settings():
    # Kept in the browser for this demo; database-backed clinical data remains in MySQL.
    if request.method == "GET":
        return jsonify({"name": session.get("hospital_name", "Healthcare Queue Management")})
    if session.get("role") != "staff":
        return jsonify({"error": "Staff access required."}), 403
    name = ((request.get_json(silent=True) or {}).get("name") or "").strip()
    if not name:
        return jsonify({"error": "Hospital name cannot be empty."}), 400
    session["hospital_name"] = name
    return jsonify({"message": "Hospital name saved.", "name": name})

@app.route("/api/doctors", methods=["GET", "POST"])
@api_login_required
def doctors_api():
    db = get_db()
    cur = db.cursor(dictionary=True)
    if request.method == "GET":
        cur.execute("""SELECT id, name, dept, avg_time AS avg, available, username
                       FROM doctors ORDER BY id""")
        rows = cur.fetchall()
        cur.close(); db.close()
        return jsonify(rows)
    if session.get("role") != "staff":
        cur.close(); db.close()
        return jsonify({"error": "Staff access required."}), 403
    data = request.get_json(silent=True) or {}
    name = (data.get("name") or "").strip()
    dept = (data.get("dept") or "").strip()
    username = (data.get("user") or data.get("username") or "").strip()
    password = data.get("pass") or data.get("password") or ""
    try:
        avg = int(data.get("avg", 10))
    except (TypeError, ValueError):
        avg = 0
    if not name or not dept or not username or len(password) < 4 or avg < 1:
        cur.close(); db.close()
        return jsonify({"error": "Enter doctor name, department, username, password (at least 4 characters) and valid average time."}), 400
    try:
        cur.execute("""INSERT INTO doctors (name, dept, avg_time, available, username, password_hash)
                       VALUES (%s, %s, %s, TRUE, %s, %s)""",
                    (name, dept, avg, username, generate_password_hash(password)))
        db.commit()
        new_id = cur.lastrowid
        return jsonify({"message": "Doctor added.", "id": new_id}), 201
    except Error as e:
        db.rollback()
        return jsonify({"error": "Could not add doctor. Username may already exist."}), 400
    finally:
        cur.close(); db.close()

@app.route("/api/doctors/<int:doctor_id>", methods=["PUT"])
@api_login_required
def update_doctor(doctor_id):
    if session.get("role") != "staff":
        return jsonify({"error": "Staff access required."}), 403
    data = request.get_json(silent=True) or {}
    db = get_db(); cur = db.cursor()
    if "available" in data:
        cur.execute("UPDATE doctors SET available=%s WHERE id=%s", (bool(data["available"]), doctor_id))
    if "avg" in data:
        try:
            avg = int(data["avg"])
        except (TypeError, ValueError):
            avg = 0
        if avg < 1:
            cur.close(); db.close()
            return jsonify({"error": "Average time must be at least 1 minute."}), 400
        cur.execute("UPDATE doctors SET avg_time=%s WHERE id=%s", (avg, doctor_id))
    db.commit(); cur.close(); db.close()
    return jsonify({"message": "Doctor updated."})

@app.route("/api/tokens", methods=["GET", "POST"])
@api_login_required
def tokens_api():
    db = get_db()
    cur = db.cursor(dictionary=True)
    if request.method == "POST":
        if session.get("role") != "staff":
            cur.close(); db.close()
            return jsonify({"error": "Only staff can register patients."}), 403
        data = request.get_json(silent=True) or {}
        required = ["name", "age", "gender", "phone", "doctor_id", "type", "reason"]
        if any(data.get(k) in (None, "") for k in required):
            cur.close(); db.close()
            return jsonify({"error": "Please complete all patient details."}), 400
        try:
            age = int(data["age"]); doctor_id = int(data["doctor_id"])
        except (TypeError, ValueError):
            cur.close(); db.close()
            return jsonify({"error": "Invalid age or doctor."}), 400
        if age < 0 or age > 120 or len(str(data["phone"])) != 10:
            cur.close(); db.close()
            return jsonify({"error": "Enter a valid age and 10-digit phone number."}), 400
        cur.execute("SELECT * FROM doctors WHERE id=%s FOR UPDATE", (doctor_id,))
        doctor = cur.fetchone()
        if not doctor or not doctor["available"]:
            db.rollback(); cur.close(); db.close()
            return jsonify({"error": "Doctor is not available."}), 400
        token_no = f"D{doctor_id}-{doctor['next_token_number']:03d}"
        cur.execute("UPDATE doctors SET next_token_number=next_token_number+1 WHERE id=%s", (doctor_id,))
        cur.execute("""INSERT INTO tokens
            (token_no, patient_name, age, phone, doctor_id, patient_type, gender, reason, status)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,'Waiting')""",
            (token_no, str(data["name"]).strip(), age, str(data["phone"]), doctor_id,
             data["type"], data["gender"], str(data["reason"]).strip()))
        db.commit()
        token_id = cur.lastrowid
        cur.close(); db.close()
        return jsonify({"id": token_id, "token_no": token_no, "message": "Token generated."}), 201

    cur.execute("""SELECT t.*, d.name AS doctor_name, d.dept, d.avg_time
                   FROM tokens t JOIN doctors d ON t.doctor_id=d.id
                   ORDER BY t.registered_at, t.id""")
    rows = cur.fetchall()
    if session.get("role") == "doctor":
        rows = [r for r in rows if r["doctor_id"] == session.get("doctor_id")]
    cur.close(); db.close()
    return jsonify(rows)

@app.route("/api/tokens/<int:token_id>/call", methods=["PUT"])
@api_login_required
def call_token(token_id):
    db = get_db(); cur = db.cursor(dictionary=True)
    cur.execute("SELECT doctor_id FROM tokens WHERE id=%s", (token_id,))
    row = cur.fetchone()
    if not row or not doctor_scope(row["doctor_id"]):
        cur.close(); db.close()
        return jsonify({"error": "Patient not found or access denied."}), 403
    cur.execute("""UPDATE tokens SET status='In Progress', started_at=NOW()
                   WHERE id=%s AND status='Waiting'""", (token_id,))
    if cur.rowcount == 0:
        db.rollback(); cur.close(); db.close()
        return jsonify({"error": "Patient is not waiting."}), 400
    db.commit(); cur.close(); db.close()
    return jsonify({"message": "Patient called."})

@app.route("/api/tokens/<int:token_id>/complete", methods=["PUT"])
@api_login_required
def complete_token(token_id):
    db = get_db(); cur = db.cursor(dictionary=True)
    cur.execute("SELECT doctor_id FROM tokens WHERE id=%s", (token_id,))
    row = cur.fetchone()
    if not row or not doctor_scope(row["doctor_id"]):
        cur.close(); db.close()
        return jsonify({"error": "Patient not found or access denied."}), 403
    cur.execute("""UPDATE tokens SET status='Completed', completed_at=NOW()
                   WHERE id=%s AND status='In Progress'""", (token_id,))
    if cur.rowcount == 0:
        db.rollback(); cur.close(); db.close()
        return jsonify({"error": "No active consultation found."}), 400
    db.commit(); cur.close(); db.close()
    return jsonify({"message": "Consultation completed."})

@app.route("/api/queue/clear", methods=["DELETE"])
@staff_required
def clear_queue():
    db = get_db(); cur = db.cursor()
    cur.execute("""UPDATE tokens SET status='Cancelled'
                   WHERE status IN ('Waiting','In Progress')""")
    db.commit(); cur.close(); db.close()
    return jsonify({"message": "Queue cleared."})

@app.route("/api/history/clear", methods=["DELETE"])
@staff_required
def clear_history():
    db = get_db(); cur = db.cursor()
    cur.execute("DELETE FROM tokens WHERE status IN ('Completed','Cancelled')")
    db.commit(); cur.close(); db.close()
    return jsonify({"message": "History cleared."})

@app.route("/api/staff/password", methods=["PUT"])
@staff_required
def change_staff_password():
    # Demo staff login is configured here; change these values before real deployment.
    data = request.get_json(silent=True) or {}
    if data.get("old_password") != "admin123":
        return jsonify({"error": "Current password is incorrect. The demo staff password is admin123 until changed in the app."}), 400
    new_password = data.get("new_password") or ""
    if len(new_password) < 6:
        return jsonify({"error": "New password must be at least 6 characters."}), 400
    # Store new password in the signed session for this running browser session.
    session["staff_password"] = new_password
    return jsonify({"message": "Password changed for this session. Use admin123 again after server restart."})

if __name__ == "__main__":
    try:
        ensure_default_logins()
    except Error as e:
        print("Database initialization error:", e)
    app.run(debug=True)
