# app.py
import os
import json
import sqlite3
from flask import Flask, render_template_string, request, redirect, url_for, jsonify, Response, session
from datetime import datetime, timedelta
from contextlib import contextmanager
import secrets
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
print("Flask app object created.") # <-- DEBUG LOG
app.secret_key = secrets.token_hex(16)

# ------ DB helpers ------

DB_PATH = '/tmp/budget.db' if os.environ.get('VERCEL') else 'budget.db'
print(f"DATABASE_PATH is set to: {DB_PATH}") # <-- DEBUG LOG

def get_db():
    print("Attempting to get DB connection...") # <-- DEBUG LOG
    try:
        conn = sqlite3.connect(DB_PATH, detect_types=sqlite3.PARSE_DECLTYPES | sqlite3.PARSE_COLNAMES)
        conn.row_factory = sqlite3.Row
        print("DB connection successful.") # <-- DEBUG LOG
        return conn
    except Exception as e:
        print(f"!!! ERROR in get_db: {e}") # <-- DEBUG LOG
        raise

def init_db():
    print("init_db function called.") # <-- DEBUG LOG
    try:
        db_exists = os.path.exists(DB_PATH)
        print(f"Database exists check: {db_exists}") # <-- DEBUG LOG

        with get_db() as conn:
            if not db_exists:
                print("Database does not exist. Creating new schema...") # <-- DEBUG LOG
                conn.execute('PRAGMA foreign_keys = ON;')
                print("Creating tables...") # <-- DEBUG LOG
                conn.execute('''CREATE TABLE users (id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT UNIQUE NOT NULL, password_hash TEXT NOT NULL, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
                conn.execute('''CREATE TABLE income (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, amount DECIMAL(10,2) NOT NULL, month_year VARCHAR(7) NOT NULL, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE, UNIQUE(user_id, month_year))''')
                conn.execute('''CREATE TABLE budgets (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, category VARCHAR(100) NOT NULL, amount DECIMAL(10,2) NOT NULL, month_year VARCHAR(7) NOT NULL, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE, UNIQUE(user_id, category, month_year))''')
                conn.execute('''CREATE TABLE expenses (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, category VARCHAR(100) NOT NULL, amount DECIMAL(10,2) NOT NULL, description TEXT, timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP, FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE)''')
                conn.execute('''CREATE TABLE goals (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, name VARCHAR(100) NOT NULL, target_amount DECIMAL(10,2) NOT NULL, current_amount DECIMAL(10,2) DEFAULT 0, deadline DATE NOT NULL, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE, UNIQUE(user_id, name))''')
                conn.execute('''CREATE TABLE notifications (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, message TEXT NOT NULL, type VARCHAR(50) NOT NULL, is_read BOOLEAN DEFAULT FALSE, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE)''')
                print("All tables created.") # <-- DEBUG LOG
                conn.commit()
                print("Schema committed.") # <-- DEBUG LOG
            else:
                print("Database already exists. Skipping schema creation.") # <-- DEBUG LOG
    except Exception as e:
        print(f"!!! ERROR in init_db: {e}") # <-- DEBUG LOG
        raise

# ------ HTML Templates ------

REGISTER_HTML = """
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Register - Budget Planner</title>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;700&display=swap" rel="stylesheet">
  <style>
    body { font-family: 'Inter', sans-serif; display:flex; min-height:100vh; align-items:center; justify-content:center; background:#f3f5f6; margin:0; }
    .box { background:#fff; padding:32px; border-radius:12px; width:100%; max-width:400px; box-shadow:0 10px 40px rgba(0,0,0,0.08); text-align:center; }
    h2 { margin-top:0; color:#333; }
    input { width:100%; box-sizing: border-box; padding:12px 15px; margin:8px 0; border-radius:8px; border:1px solid #ddd; font-size:1rem; }
    button { width:100%; padding:12px; margin-top:10px; border:none; border-radius:8px; background:#556ee6; color:#fff; cursor:pointer; font-size:1rem; font-weight:500; }
    button:hover { background:#485ec4; }
    .message { margin:15px 0; color:#d9534f; background:#fdecea; padding:10px; border-radius:6px; }
    a { color:#556ee6; text-decoration:none; font-weight:500; }
    a:hover { text-decoration:underline; }
  </style>
</head>
<body>
  <div class="box">
    <h2>Create Your Account</h2>
    {% if login_message %}
      <div class="message">{{ login_message }}</div>
    {% endif %}
    <form method="POST" action="/register">
      <input type="text" name="username" placeholder="Username" required>
      <input type="password" name="password" placeholder="Password" required>
      <input type="password" name="confirm_password" placeholder="Confirm Password" required>
      <button type="submit">Register</button>
    </form>
    <p style="margin-top:20px; color:#666;">Already have an account? <a href="/login">Login here</a></p>
  </div>
</body>
</html>
"""

LOGIN_HTML = """
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Login - Budget Planner</title>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;700&display=swap" rel="stylesheet">
  <style>
    body { font-family: 'Inter', sans-serif; display:flex; min-height:100vh; align-items:center; justify-content:center; background:#f3f5f6; margin:0; }
    .box { background:#fff; padding:32px; border-radius:12px; width:100%; max-width:400px; box-shadow:0 10px 40px rgba(0,0,0,0.08); text-align:center; }
    h2 { margin-top:0; color:#333; }
    input { width:100%; box-sizing: border-box; padding:12px 15px; margin:8px 0; border-radius:8px; border:1px solid #ddd; font-size:1rem; }
    button { width:100%; padding:12px; margin-top:10px; border:none; border-radius:8px; background:#556ee6; color:#fff; cursor:pointer; font-size:1rem; font-weight:500; }
    button:hover { background:#485ec4; }
    .message { margin:15px 0; color:#d9534f; background:#fdecea; padding:10px; border-radius:6px; }
    a { color:#556ee6; text-decoration:none; font-weight:500; }
    a:hover { text-decoration:underline; }
    .tip { margin-top:15px; font-size:0.9em; color:#777; background:#f9f9f9; padding:10px; border-radius:6px; }
  </style>
</head>
<body>
  <div class="box">
    <h2>Welcome Back!</h2>
    {% if login_message %}
      <div class="message">{{ login_message }}</div>
    {% endif %}
    <form method="POST" action="/login">
      <input type="text" name="username" placeholder="Username" required>
      <input type="password" name="password" placeholder="Password" required>
      <button type="submit">Login</button>
    </form>
    <p style="margin-top:20px; color:#666;">Don't have an account? <a href="/register">Register</a></p>
    <p class="tip">Tip: Use <b>demo / demo</b> to automatically create and log into a demo account.</p>
  </div>
</body>
</html>
"""

MAIN_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Advanced Budget & Goal Planner</title>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
  <style>
    :root {
      --primary-color: #556ee6; --primary-hover: #485ec4;
      --success-color: #34c38f; --warning-color: #f1b44c; --danger-color: #f46a6a; --danger-hover: #d9534f;
      --bg-light: #f8f8fb; --card-bg-light: #ffffff; --text-color-light: #495057;
      --border-color-light: #e6e9ec; --muted-text-light: #74788d;
      --bg-dark: #1a2035; --card-bg-dark: #2a3042; --text-color-dark: #e9ecef;
      --border-color-dark: #363b4f; --muted-text-dark: #a6b0cf;
    }
    [data-theme="light"] {
      --bg-color: var(--bg-light); --card-bg: var(--card-bg-light); --text-color: var(--text-color-light);
      --border-color: var(--border-color-light); --muted-text: var(--muted-text-light);
    }
    [data-theme="dark"] {
      --bg-color: var(--bg-dark); --card-bg: var(--card-bg-dark); --text-color: var(--text-color-dark);
      --border-color: var(--border-color-dark); --muted-text: var(--muted-text-dark);
    }
    *, *::before, *::after { box-sizing: border-box; }
    body { margin:0; font-family: 'Inter', sans-serif; background:var(--bg-color); color:var(--text-color); transition: background 0.2s, color 0.2s; }
    .sidebar { width:240px; position:fixed; top:0; left:0; bottom:0; background:var(--card-bg); padding:20px; box-shadow:2px 0 8px rgba(0,0,0,0.05); z-index:100; display:flex; flex-direction:column; border-right: 1px solid var(--border-color); }
    .sidebar-header { font-weight:700; font-size:20px; margin-bottom:24px; color: var(--primary-color); }
    .sidebar-nav { list-style:none; padding:0; margin:0; }
    .sidebar-nav a { display:block; padding:12px 16px; margin:4px 0; border-radius:8px; text-decoration:none; color:var(--muted-text); font-weight:500; transition: background 0.2s, color 0.2s; }
    .sidebar-nav a:hover, .sidebar-nav a.active { background: rgba(85, 110, 230, 0.1); color: var(--primary-color); }
    .main-content { margin-left:240px; padding:24px; }
    .top-bar { display:flex; justify-content:flex-end; gap:16px; align-items:center; margin-bottom:24px; }
    .card { background:var(--card-bg); padding:24px; border-radius:12px; box-shadow:0 0 20px rgba(0,0,0,0.05); margin-bottom:24px; border: 1px solid var(--border-color); }
    h2, h3 { color: var(--text-color); font-weight: 600; margin-top:0; }
    .grid-container { display:grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap:20px; }
    .stat-card { padding:20px; border-radius:8px; background:var(--card-bg); text-align:center; border: 1px solid var(--border-color); }
    .stat-card h3 { margin: 0 0 8px 0; font-size: 2rem; font-weight: 700; color: var(--primary-color); }
    .stat-card p { margin: 0; color: var(--muted-text); font-weight: 500; }
    .notification-bell { position:relative; cursor:pointer; }
    .notification-count { position:absolute; top:-6px; right:-8px; background:var(--danger-color); color:white; border-radius:50%; width:20px; height:20px; font-size:12px; display:flex; align-items:center; justify-content:center; }
    .notification-panel { position:absolute; top:40px; right:0; background:var(--card-bg); border:1px solid var(--border-color); border-radius:8px; width:320px; max-height:400px; overflow-y:auto; box-shadow:0 4px 12px rgba(0,0,0,0.1); z-index:1000; display:none; }
    .notification-item { padding:12px 16px; border-bottom:1px solid var(--border-color); } .notification-item:last-child { border-bottom:none; }
    .notification-item.unread { background:rgba(85, 110, 230, 0.05); }
    .progress-bar { width:100%; height:12px; background:var(--border-color); border-radius:6px; margin:10px 0; overflow:hidden; }
    .progress-fill { height:100%; transition:width 0.3s ease; background-color: var(--primary-color); }
    form { display:flex; flex-direction:column; gap:12px; margin-top:12px; max-width:500px; }
    input, select { padding:10px 12px; border-radius:6px; border:1px solid var(--border-color); background: var(--bg-color); color: var(--text-color); font-size:1rem; }
    button { padding:10px 16px; border-radius:6px; border:none; background:var(--primary-color); color:white; cursor:pointer; font-weight:500; transition: background 0.2s; }
    button:hover { background:var(--primary-hover); }
    .btn-delete { background-color: var(--danger-color); } .btn-delete:hover { background-color: var(--danger-hover); }
    .two-col { display:grid; grid-template-columns:1fr 1fr; gap:12px; }
    .list-item { display:flex; justify-content:space-between; align-items:center; padding:10px 4px; border-bottom:1px solid var(--border-color);}
    #toast-container { position: fixed; bottom: 20px; right: 20px; z-index: 9999; display: flex; flex-direction: column; gap: 10px; }
    .toast { padding: 12px 20px; color: white; border-radius: 8px; box-shadow: 0 4px 12px rgba(0,0,0,0.15); opacity: 0; transform: translateY(20px); transition: opacity 0.3s, transform 0.3s; font-weight: 500; }
    .toast.show { opacity: 1; transform: translateY(0); }
    .toast-success { background-color: var(--success-color); }
    .toast-error { background-color: var(--danger-color); }
    @media (max-width:900px) { .sidebar { display:none; } .main-content { margin-left:0; padding:12px; } }
  </style>
  <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
</head>
<body data-theme="light">
  <nav class="sidebar">
    <div class="sidebar-header">💰 Budget Planner</div>
    <ul class="sidebar-nav">
      <li><a href="#dashboard-section">📊 Dashboard</a></li>
      <li><a href="#income-section">💸 Income</a></li>
      <li><a href="#budgets-section">🏷️ Budgets</a></li>
      <li><a href="#expenses-section">📈 Expenses</a></li>
      <li><a href="#goals-section">🎯 Goals</a></li>
      <li><a href="#analytics-section">📈 Analytics</a></li>
    </ul>
  </nav>

  <main class="main-content">
    <div class="top-bar">
      <div class="notification-bell" onclick="toggleNotifications()">
        <span>🔔</span>
        <span class="notification-count" id="notificationCount">0</span>
        <div class="notification-panel" id="notificationPanel"></div>
      </div>
      <button id="themeToggle" onclick="toggleTheme()">🌙</button>
      <button onclick="logout()">Logout</button>
    </div>

    <div id="toast-container"></div>

    <section id="dashboard-section" class="card">
      <h2>📊 Smart Dashboard</h2>
      <div class="grid-container">
        <div class="stat-card"><h3 id="dashboard-income">₹0</h3><p>Monthly Income</p></div>
        <div class="stat-card"><h3 id="dashboard-expenses">₹0</h3><p>Total Expenses</p></div>
        <div class="stat-card"><h3 id="dashboard-remaining">₹0</h3><p>Remaining Funds</p></div>
        <div class="stat-card"><h3 id="dashboard-savings-rate">0%</h3><p>Savings Rate</p></div>
      </div>
      <div id="budgetAlerts" style="margin-top:24px;"></div>
    </section>

    <section id="income-section" class="card">
        <h2>💸 Set Monthly Income</h2>
        <form onsubmit="event.preventDefault(); setIncome(parseFloat(this.income.value)); this.reset();">
          <input type="number" step="0.01" id="incomeInput" name="income" placeholder="Enter this month's income" required>
          <button type="submit">Save Income</button>
        </form>
        <p style="margin-top:12px; font-size:0.9em; color:var(--muted-text);" id="income-last-updated"></p>
    </section>

    <section id="budgets-section" class="card">
        <h2>🏷️ Manage Budgets</h2>
        <form onsubmit="event.preventDefault(); addBudget(this.category.value, parseFloat(this.amount.value)); this.reset();">
          <div class="two-col">
              <input type="text" name="category" placeholder="Category (e.g., Groceries)" required>
              <input type="number" step="0.01" name="amount" placeholder="Amount" required>
          </div>
          <button type="submit">Add/Update Budget</button>
        </form>
        <h3 style="margin-top:24px;">Current Budgets</h3>
        <div id="budgetList"></div>
    </section>

    <section id="expenses-section" class="card">
      <h2>📈 Add Expense</h2>
      <form onsubmit="event.preventDefault(); addExpense(this.category.value, parseFloat(this.amount.value), this.description.value); this.reset();">
        <div class="two-col">
          <input type="text" name="category" placeholder="Category" required list="budget-categories">
          <datalist id="budget-categories"></datalist>
          <input type="number" step="0.01" name="amount" placeholder="Amount" required>
        </div>
        <input type="text" name="description" placeholder="Description (optional)">
        <button type="submit">Add Expense</button>
      </form>
      <h3 style="margin-top:24px;">Recent Expenses</h3>
      <div id="expenseList"></div>
    </section>

    <section id="goals-section" class="card">
      <h2>🎯 Financial Goals</h2>
      <form onsubmit="event.preventDefault(); addGoal(this.name.value, parseFloat(this.target.value), this.deadline.value); this.reset();">
        <input type="text" name="name" placeholder="Goal Name (e.g., Vacation Fund)" required>
        <div class="two-col">
          <input type="number" step="0.01" name="target" placeholder="Target Amount" required>
          <input type="date" name="deadline" required>
        </div>
        <button type="submit">Add Goal</button>
      </form>

      <h3 style="margin-top:24px;">Contribute to Goal</h3>
      <form onsubmit="event.preventDefault(); addSaving(this.goal_name.value, parseFloat(this.amount.value)); this.reset();">
        <div class="two-col">
          <select name="goal_name" id="goal-selector" required><option value="">Select a Goal</option></select>
          <input type="number" step="0.01" name="amount" placeholder="Amount to Save" required>
        </div>
        <button type="submit">Add Saving</button>
      </form>

      <h3 style="margin-top:24px;">💰 Quick Save Remaining Balance</h3>
      <div style="display:flex; gap:12px; align-items:center;">
        <select id="quick-save-goal-selector" style="flex:1;"><option value="">Select a Goal</option></select>
        <button onclick="addRemainingBalanceToGoal()">Save Remaining Funds</button>
      </div>

      <h3 style="margin-top:24px;">Your Goals</h3>
      <div id="goalList"></div>
    </section>
    
    <section id="analytics-section" class="card">
      <h2>📈 Analytics</h2>
      <h3>Expense Breakdown</h3>
      <div style="max-width: 400px; margin: auto;"><canvas id="expenseChart"></canvas></div>
      <h3 style="margin-top: 30px;">Spending Trends (Last 6 Months)</h3>
      <div><canvas id="trendChart"></canvas></div>
    </section>

  </main>

  <script>
    let state = { income: {}, budgets: {}, expenses: [], goals: {}, notifications: [] };
    let expenseChart, trendChart;
    
    // UPDATE: Fixed timestamp to always use Indian Standard Time
    function formatTimestamp(isoString) {
        if (!isoString) return '';
        const options = {
            year: 'numeric', month: 'short', day: 'numeric',
            hour: 'numeric', minute: '2-digit', hour12: true,
            timeZone: 'Asia/Kolkata'
        };
        return new Date(isoString).toLocaleString('en-IN', options);
    }

    // --- API Helpers ---
    async function apiCall(url, method = 'GET', data = null) {
        const options = { method, headers: { 'Content-Type': 'application/json' } };
        if (data) options.body = JSON.stringify(data);
        const res = await fetch(url, options);
        if (!res.ok) {
            const error = await res.json();
            throw new Error(error.error || 'An unknown error occurred');
        }
        return res.json();
    }

    // --- State Management ---
    async function loadState() {
      try {
        state = await apiCall("/api/data");
        refreshUI();
      } catch (err) {
        showToast(err.message, 'error');
        if (err.message.includes("Not authorized")) window.location.href = "/login";
      }
    }

    // --- Actions ---
    async function setIncome(amount) {
      try { await apiCall("/api/income", "POST", { amount }); await loadState(); showToast('Income updated!', 'success');
      } catch (e) { showToast(e.message, 'error'); }
    }
    async function addBudget(category, amount) {
      try { await apiCall("/api/budget", "POST", { category, amount }); await loadState(); showToast('Budget updated!', 'success');
      } catch (e) { showToast(e.message, 'error'); }
    }
    async function addExpense(category, amount, description = "") {
      try { await apiCall("/api/expense", "POST", { category, amount, description }); await loadState(); showToast('Expense recorded!', 'success');
      } catch (e) { showToast(e.message, 'error'); }
    }
    async function addGoal(name, target, deadline) {
      try { await apiCall("/api/goal", "POST", { name, target, deadline }); await loadState(); showToast('New goal set!', 'success');
      } catch (e) { showToast(e.message, 'error'); }
    }
    async function addSaving(goal_name, amount) {
      if (!goal_name) { showToast('Please select a goal first.', 'error'); return; }
      try { await apiCall("/api/saving", "POST", { goal_name, amount }); await loadState(); showToast(`₹${amount.toFixed(2)} added to "${goal_name}"`, 'success');
      } catch (e) { showToast(e.message, 'error'); }
    }
    // NEW: Delete actions
    async function deleteBudget(category) {
      if (!confirm(`Are you sure you want to delete the "${category}" budget?`)) return;
      try { await apiCall("/api/budget/delete", "POST", { category }); await loadState(); showToast('Budget deleted.', 'success');
      } catch (e) { showToast(e.message, 'error'); }
    }
    async function deleteGoal(name) {
      if (!confirm(`Are you sure you want to delete the "${name}" goal?`)) return;
      try { await apiCall("/api/goal/delete", "POST", { name }); await loadState(); showToast('Goal deleted.', 'success');
      } catch (e) { showToast(e.message, 'error'); }
    }
    // NEW: Quick Save action
    function addRemainingBalanceToGoal() {
        const goalName = document.getElementById('quick-save-goal-selector').value;
        if (!goalName) { showToast('Please select a goal from the dropdown.', 'error'); return; }
        
        const currentMonthExpenses = state.expenses.filter(e => e.timestamp && e.timestamp.startsWith(new Date().toISOString().slice(0, 7)));
        const totalExpenses = currentMonthExpenses.reduce((sum, e) => sum + e.amount, 0);
        const income = state.income.amount || 0;
        const remaining = income - totalExpenses;

        if (remaining <= 0) {
            showToast('No remaining balance to save.', 'warning');
            return;
        }
        addSaving(goalName, remaining);
    }

    // --- UI Rendering ---
    function refreshUI() {
        const currentMonthExpenses = state.expenses.filter(e => e.timestamp && e.timestamp.startsWith(new Date().toISOString().slice(0, 7)));
        updateDashboardStats(currentMonthExpenses);
        refreshExpenseList(state.expenses);
        refreshBudgetList();
        refreshGoalList();
        refreshSelectors();
        updateCharts(currentMonthExpenses);
        displayBudgetAlerts(currentMonthExpenses);
        updateNotificationCount();
    }

    function updateDashboardStats(expenses) {
      const totalExpenses = expenses.reduce((sum, e) => sum + e.amount, 0);
      const income = state.income.amount || 0;
      const remaining = income - totalExpenses;
      const savingsRate = income > 0 ? ((remaining / income) * 100).toFixed(1) : 0;
      document.getElementById('dashboard-income').textContent = `₹${income.toFixed(2)}`;
      document.getElementById('dashboard-expenses').textContent = `₹${totalExpenses.toFixed(2)}`;
      document.getElementById('dashboard-remaining').textContent = `₹${remaining.toFixed(2)}`;
      document.getElementById('dashboard-savings-rate').textContent = `${savingsRate > 0 ? savingsRate : 0}%`;
      const incomeUpdatedElem = document.getElementById('income-last-updated');
      if (state.income && state.income.updated_at) {
          incomeUpdatedElem.textContent = `Last updated: ${formatTimestamp(state.income.updated_at)}`;
      } else {
          incomeUpdatedElem.textContent = 'No income set for this month yet.';
      }
    }
    
    function refreshExpenseList(allExpenses) {
      const list = document.getElementById('expenseList');
      if (!allExpenses || allExpenses.length === 0) { list.innerHTML = "<p>No expenses recorded yet.</p>"; return; }
      list.innerHTML = allExpenses.slice(0, 10).map(e => `
        <div class="list-item">
            <div>
                <strong style="display:block;">${e.category}</strong>
                <span style="font-size:0.9em; color:var(--muted-text);">${e.description || formatTimestamp(e.timestamp)}</span>
            </div>
            <span style="font-weight:600; font-size:1.1em;">₹${e.amount.toFixed(2)}</span>
        </div>`).join('');
    }

    // NEW: Function to render the budget list with delete buttons
    function refreshBudgetList() {
        const container = document.getElementById('budgetList');
        const budgets = state.budgets || {};
        const keys = Object.keys(budgets);
        if (keys.length === 0) { container.innerHTML = "<p>No budgets set for this month.</p>"; return; }
        container.innerHTML = keys.map(k => {
            const b = budgets[k];
            return `<div class="list-item">
                        <span><strong>${k}</strong>: ₹${b.amount.toFixed(2)}</span>
                        <button class="btn-delete" onclick="deleteBudget('${k}')">Delete</button>
                    </div>`;
        }).join('');
    }

    function refreshGoalList() {
        const container = document.getElementById('goalList');
        const goals = state.goals || {};
        const keys = Object.keys(goals);
        if (keys.length === 0) { container.innerHTML = "<p>No goals set yet.</p>"; return; }
        container.innerHTML = keys.map(k => {
            const g = goals[k];
            const pct = g.target > 0 ? Math.min(100, (g.current / g.target) * 100) : 0;
            return `<div style="margin-bottom:16px; padding-bottom:12px; border-bottom: 1px solid var(--border-color);">
                        <div style="display:flex; justify-content:space-between; align-items:center;">
                            <strong>${k}</strong>
                            <button class="btn-delete" onclick="deleteGoal('${k}')">Delete</button>
                        </div>
                        <div style="color:var(--muted-text); font-size:0.9em;">Deadline: ${g.deadline || 'N/A'}</div>
                        <div style="display:flex; justify-content:space-between; color:var(--muted-text); font-size:0.9em;">
                            <span>₹${g.current.toFixed(2)}</span>
                            <span>₹${g.target.toFixed(2)}</span>
                        </div>
                        <div class="progress-bar"><div class="progress-fill" style="width:${pct}%;"></div></div>
                    </div>`;
        }).join('');
    }

    function refreshSelectors() {
        const budgetDatalist = document.getElementById('budget-categories');
        const budgetCategories = Object.keys(state.budgets || {});
        budgetDatalist.innerHTML = budgetCategories.map(cat => `<option value="${cat}">`).join('');
        
        const goalSelector = document.getElementById('goal-selector');
        const quickSaveSelector = document.getElementById('quick-save-goal-selector');
        const goalNames = Object.keys(state.goals || {});
        const goalOptions = '<option value="">Select a Goal</option>' + goalNames.map(name => `<option value="${name}">${name}</option>`).join('');
        goalSelector.innerHTML = goalOptions;
        quickSaveSelector.innerHTML = goalOptions;
    }
    
    function displayBudgetAlerts(expenses) {
        const container = document.getElementById('budgetAlerts');
        let html = '<h3>Budget Status</h3>';
        const budgetKeys = Object.keys(state.budgets);
        if(budgetKeys.length === 0) { container.innerHTML = '<h3>Budget Status</h3><p>No budgets set for this month.</p>'; return; }
        budgetKeys.forEach(category => {
            const budgetAmount = state.budgets[category].amount;
            const spent = expenses.filter(e => e.category === category).reduce((sum, e) => sum + e.amount, 0);
            const pct = budgetAmount > 0 ? Math.min(100, (spent / budgetAmount) * 100) : 0;
            const statusColor = pct >= 100 ? 'var(--danger-color)' : pct > 80 ? 'var(--warning-color)' : 'var(--success-color)';
            html += `<div style="margin-bottom:12px;">
                        <strong>${category}</strong>
                        <div style="display:flex; justify-content:space-between; color:var(--muted-text); font-size:0.9em;">
                           <span>Spent: ₹${spent.toFixed(2)}</span>
                           <span>Budget: ₹${budgetAmount.toFixed(2)}</span>
                        </div>
                        <div class="progress-bar"><div class="progress-fill" style="width:${pct}%; background-color:${statusColor};"></div></div>
                     </div>`;
        });
        container.innerHTML = html;
    }
    
    function toggleNotifications() {
        const panel = document.getElementById('notificationPanel');
        const isVisible = panel.style.display === 'block';
        panel.style.display = isVisible ? 'none' : 'block';
        if (!isVisible) loadNotifications();
    }
    async function loadNotifications() {
        state.notifications = await apiCall("/api/notifications");
        updateNotificationCount();
        renderNotificationPanel();
    }
    function updateNotificationCount() {
        const count = state.notifications.filter(n => !n.is_read).length;
        document.getElementById('notificationCount').textContent = count;
        document.getElementById('notificationCount').style.display = count > 0 ? 'flex' : 'none';
    }
    function renderNotificationPanel() {
        const panel = document.getElementById('notificationPanel');
        if (!state.notifications.length) { panel.innerHTML = "<div style='padding:12px;'>No new notifications</div>"; return; }
        panel.innerHTML = state.notifications.map(n => `
            <div class="notification-item ${n.is_read ? '' : 'unread'}">
                <div style="font-size:14px;">${n.message}</div>
                <div style="font-size:11px; color:var(--muted-text); margin-top:6px;">${formatTimestamp(n.created_at)}</div>
            </div>`).join('');
    }
    function showToast(message, type = 'success') {
        const container = document.getElementById('toast-container');
        const toast = document.createElement('div');
        toast.className = `toast toast-${type}`;
        toast.textContent = message;
        container.appendChild(toast);
        setTimeout(() => { toast.classList.add('show'); }, 10);
        setTimeout(() => { toast.classList.remove('show'); setTimeout(() => toast.remove(), 300); }, 3000);
    }
    async function updateCharts(currentMonthExpenses) {
        const pieCtx = document.getElementById("expenseChart")?.getContext("2d");
        if (pieCtx) {
            const categoryTotals = {};
            currentMonthExpenses.forEach(e => { categoryTotals[e.category] = (categoryTotals[e.category] || 0) + e.amount; });
            if (expenseChart) expenseChart.destroy();
            expenseChart = new Chart(pieCtx, { type: "pie", data: { labels: Object.keys(categoryTotals), datasets: [{ data: Object.values(categoryTotals) }] } });
        }
        const trendCtx = document.getElementById("trendChart")?.getContext("2d");
        if (trendCtx) {
            const trends = await apiCall("/api/analytics/trends");
            if (trendChart) trendChart.destroy();
            trendChart = new Chart(trendCtx, {
                type: 'line',
                data: { labels: trends.labels, datasets: [{ label: 'Expenses', data: trends.expenses, tension: 0.2, borderColor: 'var(--primary-color)', pointBackgroundColor: 'var(--primary-color)' }] },
                options: { responsive:true, scales:{ y:{ beginAtZero:true } } }
            });
        }
    }
    function toggleTheme() {
        const currentTheme = document.body.getAttribute('data-theme');
        const newTheme = currentTheme === 'light' ? 'dark' : 'light';
        document.body.setAttribute('data-theme', newTheme);
        localStorage.setItem('theme', newTheme);
    }
    window.onload = async function () {
        const savedTheme = localStorage.getItem('theme') || 'light';
        document.body.setAttribute('data-theme', savedTheme);
        await loadState();
        await loadNotifications();
    };
    function logout() { window.location.href = "/logout"; }
    </script>
</body>
</html>
"""


init_db()

@app.route('/')
def home():
    if not session.get('logged_in'):
        return redirect(url_for('login'))
    return render_template_string(MAIN_HTML)

# (Keep all your other @app.route functions here)
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        with get_db() as conn:
            user = conn.execute('SELECT * FROM users WHERE username = ?', (username,)).fetchone()
            if not user and username == "demo" and password == "demo":
                try:
                    password_hash = generate_password_hash("demo")
                    conn.execute('INSERT INTO users (username, password_hash) VALUES (?, ?)', (username, password_hash))
                    conn.commit()
                    user = conn.execute('SELECT * FROM users WHERE username = ?', (username,)).fetchone()
                except sqlite3.IntegrityError:
                    user = conn.execute('SELECT * FROM users WHERE username = ?', (username,)).fetchone()
            if user and check_password_hash(user['password_hash'], password):
                session['logged_in'] = True
                session['user_id'] = user['id']
                return redirect(url_for('home'))
            else:
                return render_template_string(LOGIN_HTML, login_message="❌ Invalid credentials")
    return render_template_string(LOGIN_HTML)

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')
        if not all([username, password, confirm_password]):
            return render_template_string(REGISTER_HTML, login_message="❌ Please fill out all fields.")
        if password != confirm_password:
            return render_template_string(REGISTER_HTML, login_message="❌ Passwords don't match")
        if len(password) < 6:
            return render_template_string(REGISTER_HTML, login_message="❌ Password must be at least 6 characters")
        try:
            with get_db() as conn:
                password_hash = generate_password_hash(password)
                conn.execute('INSERT INTO users (username, password_hash) VALUES (?, ?)', (username, password_hash))
                conn.commit()
                return redirect(url_for('login'))
        except sqlite3.IntegrityError:
            return render_template_string(REGISTER_HTML, login_message="❌ Username already exists")
    return render_template_string(REGISTER_HTML)

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

def check_session():
    if not session.get('logged_in'):
        return jsonify({"error": "Not authorized"}), 401
    return None, None

@app.route('/api/data')
def get_data():
    error_response, status_code = check_session()
    if error_response: return error_response, status_code
    return jsonify(load_user_data(session.get('user_id')))

@app.route('/api/income', methods=['POST'])
def set_income():
    error_response, status_code = check_session()
    if error_response: return error_response, status_code
    amount = request.json.get('amount')
    if not isinstance(amount, (int, float)) or amount < 0:
        return jsonify({"error": "Invalid amount"}), 400
    current_month = datetime.now().strftime('%Y-%m')
    with get_db() as conn:
        conn.execute('''
            INSERT INTO income (user_id, amount, month_year, created_at) VALUES (?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(user_id, month_year) DO UPDATE SET amount = excluded.amount, created_at = CURRENT_TIMESTAMP
        ''', (session.get('user_id'), amount, current_month))
        conn.commit()
    return jsonify({"success": True})

@app.route('/api/budget', methods=['POST'])
def add_budget():
    error_response, status_code = check_session()
    if error_response: return error_response, status_code
    category = request.json.get('category')
    amount = request.json.get('amount')
    current_month = datetime.now().strftime('%Y-%m')
    with get_db() as conn:
        conn.execute('''
            INSERT INTO budgets (user_id, category, amount, month_year) VALUES (?, ?, ?, ?)
            ON CONFLICT(user_id, category, month_year) DO UPDATE SET amount = excluded.amount
        ''', (session.get('user_id'), category, amount, current_month))
        conn.commit()
    return jsonify({"success": True})

@app.route('/api/budget/delete', methods=['POST'])
def delete_budget():
    error_response, status_code = check_session()
    if error_response: return error_response, status_code
    category = request.json.get('category')
    current_month = datetime.now().strftime('%Y-%m')
    with get_db() as conn:
        conn.execute('DELETE FROM budgets WHERE user_id = ? AND category = ? AND month_year = ?',
                     (session.get('user_id'), category, current_month))
        conn.commit()
    return jsonify({"success": True})

@app.route('/api/expense', methods=['POST'])
def add_expense():
    error_response, status_code = check_session()
    if error_response: return error_response, status_code
    category = request.json.get('category')
    amount = request.json.get('amount')
    description = request.json.get('description', '')
    with get_db() as conn:
        conn.execute('INSERT INTO expenses (user_id, category, amount, description) VALUES (?, ?, ?, ?)',
                     (session.get('user_id'), category, amount, description))
        conn.commit()
    check_overspending(session.get('user_id'), category)
    return jsonify({"success": True})

@app.route('/api/goal', methods=['POST'])
def add_goal():
    error_response, status_code = check_session()
    if error_response: return error_response, status_code
    name = request.json.get('name')
    target_amount = request.json.get('target')
    deadline = request.json.get('deadline')
    try:
        with get_db() as conn:
            conn.execute('INSERT INTO goals (user_id, name, target_amount, deadline) VALUES (?, ?, ?, ?)',
                         (session.get('user_id'), name, target_amount, deadline))
            conn.commit()
        return jsonify({"success": True})
    except sqlite3.IntegrityError:
        return jsonify({"error": f"A goal with the name '{name}' already exists."}), 400

@app.route('/api/goal/delete', methods=['POST'])
def delete_goal():
    error_response, status_code = check_session()
    if error_response: return error_response, status_code
    name = request.json.get('name')
    with get_db() as conn:
        conn.execute('DELETE FROM goals WHERE user_id = ? AND name = ?',
                     (session.get('user_id'), name))
        conn.commit()
    return jsonify({"success": True})

@app.route('/api/saving', methods=['POST'])
def add_saving():
    error_response, status_code = check_session()
    if error_response: return error_response, status_code
    goal_name = request.json.get('goal_name')
    amount = request.json.get('amount')
    with get_db() as conn:
        conn.execute('UPDATE goals SET current_amount = current_amount + ? WHERE user_id = ? AND name = ?',
                     (amount, session.get('user_id'), goal_name))
        conn.commit()
    return jsonify({"success": True})

@app.route('/api/notifications')
def get_notifications():
    error_response, status_code = check_session()
    if error_response: return error_response, status_code
    with get_db() as conn:
        notifications = conn.execute('SELECT message, type, is_read, created_at FROM notifications WHERE user_id = ? ORDER BY created_at DESC LIMIT 50', (session.get('user_id'),)).fetchall()
    return jsonify([dict(n) for n in notifications])

@app.route('/api/analytics/trends')
def get_trends():
    error_response, status_code = check_session()
    if error_response: return error_response, status_code
    return jsonify(generate_trend_analysis(session.get('user_id')))

def load_user_data(user_id):
    with get_db() as conn:
        current_month = datetime.now().strftime('%Y-%m')
        income = conn.execute('SELECT amount, created_at FROM income WHERE user_id = ? AND month_year = ?', (user_id, current_month)).fetchone()
        budgets = conn.execute('SELECT category, amount FROM budgets WHERE user_id = ? AND month_year = ?', (user_id, current_month)).fetchall()
        expenses = conn.execute('SELECT category, amount, description, timestamp FROM expenses WHERE user_id = ? ORDER BY timestamp DESC', (user_id,)).fetchall()
        goals = conn.execute('SELECT name, target_amount, current_amount, deadline FROM goals WHERE user_id = ? ORDER BY created_at DESC', (user_id,)).fetchall()
        notifications = conn.execute('SELECT message, type, is_read, created_at FROM notifications WHERE user_id = ? AND is_read = 0 ORDER BY created_at DESC LIMIT 10', (user_id,)).fetchall()
    return {
        'income': { 'amount': float(income['amount']) if income else 0, 'updated_at': str(income['created_at']) if income else None },
        'budgets': { b['category']: {'amount': float(b['amount'])} for b in budgets },
        'expenses': [ {'category': e['category'], 'amount': float(e['amount']), 'description': e['description'] or '', 'timestamp': str(e['timestamp'])} for e in expenses ],
        'goals': { g['name']: { 'target': float(g['target_amount']), 'current': float(g['current_amount']), 'deadline': str(g['deadline']) } for g in goals },
        'notifications': [ {'message': n['message'], 'type': n['type'], 'is_read': bool(n['is_read']), 'created_at': str(n['created_at'])} for n in notifications ]
    }

def check_overspending(user_id, category):
    with get_db() as conn:
        current_month = datetime.now().strftime('%Y-%m')
        budget = conn.execute('SELECT amount FROM budgets WHERE user_id = ? AND category = ? AND month_year = ?', (user_id, category, current_month)).fetchone()
        if not budget: return
        month_start = datetime.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        total_spent_row = conn.execute('SELECT SUM(amount) as total FROM expenses WHERE user_id = ? AND category = ? AND timestamp >= ?', (user_id, category, month_start)).fetchone()
        total_spent = total_spent_row['total'] or 0
        budget_amount = float(budget['amount'])
        if total_spent > budget_amount:
            overspent_amount = total_spent - budget_amount
            message = f"Overspending alert! You've exceeded your '{category}' budget by ₹{overspent_amount:.2f}"
            conn.execute('INSERT INTO notifications (user_id, message, type) VALUES (?, ?, ?)', (user_id, message, 'danger'))
            conn.commit()

def generate_trend_analysis(user_id):
    with get_db() as conn:
        six_months_ago = (datetime.now() - timedelta(days=180)).strftime('%Y-%m-01')
        trends = conn.execute('''
            SELECT strftime('%Y-%m', timestamp) as month, SUM(amount) as total_expenses
            FROM expenses WHERE user_id = ? AND timestamp >= ?
            GROUP BY month ORDER BY month ''', (user_id, six_months_ago)).fetchall()
    return {'labels': [t['month'] for t in trends], 'expenses': [float(t['total_expenses']) for t in trends]}

if __name__ == '__main__':
    app.run(debug=True, port=5001)