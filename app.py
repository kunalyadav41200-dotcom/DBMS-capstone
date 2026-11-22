from flask import Flask, render_template, request, redirect, url_for, flash
import mysql.connector
import os

app = Flask(__name__)
app.secret_key = os.getenv("APP_SECRET_KEY", "change-this-before-production")

def get_db_connection():
    return mysql.connector.connect(
        host=os.getenv("MYSQL_HOST", "localhost"),
        user=os.getenv("MYSQL_USER", "root"),
        password=os.getenv("MYSQL_PASSWORD", ""),
        database=os.getenv("MYSQL_DATABASE", "payroll_attendance_db")
    )

@app.route("/")
def dashboard():
    db = get_db_connection()
    cur = db.cursor(dictionary=True)
    cur.execute("SELECT COUNT(*) AS total FROM Employee")
    total_employees = cur.fetchone()["total"]
    cur.execute("SELECT COUNT(*) AS total FROM Attendance WHERE attendance_date = CURDATE() AND attendance_status = 'Present'")
    present_today = cur.fetchone()["total"]
    cur.execute("SELECT COUNT(*) AS total FROM `Leave` WHERE leave_status = 'Pending'")
    pending_leaves = cur.fetchone()["total"]
    cur.execute("SELECT COALESCE(SUM(net_salary), 0) AS total FROM Payroll WHERE payroll_month = DATE_FORMAT(CURDATE(), '%Y-%m-01')")
    monthly_payroll = cur.fetchone()["total"]
    cur.execute("SELECT employee_id, full_name, department, designation, employment_status FROM Employee ORDER BY employee_id")
    employees = cur.fetchall()
    cur.close(); db.close()
    return render_template("index.html", total_employees=total_employees, present_today=present_today,
                           pending_leaves=pending_leaves, monthly_payroll=monthly_payroll, employees=employees)

@app.route("/employees")
def employees_page():
    db = get_db_connection(); cur = db.cursor(dictionary=True)
    cur.execute("SELECT * FROM Employee ORDER BY employee_id")
    employees = cur.fetchall()
    cur.close(); db.close()
    return render_template("employees.html", employees=employees)

@app.route("/employees/add", methods=["POST"])
def add_employee():
    db = get_db_connection(); cur = db.cursor()
    try:
        cur.execute("""INSERT INTO Employee (full_name,email,phone,joining_date,department,designation,employment_status)
                      VALUES (%s,%s,%s,%s,%s,%s,'Active')""",
                    (request.form["full_name"], request.form["email"], request.form.get("phone") or None,
                     request.form["joining_date"], request.form["department"], request.form["designation"]))
        db.commit(); flash("Employee added successfully.", "success")
    except mysql.connector.Error as err:
        db.rollback(); flash(f"Could not add employee: {err}", "error")
    finally:
        cur.close(); db.close()
    return redirect(url_for("employees_page"))

@app.route("/attendance")
def attendance_page():
    db = get_db_connection(); cur = db.cursor(dictionary=True)
    cur.execute("""SELECT A.*, E.full_name, E.department FROM Attendance A
                 JOIN Employee E ON A.employee_id=E.employee_id
                 ORDER BY A.attendance_date DESC, A.employee_id DESC""")
    attendance = cur.fetchall()
    cur.execute("SELECT employee_id,full_name FROM Employee WHERE employment_status='Active' ORDER BY full_name")
    employees = cur.fetchall()
    cur.close(); db.close()
    return render_template("attendance.html", attendance=attendance, employees=employees)

@app.route("/attendance/add", methods=["POST"])
def add_attendance():
    db = get_db_connection(); cur = db.cursor()
    try:
        cur.execute("""INSERT INTO Attendance (employee_id,attendance_date,check_in,check_out,attendance_status,late_minutes)
                      VALUES (%s,%s,%s,%s,%s,%s)""",
                    (request.form["employee_id"], request.form["attendance_date"], request.form.get("check_in") or None,
                     request.form.get("check_out") or None, request.form["attendance_status"],
                     int(request.form.get("late_minutes") or 0)))
        db.commit(); flash("Attendance record added.", "success")
    except (mysql.connector.Error, ValueError) as err:
        db.rollback(); flash(f"Could not add attendance: {err}", "error")
    finally:
        cur.close(); db.close()
    return redirect(url_for("attendance_page"))

@app.route("/leaves")
def leaves_page():
    db = get_db_connection(); cur = db.cursor(dictionary=True)
    cur.execute("""SELECT L.*, E.full_name, E.department FROM `Leave` L
                 JOIN Employee E ON L.employee_id=E.employee_id ORDER BY L.leave_id DESC""")
    leaves = cur.fetchall()
    cur.execute("SELECT employee_id,full_name FROM Employee ORDER BY full_name")
    employees = cur.fetchall()
    cur.close(); db.close()
    return render_template("leaves.html", leaves=leaves, employees=employees)

@app.route("/leaves/add", methods=["POST"])
def add_leave():
    db = get_db_connection(); cur = db.cursor()
    try:
        cur.execute("""INSERT INTO `Leave` (employee_id,start_date,end_date,leave_type,leave_status,reason)
                      VALUES (%s,%s,%s,%s,'Pending',%s)""",
                    (request.form["employee_id"], request.form["start_date"], request.form["end_date"],
                     request.form["leave_type"], request.form.get("reason") or None))
        db.commit(); flash("Leave request added as Pending.", "success")
    except mysql.connector.Error as err:
        db.rollback(); flash(f"Could not add leave: {err}", "error")
    finally:
        cur.close(); db.close()
    return redirect(url_for("leaves_page"))

@app.route("/leaves/update/<int:leave_id>", methods=["POST"])
def update_leave(leave_id):
    status = request.form.get("leave_status")
    if status not in ("Approved", "Rejected"):
        flash("Invalid leave status.", "error")
        return redirect(url_for("leaves_page"))
    db = get_db_connection(); cur = db.cursor(dictionary=True)
    try:
        cur.execute("SELECT employee_id,start_date,end_date,leave_status FROM `Leave` WHERE leave_id=%s", (leave_id,))
        row = cur.fetchone()
        if not row:
            flash("Leave request not found.", "error")
        elif row["leave_status"] != "Pending":
            flash("Only pending leave requests can be updated.", "error")
        elif status == "Approved":
            cur.execute("""SELECT leave_id FROM `Leave` WHERE employee_id=%s AND leave_status='Approved'
                          AND start_date <= %s AND end_date >= %s AND leave_id != %s""",
                        (row["employee_id"], row["end_date"], row["start_date"], leave_id))
            if cur.fetchone():
                flash("This leave overlaps an already approved leave.", "error")
            else:
                cur.execute("UPDATE `Leave` SET leave_status=%s WHERE leave_id=%s", (status, leave_id))
                db.commit(); flash("Leave approved.", "success")
        else:
            cur.execute("UPDATE `Leave` SET leave_status=%s WHERE leave_id=%s", (status, leave_id))
            db.commit(); flash("Leave rejected.", "success")
    except mysql.connector.Error as err:
        db.rollback(); flash(f"Leave update failed: {err}", "error")
    finally:
        cur.close(); db.close()
    return redirect(url_for("leaves_page"))

@app.route("/payroll")
def payroll_page():
    db = get_db_connection(); cur = db.cursor(dictionary=True)
    cur.execute("""SELECT P.*, E.full_name, E.department, E.designation FROM Payroll P
                 JOIN Employee E ON P.employee_id=E.employee_id
                 ORDER BY P.payroll_month DESC, E.employee_id""")
    payroll = cur.fetchall()
    cur.close(); db.close()
    return render_template("payroll.html", payroll=payroll)

@app.route("/reports")
def reports_page():
    db = get_db_connection(); cur = db.cursor(dictionary=True)
    cur.execute("""SELECT E.employee_id,E.full_name,YEAR(A.attendance_date) AS attendance_year,
                 MONTH(A.attendance_date) AS attendance_month, COUNT(*) AS total_records,
                 SUM(A.attendance_status='Present') AS present_days,
                 SUM(A.attendance_status='Absent') AS absent_days,
                 SUM(A.attendance_status='Half Day') AS half_days,
                 SUM(A.late_minutes) AS total_late_minutes
                 FROM Employee E JOIN Attendance A ON E.employee_id=A.employee_id
                 GROUP BY E.employee_id,E.full_name,YEAR(A.attendance_date),MONTH(A.attendance_date)
                 ORDER BY attendance_year DESC,attendance_month DESC,E.employee_id""")
    attendance_report = cur.fetchall()
    cur.execute("""SELECT E.full_name,E.department,A.attendance_date,A.check_in,A.late_minutes
                 FROM Attendance A JOIN Employee E ON A.employee_id=E.employee_id
                 WHERE A.late_minutes>0 ORDER BY A.attendance_date DESC""")
    late_report = cur.fetchall()
    cur.execute("""SELECT E.employee_id,E.full_name,P.payroll_month,P.gross_salary,P.deductions,P.tax,
                 P.net_salary,P.payment_status FROM Payroll P JOIN Employee E ON P.employee_id=E.employee_id
                 ORDER BY P.payroll_month DESC,E.employee_id""")
    salary_report = cur.fetchall()
    cur.close(); db.close()
    return render_template("reports.html", attendance_report=attendance_report,
                           late_report=late_report, salary_report=salary_report)

if __name__ == "__main__":
    app.run(debug=True)
